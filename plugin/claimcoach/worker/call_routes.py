"""Worker routes for payer-call recordings and their transcription queue.

Implements: US-11.1 (``POST /cases/{case_id}/calls`` attaches a recording from the raw single-file
multipart body; ``POST /cases/{case_id}/calls/{call_id}/transcribe`` queues it for the after-hours
window; ``GET /transcriptions`` lists the queue for operators). Rules: ES-8 (typed bodies;
``CaseError`` and ``CorpusError`` become their fixed envelopes in ``create_app``), BR-2 (recordings
reach the worker only from the gateway), BR-4 (nothing here sends or transmits anything;
``test_us_7_3_no_transmitting_route`` pins the route set), BR-14 (no content is logged; the queue
holds IDs, states, dates, and codes only).

Store calls run off the event loop: sealing a 128 MiB recording takes a moment.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict

from claimcoach.calls.audio import parse_call_upload, read_call_body
from claimcoach.calls.types import (
    CALL_ID_PATTERN,
    CallAdded,
    TranscriptionJob,
    TranscriptionQueued,
)
from claimcoach.corpus.types import DEFAULT_PROFILE
from claimcoach.models.manager import ModelUnavailableError
from claimcoach.worker.case_routes import CasePath, Cases, Profile

__all__ = ["TranscriptionList", "router", "transcriptions_router"]

router = APIRouter(prefix="/cases")
transcriptions_router = APIRouter(prefix="/transcriptions")

CallPath = Annotated[str, Path(pattern=CALL_ID_PATTERN)]


class TranscriptionList(BaseModel):
    """``GET /transcriptions``: every transcription job, oldest first (no case content).

    Attributes:
        ok: Always ``True``.
        jobs: The jobs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True
    jobs: list[TranscriptionJob]


@router.post("/{case_id}/calls", response_model=CallAdded)
async def add_call(
    case_id: CasePath, request: Request, cases: Cases, profile: Profile = DEFAULT_PROFILE
) -> CallAdded:
    """Attach the one recording of a ``multipart/form-data`` body (read in memory)."""
    body = await read_call_body(request.stream(), request.headers.get("content-length"))
    upload = parse_call_upload(body, request.headers.get("content-type", ""))
    return await asyncio.to_thread(cases.add_call, profile, case_id, upload)


@router.post("/{case_id}/calls/{call_id}/transcribe", response_model=TranscriptionQueued)
async def transcribe_call(
    case_id: CasePath, call_id: CallPath, cases: Cases, profile: Profile = DEFAULT_PROFILE
) -> TranscriptionQueued:
    """Queue the call for the after-hours window (or return its queued or running job)."""
    return await asyncio.to_thread(cases.queue_transcription, profile, case_id, call_id)


@transcriptions_router.get("", response_model=TranscriptionList)
def list_transcriptions(cases: Cases) -> TranscriptionList:
    """Return every transcription job: IDs, states, windows, dates, and error codes.

    Raises:
        ModelUnavailableError: This worker has no transcription queue.
    """
    if cases.transcriptions is None:
        raise ModelUnavailableError
    return TranscriptionList(jobs=cases.transcriptions.jobs())
