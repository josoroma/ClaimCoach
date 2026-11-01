"""The persisted queue of payer-call transcription jobs.

Implements: US-11.1 (``TranscriptionQueue``: one job per call, queued for its profile's after-hours
window; a job left ``running`` by a stopped worker is queued again; finished jobs are dropped after
30 days; ``due`` picks the next job whose window is open long enough; views show a queued job under
its profile's current window). Rules: BR-13 (the file lives under
``<hermes root>/plugin-data/claimcoach/transcription/``, never in the install dir), BR-14 (the
file holds IDs, states, dates, and error codes only; logs carry counts and error types).

The file is written through a temporary name with mode 0600, so a crash leaves the old queue or
the new one, never half of either. Routes call it from worker threads and the scheduler from the
event loop, so every read and write holds one lock.
"""

from __future__ import annotations

import os
import secrets
import threading
from collections.abc import Callable, Collection
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from claimcoach.api.models import ErrorCode
from claimcoach.calls.types import TranscriptionJob, new_transcription_job_id
from claimcoach.calls.window import TranscriptionWindow
from claimcoach.corpus.paths import profile_home
from claimcoach.corpus.types import utc_now
from claimcoach.logs import get_logger
from claimcoach.settings import load_transcription_window

__all__ = ["FINISHED_TTL", "QUEUE_FILE", "TranscriptionQueue", "WindowFor", "window_reader"]

QUEUE_FILE: Final = "queue.json"
FINISHED_TTL: Final = timedelta(days=30)
"""How long a done or failed job stays visible with its case."""

WindowFor = Callable[[str], TranscriptionWindow]
"""A profile's after-hours window (``window_reader``)."""

_log = get_logger("claimcoach.calls")


class _QueueFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    jobs: list[TranscriptionJob]


def window_reader(root: Path) -> WindowFor:
    """Return the reader of each profile's window from its ``config.yaml`` under ``root``."""
    return lambda profile: load_transcription_window(profile_home(profile, root))


class TranscriptionQueue:
    """Transcription jobs of every profile, one per call, persisted in ``path``.

    Args:
        path: The queue file; its folder is created (0700) by the caller.
        window_for: Each profile's after-hours window.
        clock: The current time, aware (tests inject one).
        tz: The zone the windows are read in; the Mac's local zone by default.
    """

    def __init__(
        self,
        path: Path,
        window_for: WindowFor,
        *,
        clock: Callable[[], datetime] = utc_now,
        tz: tzinfo | None = None,
    ) -> None:
        """Load the queue; a job left running is queued again."""
        self.path = path
        self.window_for = window_for
        self._clock = clock
        self._tz = tz
        self._lock = threading.Lock()
        self._jobs: dict[str, TranscriptionJob] = {}
        for job in self._read():
            self._jobs[job.job_id] = (
                job.model_copy(update={"state": "queued"}) if job.state == "running" else job
            )

    def local_now(self) -> datetime:
        """Return the current time in the windows' zone."""
        return self._clock().astimezone(self._tz)

    def _read(self) -> list[TranscriptionJob]:
        try:
            return _QueueFile.model_validate_json(self.path.read_bytes()).jobs
        except FileNotFoundError:
            return []
        except (OSError, ValidationError):
            _log.warning("the transcription queue cannot be read; starting with an empty queue")
            return []

    def _commit(self, jobs: dict[str, TranscriptionJob]) -> None:
        """Write ``jobs`` without expired finished ones, then make them the queue (lock held).

        Memory changes only once the file is written, so a failed write (a full disk) leaves the
        queue as it was in both places.
        """
        cutoff = self._clock() - FINISHED_TTL
        kept = {
            job_id: job
            for job_id, job in jobs.items()
            if job.finished_at is None or job.finished_at > cutoff
        }
        body = _QueueFile(jobs=list(kept.values())).model_dump_json().encode()
        partial = self.path.with_name(f".{self.path.name}.{secrets.token_hex(4)}.partial")
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
            partial.replace(self.path)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        self._jobs = kept

    def _for_call(self, profile: str, case_id: str, call_id: str) -> TranscriptionJob | None:
        for job in self._jobs.values():
            if (job.profile, job.case_id, job.call_id) == (profile, case_id, call_id):
                return job
        return None

    def _current(self, job: TranscriptionJob, now: datetime) -> TranscriptionJob:
        """A queued job as views show it: under its profile's current window (lock held)."""
        if job.state != "queued":
            return job
        window = self.window_for(job.profile)
        return job.model_copy(update={"window": window, "not_before": window.next_start(now)})

    def enqueue(self, profile: str, case_id: str, call_id: str) -> TranscriptionJob:
        """Queue the call for its profile's window, or return its queued or running job.

        A done or failed job of the call is replaced by the new one.
        """
        with self._lock:
            current = self._for_call(profile, case_id, call_id)
            if current is not None and current.state in ("queued", "running"):
                return self._current(current, self.local_now())
            jobs = dict(self._jobs)
            if current is not None:
                del jobs[current.job_id]
            window = self.window_for(profile)
            job = TranscriptionJob(
                job_id=new_transcription_job_id(),
                profile=profile,
                case_id=case_id,
                call_id=call_id,
                window=window,
                queued_at=self._clock(),
                not_before=window.next_start(self.local_now()),
            )
            jobs[job.job_id] = job
            self._commit(jobs)
            return job

    def for_case(self, profile: str, case_id: str) -> dict[str, TranscriptionJob]:
        """Return the case's jobs by call ID, queued ones under the current window."""
        now = self.local_now()
        with self._lock:
            return {
                job.call_id: self._current(job, now)
                for job in self._jobs.values()
                if (job.profile, job.case_id) == (profile, case_id)
            }

    def jobs(self) -> list[TranscriptionJob]:
        """Return every job, oldest first, queued ones under the current window."""
        now = self.local_now()
        with self._lock:
            listed = [self._current(job, now) for job in self._jobs.values()]
        return sorted(listed, key=lambda job: job.queued_at)

    def due(
        self, skip: Collection[str] = (), min_left: timedelta = timedelta(0)
    ) -> TranscriptionJob | None:
        """Return the oldest queued job whose profile's window is open now, if any.

        Args:
            skip: Job IDs already tried in this pass (a job the memory guard sent back).
            min_left: Least time the window must stay open for a job to start.
        """
        now = self.local_now()
        with self._lock:
            pending = sorted(self._jobs.values(), key=lambda job: job.queued_at)
        windows: dict[str, bool] = {}
        for job in pending:
            if job.state != "queued" or job.job_id in skip:
                continue
            if job.profile not in windows:
                left = self.window_for(job.profile).remaining(now)
                windows[job.profile] = left > timedelta(0) and left >= min_left
            if windows[job.profile]:
                return job
        return None

    def _update(self, job_id: str, **changes: object) -> TranscriptionJob:
        with self._lock:
            job = self._jobs[job_id].model_copy(update=changes)
            updated = TranscriptionJob.model_validate(job.model_dump())
            self._commit({**self._jobs, job_id: updated})
            return updated

    def start(self, job_id: str) -> TranscriptionJob:
        """Mark the job running, under the window it runs in."""
        now = self._clock()
        with self._lock:
            profile = self._jobs[job_id].profile
        return self._update(
            job_id,
            state="running",
            window=self.window_for(profile),
            not_before=now,
            started_at=now,
            finished_at=None,
            error_code=None,
        )

    def finish(self, job_id: str) -> TranscriptionJob:
        """Mark the job done."""
        return self._update(job_id, state="done", finished_at=self._clock())

    def fail(self, job_id: str, code: ErrorCode) -> TranscriptionJob:
        """Mark the job failed with ``code``."""
        return self._update(job_id, state="failed", finished_at=self._clock(), error_code=code)

    def requeue(self, job_id: str) -> TranscriptionJob:
        """Queue the job again (the memory guard kept the model busy); it runs on a later tick."""
        return self._update(job_id, state="queued", started_at=None)
