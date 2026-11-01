"""US-7.4 Corrected Claim Draft (Python half).

Scenarios: an appeal-only denial gets a recommendation, not a corrected-claim draft; a correctable
denial gets a list of changes for human review; a value missing from the documents is never
invented; a draft goes stale after re-extraction; the label is always present; the corrected-claim
draft exports as PDF or DOCX; no submit control. Also: the routing table and its code splits, the
payer's rule card overriding it, the frequency code, the planned changes, the reply parser that
refuses new codes, refusals before a job starts, the corrected_claims card topic, and the purge.
The pane scenarios run under ``node --test`` (``plugin/desktop/tests/corrected_claim.test.mjs``).
Rules: ES-1, ES-4, BR-1, BR-2, BR-4, BR-7, BR-10, BR-14, Non-goals §5.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import unicodedata
import zipfile
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final

import httpx
import pymupdf
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach.agent.answers import payer_rules
from claimcoach.api import relay, routes
from claimcoach.api.client import WorkerClient, WorkerRejectedError
from claimcoach.cases.diagnosis import (
    MAX_RULE_CARDS,
    AppealLikelihood,
    DenialReason,
    Diagnosis,
    Remedy,
    RuleCardRef,
)
from claimcoach.cases.errors import CorrectionFailedError
from claimcoach.cases.extraction import CaseExtraction, JobStarted
from claimcoach.cases.service import CaseService
from claimcoach.corpus.bundle import CorpusBundle, RuleCard, parse_bundle_bytes
from claimcoach.corpus.errors import CaseClosedError
from claimcoach.corpus.lookup import payer_rule_cards
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, PurgeRequest, utc_now
from claimcoach.corrections import draft as correction_module
from claimcoach.corrections.draft import (
    CODE_FIELDS,
    CORRECTION_TEMPLATE,
    Corrector,
    PlannedCorrection,
    allowed_codes,
    parse_corrections,
    plan_corrections,
)
from claimcoach.corrections.remedy import (
    REMEDY_TABLE,
    case_code_uses,
    frequency_code,
    recommended_remedy,
)
from claimcoach.corrections.types import (
    FIELD_LABELS,
    FREQUENCY_MEANINGS,
    MAX_CORRECTIONS,
    NOT_IN_DOCUMENTS,
    ClaimCorrection,
    CorrectableField,
    CorrectedClaimDraft,
    RemedyAdvice,
)
from claimcoach.letters.export import (
    CORRECTION_TITLE,
    HEADER,
    correction_text,
    render_correction,
)
from claimcoach.letters.types import DRAFT_LABEL, AppealDraft, ExportedFile, ExportFormat
from claimcoach.models.chat import DEFAULT_MODEL_ID, ChatReply
from claimcoach.models.manager import ModelEndpoint, ModelUnavailableError
from claimcoach.models.types import ModelRole
from claimcoach.prompts.builder import registered_templates
from claimcoach.worker import case_routes
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.corrections import (
    ACTION,
    WHY,
    corrected_claims_card,
    correction_reply,
    drafting_responder,
)
from tests.fakes.diagnosis import (
    CODE_BUNDLE,
    RULE_BUNDLE,
    classification_reply,
    explanation_reply,
    role_models,
    rule_card,
)
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_5_1_case_intake import ERA_835
from tests.test_us_6_1_diagnosis import (
    PREFIX,
    Sent,
    assert_envelope,
    events_of,
    new_case,
    open_case,
    run_job,
)
from tests.test_us_7_3_no_send_submit import GATEWAY_ROUTES, SEND, WORKER_ROUTES

DENIED_LINE: Final = "CAS*CO*197*250~LQ*HE*N286~"
"""The synthetic 835's line adjustment and remark code (prior authorization)."""
CODING_ERROR: Final = "CAS*CO*4*250~LQ*HE*M51~"
"""CO-4 (procedure code inconsistent with the modifier) and M51 (procedure code invalid)."""


def era(line_codes: str) -> str:
    """The synthetic 835 with ``line_codes`` as its one line's CAS and LQ segments."""
    return ERA_835.replace(DENIED_LINE, line_codes)


# --- Fixtures ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def role_servers() -> Iterator[dict[ModelRole, FakeModelServer]]:
    """Fake Qwen3-8B, Qwen3-14B, and Bonsai 27B, each answering its own role's prompt."""
    servers = {
        role: FakeModelServer().start()
        for role in (ModelRole.CLASSIFICATION, ModelRole.EXPLANATION, ModelRole.DRAFTING)
    }
    yield servers
    for server in servers.values():
        server.stop()


@pytest.fixture(autouse=True)
def _reset_models(role_servers: dict[ModelRole, FakeModelServer]) -> None:
    for server in role_servers.values():
        server.requests.clear()
    role_servers[ModelRole.CLASSIFICATION].replies[DEFAULT_MODEL_ID] = classification_reply()
    role_servers[ModelRole.EXPLANATION].replies[DEFAULT_MODEL_ID] = explanation_reply()
    role_servers[ModelRole.DRAFTING].responders[DEFAULT_MODEL_ID] = drafting_responder()


def classify_as(servers: dict[ModelRole, FakeModelServer], reason: DenialReason) -> None:
    servers[ModelRole.CLASSIFICATION].replies[DEFAULT_MODEL_ID] = classification_reply(
        denial_reason=reason.value
    )


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def worker(service: CorpusService, role_servers: dict[ModelRole, FakeModelServer]) -> FastAPI:
    urls = {role: server.base_url for role, server in role_servers.items()}
    return create_app(TOKEN, corpus=service, pipeline_models=role_models(urls))


@pytest.fixture
def sent() -> Sent:
    return []


@pytest.fixture
async def desktop(
    worker: FastAPI, sent: Sent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """``ctx.rest`` against the gateway over ``worker``."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
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


async def diagnosed(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    text: str = ERA_835,
    cards: CorpusBundle | None = RULE_BUNDLE,
) -> str:
    """Import code notes and cards, then extract and diagnose a case holding ``text``."""
    await service.import_bundle(CODE_BUNDLE)
    if cards is not None:
        await service.import_bundle(cards)
    case_id = await new_case(desktop, text)
    await run_job(desktop, case_id, "process")
    await run_job(desktop, case_id, "diagnose")
    return case_id


async def correct(desktop: httpx.AsyncClient, case_id: str) -> JobStarted:
    """Press Draft corrected claim and wait until the relay sent the job's last event."""
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/correction", json={})
    assert response.status_code == 200, response.text
    await asyncio.gather(*relay._RELAYS.values())
    return JobStarted.model_validate_json(response.content)


async def export(desktop: httpx.AsyncClient, case_id: str, fmt: str) -> httpx.Response:
    return await desktop.post(f"{PREFIX}/cases/{case_id}/correction/export", json={"format": fmt})


# --- Builders for the pure functions -------------------------------------------------------------


def value(read: str | None) -> dict[str, Any]:
    return {"value": read, "status": "unreadable" if read is None else "extracted"}


def adjustment(carc: str | None, group: str | None = "CO") -> dict[str, Any]:
    return {"group_code": value(group), "carc": value(carc), "amount": value("250.00")}


def line(
    carcs: tuple[str | None, ...] = (),
    rarcs: tuple[str | None, ...] = (),
    procedure: str | None = "99213",
    served: str | None = "2026-09-01",
) -> dict[str, Any]:
    return {
        "procedure_code": value(procedure),
        "service_date": value(served),
        "billed_amount": value("250.00"),
        "paid_amount": value("0.00"),
        "adjustments": [adjustment(carc) for carc in carcs],
        "rarc_codes": [value(rarc) for rarc in rarcs],
    }


def extraction(
    *lines: dict[str, Any],
    carcs: tuple[str | None, ...] = (),
    rarcs: tuple[str | None, ...] = (),
    claim_id: str | None = "CLAIM-77",
    billed: str | None = "250.00",
) -> CaseExtraction:
    return CaseExtraction.model_validate(
        {
            "payer_name": value("ACME HEALTH PLAN"),
            "claim_id": value(claim_id),
            "billed_amount": value(billed),
            "paid_amount": value("0.00"),
            "adjustments": [adjustment(carc) for carc in carcs],
            "rarc_codes": [value(rarc) for rarc in rarcs],
            "lines": list(lines),
        }
    )


def diagnosis(
    reason: DenialReason, of: CaseExtraction, codes: list[str] | None = None
) -> Diagnosis:
    return Diagnosis(
        denial_reason=reason,
        appeal_likelihood=AppealLikelihood.MEDIUM,
        likelihood_reasons=["Synthetic reason."],
        codes=codes or [],
        extraction_digest=of.digest(),
        diagnosed_at=utc_now(),
    )


def card(**fields: Any) -> RuleCard:
    item = corrected_claims_card(**fields).items[0]
    assert isinstance(item, RuleCard)
    return item


def remedy_of(
    reason: DenialReason, of: CaseExtraction, cards: list[RuleCard] | None = None
) -> RemedyAdvice:
    return recommended_remedy(diagnosis(reason, of), of, cards or [])


def sample_correction(**changes: Any) -> CorrectedClaimDraft:
    fields: dict[str, Any] = {
        "original_claim_id": "CLAIM-77",
        "frequency_code": "7",
        "corrections": [
            {
                "line": 1,
                "field": "procedure_code",
                "current_value": "99213",
                "because": ["CO-4", "M51"],
                "action": ACTION,
                "why": WHY,
            },
            {"field": "member_id", "because": [], "action": ACTION, "why": WHY},
        ],
        "rule_cards": ["ACME Health/corrected_claims"],
        "extraction_digest": "0" * 64,
        "diagnosed_at": datetime(2026, 10, 31, 12, tzinfo=UTC),
        "drafted_at": datetime(2026, 10, 31, 12, 5, tzinfo=UTC),
    }
    return CorrectedClaimDraft.model_validate(fields | changes)


# --- Scenario: An appeal-only denial gets a recommendation, not a corrected-claim draft ----------


async def test_us_7_4_appeal_only_denial_gets_a_recommendation(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    role_servers: dict[ModelRole, FakeModelServer],
) -> None:
    classify_as(role_servers, DenialReason.MEDICAL_NECESSITY)
    case_id = await diagnosed(desktop, service)

    case = await open_case(desktop, case_id)

    assert case.remedy == RemedyAdvice(
        remedy=Remedy.APPEAL, basis="table", denial_reason=DenialReason.MEDICAL_NECESSITY
    ), "the pane recommends an appeal, and says the table decided it"
    assert (case.correction, case.correction_stale) == (None, False), "nothing drafted unasked"
    assert role_servers[ModelRole.DRAFTING].requests == [], "no model ran to route the case"
    wire = (await desktop.get(f"{PREFIX}/cases/{case_id}")).json()
    assert wire["remedy"] == {
        "remedy": "appeal",
        "basis": "table",
        "denial_reason": "medical_necessity",
        "codes": [],
        "rule_card": None,
    }


@pytest.mark.parametrize(
    ("reason", "remedy"),
    [
        (DenialReason.CODING_ERROR, Remedy.CORRECTED_CLAIM),
        (DenialReason.BUNDLING, Remedy.EITHER),
        (DenialReason.COORDINATION_OF_BENEFITS, Remedy.EITHER),
        (DenialReason.MEDICAL_NECESSITY, Remedy.APPEAL),
        (DenialReason.PRIOR_AUTHORIZATION, Remedy.APPEAL),
        (DenialReason.TIMELY_FILING, Remedy.APPEAL),
        (DenialReason.NON_COVERED_SERVICE, Remedy.APPEAL),
        (DenialReason.DUPLICATE_CLAIM, Remedy.NONE),
        (DenialReason.OTHER, Remedy.NONE),
        (DenialReason.ELIGIBILITY, Remedy.EITHER),  # until its codes settle it
        (DenialReason.MISSING_INFORMATION, Remedy.EITHER),
    ],
)
def test_us_7_4_routing_table_is_the_approved_one(reason: DenialReason, remedy: Remedy) -> None:
    assert set(REMEDY_TABLE) == set(DenialReason), "every denial reason has a row"
    advice = remedy_of(reason, extraction(line(carcs=("197",))))
    assert (advice.remedy, advice.basis, advice.codes) == (remedy, "table", [])


async def test_us_7_4_no_remedy_without_a_current_diagnosis(
    desktop: httpx.AsyncClient,
) -> None:
    case_id = await new_case(desktop)
    assert (await open_case(desktop, case_id)).remedy is None, "not extracted"
    await run_job(desktop, case_id, "process")
    assert (await open_case(desktop, case_id)).remedy is None, "not diagnosed"
    await run_job(desktop, case_id, "diagnose")
    assert (await open_case(desktop, case_id)).remedy is not None
    confirmed = await desktop.post(
        f"{PREFIX}/cases/{case_id}/fields", json={"path": "claim_id", "value": "CLAIM-78"}
    )
    assert confirmed.json()["remedy"] is None, "the fields changed since the diagnosis"
    assert CaseService.remedy(None, None, []) is None


# --- Scenario: Codes split eligibility and missing information -----------------------------------


@pytest.mark.parametrize(
    ("reason", "codes", "remedy", "shown"),
    [
        (DenialReason.ELIGIBILITY, {"carcs": ("31",)}, Remedy.CORRECTED_CLAIM, ["CO-31"]),
        (DenialReason.ELIGIBILITY, {"carcs": ("27",)}, Remedy.NONE, ["CO-27"]),
        (DenialReason.ELIGIBILITY, {"carcs": ("31", "27")}, Remedy.EITHER, ["CO-31", "CO-27"]),
        (DenialReason.MISSING_INFORMATION, {"rarcs": ("M76",)}, Remedy.CORRECTED_CLAIM, ["M76"]),
        (
            DenialReason.MISSING_INFORMATION,
            {"rarcs": ("MA130",)},
            Remedy.CORRECTED_CLAIM,
            ["MA130"],
        ),
        (DenialReason.MISSING_INFORMATION, {"rarcs": ("N706",)}, Remedy.APPEAL, ["N706"]),
        (DenialReason.MISSING_INFORMATION, {"carcs": ("252",)}, Remedy.APPEAL, ["CO-252"]),
        (
            DenialReason.MISSING_INFORMATION,
            {"carcs": ("16",), "rarcs": ("M51", "M127")},
            Remedy.EITHER,
            ["M51", "M127"],
        ),
    ],
)
def test_us_7_4_codes_split_eligibility_and_missing_information(
    reason: DenialReason, codes: dict[str, tuple[str, ...]], remedy: Remedy, shown: list[str]
) -> None:
    advice = remedy_of(reason, extraction(line(codes.get("carcs", ()), codes.get("rarcs", ()))))
    assert (advice.remedy, advice.basis, advice.codes) == (remedy, "codes", shown)
    unsettled = remedy_of(reason, extraction(line(carcs=("16",))))
    assert (unsettled.remedy, unsettled.basis) == (Remedy.EITHER, "table"), "no deciding code"


async def test_us_7_4_codes_split_end_to_end(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    role_servers: dict[ModelRole, FakeModelServer],
) -> None:
    classify_as(role_servers, DenialReason.MISSING_INFORMATION)
    case_id = await diagnosed(desktop, service, era("CAS*CO*16*250~LQ*HE*M76~"))
    remedy = (await open_case(desktop, case_id)).remedy
    assert remedy is not None
    assert (remedy.remedy, remedy.basis, remedy.codes) == (Remedy.CORRECTED_CLAIM, "codes", ["M76"])


def test_us_7_4_codes_where_they_appear() -> None:
    read = extraction(
        line(carcs=("4",), rarcs=("M51",)),
        line(carcs=(None, "97"), rarcs=(None,)),
        carcs=("31",),
        rarcs=("MA130",),
    )
    uses = [(use.line, use.code, use.shown) for use in case_code_uses(read)]
    assert uses == [
        (None, "31", "CO-31"),
        (None, "MA130", "MA130"),
        (1, "4", "CO-4"),
        (1, "M51", "M51"),
        (2, "97", "CO-97"),
    ], "unreadable codes are skipped"
    ungrouped = CaseExtraction.model_validate(
        extraction().model_dump() | {"adjustments": [adjustment("31", None)]}
    )
    assert [use.shown for use in case_code_uses(ungrouped)] == ["31"], "no group code read"


# --- Scenario: A payer's rule card overrides the table -------------------------------------------


def test_us_7_4_rule_card_overrides_the_table() -> None:
    bundled = extraction(line(carcs=("97",)))
    acme = card(remedies={"bundling": "corrected_claim"})
    advice = remedy_of(DenialReason.BUNDLING, bundled, [acme])
    assert advice == RemedyAdvice(
        remedy=Remedy.CORRECTED_CLAIM,
        basis="rule_card",
        denial_reason=DenialReason.BUNDLING,
        rule_card="ACME Health/corrected_claims",
    )
    other = remedy_of(DenialReason.CODING_ERROR, bundled, [acme])
    assert (other.remedy, other.basis) == (Remedy.CORRECTED_CLAIM, "table"), "reason not on card"
    eligibility = remedy_of(DenialReason.ELIGIBILITY, extraction(line(carcs=("31",))), [acme])
    assert eligibility.basis == "codes", "a card without the reason leaves the code split"
    with pytest.raises(ValidationError):
        RemedyAdvice(remedy=Remedy.APPEAL, basis="table", denial_reason="other", rule_card="x/y")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        RemedyAdvice(remedy=Remedy.APPEAL, basis="rule_card", denial_reason="other")  # type: ignore[arg-type]


async def test_us_7_4_rule_card_override_end_to_end(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    role_servers: dict[ModelRole, FakeModelServer],
) -> None:
    classify_as(role_servers, DenialReason.BUNDLING)
    await service.import_bundle(corrected_claims_card(remedies={"bundling": "corrected_claim"}))
    case_id = await diagnosed(desktop, service, era("CAS*CO*97*250~"))
    case = await open_case(desktop, case_id)
    assert case.remedy is not None
    assert (case.remedy.remedy, case.remedy.rule_card) == (
        Remedy.CORRECTED_CLAIM,
        "ACME Health/corrected_claims",
    )
    assert case.diagnosis is not None
    assert "ACME Health/corrected_claims" in [ref.key for ref in case.diagnosis.rule_cards]


# --- Scenario: A correctable denial gets a list of changes for human review ----------------------


async def test_us_7_4_correctable_denial_gets_a_list_of_changes(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    sent: Sent,
    role_servers: dict[ModelRole, FakeModelServer],
) -> None:
    classify_as(role_servers, DenialReason.CODING_ERROR)
    case_id = await diagnosed(desktop, service, era(CODING_ERROR))
    before = await open_case(desktop, case_id)
    assert before.remedy is not None
    assert before.remedy.remedy is Remedy.CORRECTED_CLAIM

    started = await correct(desktop, case_id)

    assert started.kind == "correct"
    case = await open_case(desktop, case_id)
    correction = case.correction
    assert correction is not None, "a corrected-claim draft is attached to the case"
    assert correction.label == DRAFT_LABEL == "draft for human review"
    assert (correction.original_claim_id, correction.frequency_code) == ("CLAIM-77", "7")
    assert [(c.line, c.field, c.current_value, c.because) for c in correction.corrections] == [
        (1, CorrectableField.MODIFIER, None, ["CO-4"]),
        (1, CorrectableField.PROCEDURE_CODE, "99213", ["CO-4", "M51"]),
    ], "each change names a line, a field, and the codes behind it"
    assert all((c.action, c.why) == (ACTION, WHY) for c in correction.corrections)
    assert case.diagnosis is not None
    assert correction.diagnosed_at == case.diagnosis.diagnosed_at
    assert correction.rule_cards == ["ACME Health/appeal_levels", "ACME Health/required_docs"]
    assert case.correction_stale is False
    events = events_of(sent, started.job_id)
    assert [(e.stage, e.progress) for e in events] == [("drafting", 0.0), ("done", 1.0)]
    actions = [entry.action for entry in service.user_store("default").audit_log(case_id)]
    assert actions[-2:] == [AuditAction.CORRECTION_DRAFTED, AuditAction.CASE_OPENED]
    wire = json.dumps([event.model_dump() for event in events])
    assert "CLAIM-77" not in wire, "events carry no case content"
    assert "99213" not in wire


async def test_us_7_4_the_prompt_holds_the_plan_as_data(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    role_servers: dict[ModelRole, FakeModelServer],
) -> None:
    classify_as(role_servers, DenialReason.CODING_ERROR)
    case_id = await diagnosed(desktop, service, era(CODING_ERROR))
    await correct(desktop, case_id)

    request = role_servers[ModelRole.DRAFTING].requests[-1]
    system, user = (str(message.content) for message in request.messages)
    assert "corrected-claim changes" in system
    assert "never which new value to enter" in user
    assert '"field": "modifier"' in user
    assert f'"current_value": "{NOT_IN_DOCUMENTS}"' in user
    assert "CLAIM-77" in user, "the case facts are data"
    assert (request.model_extra or {})["max_tokens"] == 8192
    assert CORRECTION_TEMPLATE in registered_templates()


async def test_us_7_4_correction_through_the_gateway_refusals(
    desktop: httpx.AsyncClient,
) -> None:
    await new_case(desktop)  # the profile has a case store
    bad_body = await desktop.post(f"{PREFIX}/cases/case_0000000000000000/correction", json=[])
    assert_envelope(bad_body, 422, "invalid_request")
    bad_id = await desktop.post(f"{PREFIX}/cases/not%20a%20case/correction", json={})
    assert_envelope(bad_id, 422, "invalid_request")
    bad_format = await export(desktop, "case_0000000000000000", "txt")
    assert_envelope(bad_format, 422, "invalid_request")
    bad_export_id = await desktop.post(
        f"{PREFIX}/cases/not%20a%20case/correction/export", json={"format": "pdf"}
    )
    assert_envelope(bad_export_id, 422, "invalid_request")
    missing = await export(desktop, "case_0000000000000000", "pdf")
    assert_envelope(missing, 404, "case_not_found")


# --- Scenario: Drafting needs a current diagnosis ------------------------------------------------


async def test_us_7_4_drafting_needs_a_current_diagnosis(
    desktop: httpx.AsyncClient,
) -> None:
    case_id = await new_case(desktop)
    await run_job(desktop, case_id, "process")
    worker: FastAPI = desktop.worker  # type: ignore[attr-defined]

    response = await desktop.post(f"{PREFIX}/cases/{case_id}/correction", json={})

    assert_envelope(response, 409, "not_diagnosed")
    assert worker.state.jobs.running("default", case_id) is None, "no job started"
    await run_job(desktop, case_id, "diagnose")
    confirmed = await desktop.post(
        f"{PREFIX}/cases/{case_id}/fields", json={"path": "claim_id", "value": "CLAIM-78"}
    )
    assert confirmed.status_code == 200
    stale = await desktop.post(f"{PREFIX}/cases/{case_id}/correction", json={})
    assert_envelope(stale, 409, "not_diagnosed")
    missing = await desktop.post(f"{PREFIX}/cases/case_0000000000000000/correction", json={})
    assert_envelope(missing, 404, "case_not_found")


async def test_us_7_4_a_closed_case_is_refused(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await diagnosed(desktop, service)
    await correct(desktop, case_id)
    service.user_store("default").close_case(case_id)
    refused = await desktop.post(f"{PREFIX}/cases/{case_id}/correction", json={})
    assert_envelope(refused, 409, "case_closed")
    exported = await export(desktop, case_id, "pdf")
    assert exported.status_code == 200, "a closed case still exports"


async def test_us_7_4_a_running_job_is_returned(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await diagnosed(desktop, service)
    worker: FastAPI = desktop.worker  # type: ignore[attr-defined]
    running = JobStarted(case_id=case_id, job_id="job_0123456789abcdef", kind="draft")
    worker.state.jobs.running = lambda *_args: running
    response = await desktop.post(f"{PREFIX}/cases/{case_id}/correction", json={})
    assert JobStarted.model_validate_json(response.content) == running, "one job per case"


async def test_us_7_4_a_worker_without_models_cannot_correct(service: CorpusService) -> None:
    app = create_app(TOKEN, corpus=service)
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(app))
    case = await client.create_case("default")
    with pytest.raises(WorkerRejectedError) as raised:
        await client.start_correction("default", case.case_id)
    assert raised.value.code == "model_unavailable"
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(ModelUnavailableError):
        case_routes.get_corrector(request)  # type: ignore[arg-type]


async def test_us_7_4_a_closed_case_never_loads_the_model(service: CorpusService) -> None:
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    service.user_store("default").close_case(case_id)
    asked: list[ModelRole] = []

    @asynccontextmanager
    async def models(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        asked.append(role)
        yield ModelEndpoint(role=role, base_url="http://127.0.0.1:9/v1")

    reported: list[str] = []
    with pytest.raises(CaseClosedError):
        await Corrector(cases, models).run("default", case_id, lambda s, _p: reported.append(s))
    assert (asked, reported) == ([], ["drafting"])


# --- Scenario: An unprocessable claim is resubmitted as new --------------------------------------


def test_us_7_4_unprocessable_claim_is_new() -> None:
    assert frequency_code(extraction(line(rarcs=("MA130",))), []) == "1"
    assert frequency_code(extraction(line(carcs=("4",))), []) == "7"
    assert frequency_code(extraction(line(), rarcs=("MA130",)), []) == "1", "claim-level too"
    assert frequency_code(extraction(line(rarcs=("MA130",))), [card(frequency_code="8")]) == "8"
    assert frequency_code(extraction(line()), [card(remedies={"other": "none"})]) == "7"


# --- Scenario: A value missing from the documents is never invented ------------------------------


def test_us_7_4_value_missing_from_documents_is_never_invented() -> None:
    read = extraction(line(carcs=("181",), served=None), carcs=("31",))
    planned = plan_corrections(read, diagnosis(DenialReason.ELIGIBILITY, read))
    assert planned == [
        PlannedCorrection(None, CorrectableField.MEMBER_ID, None, ("CO-31",)),
        PlannedCorrection(None, CorrectableField.PATIENT_DEMOGRAPHICS, None, ("CO-31",)),
        PlannedCorrection(1, CorrectableField.PROCEDURE_CODE, "99213", ("CO-181",)),
        PlannedCorrection(1, CorrectableField.SERVICE_DATE, None, ("CO-181",)),
    ], "the member ID is not in the documents, and the service date was unreadable"
    for bad in (
        {"field": "modifier", "line": 1, "current_value": "25"},
        {"field": "member_id", "current_value": "ABC123"},
        {"field": "procedure_code", "current_value": "99213"},  # no line
        {"field": "member_id", "line": 1},
    ):
        with pytest.raises(ValidationError):
            ClaimCorrection.model_validate({"action": ACTION, "why": WHY} | bad)


def test_us_7_4_changes_are_planned_by_fixed_rules() -> None:
    two_lines = extraction(
        line(carcs=("97", "97"), rarcs=("M53",)), line(procedure=None), carcs=("4", "22")
    )
    planned = plan_corrections(two_lines, diagnosis(DenialReason.CODING_ERROR, two_lines))
    assert [(p.line, p.field, p.current_value, p.because) for p in planned] == [
        (None, CorrectableField.OTHER_INSURANCE, None, ("CO-22",)),
        (1, CorrectableField.MODIFIER, None, ("CO-4", "CO-97")),
        (1, CorrectableField.PROCEDURE_CODE, "99213", ("CO-4",)),
        (1, CorrectableField.UNITS, None, ("M53",)),
        (2, CorrectableField.MODIFIER, None, ("CO-4",)),
        (2, CorrectableField.PROCEDURE_CODE, None, ("CO-4",)),
    ], "a claim-level code points at every line for a line field"
    no_lines = extraction(carcs=("4",))
    assert [
        (p.line, p.field)
        for p in plan_corrections(no_lines, diagnosis(DenialReason.CODING_ERROR, no_lines))
    ] == [
        (None, CorrectableField.MODIFIER),
        (None, CorrectableField.PROCEDURE_CODE),
    ], "a claim whose lines were not read gets claim-level changes"
    unmapped = extraction(line(carcs=("197",)))
    assert plan_corrections(unmapped, diagnosis(DenialReason.OTHER, unmapped, ["CO-197"])) == [
        PlannedCorrection(None, CorrectableField.CLAIM_DATA, None, ("CO-197",))
    ], "no code maps to a field: one claim-level change cites the codes"
    many = extraction(*(line() for _ in range(30)), carcs=("4",))
    assert len(plan_corrections(many, diagnosis(DenialReason.CODING_ERROR, many))) == 60
    assert all(code[0] in "0123456789ABDPWY" or code.startswith(("M", "N")) for code in CODE_FIELDS)


# --- Scenario: A reply that proposes a code is refused -------------------------------------------


@pytest.mark.parametrize(
    "action",
    [
        "Append modifier 59 to the second line.",
        "Add modifiers -25 and recheck.",
        "Bill 99214 instead of the visit code.",
        "Use HCPCS G0438 for the wellness visit.",
        "Point the line at diagnosis E11.9.",
        "Point the line at diagnosis I10.",
        # Review: phrasings the first parser let through.
        "Append modifier-59 to line 1.",
        "Add a 59 modifier.",
        "Use the -59 modifier.",
        "Add the XS modifier.",
        "Use 99213-25 instead.",
        "Bill code 99213 with mod 59.",
        'Add modifier "59".',
        "Add modifier: 59.",
        "Use modifier (25).",
        "Change the diagnosis to E119.",
        "Change diagnosis to M545.",
        "Point at J449.",
        "Add XU to the line.",
    ],
)
def test_us_7_4_reply_that_proposes_a_code_is_refused(action: str) -> None:
    read = extraction(line(carcs=("4",), rarcs=("M51",)))
    allowed = allowed_codes(read)
    assert parse_corrections(correction_reply(1, action=action), 1, allowed) is None
    assert parse_corrections(correction_reply(1, why=action), 1, allowed) is None


def test_us_7_4_a_reply_may_repeat_what_the_documents_hold() -> None:
    read = extraction(line(carcs=("4",), rarcs=("M51",)), billed="15000.00", carcs=("22",))
    allowed = allowed_codes(read)
    assert {"99213", "4", "CO-4", "M51", "CLAIM-77", "15000", "00"} <= allowed
    text = "Check the modifier on line 1 (99213, CO-4, M51); the claim billed 15000.00."
    assert parse_corrections(correction_reply(1, action=text), 1, allowed) == [(text, WHY)]
    plain = "Resubmit the X12 claim after a P2P review; check whether a modifier applies."
    assert parse_corrections(correction_reply(1, action=plain), 1, allowed) == [(plain, WHY)]
    unread = extraction(line(procedure=None), claim_id=None, billed=None)
    assert "None" not in allowed_codes(unread)


@pytest.mark.parametrize(
    "reply",
    [
        "No JSON here.",
        '{"corrections": "none"}',
        json.dumps({"corrections": [{"index": 0, "action": " ", "why": WHY}]}),
        json.dumps({"corrections": [{"index": "0", "action": ACTION, "why": WHY}]}),
        correction_reply(2),  # an index the plan does not have
        json.dumps({"corrections": [{"index": 0, "action": ACTION, "why": WHY}] * 2}),
        correction_reply(0),
    ],
)
def test_us_7_4_unusable_replies_are_refused(reply: str) -> None:
    assert parse_corrections(reply, 1, frozenset()) is None


def test_us_7_4_long_text_is_clipped() -> None:
    long = "Check the visit's documentation. " * 40
    parsed = parse_corrections(correction_reply(1, action=long, why=long), 1, frozenset())
    assert parsed is not None
    assert all(len(text) <= 500 for text in parsed[0])


async def test_us_7_4_a_refused_reply_stores_nothing(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    sent: Sent,
    role_servers: dict[ModelRole, FakeModelServer],
) -> None:
    classify_as(role_servers, DenialReason.BUNDLING)
    case_id = await diagnosed(desktop, service, era("CAS*CO*97*250~"))
    await correct(desktop, case_id)
    first = (await open_case(desktop, case_id)).correction
    assert first is not None
    drafting = role_servers[ModelRole.DRAFTING]
    drafting.responders[DEFAULT_MODEL_ID] = drafting_responder(action="Append modifier 59.")

    started = await correct(desktop, case_id)

    last = events_of(sent, started.job_id)[-1]
    assert (last.stage, last.error_code) == ("failed", "correction_failed")
    assert (await open_case(desktop, case_id)).correction == first, "the previous draft is kept"


async def test_us_7_4_a_cut_off_reply_is_named_in_the_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def cut_off(*_args: Any, **_kwargs: Any) -> ChatReply:
        return ChatReply(content='{"corrections": [{"index": 0, "action": "Check', truncated=True)

    monkeypatch.setattr(correction_module, "chat_completion", cut_off)
    endpoint = ModelEndpoint(role=ModelRole.DRAFTING, base_url="http://127.0.0.1:9/v1")
    read = extraction(line(carcs=("4",)))
    planned = plan_corrections(read, diagnosis(DenialReason.CODING_ERROR, read))
    with pytest.raises(CorrectionFailedError):
        await correction_module.draft_corrections(
            endpoint, read, diagnosis(DenialReason.CODING_ERROR, read), [], planned
        )
    assert "correction reply stopped at max_tokens" in caplog.text
    assert "Check" not in caplog.text

    async def unusable(*_args: Any, **_kwargs: Any) -> ChatReply:
        return ChatReply(content="I cannot help with that.", truncated=False)

    caplog.clear()
    monkeypatch.setattr(correction_module, "chat_completion", unusable)
    with pytest.raises(CorrectionFailedError):
        await correction_module.draft_corrections(
            endpoint, read, diagnosis(DenialReason.CODING_ERROR, read), [], planned
        )
    assert "max_tokens" not in caplog.text


# --- Scenario: A draft goes stale after re-extraction --------------------------------------------


async def test_us_7_4_draft_goes_stale_after_re_extraction(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    role_servers: dict[ModelRole, FakeModelServer],
) -> None:
    classify_as(role_servers, DenialReason.CODING_ERROR)
    case_id = await diagnosed(desktop, service, era(CODING_ERROR))
    await correct(desktop, case_id)
    assert (await open_case(desktop, case_id)).correction_stale is False

    confirmed = await desktop.post(
        f"{PREFIX}/cases/{case_id}/fields", json={"path": "claim_id", "value": "CLAIM-78"}
    )

    assert confirmed.json()["correction_stale"] is True, "the fields changed"
    # Tester: a stale draft still exports, and the file says it is out of date.
    stale_file = ExportedFile.model_validate_json((await export(desktop, case_id, "docx")).content)
    with zipfile.ZipFile(Path(stale_file.path)) as package:
        assert "OUT OF DATE: the case changed" in package.read("word/document.xml").decode()
    await run_job(desktop, case_id, "diagnose")
    rediagnosed = await open_case(desktop, case_id)
    assert rediagnosed.correction_stale is True, "the diagnosis it was drafted from is gone"
    await correct(desktop, case_id)
    assert (await open_case(desktop, case_id)).correction_stale is False, "drafted again"
    fresh = ExportedFile.model_validate_json((await export(desktop, case_id, "docx")).content)
    with zipfile.ZipFile(Path(fresh.path)) as package:
        assert "OUT OF DATE" not in package.read("word/document.xml").decode()


# --- Scenario: The label is always present -------------------------------------------------------


def test_us_7_4_label_is_always_present() -> None:
    correction = sample_correction()
    assert correction.label == "draft for human review"
    bad: dict[str, Any]
    for bad in (
        {"label": "final claim"},
        {"corrections": []},
        {"frequency_code": "2"},
        {"frequency_code": 7},
        {"rule_cards": ["x"] * (MAX_RULE_CARDS + 1)},
        {"submit_to": "clearinghouse"},
        {"drafted_at": "2026-10-31T12:05:00"},
    ):
        with pytest.raises(ValidationError):
            sample_correction(**bad)
    assert correction_text(correction).startswith("Corrected claim: draft for human review")


# --- Scenario: The corrected-claim draft exports as PDF or DOCX ----------------------------------


async def test_us_7_4_export_pdf_and_docx(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    role_servers: dict[ModelRole, FakeModelServer],
) -> None:
    classify_as(role_servers, DenialReason.CODING_ERROR)
    case_id = await diagnosed(desktop, service, era(CODING_ERROR))
    refused = await export(desktop, case_id, "pdf")
    assert_envelope(refused, 409, "not_corrected")
    await correct(desktop, case_id)

    pdf = ExportedFile.model_validate_json((await export(desktop, case_id, "pdf")).content)
    docx = ExportedFile.model_validate_json((await export(desktop, case_id, "docx")).content)

    assert pdf.filename == f"corrected-claim-draft-{case_id}.pdf"
    assert docx.filename == f"corrected-claim-draft-{case_id}.docx"
    assert Path(pdf.path).name.startswith(f"corrected-claim-draft-{case_id}-")
    with pymupdf.open(Path(pdf.path)) as document:  # type: ignore[no-untyped-call]
        # NFKC: the PDF sets "fi" as a ligature, which reads back as one character.
        pages = [unicodedata.normalize("NFKC", page.get_text(sort=True)) for page in document]
        assert document.metadata["title"] == CORRECTION_TITLE
    assert all(page.startswith(HEADER) for page in pages), "the label on every page"
    assert "Line 1, procedure code (current value: 99213)" in pages[0]
    assert f"Line 1, modifier (current value: {NOT_IN_DOCUMENTS})" in pages[0]
    with zipfile.ZipFile(Path(docx.path)) as package:
        document_xml = package.read("word/document.xml").decode()
        core = package.read("docProps/core.xml").decode()
    assert document_xml.index(HEADER) < document_xml.index("Claim frequency code: 7")
    assert CORRECTION_TITLE in core
    actions = [entry.action for entry in service.user_store("default").audit_log(case_id)]
    assert actions.count(AuditAction.CORRECTION_EXPORTED) == 2
    assert AuditAction.DRAFT_EXPORTED not in actions, "the appeal draft was not exported"


def test_us_7_4_export_text_says_what_is_missing() -> None:
    bare = sample_correction(original_claim_id=None, rule_cards=[], frequency_code="1")
    text = correction_text(bare)
    assert f"Original claim number: {NOT_IN_DOCUMENTS}" in text
    assert "Claim frequency code: 1 (a new claim)" in text
    assert "Payer rule cards on file when drafted: none on file for this payer" in text
    assert "2. Claim, member ID (current value: not in your documents)" in text
    assert "Codes: none read" in text
    for export_format in ExportFormat:
        assert render_correction(bare, export_format)
    with zipfile.ZipFile(io.BytesIO(render_correction(bare, ExportFormat.DOCX))) as package:
        assert package.testzip() is None


# --- Scenario: No submit control -----------------------------------------------------------------


def test_us_7_4_no_submit_control() -> None:
    added = {
        ("POST", "/cases/{case_id}/correction"),
        ("POST", "/cases/{case_id}/correction/export"),
    }
    assert added <= GATEWAY_ROUTES, "pinned by US-7.3"
    assert added <= WORKER_ROUTES
    assert not any(SEND.search(path) for _, path in added), "no route is named for sending"
    text = correction_text(sample_correction())
    assert "nothing here leaves this Mac" in text


# --- The corrected_claims rule card --------------------------------------------------------------


async def test_us_7_4_corrected_claims_card_imports(service: CorpusService) -> None:
    yaml_card = (
        "items:\n"
        "  - kind: rule_card\n"
        "    payer: ACME Health\n"
        "    topic: corrected_claims\n"
        "    title: ACME corrected claims\n"
        "    body: Corrected claims use frequency code 7.\n"
        "    remedies: {bundling: corrected_claim, eligibility: appeal}\n"
        "    frequency_code: 7\n"
        "    source: Synthetic manual\n"
        "    verified_on: 2026-09-15\n"
    )
    bundle = parse_bundle_bytes(yaml_card.encode(), "cards.yaml")
    await service.import_bundle(bundle)
    await service.import_bundle(RULE_BUNDLE)
    cards = payer_rule_cards(service.global_store(), "ACME HEALTH PLAN")
    stored = [c for c in cards if c.topic == "corrected_claims"]
    assert len(stored) == 1
    assert stored[0].remedies == {
        DenialReason.BUNDLING: Remedy.CORRECTED_CLAIM,
        DenialReason.ELIGIBILITY: Remedy.APPEAL,
    }
    assert stored[0].frequency_code == "7", "YAML's number 7 is the code 7"
    for misplaced in ({"remedies": {"bundling": "appeal"}}, {"frequency_code": "7"}):
        with pytest.raises(ValidationError, match="allowed only on corrected_claims"):
            RuleCard.model_validate(card().model_dump() | {"topic": "timely_filing"} | misplaced)
    with pytest.raises(ValidationError):
        card(remedies={"fraud": "appeal"})
    with pytest.raises(ValidationError):
        card(frequency_code=True)


def test_us_7_4_a_payer_has_six_rule_cards() -> None:
    refs = [
        RuleCardRef(
            key=f"ACME Health/{topic}",
            payer="ACME Health",
            topic=topic,
            source="Synthetic",
            verified_on=date(2026, 9, 15),
            stale=False,
        )
        for topic in (
            "timely_filing",
            "appeal_levels",
            "required_docs",
            "submission",
            "corrected_claims",
            "other",
        )
    ]
    read = extraction(line())
    six = diagnosis(DenialReason.OTHER, read).model_copy(update={"rule_cards": refs})
    assert len(Diagnosis.model_validate(six.model_dump()).rule_cards) == MAX_RULE_CARDS == 6
    letter = AppealDraft(
        text="Letter",
        template_id="appeal",
        rule_cards=[ref.key for ref in refs],
        extraction_digest="0" * 64,
        diagnosed_at=utc_now(),
        drafted_at=utc_now(),
    )
    assert len(letter.rule_cards) == 6


# --- The purge (BR-7) ----------------------------------------------------------------------------


async def test_us_7_4_correction_purged_with_case(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await diagnosed(desktop, service)
    await correct(desktop, case_id)
    assert (await open_case(desktop, case_id)).correction is not None
    store = service.user_store("default")
    store.close_case(case_id)
    service.purge(PurgeRequest(profile="default", case_id=case_id, confirm=True))

    case = await open_case(desktop, case_id)
    assert (case.correction, case.remedy) == (None, None)
    assert_envelope(await export(desktop, case_id, "pdf"), 409, "not_corrected")


# --- The pane names what the backend sends -------------------------------------------------------


PLUGIN_JS: Final = Path(__file__).resolve().parents[1] / "plugin" / "desktop" / "plugin.js"


def _js_object(name: str) -> dict[str, str]:
    source = PLUGIN_JS.read_text()
    start = source.index(f"export const {name} = Object.freeze({{")
    body = source[start : source.index("});", start)]
    return dict(re.findall(r"^\s+'?(\w+)'?: '([^']*)',$", body, re.MULTILINE))


def test_us_7_4_the_pane_and_the_export_name_fields_alike() -> None:
    assert _js_object("CORRECTABLE_FIELDS") == {f.value: label for f, label in FIELD_LABELS.items()}
    assert _js_object("FREQUENCY_CODES") == FREQUENCY_MEANINGS
    assert set(_js_object("REMEDIES")) == {remedy.value for remedy in Remedy}
    assert "export const NOT_IN_DOCUMENTS = 'not in your documents';" in PLUGIN_JS.read_text()
    assert NOT_IN_DOCUMENTS == "not in your documents"


async def test_us_7_4_changes_beyond_forty_are_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review: a claim-level code on a long claim lists 40 changes and says how many more."""
    many = extraction(*(line() for _ in range(30)), carcs=("4",))
    diagnosed_many = diagnosis(DenialReason.CODING_ERROR, many)
    saved: list[CorrectedClaimDraft] = []
    cases = SimpleNamespace(save_correction=lambda _p, _c, draft: saved.append(draft))

    @asynccontextmanager
    async def models(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        yield ModelEndpoint(role=role, base_url="http://127.0.0.1:9/v1")

    async def answer(*_args: Any, **_kwargs: Any) -> ChatReply:
        return ChatReply(content=correction_reply(MAX_CORRECTIONS), truncated=False)

    corrector = Corrector(cases, models)  # type: ignore[arg-type]
    monkeypatch.setattr(corrector, "_inputs", lambda *_args: (many, diagnosed_many, []))
    monkeypatch.setattr(correction_module, "chat_completion", answer)
    draft = await corrector.run("default", "case_0123456789abcdef", lambda _s, _p: None)
    assert (len(draft.corrections), draft.omitted) == (MAX_CORRECTIONS, 20)
    assert saved == [draft]
    assert "20 more change(s) are not listed" in correction_text(draft)
    assert "not listed" not in correction_text(sample_correction())


async def test_us_7_4_a_payer_with_six_cards_still_answers_the_agent(
    service: CorpusService,
) -> None:
    """Review: ``claimcoach_payer_rules`` held five cards; a corrected_claims card made six."""
    topics = ("timely_filing", "appeal_levels", "required_docs", "submission", "other")
    await service.import_bundle(CorpusBundle(items=[rule_card("ACME Health", t) for t in topics]))
    await service.import_bundle(corrected_claims_card(remedies={"bundling": "appeal"}))
    result = payer_rules(service.global_store(), "ACME HEALTH PLAN", date(2026, 11, 1))
    assert len(result.cards) == MAX_RULE_CARDS
    assert result.cards[-2].topic == "corrected_claims"
