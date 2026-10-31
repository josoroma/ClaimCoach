"""Background extraction jobs and their progress events, long-polled by the gateway.

Implements: US-5.2 (``JobRegistry``: one job per case at a time; each stage appends a
``CaseProgressEvent``; ``events`` waits for new ones so the gateway can relay them through
``broadcast_plugin_event``). Rules: PC-4 (heavy work in the worker, push updates through the
gateway), BR-14 (events hold IDs, a stage enum, a fraction, and an error code only; a failure is
logged by error type only).

Jobs live in memory: a worker restart forgets them, and the stored case stays the source of truth.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from claimcoach.api.models import ErrorCode
from claimcoach.cases.errors import CaseError, JobNotFoundError
from claimcoach.cases.extraction import JOB_DEADLINE, JobEvents, JobStarted
from claimcoach.corpus.errors import CorpusError
from claimcoach.events import CaseProgressEvent, CaseStage, new_job_id
from claimcoach.logs import get_logger, job_id_var
from claimcoach.models.manager import ModelError
from claimcoach.pipeline.extract import Extractor

__all__ = ["JOB_DEADLINE", "JOB_TTL", "MAX_JOBS", "MAX_WAIT", "JobRegistry"]

JOB_TTL: Final = 600.0
"""Seconds a finished job stays readable, so a late poll still sees how it ended."""
MAX_JOBS: Final = 64
MAX_WAIT: Final = 25.0
"""Longest wait of one ``events`` call (the gateway's poll timeout is longer)."""

_log = get_logger("claimcoach.jobs")


@dataclass
class _Job:
    job_id: str
    profile: str
    case_id: str
    events: list[CaseProgressEvent] = field(default_factory=list)
    finished: bool = False
    ended_at: float | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None


class JobRegistry:
    """The worker's extraction jobs.

    Args:
        extractor: Runs one case's extraction.
        clock: Monotonic seconds (tests inject one).
        deadline: Seconds a job may run.
    """

    def __init__(
        self,
        extractor: Extractor,
        clock: Callable[[], float] = time.monotonic,
        *,
        deadline: float = JOB_DEADLINE,
    ) -> None:
        """Start empty; jobs start with ``start``."""
        self.extractor = extractor
        self.deadline = deadline
        self._clock = clock
        self._jobs: dict[str, _Job] = {}

    def start(self, profile: str, case_id: str) -> JobStarted:
        """Start extracting the case, or return the job already extracting it.

        Call ``CaseService.check_extractable`` first: a job reports refusals only as events.
        """
        self._prune()
        for job in self._jobs.values():
            if (job.profile, job.case_id) == (profile, case_id) and not job.finished:
                return JobStarted(case_id=case_id, job_id=job.job_id)
        job = _Job(job_id=new_job_id(), profile=profile, case_id=case_id)
        self._jobs[job.job_id] = job
        job.task = asyncio.create_task(self._run(job))
        return JobStarted(case_id=case_id, job_id=job.job_id)

    def _report(self, job: _Job, stage: CaseStage, progress: float, code: ErrorCode | None) -> None:
        event = CaseProgressEvent(
            case_id=job.case_id,
            job_id=job.job_id,
            stage=stage,
            progress=round(progress, 4),
            error_code=code,
        )
        job.events.append(event)
        job.changed.set()

    async def _run(self, job: _Job) -> None:
        token = job_id_var.set(job.job_id)  # every log line of the job carries its ID
        try:
            await asyncio.wait_for(
                self.extractor.run(
                    job.profile,
                    job.case_id,
                    lambda stage, progress: self._report(job, stage, progress, None),
                ),
                timeout=self.deadline,
            )
        except TimeoutError:
            _log.warning("extraction stopped at its deadline")
            self._report(job, "failed", _last(job), "processing_timeout")
        except (ModelError, CorpusError, CaseError) as exc:
            _log.warning("extraction failed: %s", type(exc).__name__)
            self._report(job, "failed", _last(job), exc.code)
        except Exception as exc:  # noqa: BLE001 - a job's last word is always an event
            _log.error("extraction failed: %s", type(exc).__name__)
            self._report(job, "failed", _last(job), "extraction_failed")
        finally:
            job.finished = True
            job.ended_at = self._clock()
            job.changed.set()
            job_id_var.reset(token)

    async def events(self, job_id: str, after: int = 0, wait: float = 0.0) -> JobEvents:
        """Return the job's events after position ``after``, waiting up to ``wait`` for one.

        Raises:
            JobNotFoundError: No such job.
        """
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError
        if len(job.events) <= after and not job.finished and wait > 0:
            job.changed.clear()
            with contextlib.suppress(TimeoutError):  # no news: the caller polls again
                await asyncio.wait_for(job.changed.wait(), timeout=min(wait, MAX_WAIT))
        return JobEvents(job_id=job_id, events=job.events[after:], finished=job.finished)

    def _prune(self) -> None:
        now = self._clock()
        ended = sorted(
            (job.ended_at, job.job_id) for job in self._jobs.values() if job.ended_at is not None
        )
        excess = len(self._jobs) - MAX_JOBS + 1
        for index, (ended_at, job_id) in enumerate(ended):
            if index < excess or now - ended_at > JOB_TTL:
                del self._jobs[job_id]

    async def shutdown(self) -> None:
        """Cancel every running job and wait for it to stop."""
        tasks = [job.task for job in self._jobs.values() if job.task and not job.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _last(job: _Job) -> float:
    return job.events[-1].progress if job.events else 0.0
