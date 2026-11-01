"""US-9.1 Code and Payer-Rule Tools.

Scenarios: explain_code answers from the global corpus; payer_rules returns the payer's rule card.
Also: code shapes, unknown codes and payers, long reference text, schemas, handler failures, the
guard over reference text, and the worker routes. The tools are called the way Hermes calls them,
through the registered (guarded) handlers, against a live worker on loopback.
Rules: ES-1, ES-4, ES-8, BR-3, BR-14, PC-4, PC-8.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator, Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from claimcoach.agent import __main__ as agent_cli
from claimcoach.agent import tools as tools_module
from claimcoach.agent.answers import code_keys
from claimcoach.agent.types import (
    MAX_REFERENCE_CHARS,
    ExplainCodeParams,
    ExplainCodeResult,
    PayerRulesResult,
    ToolResult,
)
from claimcoach.api.client import WorkerClient, WorkerRejectedError
from claimcoach.api.models import ErrorCode, envelope
from claimcoach.corpus.bundle import CodeEntry, CorpusBundle, is_stale
from claimcoach.corpus.service import CorpusService
from claimcoach.worker.app import create_app
from tests.conftest import free_port_in_range
from tests.fakes.agent import AgentWorker, agent_worker, assert_envelope
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.diagnosis import ACME_DOCUMENTS, CODE_BUNDLE, RULE_BUNDLE
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, leaked_strings

EXPLAIN = "claimcoach_explain_code"
RULES = "claimcoach_payer_rules"
SYNTHETIC_VERIFIED = date(2026, 9, 1)
"""When ``CODE_BUNDLE``'s synthetic entries were verified."""


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
async def worker(service: CorpusService) -> AsyncIterator[AgentWorker]:
    await service.import_bundle(CODE_BUNDLE)
    await service.import_bundle(RULE_BUNDLE)
    with agent_worker(service) as live:
        yield live


# --- Scenario: explain_code answers from the global corpus ---------------------------------------


def test_us_9_1_explain_code_from_global(worker: AgentWorker) -> None:
    raw = worker.call(EXPLAIN, {"code": "CO-197"})

    assert isinstance(raw, str), "PC-8"
    result = ExplainCodeResult.model_validate_json(raw)
    assert result.code == "CO-197"
    assert [(e.code_set, e.code, e.title) for e in result.entries] == [
        ("GROUP", "CO", "Contractual obligation"),
        ("CARC", "197", "Precertification absent"),
    ]
    carc = result.entries[1]
    assert carc.explanation == "Authorization was not obtained."
    assert (carc.source, carc.verified_on) == ("Synthetic code list for tests", SYNTHETIC_VERIFIED)
    assert carc.stale is is_stale(SYNTHETIC_VERIFIED, date.today())
    assert carc.truncated is False


def test_us_9_1_explain_code_answers_a_bare_or_remark_code(worker: AgentWorker) -> None:
    remark = ExplainCodeResult.model_validate_json(worker.call(EXPLAIN, {"code": "n286"}))
    assert (remark.code, [e.code for e in remark.entries]) == ("N286", ["N286"])
    bare = ExplainCodeResult.model_validate_json(worker.call(EXPLAIN, {"code": "197"}))
    assert [(e.code_set, e.code) for e in bare.entries] == [("CARC", "197")]


@pytest.mark.parametrize(
    ("code", "keys"),
    [
        ("CO-197", ["GROUP/CO", "CARC/197"]),
        ("co-197", ["GROUP/CO", "CARC/197"]),
        ("PR-B7", ["GROUP/PR", "CARC/B7"]),
        ("OA-016", ["GROUP/OA", "CARC/016"]),
        ("197", ["CARC/197"]),
        ("N286", ["RARC/N286"]),
        ("MA130", ["RARC/MA130"]),
        ("M15", ["RARC/M15"]),
        ("CO", ["GROUP/CO"]),
        ("CO-N286", ["GROUP/CO", "RARC/N286"]),
        ("XYZ", []),
        ("1970", []),
        ("ZZ-197", []),
        ("CO-197-1", []),
        ("CO-", []),
        ("-197", []),
    ],
)
def test_us_9_1_code_shapes(code: str, keys: list[str]) -> None:
    assert code_keys(code) == keys


# --- Scenario: payer_rules returns the payer's rule card -----------------------------------------


@pytest.mark.parametrize("asked", ["ACME Health", "ACME HEALTH PLAN", "The ACME Health Plan"])
def test_us_9_1_payer_rules_returns_card(worker: AgentWorker, asked: str) -> None:
    raw = worker.call(RULES, {"payer": asked})

    result = PayerRulesResult.model_validate_json(raw)
    assert result.payer == "ACME Health", "the longest matching card payer wins (US-6.2)"
    assert [card.topic for card in result.cards] == ["appeal_levels", "required_docs"]
    required = result.cards[1]
    assert required.required_documents == list(ACME_DOCUMENTS)
    assert (required.source, required.stale) == ("ACME Health provider manual (synthetic)", False)
    assert required.verified_on == date.today() - timedelta(days=30)
    if asked != "ACME Health":
        assert asked.casefold() not in raw.casefold(), "the asked name is never echoed"


# --- Unknown codes and payers --------------------------------------------------------------------


@pytest.mark.parametrize("code", ["CO-999", "999", "N999", "XYZ", "CR"])
def test_us_9_1_unknown_code_is_not_found(worker: AgentWorker, code: str) -> None:
    raw = worker.call(EXPLAIN, {"code": code})
    assert_envelope(raw, "code_not_found")


def test_us_9_1_unknown_payer_is_not_found(worker: AgentWorker) -> None:
    raw = worker.call(RULES, {"payer": "Harborline Health Plan"})
    assert_envelope(raw, "payer_not_found")
    assert "Harborline" not in raw


async def test_us_9_1_a_reason_code_without_its_group_entry(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    """``PI-18`` with no ``GROUP/PI`` entry is answered with the ``CARC/18`` entry alone."""
    service = make_service(tmp_path / "hermes", corpus_server)
    await service.import_bundle(CODE_BUNDLE)
    try:
        with agent_worker(service) as worker:
            result = ExplainCodeResult.model_validate_json(worker.call(EXPLAIN, {"code": "PI-18"}))
    finally:
        service.close()
    assert result.code == "PI-18"
    assert [(e.code_set, e.code) for e in result.entries] == [("CARC", "18")]


# --- Reference text: cut to fit one redaction call, and guarded -------------------------------


def _entry(code: str, body: str) -> CodeEntry:
    return CodeEntry.model_validate(
        {
            "kind": "code",
            "code_set": "CARC",
            "code": code,
            "title": f"Synthetic {code}",
            "body": body,
            "source": "Synthetic code list for tests",
            "verified_on": date.today() - timedelta(days=400),
        }
    )


@pytest.mark.parametrize(
    ("stored", "asked"), [("016", "16"), ("016", "CO-016"), ("16", "016"), ("7", "007")]
)
async def test_us_9_1_zero_padded_codes_are_one_code(
    tmp_path: Path, corpus_server: FakeModelServer, stored: str, asked: str
) -> None:
    """Review finding: an entry imported as ``016`` is found as ``16``, and the other way round."""
    service = make_service(tmp_path / "hermes", corpus_server)
    await service.import_bundle(CorpusBundle(items=[_entry(stored, "Claim lacks information.")]))
    try:
        with agent_worker(service) as worker:
            raw = worker.call(EXPLAIN, {"code": asked})
    finally:
        service.close()
    entries = ExplainCodeResult.model_validate_json(raw).entries
    assert [(e.code_set, e.code) for e in entries] == [("CARC", stored)]


async def test_us_9_1_long_reference_text_is_cut(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    service = make_service(tmp_path / "hermes", corpus_server)
    await service.import_bundle(CorpusBundle(items=[_entry("45", "Charge exceeds fee. " * 500)]))
    try:
        with agent_worker(service) as worker:
            raw = worker.call(EXPLAIN, {"code": "45"})
    finally:
        service.close()
    (entry,) = ExplainCodeResult.model_validate_json(raw).entries
    assert len(entry.explanation) == MAX_REFERENCE_CHARS
    assert entry.truncated is True
    assert entry.stale is True, "verified 400 days ago"


async def test_us_9_1_reference_text_is_guarded(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    """A code entry someone wrote a patient into is redacted by the handler's guard (BR-3)."""
    document = PHI_DOCUMENTS[0]
    service = make_service(tmp_path / "hermes", corpus_server)
    await service.import_bundle(CorpusBundle(items=[_entry("27", document["text"])]))
    try:
        with agent_worker(service) as worker:
            raw = worker.call(EXPLAIN, {"code": "27"})
    finally:
        service.close()
    assert leaked_strings(raw, document) == []
    assert "[NAME]" in ExplainCodeResult.model_validate_json(raw).entries[0].explanation


# --- Schemas and handlers --------------------------------------------------------------------


def test_us_9_1_schemas_from_params() -> None:
    by_name = {tool.name: tool for tool in tools_module.TOOLS}
    assert by_name[EXPLAIN].params is ExplainCodeParams
    assert by_name[EXPLAIN].result is ExplainCodeResult
    assert by_name[RULES].result is PayerRulesResult
    for tool in tools_module.TOOLS:
        schema = tool.schema()
        assert schema["parameters"] == tool.params.model_json_schema()
        assert schema["parameters"]["additionalProperties"] is False
        assert issubclass(tool.result, ToolResult)
        assert tool.result.model_fields["ok"].default is True


@pytest.mark.parametrize(
    "args", [{}, {"code": ""}, {"code": "CO 197"}, {"code": "CO-197", "patient": "x"}, {"code": 7}]
)
def test_us_9_1_bad_arguments_are_invalid_requests(worker: AgentWorker, args: Any) -> None:
    raw = worker.call(EXPLAIN, args)
    assert_envelope(raw, "invalid_request")


def test_us_9_1_handler_failures_are_envelopes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker that is down, refuses, or is too slow: a fixed envelope, never an exception."""
    tool = tools_module.TOOLS[0]
    down = WorkerClient(f"http://127.0.0.1:{free_port_in_range(18214)}", lambda: TOKEN, timeout=2)
    assert_envelope(tool.handle({"code": "CO-197"}, connect=lambda: down), "worker_unavailable")

    async def refused(_client: WorkerClient, _params: Any) -> ToolResult:
        raise WorkerRejectedError("code_not_found")

    async def slow(_client: WorkerClient, _params: Any) -> ToolResult:
        await asyncio.sleep(5)
        raise AssertionError("not reached")

    monkeypatch.setattr(tools_module, "TOOL_TIMEOUT", 0.2)
    failures: list[tuple[Any, ErrorCode]] = [
        (refused, "code_not_found"),
        (slow, "worker_unavailable"),
    ]
    for call, code in failures:
        spec = tools_module.ToolSpec(tool.name, tool.description, tool.params, tool.result, call)
        assert_envelope(spec.handle({"code": "CO-197"}, connect=lambda: down), code)


def test_us_9_1_handlers_are_bound_at_registration(worker: AgentWorker) -> None:
    """Every registered tool is the guarded handler of its ``ToolSpec`` (US-3.2)."""
    for tool in tools_module.TOOLS:
        assert worker.registrar.tools[tool.name]["handler"].__claimcoach_guarded__ is True


# --- Worker routes ---------------------------------------------------------------------------


@pytest.fixture
async def asgi(service: CorpusService) -> AsyncIterator[httpx.AsyncClient]:
    await service.import_bundle(CODE_BUNDLE)
    await service.import_bundle(RULE_BUNDLE)
    transport = httpx.ASGITransport(app=create_app(TOKEN, corpus=service))
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as client:
        yield client


async def test_us_9_1_tools_through_the_worker(asgi: httpx.AsyncClient) -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    explained = await asgi.post("/agent/explain-code", json={"code": "CO-197"}, headers=headers)
    assert explained.status_code == 200
    ExplainCodeResult.model_validate_json(explained.content)
    cards = await asgi.post("/agent/rule-cards", json={"payer": "ACME Health"}, headers=headers)
    assert PayerRulesResult.model_validate_json(cards.content).payer == "ACME Health"

    cases: list[tuple[str, Mapping[str, Any], int, ErrorCode]] = [
        ("/agent/explain-code", {"code": "CO-999"}, 404, "code_not_found"),
        ("/agent/rule-cards", {"payer": "Nobody Mutual"}, 404, "payer_not_found"),
        ("/agent/explain-code", {"code": "CO-197", "ssn": "123-45-6789"}, 422, "invalid_request"),
        ("/agent/rule-cards", {"payer": "x" * 121}, 422, "invalid_request"),
    ]
    for path, body, status, code in cases:
        response = await asgi.post(path, json=body, headers=headers)
        assert response.status_code == status, path
        assert response.json() == envelope(code).model_dump(), path
        assert "123-45-6789" not in response.text
    unauthorized = await asgi.post("/agent/explain-code", json={"code": "CO-197"})
    assert unauthorized.status_code == 401


# --- Operator CLI: python -m claimcoach.agent (make agent-tools, make agent-call) ----------------


def test_us_9_1_cli_lists_the_tools_offline() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "claimcoach.agent", "tools"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    lines = completed.stdout.splitlines()
    assert [line.split()[0] for line in lines if line.startswith("claimcoach_")] == [
        tool.name for tool in tools_module.TOOLS
    ]
    assert "skill: claimcoach:denial-triage" in completed.stdout
    assert "command: /denial [case ID]" in completed.stdout


def test_us_9_1_cli_calls_a_tool_as_the_agent_does(worker: AgentWorker) -> None:
    lines: list[str] = []
    argv = ["call", EXPLAIN, "--args", '{"code": "CO-197"}', "--port", "18219"]
    assert agent_cli.main(argv, out=lines.append, connect=lambda _port: worker.connect()) == 0
    assert ExplainCodeResult.model_validate_json(lines[0]).code == "CO-197"

    lines.clear()
    argv = ["call", EXPLAIN, "--args", '{"code": "CO-999"}']
    assert agent_cli.main(argv, out=lines.append, connect=lambda _port: worker.connect()) == 1
    assert json.loads(lines[0])["error"]["code"] == "code_not_found"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("Avery Vandermeer", "error: --args is not JSON"),
        ('["CO-197"]', "error: --args is not a JSON object"),
    ],
)
def test_us_9_1_cli_refuses_bad_args_without_echoing(raw: str, message: str) -> None:
    lines: list[str] = []
    assert agent_cli.main(["call", EXPLAIN, "--args", raw], out=lines.append) == 2
    assert lines == [message]


def test_us_9_1_cli_ports_stay_in_range(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        agent_cli.main(["call", EXPLAIN, "--port", "8080"])
    assert "not a ClaimCoach port" in capsys.readouterr().err
