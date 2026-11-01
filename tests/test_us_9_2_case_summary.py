"""US-9.2 Redacted Case Summary Tool.

Scenarios: the summary accepts only a case ID; the summary is redacted. Also: stages and status,
the printed payer name never returned, the audit entry, another profile's case, and the worker
route. The tool is called the way Hermes calls it, through the registered (guarded) handler,
against a live worker on loopback.
Rules: ES-1, ES-4, BR-3, BR-5, BR-14, PC-4, PC-8, PRD §7.2.
"""

from __future__ import annotations

import contextvars
import sys
import types
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from claimcoach.agent.answers import case_summary
from claimcoach.agent.tools import CASE_SUMMARY
from claimcoach.agent.types import CaseSummaryParams, CaseSummaryResult
from claimcoach.cases.diagnosis import AppealLikelihood, DenialReason
from claimcoach.cases.extraction import FieldConfirmation
from claimcoach.cases.service import CaseService
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, CaseOutcome
from claimcoach.letters.draft import Drafter
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.extract import Extractor
from claimcoach.worker.app import create_app
from tests.fakes.agent import (
    AgentWorker,
    agent_worker,
    assert_envelope,
    diagnosed_case,
    pipeline_models,
    serve_pipeline,
)
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.diagnosis import CODE_BUNDLE, RULE_BUNDLE, role_models
from tests.fakes.drafting import TEMPLATE_BUNDLE, letter_reply
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, leaked_strings, seeded_strings
from tests.test_us_5_1_case_intake import ERA_835

SUMMARY = "claimcoach_case_summary"
DOCUMENT = PHI_DOCUMENTS[0]
CASE_TEXT = ("CLAIM-77", "PCN-0001", "SYNTHETIC", "ACME HEALTH PLAN", "2026-09-01", "250", "99213")
"""The synthetic 835's claim numbers, names, dates, amount, and procedure: none is summarized."""


@pytest.fixture(scope="module")
def role_servers() -> Iterator[dict[ModelRole, FakeModelServer]]:
    with serve_pipeline() as servers:
        yield servers


@pytest.fixture
def models(role_servers: dict[ModelRole, FakeModelServer]) -> Any:
    return pipeline_models(role_servers)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The Hermes root; ``HERMES_HOME`` points at it, so the active profile is ``default``."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    return tmp_path / "hermes"


@pytest.fixture
def service(root: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(root, corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def worker(service: CorpusService) -> Iterator[AgentWorker]:
    with agent_worker(service) as live:
        yield live


# --- Scenario: Summary accepts only a case ID ----------------------------------------------------


def test_us_9_2_summary_accepts_only_case_id() -> None:
    parameters = CASE_SUMMARY.schema()["parameters"]
    assert set(parameters["properties"]) == {"case_id"}
    assert parameters["required"] == ["case_id"]
    assert parameters["additionalProperties"] is False
    assert parameters["properties"]["case_id"]["pattern"] == r"^[A-Za-z0-9_-]{1,64}$"
    assert set(CaseSummaryParams.model_fields) == {"case_id"}


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"case_id": "case_01", "text": DOCUMENT["text"]},
        {"case_id": "Avery Vandermeer"},
        {"case_id": "case_01", "profile": "other"},
        {"case_id": "x" * 65},
    ],
)
def test_us_9_2_anything_but_a_case_id_is_refused(worker: AgentWorker, args: Any) -> None:
    raw = worker.call(SUMMARY, args)
    assert_envelope(raw, "invalid_request")
    assert leaked_strings(raw, DOCUMENT) == []


# --- Scenario: Summary is redacted ----------------------------------------------------------------


async def test_us_9_2_summary_redacted(
    service: CorpusService, models: Any, worker: AgentWorker
) -> None:
    member_id = DOCUMENT["phi"]["member_id"][0]
    case_id = await diagnosed_case(
        service, models, DOCUMENT["text"], confirm={"claim_id": member_id}
    )

    raw = worker.call(SUMMARY, {"case_id": case_id})

    summary = CaseSummaryResult.model_validate_json(raw)
    assert summary.case_id == case_id
    assert (summary.status, summary.stage) == ("open", "diagnosed")
    assert summary.codes == ["CO-197", "N286"]
    assert summary.payer == "ACME Health"
    assert summary.denial_reason is DenialReason.PRIOR_AUTHORIZATION
    assert summary.appeal_likelihood is AppealLikelihood.HIGH
    assert summary.diagnosis_stale is False
    assert summary.deadline == "no_appeal_limit", "ACME's synthetic appeal card gives no limit"
    assert summary.documents == 2
    assert list(seeded_strings(DOCUMENT)), "the fixture seeds PHI"
    assert leaked_strings(raw, DOCUMENT) == []
    content = raw.replace(case_id, "")  # a random hex ID may hold "250"
    for case_text in CASE_TEXT:
        assert case_text not in content, case_text


async def test_us_9_2_printed_payer_never_returned(
    service: CorpusService, models: Any, worker: AgentWorker
) -> None:
    """A payer field misread as the patient's name matches no rule card: the payer is null."""
    name = DOCUMENT["phi"]["name"][0]
    case_id = await diagnosed_case(service, models, DOCUMENT["text"], confirm={"payer_name": name})

    raw = worker.call(SUMMARY, {"case_id": case_id})

    summary = CaseSummaryResult.model_validate_json(raw)
    assert summary.payer is None
    assert summary.deadline == "no_rule_card"
    assert leaked_strings(raw, DOCUMENT) == []


# --- Stages, status, audit, profiles --------------------------------------------------------------


async def test_us_9_2_summary_stages(service: CorpusService, models: Any) -> None:
    await service.import_bundle(CODE_BUNDLE)
    await service.import_bundle(RULE_BUNDLE)
    cases = CaseService(service)
    case_id = cases.create("default").case_id

    new = case_summary(cases, "default", case_id)
    assert (new.status, new.stage, new.documents, new.codes, new.payer) == (
        "open",
        "intake",
        0,
        [],
        None,
    )
    assert (new.deadline, new.denial_reason, new.diagnosis_stale) == (None, None, False)

    cases.add_text("default", case_id, ERA_835)
    await Extractor(cases, models).run("default", case_id, lambda _s, _p: None)
    extracted = case_summary(cases, "default", case_id)
    assert (extracted.stage, extracted.codes, extracted.payer) == (
        "extracted",
        ["CO-197", "N286"],
        "ACME Health",
    )
    assert extracted.needs_confirmation == len(
        cases.extraction(cases.store("default"), case_id).needs_confirmation()  # type: ignore[union-attr]
    )

    cases.record_outcome("default", case_id, CaseOutcome.WRITTEN_OFF)
    closed = case_summary(cases, "default", case_id)
    assert (closed.status, closed.outcome) == ("closed", CaseOutcome.WRITTEN_OFF)


async def test_us_9_2_a_drafted_case(service: CorpusService, models: Any) -> None:
    case_id = await diagnosed_case(service, models, "Denial notice: see the remittance.")
    await service.import_bundle(TEMPLATE_BUNDLE)
    cases = CaseService(service)
    with FakeModelServer(replies={DEFAULT_MODEL_ID: letter_reply()}) as drafting:
        drafter = Drafter(cases, role_models({ModelRole.DRAFTING: drafting.base_url}))
        await drafter.run("default", case_id, lambda _s, _p: None)
    assert case_summary(cases, "default", case_id).stage == "drafted"


async def test_us_9_2_summary_is_audited(
    service: CorpusService, models: Any, worker: AgentWorker
) -> None:
    case_id = await diagnosed_case(service, models, DOCUMENT["text"])
    worker.call(SUMMARY, {"case_id": case_id})
    worker.call(SUMMARY, {"case_id": case_id})
    actions = [entry.action for entry in service.audit("default", case_id).entries]
    assert actions.count(AuditAction.CASE_SUMMARIZED) == 2
    assert AuditAction.CASE_OPENED not in actions, "a summary is its own kind of access"


async def test_us_9_2_other_profiles_case_not_found(
    service: CorpusService, models: Any, worker: AgentWorker
) -> None:
    """The handler asks for the active profile's case only (BR-5)."""
    other = await diagnosed_case(service, models, DOCUMENT["text"], profile="clinic2")
    # "default" has no user scope yet: still case_not_found (review finding), never another code.
    assert_envelope(worker.call(SUMMARY, {"case_id": other}), "case_not_found")
    await diagnosed_case(service, models, "Denial notice.")  # now "default" has a user scope
    assert_envelope(worker.call(SUMMARY, {"case_id": other}), "case_not_found")
    actions = [entry.action for entry in service.audit("clinic2", other).entries]
    assert AuditAction.CASE_SUMMARIZED not in actions


# --- Worker route ---------------------------------------------------------------------------------


@pytest.fixture
async def asgi(service: CorpusService) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(TOKEN, corpus=service))
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as client:
        yield client


async def test_us_9_2_summary_through_the_worker(
    service: CorpusService, models: Any, asgi: httpx.AsyncClient
) -> None:
    case_id = await diagnosed_case(service, models, DOCUMENT["text"])
    headers = {"Authorization": f"Bearer {TOKEN}"}
    ok = await asgi.post(
        "/agent/case-summary?profile=default", json={"case_id": case_id}, headers=headers
    )
    assert CaseSummaryResult.model_validate_json(ok.content).case_id == case_id
    missing = await asgi.post(
        "/agent/case-summary", json={"case_id": "case_ffffffffffffffff"}, headers=headers
    )
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "case_not_found")
    bad = await asgi.post(
        "/agent/case-summary?profile=../x", json={"case_id": case_id}, headers=headers
    )
    assert (bad.status_code, bad.json()["error"]["code"]) == (422, "invalid_request")
    confirmed = FieldConfirmation(path="claim_id", value="CLAIM-78")
    CaseService(service).confirm_field("default", case_id, confirmed)
    stale = await asgi.post(
        "/agent/case-summary?profile=default", json={"case_id": case_id}, headers=headers
    )
    assert CaseSummaryResult.model_validate_json(stale.content).diagnosis_stale is True


async def test_us_9_2_the_sessions_profile_reaches_the_worker(
    service: CorpusService,
    models: Any,
    worker: AgentWorker,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review finding: Hermes names a session's profile in a context variable, not the env.

    Hermes v0.22.5 ``get_hermes_home()`` reads the context-local ``_HERMES_HOME_OVERRIDE`` that the
    Desktop gateway sets per session. The handler's worker call runs on its own thread, so the
    caller's context must travel with it; otherwise the launch profile's case is summarized.
    """
    override: contextvars.ContextVar[str | None] = contextvars.ContextVar("hermes_home_override")
    constants = types.ModuleType("hermes_constants")
    constants.get_default_hermes_root = lambda: str(root)  # type: ignore[attr-defined]
    constants.get_hermes_home = lambda: override.get(None) or str(root)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)
    launch_case = await diagnosed_case(service, models, DOCUMENT["text"])  # profile "default"
    alice_case = await diagnosed_case(service, models, "Denial notice.", profile="alice")

    token = override.set(str(root / "profiles" / "alice"))
    try:
        mine = worker.call(SUMMARY, {"case_id": alice_case})
        theirs = worker.call(SUMMARY, {"case_id": launch_case})
    finally:
        override.reset(token)

    assert CaseSummaryResult.model_validate_json(mine).case_id == alice_case
    assert_envelope(theirs, "case_not_found")
    actions = [entry.action for entry in service.audit("default", launch_case).entries]
    assert AuditAction.CASE_SUMMARIZED not in actions
    alice = service.audit("alice", alice_case).entries
    assert [(e.action, e.profile) for e in alice if e.action is AuditAction.CASE_SUMMARIZED] == [
        (AuditAction.CASE_SUMMARIZED, "alice")
    ]
