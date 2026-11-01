"""US-12.1 Redaction Recall Release Gate.

Scenarios: the gate passes at or above target; the gate blocks below target. Also: recall exactly
at the target, documents the worker could not redact, whole-word leak matching, a report that
names no PHI value, the report file, and the runs that measure nothing (no worker, an unreadable
set). The real-model gate runs under the ``models`` marker against the running worker.
Rules: ES-4, ES-5, NFR-4, BR-14.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claimcoach.api.client import WorkerClient
from claimcoach.evals import datasets
from claimcoach.evals.__main__ import main
from claimcoach.evals.datasets import (
    PRD_CATEGORIES,
    EvalSetError,
    PhiEvalDocument,
    PhiEvalSet,
    load_phi_set,
)
from claimcoach.evals.redaction_recall import leaks, score_redaction
from claimcoach.evals.types import RECALL_TARGET, EvalResult, Score, exit_code
from claimcoach.redact.types import PhiCategory
from tests.fakes.evals import connect_to, eval_worker, running_worker_port
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, fake_phi_reply, seeded_strings
from tests.fixtures.phi.generate import FIXTURE_PATH

SEVEN = {c.value for c in PhiCategory} - {"other"}
REPORT = Path("US-12.1") / "redaction-recall.json"


def run_gate(tmp_path: Path, corpus_server: FakeModelServer, phi_reply: str) -> tuple[int, str]:
    lines: list[str] = []
    with eval_worker(tmp_path / "hermes", corpus_server, phi_reply=phi_reply) as worker:
        argv = ["redaction", "--set", str(FIXTURE_PATH), "--out", str(tmp_path / "evidence")]
        code = main(argv, out=lines.append, connect=connect_to(worker))
    return code, "\n".join(lines)


def read_report(tmp_path: Path) -> EvalResult:
    return EvalResult.model_validate_json((tmp_path / "evidence" / REPORT).read_text())


# --- Scenario: Gate passes at or above target ----------------------------------------------------


def test_us_12_1_gate_passes_at_target(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    phi_set = load_phi_set(FIXTURE_PATH)
    assert {c for d in phi_set.documents for c in d.phi} == SEVEN  # the seven PRD categories

    code, printed = run_gate(tmp_path, corpus_server, fake_phi_reply(*PHI_DOCUMENTS))

    assert code == 0
    report = read_report(tmp_path)
    assert report.passed
    assert report.overall.value >= RECALL_TARGET
    assert (report.story, report.eval, report.metric) == ("US-12.1", "redaction_recall", "recall")
    assert set(report.by_category) == SEVEN
    assert report.dataset == "phi_set"
    units = sum(len(set(v)) for d in phi_set.documents for v in d.phi.values())
    assert report.overall.total == units
    assert "PASS" in printed.splitlines()[0]
    assert str(tmp_path / "evidence" / REPORT) in printed


def one_category_set(count: int) -> PhiEvalSet:
    """``count`` documents with one MRN each; built without the seven-category check (a boundary
    needs one category)."""
    documents = [
        PhiEvalDocument.model_validate(
            {"id": f"d{i}", "kind": "note", "text": f"MRN {i:07d}", "phi": {"mrn": [f"{i:07d}"]}}
        )
        for i in range(count)
    ]
    return PhiEvalSet.model_construct(name="boundary", documents=documents)


def test_us_12_1_recall_exactly_at_target_passes() -> None:
    # 50 values, 49 redacted: 0.98 is "98% or higher".
    phi_set = one_category_set(50)
    redacted = {f"d{i}": "MRN [MRN]" for i in range(49)} | {"d49": "MRN 0000049"}
    now = datetime.now(UTC)
    report = score_redaction(phi_set, redacted, {}, started_at=now, finished_at=now)
    assert report.overall.value == 0.98
    assert report.passed
    assert exit_code(report.passed) == 0
    assert report.misses == ["d49:mrn"]


def test_us_12_1_recall_just_below_target_blocks_though_it_rounds_to_it() -> None:
    # Review finding: 440/449 = 0.97996 displays as 0.98 but is below the target.
    phi_set = one_category_set(449)
    redacted = {f"d{i}": "MRN [MRN]" for i in range(440)}
    now = datetime.now(UTC)
    report = score_redaction(phi_set, redacted, {}, started_at=now, finished_at=now)
    assert report.overall.value == 0.98
    assert not report.passed
    assert not Score.of(0, 0).meets(0.5)


def test_us_12_1_a_partly_redacted_value_is_a_miss() -> None:
    # Review finding: "[ADDRESS], Port Ellery, OR 80210" still leaks the town and the ZIP.
    document = PhiEvalDocument.model_validate(
        {
            "id": "letter",
            "kind": "denial_letter",
            "text": "Mail it or fax it to 2247 Juniper Hollow Road, Port Ellery, OR 80210. "
            "Call (950) 555-0157.",
            "phi": {
                "address": ["2247 Juniper Hollow Road, Port Ellery, OR 80210"],
                "phone": ["(950) 555-0157"],
            },
        }
    )
    phi_set = PhiEvalSet.model_construct(name="partial", documents=[document])
    now = datetime.now(UTC)

    def score(text: str) -> list[str]:
        return score_redaction(
            phi_set, {"letter": text}, {}, started_at=now, finished_at=now
        ).misses

    assert score("Mail it or fax it to [ADDRESS]. Call [PHONE].") == []  # "or" is prose
    assert score("Mail it or fax it to [ADDRESS], Port Ellery, OR 80210. Call [PHONE].") == [
        "letter:address"
    ]
    assert score("Mail it or fax it to [ADDRESS]. Call (950) [PHONE].") == ["letter:phone"]


def test_us_12_1_seeds_must_occur_and_cover_every_category(tmp_path: Path) -> None:
    # Review finding: a seed the text lacks would count as redacted; a set without SSN would pass.
    documents = json.loads(FIXTURE_PATH.read_text())
    typo = [dict(d) for d in documents]
    typo[0] = typo[0] | {"phi": typo[0]["phi"] | {"ssn": ["999-99-9999"]}}
    no_ssn = [d | {"phi": {k: v for k, v in d["phi"].items() if k != "ssn"}} for d in documents]
    for name, content in (("typo", typo), ("no_ssn", no_ssn)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(content))
        with pytest.raises(EvalSetError):
            load_phi_set(path)
    assert {PhiCategory(c) for c in SEVEN} == PRD_CATEGORIES


# --- Scenario: Gate blocks below target ----------------------------------------------------------


def test_us_12_1_gate_blocks_below_target(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    # A PHI model that finds nothing: the regex validators still catch the structured categories,
    # but names and addresses stay.
    code, printed = run_gate(tmp_path, corpus_server, '{"spans": []}')

    assert code != 0
    report = read_report(tmp_path)
    assert not report.passed
    assert report.overall.value < RECALL_TARGET
    assert report.by_category["name"].value < RECALL_TARGET
    assert report.by_category["address"].value < RECALL_TARGET
    assert report.by_category["ssn"].value == 1.0
    lines = printed.splitlines()
    assert "BLOCKED" in lines[0]
    for category in SEVEN:  # recall per PHI category, on the terminal too
        assert any(line.split()[:1] == [category] for line in lines[1:]), category
    assert any(line.startswith("  missed ") and line.endswith(":name") for line in lines)


def test_us_12_1_unredactable_documents_miss_every_value(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    code, printed = run_gate(tmp_path, corpus_server, "I cannot help with that.")
    assert code == 1
    report = read_report(tmp_path)
    assert report.overall.hits == 0
    assert report.errors == sorted(f"{d['id']}:worker_error" for d in PHI_DOCUMENTS)
    assert "  error  " in printed


def test_us_12_1_report_names_no_phi_value(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    run_gate(tmp_path, corpus_server, '{"spans": []}')
    text = (tmp_path / "evidence" / REPORT).read_text()
    for value in seeded_strings(*PHI_DOCUMENTS):
        assert not leaks(value, text), "the report must name categories, never values"


def test_us_12_1_leaks_whole_words_only() -> None:
    assert leaks("Li", "Patient LI, J")
    assert not leaks("Li", "listed in the claim")
    assert leaks("(950) 555-0157", "call (950) 555-0157 today")
    assert not leaks("9979369", "MRN [MRN]")


def test_us_12_1_report_is_replaced_whole(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    run_gate(tmp_path, corpus_server, '{"spans": []}')
    run_gate(tmp_path, corpus_server, fake_phi_reply(*PHI_DOCUMENTS))
    folder = tmp_path / "evidence" / "US-12.1"
    assert [p.name for p in folder.iterdir()] == ["redaction-recall.json"]
    assert read_report(tmp_path).passed
    assert json.loads((folder / "redaction-recall.json").read_text())["story"] == "US-12.1"


# --- Nothing measured ----------------------------------------------------------------------------


def test_us_12_1_no_worker_is_not_measured(tmp_path: Path) -> None:
    lines: list[str] = []
    client = WorkerClient("http://127.0.0.1:18219", lambda: None)
    argv = ["redaction", "--set", str(FIXTURE_PATH), "--out", str(tmp_path), "--port", "18219"]
    assert main(argv, out=lines.append, connect=lambda _port: client) == 2
    assert lines == ["not measured: the worker on port 18219 answered worker_unavailable"]
    assert not (tmp_path / "US-12.1").exists()


@pytest.mark.parametrize("content", [None, b"not json", b'[{"id": "x"}]', b"[]"])
def test_us_12_1_unreadable_set_is_not_measured(tmp_path: Path, content: bytes | None) -> None:
    path = tmp_path / "set.json"
    if content is not None:
        path.write_bytes(content + b"\n# 123-45-6789")
    lines: list[str] = []
    argv = ["redaction", "--set", str(path), "--out", str(tmp_path)]
    assert main(argv, out=lines.append) == 2
    assert lines == [f"not measured: eval set {path} is missing or not a valid eval set"]


def test_us_12_1_oversized_set_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(datasets, "MAX_SET_BYTES", 10)
    path = tmp_path / "set.json"
    path.write_text("[" + " " * 20 + "]")
    with pytest.raises(EvalSetError):
        load_phi_set(path)


def test_us_12_1_port_outside_the_range_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["redaction", "--set", "x.json", "--port", "8080"])
    assert exited.value.code == 2
    assert "not a ClaimCoach port" in capsys.readouterr().err


# --- Real models ---------------------------------------------------------------------------------


@pytest.mark.models
def test_us_12_1_gate_on_real_models(tmp_path: Path) -> None:
    port = running_worker_port()
    lines: list[str] = []
    argv = ["redaction", "--set", str(FIXTURE_PATH), "--out", str(tmp_path), "--port", str(port)]
    code = main(argv, out=lines.append)
    report = EvalResult.model_validate_json((tmp_path / REPORT).read_text())
    assert code == exit_code(report.passed), lines
    assert report.passed, "\n".join(lines)
