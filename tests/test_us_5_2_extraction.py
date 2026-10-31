"""US-5.2 Structured Extraction and Field Confirmation (Python half).

Scenarios: extraction fills the structured case; unreadable fields are highlighted; confirmed
fields are stored as confirmed; extraction progress is pushed as events. Also: the 835 reader, one
value at a time validation, the job registry, the gateway relay, and the extraction prompt. The
pane scenarios run under ``node --test`` (``plugin/desktop/tests/case_extraction.test.mjs``).
Rules: ES-1, ES-4, BR-1, BR-2, BR-10, BR-14, PC-4.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import httpx
import pymupdf
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach import PLUGIN_NAME
from claimcoach.api import relay, routes
from claimcoach.api.client import WorkerClient
from claimcoach.api.models import ERROR_MESSAGES, ErrorEnvelope
from claimcoach.cases.errors import FieldError, JobNotFoundError, NoDocumentsError
from claimcoach.cases.extraction import (
    CaseExtraction,
    Extracted,
    FieldConfirmation,
    FieldStatus,
    JobStarted,
    read_value,
)
from claimcoach.cases.intake import parse_upload
from claimcoach.cases.models import Case, SourceDocument
from claimcoach.cases.service import CaseService
from claimcoach.corpus.errors import CaseClosedError, CaseNotFoundError
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, CaseItem, utc_now
from claimcoach.events import CaseProgressEvent, EventSink
from claimcoach.models.chat import DEFAULT_MODEL_ID, chat_completion
from claimcoach.models.manager import ModelEndpoint, ModelUnavailableError
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.edi835 import parse_835
from claimcoach.pipeline.extract import (
    EXTRACTION_TEMPLATE,
    MAX_SIDE,
    TEXT_CHUNK,
    Extractor,
    _dpi,
    parse_reply,
    rasterize_pdf,
    to_png,
    units_of,
)
from claimcoach.pipeline.jobs import JOB_TTL, MAX_JOBS, JobRegistry
from claimcoach.pipeline.reading import Reading, SourceReading, build_extraction
from claimcoach.prompts.builder import DataItem, PromptParts, build_prompt, data_close
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.eob import EOB_LINES, eob_reply, synthetic_eob_pdf
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import static_models
from tests.test_us_5_1_case_intake import ERA_835, PNG, hermes_multipart

PNG_IMAGE: Final = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
"""A real 1x1 PNG (``PNG`` in the US-5.1 tests is a signature followed by junk)."""

PREFIX: Final = "/api/plugins/claimcoach"

Sent = list[tuple[str, str, dict[str, Any]]]


@pytest.fixture(scope="module")
def vision() -> Iterator[FakeModelServer]:
    """A fake Qwen3-VL-8B: answers every chat request with the EOB reading."""
    with FakeModelServer() as server:
        yield server


@pytest.fixture(autouse=True)
def _reset_vision(vision: FakeModelServer) -> None:
    vision.requests.clear()
    vision.replies[DEFAULT_MODEL_ID] = eob_reply()


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def worker(service: CorpusService, vision: FakeModelServer) -> FastAPI:
    return create_app(TOKEN, corpus=service, pipeline_models=static_models(vision.base_url))


@pytest.fixture
def sent() -> Sent:
    return []


@pytest.fixture
async def desktop(
    worker: FastAPI, sent: Sent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """``ctx.rest`` against the gateway, whose events land in ``sent``."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: client

    def sink(plugin: str, event: str, payload: dict[str, Any]) -> None:
        sent.append((plugin, event, payload))

    gateway.dependency_overrides[routes.get_event_sink] = lambda: sink
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        yield desktop


def assert_envelope(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = ErrorEnvelope.model_validate_json(response.content)
    assert (body.error.code, body.error.message) == (code, ERROR_MESSAGES[body.error.code])


async def case_with(desktop: httpx.AsyncClient, *uploads: tuple[bytes, str]) -> str:
    response = await desktop.post(f"{PREFIX}/cases", json={})
    case_id = Case.model_validate_json(response.content).case_id
    for body, content_type in uploads:
        added = await desktop.post(
            f"{PREFIX}/cases/{case_id}/documents",
            content=body,
            headers={"content-type": content_type},
        )
        assert added.status_code == 200, added.text
    return case_id


async def process(desktop: httpx.AsyncClient, case_id: str) -> JobStarted:
    """Press Process case and wait until the gateway relayed the job's last event."""
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/process", json={})
    assert response.status_code == 200, response.text
    await asyncio.gather(*relay._RELAYS.values())
    return JobStarted.model_validate_json(response.content)


async def open_case(desktop: httpx.AsyncClient, case_id: str) -> Case:
    response = await desktop.get(f"{PREFIX}/cases/{case_id}")
    assert response.status_code == 200, response.text
    return Case.model_validate_json(response.content)


def eob_upload(pages: int = 1) -> tuple[bytes, str]:
    return hermes_multipart("eob.pdf", "application/pdf", synthetic_eob_pdf(pages))


def assert_eob_fields(extraction: CaseExtraction) -> None:
    assert (extraction.payer_name.value, extraction.claim_id.value) == (
        "ACME HEALTH PLAN",
        "CLAIM-77",
    )
    line = extraction.lines[0]
    assert (line.procedure_code.value, line.service_date.value) == ("99213", date(2026, 9, 1))
    assert (line.billed_amount.value, line.paid_amount.value) == (Decimal("250.00"), Decimal(0))
    adjustment = line.adjustments[0]
    assert (adjustment.group_code.value, adjustment.carc.value, adjustment.amount.value) == (
        "CO",
        "197",
        Decimal("250.00"),
    )
    assert [code.value for code in line.rarc_codes] == ["N286"]
    # The stored case round-trips through the typed model (ES-1).
    assert CaseExtraction.model_validate_json(extraction.model_dump_json()) == extraction


# --- Scenario: Extraction fills the structured case ----------------------------------------------


@pytest.mark.models
async def test_us_5_2_extraction_fills_case(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    """Qwen3-VL-8B from MODELS_HOME reads the synthetic EOB (skips without its weights)."""
    from claimcoach.models.manager import ModelManager  # noqa: PLC0415
    from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry, models_home  # noqa: PLC0415

    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    home = models_home()
    spec = registry.roles[ModelRole.EXTRACTION]
    if spec.weights(home) == "missing" or not os.access(home, os.R_OK):
        pytest.skip(f"Qwen3-VL-8B weights not found at {spec.model_path(home)}")
    models = ModelManager(registry, models_home=home, state_dir=tmp_path / "models")
    corpus = make_service(tmp_path / "hermes", corpus_server)
    cases = CaseService(corpus)
    try:
        case_id = cases.create("default").case_id
        body, content_type = eob_upload()

        cases.add_file("default", case_id, parse_upload(body, content_type))
        stages: list[str] = []
        extraction = await Extractor(cases, models.use).run(
            "default", case_id, lambda stage, _progress: stages.append(stage)
        )
    finally:
        await models.shutdown()
        corpus.close()
    assert stages[-1] == "done"
    assert extraction.lines, "the model read at least one claim line"
    line = extraction.lines[0]
    assert line.adjustments
    assert line.adjustments[0].carc.value == "197"
    assert line.adjustments[0].group_code.value == "CO"
    assert [code.value for code in line.rarc_codes] == ["N286"]
    assert line.service_date.value == date(2026, 9, 1)


async def test_us_5_2_extraction_fills_case_offline(
    desktop: httpx.AsyncClient, service: CorpusService, vision: FakeModelServer
) -> None:
    case_id = await case_with(desktop, eob_upload())
    started = await process(desktop, case_id)
    assert started.case_id == case_id

    case = await open_case(desktop, case_id)
    assert case.extraction is not None
    assert_eob_fields(case.extraction)
    assert case.needs_confirmation == []
    assert case.extraction.sources == [case.documents[0].doc_id]

    # One model call for the one page: the page image and its text layer are data (BR-10).
    (request,) = vision.requests
    system, user = request.messages
    assert isinstance(system.content, str)
    assert system.content.startswith(EXTRACTION_TEMPLATE.system)
    assert isinstance(user.content, list)
    text, image = user.content
    assert text["text"].startswith(EXTRACTION_TEMPLATE.instructions)
    assert EOB_LINES[1].split()[0] in text["text"]
    boundary = text["text"].rsplit("<<<END DATA ", 1)[1].removesuffix(">>>")
    assert text["text"].endswith(data_close(boundary))
    assert image["image_url"]["url"].startswith("data:image/png;base64,iVBOR")
    assert request.model == DEFAULT_MODEL_ID  # a static endpoint names no model path
    actions = [e.action for e in service.user_store("default").audit_log(case_id)]
    assert AuditAction.CASE_EXTRACTED in actions


async def test_us_5_2_835_extraction_fills_case(
    desktop: httpx.AsyncClient, vision: FakeModelServer
) -> None:
    case_id = await case_with(desktop)
    await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": ERA_835})
    await process(desktop, case_id)
    case = await open_case(desktop, case_id)
    assert case.extraction is not None
    assert_eob_fields(case.extraction)
    assert vision.requests == [], "835 text is parsed, no model is called"


async def test_us_5_2_835_lines_win_over_a_scanned_copy(
    desktop: httpx.AsyncClient, vision: FakeModelServer
) -> None:
    vision.replies[DEFAULT_MODEL_ID] = eob_reply(claim_id=None, payer_name="Other Name")
    case_id = await case_with(desktop, eob_upload())
    await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": ERA_835})
    await process(desktop, case_id)
    extraction = (await open_case(desktop, case_id)).extraction
    assert extraction is not None
    assert len(extraction.lines) == 1, "the EOB's copy of the line is not added again"
    assert extraction.payer_name.value == "ACME HEALTH PLAN"  # the 835 is read first
    assert len(extraction.sources) == 2


# --- Scenario: Unreadable fields are highlighted -------------------------------------------------


async def test_us_5_2_unreadable_fields_highlighted(
    desktop: httpx.AsyncClient, vision: FakeModelServer
) -> None:
    line = {
        "procedure_code": "99213",
        "service_date": "13/45/2026",
        "billed_amount": "two hundred",
        "paid_amount": None,
        "adjustments": [{"group_code": "XX", "carc": "197", "amount": "250"}],
        "rarc_codes": ["N286", "X1"],
    }
    vision.replies[DEFAULT_MODEL_ID] = eob_reply(claim_id=None, lines=[line])
    case_id = await case_with(desktop, eob_upload())
    await process(desktop, case_id)
    case = await open_case(desktop, case_id)
    assert case.needs_confirmation == [
        "claim_id",
        "lines.0.service_date",
        "lines.0.billed_amount",
        "lines.0.paid_amount",
        "lines.0.adjustments.0.group_code",
        "lines.0.rarc_codes.1",
    ]
    assert case.extraction is not None
    fields = dict(case.extraction.fields())
    for path in case.needs_confirmation:
        assert (fields[path].status, fields[path].value) == (FieldStatus.UNREADABLE, None)
    assert fields["lines.0.adjustments.0.carc"].status is FieldStatus.EXTRACTED


async def test_us_5_2_an_unusable_reply_leaves_every_field_unreadable(
    desktop: httpx.AsyncClient, vision: FakeModelServer
) -> None:
    vision.replies[DEFAULT_MODEL_ID] = "I cannot read this page."
    case_id = await case_with(desktop, eob_upload())
    await process(desktop, case_id)
    case = await open_case(desktop, case_id)
    assert case.needs_confirmation == [
        "payer_name",
        "claim_id",
        "billed_amount",
        "paid_amount",
        "denial_date",  # US-6.3
    ]


# --- Scenario: Confirmed fields are stored as confirmed ------------------------------------------


async def test_us_5_2_confirmed_fields_stored(
    desktop: httpx.AsyncClient, service: CorpusService, vision: FakeModelServer
) -> None:
    vision.replies[DEFAULT_MODEL_ID] = eob_reply(claim_id=None)
    case_id = await case_with(desktop, eob_upload())
    await process(desktop, case_id)
    assert (await open_case(desktop, case_id)).needs_confirmation == ["claim_id"]

    fields = f"{PREFIX}/cases/{case_id}/fields"
    response = await desktop.post(fields, json={"path": "claim_id", "value": " CLAIM-77 "})
    assert response.status_code == 200, response.text
    case = Case.model_validate_json(response.content)
    assert case.extraction is not None
    assert case.extraction.claim_id == Extracted[str](
        value="CLAIM-77", status=FieldStatus.CONFIRMED
    )
    assert case.needs_confirmation == []
    assert (await open_case(desktop, case_id)).needs_confirmation == []
    actions = [e.action for e in service.user_store("default").audit_log(case_id)]
    assert AuditAction.FIELD_CONFIRMED in actions

    # A correction of an extracted value is a confirmation too.
    response = await desktop.post(
        fields, json={"path": "lines.0.service_date", "value": "2026-09-02"}
    )
    line = Case.model_validate_json(response.content).extraction.lines[0]  # type: ignore[union-attr]
    assert (line.service_date.value, line.service_date.status) == (
        date(2026, 9, 2),
        FieldStatus.CONFIRMED,
    )

    # A re-run keeps what the biller confirmed.
    await process(desktop, case_id)
    rerun = (await open_case(desktop, case_id)).extraction
    assert rerun is not None
    assert rerun.claim_id.status is FieldStatus.CONFIRMED
    assert rerun.lines[0].service_date.value == date(2026, 9, 2)


async def test_us_5_2_invalid_confirmations_change_nothing(desktop: httpx.AsyncClient) -> None:
    case_id = await case_with(desktop, eob_upload())
    fields = f"{PREFIX}/cases/{case_id}/fields"
    no_extraction = await desktop.post(fields, json={"path": "claim_id", "value": "X"})
    assert_envelope(no_extraction, 422, "invalid_request")
    await process(desktop, case_id)
    before = await open_case(desktop, case_id)
    for body in (
        {"path": "lines.0.service_date", "value": "not a date"},
        {"path": "lines.9.service_date", "value": "2026-09-01"},
        {"path": "lines.0.adjustments.0.carc", "value": "Jane Doe"},
        {"path": "../etc", "value": "x"},
        {"path": "claim_id", "value": ""},
    ):
        response = await desktop.post(fields, json=body)
        assert_envelope(response, 422, "invalid_request")
        assert b"Jane Doe" not in response.content
    assert_envelope(await desktop.post(fields, content=b"x"), 422, "invalid_request")
    assert_envelope(
        await desktop.post(
            f"{PREFIX}/cases/bad id/fields", json={"path": "claim_id", "value": "1"}
        ),
        422,
        "invalid_request",
    )
    assert await open_case(desktop, case_id) == before


# --- Scenario: Extraction progress is pushed as events -------------------------------------------


async def test_us_5_2_progress_pushed_as_events(desktop: httpx.AsyncClient, sent: Sent) -> None:
    case_id = await case_with(desktop, eob_upload(pages=2))
    started = await process(desktop, case_id)
    assert {(plugin, event) for plugin, event, _ in sent} == {(PLUGIN_NAME, "case.progress")}
    events = [CaseProgressEvent.model_validate(payload) for _, _, payload in sent]
    assert {(e.case_id, e.job_id) for e in events} == {(case_id, started.job_id)}
    assert [e.stage for e in events] == ["extracting", "extracting", "extracting", "done"]
    progress = [e.progress for e in events]
    assert progress == sorted(progress)
    assert (progress[0], progress[-1]) == (0.0, 1.0)
    # PHI-free by construction (US-3.4): nothing read from the document is in any payload.
    wire = json.dumps([payload for _, _, payload in sent])
    for text in ("ACME", "CLAIM-77", "eob.pdf", "99213"):
        assert text not in wire


class Failing:
    """A model provider whose ``use`` raises ``error`` (or whose call does, ``on_call``)."""

    def __init__(self, error: Exception | None) -> None:
        self.error = error

    @asynccontextmanager
    async def __call__(self, role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        if self.error is not None:
            raise self.error
        yield ModelEndpoint(role=role, base_url="http://127.0.0.1:9/v1")


def registry_for(service: CorpusService, provider: Any) -> tuple[JobRegistry, CaseService, str]:
    cases = CaseService(service)
    case_id = cases.create("default").case_id

    cases.add_file("default", case_id, parse_upload(*eob_upload()))
    return JobRegistry(Extractor(cases, provider)), cases, case_id


async def finish(jobs: JobRegistry, job_id: str) -> list[CaseProgressEvent]:
    events: list[CaseProgressEvent] = []
    while True:
        batch = await jobs.events(job_id, len(events), wait=5)
        events += batch.events
        if batch.finished:
            return events


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ModelUnavailableError(), "model_unavailable"),
        (CaseClosedError(), "case_closed"),
        (NoDocumentsError(), "no_documents"),
        (RuntimeError("Jane Doe"), "extraction_failed"),
    ],
)
async def test_us_5_2_a_failed_job_ends_with_its_code(
    service: CorpusService, error: Exception, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    jobs, _cases, case_id = registry_for(service, Failing(error))
    started = jobs.start("default", case_id)
    events = await finish(jobs, started.job_id)
    assert (events[-1].stage, events[-1].error_code) == ("failed", code)
    assert "Jane Doe" not in caplog.text  # BR-14: the error type only


# --- Job registry -------------------------------------------------------------------------------


async def test_us_5_2_one_job_per_case(service: CorpusService, vision: FakeModelServer) -> None:
    jobs, _cases, case_id = registry_for(service, static_models(vision.base_url))
    first = jobs.start("default", case_id)
    assert jobs.start("default", case_id) == first, "a double click joins the running job"
    events = await finish(jobs, first.job_id)
    assert events[-1].stage == "done"
    assert (await jobs.events(first.job_id, len(events), wait=5)).events == []
    assert jobs.start("default", case_id).job_id != first.job_id, "a finished job is not reused"
    with pytest.raises(JobNotFoundError):
        await jobs.events("job_0000000000000000")


async def test_us_5_2_a_poll_without_news_returns_after_its_wait(service: CorpusService) -> None:
    gate = asyncio.Event()

    @asynccontextmanager
    async def slow(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        await gate.wait()
        if gate.is_set():
            raise ModelUnavailableError
        yield ModelEndpoint(role=role, base_url="http://127.0.0.1:9/v1")

    jobs, _cases, case_id = registry_for(service, slow)
    started = jobs.start("default", case_id)
    first = await jobs.events(started.job_id, 0, wait=1)
    assert [e.stage for e in first.events] == ["extracting"]
    quiet = await jobs.events(started.job_id, 1, wait=0.05)
    assert (quiet.events, quiet.finished) == ([], False)
    gate.set()
    events = await finish(jobs, started.job_id)
    assert events[-1].stage == "failed"
    await jobs.shutdown()


async def test_us_5_2_finished_jobs_expire(service: CorpusService, vision: FakeModelServer) -> None:
    now = [0.0]
    cases = CaseService(service)
    jobs = JobRegistry(Extractor(cases, static_models(vision.base_url)), clock=lambda: now[0])

    ids = []
    for _ in range(2):
        case_id = cases.create("default").case_id
        cases.add_file("default", case_id, parse_upload(*eob_upload()))
        started = jobs.start("default", case_id)
        await finish(jobs, started.job_id)
        ids.append((case_id, started.job_id))
    now[0] = JOB_TTL + 1
    jobs.start("default", ids[1][0])
    with pytest.raises(JobNotFoundError):
        await jobs.events(ids[0][1])
    await jobs.shutdown()


async def test_us_5_2_the_oldest_finished_job_makes_room(service: CorpusService) -> None:
    jobs = JobRegistry(Extractor(CaseService(service), Failing(ModelUnavailableError())))
    finished = []
    for index in range(MAX_JOBS):
        started = jobs.start("default", f"case_{index:016x}")
        await finish(jobs, started.job_id)
        finished.append(started.job_id)
    jobs.start("default", "case_ffffffffffffffff")
    with pytest.raises(JobNotFoundError):
        await jobs.events(finished[0])
    assert (await jobs.events(finished[1])).finished
    await jobs.shutdown()


async def test_us_5_2_shutdown_cancels_running_jobs(service: CorpusService) -> None:
    started_event = asyncio.Event()

    @asynccontextmanager
    async def hang(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        started_event.set()
        await asyncio.Event().wait()
        yield ModelEndpoint(role=role, base_url="http://127.0.0.1:9/v1")

    jobs, _cases, case_id = registry_for(service, hang)
    started = jobs.start("default", case_id)
    await started_event.wait()
    await jobs.shutdown()
    batch = await jobs.events(started.job_id)
    assert batch.finished
    await jobs.shutdown()  # nothing left to cancel


# --- The worker refuses what it cannot extract ----------------------------------------------------


async def test_us_5_2_process_refusals(desktop: httpx.AsyncClient, service: CorpusService) -> None:
    empty = await case_with(desktop)
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/{empty}/process", json={}), 409, "no_documents"
    )
    closed = await case_with(desktop, eob_upload())
    service.user_store("default").close_case(closed)
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/{closed}/process", json={}), 409, "case_closed"
    )
    service.user_store("default").create_case("legacy-id")
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/legacy-id/process", json={}), 404, "case_not_found"
    )
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/x y/process", json={}), 422, "invalid_request"
    )
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/{empty}/process", content=b"x"), 422, "invalid_request"
    )


async def test_us_5_2_worker_without_models_cannot_extract(service: CorpusService) -> None:
    app = create_app(TOKEN, corpus=service)
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://w", headers=headers) as w:
        assert_envelope(await w.post(f"/cases/{case_id}/extract"), 503, "model_unavailable")
        assert_envelope(await w.get("/jobs/job_0000000000000000/events"), 404, "not_found")


async def test_us_5_2_job_events_route(worker: FastAPI) -> None:
    transport = httpx.ASGITransport(app=worker)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://w", headers=headers) as w:
        missing = await w.get("/jobs/job_0000000000000000/events", params={"wait": 0})
        assert_envelope(missing, 404, "job_not_found")
        assert_envelope(await w.get("/jobs/nope/events"), 422, "invalid_request")
        too_long = await w.get("/jobs/job_0000000000000000/events", params={"wait": 99})
        assert_envelope(too_long, 422, "invalid_request")


def test_us_5_2_check_extractable_names_each_refusal(service: CorpusService) -> None:
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    with pytest.raises(NoDocumentsError):
        cases.check_extractable("default", case_id)
    with pytest.raises(CaseNotFoundError):
        cases.check_extractable("default", "c1")
    with pytest.raises(FieldError):
        cases.confirm_field(
            "default",
            case_id,
            __import__("claimcoach").cases.extraction.FieldConfirmation(path="claim_id", value="1"),
        )


# --- The gateway relay (PC-4) ---------------------------------------------------------------------


def started_job() -> JobStarted:
    return JobStarted(case_id="case_0123456789abcdef", job_id="job_0123456789abcdef")


async def test_us_5_2_relay_reports_a_lost_worker() -> None:
    sent: Sent = []
    naps: list[float] = []

    def sink(plugin: str, event: str, payload: dict[str, Any]) -> None:
        sent.append((plugin, event, payload))

    async def nap(seconds: float) -> None:
        naps.append(seconds)

    client = WorkerClient("http://worker", lambda: None)
    relayed = await relay.relay_job(client, started_job(), sink, sleep=nap)
    assert relayed == 0
    assert naps == [relay.RETRY_DELAY] * (relay.MAX_FAILURES - 1)
    (event,) = [CaseProgressEvent.model_validate(payload) for _, _, payload in sent]
    assert (event.stage, event.error_code) == ("failed", "worker_unavailable")


async def test_us_5_2_relay_recovers_from_a_dropped_poll() -> None:
    sent: Sent = []
    answers = iter(
        [
            httpx.Response(503),
            httpx.Response(
                200,
                json={
                    "ok": True,
                    "job_id": started_job().job_id,
                    "events": [
                        {
                            "case_id": started_job().case_id,
                            "job_id": started_job().job_id,
                            "stage": "done",
                            "progress": 1.0,
                        }
                    ],
                    "finished": True,
                },
            ),
        ]
    )
    transport = httpx.MockTransport(lambda _request: next(answers))
    client = WorkerClient("http://worker", lambda: "t", transport=transport)

    async def nap(_seconds: float) -> None:
        return None

    sink: EventSink = lambda plugin, event, payload: sent.append((plugin, event, payload))  # noqa: E731
    assert await relay.relay_job(client, started_job(), sink, sleep=nap) == 1
    assert [payload["stage"] for _, _, payload in sent] == ["done"]


async def test_us_5_2_relay_stops_at_its_deadline() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": True, "job_id": started_job().job_id, "events": [], "finished": False}
        )

    ticks = iter([0.0, 0.0, 10.0])
    sent: Sent = []
    client = WorkerClient("http://worker", lambda: "t", transport=httpx.MockTransport(handler))
    relayed = await relay.relay_job(
        client,
        started_job(),
        lambda plugin, event, payload: sent.append((plugin, event, payload)),
        deadline=5,
        clock=lambda: next(ticks),
    )
    assert relayed == 0
    # The pane never waits forever: the relay's last word is a failed event (review finding).
    (event,) = [CaseProgressEvent.model_validate(payload) for _, _, payload in sent]
    assert (event.stage, event.error_code) == ("failed", "processing_timeout")


async def test_us_5_2_gateway_relays_worker_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    def handler(_request: httpx.Request) -> httpx.Response:
        body = {"ok": False, "error": {"code": "no_documents", "message": "worker text"}}
        return httpx.Response(409, json=body)

    client = WorkerClient("http://worker", lambda: "t", transport=httpx.MockTransport(handler))
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    app.dependency_overrides[routes.get_worker_client] = lambda: client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://g") as desktop:
        process_response = await desktop.post(f"{PREFIX}/cases/case_1/process", json={})
        assert_envelope(process_response, 409, "no_documents")
        confirm = await desktop.post(
            f"{PREFIX}/cases/case_1/fields", json={"path": "claim_id", "value": "1"}
        )
        assert_envelope(confirm, 409, "no_documents")
    assert not relay._RELAYS


def test_us_5_2_event_sink_is_hermes_broadcast() -> None:
    assert routes.get_event_sink() is None  # no gateway in the test process


# --- 835 reader -----------------------------------------------------------------------------------


def test_us_5_2_835_reader_details() -> None:
    era = (
        ERA_835.replace(
            "CLP*PCN-0001*4*250*0**12*CLAIM-77*11*1~",
            "CLP*PCN-0001*4*250*0**12**11*1~CAS*OA*23*10**45*5~MOA***MA130*N1~",
        )
        .replace(
            "SVC*HC:99213*250*0**1~DTM*472*20260901~CAS*CO*197*250~LQ*HE*N286~",
            "SVC*99214*100*0~DTM*150*20260801~DTM*472*20260802~DTM*150*20260803~LQ*RX*1~"
            "CAS*PR*1*10*1*2*~SVC*HC:J1100*5~DTM*472*2026-08~",
        )
        .replace("SE*12*0001~", "CLP*PCN-0002*1*5*5~SVC*HC:99212*5*5~SE*12*0001~")
    )
    reading, others = parse_835(era)
    assert others == 1
    assert reading.claim_id == "PCN-0001"  # CLP07 absent: the provider's claim number
    assert [a.model_dump() for a in reading.adjustments] == [
        {"group_code": "OA", "carc": "23", "amount": "10"},
        {"group_code": "OA", "carc": "45", "amount": "5"},
    ]
    assert reading.rarc_codes == ["MA130", "N1"]
    first, second = reading.lines
    assert (first.procedure_code, first.service_date, first.rarc_codes) == (
        "99214",
        "2026-08-02",
        [],
    )
    assert [a.carc for a in first.adjustments] == ["1", "2"]
    assert (second.procedure_code, second.service_date, second.paid_amount) == (
        "J1100",
        "2026-08",
        None,
    )
    extraction = build_extraction([SourceReading(doc_id="s", readings=[reading], other_claims=1)])
    assert extraction.other_claims == 1
    assert "lines.1.service_date" in extraction.needs_confirmation()
    with pytest.raises(ValueError, match="not an 835"):
        parse_835("ST*835~")


# --- Values validate one at a time ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "raw", "value"),
    [
        ("billed_amount", "$1,250.50", "1250.50"),
        ("billed_amount", 12.5, "12.5"),
        ("paid_amount", True, None),
        ("amount", "1.005", None),
        ("group_code", " pr ", "PR"),
        ("carc", "b7", "B7"),
        ("carc", "1234", None),
        ("rarc_codes", "ma130", "MA130"),
        ("procedure_code", "0001f", "0001F"),
        ("procedure_code", "9921", None),
        ("service_date", "2026-02-30", None),
        ("claim_id", "  ", None),
        ("payer_name", ["list"], None),
    ],
)
def test_us_5_2_values_validate_one_by_one(name: str, raw: object, value: str | None) -> None:
    read = read_value(name, raw)
    assert read["value"] == value
    expected = FieldStatus.UNREADABLE if value is None else FieldStatus.EXTRACTED
    assert read["status"] == expected.value


def test_us_5_2_extracted_value_matches_status() -> None:
    with pytest.raises(ValidationError):
        Extracted[str](value="x", status=FieldStatus.UNREADABLE)
    with pytest.raises(ValidationError):
        Extracted[str](status=FieldStatus.CONFIRMED)
    extraction = build_extraction([])
    with pytest.raises(KeyError):
        extraction.confirm("lines.0.carc", "197")
    assert build_extraction([]).keep_confirmed(extraction) == extraction


def test_us_5_2_scalars_come_from_the_first_source_that_reads_them() -> None:
    first = SourceReading(doc_id="a", readings=[Reading(payer_name=None, claim_id="A-1")])
    second = SourceReading(doc_id="b", readings=[Reading(payer_name="Payer B", claim_id="B-2")])
    extraction = build_extraction([first, second])
    assert (extraction.payer_name.value, extraction.claim_id.value) == ("Payer B", "A-1")
    assert extraction.lines == []


# --- The extraction prompt and the model call ----------------------------------------------------


@pytest.mark.parametrize(
    ("content", "claim_id"),
    [
        ('{"claim_id": "A-1"}', "A-1"),
        ('<think>{"claim_id": "no"}</think>\n```json\n{"claim_id": "B-2"}\n```', "B-2"),
    ],
)
def test_us_5_2_reply_is_parsed_as_data(content: str, claim_id: str) -> None:
    reading = parse_reply(content)
    assert reading is not None
    assert reading.claim_id == claim_id


@pytest.mark.parametrize(
    "content", ["no json here", "} {", '{"claim_id": }', '{"claim_id": "A"} then {"claim_id": "B"}']
)
def test_us_5_2_unusable_replies_are_ignored(content: str) -> None:
    assert parse_reply(content) is None


async def test_us_5_2_vision_requests_name_the_served_model(vision: FakeModelServer) -> None:
    vision.replies["/models/Qwen3-VL"] = '{"ok": true}'

    prompt = build_prompt(
        PromptParts(template=EXTRACTION_TEMPLATE, data=(DataItem(label="page", text="page 1"),))
    )
    served = ModelEndpoint(ModelRole.EXTRACTION, vision.base_url, "/models/Qwen3-VL")
    await chat_completion(served, prompt, max_tokens=8)
    phi = ModelEndpoint(ModelRole.PHI_DETECTION, vision.base_url, "/models/Qwen3-8B")
    await chat_completion(phi, prompt, max_tokens=8)
    assert [r.model for r in vision.requests] == ["/models/Qwen3-VL", DEFAULT_MODEL_ID]
    assert all(isinstance(r.messages[1].content, str) for r in vision.requests)


def test_us_5_2_documents_split_into_model_calls() -> None:

    def doc(kind: str) -> SourceDocument:
        return SourceDocument(
            doc_id="src_0123456789abcdef",
            kind=kind,  # type: ignore[arg-type]
            content_type="x/y",
            size_bytes=1,
            added_at=utc_now(),
        )

    pages = units_of(doc("pdf"), synthetic_eob_pdf(pages=3))
    assert [u.label for u in pages] == ["page 1 of 3", "page 2 of 3", "page 3 of 3"]
    assert all(u.image and u.text for u in pages)
    capped = rasterize_pdf(synthetic_eob_pdf(pages=3), max_pages=2)
    assert len(capped) == 2
    (image,) = units_of(doc("image"), PNG_IMAGE)
    assert image.image is not None
    assert image.image.startswith(b"\x89PNG")
    text = units_of(doc("text"), ("x" * (TEXT_CHUNK + 1)).encode())
    assert [u.label for u in text] == ["part 1 of 2", "part 2 of 2"]
    assert text[1].text == "x"


async def test_us_5_2_undecodable_documents_are_skipped(
    service: CorpusService, vision: FakeModelServer, caplog: pytest.LogCaptureFixture
) -> None:
    cases = CaseService(service)
    case_id = cases.create("default").case_id

    cases.add_file("default", case_id, parse_upload(*hermes_multipart(data=b"%PDF-1.7 broken")))
    cases.add_file("default", case_id, parse_upload(*hermes_multipart("s.png", "image/png", PNG)))
    stages: list[tuple[str, float]] = []
    extraction = await Extractor(cases, static_models(vision.base_url)).run(
        "default", case_id, lambda stage, progress: stages.append((stage, progress))
    )
    assert vision.requests == [], "neither file decoded, so the model was never loaded"
    assert extraction.needs_confirmation() == [
        "payer_name",
        "claim_id",
        "billed_amount",
        "paid_amount",
        "denial_date",  # US-6.3
    ]
    assert stages[-1] == ("done", 1.0)
    assert extraction.unread_sources == extraction.sources, "the pane can say what was not read"
    assert "could not be decoded" in caplog.text


async def test_us_5_2_an_image_page_is_read_without_a_text_layer(
    service: CorpusService, vision: FakeModelServer
) -> None:
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    cases.add_file(
        "default", case_id, parse_upload(*hermes_multipart("s.png", "image/png", PNG_IMAGE))
    )
    extraction = await Extractor(cases, static_models(vision.base_url)).run(
        "default", case_id, lambda _stage, _progress: None
    )
    assert extraction.claim_id.value == "CLAIM-77"
    (request,) = vision.requests
    content = request.messages[1].content
    assert isinstance(content, list)
    text, image = content
    assert "label=page_text" not in text["text"]
    assert image["type"] == "image_url"


def test_us_5_2_store_guards_closed_cases_and_dataless_items(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    item = CaseItem(
        case_id=case_id,
        item_id="src_0123456789abcdef",
        kind="source",
        created_at=utc_now(),
        payload=SourceDocument(
            doc_id="src_0123456789abcdef",
            kind="pdf",
            content_type="application/pdf",
            size_bytes=1,
            added_at=utc_now(),
        )
        .model_dump_json()
        .encode(),
    )
    store.put_case_item(item, audit=AuditAction.DOCUMENT_ADDED)  # a source without bytes
    assert cases.sources("default", case_id) == []
    store.close_case(case_id)
    with pytest.raises(CaseClosedError):  # the store's own guard, inside its transaction
        store.put_case_item(item, b"x", audit=AuditAction.DOCUMENT_ADDED)


# --- Review regressions ---------------------------------------------------------------------------


async def test_us_5_2_null_lists_and_bad_items_keep_the_rest(
    desktop: httpx.AsyncClient, vision: FakeModelServer
) -> None:
    """A reply with ``null`` lists, a malformed line, and odd values loses only those values."""
    line = {
        "procedure_code": "99213",
        "service_date": "2026-09-01",
        "billed_amount": "250.00",
        "paid_amount": True,
        "adjustments": None,
        "rarc_codes": ["N286", {"code": "M15"}],
    }
    reply = eob_reply(adjustments=None, rarc_codes=None, lines=["junk", line, 7])
    vision.replies[DEFAULT_MODEL_ID] = reply.replace(
        '"billed_amount": "250.00"', '"billed_amount": {"v": 1}', 1
    )
    case_id = await case_with(desktop, eob_upload())
    await process(desktop, case_id)
    case = await open_case(desktop, case_id)
    assert case.extraction is not None
    assert case.extraction.payer_name.value == "ACME HEALTH PLAN"
    (kept,) = case.extraction.lines
    assert kept.procedure_code.value == "99213"
    assert kept.adjustments == []
    assert case.needs_confirmation == [
        "billed_amount",
        "lines.0.paid_amount",  # JSON true is not an amount
        "lines.0.rarc_codes.1",
    ]


async def test_us_5_2_line_confirmations_stay_with_their_source(
    desktop: httpx.AsyncClient, vision: FakeModelServer
) -> None:
    """A re-run that takes its lines from another source drops line-level confirmations."""
    two_lines = [
        {"procedure_code": "99213", "service_date": "2026-09-01", "billed_amount": "100.00"},
        {"procedure_code": "99214", "service_date": "2026-09-01", "billed_amount": "150.00"},
    ]
    vision.replies[DEFAULT_MODEL_ID] = eob_reply(claim_id=None, lines=two_lines)
    case_id = await case_with(desktop, eob_upload())
    await process(desktop, case_id)
    fields = f"{PREFIX}/cases/{case_id}/fields"
    await desktop.post(fields, json={"path": "lines.1.billed_amount", "value": "175.00"})
    await desktop.post(fields, json={"path": "claim_id", "value": "CLAIM-77"})

    await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": ERA_835})
    await process(desktop, case_id)
    extraction = (await open_case(desktop, case_id)).extraction
    assert extraction is not None
    assert extraction.itemized_by != extraction.sources[1]  # the 835 now gives the lines
    assert len(extraction.lines) == 1
    assert extraction.lines[0].billed_amount.status is FieldStatus.EXTRACTED
    assert extraction.claim_id.status is FieldStatus.CONFIRMED  # claim-level values are kept


async def test_us_5_2_jobs_stop_at_their_deadline(service: CorpusService) -> None:
    @asynccontextmanager
    async def hang(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        await asyncio.Event().wait()
        yield ModelEndpoint(role=role, base_url="http://127.0.0.1:9/v1")

    cases = CaseService(service)
    case_id = cases.create("default").case_id
    cases.add_file("default", case_id, parse_upload(*eob_upload()))
    jobs = JobRegistry(Extractor(cases, hang), deadline=0.05)
    started = jobs.start("default", case_id)
    events = await finish(jobs, started.job_id)
    assert (events[-1].stage, events[-1].error_code) == ("failed", "processing_timeout")


async def test_us_5_2_one_relay_per_job() -> None:
    gate = asyncio.Event()

    async def handler(_request: httpx.Request) -> httpx.Response:
        await gate.wait()
        body = {"ok": True, "job_id": started_job().job_id, "events": [], "finished": True}
        return httpx.Response(200, json=body)

    client = WorkerClient("http://worker", lambda: "t", transport=httpx.MockTransport(handler))
    first = relay.start_relay(client, started_job(), lambda *_: None)
    assert relay.start_relay(client, started_job(), lambda *_: None) is first
    gate.set()
    assert await first == 0
    await asyncio.sleep(0)
    assert started_job().job_id not in relay._RELAYS


def test_us_5_2_save_and_confirm_hold_the_case_lock(
    service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    lock = cases._case_lock("default", case_id)
    assert cases._case_lock("default", case_id) is lock
    held: list[bool] = []
    real = CaseService.extraction

    def watched(store: Any, case: str) -> CaseExtraction | None:
        held.append(lock.locked())
        return real(store, case)

    monkeypatch.setattr(CaseService, "extraction", staticmethod(watched))
    cases.save_extraction("default", case_id, build_extraction([]))
    cases.confirm_field("default", case_id, FieldConfirmation(path="payer_name", value="ACME"))
    assert held == [True, True]


async def test_us_5_2_confirming_on_a_closed_case_says_closed(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await case_with(desktop, eob_upload())
    await process(desktop, case_id)
    service.user_store("default").close_case(case_id)
    response = await desktop.post(
        f"{PREFIX}/cases/{case_id}/fields", json={"path": "claim_id", "value": "CLAIM-77"}
    )
    assert_envelope(response, 409, "case_closed")


def test_us_5_2_cmyk_and_oversized_images_are_normalized() -> None:
    cmyk = pymupdf.Pixmap(pymupdf.csCMYK, pymupdf.IRect(0, 0, 8, 8))  # type: ignore[no-untyped-call]
    cmyk.clear_with(0)  # type: ignore[no-untyped-call]
    jpeg = bytes(cmyk.tobytes("jpg"))  # type: ignore[no-untyped-call]
    rgb = pymupdf.Pixmap(to_png(jpeg))  # type: ignore[no-untyped-call]
    assert rgb.colorspace.n == 3
    wide = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 5000, 10))  # type: ignore[no-untyped-call]
    wide.clear_with(255)  # type: ignore[no-untyped-call]
    small = pymupdf.Pixmap(to_png(bytes(wide.tobytes("png"))))  # type: ignore[no-untyped-call]
    assert max(small.width, small.height) <= MAX_SIDE
    assert _dpi(612, 792) == 150
    assert _dpi(14400, 14400) * 200 <= MAX_SIDE  # a 200-inch page renders under the cap
    assert _dpi(0, 0) == 150


def test_us_5_2_gateway_never_loads_pymupdf() -> None:
    script = (
        "import sys; sys.path[:0] = ['plugin']\n"
        "import claimcoach.api.routes, claimcoach.api.relay\n"
        "print('pymupdf' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True, timeout=60
    )
    assert result.stdout.strip() == "False"
