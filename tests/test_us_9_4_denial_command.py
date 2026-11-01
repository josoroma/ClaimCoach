"""US-9.4 The /denial Slash Command.

Scenario: /denial returns text without PHI. Also: /denial with a case ID summarizes the case
through the guarded case-summary handler, arguments are never echoed, failures are fixed
messages, and the real Hermes dispatch runs it.
Rules: ES-4, BR-2, BR-3, BR-14, PRD §7 (slash command /denial).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from claimcoach.agent import __main__ as agent_cli
from claimcoach.agent.commands import COMMAND_NAME, USAGE, denial_command, render_summary
from claimcoach.agent.types import CaseSummaryResult
from claimcoach.api.models import ERROR_MESSAGES, envelope
from claimcoach.cases.diagnosis import AppealLikelihood, DenialReason
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import CaseOutcome
from claimcoach.models.types import ModelRole
from claimcoach.redact.validators import find_regex_spans
from tests.fakes.agent import (
    AgentWorker,
    agent_worker,
    diagnosed_case,
    pipeline_models,
    serve_pipeline,
)
from tests.fakes.corpus import make_service
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, leaked_strings, seeded_strings
from tests.test_us_9_3_skill import probe_agent

DOCUMENT = PHI_DOCUMENTS[0]


@pytest.fixture(scope="module")
def role_servers() -> Iterator[dict[ModelRole, FakeModelServer]]:
    with serve_pipeline() as servers:
        yield servers


@pytest.fixture
def models(role_servers: dict[ModelRole, FakeModelServer]) -> Any:
    return pipeline_models(role_servers)


@pytest.fixture
def service(
    tmp_path: Path, corpus_server: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[CorpusService]:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def worker(service: CorpusService) -> Iterator[AgentWorker]:
    with agent_worker(service) as live:
        yield live


def assert_phi_free(text: str) -> None:
    assert leaked_strings(text, *PHI_DOCUMENTS) == []
    assert find_regex_spans(text) == []


# --- Scenario: /denial returns text without PHI ---------------------------------------------------


def test_us_9_4_denial_returns_text_without_phi(worker: AgentWorker) -> None:
    reply = worker.run(COMMAND_NAME)
    assert reply == USAGE
    assert isinstance(reply, str)
    assert "ClaimCoach pane" in reply
    assert "/denial <case ID>" in reply
    assert_phi_free(reply)


def test_us_9_4_command_registered(worker: AgentWorker) -> None:
    entry = worker.registrar.commands[COMMAND_NAME]
    assert entry["args_hint"] == "[case ID]"
    assert "no PHI" in entry["description"]


@pytest.mark.hermes
def test_us_9_4_real_hermes_command(hermes_python: Path, tmp_path: Path) -> None:
    """Hermes v0.22.5 ``invoke_plugin_command`` runs ``/denial``; no worker runs in that home."""
    probe = probe_agent(hermes_python, tmp_path, DOCUMENT["phi"]["member_id"][0])
    assert probe["denial"] == USAGE
    assert probe["denial_case"] == ERROR_MESSAGES["worker_unavailable"]
    assert_phi_free(json.dumps(probe["denial_case"]))


# --- /denial <case ID> ---------------------------------------------------------------------


async def test_us_9_4_denial_summarizes_a_case(
    service: CorpusService, models: Any, worker: AgentWorker
) -> None:
    member_id = DOCUMENT["phi"]["member_id"][0]
    case_id = await diagnosed_case(
        service, models, DOCUMENT["text"], confirm={"claim_id": member_id}
    )

    reply = worker.run(COMMAND_NAME, f"  {case_id}  ")

    assert reply.splitlines()[0] == f"ClaimCoach case {case_id}: open, diagnosed"
    assert "Payer: ACME Health" in reply
    assert "Codes: CO-197, N286" in reply
    assert "Denial reason: prior_authorization; appeal likelihood: high" in reply
    assert "Next: Draft the appeal in the pane." in reply
    assert list(seeded_strings(DOCUMENT)), "the fixture seeds PHI"
    assert_phi_free(reply.replace(case_id, ""))
    for case_text in ("CLAIM-77", "PCN-0001", "SYNTHETIC", "ACME HEALTH PLAN", "2026-09-01"):
        assert case_text not in reply, case_text


@pytest.mark.parametrize(
    "raw_args", ["Avery Vandermeer", "SSN 133-94-1993", "case 01", "x" * 65, DOCUMENT["text"]]
)
def test_us_9_4_arguments_are_never_echoed(worker: AgentWorker, raw_args: str) -> None:
    reply = worker.run(COMMAND_NAME, raw_args)
    assert reply == USAGE


def test_us_9_4_unknown_case_is_a_fixed_message(worker: AgentWorker) -> None:
    """A word that looks like a case ID (a surname) is looked up, not echoed."""
    assert worker.run(COMMAND_NAME, "Vandermeer") == ERROR_MESSAGES["case_not_found"]


def summarizer(result: str) -> Any:
    def summarize(_args: Mapping[str, Any], **_context: Any) -> str:
        return result

    return summarize


def test_us_9_4_failures_are_fixed_messages(caplog: pytest.LogCaptureFixture) -> None:
    for code in ("case_not_found", "redaction_failed", "worker_unavailable"):
        reply = denial_command(summarizer(envelope(code).model_dump_json()))("case_01")
        assert reply == ERROR_MESSAGES[code]
    # Redaction turned a field into something the summary type refuses: show none of it.
    redacted = json.dumps({"ok": True, "case_id": "case_01", "status": "[NAME]"})
    assert denial_command(summarizer(redacted))("case_01") == ERROR_MESSAGES["redaction_failed"]

    def explode(_args: Mapping[str, Any], **_context: Any) -> str:
        raise RuntimeError(DOCUMENT["text"])

    assert denial_command(explode)("case_01") == ERROR_MESSAGES["internal_error"]
    assert "RuntimeError" in caplog.text
    assert leaked_strings(caplog.text, DOCUMENT) == []


def test_us_9_4_render_summary_variants() -> None:
    closed = CaseSummaryResult(
        case_id="case_01",
        status="closed",
        stage="diagnosed",
        outcome=CaseOutcome.OVERTURNED,
        codes=[],
        denial_reason=DenialReason.TIMELY_FILING,
        appeal_likelihood=AppealLikelihood.LOW,
        diagnosis_stale=True,
        deadline="no_rule_card",
        documents=1,
        needs_confirmation=2,
    )
    assert render_summary(closed).splitlines() == [
        "ClaimCoach case case_01: closed, diagnosed",
        "Payer: no rule card matches the payer",
        "Codes: none read yet",
        "Denial reason: timely_filing; appeal likelihood: low (diagnosis out of date: diagnose "
        "again)",
        "Appeal deadline: unknown: no rule card for this payer",
        "Documents: 1; fields to confirm: 2",
        "Outcome: overturned",
    ]
    new = CaseSummaryResult(
        case_id="case_02", status="open", stage="intake", documents=0, needs_confirmation=0
    )
    assert render_summary(new).splitlines()[-1] == (
        "Next: Process the case in the ClaimCoach pane to extract its fields."
    )
    assert "Denial reason" not in render_summary(new)
    assert "Appeal deadline" not in render_summary(new)


def test_us_9_4_cli_runs_denial(worker: AgentWorker) -> None:
    lines: list[str] = []
    connect = lambda _port: worker.connect()  # noqa: E731
    assert agent_cli.main(["denial"], out=lines.append, connect=connect) == 0
    assert lines == [USAGE]
    lines.clear()
    assert (
        agent_cli.main(["denial", "case_01", "--port", "18219"], out=lines.append, connect=connect)
        == 0
    )
    assert lines == [ERROR_MESSAGES["case_not_found"]]
