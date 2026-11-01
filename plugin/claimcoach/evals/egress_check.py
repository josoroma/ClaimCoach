"""The zero-egress check: a full case flow opens no connection beyond loopback.

Implements: US-12.4 (one denial case runs from upload through extraction, diagnosis, draft, and
export through the ``plugin_api`` router in this process; meanwhile the socket audit hook watches
this process (the ``plugin_api`` half), the worker's own hook writes ``worker/egress.jsonl``, and
``lsof`` samples the process groups of the worker and of every running model server; any
non-loopback connection or attempt fails the check, and the report says which observers covered
each process). Rules: BR-1 and NFR-5 (no outbound call carries case content; the check runs
only when no confirmed download is in progress, the one case where the worker may
reach out), BR-11 (the model servers are the worker's own, found through ``/models/status``),
BR-14 (a finding is a process, an address, and a port).

``lsof`` is a fixed argv with numeric hosts and ports (``-nP``), run off the event loop with a
bounded wait; a sample sees every connection a process holds at that instant, including ones its
own code did not open (a library's telemetry), which the audit hook alone could miss in a model
server. A model server is watched by ``lsof`` only: a connection it opens and closes between two
samples, or a DNS lookup (macOS resolves through mDNSResponder over a Unix socket), is not seen.
The report's ``observers`` say so for each process; the check is fail-closed for everything else
(the worker's audit must be recording, an unreadable observation is a finding, a sampling failure
stops the flow).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Final, Literal

from claimcoach.api.client import WorkerClient, WorkerError
from claimcoach.egress import (
    EGRESS_AUDIT,
    EgressAudit,
    EgressRecord,
    EgressStatus,
    is_loopback,
    read_records,
)
from claimcoach.evals.datasets import DenialCase
from claimcoach.evals.flow import GatewayDriver, run_case
from claimcoach.evals.types import EgressFinding, EgressReport
from claimcoach.models.types import ModelRole, ModelsStatusResponse
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.launcher import worker_status

__all__ = [
    "LSOF",
    "EgressAuditOffError",
    "EgressLogError",
    "EgressToolError",
    "app_processes",
    "parse_lsof",
    "preconditions",
    "run_egress_check",
    "sample_lsof",
]

LSOF: Final = "/usr/sbin/lsof"
LSOF_TIMEOUT: Final = 15.0
"""Seconds one ``lsof`` sample may take."""
SAMPLE_INTERVAL: Final = 0.5
"""Seconds between samples."""
CASE_ROLES: Final = frozenset(ModelRole) - {ModelRole.TRANSCRIPTION}
"""Roles a case flow uses from upload to export (transcription is a separate, after-hours job)."""

Sampler = Callable[[Sequence[int]], Awaitable[str]]
Processes = Callable[[], Coroutine[Any, Any, dict[int, str]]]
"""The process groups to watch now, as ``group -> name``."""
WorkerAudit = Callable[[], Coroutine[Any, Any, EgressStatus]]
Observer = Literal["audit", "lsof"]


class EgressToolError(RuntimeError):
    """``lsof`` is missing, failed, or timed out, so connections cannot be sampled."""

    message: ClassVar[str] = f"{LSOF} could not sample connections"

    def __init__(self) -> None:
        """Fixed message."""
        super().__init__(self.message)


class EgressLogError(EgressToolError):
    """The worker's ``egress.jsonl`` exists but cannot be read, so its records are unknown."""

    message: ClassVar[str] = (
        "the worker's egress record file (worker/egress.jsonl) cannot be read; "
        "check its owner and mode (0600)"
    )


class EgressAuditOffError(EgressToolError):
    """The worker's socket audit is not recording, so its attempts would go unseen."""

    message: ClassVar[str] = (
        "the worker's egress audit is not recording; restart it (make stop, make start)"
    )


def parse_lsof(output: str) -> list[tuple[int, int, str, int | None]]:
    """Read the remote end of every connection in ``lsof -F pgn`` output.

    Args:
        output: Lines ``p<pid>``, ``g<process group>``, ``f<fd>``, ``n<local>-><remote>``;
            listening sockets and unconnected datagram sockets have no ``->`` and are skipped.

    Returns:
        ``(process group, pid, remote host, remote port)`` per connection. A remote that cannot be
        read keeps an empty host, which is not loopback, so it fails the check.
    """
    connections: list[tuple[int, int, str, int | None]] = []
    pid = group = 0
    for line in output.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = group = int(line[1:])
        elif line.startswith("g") and line[1:].isdigit():
            group = int(line[1:])
        elif line.startswith("n") and "->" in line:
            remote = line.split("->", 1)[1].split(" ", 1)[0]
            host, _colon, port = remote.rpartition(":")
            number = int(port) if port.isdigit() else None
            connections.append((group, pid, host.strip("[]") or remote, number))
    return connections


def _run_lsof(groups: Sequence[int]) -> str:
    argv = [LSOF, "-nP", "-a", "-g", ",".join(map(str, groups)), "-i", "-F", "pgn"]
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=LSOF_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EgressToolError from exc
    # 1 with nothing on stderr: no process of the groups holds an internet socket (or is gone).
    if done.returncode == 0 or (done.returncode == 1 and not done.stderr.strip()):
        return done.stdout
    raise EgressToolError


async def sample_lsof(groups: Sequence[int]) -> str:
    """One ``lsof`` sample of the internet sockets of every process in ``groups``.

    The worker and each model server start their own session, so a group is a server and every
    helper process it forks. Runs off the event loop.

    Raises:
        EgressToolError: ``lsof`` could not run or reported an error.
    """
    if not groups:
        return ""
    return await asyncio.to_thread(_run_lsof, groups)


def preconditions(status: ModelsStatusResponse) -> list[str]:
    """Why a full flow cannot be checked now: missing weights, or a download in progress.

    Returns:
        ``<role>: <reason>`` per problem; empty when the check may run.
    """
    problems: list[str] = []
    for model in status.models:
        if model.acquire == "downloading":
            problems.append(f"{model.role}: {model.acquire}")
        if model.role in CASE_ROLES and model.weights != "present":
            problems.append(f"{model.role}: weights {model.weights}")
    return problems


def app_processes(client: WorkerClient, config: WorkerConfig) -> Processes:
    """The running worker and each model server it runs, by process group, refreshed per call.

    A worker that stops answering keeps its last known model servers in the next sample.
    """
    known: dict[int, str] = {}

    async def current() -> dict[int, str]:
        handle = worker_status(config)
        found = {handle.pid: "worker"} if handle is not None else {}
        try:
            status = await client.models_status()
        except WorkerError:
            return found | {pid: name for pid, name in known.items() if name != "worker"}
        known.clear()
        known.update({m.pid: f"model:{m.role}" for m in status.models if m.pid is not None})
        return found | known

    return current


def _audit_finding(record: EgressRecord) -> EgressFinding:
    return EgressFinding(
        source="audit",
        process=record.process,
        pid=record.pid,
        event=record.event,
        host=record.host,
        port=record.port,
    )


def _log_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise EgressLogError from exc


def _observers(name: str) -> list[Observer]:
    if name == "worker":
        return ["audit", "lsof"]
    return ["lsof"]


async def _sample(
    processes: Processes,
    sampler: Sampler,
    findings: list[EgressFinding],
    watched: dict[str, list[Observer]],
) -> None:
    try:
        names = await processes()
    except Exception as exc:
        raise EgressToolError from exc
    watched.update({f"{name}:{group}": _observers(name) for group, name in names.items()})
    for group, pid, host, port in parse_lsof(await sampler(sorted(names))):
        if not is_loopback(host):
            findings.append(
                EgressFinding(
                    source="lsof",
                    process=names.get(group, "unknown"),
                    pid=pid,
                    event="connect",
                    host=host,
                    port=port,
                )
            )


async def run_egress_check(  # noqa: PLR0913 - the flow, its case, and each injectable observer
    gateway: GatewayDriver,
    case: DenialCase,
    *,
    processes: Processes,
    worker_log: Path,
    worker_audit: WorkerAudit,
    sampler: Sampler = sample_lsof,
    audit: EgressAudit = EGRESS_AUDIT,
    interval: float = SAMPLE_INTERVAL,
    wall: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[EgressReport, list[str]]:
    """Run ``case`` through the gateway router while watching every process for egress.

    Args:
        gateway: The in-process ``plugin_api`` driver.
        case: The denial case to run.
        processes: The worker and model-server process groups to sample.
        worker_log: The worker's ``egress.jsonl``; only records appended during the flow count.
        worker_audit: The worker's ``GET /egress``; the check refuses a worker whose audit is off,
            and an attempt it could not record during the flow is a finding.
        sampler: Takes one connection sample of some process groups (tests).
        audit: This process's audit hook (tests).
        interval: Seconds between samples.
        wall: The current UTC time (tests).

    Returns:
        The report, and the worker case ID of the eval case when it could not be purged.

    Raises:
        EgressToolError: The worker's audit is off, or connections could not be sampled, so
            nothing was proven. A sampling failure stops the flow at once.
    """
    before = await worker_audit()
    if not before.audit:
        raise EgressAuditOffError
    offset = _log_size(worker_log)
    records: list[EgressRecord] = []
    findings: list[EgressFinding] = []
    watched: dict[str, list[Observer]] = {f"plugin_api:{os.getpid()}": ["audit"]}
    samples = 0
    done = asyncio.Event()

    async def watch() -> None:
        nonlocal samples
        while not done.is_set():
            await _sample(processes, sampler, findings, watched)
            samples += 1
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(done.wait(), interval)
        await _sample(processes, sampler, findings, watched)  # always one after the flow
        samples += 1

    started = wall()
    audit.start("plugin_api", records.append)
    watcher = asyncio.create_task(watch())
    flow = asyncio.create_task(run_case(gateway, case, until="export"))
    try:
        await asyncio.wait({flow, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if not flow.done():  # the watcher only ends early by failing: stop the flow now
            flow.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await flow
            watcher.result()
        done.set()
        await watcher
        result = flow.result()
    finally:
        done.set()
        audit.stop()
        for task in (flow, watcher):
            task.cancel()
    try:
        logged = read_records(worker_log, offset)
    except OSError as exc:
        raise EgressLogError from exc
    findings += [_audit_finding(r) for r in records + logged]
    after = await worker_audit()
    if after.dropped > before.dropped:  # attempts the worker saw but could not write down
        findings.append(
            EgressFinding(
                source="audit", process="worker", pid=0, event="connect", host="unrecorded"
            )
        )
    completed = result.error_code is None and result.exported is not None
    report = EgressReport(
        started_at=started,
        finished_at=wall(),
        flow_completed=completed,
        error_code=result.error_code,
        processes=sorted(watched),
        observers=dict(sorted(watched.items())),
        samples=samples,
        findings=findings,
        passed=completed and not findings,
    )
    return report, [] if result.discarded or result.case_id is None else [result.case_id]
