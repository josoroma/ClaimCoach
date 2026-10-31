"""Confirmed model downloads and local reranker conversion.

Implements: US-2.4 (``Acquirer`` over ``DownloadRequest``, ``ConversionRequest``, and
``AcquireResult`` from ``claimcoach.models.types``; missing models are reported by
``ModelManager.status``). Rules: BR-1 (the only outbound calls are downloads the user confirmed;
``confirm: false`` starts nothing), BR-11 (files land under ``MODELS_HOME``), BR-14 (job output
goes to a 0600 log, never to a response).

Downloads and conversions take minutes, so each runs as a background job; the status the settings
page polls shows ``downloading`` / ``converting`` / ``failed`` and flips ``weights`` to
``present`` when the files land.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from claimcoach.models.manager import ModelError, ModelManager, terminate
from claimcoach.models.types import (
    AcquireResult,
    AcquireState,
    ConversionRequest,
    DownloadRequest,
    ModelRole,
)

__all__ = ["Acquirer", "ConversionUnavailableError"]

_log = logging.getLogger("claimcoach.models")


class ConversionUnavailableError(ModelError):
    """The role is not converted locally, or its source model is not present yet."""

    code = "conversion_unavailable"
    status_code = 409


class Acquirer:
    """Runs at most one download or conversion job per target directory.

    Jobs are keyed by the directory they write, not by role: phi_detection and classification
    share ``Qwen3-8B-4bit``, and two ``hf download`` runs must never write one folder at once.

    Args:
        models: The model manager; supplies the registry, ``MODELS_HOME``, the state dir, and
            whether any model server is resident.
        term_grace: Seconds a job gets to exit after SIGTERM on shutdown.
    """

    def __init__(self, models: ModelManager, *, term_grace: float = 10.0) -> None:
        """Start with no jobs."""
        self.models = models
        self.term_grace = term_grace
        self._running: dict[Path, AcquireState] = {}
        self._failed: set[ModelRole] = set()
        self._processes: dict[Path, asyncio.subprocess.Process] = {}
        self._tasks: dict[Path, asyncio.Task[None]] = {}

    @property
    def _home(self) -> Path:
        return self.models.models_home

    def _dirs(self, role: ModelRole) -> set[Path]:
        """The directories a role's jobs write: its model dir and, if converted, its source."""
        spec = self.models.registry.roles[role]
        dirs = {spec.model_path(self._home)}
        if spec.convert is not None:
            dirs.add(self._home / spec.convert.source_dir)
        return dirs

    def _sharing(self, target: Path) -> set[ModelRole]:
        return {role for role in self.models.registry.roles if target in self._dirs(role)}

    def states(self) -> dict[ModelRole, AcquireState]:
        """Return the running or failed job of each role that has one."""
        states: dict[ModelRole, AcquireState] = dict.fromkeys(self._failed, "failed")
        for target, kind in self._running.items():
            states.update(dict.fromkeys(self._sharing(target), kind))
        return states

    def _in_progress(self, role: ModelRole) -> bool:
        return not self._dirs(role).isdisjoint(self._running)

    async def download(self, request: DownloadRequest) -> AcquireResult:
        """Download what ``request.role`` needs, if the user confirmed.

        Converted roles download their source model; conversion is a separate confirmed step.

        Returns:
            ``declined`` (nothing ran), ``present`` (nothing to fetch), ``in_progress``, or
            ``started``.
        """
        role = request.role
        if not request.confirm:
            return AcquireResult(role=role, outcome="declined")
        if self._in_progress(role):
            return AcquireResult(role=role, outcome="in_progress")
        if self._downloaded(role):
            return AcquireResult(role=role, outcome="present")
        spec = self.models.registry.roles[role]
        if spec.convert is None:
            repo_id, target = str(spec.repo_id), spec.model_dir
        else:
            repo_id, target = spec.convert.source_repo_id, spec.convert.source_dir
        argv = _fill(
            self.models.registry.acquire.download,
            models_home=str(self._home),
            repo_id=repo_id,
            target=str(self._home / target),
        )
        env = {**os.environ, "HF_HUB_DISABLE_TELEMETRY": "1"}
        self.models.begin_job(self._home / target, exclusive=False)
        self._launch(role, "downloading", self._home / target, argv, env)
        return AcquireResult(role=role, outcome="started")

    async def convert(self, request: ConversionRequest) -> AcquireResult:
        """Convert ``request.role``'s source model to local MLX, if the user confirmed.

        Returns:
            ``declined``, ``in_progress``, ``present``, or ``started``.

        Raises:
            ConversionUnavailableError: The role is not converted, or its source is missing.
            ModelBusyError: A model server is resident; converting an 8B needs ~16 GB. While the
                conversion runs, every model load queues behind it.
        """
        role = request.role
        if not request.confirm:
            return AcquireResult(role=role, outcome="declined")
        if self._in_progress(role):
            return AcquireResult(role=role, outcome="in_progress")
        spec = self.models.registry.roles[role]
        if spec.convert is None or not spec.source_present(self._home):
            raise ConversionUnavailableError
        if spec.weights(self._home) == "present":
            return AcquireResult(role=role, outcome="present")
        target = spec.model_path(self._home)
        # Conversion needs ~16 GB: refuse while a model is resident, and make every load queue
        # until it ends (raises ModelBusyError).
        self.models.begin_job(target, exclusive=True)
        argv = _fill(
            self.models.registry.acquire.convert,
            models_home=str(self._home),
            source=str(self._home / spec.convert.source_dir),
            target=str(target),
            q_bits=str(spec.convert.q_bits),
        )
        # Local conversion never needs the network (BR-1).
        env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
        self._launch(role, "converting", target, argv, env)
        return AcquireResult(role=role, outcome="started")

    async def shutdown(self) -> None:
        """Stop running jobs; the worker calls it on exit. ``hf download`` resumes next time."""
        processes = list(self._processes.values())
        await asyncio.gather(*(terminate(process, self.term_grace) for process in processes))
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def _downloaded(self, role: ModelRole) -> bool:
        spec = self.models.registry.roles[role]
        if spec.convert is None:
            return spec.weights(self._home) == "present"
        return bool(spec.source_present(self._home))

    def _launch(
        self,
        role: ModelRole,
        kind: AcquireState,
        target: Path,
        argv: list[str],
        env: Mapping[str, str],
    ) -> None:
        self._failed -= self._sharing(target)
        self._running[target] = kind
        self._tasks[target] = asyncio.create_task(self._run(role, kind, target, argv, env))

    async def _run(
        self,
        role: ModelRole,
        kind: AcquireState,
        target: Path,
        argv: list[str],
        env: Mapping[str, str],
    ) -> None:
        log_fd = os.open(
            self.models.state_dir / f"acquire-{role.value}.log",
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        os.fchmod(log_fd, 0o600)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=subprocess.DEVNULL,
                stdout=log_fd,
                stderr=subprocess.STDOUT,
                env=dict(env),
                start_new_session=True,
            )
        except OSError:
            succeeded = False
        else:
            self._processes[target] = process
            succeeded = await process.wait() == 0
        finally:
            os.close(log_fd)
        self._processes.pop(target, None)
        del self._running[target]
        await self.models.end_job(target, exclusive=kind == "converting")
        done = (
            self._downloaded(role)
            if kind == "downloading"
            else self.models.registry.roles[role].weights(self._home) == "present"
        )
        if succeeded and done:
            _log.info("%s for role %s finished", kind, role.value)
        else:
            self._failed |= self._sharing(target)
            _log.warning("%s for role %s failed; see acquire-%s.log", kind, role.value, role.value)


def _fill(template: list[str], **values: str) -> list[str]:
    return [part.format_map(values) for part in template]
