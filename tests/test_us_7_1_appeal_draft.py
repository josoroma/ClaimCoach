"""US-7.1 Draft the Appeal Letter (Python half).

Scenarios: draft is generated from rule card and template; draft carries the human-review label.
Also: template choice by denial reason, refusals before a job starts, unusable replies, the
drafting prompt, the draft's staleness, one job per case, and the purge. The pane scenarios run
under ``node --test`` (``plugin/desktop/tests/appeal_draft.test.mjs``).
Rules: ES-1, ES-4, BR-1, BR-4, BR-5, BR-7, BR-10, BR-12, BR-14, PC-4.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sqlite3
import stat
import zipfile
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pymupdf
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach import PLUGIN_NAME
from claimcoach.api import relay, routes
from claimcoach.api.client import WorkerClient, WorkerRejectedError
from claimcoach.cases.diagnosis import AppealLikelihood, DenialReason, Diagnosis
from claimcoach.cases.errors import (
    DraftingFailedError,
    NoLetterTemplateError,
    NotDiagnosedError,
)
from claimcoach.cases.extraction import CaseExtraction, JobStarted
from claimcoach.cases.service import CaseService
from claimcoach.corpus.bundle import CorpusBundle
from claimcoach.corpus.crypto import InMemoryKeyProvider
from claimcoach.corpus.errors import CaseClosedError, CaseNotFoundError, CorpusError
from claimcoach.corpus.lookup import letter_template
from claimcoach.corpus.paths import DATABASE, profile_user_scope_dir
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.store import split_text
from claimcoach.corpus.types import AuditAction, CorpusScope, Document, PurgeRequest, utc_now
from claimcoach.letters import draft as draft_module
from claimcoach.letters.draft import (
    DRAFT_TEMPLATE,
    Drafter,
    parse_letter,
    template_ids,
)
from claimcoach.letters.export import render_docx, render_pdf
from claimcoach.letters.types import DRAFT_LABEL, AppealDraft, DraftRequest
from claimcoach.models.chat import DEFAULT_MODEL_ID, ChatReply
from claimcoach.models.manager import ModelEndpoint, ModelUnavailableError
from claimcoach.models.registry import (
    DEFAULT_REGISTRY,
    REGISTRY_FILE,
    ModelRegistry,
    ensure_registry_file,
)
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.diagnose import Diagnoser
from claimcoach.pipeline.extract import Extractor
from claimcoach.pipeline.facts import letter_facts
from claimcoach.pipeline.jobs import JobRegistry
from claimcoach.prompts.builder import registered_templates
from claimcoach.worker import case_routes
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service, vectors_for
from tests.fakes.diagnosis import (
    ACME_DOCUMENTS,
    CLASSIFICATION,
    CODE_BUNDLE,
    RULE_BUNDLE,
    classification_reply,
    explanation_reply,
    role_models,
)
from tests.fakes.drafting import LETTER, TEMPLATE_BUNDLE, letter_reply
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_5_1_case_intake import ERA_835
from tests.test_us_6_1_diagnosis import (
    PREFIX,
    Failing,
    Sent,
    assert_envelope,
    events_of,
    finish,
    new_case,
    open_case,
    run_job,
)


@pytest.fixture(scope="module")
def classifier() -> Iterator[FakeModelServer]:
    """A fake Qwen3-8B (the ``classification`` role)."""
    with FakeModelServer() as server:
        yield server


@pytest.fixture(scope="module")
def explainer() -> Iterator[FakeModelServer]:
    """A fake Qwen3-14B (the ``explanation`` role)."""
    with FakeModelServer() as server:
        yield server


@pytest.fixture(scope="module")
def drafter_server() -> Iterator[FakeModelServer]:
    """A fake Ternary-Bonsai-2-27B (the ``drafting`` role)."""
    with FakeModelServer() as server:
        yield server


@pytest.fixture(autouse=True)
def _reset_models(
    classifier: FakeModelServer, explainer: FakeModelServer, drafter_server: FakeModelServer
) -> None:
    for server in (classifier, explainer, drafter_server):
        server.requests.clear()
    classifier.replies[DEFAULT_MODEL_ID] = classification_reply()
    explainer.replies[DEFAULT_MODEL_ID] = explanation_reply()
    drafter_server.replies[DEFAULT_MODEL_ID] = letter_reply()


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def roles(
    classifier: FakeModelServer, explainer: FakeModelServer, drafter_server: FakeModelServer
) -> dict[ModelRole, str]:
    return {
        ModelRole.CLASSIFICATION: classifier.base_url,
        ModelRole.EXPLANATION: explainer.base_url,
        ModelRole.DRAFTING: drafter_server.base_url,
    }


@pytest.fixture
def sent() -> Sent:
    return []


Desktop = Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]]


@pytest.fixture
def desktop_for(
    service: CorpusService,
    roles: dict[ModelRole, str],
    sent: Sent,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Desktop:
    """``ctx.rest`` against a gateway whose worker serves ``roles`` (all of them by default)."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))

    @asynccontextmanager
    async def connect(
        only: tuple[ModelRole, ...] | None = None,
    ) -> AsyncIterator[httpx.AsyncClient]:
        served = roles if only is None else {role: roles[role] for role in only}
        worker = create_app(TOKEN, corpus=service, pipeline_models=role_models(served))
        client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
        gateway = FastAPI()
        gateway.include_router(routes.router, prefix=PREFIX)
        gateway.dependency_overrides[routes.get_worker_client] = lambda: client
        gateway.dependency_overrides[routes.get_event_sink] = lambda: (
            lambda plugin, event, payload: sent.append((plugin, event, payload))
        )
        transport = httpx.ASGITransport(app=gateway)
        async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
            desktop.worker = worker  # type: ignore[attr-defined]
            yield desktop

    return connect


@pytest.fixture
async def desktop(desktop_for: Desktop) -> AsyncIterator[httpx.AsyncClient]:
    async with desktop_for() as client:
        yield client


async def diagnosed_case(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    *,
    templates: CorpusBundle | None = TEMPLATE_BUNDLE,
    cards: CorpusBundle | None = RULE_BUNDLE,
) -> str:
    """Import code notes, cards, and templates, then extract and diagnose the synthetic case."""
    await service.import_bundle(CODE_BUNDLE)
    for bundle in (cards, templates):
        if bundle is not None:
            await service.import_bundle(bundle)
    case_id = await new_case(desktop)
    await run_job(desktop, case_id, "process")
    await run_job(desktop, case_id, "diagnose")
    return case_id


async def drafted_case(desktop: httpx.AsyncClient, service: CorpusService, **kwargs: Any) -> str:
    case_id = await diagnosed_case(desktop, service, **kwargs)
    started = await draft(desktop, case_id)
    assert started.kind == "draft"
    return case_id


async def draft(
    desktop: httpx.AsyncClient, case_id: str, body: dict[str, Any] | None = None
) -> JobStarted:
    """Press Draft appeal and wait until the relay sent the job's last event."""
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/draft", json=body or {})
    assert response.status_code == 200, response.text
    await asyncio.gather(*relay._RELAYS.values())
    return JobStarted.model_validate_json(response.content)


# --- Scenario: Draft is generated from rule card and template ------------------------------------


async def test_us_7_1_draft_from_rule_card_and_template(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    sent: Sent,
    drafter_server: FakeModelServer,
) -> None:
    case_id = await diagnosed_case(desktop, service)

    started = await draft(desktop, case_id)

    assert started.kind == "draft"
    case = await open_case(desktop, case_id)
    assert case.draft is not None, "a draft letter is attached to the case"
    assert case.draft.text == LETTER
    assert case.draft.template_id == "appeal-prior-authorization"
    assert case.draft.rule_cards == ["ACME Health/appeal_levels", "ACME Health/required_docs"]
    assert case.diagnosis is not None
    assert case.draft.diagnosed_at == case.diagnosis.diagnosed_at
    assert (case.draft.edited_at, case.draft_stale) == (None, False)
    # The rule cards and the template both reached the drafting model, as data.
    data = str(drafter_server.requests[-1].messages[1].content)
    assert "Prior-authorization appeal: cite the retro-authorization request" in data
    assert "ACME Health/required_docs (source: ACME Health provider manual (synthetic)" in data
    assert all(document in data for document in ACME_DOCUMENTS[::2]), "the checklist encloses"
    events = events_of(sent, started.job_id)
    assert [(e.stage, e.progress) for e in events] == [("drafting", 0.0), ("done", 1.0)]
    actions = [entry.action for entry in service.user_store("default").audit_log(case_id)]
    assert actions[-2:] == [AuditAction.CASE_DRAFTED, AuditAction.CASE_OPENED]


async def test_us_7_1_progress_relayed(
    desktop: httpx.AsyncClient, service: CorpusService, sent: Sent
) -> None:
    case_id = await diagnosed_case(desktop, service)
    started = await draft(desktop, case_id)
    assert {(plugin, event) for plugin, event, _ in sent} == {(PLUGIN_NAME, "case.progress")}
    # PHI-free by construction (US-3.4): no letter text in any payload.
    wire = json.dumps([event.model_dump() for event in events_of(sent, started.job_id)])
    for text in ("ACME", "CLAIM-77", "appeal", "Appeals Unit"):
        assert text not in wire


# --- Scenario: Draft carries the human-review label ----------------------------------------------


async def test_us_7_1_draft_carries_review_label(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await drafted_case(desktop, service)

    case = await open_case(desktop, case_id)
    assert case.draft is not None
    assert case.draft.label == DRAFT_LABEL == "draft for human review", "displayed with the label"
    wire = (await desktop.get(f"{PREFIX}/cases/{case_id}")).json()
    assert wire["draft"]["label"] == "draft for human review", "the pane receives it"
    # Exported: on every PDF page, and as the DOCX's first paragraph (US-7.2 renders both).
    with pymupdf.open(stream=render_pdf(case.draft), filetype="pdf") as pdf:  # type: ignore[no-untyped-call]
        assert all(page.get_text(sort=True).startswith("Draft for human review") for page in pdf)
        assert "draft for human review" in pdf.metadata["title"]
    with zipfile.ZipFile(io.BytesIO(render_docx(case.draft))) as docx:
        document = docx.read("word/document.xml").decode()
    assert document.index("Draft for human review") < document.index("Appeals Unit")


def test_us_7_1_draft_model_is_strict() -> None:
    fields = {
        "text": "Letter",
        "template_id": "appeal",
        "extraction_digest": "0" * 64,
        "diagnosed_at": "2026-10-31T12:00:00Z",
        "drafted_at": "2026-10-31T12:05:00Z",
    }
    assert AppealDraft.model_validate(fields).label == "draft for human review"
    for bad in (
        {"label": "final letter"},
        {"text": "   "},
        {"text": "x" * 20_001},
        {"template_id": "Not A Template"},
        {"recipient": "payer@example.com"},
        {"drafted_at": "2026-10-31T12:05:00"},
    ):
        with pytest.raises(ValidationError):
            AppealDraft.model_validate(fields | bad)
    with pytest.raises(ValidationError):
        DraftRequest.model_validate({"template_id": "../etc"})
    assert DraftRequest().template_id is None


# --- Scenario: The template is chosen by the denial reason ---------------------------------------


@pytest.mark.parametrize(
    ("templates", "body", "chosen"),
    [
        (
            ["appeal", "appeal-prior-authorization", "corrected-claim"],
            {},
            "appeal-prior-authorization",
        ),
        (["appeal", "corrected-claim"], {}, "appeal"),
        (["appeal", "corrected-claim"], {"template_id": "corrected-claim"}, "corrected-claim"),
    ],
)
async def test_us_7_1_template_chosen_by_denial_reason(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    templates: list[str],
    body: dict[str, Any],
    chosen: str,
) -> None:
    bundle = CorpusBundle(items=[item for item in TEMPLATE_BUNDLE.items if item.key in templates])
    case_id = await diagnosed_case(desktop, service, templates=bundle)
    await draft(desktop, case_id, body)
    drafted = (await open_case(desktop, case_id)).draft
    assert drafted is not None
    assert drafted.template_id == chosen


def test_us_7_1_template_ids() -> None:
    assert template_ids(DenialReason.COORDINATION_OF_BENEFITS, DraftRequest()) == [
        "appeal-coordination-of-benefits",
        "appeal",
    ]
    assert template_ids(DenialReason.OTHER, DraftRequest(template_id="x")) == ["x"]


async def test_us_7_1_letter_template_lookup(
    service: CorpusService, caplog: pytest.LogCaptureFixture
) -> None:
    await service.import_bundle(TEMPLATE_BUNDLE)
    store = service.global_store()
    found = letter_template(store, ["missing", "corrected-claim", "appeal"])
    assert found is not None
    assert (found.template_id, found.verified_on) == ("corrected-claim", date(2026, 9, 1))
    assert letter_template(store, ["missing"]) is None
    broken = Document(
        doc_id="letter_template:broken",
        scope=CorpusScope.GLOBAL,
        kind="letter_template",
        title="Broken",
        text="A stored template without its key.",
        metadata={"source": "x"},
    )
    store.put_document(broken, split_text(broken.text), vectors_for(split_text(broken.text)))
    assert letter_template(store, ["appeal"]) is not None, "a malformed template is skipped"
    assert "a stored letter template did not validate: KeyError" in caplog.text
    with pytest.raises(CorpusError):
        letter_template(service.user_store("default", create=True), ["appeal"])


# --- Scenario: Drafting needs a current diagnosis and a template ---------------------------------


async def test_us_7_1_drafting_needs_a_current_diagnosis(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    await service.import_bundle(TEMPLATE_BUNDLE)
    case_id = await new_case(desktop)
    await run_job(desktop, case_id, "process")
    worker: FastAPI = desktop.worker  # type: ignore[attr-defined]

    response = await desktop.post(f"{PREFIX}/cases/{case_id}/draft", json={})
    assert_envelope(response, 409, "not_diagnosed")
    assert relay._RELAYS == {}, "nothing relayed"
    assert worker.state.jobs.running("default", case_id) is None, "no job started"

    await run_job(desktop, case_id, "diagnose")
    confirmed = await desktop.post(
        f"{PREFIX}/cases/{case_id}/fields", json={"path": "claim_id", "value": "CLAIM-78"}
    )
    assert confirmed.status_code == 200, confirmed.text
    stale = await desktop.post(f"{PREFIX}/cases/{case_id}/draft", json={})
    assert_envelope(stale, 409, "not_diagnosed")  # the fields changed since the diagnosis

    missing = await desktop.post(f"{PREFIX}/cases/case_0000000000000000/draft", json={})
    assert_envelope(missing, 404, "case_not_found")
    for bad in (b"x", b'{"template_id": "Bad Id"}', b'{"to": "payer"}'):
        refused = await desktop.post(
            f"{PREFIX}/cases/{case_id}/draft",
            content=bad,
            headers={"content-type": "application/json"},
        )
        assert_envelope(refused, 422, "invalid_request")
    assert_envelope(
        await desktop.post(f"{PREFIX}/cases/bad!id/draft", json={}), 422, "invalid_request"
    )

    service.user_store("default").close_case(case_id)
    closed = await desktop.post(f"{PREFIX}/cases/{case_id}/draft", json={})
    assert_envelope(closed, 409, "case_closed")


async def test_us_7_1_no_letter_template(
    desktop: httpx.AsyncClient, service: CorpusService, drafter_server: FakeModelServer
) -> None:
    case_id = await diagnosed_case(desktop, service, templates=None)

    response = await desktop.post(f"{PREFIX}/cases/{case_id}/draft", json={})
    assert_envelope(response, 409, "no_letter_template")

    await service.import_bundle(TEMPLATE_BUNDLE)
    named = await desktop.post(f"{PREFIX}/cases/{case_id}/draft", json={"template_id": "nope"})
    assert_envelope(named, 409, "no_letter_template")
    assert drafter_server.requests == [], "the model was never asked"


async def test_us_7_1_a_case_without_rule_cards_is_drafted(
    desktop: httpx.AsyncClient, service: CorpusService, drafter_server: FakeModelServer
) -> None:
    """Design decision 2: a payer without cards still gets a draft, and the draft says so."""
    case_id = await drafted_case(desktop, service, cards=None)
    drafted = (await open_case(desktop, case_id)).draft
    assert drafted is not None
    assert drafted.rule_cards == []
    assert "No rule card is on file for this payer." in str(
        drafter_server.requests[-1].messages[1].content
    )


async def test_us_7_1_case_ids_events_cannot_carry_are_unknown(service: CorpusService) -> None:
    cases = CaseService(service)
    service.user_store("default", create=True).create_case("legacy-case")
    with pytest.raises(CaseNotFoundError):
        Drafter(cases, role_models({})).check("default", "legacy-case")


# --- Scenario: An unusable reply stores nothing --------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "Dear payer, here is the letter.",
        letter_reply("   "),
        letter_reply(5),
        letter_reply(None),
        json.dumps({"text": LETTER}),
    ],
)
async def test_us_7_1_unusable_reply_stores_nothing(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    sent: Sent,
    drafter_server: FakeModelServer,
    reply: str,
) -> None:
    case_id = await drafted_case(desktop, service)
    before = (await open_case(desktop, case_id)).draft
    drafter_server.replies[DEFAULT_MODEL_ID] = reply

    started = await draft(desktop, case_id)

    last = events_of(sent, started.job_id)[-1]
    assert (last.stage, last.error_code) == ("failed", "drafting_failed")
    assert (await open_case(desktop, case_id)).draft == before, "the previous draft is kept"


def test_us_7_1_replies_are_read_leniently_where_safe() -> None:
    assert parse_letter(f"<think>plan</think>```json\n{letter_reply()}\n```") == LETTER
    assert parse_letter(letter_reply("  Letter text.  ", extra="ignored")) == "Letter text."
    clipped = parse_letter(letter_reply("word " * 5000))
    assert clipped is not None
    assert (len(clipped), clipped[-1]) == (20_000, "…"), "a long letter is clipped, not refused"
    assert parse_letter("{not json}") is None


async def test_us_7_1_drafting_model_missing(
    desktop_for: Desktop, service: CorpusService, sent: Sent
) -> None:
    only = (ModelRole.CLASSIFICATION, ModelRole.EXPLANATION)
    async with desktop_for(only) as desktop:
        case_id = await diagnosed_case(desktop, service)
        started = await draft(desktop, case_id)
        last = events_of(sent, started.job_id)[-1]
        assert (last.stage, last.error_code) == ("failed", "model_unavailable")
        assert (await open_case(desktop, case_id)).draft is None


async def test_us_7_1_a_worker_without_models_cannot_draft(service: CorpusService) -> None:
    app = create_app(TOKEN, corpus=service)
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(app))
    case = await client.create_case("default")
    with pytest.raises(WorkerRejectedError) as raised:
        await client.start_draft("default", case.case_id, DraftRequest())
    assert raised.value.code == "model_unavailable"


async def extracted_and_diagnosed(cases: CaseService, models: Any) -> str:
    case_id = cases.create("default").case_id
    cases.add_text("default", case_id, ERA_835)
    await Extractor(cases, models).run("default", case_id, lambda _s, _p: None)
    await Diagnoser(cases, models).run("default", case_id, lambda _s, _p: None)
    return case_id


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ModelUnavailableError(), "model_unavailable"),
        (CaseClosedError(), "case_closed"),
        (RuntimeError("Jane Doe"), "drafting_failed"),
    ],
)
async def test_us_7_1_a_failed_draft_ends_with_its_code(
    service: CorpusService,
    roles: dict[ModelRole, str],
    error: Exception,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await service.import_bundle(TEMPLATE_BUNDLE)
    cases = CaseService(service)
    case_id = await extracted_and_diagnosed(cases, role_models(roles))
    jobs = JobRegistry(Extractor(cases, Failing(error)))
    started = jobs.start("default", case_id, "draft", runner=Drafter(cases, Failing(error)))
    events = await finish(jobs, started.job_id)
    assert (events[-1].stage, events[-1].error_code) == ("failed", code)
    assert "Jane Doe" not in caplog.text  # BR-14: the error type only
    assert "draft job failed" in caplog.text


async def test_us_7_1_a_job_reads_the_case_again(
    service: CorpusService, roles: dict[ModelRole, str]
) -> None:
    """The route checks first, but the job checks again: it never drafts from nothing."""
    cases = CaseService(service)
    models = role_models(roles)
    case_id = cases.create("default").case_id
    with pytest.raises(NotDiagnosedError):
        await Drafter(cases, models).run("default", case_id, lambda _s, _p: None)
    case_id = await extracted_and_diagnosed(cases, models)
    with pytest.raises(NoLetterTemplateError):
        await Drafter(cases, models).run("default", case_id, lambda _s, _p: None)


async def test_us_7_1_one_job_per_case(service: CorpusService, roles: dict[ModelRole, str]) -> None:
    await service.import_bundle(TEMPLATE_BUNDLE)
    cases = CaseService(service)
    models = role_models(roles)
    case_id = await extracted_and_diagnosed(cases, models)
    gate = asyncio.Event()

    class SlowDrafter(Drafter):
        async def run(self, profile: str, case_id: str, report: Any) -> AppealDraft:
            await gate.wait()
            return await super().run(profile, case_id, report)

    jobs = JobRegistry(Extractor(cases, models), diagnoser=Diagnoser(cases, models))
    drafting = jobs.start("default", case_id, "draft", runner=SlowDrafter(cases, models))
    joined = jobs.start("default", case_id, "diagnose")
    assert joined == drafting, "a diagnosis asked for mid-draft joins the running job"
    assert joined.kind == "draft"
    gate.set()
    events = await finish(jobs, drafting.job_id)
    assert events[-1].stage == "done"
    assert cases.draft(cases.store("default"), case_id) is not None
    with pytest.raises(ModelUnavailableError):
        jobs.start("default", case_id, "draft")  # no runner registered or given


async def test_us_7_1_draft_during_a_running_job_joins_it(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await diagnosed_case(desktop, service)
    worker: FastAPI = desktop.worker  # type: ignore[attr-defined]
    gate = asyncio.Event()

    class Slow:
        async def run(self, _profile: str, _case_id: str, report: Any) -> None:
            await gate.wait()
            report("done", 1.0)

    running = worker.state.jobs.start("default", case_id, "diagnose", runner=Slow())
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/draft", json={})
    assert JobStarted.model_validate_json(response.content) == running, "the biller follows it"
    gate.set()
    await asyncio.gather(*relay._RELAYS.values())


def test_us_7_1_a_worker_without_models_has_no_drafter() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(ModelUnavailableError):
        case_routes.get_drafter(request)  # type: ignore[arg-type]


# --- The drafting prompt -------------------------------------------------------------------------


async def test_us_7_1_prompt_carries_letter_facts(
    desktop: httpx.AsyncClient, service: CorpusService, drafter_server: FakeModelServer
) -> None:
    case_id = await diagnosed_case(desktop, service)
    # Another case of the same profile, extracted and diagnosed: its claim number is in the store.
    other = await new_case(desktop, ERA_835.replace("CLAIM-77", "CLAIM-99"))
    await run_job(desktop, other, "process")
    await run_job(desktop, other, "diagnose")
    await draft(desktop, case_id)

    request = drafter_server.requests[-1]
    system, user = (str(message.content) for message in request.messages)
    assert "draft appeal letters" in system
    assert "Return one JSON object" in user
    assert "letter" in user
    assert "[Patient name]" in user, "placeholders stand in for what the data does not give"
    for fact in ("CLAIM-77", "2026-10-15", "2026-09-01", "99213", "197", "N286"):
        assert fact in user
    assert "CLAIM-99" not in user, f"case {other} never reaches this case's prompt (BR-5)"
    assert DRAFT_TEMPLATE in registered_templates()
    assert (request.model_extra or {})["max_tokens"] == 8192, "room for a 20000-character letter"
    assert case_id


def test_us_7_1_letter_facts_of_an_extraction() -> None:
    extraction = CaseExtraction.model_validate(
        {
            "payer_name": {"value": "ACME HEALTH PLAN", "status": "extracted"},
            "claim_id": {"value": "CLAIM-77", "status": "confirmed"},
            "billed_amount": {"value": "250.00", "status": "extracted"},
            "paid_amount": {"value": None, "status": "unreadable"},
            "denial_date": {"value": "2026-10-15", "status": "extracted"},
            "lines": [
                {
                    "procedure_code": {"value": "99213", "status": "extracted"},
                    "service_date": {"value": "2026-09-01", "status": "extracted"},
                    "billed_amount": {"value": "250.00", "status": "extracted"},
                    "paid_amount": {"value": "0.00", "status": "extracted"},
                }
            ],
        }
    )
    facts = letter_facts(extraction)
    assert list(facts)[:3] == ["payer", "claim_number", "denial_date"]
    assert (facts["claim_number"], facts["denial_date"], facts["paid_amount"]) == (
        "CLAIM-77",
        "2026-10-15",
        None,
    )
    assert facts["lines"][0]["service_date"] == "2026-09-01"
    assert facts["lines"][0]["procedure_code"] == "99213"


# --- Scenario: A confirmed field makes the draft stale -------------------------------------------


async def test_us_7_1_draft_stale_after_confirmed_field(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await drafted_case(desktop, service)
    assert (await open_case(desktop, case_id)).draft_stale is False

    confirmed = await desktop.post(
        f"{PREFIX}/cases/{case_id}/fields", json={"path": "claim_id", "value": "CLAIM-78"}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["draft_stale"] is True, "the confirmation's answer says so"

    await run_job(desktop, case_id, "diagnose")
    rediagnosed = await open_case(desktop, case_id)
    assert rediagnosed.draft is not None, "drafting again is the biller's choice"
    assert rediagnosed.draft_stale is True, "the diagnosis it argued from was replaced"

    await draft(desktop, case_id)
    assert (await open_case(desktop, case_id)).draft_stale is False


async def test_us_7_1_draft_again_replaces_the_draft(
    desktop: httpx.AsyncClient, service: CorpusService, drafter_server: FakeModelServer
) -> None:
    case_id = await drafted_case(desktop, service)
    edited = await desktop.post(f"{PREFIX}/cases/{case_id}/draft/text", json={"text": "Mine."})
    assert edited.status_code == 200, edited.text
    drafter_server.replies[DEFAULT_MODEL_ID] = letter_reply("A second letter.")

    await draft(desktop, case_id)

    drafted = (await open_case(desktop, case_id)).draft
    assert drafted is not None
    assert (drafted.text, drafted.edited_at) == ("A second letter.", None)


async def test_us_7_1_draft_purged_with_case(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await drafted_case(desktop, service)
    store = service.user_store("default")
    assert store.case_items(case_id, "draft")
    store.close_case(case_id)
    service.purge(PurgeRequest(profile="default", case_id=case_id, confirm=True))
    assert store.case_items(case_id, "draft") == []


async def test_us_7_1_a_us_6_store_accepts_drafts(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    """A store whose ``case_items`` CHECK predates drafts is rebuilt once (the US-6.1 migration)."""
    root = tmp_path / "hermes"
    keys = InMemoryKeyProvider()
    corpus = make_service(root, corpus_server, keys=keys)
    case_id = CaseService(corpus).create("default").case_id
    corpus.close()
    database = profile_user_scope_dir("default", root, create=False) / DATABASE
    with sqlite3.connect(database) as db:
        db.executescript(
            """
            CREATE TABLE case_items_old (
                case_id TEXT NOT NULL REFERENCES cases(case_id), item_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('source', 'extraction', 'diagnosis')),
                created_at TEXT NOT NULL, payload BLOB NOT NULL, data BLOB,
                PRIMARY KEY (case_id, item_id)
            ) STRICT;
            INSERT INTO case_items_old SELECT * FROM case_items;
            DROP TABLE case_items;
            ALTER TABLE case_items_old RENAME TO case_items;
            """
        )
    db.close()
    corpus = make_service(root, corpus_server, keys=keys)
    try:
        cases = CaseService(corpus)
        draft = AppealDraft(
            text="Letter.",
            template_id="appeal",
            extraction_digest="0" * 64,
            diagnosed_at=utc_now(),
            drafted_at=utc_now(),
        )
        cases.save_draft("default", case_id, draft)
        assert cases.draft(cases.store("default"), case_id) == draft
    finally:
        corpus.close()
    with sqlite3.connect(database) as db:
        (sql,) = db.execute("SELECT sql FROM sqlite_master WHERE name = 'case_items'").fetchone()
    db.close()
    assert "'draft'" in sql


async def test_us_7_1_a_cut_off_reply_is_named_in_the_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Review: a reply stopped at max_tokens fails like any unusable reply, and the log says so."""

    async def cut_off(*_args: Any, **_kwargs: Any) -> ChatReply:
        return ChatReply(content='{"letter": "Dear reviewer, we appeal', truncated=True)

    monkeypatch.setattr(draft_module, "chat_completion", cut_off)
    endpoint = ModelEndpoint(role=ModelRole.DRAFTING, base_url="http://127.0.0.1:9/v1")
    template = TEMPLATE_BUNDLE.items[0]
    extraction = CaseExtraction.model_validate_json(_extraction_json())
    with pytest.raises(DraftingFailedError):
        await draft_module.draft_letter(endpoint, extraction, _diagnosis(extraction), [], template)  # type: ignore[arg-type]
    assert "drafting reply stopped at max_tokens" in caplog.text
    assert "Dear reviewer" not in caplog.text


async def test_us_7_1_a_closed_case_never_loads_the_model(
    service: CorpusService, roles: dict[ModelRole, str]
) -> None:
    """Review: closing the case after Draft appeal stops the job before the 27B model loads."""
    await service.import_bundle(TEMPLATE_BUNDLE)
    cases = CaseService(service)
    case_id = await extracted_and_diagnosed(cases, role_models(roles))
    service.user_store("default").close_case(case_id)
    asked: list[ModelRole] = []

    @asynccontextmanager
    async def models(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        asked.append(role)
        yield ModelEndpoint(role=role, base_url="http://127.0.0.1:9/v1")

    with pytest.raises(CaseClosedError):
        await Drafter(cases, models).run("default", case_id, lambda _s, _p: None)
    assert asked == []


def test_us_7_1_unedited_drafting_command_migrates(tmp_path: Path) -> None:
    """Review: an existing pre-US-7.1 models.yaml gets --reasoning off, unless it was edited."""
    new = DEFAULT_REGISTRY.read_text()
    shipped = '"--port", "{port}", "--no-auth", "--reasoning", "off"]'
    assert shipped in new
    old = new.replace(shipped, '"--port", "{port}", "--no-auth"]')
    unedited = tmp_path / "unedited"
    unedited.mkdir()
    (unedited / REGISTRY_FILE).write_text(old)
    (unedited / REGISTRY_FILE).chmod(0o640)
    path = ensure_registry_file(unedited)
    assert path.read_text() == new
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert ensure_registry_file(unedited).read_text() == new, "once"
    command = ModelRegistry.load(path).roles[ModelRole.DRAFTING].command
    assert command[-2:] == ["--reasoning", "off"]
    edited = tmp_path / "edited"
    edited.mkdir()
    custom = old.replace('"--no-auth"]', '"--no-auth", "--profile", "turbo"]')
    (edited / REGISTRY_FILE).write_text(custom)
    assert ensure_registry_file(edited).read_text() == custom, "an edited command is left alone"
    assert list(edited.iterdir()) == [edited / REGISTRY_FILE], "no temporary file is left"


def _extraction_json() -> str:
    return json.dumps(
        {
            "payer_name": {"value": "ACME HEALTH PLAN", "status": "extracted"},
            "claim_id": {"value": "CLAIM-77", "status": "extracted"},
            "billed_amount": {"value": "250.00", "status": "extracted"},
            "paid_amount": {"value": "0.00", "status": "extracted"},
        }
    )


def _diagnosis(extraction: CaseExtraction) -> Diagnosis:
    return Diagnosis(
        denial_reason=DenialReason.PRIOR_AUTHORIZATION,
        appeal_likelihood=AppealLikelihood.HIGH,
        likelihood_reasons=CLASSIFICATION["reasons"],
        extraction_digest=extraction.digest(),
        diagnosed_at=utc_now(),
    )


# --- Real model ----------------------------------------------------------------------------------


@pytest.mark.models
async def test_us_7_1_draft_real_model(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    """Bonsai 27B from MODELS_HOME drafts the synthetic case's letter (skips without weights)."""
    from claimcoach.models.manager import ModelManager  # noqa: PLC0415
    from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry, models_home  # noqa: PLC0415

    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    home = models_home()
    spec = registry.roles[ModelRole.DRAFTING]
    if spec.weights(home) == "missing" or not os.access(home, os.R_OK):
        pytest.skip(f"Ternary-Bonsai-2-27B weights not found at {spec.model_path(home)}")
    manager = ModelManager(registry, models_home=home, state_dir=tmp_path / "models")
    corpus = make_service(tmp_path / "hermes", corpus_server)
    cases = CaseService(corpus)
    try:
        for bundle in (CODE_BUNDLE, RULE_BUNDLE, TEMPLATE_BUNDLE):
            await corpus.import_bundle(bundle)
        case_id = cases.create("default").case_id
        cases.add_text("default", case_id, ERA_835)
        # A pasted 835 is read without a model; only the 27B model runs here.
        await Extractor(cases, role_models({})).run("default", case_id, lambda _s, _p: None)
        extraction = cases.extraction_of("default", case_id)
        diagnosis = Diagnosis(
            denial_reason=DenialReason.PRIOR_AUTHORIZATION,
            appeal_likelihood=AppealLikelihood.HIGH,
            likelihood_reasons=CLASSIFICATION["reasons"],
            extraction_digest=extraction.digest(),
            diagnosed_at=utc_now(),
        )
        cases.save_diagnosis("default", case_id, diagnosis)
        drafted = await Drafter(cases, manager.use).run("default", case_id, lambda _s, _p: None)
    finally:
        await manager.shutdown()
        corpus.close()
    assert "CLAIM-77" in drafted.text
    assert drafted.label == "draft for human review"
