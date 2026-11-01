"""The worker's after-hours transcription runner.

Implements: US-11.1 (``TranscriptionScheduler``: every minute, while a profile's window is open
for at least ``MIN_WINDOW_LEFT`` more, transcribe its queued calls one at a time with the
``transcription`` role, read the reference number and the rep's instructions, and store the
transcript with the case; a call still running ``WINDOW_GRACE`` after the window closes is
stopped). Rules: BR-12 (the role
runs alone: it is held through ``ModelManager.use``, so the memory guard evicts idle servers and
waits for busy ones; a guard that keeps it waiting sends the job back to the queue), BR-14 (logs
carry the job ID, its state, and error types only).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Final

import httpx

from claimcoach.calls.notes import reference_number, rep_instructions
from claimcoach.calls.queue import TranscriptionQueue
from claimcoach.calls.transcribe import TRANSCRIBE_TIMEOUT, transcribe
from claimcoach.calls.types import CallTranscript, TranscriptionJob
from claimcoach.cases.errors import CaseError
from claimcoach.cases.service import CaseService
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.types import utc_now
from claimcoach.logs import get_logger, job_context
from claimcoach.models.manager import EndpointProvider, ModelBusyError, ModelError
from claimcoach.models.types import ModelRole

__all__ = ["MIN_WINDOW_LEFT", "TICK", "WINDOW_GRACE", "TranscriptionScheduler"]

TICK: Final = 60.0
"""Seconds between checks of the queue and the windows."""
MIN_WINDOW_LEFT: Final = timedelta(minutes=45)
"""A call starts only with this much window left: a 30-minute call takes less on Apple silicon."""
WINDOW_GRACE: Final = timedelta(minutes=15)
"""How long a running call may outlast the window before it is stopped (``processing_timeout``):
the biller's morning loads wait behind Voxtral meanwhile."""

_log = get_logger("claimcoach.calls")


class TranscriptionScheduler:
    """Run queued transcriptions inside their windows.

    Args:
        cases: Reads recordings and stores transcripts.
        queue: The transcription jobs.
        models: The model provider (``ModelManager.use``).
        interval: Seconds between passes.
        timeout: Most seconds one transcription request may take; the window's end plus
            ``WINDOW_GRACE`` comes first.
        transport: Optional httpx transport for the transcription request (tests).
    """

    def __init__(  # noqa: PLR0913 - collaborators plus the request's limits
        self,
        cases: CaseService,
        queue: TranscriptionQueue,
        models: EndpointProvider,
        *,
        interval: float = TICK,
        timeout: float = TRANSCRIBE_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Keep the collaborators; nothing runs until ``run`` or ``run_due``."""
        self.cases = cases
        self.queue = queue
        self.models = models
        self.interval = interval
        self.timeout = timeout
        self._transport = transport

    async def run(self) -> None:
        """Run the due jobs now, then every ``interval`` seconds, until cancelled."""
        while True:
            try:
                await self.run_due()
            except Exception as exc:  # noqa: BLE001 - the schedule must outlive one bad pass
                _log.error("transcription pass failed: %s", type(exc).__name__)
            await asyncio.sleep(self.interval)

    async def run_due(self) -> int:
        """Run every job that is due, one at a time; the window is checked before each.

        Returns:
            How many jobs were tried.
        """
        tried: list[str] = []
        while (job := self.queue.due(skip=tried, min_left=MIN_WINDOW_LEFT)) is not None:
            tried.append(job.job_id)
            await self._run(job)
        return len(tried)

    async def _run(self, job: TranscriptionJob) -> None:
        with job_context(job.job_id):
            self.queue.start(job.job_id)
            try:
                transcript = await self._transcribe(job)
                await asyncio.to_thread(
                    self.cases.save_transcript, job.profile, job.case_id, transcript
                )
            except ModelBusyError:
                _log.info("transcription waits for the memory guard; queued again")
                self.queue.requeue(job.job_id)
            except (ModelError, CorpusError, CaseError) as exc:
                _log.warning("transcription failed: %s", type(exc).__name__)
                self.queue.fail(job.job_id, exc.code)
            except Exception as exc:  # noqa: BLE001 - a job's last word is always its state
                _log.error("transcription failed: %s", type(exc).__name__)
                self.queue.fail(job.job_id, "transcription_failed")
            else:
                _log.info("transcription done")
                self.queue.finish(job.job_id)

    async def _transcribe(self, job: TranscriptionJob) -> CallTranscript:
        # The case is checked before the model loads: a closed case wastes no 24B load.
        recording, audio = await asyncio.to_thread(
            self.cases.call_audio, job.profile, job.case_id, job.call_id
        )
        async with self.models(ModelRole.TRANSCRIPTION) as endpoint:
            # Read once the model is held: the memory guard may have kept it waiting.
            left = self.queue.window_for(job.profile).remaining(self.queue.local_now())
            result = await transcribe(
                endpoint,
                audio,
                recording.format,
                timeout=min(self.timeout, (left + WINDOW_GRACE).total_seconds()),
                transport=self._transport,
            )
        return CallTranscript(
            call_id=job.call_id,
            text=result.text,
            reference_number=reference_number(result.text),
            rep_instructions=rep_instructions(result.text),
            truncated=result.truncated,
            transcribed_at=utc_now(),
        )
