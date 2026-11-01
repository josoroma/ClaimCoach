"""US-11.1 Transcribe Recorded Payer Calls After Hours (Python half).

Scenarios: an attached call is queued for transcription; submitting a queued call again; a
recording is attached; not a recording; outside the window nothing runs; inside the window the
call is transcribed; the transcript's notes are shown with the case; the queue file holds no case
content. Also: the window, the settings, the notes, the queue file, the transcription request, the
scheduler's failure paths, the routes' refusals, and the retention purge. The pane scenarios run
under ``node --test`` (``plugin/desktop/tests/payer_calls.test.mjs``).
Rules: ES-1, ES-4, ES-8, BR-1, BR-2, BR-12, BR-13, BR-14.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import stat
import subprocess
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
import yaml
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.calls import audio as audio_module
from claimcoach.calls.audio import parse_call_upload, sniff_audio
from claimcoach.calls.notes import MAX_INSTRUCTION_CHARS, reference_number, rep_instructions
from claimcoach.calls.queue import FINISHED_TTL, QUEUE_FILE, TranscriptionQueue, window_reader
from claimcoach.calls.scheduler import WINDOW_GRACE, TranscriptionScheduler
from claimcoach.calls.transcribe import MAX_TOKENS, transcribe
from claimcoach.calls.types import (
    AudioFormat,
    CallAdded,
    CallTranscript,
    TranscriptionQueued,
    transcript_item_id,
)
from claimcoach.calls.window import TranscriptionWindow
from claimcoach.cases.errors import (
    CallNotFoundError,
    CallTooLargeError,
    TranscriptionFailedError,
    UnsupportedAudioError,
)
from claimcoach.cases.models import Case
from claimcoach.cases.service import CaseService
from claimcoach.corpus.errors import CaseClosedError
from claimcoach.corpus.paths import transcription_dir
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, CaseItem, CaseOutcome, PurgeRequest, utc_now
from claimcoach.models.manager import (
    ModelBusyError,
    ModelEndpoint,
    ModelManager,
    ModelUnavailableError,
)
from claimcoach.models.registry import (
    DEFAULT_REGISTRY,
    REGISTRY_FILE,
    ModelRegistry,
    ensure_registry_file,
    models_home,
)
from claimcoach.models.types import ModelRole
from claimcoach.settings import ClaimCoachSettings, load_transcription_window
from claimcoach.worker import call_routes
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_6_1_diagnosis import PREFIX, assert_envelope

WAV: Final = b"RIFF\x24\x00\x00\x00WAVEfmt " + bytes(64)
MP3_ID3: Final = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(64)
MP3_FRAME: Final = b"\xff\xfb\x90\x64" + bytes(64)
FLAC: Final = b"fLaC\x00\x00\x00\x22" + bytes(64)
M4A: Final = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00" + bytes(64)
FILENAME: Final = "Jane Doe call 1970-01-01.wav"
"""A filename that is PHI: it may be stored sealed and shown in the pane, never logged or queued."""
TRANSCRIPT: Final = (
    "Thank you for calling. Can I have the claim number? "
    "The claim was denied for missing authorization. "
    "You need to resubmit it as a corrected claim with the authorization number attached. "
    "Please fax the medical records to the appeals unit within 30 days. "
    "Your reference number for this call is 8 4 1 7 2 9 3. "
    "Is there anything else? Have a good day."
)
REF: Final = "8417293"
NIGHT: Final = datetime(2026, 10, 31, 22, 0, tzinfo=UTC)
DAY: Final = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)


class Clock:
    """A settable aware clock."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock(DAY)


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def queue(service: CorpusService, clock: Clock) -> TranscriptionQueue:
    return TranscriptionQueue(
        transcription_dir(service.root) / QUEUE_FILE,
        lambda _profile: TranscriptionWindow(),
        clock=clock,
        tz=UTC,
    )


@pytest.fixture
def worker(service: CorpusService, queue: TranscriptionQueue) -> FastAPI:
    """A worker without models: attaching and queuing run no model."""
    return create_app(TOKEN, corpus=service, transcriptions=queue)


@pytest.fixture
def cases(worker: FastAPI) -> CaseService:
    service: CaseService = worker.state.cases
    return service


@pytest.fixture
async def desktop(
    worker: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """``ctx.rest`` against the gateway over ``worker``."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: client
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        yield desktop


@pytest.fixture
async def direct(worker: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """The worker itself, with its token."""
    transport = httpx.ASGITransport(app=worker)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://worker", headers=headers
    ) as client:
        yield client


async def new_case(desktop: httpx.AsyncClient) -> str:
    response = await desktop.post(f"{PREFIX}/cases", json={})
    assert response.status_code == 200, response.text
    return Case.model_validate_json(response.content).case_id


async def open_case(desktop: httpx.AsyncClient, case_id: str) -> Case:
    response = await desktop.get(f"{PREFIX}/cases/{case_id}")
    assert response.status_code == 200, response.text
    return Case.model_validate_json(response.content)


async def attach(
    desktop: httpx.AsyncClient, case_id: str, data: bytes = WAV, name: str = FILENAME
) -> httpx.Response:
    return await desktop.post(
        f"{PREFIX}/cases/{case_id}/calls", files={"file": (name, data, "audio/wav")}
    )


async def attached(desktop: httpx.AsyncClient, case_id: str, data: bytes = WAV) -> str:
    response = await attach(desktop, case_id, data)
    assert response.status_code == 200, response.text
    return CallAdded.model_validate_json(response.content).call.call_id


async def submit(desktop: httpx.AsyncClient, case_id: str, call_id: str) -> httpx.Response:
    return await desktop.post(f"{PREFIX}/cases/{case_id}/calls/{call_id}/transcribe", json={})


async def queued(desktop: httpx.AsyncClient, case_id: str, call_id: str) -> TranscriptionQueued:
    response = await submit(desktop, case_id, call_id)
    assert response.status_code == 200, response.text
    return TranscriptionQueued.model_validate_json(response.content)


def voxtral(
    reply: object = None, *, status: int = 200, seen: list[httpx.Request] | None = None
) -> httpx.MockTransport:
    """A fake ``mlx_audio.server`` transcription endpoint."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        body = {"text": TRANSCRIPT} if reply is None else reply
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


Provider = Callable[[ModelRole], AbstractAsyncContextManager[ModelEndpoint]]


def provider(loads: list[ModelRole], error: Exception | None = None) -> Provider:
    """A model provider that records each load and may refuse it."""

    @asynccontextmanager
    async def use(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        loads.append(role)
        if error is not None:
            raise error
        yield ModelEndpoint(
            role=role, base_url="http://127.0.0.1:18207/v1", model_path="/models/voxtral"
        )

    return use


def scheduler(
    cases: CaseService,
    queue: TranscriptionQueue,
    loads: list[ModelRole],
    *,
    error: Exception | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TranscriptionScheduler:
    return TranscriptionScheduler(
        cases, queue, provider(loads, error), transport=transport or voxtral()
    )


# --- Scenario: An attached call is queued for transcription --------------------------------------


async def test_us_11_1_attached_call_queued(
    desktop: httpx.AsyncClient, queue: TranscriptionQueue
) -> None:
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)

    answer = await queued(desktop, case_id, call_id)

    job = answer.job
    assert (answer.case_id, job.case_id, job.call_id, job.profile) == (
        case_id,
        case_id,
        call_id,
        "default",
    )
    assert job.state == "queued"
    assert job.window == TranscriptionWindow(start_hour=19, end_hour=7)
    assert job.not_before == DAY.replace(hour=19), "queued at 10:00, it waits for 19:00"
    assert queue.jobs() == [job]
    case = await open_case(desktop, case_id)
    assert [call.recording.call_id for call in case.calls] == [call_id]
    assert case.calls[0].transcription == job
    assert case.calls[0].transcript is None


async def test_us_11_1_queued_inside_the_window_may_start_now(
    desktop: httpx.AsyncClient, clock: Clock
) -> None:
    clock.now = NIGHT
    case_id = await new_case(desktop)
    job = (await queued(desktop, case_id, await attached(desktop, case_id))).job
    assert job.not_before == NIGHT


# --- Scenario: Submitting a queued call again ----------------------------------------------------


async def test_us_11_1_submitting_a_queued_call_again(
    desktop: httpx.AsyncClient, queue: TranscriptionQueue
) -> None:
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)
    first = await queued(desktop, case_id, call_id)
    second = await queued(desktop, case_id, call_id)
    assert second.job == first.job
    assert len(queue.jobs()) == 1


async def test_us_11_1_a_finished_call_is_queued_again(
    desktop: httpx.AsyncClient, queue: TranscriptionQueue
) -> None:
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)
    first = (await queued(desktop, case_id, call_id)).job
    queue.fail(first.job_id, "model_unavailable")
    second = (await queued(desktop, case_id, call_id)).job
    assert second.job_id != first.job_id
    assert second.state == "queued"
    assert [job.job_id for job in queue.jobs()] == [second.job_id]


# --- Scenario: A recording is attached -----------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "fmt"),
    [(WAV, "wav"), (MP3_ID3, "mp3"), (MP3_FRAME, "mp3"), (FLAC, "flac"), (M4A, "m4a")],
)
async def test_us_11_1_recording_attached(
    desktop: httpx.AsyncClient, service: CorpusService, data: bytes, fmt: str
) -> None:
    case_id = await new_case(desktop)
    response = await attach(desktop, case_id, data)
    assert response.status_code == 200, response.text
    call = CallAdded.model_validate_json(response.content).call
    assert (call.format, call.size_bytes, call.filename) == (fmt, len(data), FILENAME)
    case = await open_case(desktop, case_id)
    assert [c.recording for c in case.calls] == [call]
    store = service.user_store("default")
    assert store.case_item_data(case_id, call.call_id) == data
    assert AuditAction.CALL_ADDED in [entry.action for entry in store.audit_log(case_id)]


# --- Scenario: Not a recording -------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.7 not audio",
        b"plain text, not audio",
        b"\xff\xf1\x50\x80" + bytes(8),  # ADTS AAC: layer bits 00
        b"\xff\xeb\x90\x64" + bytes(8),  # MPEG version bits 01 (reserved)
        b"\xff",
        b"\x00\x00\x00\x20ftypqt  " + bytes(8),  # a QuickTime movie, not M4A
    ],
)
async def test_us_11_1_not_a_recording(
    desktop: httpx.AsyncClient, service: CorpusService, data: bytes
) -> None:
    case_id = await new_case(desktop)
    assert_envelope(await attach(desktop, case_id, data), 415, "unsupported_audio")
    assert service.user_store("default").case_items(case_id, "call") == []


async def test_us_11_1_empty_recording(desktop: httpx.AsyncClient) -> None:
    case_id = await new_case(desktop)
    assert_envelope(await attach(desktop, case_id, b""), 415, "unsupported_audio")


async def test_us_11_1_recording_too_large(
    desktop: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = await new_case(desktop)
    monkeypatch.setattr(audio_module, "MAX_CALL_BYTES", 16)
    assert_envelope(await attach(desktop, case_id, WAV), 413, "call_too_large")
    monkeypatch.setattr(audio_module, "MAX_CALL_BODY", 32)
    assert_envelope(await attach(desktop, case_id, WAV), 413, "call_too_large")


def test_us_11_1_parse_call_upload_refusals() -> None:
    with pytest.raises(UnsupportedAudioError):
        sniff_audio(b"")
    body = b'--b\r\nContent-Disposition: form-data; name="file"\r\n\r\n\r\n--b--\r\n'
    with pytest.raises(UnsupportedAudioError):
        parse_call_upload(body, "multipart/form-data; boundary=b")


async def test_us_11_1_gateway_refuses_bad_requests(desktop: httpx.AsyncClient) -> None:
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)
    url = f"{PREFIX}/cases/{case_id}/calls"
    assert_envelope(await desktop.post(url, content=WAV), 422, "invalid_request")
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/bad%20id/calls", files={"file": ("a", WAV)}),
        422,
        "invalid_request",
    )
    big = {"content-type": "multipart/form-data; boundary=b", "content-length": str(2**40)}
    assert_envelope(await desktop.post(url, content=b"x", headers=big), 413, "call_too_large")
    transcribe_url = f"{PREFIX}/cases/{case_id}/calls/{call_id}/transcribe"
    assert_envelope(await desktop.post(transcribe_url, content=b"{}"), 422, "invalid_request")
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/{case_id}/calls/call_x/transcribe", json={}),
        422,
        "invalid_request",
    )
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/bad%20id/calls/{call_id}/transcribe", json={}),
        422,
        "invalid_request",
    )


async def test_us_11_1_unknown_call_and_closed_case(
    desktop: httpx.AsyncClient, direct: httpx.AsyncClient
) -> None:
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)
    assert_envelope(await submit(desktop, case_id, "call_0000000000000000"), 404, "call_not_found")
    assert_envelope(
        await direct.post(f"/cases/{case_id}/calls/not-a-call/transcribe"), 422, "invalid_request"
    )
    outcome = await desktop.post(f"{PREFIX}/cases/{case_id}/outcome", json={"outcome": "upheld"})
    assert outcome.status_code == 200, outcome.text
    assert_envelope(await attach(desktop, case_id), 409, "case_closed")
    assert_envelope(await submit(desktop, case_id, call_id), 409, "case_closed")


# --- Scenario: Outside the window nothing runs ---------------------------------------------------


async def test_us_11_1_outside_the_window_nothing_runs(
    desktop: httpx.AsyncClient, cases: CaseService, queue: TranscriptionQueue
) -> None:
    case_id = await new_case(desktop)
    job = (await queued(desktop, case_id, await attached(desktop, case_id))).job
    loads: list[ModelRole] = []

    assert await scheduler(cases, queue, loads).run_due() == 0

    assert loads == [], "no model loads outside the window"
    assert queue.jobs() == [job]


# --- Scenario: Inside the window the call is transcribed -----------------------------------------


async def test_us_11_1_inside_the_window_the_call_is_transcribed(
    desktop: httpx.AsyncClient, cases: CaseService, queue: TranscriptionQueue, clock: Clock
) -> None:
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)
    job = (await queued(desktop, case_id, call_id)).job
    clock.now = NIGHT
    loads: list[ModelRole] = []
    seen: list[httpx.Request] = []

    tried = await scheduler(cases, queue, loads, transport=voxtral(seen=seen)).run_due()

    assert tried == 1
    assert loads == [ModelRole.TRANSCRIPTION], "Voxtral is held through the memory guard"
    (done,) = queue.jobs()
    assert (done.job_id, done.state, done.error_code) == (job.job_id, "done", None)
    assert done.started_at == NIGHT
    assert done.finished_at == NIGHT
    (request,) = seen
    assert request.url == "http://127.0.0.1:18207/v1/audio/transcriptions"
    body = request.content
    assert b"/models/voxtral" in body
    assert b'name="response_format"\r\n\r\nverbose_json' in body
    assert f'name="max_tokens"\r\n\r\n{MAX_TOKENS}'.encode() in body
    assert b'filename="call.wav"' in body
    assert FILENAME.encode() not in body, "the biller's filename never reaches the model server"
    assert WAV in body


# --- Scenario: The transcript's notes are shown with the case ------------------------------------


async def test_us_11_1_transcript_notes_shown_with_the_case(
    desktop: httpx.AsyncClient,
    cases: CaseService,
    queue: TranscriptionQueue,
    service: CorpusService,
    clock: Clock,
) -> None:
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)
    await queued(desktop, case_id, call_id)
    clock.now = NIGHT
    await scheduler(cases, queue, []).run_due()

    case = await open_case(desktop, case_id)

    (call,) = case.calls
    assert call.transcription is not None
    assert call.transcription.state == "done"
    transcript = call.transcript
    assert transcript is not None
    assert transcript.text == TRANSCRIPT
    assert transcript.reference_number == REF
    assert transcript.rep_instructions == [
        "You need to resubmit it as a corrected claim with the authorization number attached.",
        "Please fax the medical records to the appeals unit within 30 days.",
    ]
    store = service.user_store("default")
    assert [i.item_id for i in store.case_items(case_id, "transcript")] == [
        transcript_item_id(call_id)
    ]
    assert AuditAction.CALL_TRANSCRIBED in [e.action for e in store.audit_log(case_id)]


# --- Scenario: The queue file holds no case content ----------------------------------------------


async def test_us_11_1_queue_file_holds_no_case_content(
    desktop: httpx.AsyncClient,
    cases: CaseService,
    queue: TranscriptionQueue,
    clock: Clock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)
    await queued(desktop, case_id, call_id)
    clock.now = NIGHT
    await scheduler(cases, queue, []).run_due()

    stored = queue.path.read_text()
    assert set(json.loads(stored)["jobs"][0]) == {
        "job_id",
        "profile",
        "case_id",
        "call_id",
        "state",
        "window",
        "queued_at",
        "not_before",
        "started_at",
        "finished_at",
        "error_code",
    }
    for secret in (FILENAME, "Jane", REF, "resubmit"):
        assert secret not in stored
        assert secret not in caplog.text
    assert stat.S_IMODE(queue.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(queue.path.parent.stat().st_mode) == 0o700


# --- The scheduler's failure paths ---------------------------------------------------------------


async def queue_one(desktop: httpx.AsyncClient, clock: Clock) -> tuple[str, str]:
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)
    await queued(desktop, case_id, call_id)
    clock.now = NIGHT
    return case_id, call_id


async def test_us_11_1_busy_guard_queues_the_job_again(
    desktop: httpx.AsyncClient, cases: CaseService, queue: TranscriptionQueue, clock: Clock
) -> None:
    await queue_one(desktop, clock)
    loads: list[ModelRole] = []
    assert await scheduler(cases, queue, loads, error=ModelBusyError()).run_due() == 1
    (job,) = queue.jobs()
    assert (job.state, job.started_at) == ("queued", None), "tried once per pass, then waits"
    assert await scheduler(cases, queue, loads).run_due() == 1
    assert queue.jobs()[0].state == "done"
    assert loads == [ModelRole.TRANSCRIPTION, ModelRole.TRANSCRIPTION]


@pytest.mark.parametrize(
    ("error", "transport", "code"),
    [
        (ModelUnavailableError(), None, "model_unavailable"),
        (None, voxtral({"text": "   "}), "transcription_failed"),
        (None, voxtral(status=500), "model_unavailable"),
        (None, voxtral({"segments": []}), "model_unavailable"),
        (RuntimeError("Jane Doe"), None, "transcription_failed"),
    ],
)
async def test_us_11_1_failed_transcription(  # noqa: PLR0917 - fixtures and parameters
    desktop: httpx.AsyncClient,
    cases: CaseService,
    queue: TranscriptionQueue,
    clock: Clock,
    caplog: pytest.LogCaptureFixture,
    error: Exception | None,
    transport: httpx.AsyncBaseTransport | None,
    code: str,
) -> None:
    case_id, _call = await queue_one(desktop, clock)
    await scheduler(cases, queue, [], error=error, transport=transport).run_due()
    (job,) = queue.jobs()
    assert (job.state, job.error_code) == ("failed", code)
    assert (await open_case(desktop, case_id)).calls[0].transcript is None
    assert "Jane" not in caplog.text


async def test_us_11_1_closed_case_fails_before_the_model_loads(
    desktop: httpx.AsyncClient, cases: CaseService, queue: TranscriptionQueue, clock: Clock
) -> None:
    case_id, _call = await queue_one(desktop, clock)
    await desktop.post(f"{PREFIX}/cases/{case_id}/outcome", json={"outcome": "overturned"})
    loads: list[ModelRole] = []
    await scheduler(cases, queue, loads).run_due()
    assert loads == []
    assert (queue.jobs()[0].state, queue.jobs()[0].error_code) == ("failed", "case_closed")


async def test_us_11_1_case_closed_while_transcribing(
    desktop: httpx.AsyncClient, cases: CaseService, queue: TranscriptionQueue, clock: Clock
) -> None:
    case_id, _call = await queue_one(desktop, clock)

    def close_then_answer(_request: httpx.Request) -> httpx.Response:
        cases.store("default").close_case(case_id)
        return httpx.Response(200, json={"text": TRANSCRIPT})

    transport = httpx.MockTransport(close_then_answer)
    await scheduler(cases, queue, [], transport=transport).run_due()
    assert queue.jobs()[0].error_code == "case_closed"


def test_us_11_1_call_audio_without_bytes(service: CorpusService, cases: CaseService) -> None:
    store = service.user_store("default", create=True)
    store.create_case("c1")
    recording = {
        "call_id": "call_0123456789abcdef",
        "format": "wav",
        "content_type": "audio/wav",
        "size_bytes": 1,
        "added_at": utc_now().isoformat(),
    }
    item = CaseItem(
        case_id="c1",
        item_id="call_0123456789abcdef",
        kind="call",
        created_at=utc_now(),
        payload=json.dumps(recording).encode(),
    )
    store.put_case_item(item, audit=AuditAction.CALL_ADDED)
    with pytest.raises(CallNotFoundError):
        cases.call_audio("default", "c1", "call_0123456789abcdef")
    with pytest.raises(CallNotFoundError):
        cases.call_audio("default", "c1", "call_ffffffffffffffff")


async def test_us_11_1_scheduler_outlives_a_bad_pass(
    cases: CaseService, queue: TranscriptionQueue, caplog: pytest.LogCaptureFixture
) -> None:
    runner = TranscriptionScheduler(cases, queue, provider([]), interval=0.01)
    passes = 0

    async def failing() -> int:
        nonlocal passes
        passes += 1
        if passes == 1:
            raise RuntimeError("Jane Doe")
        return 0

    runner.run_due = failing  # type: ignore[method-assign]
    task = asyncio.create_task(runner.run())
    while passes < 3:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "transcription pass failed: RuntimeError" in caplog.text
    assert "Jane" not in caplog.text


async def test_us_11_1_worker_lifespan_runs_the_scheduler(
    service: CorpusService, queue: TranscriptionQueue
) -> None:
    loads: list[ModelRole] = []
    app = create_app(TOKEN, corpus=service, pipeline_models=provider(loads), transcriptions=queue)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)
    assert loads == [], "an empty queue loads nothing"


def test_us_11_1_default_queue_lives_under_the_root(service: CorpusService) -> None:
    app = create_app(TOKEN, corpus=service)
    queue: TranscriptionQueue = app.state.cases.transcriptions
    assert queue.path == service.root / "plugin-data" / "claimcoach" / "transcription" / QUEUE_FILE


async def test_us_11_1_transcriptions_listing(
    desktop: httpx.AsyncClient, direct: httpx.AsyncClient, cases: CaseService
) -> None:
    case_id = await new_case(desktop)
    job = (await queued(desktop, case_id, await attached(desktop, case_id))).job
    response = await direct.get("/transcriptions")
    assert response.status_code == 200, response.text
    assert call_routes.TranscriptionList.model_validate_json(response.content).jobs == [job]
    cases.transcriptions = None
    assert_envelope(await direct.get("/transcriptions"), 503, "model_unavailable")


def test_us_11_1_service_without_a_queue(service: CorpusService) -> None:
    plain = CaseService(service)
    case = plain.create("default")
    with pytest.raises(ModelUnavailableError):
        plain.queue_transcription("default", case.case_id, "call_0123456789abcdef")


# --- The window and the settings ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "hour", "inside"),
    [
        (19, 7, 19, True),
        (19, 7, 23, True),
        (19, 7, 6, True),
        (19, 7, 7, False),
        (19, 7, 12, False),
        (1, 5, 1, True),
        (1, 5, 4, True),
        (1, 5, 5, False),
        (1, 5, 0, False),
    ],
)
def test_us_11_1_window_contains(start: int, end: int, hour: int, inside: bool) -> None:
    window = TranscriptionWindow(start_hour=start, end_hour=end)
    assert window.contains(DAY.replace(hour=hour)) is inside


def test_us_11_1_window_next_start() -> None:
    evening = TranscriptionWindow(start_hour=19, end_hour=7)
    assert evening.next_start(DAY) == DAY.replace(hour=19)
    assert evening.next_start(NIGHT) == NIGHT
    early = TranscriptionWindow(start_hour=1, end_hour=5)
    assert early.next_start(DAY) == DAY.replace(hour=1) + timedelta(days=1)
    assert early.next_start(DAY.replace(hour=0, minute=30)) == DAY.replace(hour=1, minute=0)


def test_us_11_1_window_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        TranscriptionWindow(start_hour=3, end_hour=3)
    with pytest.raises(ValidationError):
        TranscriptionWindow(start_hour=24)


def write_settings(home: Path, settings: dict[str, Any] | str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    body = (
        settings
        if isinstance(settings, str)
        else yaml.safe_dump({"plugins": {"entries": {"claimcoach": {"settings": settings}}}})
    )
    (home / "config.yaml").write_text(body)


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ({}, (19, 7)),
        ({"transcription_start_hour": 22, "transcription_end_hour": 5}, (22, 5)),
        ({"transcription_start_hour": 20}, (20, 7)),
        ({"transcription_start_hour": 7, "transcription_end_hour": 7}, (19, 7)),
        ({"transcription_start_hour": 25}, (19, 7)),
        ({"transcription_end_hour": "late"}, (19, 7)),
        ({"retention_days": "bad", "transcription_start_hour": 21}, (21, 7)),
        ("plugins: [unclosed", (19, 7)),
    ],
)
def test_us_11_1_window_settings(
    tmp_path: Path, stored: dict[str, Any] | str, expected: tuple[int, int]
) -> None:
    write_settings(tmp_path, stored)
    window = load_transcription_window(tmp_path)
    assert (window.start_hour, window.end_hour) == expected


def test_us_11_1_window_reader_reads_each_profile(tmp_path: Path) -> None:
    write_settings(tmp_path / "profiles" / "night", {"transcription_start_hour": 23})
    read = window_reader(tmp_path)
    assert read("default") == TranscriptionWindow()
    assert read("night") == TranscriptionWindow(start_hour=23, end_hour=7)


def test_us_11_1_settings_defaults() -> None:
    settings = ClaimCoachSettings()
    assert (settings.transcription_start_hour, settings.transcription_end_hour) == (19, 7)


# --- The notes ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (TRANSCRIPT, REF),
        ("Your call reference number is ABC-12345.", "ABC-12345"),
        ("Call ref number CN 77 31 99 and that is all.", "CN773199"),
        ("Confirmation number: 5512 9087. Thanks.", "55129087"),
        ("Ticket 4471 then later the reference number is 9 9 0 0 1.", "99001"),
        ("In this case the claim was denied.", None),
        ("The reference number is pending.", None),
        ("Reference number 12.", None),
        ("Reference number ABCDEF.", None),
        ("Ticket ABCDE 12345", None),
        ("No numbers here at all.", None),
        ("The reference number is 55667788", "55667788"),
    ],
)
def test_us_11_1_notes_reference_number(text: str, expected: str | None) -> None:
    assert reference_number(text) == expected


def test_us_11_1_notes_rep_instructions() -> None:
    long = "Please send " + "x" * 600 + "."
    text = (
        "Please attach the referral. Can you send it today? Please attach the referral. "
        f"Hello there. {long} " + " ".join(f"Fax page {n} please." for n in range(20))
    )
    instructions = rep_instructions(text)
    assert instructions[0] == "Please attach the referral."
    assert "Can you send it today?" not in instructions, "questions are not instructions"
    assert instructions.count("Please attach the referral.") == 1
    assert "Hello there." not in instructions
    assert len(instructions[1]) == MAX_INSTRUCTION_CHARS
    assert len(instructions) == 10
    assert rep_instructions("") == []


# --- The queue file -------------------------------------------------------------------------------


def make_queue(
    path: Path, clock: Clock, window: TranscriptionWindow | None = None
) -> TranscriptionQueue:
    return TranscriptionQueue(path, lambda _p: window or TranscriptionWindow(), clock=clock, tz=UTC)


def test_us_11_1_queue_running_jobs_are_queued_again_at_load(tmp_path: Path, clock: Clock) -> None:
    queue = make_queue(tmp_path / QUEUE_FILE, clock)
    job = queue.enqueue("default", "c1", "call_0123456789abcdef")
    queue.start(job.job_id)
    reloaded = make_queue(tmp_path / QUEUE_FILE, clock)
    assert [j.state for j in reloaded.jobs()] == ["queued"]
    assert reloaded.for_case("default", "c1")["call_0123456789abcdef"].job_id == job.job_id
    assert reloaded.for_case("default", "c2") == {}


def test_us_11_1_queue_unreadable_file_starts_empty(
    tmp_path: Path, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / QUEUE_FILE
    path.write_text('{"version": 1, "jobs": [{"filename": "Jane Doe"}]}')
    assert make_queue(path, clock).jobs() == []
    assert "cannot be read" in caplog.text
    assert "Jane" not in caplog.text


def test_us_11_1_queue_drops_finished_jobs_after_30_days(tmp_path: Path, clock: Clock) -> None:
    queue = make_queue(tmp_path / QUEUE_FILE, clock)
    old = queue.enqueue("default", "c1", "call_0123456789abcdef")
    queue.finish(old.job_id)
    waiting = queue.enqueue("default", "c2", "call_0123456789abcdef")
    clock.now = DAY + FINISHED_TTL + timedelta(seconds=1)
    queue.enqueue("default", "c3", "call_0123456789abcdef")
    assert old.job_id not in {job.job_id for job in queue.jobs()}
    assert waiting.job_id in {job.job_id for job in queue.jobs()}, "queued jobs are kept"


def test_us_11_1_queue_due_per_profile_window(tmp_path: Path, clock: Clock) -> None:
    windows = {"day": TranscriptionWindow(start_hour=9, end_hour=17)}
    queue = TranscriptionQueue(
        tmp_path / QUEUE_FILE,
        lambda profile: windows.get(profile, TranscriptionWindow()),
        clock=clock,
        tz=UTC,
    )
    night = queue.enqueue("default", "c1", "call_0123456789abcdef")
    queue.enqueue("default", "c4", "call_0123456789abcdef")  # its window is read once
    first = queue.enqueue("day", "c2", "call_0123456789abcdef")
    second = queue.enqueue("day", "c3", "call_0123456789abcdef")
    assert queue.due() == first, "the default window is closed at 10:00; the day window is open"
    assert queue.due(skip=[first.job_id]) == second
    queue.start(second.job_id)
    assert queue.due(skip=[first.job_id]) is None
    clock.now = NIGHT
    assert queue.due() == night


def test_us_11_1_queue_write_failure_leaves_the_old_file(
    tmp_path: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = make_queue(tmp_path / QUEUE_FILE, clock)
    job = queue.enqueue("default", "c1", "call_0123456789abcdef")
    before = queue.path.read_bytes()

    def broken(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "fdopen", broken)
    with pytest.raises(OSError, match="disk full"):
        queue.fail(job.job_id, "model_unavailable")
    assert queue.path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == [QUEUE_FILE], "no partial file is left"
    assert queue.jobs()[0].state == "queued", "memory changes only once the file is written"
    with pytest.raises(OSError, match="disk full"):
        queue.enqueue("default", "c2", "call_0123456789abcdef")
    assert [j.case_id for j in queue.jobs()] == ["c1"]


# --- The transcription request -------------------------------------------------------------------


async def test_us_11_1_transcribe_names_the_default_model_without_a_path() -> None:
    seen: list[httpx.Request] = []
    endpoint = ModelEndpoint(role=ModelRole.TRANSCRIPTION, base_url="http://127.0.0.1:18207/v1")
    result = await transcribe(endpoint, FLAC, "flac", transport=voxtral(seen=seen))
    assert (result.text, result.truncated) == (TRANSCRIPT, False)
    assert b'name="model"\r\n\r\ndefault_model' in seen[0].content
    assert b"audio/flac" in seen[0].content


async def test_us_11_1_transcribe_refusals() -> None:
    endpoint = ModelEndpoint(role=ModelRole.TRANSCRIPTION, base_url="http://127.0.0.1:18207/v1")
    with pytest.raises(ModelUnavailableError):
        await transcribe(endpoint, WAV, "wav", transport=voxtral(status=503))
    with pytest.raises(TranscriptionFailedError):
        await transcribe(endpoint, WAV, "wav", transport=voxtral({"text": ""}))


def test_us_11_1_error_codes() -> None:
    assert (CallTooLargeError.code, CallTooLargeError.status_code) == ("call_too_large", 413)
    assert (CallNotFoundError.code, CallNotFoundError.status_code) == ("call_not_found", 404)


# --- Retention ------------------------------------------------------------------------------------


async def test_us_11_1_purge_removes_calls(
    desktop: httpx.AsyncClient, cases: CaseService, queue: TranscriptionQueue, clock: Clock
) -> None:
    case_id, call_id = await queue_one(desktop, clock)
    await scheduler(cases, queue, []).run_due()
    await desktop.post(f"{PREFIX}/cases/{case_id}/outcome", json={"outcome": CaseOutcome.UPHELD})
    response = cases.corpus.purge(PurgeRequest(profile="default", case_id=case_id, confirm=True))
    (report,) = response.reports
    assert report.documents == 1, "the recording counts as a document"
    store = cases.store("default")
    assert store.case_items(case_id, "call") == []
    assert store.case_items(case_id, "transcript") == []
    assert store.case_item_data(case_id, call_id) is None
    with pytest.raises(CaseClosedError):
        cases.call_audio("default", case_id, call_id)


def test_us_11_1_transcript_is_typed() -> None:
    with pytest.raises(ValidationError):
        CallTranscript(call_id="call_0123456789abcdef", text="", transcribed_at=utc_now())


# --- Review regressions --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "fmt"), [(WAV, "wav"), (MP3_ID3, "mp3"), (FLAC, "flac"), (M4A, "m4a")]
)
async def test_us_11_1_every_format_is_sent_as_call_wav(data: bytes, fmt: AudioFormat) -> None:
    """Review: mlx_audio.server writes the decoded call under the upload's suffix; M4A cannot be."""
    seen: list[httpx.Request] = []
    endpoint = ModelEndpoint(role=ModelRole.TRANSCRIPTION, base_url="http://127.0.0.1:18207/v1")
    await transcribe(endpoint, data, fmt, transport=voxtral(seen=seen))
    assert b'filename="call.wav"' in seen[0].content
    assert f'filename="call.{fmt}"'.encode() not in seen[0].content or fmt == "wav"


async def test_us_11_1_a_transcript_cut_off_at_the_limit_is_flagged(
    desktop: httpx.AsyncClient, cases: CaseService, queue: TranscriptionQueue, clock: Clock
) -> None:
    """Review: max_tokens caps the whole transcript; a call longer than that is flagged."""
    case_id, _call = await queue_one(desktop, clock)
    reply = {"text": TRANSCRIPT, "segments": None, "generation_tokens": MAX_TOKENS}
    await scheduler(cases, queue, [], transport=voxtral(reply)).run_due()
    transcript = (await open_case(desktop, case_id)).calls[0].transcript
    assert transcript is not None
    assert transcript.truncated is True


async def test_us_11_1_no_call_starts_near_the_window_end(
    desktop: httpx.AsyncClient, cases: CaseService, queue: TranscriptionQueue, clock: Clock
) -> None:
    """Review: a call started at 06:59 would hold Voxtral alone into the working day."""
    await queue_one(desktop, clock)
    clock.now = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)  # 30 minutes left in 19-07
    loads: list[ModelRole] = []
    assert await scheduler(cases, queue, loads).run_due() == 0
    assert loads == []
    clock.now = datetime(2026, 11, 1, 6, 14, tzinfo=UTC)  # 46 minutes left
    assert await scheduler(cases, queue, loads).run_due() == 1


async def test_us_11_1_a_call_is_stopped_after_the_window_ends(
    desktop: httpx.AsyncClient, cases: CaseService, queue: TranscriptionQueue, clock: Clock
) -> None:
    """Review: the request's deadline is the window's end plus the grace period."""
    await queue_one(desktop, clock)
    clock.now = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
    timeouts: list[float] = []

    def slow(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"]["read"])
        raise httpx.ReadTimeout("slow", request=request)

    await scheduler(cases, queue, [], transport=httpx.MockTransport(slow)).run_due()
    assert timeouts == [(timedelta(hours=1) + WINDOW_GRACE).total_seconds()]
    (job,) = queue.jobs()
    assert (job.state, job.error_code) == ("failed", "processing_timeout")


def test_us_11_1_window_remaining() -> None:
    evening = TranscriptionWindow(start_hour=19, end_hour=7)
    assert evening.remaining(NIGHT) == timedelta(hours=9)
    assert evening.remaining(DAY.replace(hour=6, minute=30) + timedelta(days=1)) == timedelta(
        minutes=30
    )
    assert evening.remaining(DAY) == timedelta(0)
    early = TranscriptionWindow(start_hour=1, end_hour=5)
    assert early.remaining(DAY.replace(hour=2)) == timedelta(hours=3)


async def test_us_11_1_views_show_the_current_window(
    desktop: httpx.AsyncClient, service: CorpusService, clock: Clock
) -> None:
    """Review: a queued job shows the window the scheduler will use, not the one at queue time."""
    windows = {"default": TranscriptionWindow()}
    queue = TranscriptionQueue(
        transcription_dir(service.root) / "other.json",
        lambda profile: windows[profile],
        clock=clock,
        tz=UTC,
    )
    cases = CaseService(service, queue)
    case_id = await new_case(desktop)
    call_id = await attached(desktop, case_id)
    cases.queue_transcription("default", case_id, call_id)
    windows["default"] = TranscriptionWindow(start_hour=22, end_hour=5)
    (job,) = queue.jobs()
    assert (job.window.start_hour, job.not_before) == (22, DAY.replace(hour=22))
    shown = cases.calls(service.user_store("default"), case_id)[0].transcription
    assert shown == job
    again = cases.queue_transcription("default", case_id, call_id).job
    assert again == job, "submitting again answers the current window too"
    queue.start(job.job_id)
    queue.finish(job.job_id)
    windows["default"] = TranscriptionWindow(start_hour=20, end_hour=6)
    assert queue.jobs()[0].window.start_hour == 22, "a finished job keeps the window it ran in"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Your reference number is 8417293. We are tracking 2024 claims.", "8417293"),
        ("We issued a REFUND 4471 last week.", None),
        ("The case 99887766 is closed.", None),
    ],
)
def test_us_11_1_notes_cues_are_whole_words(text: str, expected: str | None) -> None:
    assert reference_number(text) == expected


def test_us_11_1_unedited_transcription_command_migrates(tmp_path: Path) -> None:
    """Review: mlx_audio.server has no --model; an unedited copy is fixed, an edited one kept."""
    new = DEFAULT_REGISTRY.read_text()
    shipped = '"--port", "{port}", "--log-dir", "{logs}"]'
    assert shipped in new
    old = new.replace(
        '"mlx_audio.server", "--host", "{host}", "--port", "{port}", "--log-dir", "{logs}"]',
        '"mlx_audio.server", "--model", "{model}", "--host", "{host}", "--port", "{port}"]',
    )
    assert old != new
    (tmp_path / REGISTRY_FILE).write_text(old)
    path = ensure_registry_file(tmp_path)
    assert path.read_text() == new
    command = ModelRegistry.load(path).roles[ModelRole.TRANSCRIPTION].command
    assert "--model" not in command
    assert command[-2:] == ["--log-dir", "{logs}"]
    edited = tmp_path / "edited"
    edited.mkdir()
    custom = old.replace('"--port", "{port}"]', '"--port", "{port}", "--reload"]')
    (edited / REGISTRY_FILE).write_text(custom)
    assert ensure_registry_file(edited).read_text() == custom


async def test_us_11_1_model_servers_spawn_owner_only_with_a_logs_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review: mlx_audio.server writes the decoded call to /tmp and logs/ to its cwd."""
    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    manager = ModelManager(registry, models_home=tmp_path / "Models", state_dir=tmp_path / "state")
    spawned: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    async def capture(*argv: str, **kwargs: Any) -> None:
        spawned.append((argv, kwargs))
        raise OSError("not started in this test")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    server = manager._by_role[ModelRole.TRANSCRIPTION]
    assert await manager._launch(server) is False
    ((argv, kwargs),) = spawned
    logs = tmp_path / "state" / "server-logs"
    assert argv[-2:] == ("--log-dir", str(logs))
    assert "--model" not in argv
    assert kwargs["umask"] == 0o077
    assert stat.S_IMODE(logs.stat().st_mode) == 0o700


@pytest.mark.models
async def test_us_11_1_real_voxtral_transcribes_a_spoken_call(tmp_path: Path) -> None:
    """Voxtral-Small-24B from MODELS_HOME transcribes speech made by macOS ``say``."""
    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    home = models_home()
    spec = registry.roles[ModelRole.TRANSCRIPTION]
    if spec.weights(home) == "missing" or not os.access(home, os.R_OK):
        pytest.skip(f"Voxtral weights not found at {spec.model_path(home)}")
    say = shutil.which("say")
    if say is None:
        pytest.skip("macOS say is not available to synthesize the call")
    spoken = tmp_path / "call.wav"
    subprocess.run(
        [
            say,
            "-o",
            str(spoken),
            "--data-format=LEI16@16000",
            "You need to resubmit the claim with the referral attached. "
            "Your reference number for this call is 5 5 0 1 2 3 4.",
        ],
        check=True,
        timeout=60,
    )
    manager = ModelManager(registry, models_home=home, state_dir=tmp_path / "models")
    try:
        async with manager.use(ModelRole.TRANSCRIPTION) as endpoint:
            result = await transcribe(
                endpoint, spoken.read_bytes(), sniff_audio(spoken.read_bytes())
            )
    finally:
        await manager.shutdown()
    assert reference_number(result.text) == "5501234"
    assert any("resubmit" in line for line in rep_instructions(result.text))
    assert result.truncated is False
