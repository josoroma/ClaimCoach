"""Confirmed model downloads.

Implements: US-2.4 (``Acquirer`` over ``DownloadRequest`` and ``AcquireResult`` from
``claimcoach.models.types``; missing models are reported by ``ModelManager.status``), US-14.1 (no
local conversion: the reranker it built is gone). Rules: BR-1 (the only outbound calls are downloads
the user confirmed; ``confirm: false`` starts nothing), BR-11 (files land under ``MODELS_HOME``),
BR-14 (job output goes to a 0600 log, never to a response), US-3.4 (log lines carry the job ID).

Downloads take minutes, so each runs as a background job; the status the settings page polls shows
``downloading`` / ``failed`` and flips ``weights`` to ``present`` when the files land.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from claimcoach.logs import get_logger, job_id_var
from claimcoach.models.manager import ModelManager, terminate
from claimcoach.models.types import AcquireResult, AcquireState, DownloadRequest, ModelRole

__all__ = ["Acquirer"]

_log = get_logger("claimcoach.models")


class Acquirer:
    """Runs at most one download job per target directory.

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

    def _dir(self, role: ModelRole) -> Path:
        """The directory a role's download writes: its model dir."""
        return self.models.registry.roles[role].model_path(self._home)

    def _sharing(self, target: Path) -> set[ModelRole]:
        return {role for role in self.models.registry.roles if self._dir(role) == target}

    def states(self) -> dict[ModelRole, AcquireState]:
        """Return the running or failed job of each role that has one."""
        states: dict[ModelRole, AcquireState] = dict.fromkeys(self._failed, "failed")
        for target, kind in self._running.items():
            states.update(dict.fromkeys(self._sharing(target), kind))
        return states

    def _in_progress(self, role: ModelRole) -> bool:
        return self._dir(role) in self._running

    async def download(self, request: DownloadRequest) -> AcquireResult:
        """Download ``request.role``'s model, if the user confirmed.

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
        target = self._dir(role)
        argv = _fill(
            self.models.registry.acquire.download,
            models_home=str(self._home),
            repo_id=self.models.registry.roles[role].repo_id,
            target=str(target),
        )
        env = {**os.environ, "HF_HUB_DISABLE_TELEMETRY": "1"}
        self.models.begin_job(target)
        self._launch(role, target, argv, env)
        return AcquireResult(role=role, outcome="started")

    async def shutdown(self) -> None:
        """Stop running jobs; the worker calls it on exit. ``hf download`` resumes next time."""
        processes = list(self._processes.values())
        await asyncio.gather(*(terminate(process, self.term_grace) for process in processes))
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def _downloaded(self, role: ModelRole) -> bool:
        return self.models.registry.roles[role].weights(self._home) == "present"

    def _launch(
        self, role: ModelRole, target: Path, argv: list[str], env: Mapping[str, str]
    ) -> None:
        self._failed -= self._sharing(target)
        self._running[target] = "downloading"
        self._tasks[target] = asyncio.create_task(
            self._run(role, target, argv, env), context=contextvars.Context()
        )

    async def _run(
        self, role: ModelRole, target: Path, argv: list[str], env: Mapping[str, str]
    ) -> None:
        job_id_var.set(f"downloading-{role.value}")  # this task's own context (US-3.4)
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
        await self.models.end_job(target)
        if succeeded and self._downloaded(role):
            _log.info("downloading for role %s finished", role.value)
        else:
            self._failed |= self._sharing(target)
            _log.warning(
                "downloading for role %s failed; see acquire-%s.log", role.value, role.value
            )


def _fill(template: list[str], **values: str) -> list[str]:
    return [part.format_map(values) for part in template]
