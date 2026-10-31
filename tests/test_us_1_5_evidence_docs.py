"""US-1.5 Evidence Template, Runbook Skeletons, and ADR-0001.

Scenarios: evidence template follows the OhMyOrch report contract; required runbooks exist with
the four sections; ADR-0001 records the worker decision. Rules: ES-5, ES-6, ES-9.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT
from tools import check_evidence

TEMPLATE = REPO_ROOT / "evidence" / "TEMPLATE" / "test-report.md"
OHMYORCH = Path(
    os.environ.get("OHMYORCH_BIN", Path.home() / "sites/OhMyOrch/plugins/ohmyorch/bin/ohmyorch")
)
RUNBOOKS = (
    "install-enable",
    "worker-start-stop-health",
    "model-download-convert",
    "corpus-import-reindex-backup-restore",
    "upgrade",
    "troubleshooting",
    "phi-purge",
    "phi-incident",
    "phi-redaction",
    "case-intake-extraction",
    "case-diagnosis",
)
SECTIONS = ("Preconditions", "Steps", "Verification", "Rollback")

FILLED = {
    "<US-x.y>": "US-1.5",
    "<story title>": "Evidence Template",
    "<change-id>": "us-1-5-evidence-runbooks-adr",
    "<pass | fail>": "pass",
    "<evaluated>/<total>": "1/2",
    "<YYYY-MM-DD>": "2026-10-30",
    '"<Scenario name>: <Then clause>"': '"Scenario: Runbooks exist: Then each has four headings"',
    "<PASS/FAIL/UNVERIFIED>": "PASS",
    "<test id or command>": "pytest tests/test_us_1_5_evidence_docs.py",
    "<observed output>": "1 passed",
}
UNVERIFIED_ROW = (
    '| 2 | "Scenario: Other: Then not exercised" | UNVERIFIED | not run: needs Hermes |\n'
)


def render_template(**overrides: str) -> str:
    text = TEMPLATE.read_text()
    for placeholder, value in {**FILLED, **overrides}.items():
        text = text.replace(placeholder, value)
    marker = "| 1 | "
    row_end = text.index("\n", text.index(marker)) + 1
    return text[:row_end] + UNVERIFIED_ROW + text[row_end:]


# --- Scenario: Evidence template follows the OhMyOrch report contract --------------------------


def test_us_1_5_evidence_template_contract() -> None:
    raw = TEMPLATE.read_text()
    for required in (
        "Change:",
        "Story:",
        "Verdict:",
        "Coverage:",
        "## Acceptance Criteria Evaluated",
        "## Evidence Commands",
        "## Failures",
        "UNVERIFIED",
    ):
        assert required in raw
    assert check_evidence.validate_report(render_template(), story="US-1.5") == []


def test_us_1_5_reports_pass_ohmyorch_validator(tmp_path: Path) -> None:
    if not OHMYORCH.exists():
        pytest.skip(f"OhMyOrch not installed at {OHMYORCH}")
    # Delivered reports are checked by `make evidence-check`, which also runs this validator.
    report = tmp_path / "rendered.md"
    report.write_text(render_template())
    result = subprocess.run(
        [
            "bash",
            str(OHMYORCH),
            "--project-root",
            str(REPO_ROOT),
            "validate-test-report",
            "--report",
            str(report),
            "--story",
            "US-1.5",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "RESULT: PASS" in result.stdout


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"<PASS/FAIL/UNVERIFIED>": "FAIL"}, "verdict is pass but 1"),
        ({"<pass | fail>": "fail"}, "verdict is fail but no criterion FAILs"),
        ({"<pass | fail>": "maybe"}, "unrecognised verdict"),
        ({"<evaluated>/<total>": "2/2"}, "Coverage says 2/2 but the table has 1/2"),
        ({"<evaluated>/<total>": "all"}, "Coverage must read"),
        ({"<US-x.y>": "US-9.9"}, "expected 'US-1.5'"),
        ({'"<Scenario name>: <Then clause>"': "unquoted"}, "row 1: criterion is not quoted"),
        ({"<test id or command>": "", "<observed output>": "", "`` → ": ""}, "row 1: no evidence"),
    ],
)
def test_us_1_5_validator_rejects_broken_reports(overrides: dict[str, str], problem: str) -> None:
    problems = check_evidence.validate_report(render_template(**overrides), story="US-1.5")
    assert any(problem in p for p in problems), problems


def test_us_1_5_validator_requires_failures_section_and_commands() -> None:
    text = render_template(**{"<PASS/FAIL/UNVERIFIED>": "FAIL", "<pass | fail>": "fail"})
    text = text.replace("## Failures", "## Problems").replace("```", "")
    problems = check_evidence.validate_report(text)
    assert "records FAIL but has no '## Failures' section" in problems
    assert any("Evidence Commands" in p for p in problems)


def test_us_1_5_validator_rejects_empty_report() -> None:
    problems = check_evidence.validate_report("# nothing here\n")
    assert "missing 'Change:' line" in problems
    assert "no '## Acceptance Criteria Evaluated' section" in problems
    assert "lists no criterion with PASS, FAIL, or UNVERIFIED" in problems


def test_us_1_5_validator_rejects_zero_coverage() -> None:
    text = render_template(**{"<PASS/FAIL/UNVERIFIED>": "UNVERIFIED", "<evaluated>/<total>": "0/2"})
    assert "Coverage says no criterion was evaluated" in check_evidence.validate_report(text)


JUNIT_OK = '<testsuites><testsuite name="s" tests="3" failures="0" errors="0"/></testsuites>'


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        (None, "junit.xml missing"),
        ('<testsuite name="s" tests="0" failures="0" errors="0"/>', "records no executed tests"),
        ('<testsuite name="s" tests="4" skipped="4"/>', "records no executed tests"),
        ('<testsuite name="s" tests="2" failures="1" errors="1"/>', "records 2 failure(s)"),
    ],
)
def test_us_1_5_junit_validation(tmp_path: Path, content: str | None, problem: str) -> None:
    path = tmp_path / "junit.xml"
    if content is not None:
        path.write_text(content)
    assert any(problem in p for p in check_evidence.validate_junit(path))


def test_us_1_5_evidence_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert check_evidence.main([str(tmp_path)]) == 1
    assert "no US-x.y folders" in capsys.readouterr().out

    good = tmp_path / "US-1.5"
    good.mkdir()
    (good / "test-report.md").write_text(render_template())
    (good / "junit.xml").write_text(JUNIT_OK)
    (tmp_path / "TEMPLATE").mkdir()
    assert check_evidence.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "ok   US-1.5"

    (tmp_path / "US-1.6").mkdir()
    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.setattr("sys.argv", ["check_evidence.py", tmp_path.name])
    assert check_evidence.main() == 1
    out = capsys.readouterr().out
    assert "FAIL US-1.6" in out
    assert "test-report.md missing" in out


# --- Scenario: Required runbooks exist with the four sections ----------------------------------


@pytest.mark.parametrize("name", RUNBOOKS)
def test_us_1_5_runbooks_have_sections(name: str) -> None:
    path = REPO_ROOT / "docs" / "runbooks" / f"{name}.md"
    assert path.is_file(), f"missing runbook {path.name}"
    headings = re.findall(r"^## (.+?)\s*$", path.read_text(), re.MULTILINE)
    assert [h for h in headings if h in SECTIONS] == list(SECTIONS), headings


# --- Scenario: ADR-0001 records the worker decision --------------------------------------------


def test_us_1_5_adr_0001_present() -> None:
    adr = (REPO_ROOT / "docs" / "adr" / "0001-worker-sidecar.md").read_text()
    assert re.search(r"^- Status: Accepted$", adr, re.MULTILINE)
    for section in ("Context", "Decision", "Consequences"):
        assert re.search(rf"^## {section}$", adr, re.MULTILINE), section
    for fact in ("~/Models/.venvs/claimcoach", "127.0.0.1:18200", "token_urlsafe", "0600", "§7.9"):
        assert fact in adr, fact
