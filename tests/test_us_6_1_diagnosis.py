"""US-6.1 Denial Classification and Appeal Likelihood (Python half).

Scenarios: classification returns a typed result; appeal likelihood includes reasons. Also: the
closed label set, the reply parser, the prompt's data minimization, exact code notes, the
``case_items`` migration, diagnosis jobs and their events, staleness, and the purge. The pane
scenario runs under ``node --test`` (``plugin/desktop/tests/case_diagnosis.test.mjs``).
Rules: ES-1, ES-4, BR-1, BR-5, BR-7, BR-10, BR-14, PC-4.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach import PLUGIN_NAME
from claimcoach.api import relay, routes
from claimcoach.api.client import WorkerClient, WorkerRejectedError
from claimcoach.api.models import ERROR_MESSAGES, ErrorEnvelope
from claimcoach.cases.diagnosis import REASON_GUIDE
from claimcoach.cases.errors import DiagnosisFailedError, NotExtractedError
from claimcoach.cases.extraction import CaseExtraction, JobStarted
from claimcoach.cases.models import Case
from claimcoach.cases.service import CaseService
from claimcoach.corpus.crypto import InMemoryKeyProvider
from claimcoach.corpus.errors import CaseClosedError, CaseNotFoundError, CorpusError
from claimcoach.corpus.lookup import code_entries
from claimcoach.corpus.paths import DATABASE, profile_user_scope_dir
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, CaseItem, PurgeRequest, utc_now
from claimcoach.events import CaseProgressEvent
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.manager import ModelEndpoint, ModelUnavailableError
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.diagnose import (
    CLASSIFICATION_TEMPLATE,
    AppealLikelihood,
    DenialReason,
    Diagnoser,
    Diagnosis,
    case_codes,
    case_facts,
    classify,
    code_keys,
    parse_classification,
)
from claimcoach.pipeline.extract import Extractor
from claimcoach.pipeline.jobs import JobRegistry
from claimcoach.prompts.builder import registered_templates
from claimcoach.worker import case_routes
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.diagnosis import (
    CLASSIFICATION,
    CODE_BUNDLE,
    classification_reply,
    explanation_reply,
    role_models,
)
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_5_1_case_intake import ERA_835

PREFIX: Final = "/api/plugins/claimcoach"

Sent = list[tuple[str, str, dict[str, Any]]]


@pytest.fixture(scope="module")
def classifier() -> Iterator[FakeModelServer]:
    """A fake Qwen3-8B (the ``classification`` role)."""
    with FakeModelServer() as server:
        yield server


@pytest.fixture(scope="module")
def explainer() -> Iterator[FakeModelServer]:
    """A fake Qwen3-14B (the ``explanation`` role, US-6.2)."""
    with FakeModelServer() as server:
        yield server


@pytest.fixture(autouse=True)
def _reset_models(classifier: FakeModelServer, explainer: FakeModelServer) -> None:
    for server in (classifier, explainer):
        server.requests.clear()
    classifier.replies[DEFAULT_MODEL_ID] = classification_reply()
    explainer.replies[DEFAULT_MODEL_ID] = explanation_reply()


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def models(classifier: FakeModelServer, explainer: FakeModelServer) -> Any:
    return role_models(
        {ModelRole.CLASSIFICATION: classifier.base_url, ModelRole.EXPLANATION: explainer.base_url}
    )


@pytest.fixture
def worker(service: CorpusService, models: Any) -> FastAPI:
    return create_app(TOKEN, corpus=service, pipeline_models=models)


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


async def new_case(desktop: httpx.AsyncClient, text: str = ERA_835) -> str:
    """A case holding pasted 835 text (extracted without a model)."""
    response = await desktop.post(f"{PREFIX}/cases", json={})
    case_id = Case.model_validate_json(response.content).case_id
    pasted = await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": text})
    assert pasted.status_code == 200, pasted.text
    return case_id


async def run_job(desktop: httpx.AsyncClient, case_id: str, action: str) -> JobStarted:
    """Press Process case or Diagnose case and wait until the relay sent the last event."""
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/{action}", json={})
    assert response.status_code == 200, response.text
    await asyncio.gather(*relay._RELAYS.values())
    return JobStarted.model_validate_json(response.content)


async def extracted_case(desktop: httpx.AsyncClient) -> str:
    case_id = await new_case(desktop)
    await run_job(desktop, case_id, "process")
    return case_id


async def open_case(desktop: httpx.AsyncClient, case_id: str) -> Case:
    response = await desktop.get(f"{PREFIX}/cases/{case_id}")
    assert response.status_code == 200, response.text
    return Case.model_validate_json(response.content)


def events_of(sent: Sent, job_id: str) -> list[CaseProgressEvent]:
    events = [CaseProgressEvent.model_validate(payload) for _, _, payload in sent]
    return [event for event in events if event.job_id == job_id]


# --- Scenario: Classification returns a typed result ---------------------------------------------


async def test_us_6_1_classification_typed_result(
    desktop: httpx.AsyncClient, service: CorpusService, sent: Sent
) -> None:
    case_id = await extracted_case(desktop)
    started = await run_job(desktop, case_id, "diagnose")
    assert started.kind == "diagnose"

    case = await open_case(desktop, case_id)
    diagnosis = case.diagnosis
    assert diagnosis is not None
    assert diagnosis.denial_reason is DenialReason.PRIOR_AUTHORIZATION
    assert diagnosis.appeal_likelihood in {"low", "medium", "high"}
    assert diagnosis.appeal_likelihood is AppealLikelihood.HIGH
    assert diagnosis.codes == ["CO-197", "N286"]
    assert case.extraction is not None
    assert diagnosis.extraction_digest == case.extraction.digest()
    assert case.diagnosis_stale is False
    # The stored diagnosis round-trips through the typed model (ES-1).
    assert Diagnosis.model_validate_json(diagnosis.model_dump_json()) == diagnosis
    actions = [entry.action for entry in service.user_store("default").audit_log(case_id)]
    # One entry per stored write: the classification, then the explanation (US-6.2).
    assert actions.count(AuditAction.CASE_DIAGNOSED) == 2
    assert events_of(sent, started.job_id)[-1].stage == "done"


# --- Scenario: Appeal likelihood includes reasons ------------------------------------------------


async def test_us_6_1_likelihood_includes_reasons(desktop: httpx.AsyncClient) -> None:
    case_id = await extracted_case(desktop)
    await run_job(desktop, case_id, "diagnose")

    case = await open_case(desktop, case_id)
    assert case.diagnosis is not None
    assert len(case.diagnosis.likelihood_reasons) >= 1
    assert case.diagnosis.likelihood_reasons == CLASSIFICATION["reasons"]


# --- Scenario: A reply outside the closed set ----------------------------------------------------


async def test_us_6_1_reply_outside_closed_set_fails(
    desktop: httpx.AsyncClient, classifier: FakeModelServer, sent: Sent
) -> None:
    case_id = await extracted_case(desktop)
    await run_job(desktop, case_id, "diagnose")
    first = (await open_case(desktop, case_id)).diagnosis

    classifier.replies[DEFAULT_MODEL_ID] = classification_reply(denial_reason="fraud")
    started = await run_job(desktop, case_id, "diagnose")
    last = events_of(sent, started.job_id)[-1]
    assert (last.stage, last.error_code) == ("failed", "diagnosis_failed")
    assert (await open_case(desktop, case_id)).diagnosis == first, "the last diagnosis stays"


async def test_us_6_1_no_diagnosis_is_stored_for_a_bad_reply(
    service: CorpusService, classifier: FakeModelServer, models: Any
) -> None:
    classifier.replies[DEFAULT_MODEL_ID] = "I think it is prior authorization."
    cases = CaseService(service)
    case_id = await extracted_by_service(cases)
    with pytest.raises(DiagnosisFailedError):
        await Diagnoser(cases, models).run("default", case_id, lambda _stage, _progress: None)
    assert cases.diagnosis(cases.store("default"), case_id) is None


@pytest.mark.parametrize(
    "content",
    [
        "no json at all",
        '{"denial_reason": "prior_authorization", "appeal_likelihood": "high"}',
        classification_reply(reasons=[]),
        classification_reply(reasons=["  ", ""]),
        classification_reply(reasons="Because."),
        classification_reply(reasons=["Fine.", 7]),
        classification_reply(appeal_likelihood="certain"),
        classification_reply(denial_reason=None),
        '{"denial_reason": }',
    ],
)
def test_us_6_1_unusable_replies_are_refused(content: str) -> None:
    assert parse_classification(content) is None


def test_us_6_1_replies_are_read_leniently_where_safe() -> None:
    reply = parse_classification(
        "<think>CO-197 means no authorization.</think>```json\n"
        + classification_reply(
            denial_reason="Prior Authorization",
            appeal_likelihood=" Medium ",
            reasons=["One.", " ", "Two.", "Three.", "Four.", "Five.", "Six."],
            extra="ignored",
        )
        + "\n```"
    )
    assert reply is not None
    assert reply.denial_reason is DenialReason.PRIOR_AUTHORIZATION
    assert reply.appeal_likelihood is AppealLikelihood.MEDIUM
    assert reply.reasons == ["One.", "Two.", "Three.", "Four.", "Five."]
    long = parse_classification(classification_reply(reasons=["word " * 100]))
    assert long is not None, "a long reason is clipped, not refused (a retry would repeat it)"
    assert len(long.reasons[0]) == 300
    assert long.reasons[0].endswith("…")
    coordination = parse_classification(
        classification_reply(denial_reason="coordination-of-benefits")
    )
    assert coordination is not None
    assert coordination.denial_reason is DenialReason.COORDINATION_OF_BENEFITS


def test_us_6_1_label_set_is_closed_and_guided() -> None:
    assert {reason.value for reason in DenialReason} == {
        "eligibility",
        "prior_authorization",
        "medical_necessity",
        "coding_error",
        "missing_information",
        "duplicate_claim",
        "timely_filing",
        "non_covered_service",
        "bundling",
        "coordination_of_benefits",
        "other",
    }
    assert set(REASON_GUIDE) == set(DenialReason), "every label is explained to the model"
    for reason in DenialReason:
        assert reason.value in CLASSIFICATION_TEMPLATE.instructions


def test_us_6_1_diagnosis_model_is_strict() -> None:
    good = {
        "denial_reason": "bundling",
        "appeal_likelihood": "low",
        "likelihood_reasons": ["Bundled into the visit."],
        "codes": ["CO-97", "197", "N286"],
        "extraction_digest": "0" * 64,
        "diagnosed_at": utc_now().isoformat(),
    }
    assert Diagnosis.model_validate(good).codes == ["CO-97", "197", "N286"]
    changes: list[dict[str, object]] = [
        {"likelihood_reasons": []},
        {"likelihood_reasons": ["a"] * 6},
        {"appeal_likelihood": "certain"},
        {"denial_reason": "fraud"},
        {"codes": ["co 97; drop"]},
        {"extraction_digest": "xyz"},
        {"diagnosed_at": "2026-10-31T10:00:00"},
        {"surprise": True},
    ]
    for change in changes:
        with pytest.raises(ValidationError):
            Diagnosis.model_validate(good | change)


# --- The prompt (BR-5, BR-10, data minimization) -------------------------------------------------


async def test_us_6_1_prompt_carries_only_facts(
    desktop: httpx.AsyncClient, service: CorpusService, classifier: FakeModelServer
) -> None:
    await service.import_bundle(CODE_BUNDLE)
    case_id = await extracted_case(desktop)
    await run_job(desktop, case_id, "diagnose")

    assert CLASSIFICATION_TEMPLATE in registered_templates()
    (request,) = classifier.requests
    assert request.model == DEFAULT_MODEL_ID
    system, user = request.messages
    assert isinstance(system.content, str)
    assert isinstance(user.content, str)
    assert system.content.startswith(CLASSIFICATION_TEMPLATE.system)
    assert user.content.startswith(CLASSIFICATION_TEMPLATE.instructions)
    data = user.content[len(CLASSIFICATION_TEMPLATE.instructions) :]
    assert "label=case_facts>>>" in data
    assert "label=code_notes>>>" in data
    for fact in ("ACME HEALTH PLAN", "99213", '"carc": "197"', '"group_code": "CO"', "N286"):
        assert fact in data
    for withheld in ("CLAIM-77", "PCN-0001", "2026-09-01", "PATIENT", "SYNTHETIC CLINIC"):
        assert withheld not in data, "the claim number, dates, and names stay out"
    assert "CARC/197: Precertification absent" in data
    assert "RARC/N286" in data
    assert "GROUP/CO" in data
    assert "Duplicate claim" not in data, "only the case's own codes are looked up"
    extra = request.model_extra or {}
    assert (extra["temperature"], extra["max_tokens"]) == (0.0, 1024)


async def test_us_6_1_prompt_says_when_no_code_notes_exist(
    desktop: httpx.AsyncClient, classifier: FakeModelServer
) -> None:
    case_id = await extracted_case(desktop)
    await run_job(desktop, case_id, "diagnose")
    (request,) = classifier.requests
    assert "No code notes are on file for these codes." in str(request.messages[1].content)


def test_us_6_1_facts_and_codes_of_an_extraction() -> None:
    unreadable = {"value": None, "status": "unreadable"}

    def read(value: str) -> dict[str, str]:
        return {"value": value, "status": "extracted"}

    extraction = CaseExtraction.model_validate(
        {
            "payer_name": unreadable,
            "claim_id": read("CLAIM-9"),
            "billed_amount": read("100.00"),
            "paid_amount": unreadable,
            "adjustments": [
                {"group_code": unreadable, "carc": read("45"), "amount": read("10.00")},
                {"group_code": read("PR"), "carc": unreadable, "amount": read("5.00")},
            ],
            "rarc_codes": [read("M15"), unreadable],
            "lines": [
                {
                    "procedure_code": read("97110"),
                    "service_date": read("2026-08-01"),
                    "billed_amount": read("100.00"),
                    "paid_amount": read("0.00"),
                    "adjustments": [
                        {"group_code": read("CO"), "carc": read("45"), "amount": read("90.00")}
                    ],
                    "rarc_codes": [read("M15")],
                }
            ],
        }
    )
    facts = case_facts(extraction)
    assert facts["payer"] is None
    assert facts["claim_adjustments"][1] == {"group_code": "PR", "carc": None, "amount": "5.00"}
    assert facts["claim_remark_codes"] == ["M15", None]
    assert "CLAIM-9" not in json.dumps(facts)
    assert "2026-08-01" not in json.dumps(facts)
    assert case_codes(extraction) == ["45", "M15", "CO-45"]
    assert code_keys(extraction) == ["CARC/45", "GROUP/PR", "RARC/M15", "GROUP/CO"]


# --- Code notes are looked up exactly (BR-5) -----------------------------------------------------


async def test_us_6_1_code_notes_are_exact(service: CorpusService) -> None:
    await service.import_bundle(CODE_BUNDLE)
    store = service.global_store()
    notes = code_entries(store, ["RARC/N286", "CARC/999", "CARC/197", "RARC/N286"])
    assert [note.doc_id for note in notes] == ["code:RARC/N286", "code:CARC/197"]
    assert {document.kind for document in store.documents(kind="code")} == {"code"}
    assert store.documents(kind="rule_card") == []
    assert len(store.documents()) == len(CODE_BUNDLE.items)
    CaseService(service).create("default")
    with pytest.raises(CorpusError):
        code_entries(service.user_store("default"), ["CARC/197"])


# --- Diagnosis runs as a job after extraction ----------------------------------------------------


async def test_us_6_1_diagnosis_requires_extraction(
    desktop: httpx.AsyncClient, service: CorpusService, worker: FastAPI
) -> None:
    case_id = await new_case(desktop)
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/diagnose", json={})
    assert_envelope(response, 409, "not_extracted")
    assert relay._RELAYS == {}, "nothing relayed"
    assert worker.state.jobs.running("default", case_id) is None, "no job started"

    missing = await desktop.post(f"{PREFIX}/cases/case_0000000000000000/diagnose", json={})
    assert_envelope(missing, 404, "case_not_found")
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/bad!id/diagnose", json={}), 422, "invalid_request"
    )
    no_json = await desktop.post(f"{PREFIX}/cases/{case_id}/diagnose", content=b"x")
    assert_envelope(no_json, 422, "invalid_request")

    await run_job(desktop, case_id, "process")
    service.user_store("default").close_case(case_id)
    closed = await desktop.post(f"{PREFIX}/cases/{case_id}/diagnose", json={})
    assert_envelope(closed, 409, "case_closed")


async def test_us_6_1_case_ids_events_cannot_carry_are_unknown(service: CorpusService) -> None:
    cases = CaseService(service)
    service.user_store("default", create=True).create_case("legacy-case")
    with pytest.raises(CaseNotFoundError):
        cases.check_diagnosable("default", "legacy-case")


async def test_us_6_1_progress_relayed(desktop: httpx.AsyncClient, sent: Sent) -> None:
    case_id = await extracted_case(desktop)
    started = await run_job(desktop, case_id, "diagnose")
    events = events_of(sent, started.job_id)
    assert {(plugin, event) for plugin, event, _ in sent} == {(PLUGIN_NAME, "case.progress")}
    # US-6.2 adds ``explaining`` between the two (test_us_6_2_progress_relayed).
    assert (events[0].stage, events[0].progress) == ("classifying", 0.0)
    assert (events[-1].stage, events[-1].progress) == ("done", 1.0)
    assert {e.case_id for e in events} == {case_id}
    # PHI-free by construction (US-3.4): no case content and no model text in any payload.
    wire = json.dumps([payload for _, _, payload in sent])
    for text in ("ACME", "CLAIM-77", "prior_authorization", "authorization"):
        assert text not in wire


async def test_us_6_1_one_job_per_case(service: CorpusService, models: Any) -> None:
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    cases.add_text("default", case_id, ERA_835)
    gate = asyncio.Event()

    class SlowExtractor(Extractor):
        async def run(self, profile: str, case_id: str, report: Any) -> CaseExtraction:
            await gate.wait()
            return await super().run(profile, case_id, report)

    jobs = JobRegistry(SlowExtractor(cases, models), diagnoser=Diagnoser(cases, models))
    extracting = jobs.start("default", case_id)
    joined = jobs.start("default", case_id, "diagnose")
    assert joined == extracting, "a diagnosis asked for mid-extraction joins the running job"
    assert joined.kind == "extract"
    gate.set()
    await finish(jobs, extracting.job_id)
    diagnosing = jobs.start("default", case_id, "diagnose")
    assert (diagnosing.kind, diagnosing.job_id != extracting.job_id) == ("diagnose", True)
    events = await finish(jobs, diagnosing.job_id)
    assert events[-1].stage == "done"
    assert cases.diagnosis(cases.store("default"), case_id) is not None

    without = JobRegistry(Extractor(cases, models))
    with pytest.raises(ModelUnavailableError):
        without.start("default", case_id, "diagnose")


async def finish(jobs: JobRegistry, job_id: str) -> list[CaseProgressEvent]:
    events: list[CaseProgressEvent] = []
    while True:
        batch = await jobs.events(job_id, len(events), wait=5)
        events += batch.events
        if batch.finished:
            return events


class Failing:
    """A model provider whose ``use`` raises ``error``."""

    def __init__(self, error: Exception | None) -> None:
        self.error = error

    @asynccontextmanager
    async def __call__(self, role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        if self.error is not None:
            raise self.error
        yield ModelEndpoint(role=role, base_url="http://127.0.0.1:9/v1")


async def extracted_by_service(cases: CaseService) -> str:
    case_id = cases.create("default").case_id
    cases.add_text("default", case_id, ERA_835)
    await Extractor(cases, role_models({})).run("default", case_id, lambda _s, _p: None)
    return case_id


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ModelUnavailableError(), "model_unavailable"),
        (CaseClosedError(), "case_closed"),
        (NotExtractedError(), "not_extracted"),
        (RuntimeError("Jane Doe"), "diagnosis_failed"),
    ],
)
async def test_us_6_1_a_failed_diagnosis_ends_with_its_code(
    service: CorpusService, error: Exception, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    cases = CaseService(service)
    case_id = await extracted_by_service(cases)
    jobs = JobRegistry(Extractor(cases, Failing(error)), diagnoser=Diagnoser(cases, Failing(error)))
    started = jobs.start("default", case_id, "diagnose")
    events = await finish(jobs, started.job_id)
    assert (events[-1].stage, events[-1].error_code) == ("failed", code)
    assert "Jane Doe" not in caplog.text  # BR-14: the error type only
    assert "diagnose job failed" in caplog.text


async def test_us_6_1_a_job_that_finds_no_extraction_says_so(
    service: CorpusService, models: Any
) -> None:
    """The route checks first, but a job reads the case again: it never diagnoses nothing."""
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    with pytest.raises(NotExtractedError):
        await Diagnoser(cases, models).run("default", case_id, lambda _stage, _progress: None)


async def test_us_6_1_a_worker_without_models_cannot_diagnose(service: CorpusService) -> None:
    app = create_app(TOKEN, corpus=service)
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(app))
    case = await client.create_case("default")
    with pytest.raises(WorkerRejectedError) as raised:
        await client.start_diagnosis("default", case.case_id)
    assert raised.value.code == "model_unavailable"


# --- Scenario: A confirmed field makes the diagnosis stale ---------------------------------------


async def test_us_6_1_confirmed_field_makes_diagnosis_stale(desktop: httpx.AsyncClient) -> None:
    case_id = await extracted_case(desktop)
    await run_job(desktop, case_id, "diagnose")
    assert (await open_case(desktop, case_id)).diagnosis_stale is False

    confirmed = await desktop.post(
        f"{PREFIX}/cases/{case_id}/fields", json={"path": "claim_id", "value": "CLAIM-78"}
    )
    assert confirmed.status_code == 200, confirmed.text
    answer = Case.model_validate_json(confirmed.content)
    assert answer.diagnosis is not None, "the answer to a confirmation keeps the diagnosis"
    assert answer.diagnosis_stale is True
    assert (await open_case(desktop, case_id)).diagnosis_stale is True

    await run_job(desktop, case_id, "diagnose")
    assert (await open_case(desktop, case_id)).diagnosis_stale is False


async def test_us_6_1_a_case_without_diagnosis(desktop: httpx.AsyncClient) -> None:
    case = await open_case(desktop, await extracted_case(desktop))
    assert (case.diagnosis, case.diagnosis_stale) == (None, False)


async def test_us_6_1_diagnose_during_first_extraction_joins_it(
    service: CorpusService, models: Any
) -> None:
    """Review regression: the running extraction is returned, not ``not_extracted``."""
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    cases.add_text("default", case_id, ERA_835)
    gate = asyncio.Event()

    class SlowExtractor(Extractor):
        async def run(self, profile: str, case_id: str, report: Any) -> CaseExtraction:
            await gate.wait()
            return await super().run(profile, case_id, report)

    app = create_app(TOKEN, corpus=service)
    app.state.jobs = JobRegistry(SlowExtractor(cases, models), diagnoser=Diagnoser(cases, models))
    app.include_router(case_routes.jobs_router)
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(app))
    extracting = await client.start_extraction("default", case_id)
    joined = await client.start_diagnosis("default", case_id)
    assert (joined.job_id, joined.kind) == (extracting.job_id, "extract")
    again = await client.start_extraction("default", case_id)
    assert again == extracting, "a second Process joins too"
    gate.set()
    await finish(app.state.jobs, extracting.job_id)


# --- Storage: the case_items migration and the purge (BR-7) --------------------------------------


async def test_us_6_1_case_items_check_migrates(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    root = tmp_path / "hermes"
    keys = InMemoryKeyProvider()
    corpus = make_service(root, corpus_server, keys=keys)
    cases = CaseService(corpus)
    case_id = cases.create("default").case_id
    added = cases.add_text("default", case_id, ERA_835)
    corpus.close()

    # Rewrite the table as US-5.2 created it: its CHECK knows only two kinds.
    database = profile_user_scope_dir("default", root, create=False) / DATABASE
    with sqlite3.connect(database) as db:
        db.executescript(
            """
            CREATE TABLE case_items_old (
                case_id TEXT NOT NULL REFERENCES cases(case_id), item_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('source', 'extraction')),
                created_at TEXT NOT NULL, payload BLOB NOT NULL, data BLOB,
                PRIMARY KEY (case_id, item_id)
            ) STRICT;
            INSERT INTO case_items_old SELECT * FROM case_items;
            DROP TABLE case_items;
            ALTER TABLE case_items_old RENAME TO case_items;
            """
        )
        (old,) = db.execute("SELECT sql FROM sqlite_master WHERE name = 'case_items'").fetchone()
    assert "'diagnosis'" not in old
    db.close()

    corpus = make_service(root, corpus_server, keys=keys)
    try:
        migrated = CaseService(corpus)
        store = migrated.store("default")
        assert [d.doc_id for d in migrated.documents(store, case_id)] == [added.document.doc_id]
        item = CaseItem(
            case_id=case_id,
            item_id="diagnosis",
            kind="diagnosis",
            created_at=utc_now(),
            payload=b"{}",
        )
        store.put_case_item(item, audit=AuditAction.CASE_DIAGNOSED)
        assert [i.item_id for i in store.case_items(case_id, "diagnosis")] == ["diagnosis"]
    finally:
        corpus.close()
    with sqlite3.connect(database) as db:
        (new,) = db.execute("SELECT sql FROM sqlite_master WHERE name = 'case_items'").fetchone()
    db.close()
    assert "'diagnosis'" in new
    assert "case_items_next" not in new


async def test_us_6_1_failed_migration_leaves_the_store_as_it_was(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    """Review regression: a rebuild that fails rolls back, and the store refuses to open."""
    root = tmp_path / "hermes"
    keys = InMemoryKeyProvider()
    corpus = make_service(root, corpus_server, keys=keys)
    CaseService(corpus).create("default")
    corpus.close()
    database = profile_user_scope_dir("default", root, create=False) / DATABASE
    with sqlite3.connect(database) as db:
        db.executescript(
            """
            CREATE TABLE case_items_old (
                case_id TEXT NOT NULL REFERENCES cases(case_id), item_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('source', 'extraction')),
                created_at TEXT NOT NULL, payload BLOB NOT NULL, data BLOB,
                PRIMARY KEY (case_id, item_id)
            ) STRICT;
            DROP TABLE case_items;
            ALTER TABLE case_items_old RENAME TO case_items;
            CREATE TABLE case_items_next (leftover INTEGER);
            """
        )
        # A row whose case does not exist (foreign keys are off in this raw connection): the copy
        # into the new table checks it, so the rebuild fails.
        db.execute(
            "INSERT INTO case_items VALUES "
            "('case_ffffffffffffffff', 'x', 'source', '', x'00', NULL)"
        )
    db.close()

    corpus = make_service(root, corpus_server, keys=keys)
    with pytest.raises(CorpusError):
        corpus.user_store("default")
    corpus.close()
    with sqlite3.connect(database) as db:
        (sql,) = db.execute("SELECT sql FROM sqlite_master WHERE name = 'case_items'").fetchone()
        rows = db.execute("SELECT case_id FROM case_items").fetchall()
        leftover = db.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'case_items_next'"
        ).fetchone()
    db.close()
    assert "'diagnosis'" not in sql, "the old table is untouched"
    assert rows == [("case_ffffffffffffffff",)]
    assert leftover is not None, "the rollback restored even the leftover table"


async def test_us_6_1_diagnosis_purged_with_case(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await extracted_case(desktop)
    await run_job(desktop, case_id, "diagnose")
    store = service.user_store("default")
    assert store.case_items(case_id, "diagnosis")
    store.close_case(case_id)
    service.purge(PurgeRequest(profile="default", case_id=case_id, confirm=True))
    assert store.case_items(case_id, "diagnosis") == []


# --- Real model ----------------------------------------------------------------------------------


@pytest.mark.models
async def test_us_6_1_classification_real_model(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    """Qwen3-8B from MODELS_HOME classifies the synthetic CO-197 case (skips without weights)."""
    from claimcoach.models.manager import ModelManager  # noqa: PLC0415
    from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry, models_home  # noqa: PLC0415

    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    home = models_home()
    spec = registry.roles[ModelRole.CLASSIFICATION]
    if spec.weights(home) == "missing" or not os.access(home, os.R_OK):
        pytest.skip(f"Qwen3-8B weights not found at {spec.model_path(home)}")
    manager = ModelManager(registry, models_home=home, state_dir=tmp_path / "models")
    corpus = make_service(tmp_path / "hermes", corpus_server)
    cases = CaseService(corpus)
    try:
        case_id = await extracted_by_service(cases)
        extraction = cases.extraction_of("default", case_id)
        async with manager.use(ModelRole.CLASSIFICATION) as endpoint:
            classification = await classify(endpoint, extraction, [])
    finally:
        await manager.shutdown()
        corpus.close()
    assert classification.denial_reason is DenialReason.PRIOR_AUTHORIZATION
    assert classification.reasons
