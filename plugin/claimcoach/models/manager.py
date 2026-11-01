"""Run the local model servers: lazy start, health check, idle unload, memory guard.

Implements: US-2.2 (``ModelManager``: start on first use, serve only once ``/v1/models`` is
healthy, idle sweep, typed status), US-2.3 (admission through ``MemoryGuard``; blocked loads are
``queued``, idle blockers are evicted, waits are bounded by ``queue_timeout_s``). Rules: BR-11
(servers bind ``127.0.0.1`` on ports 18201-18219; weights read in place), BR-12, BR-14 (logs carry
roles, ports, and PIDs only; US-3.4: the idle sweep logs under its job ID), PRD §7.9 (the worker
owns these processes), US-11.1 (servers start with umask 077 and get a ``{logs}`` folder in the
data dir, so ``mlx_audio.server``'s files are owner-only and never land in the install dir).

All server state is guarded by one ``asyncio.Condition`` so the memory guard always sees every
server. A server is *resident* while it is starting, ready, or stopping: a stopping process still
holds its memory until it exits. A process group whose only members are zombies counts as gone:
macOS answers ``killpg`` on it with ``EPERM``, and a zombie holds no memory or port.
"""

from __future__ import annotations

import asyncio
import contextvars
import itertools
import os
import signal
import socket
import subprocess
import time
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Final

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from claimcoach.api.models import ErrorCode
from claimcoach.logs import get_logger, job_id_var
from claimcoach.models.memory_guard import MemoryGuard, SizeTier
from claimcoach.models.registry import ModelRegistry, ModelSpec
from claimcoach.models.types import (
    AcquireState,
    ModelRole,
    ModelsStatusResponse,
    ModelState,
    ModelStatus,
)
from claimcoach.worker.config import LOOPBACK

__all__ = [
    "HEALTH_PATH",
    "EndpointProvider",
    "ModelBusyError",
    "ModelEndpoint",
    "ModelError",
    "ModelManager",
    "ModelUnavailableError",
    "terminate",
]

HEALTH_PATH: Final = "/v1/models"
POLL_INTERVAL: Final = 0.25
"""Seconds between health probes while a server starts."""

SWEEP_INTERVAL_MAX: Final = 30.0
SIGKILL_SETTLE: Final = 2.0
"""Seconds to wait for SIGKILLed orphans to disappear."""
_PS: Final = "/bin/ps"
_GROUP_GONE: Final = (ProcessLookupError, PermissionError)
"""What ``killpg`` raises when no member of a group can take a signal: ``ESRCH`` once the group is
gone, and on macOS ``EPERM`` while its only members are zombies (exited, not yet reaped by their
parent or launchd). Only groups this worker started are signalled, so ``EPERM`` never means
another user's processes."""
_RESIDENT: Final = frozenset({ModelState.STARTING, ModelState.READY, ModelState.STOPPING})
_SERVER_ENV: Final = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
"""Model servers never reach the network; only confirmed downloads do (BR-1)."""

_log = get_logger("claimcoach.models")


class ModelError(Exception):
    """A model request failed; ``code`` and ``status_code`` give the envelope to answer with."""

    code: ClassVar[ErrorCode]
    status_code: ClassVar[int]


class ModelUnavailableError(ModelError):
    """The role's server could not be started or failed its health check."""

    code = "model_unavailable"
    status_code = 503


class ModelBusyError(ModelError):
    """The role's server is in use, or the memory guard kept the load queued too long."""

    code = "model_busy"
    status_code = 409


@dataclass(frozen=True, slots=True)
class ModelEndpoint:
    """Where a caller sends OpenAI-compatible requests for a role while it holds ``use()``.

    Attributes:
        role: The role.
        base_url: OpenAI-style base URL, e.g. ``http://127.0.0.1:18202/v1``.
        model_path: The model directory the server was started with; ``mlx_vlm.server`` resolves
            a request's ``model`` field as a path (US-5.2).
    """

    role: ModelRole
    base_url: str
    model_path: str | None = None


EndpointProvider = Callable[[ModelRole], AbstractAsyncContextManager[ModelEndpoint]]
"""``ModelManager.use``: holds a role's server for the duration of the context."""


class _Record(BaseModel):
    """A running server as recorded in ``servers.json`` for orphan reaping.

    ``markers`` are strings its command line must still contain: the model path and the port
    option. A server may re-execute itself (``mtplx serve`` becomes ``python -m
    mtplx.server.openai``), so the exact argv is not a reliable identity, but these survive.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    pid: int
    markers: list[str] = Field(min_length=2)


_RECORDS: Final = TypeAdapter(dict[int, _Record])


@dataclass(eq=False)
class _Server:
    """One server process; roles that share a port share it."""

    spec: ModelSpec
    roles: tuple[ModelRole, ...]
    state: ModelState = ModelState.UNLOADED
    process: asyncio.subprocess.Process | None = None
    markers: list[str] = field(default_factory=list)
    refcount: int = 0
    """Requests holding ``use()``; a pinned server is never swept or evicted."""
    waiting: int = 0
    """Requests queued on the memory guard."""
    last_used: float = 0.0
    start_attempts: int = 0

    @property
    def port(self) -> int:
        return self.spec.port

    @property
    def resident(self) -> bool:
        return self.state in _RESIDENT


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((LOOPBACK, port)) == 0


def _command_line(pid: int) -> str:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [_PS, "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def _markers(argv: list[str], model: Path, port: int) -> list[str]:
    """The model path and the ``--port N`` pair (or the bare port) of a server's argv."""
    port_text = str(port)
    pairs = [f"{flag} {value}" for flag, value in itertools.pairwise(argv)]
    port_marker = next((pair for pair in pairs if pair.endswith(f" {port_text}")), port_text)
    return [str(model), port_marker]


def _group_alive(pgid: int) -> bool:
    """Whether a member of group ``pgid`` is still running (a zombie is not)."""
    try:
        os.killpg(pgid, 0)
    except _GROUP_GONE:
        return False
    return True


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def terminate(process: asyncio.subprocess.Process, grace: float) -> None:
    """Stop a process this worker started, and its process group: SIGTERM, then SIGKILL.

    The group is SIGKILLed once the leader has exited (or after ``grace``), so helpers that
    outlive the leader do not keep memory or the port. A group ID is not reused while any member
    of the group exists.

    Args:
        process: A child started with ``start_new_session=True`` (its PID is its group ID).
        grace: Seconds to wait after SIGTERM.
    """
    if process.returncode is not None:
        return  # reaped before we got here: its PID may belong to someone else now
    with suppress(*_GROUP_GONE):
        os.killpg(process.pid, signal.SIGTERM)
    with suppress(TimeoutError):
        await asyncio.wait_for(process.wait(), grace)
    with suppress(*_GROUP_GONE):
        os.killpg(process.pid, signal.SIGKILL)
    await process.wait()
    # Wait until the whole group is gone so its port is free before anything restarts it.
    deadline = asyncio.get_running_loop().time() + SIGKILL_SETTLE
    while _group_alive(process.pid) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)


async def _healthy(port: int) -> bool:
    """Return whether ``GET /v1/models`` answers 200 with an OpenAI model list."""
    try:
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
            response = await client.get(f"http://{LOOPBACK}:{port}{HEALTH_PATH}")
    except httpx.HTTPError:
        return False
    if response.status_code != httpx.codes.OK:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and isinstance(body.get("data"), list)


class ModelManager:
    """Owns every ClaimCoach model server process.

    Args:
        registry: The loaded ``models.yaml``.
        models_home: ``MODELS_HOME``; weights are read from here in place.
        state_dir: Where server logs (``<port>.log``, mode 0600) and ``servers.json`` live.
        clock: Monotonic clock for idle accounting; tests inject a fake.
        term_grace: Seconds a server gets to exit after SIGTERM before SIGKILL.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        models_home: Path,
        state_dir: Path,
        clock: Callable[[], float] = time.monotonic,
        term_grace: float = 10.0,
    ) -> None:
        """Index the servers ``registry`` describes; nothing is started (lazy start)."""
        self.registry = registry
        self.models_home = models_home
        self.state_dir = state_dir
        self.term_grace = term_grace
        self._clock = clock
        self._guard = MemoryGuard.from_registry(registry)
        self._cond = asyncio.Condition()
        self._servers = {
            port: _Server(spec=registry.roles[roles[0]], roles=tuple(roles))
            for port, roles in registry.servers().items()
        }
        self._by_role = {role: s for s in self._servers.values() for role in s.roles}
        self._tasks: set[asyncio.Task[None]] = set()
        self._jobs: set[Path] = set()
        """Directories a download or conversion is writing (US-2.4)."""
        self._exclusive_jobs = 0
        """Running jobs that need the memory of a large model (conversion); loads queue behind."""
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    @property
    def records_path(self) -> Path:
        """``servers.json``: the running servers, for reaping after a worker crash."""
        return self.state_dir / "servers.json"

    # --- Public API ----------------------------------------------------------------------------

    @asynccontextmanager
    async def use(self, role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        """Hold the role's server for one request, starting it first if needed.

        While the context is open the server is pinned: the idle sweep and the memory guard leave
        it running.

        Args:
            role: The role the request needs.

        Yields:
            The loopback endpoint to call.

        Raises:
            ModelUnavailableError: The model is missing, or its server did not become healthy.
            ModelBusyError: The memory guard kept the load queued past ``queue_timeout_s``.
        """
        server = self._by_role[role]
        model = server.spec.model_path(self.models_home)
        if model in self._jobs or server.spec.weights(self.models_home) == "missing":
            raise ModelUnavailableError  # never serve files a job is still writing
        await self._acquire(server)
        try:
            yield ModelEndpoint(
                role=role, base_url=f"http://{LOOPBACK}:{server.port}/v1", model_path=str(model)
            )
        finally:
            await self._release(server)

    async def unload(self, role: ModelRole) -> ModelStatus:
        """Stop the role's server now if no request is using it.

        Raises:
            ModelBusyError: A request is using the server.
        """
        server = self._by_role[role]
        async with self._cond:
            if server.refcount:
                raise ModelBusyError
        await self._stop(server, ModelState.UNLOADED, only_if_idle=True)
        return self.role_status(role)

    async def sweep_idle(self) -> list[int]:
        """Stop every unpinned server unused for longer than ``idle_timeout_s``.

        Returns:
            Ports of the servers that were stopped.
        """
        cutoff = self._clock() - self.registry.idle_timeout_s
        async with self._cond:
            idle = [
                s
                for s in self._servers.values()
                if s.state is ModelState.READY and not s.refcount and s.last_used < cutoff
            ]
        stopped = [
            s.port
            for s in idle
            if await self._stop(s, ModelState.UNLOADED, only_if_idle=True, used_before=cutoff)
        ]
        for port in stopped:
            _log.info("model server on port %d unloaded after idle timeout", port)
        return stopped

    async def run_sweeper(self, interval: float | None = None) -> None:
        """Run ``sweep_idle`` forever; the worker lifespan starts and cancels it."""
        period = interval or min(SWEEP_INTERVAL_MAX, self.registry.idle_timeout_s / 4)
        job_id_var.set("idle-sweep")  # this task's own context: every sweep log line carries it
        while True:
            await asyncio.sleep(period)
            try:
                await self.sweep_idle()
            except Exception as exc:  # noqa: BLE001 - one failed sweep must not end the sweeper
                _log.error("idle sweep failed: %s", type(exc).__name__)

    def any_resident(self) -> bool:
        """Return whether any model server is starting, running, or stopping."""
        return any(s.resident for s in self._servers.values())

    def begin_job(self, target: Path, *, exclusive: bool) -> None:
        """Register a download or conversion writing ``target`` (US-2.4).

        No server is started from ``target`` until ``end_job``. An exclusive job (conversion)
        also makes every load queue until it ends, as if a ``runs_alone`` server were resident.

        Raises:
            ModelBusyError: ``exclusive`` and a model server or another exclusive job is resident.
        """
        if exclusive:
            if self.any_resident() or self._exclusive_jobs:
                raise ModelBusyError
            self._exclusive_jobs += 1
        self._jobs.add(target)

    async def end_job(self, target: Path, *, exclusive: bool) -> None:
        """Forget a job registered with ``begin_job`` and wake queued loads."""
        async with self._cond:
            self._jobs.discard(target)
            if exclusive:
                self._exclusive_jobs -= 1
            self._cond.notify_all()

    def role_status(
        self, role: ModelRole, acquire: Mapping[ModelRole, AcquireState] | None = None
    ) -> ModelStatus:
        """Return the typed status of one role."""
        server = self._by_role[role]
        spec = self.registry.roles[role]
        return ModelStatus(
            role=role,
            state=server.state,
            port=spec.port,
            pid=server.process.pid if server.process is not None else None,
            queued_requests=server.waiting,
            tier_b=spec.tier_b,
            model_dir=spec.model_dir,
            weights=spec.weights(self.models_home),
            source_present=spec.source_present(self.models_home),
            venv_present=spec.venv_present(self.models_home),
            acquire=(acquire or {}).get(role),
        )

    def status(
        self, acquire: Mapping[ModelRole, AcquireState] | None = None
    ) -> ModelsStatusResponse:
        """Return the status of every role, in registry order.

        Args:
            acquire: Running or failed download/conversion jobs by role (US-2.4).
        """
        return ModelsStatusResponse(
            idle_timeout_s=self.registry.idle_timeout_s,
            models=[self.role_status(role, acquire) for role in self.registry.roles],
        )

    async def shutdown(self) -> None:
        """Stop every server this manager started, all at once; the worker calls it on exit."""
        await asyncio.gather(*self._tasks, return_exceptions=True)
        running = [s for s in self._servers.values() if s.process is not None]
        await asyncio.gather(*(self._stop(s, ModelState.UNLOADED) for s in running))

    def reap_orphans(self) -> list[int]:
        """Stop servers a previous worker left running, then forget them.

        A recorded PID is signalled only if ``ps`` still shows its model path and port, so a PID
        the OS reused for another program is never touched. All orphans get SIGTERM first and
        share one ``term_grace`` deadline before SIGKILL, so reaping stays well inside the
        launcher's readiness timeout.

        Returns:
            PIDs that were stopped.
        """
        try:
            records = _RECORDS.validate_json(self.records_path.read_bytes())
        except FileNotFoundError:
            return []
        except ValidationError:
            records = {}
        reaped = []
        for record in records.values():
            command = _command_line(record.pid)
            if command and all(marker in command for marker in record.markers):
                with suppress(*_GROUP_GONE):
                    os.killpg(record.pid, signal.SIGTERM)
                reaped.append(record.pid)
        self._wait_gone(reaped, self.term_grace)
        for pid in reaped:
            with suppress(*_GROUP_GONE):
                os.killpg(pid, signal.SIGKILL)
        self._wait_gone(reaped, SIGKILL_SETTLE)  # free the ports before the worker serves
        self.records_path.unlink()
        return reaped

    @staticmethod
    def _wait_gone(pids: list[int], timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while any(_alive(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(0.05)

    # --- Admission (US-2.2 lazy start, US-2.3 memory guard) ------------------------------------

    async def _acquire(self, server: _Server) -> None:
        """Admit and pin ``server`` for one request; cancellation leaves no state behind."""
        async with self._cond:
            must_start = await self._admit(server)  # pins the server when it returns
        try:
            healthy = await (self._start(server) if must_start else self._check(server))
        except BaseException:
            await self._release(server)  # e.g. the caller's timeout cancelled us mid-start
            raise
        if not healthy:
            await self._release(server)
            raise ModelUnavailableError

    async def _admit(self, server: _Server) -> bool:
        """Wait (lock held) until ``server`` is ready or may start, then pin it.

        A waiting request does not pin the server, so the guard can still evict it for a load
        queued behind it.

        Returns:
            Whether this task must start the server.
        """
        deadline = asyncio.get_running_loop().time() + self.registry.queue_timeout_s
        queued = False
        waited_on: int | None = None  # the start attempt this task waited for, if any
        try:
            while True:
                state = server.state
                if state is ModelState.READY:
                    if self._blocks_queued_load(server):
                        # Let the load queued behind this server go first instead of re-pinning
                        # it; otherwise steady traffic would starve that load.
                        await self._wait(deadline)
                        continue
                    server.refcount += 1
                    return False
                if state is ModelState.STARTING:
                    waited_on = server.start_attempts
                if state in (ModelState.STARTING, ModelState.STOPPING):
                    await self._wait(deadline)
                    continue
                if state is ModelState.UNHEALTHY and waited_on == server.start_attempts:
                    raise ModelUnavailableError  # share the outcome of the start we waited on
                blockers = self._blockers(server)
                if not blockers and not self._exclusive_jobs:
                    server.state = ModelState.STARTING  # reserves residency before unlocking
                    server.start_attempts += 1
                    server.refcount += 1
                    return True
                if not queued:
                    queued = True
                    server.waiting += 1
                server.state = ModelState.QUEUED
                self._evict_idle(blockers)
                await self._wait(deadline)
        finally:
            if queued:
                server.waiting -= 1
                if not server.waiting and server.state is ModelState.QUEUED:
                    server.state = ModelState.UNLOADED

    async def _wait(self, deadline: float) -> None:
        remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        try:
            await asyncio.wait_for(self._cond.wait(), remaining)
        except TimeoutError:
            raise ModelBusyError from None

    def _blockers(self, server: _Server) -> list[_Server]:
        resident = [SizeTier.of(s.spec) for s in self._servers.values() if s.resident]
        blocking = self._guard.blockers(SizeTier.of(server.spec), resident)
        return [self._servers[tier.port] for tier in blocking]

    async def _release(self, server: _Server) -> None:
        async with self._cond:
            server.refcount -= 1
            server.last_used = self._clock()
            if not server.refcount and self._blocks_queued_load(server):
                self._spawn(self._stop(server, ModelState.UNLOADED, only_if_idle=True))
            self._cond.notify_all()

    def _evict_idle(self, blockers: list[_Server]) -> None:
        """Stop, in the background, the blockers no request is using (US-2.3)."""
        for blocker in blockers:
            if not blocker.refcount and blocker.state is ModelState.READY:
                self._spawn(self._stop(blocker, ModelState.UNLOADED, only_if_idle=True))

    def _blocks_queued_load(self, server: _Server) -> bool:
        return any(
            other.state is ModelState.QUEUED and server in self._blockers(other)
            for other in self._servers.values()
        )

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> None:
        # A clean context: background work never logs under the request that started it.
        task = asyncio.create_task(coro, context=contextvars.Context())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # --- Process lifecycle ---------------------------------------------------------------------

    async def _start(self, server: _Server) -> bool:
        """Start ``server`` (state already ``starting``) and wait until it is healthy.

        If the caller is cancelled, the half-started process is stopped and the server is left
        ``unloaded``, so neither the role nor the memory guard stays wedged.
        """
        try:
            return await self._launch(server)
        except BaseException:
            await self._stop(server, ModelState.UNLOADED)
            raise

    async def _launch(self, server: _Server) -> bool:
        logs = self.state_dir / "server-logs"
        logs.mkdir(mode=0o700, exist_ok=True)
        argv = server.spec.argv(self.models_home, LOOPBACK, logs)
        if _port_in_use(server.port):
            # Never adopt a server ClaimCoach did not start, even one that looks healthy.
            _log.warning("port %d is already in use; not starting its model server", server.port)
            await self._stop(server, ModelState.UNHEALTHY)
            return False
        log_fd = os.open(
            self.state_dir / f"{server.port}.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
        )
        os.fchmod(log_fd, 0o600)  # an older log may have been created with a wider mode
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=subprocess.DEVNULL,
                stdout=log_fd,
                stderr=subprocess.STDOUT,
                env={**os.environ, **_SERVER_ENV},
                start_new_session=True,
                # Files a server writes (mlx_audio.server's decoded call in /tmp) are owner-only.
                umask=0o077,
            )
        except OSError:
            _log.warning("model server for port %d could not be executed", server.port)
            await self._stop(server, ModelState.UNHEALTHY)
            return False
        finally:
            os.close(log_fd)
        async with self._cond:
            server.process = process
            server.markers = _markers(argv, server.spec.model_path(self.models_home), server.port)
            self._save_records()
        _log.info("model server on port %d started (pid %d)", server.port, process.pid)
        if await self._wait_healthy(server, process):
            async with self._cond:
                server.state = ModelState.READY
                server.last_used = self._clock()
                self._cond.notify_all()
            return True
        _log.warning("model server on port %d did not become healthy", server.port)
        await self._stop(server, ModelState.UNHEALTHY)
        return False

    async def _wait_healthy(self, server: _Server, process: asyncio.subprocess.Process) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + server.spec.startup_timeout_s
        while loop.time() < deadline:
            if process.returncode is not None:
                return False
            if await _healthy(server.port):
                return True
            await asyncio.sleep(POLL_INTERVAL)
        return False

    async def _check(self, server: _Server) -> bool:
        """Health-check a ready server before handing it out; stop it if it fails."""
        if await _healthy(server.port):
            return True
        _log.warning("model server on port %d failed its health check", server.port)
        await self._stop(server, ModelState.UNHEALTHY)
        return False

    async def _stop(
        self,
        server: _Server,
        final: ModelState,
        *,
        only_if_idle: bool = False,
        used_before: float | None = None,
    ) -> bool:
        """Stop ``server`` and leave it in ``final``.

        With ``only_if_idle`` the idle check and the switch to ``stopping`` happen in one critical
        section, so a request can never pin a server that is about to be killed.

        Returns:
            Whether the server was stopped.
        """
        async with self._cond:
            if only_if_idle and (
                server.refcount
                or server.state is not ModelState.READY
                or (used_before is not None and server.last_used >= used_before)
            ):
                return False
            process = server.process
            server.state = ModelState.STOPPING
            self._cond.notify_all()
        if process is not None:
            await terminate(process, self.term_grace)
        async with self._cond:
            server.process = None
            server.markers = []
            server.state = final
            self._save_records()
            self._cond.notify_all()
        return True

    def _save_records(self) -> None:
        records = {
            s.port: _Record(pid=s.process.pid, markers=s.markers)
            for s in self._servers.values()
            if s.process is not None
        }
        tmp = self.records_path.with_name(f".{self.records_path.name}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(_RECORDS.dump_json(records))
        tmp.replace(self.records_path)
