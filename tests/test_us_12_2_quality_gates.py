"""US-12.2 Classification and Draft-Quality Gates.

Scenario: the classification eval reports accuracy. Also: the gate at and above target, cases
that reach no diagnosis, the purge of every eval case, ``--limit``, the labeled set (reproducible,
each label signaled by its code), and the draft-acceptance rubric and gate. The real-model run is
under the ``models`` marker against the running worker.
Rules: ES-4, ES-5, NFR-1, NFR-2, BR-7, BR-14.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from claimcoach.cases.diagnosis import REASON_GUIDE, DenialReason
from claimcoach.evals import __main__ as evals_main
from claimcoach.evals.__main__ import main
from claimcoach.evals.datasets import DenialEvalSet, DraftReviewSet, load_denial_set
from claimcoach.evals.draft_acceptance import (
    MINOR_EDIT_SIMILARITY,
    UNLABELED,
    score_drafts,
    similarity,
)
from claimcoach.evals.types import CLASSIFICATION_TARGET, DRAFT_ACCEPTANCE_TARGET, EvalResult
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.types import ModelRole
from tests.fakes.drafting import LETTER
from tests.fakes.evals import (
    DENIAL_SET,
    EvalWorker,
    connect_to,
    eval_worker,
    running_worker_port,
    subset,
)
from tests.fakes.fake_model_server import FakeModelServer
from tests.fixtures.denials.generate import CODES, FIXTURE_PATH, generate

REPORT = Path("US-12.2") / "classification-accuracy.json"


def write_set(tmp_path: Path, denial_set: DenialEvalSet) -> Path:
    path = tmp_path / "denials.json"
    path.write_text(denial_set.model_dump_json())
    return path


def classify(
    tmp_path: Path, worker: EvalWorker, denial_set: DenialEvalSet, *extra: str
) -> tuple[int, list[str], EvalResult]:
    lines: list[str] = []
    argv = ["classification", "--set", str(write_set(tmp_path, denial_set))]
    argv += ["--out", str(tmp_path / "evidence"), *extra]
    code = main(argv, out=lines.append, connect=connect_to(worker))
    report = EvalResult.model_validate_json((tmp_path / "evidence" / REPORT).read_text())
    return code, lines, report


@pytest.fixture
def worker(
    tmp_path: Path, corpus_server: FakeModelServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[EvalWorker]:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    with eval_worker(tmp_path / "hermes", corpus_server) as served:
        yield served


# --- Scenario: Classification eval reports accuracy ----------------------------------------------


def test_us_12_2_classification_eval_reports_accuracy(tmp_path: Path, worker: EvalWorker) -> None:
    # The fake vision model reads every EOB PDF as CO-197, so only the PDF cases labeled
    # prior_authorization are right: 15 of 20, under the 85% target.
    code, lines, report = classify(tmp_path, worker, DENIAL_SET)

    assert code != 0
    assert (report.metric, report.target) == ("accuracy", CLASSIFICATION_TARGET)
    assert report.overall.value == 0.75
    assert (report.overall.hits, report.overall.total) == (15, 20)
    assert not report.passed
    assert set(report.by_category) == {r.value for r in CODES}
    assert len(report.misses) == 5
    assert all(miss.split(":")[0] in {c.id for c in DENIAL_SET.cases} for miss in report.misses)
    assert lines[0].startswith("US-12.2 classification_accuracy: accuracy 0.7500 (15/20)")
    assert "BLOCKED" in lines[0]


def test_us_12_2_classification_passes_at_target(tmp_path: Path, worker: EvalWorker) -> None:
    readable = subset(DENIAL_SET, "era_835", "letter")
    code, lines, report = classify(tmp_path, worker, readable)
    assert code == 0
    assert report.passed
    assert report.overall.value == 1.0
    assert report.overall.total == len(readable.cases) == 14
    assert "PASS" in lines[0]


def test_us_12_2_cases_without_a_diagnosis_are_misses(tmp_path: Path, worker: EvalWorker) -> None:
    classifier = worker.servers[ModelRole.CLASSIFICATION]
    classifier.responders.clear()
    classifier.replies[DEFAULT_MODEL_ID] = "not a classification"
    two = DENIAL_SET.model_copy(update={"cases": DENIAL_SET.cases[:2]})
    code, lines, report = classify(tmp_path, worker, two)
    assert code == 1
    assert report.overall.hits == 0
    assert report.errors == ["denial_001:diagnosis_failed", "denial_002:diagnosis_failed"]
    assert "  error  denial_001:diagnosis_failed" in lines


def test_us_12_2_every_eval_case_is_purged(tmp_path: Path, worker: EvalWorker) -> None:
    classify(tmp_path, worker, DENIAL_SET, "--limit", "3", "--profile", "default")
    cases = asyncio.run(worker.client().list_cases("default")).cases
    assert len(cases) == 3
    for listed in cases:
        case = asyncio.run(worker.client().get_case("default", listed.case_id))
        assert case.documents == []
        assert case.diagnosis is None


def test_us_12_2_limit_runs_the_first_cases(tmp_path: Path, worker: EvalWorker) -> None:
    _code, _lines, report = classify(tmp_path, worker, DENIAL_SET, "--limit", "4")
    assert report.overall.total == 4
    assert set(report.by_category) == {"eligibility", "prior_authorization"}


@pytest.mark.parametrize("limit", ["0", "-1", "two"])
def test_us_12_2_limit_must_be_positive(limit: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["classification", "--set", "x.json", "--limit", limit])
    assert "must be a whole number of 1 or more" in capsys.readouterr().err


def test_us_12_2_unpurgeable_cases_are_reported(
    tmp_path: Path, worker: EvalWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    from claimcoach.evals import flow  # noqa: PLC0415 - patched for this test only

    async def failing_discard(_self: flow.WorkerDriver, _case_id: str) -> None:
        raise flow.FlowError("corpus_unavailable")

    monkeypatch.setattr(flow.WorkerDriver, "discard", failing_discard)
    _code, lines, _report = classify(tmp_path, worker, DENIAL_SET, "--limit", "2")
    warnings = [line for line in lines if line.startswith("warning: ")]
    assert len(warnings) == 2
    for line in warnings:  # review finding: name the case and the profile to purge
        case_id = line.split()[3]
        assert case_id.startswith("case_")
        assert line.endswith(f"make corpus-purge PROFILE=default CASE={case_id} CONFIRM=yes")


def test_us_12_2_unexpected_failure_names_its_type_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review finding: an unexpected error must not print its text (it may hold case content).
    async def boom(*_args: object) -> object:
        raise RuntimeError("Patient Avery Vandermeer, DOB 07/05/1954")

    monkeypatch.setattr(evals_main, "run_classification", boom)
    monkeypatch.setattr(evals_main._Run, "client", boom)
    lines: list[str] = []
    argv = ["classification", "--set", str(FIXTURE_PATH), "--out", str(tmp_path)]
    assert main(argv, out=lines.append) == 2
    assert lines == ["not measured: unexpected RuntimeError"]


# --- The labeled set -----------------------------------------------------------------------------


def test_us_12_2_denial_set_is_reproducible() -> None:
    assert generate() == load_denial_set(FIXTURE_PATH)


def test_us_12_2_each_label_is_signaled_by_its_code() -> None:
    kinds: set[str] = set()
    for case in DENIAL_SET.cases:
        (document,) = case.documents
        kinds.add(document.kind)
        codes = {carc for _group, carc in CODES[case.denial_reason]}
        assert any(code in document.text for code in codes), case.id
        guide = set(re.findall(r"\d+", REASON_GUIDE[case.denial_reason]))
        assert codes <= guide, case.id
    assert kinds == {"era_835", "letter", "eob_pdf"}
    assert DenialReason.OTHER not in {c.denial_reason for c in DENIAL_SET.cases}
    assert "SYNTHETIC" in DENIAL_SET.cases[0].documents[0].text


# --- Draft acceptance ----------------------------------------------------------------------------


def reviews(*pairs: tuple[str, str], reason: DenialReason | None = None) -> DraftReviewSet:
    return DraftReviewSet.model_validate(
        {
            "name": "manager-review",
            "provenance": "synthetic",
            "reviews": [
                {"id": f"r{i}", "denial_reason": reason, "draft": d, "final": f}
                for i, (d, f) in enumerate(pairs)
            ],
        }
    )


MINOR = LETTER.replace("To the appeals reviewer:", "Dear appeals reviewer,")
MAJOR = "We write to ask you to reconsider. Please call our office."


def test_us_12_2_similarity_of_letters() -> None:
    assert similarity(LETTER, LETTER) == 1.0
    assert similarity(LETTER, LETTER.upper().replace("\n", "\n\n  ")) == 1.0
    assert similarity(LETTER, MINOR) >= MINOR_EDIT_SIMILARITY
    assert similarity(LETTER, MAJOR) < 0.2
    assert similarity(" ", ".") == 0.0
    assert similarity(" ", "  ") == 1.0


def test_us_12_2_rubric_counts_cuts_and_additions() -> None:
    # Review finding: the symmetric ratio passed a draft with its last quarter cut.
    words = [f"w{n}" for n in range(400)]
    draft = " ".join(words)
    cut = " ".join(words[:300])  # 75% of the draft kept
    padded = " ".join(words + [f"x{n}" for n in range(144)])  # 36% more text
    reworded = " ".join(words[:200] + ["changed"] * 20 + words[220:])
    assert similarity(draft, cut) == 0.75
    assert similarity(draft, padded) < MINOR_EDIT_SIMILARITY
    assert similarity(draft, reworded) == 0.95


def test_us_12_2_draft_acceptance_gate(tmp_path: Path) -> None:
    accepted = reviews(*[(LETTER, MINOR)] * 7, *[(LETTER, MAJOR)] * 3)
    path = tmp_path / "reviews.json"
    path.write_text(accepted.model_dump_json())
    lines: list[str] = []
    argv = ["drafts", "--reviews", str(path), "--out", str(tmp_path)]
    assert main(argv, out=lines.append) == 0  # 70% exactly
    report = EvalResult.model_validate_json(
        (tmp_path / "US-12.2" / "draft-acceptance.json").read_text()
    )
    assert (report.eval, report.metric) == ("draft_acceptance", "acceptance_rate")
    assert report.overall.value == DRAFT_ACCEPTANCE_TARGET
    assert report.by_category == {UNLABELED: report.overall}
    assert report.misses == ["r7:unlabeled", "r8:unlabeled", "r9:unlabeled"]
    assert "CLAIM-77" not in (tmp_path / "US-12.2" / "draft-acceptance.json").read_text()

    path.write_text(reviews(*[(LETTER, MINOR)] * 6, *[(LETTER, MAJOR)] * 4).model_dump_json())
    assert main(argv, out=lines.append) == 1


def test_us_12_2_draft_reviews_group_by_reason() -> None:
    report = score_drafts(reviews((LETTER, MINOR), reason=DenialReason.PRIOR_AUTHORIZATION))
    assert list(report.by_category) == ["prior_authorization"]
    assert report.passed


def test_us_12_2_review_file_is_strict(tmp_path: Path) -> None:
    path = tmp_path / "reviews.json"
    path.write_text(json.dumps({"name": "x", "provenance": "y", "reviews": [], "extra": 1}))
    lines: list[str] = []
    assert main(["drafts", "--reviews", str(path)], out=lines.append) == 2
    assert lines[0].startswith("not measured: eval set")


# --- Real models ---------------------------------------------------------------------------------


@pytest.mark.models
def test_us_12_2_classification_on_real_models(tmp_path: Path) -> None:
    port = running_worker_port()
    lines: list[str] = []
    argv = ["classification", "--set", str(FIXTURE_PATH), "--out", str(tmp_path)]
    code = main([*argv, "--port", str(port)], out=lines.append)
    report = EvalResult.model_validate_json((tmp_path / REPORT).read_text())
    assert code == (0 if report.passed else 1), lines
    assert report.overall.total == len(DENIAL_SET.cases)
    assert report.passed, "\n".join(lines)  # the 85% gate, as the other real-model tests


def test_us_12_2_unreadable_denial_set_is_not_measured(tmp_path: Path) -> None:
    path = tmp_path / "denials.json"
    path.write_text(json.dumps({"name": "x", "provenance": "y", "cases": []}))
    lines: list[str] = []
    for command in ("classification", "latency", "egress"):
        assert main([command, "--set", str(path)], out=lines.append) == 2
    assert lines == [f"not measured: eval set {path} is missing or not a valid eval set"] * 3


def test_us_12_2_drafts_run_as_a_module(tmp_path: Path) -> None:
    path = tmp_path / "reviews.json"
    path.write_text(reviews((LETTER, MINOR)).model_dump_json())
    argv = ["drafts", "--reviews", str(path), "--out", str(tmp_path)]
    done = subprocess.run(
        [sys.executable, "-m", "claimcoach.evals", *argv],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ | {"PYTHONPATH": "plugin"},
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("US-12.2 draft_acceptance: acceptance_rate 1.0000 (1/1)")
