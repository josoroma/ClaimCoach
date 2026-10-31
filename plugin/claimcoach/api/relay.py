"""Relay a worker job's progress events to the desktop half, from inside the gateway.

Implements: US-5.2 (each ``CaseProgressEvent`` the worker records is broadcast as
``plugin.claimcoach.case.progress``; when the worker stops answering, a ``failed`` event says so).
Rules: PC-4 (only the gateway can call ``broadcast_plugin_event``, so it long-polls the worker),
BR-14 (events are PHI-free by construction, US-3.4).

A relay is a background task of the gateway's event loop, one per job (a second Process of a
running job joins it instead of replaying its events); a dict holds each one until it ends so it is
not garbage-collected mid-run. Every wait is bounded: 20 s per poll, and the relay outlives the
job's own deadline by five minutes; if the job has still not ended then, a ``failed`` event with
``processing_timeout`` says so.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Final

from claimcoach.api.client import WorkerClient, WorkerError
from claimcoach.api.models import ErrorCode
from claimcoach.cases.extraction import JOB_DEADLINE, JobStarted
from claimcoach.events import CaseProgressEvent, EventSink, publish

__all__ = ["MAX_FAILURES", "POLL_WAIT", "RELAY_DEADLINE", "relay_job", "start_relay"]

POLL_WAIT: Final = 20.0
RELAY_DEADLINE: Final = JOB_DEADLINE + 300.0
MAX_FAILURES: Final = 3
RETRY_DELAY: Final = 1.0

_RELAYS: dict[str, asyncio.Task[int]] = {}


async def relay_job(  # noqa: PLR0913 - the job, where events go, and three injectable bounds
    client: WorkerClient,
    started: JobStarted,
    sink: EventSink | None = None,
    *,
    deadline: float = RELAY_DEADLINE,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """Publish the job's events until it finishes, the worker is lost, or ``deadline`` passes.

    Args:
        client: The worker client.
        started: The job.
        sink: Where events go; Hermes' broadcaster by default.
        deadline: Seconds to relay at most.
        clock: Monotonic seconds (tests).
        sleep: Waits between failed polls (tests).

    Returns:
        How many of the job's events were relayed. Unless the job finished, the last event
        published is a ``failed`` one, so the pane never waits forever.
    """
    after = failures = 0
    end = clock() + deadline
    while clock() < end:
        try:
            batch = await client.job_events(started.job_id, after, POLL_WAIT)
        except WorkerError as exc:
            failures += 1
            if failures >= MAX_FAILURES:
                _lost(started, exc.code, sink)
                return after
            await sleep(RETRY_DELAY)
            continue
        failures = 0
        for event in batch.events:
            publish(event, sink)
        after += len(batch.events)
        if batch.finished:
            return after
    _lost(started, "processing_timeout", sink)
    return after


def _lost(started: JobStarted, code: ErrorCode, sink: EventSink | None) -> None:
    """Tell the pane the job's outcome is unknown, so it never waits forever."""
    event = CaseProgressEvent(
        case_id=started.case_id, job_id=started.job_id, stage="failed", progress=0, error_code=code
    )
    publish(event, sink)


def start_relay(
    client: WorkerClient, started: JobStarted, sink: EventSink | None = None
) -> asyncio.Task[int]:
    """Relay the job's events in the background of the gateway's event loop (once per job)."""
    running = _RELAYS.get(started.job_id)
    if running is not None:
        return running
    task = asyncio.create_task(relay_job(client, started, sink))
    _RELAYS[started.job_id] = task
    task.add_done_callback(lambda _done: _RELAYS.pop(started.job_id, None))
    return task
