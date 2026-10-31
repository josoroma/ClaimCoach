"""Validate ``evidence/US-x.y/test-report.md`` files against the evidence contract.

Implements: US-1.5 (evidence template contract), ES-5 (a criterion that was not exercised is
``UNVERIFIED``, never ``PASS``; each story also ships JUnit XML).

The rules mirror the required checks of OhMyOrch's ``validate-test-report`` (``Change:``,
``Story:``, ``Verdict:``, ``Coverage:``, an ``Acceptance Criteria`` section, verdict/FAIL
consistency, a ``Failures`` section when anything fails) and add ClaimCoach's stricter ones:
every row carries ``PASS``, ``FAIL``, or ``UNVERIFIED`` plus evidence, ``Coverage:`` counts the
exercised rows exactly, and the report lists the commands it ran.

Usage::

    python tools/check_evidence.py [EVIDENCE_DIR]
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

__all__ = ["Report", "Row", "main", "parse_report", "validate_junit", "validate_report"]

Result = Literal["PASS", "FAIL", "UNVERIFIED"]
RESULTS: Final[frozenset[str]] = frozenset({"PASS", "FAIL", "UNVERIFIED"})

_FIELD = re.compile(r"^(Change|Story|Verdict|Coverage):[ \t]*(.*?)[ \t]*$", re.MULTILINE)
_COVERAGE = re.compile(r"^(\d+)/(\d+)\b")
_HEADING = re.compile(r"^#{1,4}\s+(.+?)\s*$", re.MULTILINE)
_STORY_DIR = re.compile(r"^US-\d+\.\d+$")


@dataclass(frozen=True, slots=True)
class Row:
    """One evaluated acceptance criterion."""

    criterion: str
    result: str
    evidence: str


@dataclass(frozen=True, slots=True)
class Report:
    """The parts of a test report the contract checks."""

    fields: dict[str, str]
    headings: list[str]
    rows: list[Row]
    text: str


def _section(text: str, title: str) -> str:
    """Return the body of the first heading that starts with ``title`` (case-insensitive)."""
    matches = list(_HEADING.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1).lower().startswith(title.lower()):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[match.end() : end]
    return ""


def parse_report(text: str) -> Report:
    """Parse a test report.

    Args:
        text: Markdown report.

    Returns:
        The parsed report; rows come from the first table in ``Acceptance Criteria Evaluated``.
    """
    fields = {m.group(1): m.group(2) for m in _FIELD.finditer(text)}
    rows: list[Row] = []
    for line in _section(text, "Acceptance Criteria").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[2] in RESULTS:
            rows.append(Row(criterion=cells[1], result=cells[2], evidence=cells[3]))
    return Report(fields=fields, headings=_HEADING.findall(text), rows=rows, text=text)


def validate_report(text: str, *, story: str | None = None) -> list[str]:
    """Return every contract violation in ``text`` (empty when the report is valid).

    Args:
        text: Markdown report.
        story: Story the report must name, e.g. ``US-1.1``.

    Returns:
        Human-readable problems.
    """
    report = parse_report(text)
    problems = [
        f"missing '{name}:' line"
        for name in ("Change", "Story", "Verdict", "Coverage")
        if not report.fields.get(name)
    ]
    if story is not None and report.fields.get("Story") != story:
        problems.append(f"names story {report.fields.get('Story')!r}, expected {story!r}")
    if not any(h.lower().startswith("acceptance criteria") for h in report.headings):
        problems.append("no '## Acceptance Criteria Evaluated' section")
    if not report.rows:
        problems.append("lists no criterion with PASS, FAIL, or UNVERIFIED")
    problems += [
        f"row {i}: no evidence" for i, row in enumerate(report.rows, 1) if not row.evidence
    ]
    problems += [
        f"row {i}: criterion is not quoted"
        for i, row in enumerate(report.rows, 1)
        if not row.criterion.startswith('"')
    ]

    fails = sum(row.result == "FAIL" for row in report.rows)
    exercised = sum(row.result != "UNVERIFIED" for row in report.rows)
    verdict = report.fields.get("Verdict", "").lower()
    if verdict not in {"", "pass", "fail"}:
        problems.append(f"unrecognised verdict {verdict!r}")
    if verdict == "pass" and fails:
        problems.append(f"verdict is pass but {fails} criterion/criteria FAIL")
    if verdict == "fail" and not fails:
        problems.append("verdict is fail but no criterion FAILs")
    if fails and not any(h.lower().startswith("failure") for h in report.headings):
        problems.append("records FAIL but has no '## Failures' section")

    coverage = _COVERAGE.match(report.fields.get("Coverage", ""))
    if report.fields.get("Coverage") and coverage is None:
        problems.append("Coverage must read '<evaluated>/<total> ...'")
    elif coverage is not None:
        evaluated, total = int(coverage.group(1)), int(coverage.group(2))
        if (evaluated, total) != (exercised, len(report.rows)):
            problems.append(
                f"Coverage says {evaluated}/{total} but the table has "
                f"{exercised}/{len(report.rows)} exercised"
            )
        if evaluated == 0:
            problems.append("Coverage says no criterion was evaluated")

    if "```" not in _section(text, "Evidence Commands"):
        problems.append("no '## Evidence Commands' section with the commands and their output")
    return problems


def validate_junit(path: Path) -> list[str]:
    """Return problems with a JUnit XML file: missing, nothing executed, or failures recorded."""
    if not path.is_file():
        return [f"{path.name} missing"]
    root = ET.parse(path).getroot()  # noqa: S314 - our own generated file
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))

    def total(attribute: str) -> int:
        return sum(int(suite.get(attribute, "0")) for suite in suites)

    problems = []
    # Skipped tests are not evidence: an all-skipped run (e.g. Hermes absent) proves nothing.
    if total("tests") - total("skipped") <= 0:
        problems.append(f"{path.name} records no executed tests")
    bad = total("failures") + total("errors")
    if bad:
        problems.append(f"{path.name} records {bad} failure(s)/error(s)")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Validate every ``US-x.y`` evidence folder under the given directory.

    Args:
        argv: ``[EVIDENCE_DIR]``; defaults to ``evidence``.

    Returns:
        ``0`` when every report and JUnit file is valid, else ``1``.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0] if args else "evidence")
    stories = sorted(p for p in root.iterdir() if p.is_dir() and _STORY_DIR.match(p.name))
    failed = False
    for story_dir in stories:
        report = story_dir / "test-report.md"
        problems = (
            validate_report(report.read_text(encoding="utf-8"), story=story_dir.name)
            if report.is_file()
            else ["test-report.md missing"]
        ) + validate_junit(story_dir / "junit.xml")
        failed = failed or bool(problems)
        print(f"{'FAIL' if problems else 'ok  '} {story_dir.name}")
        for problem in problems:
            print(f"     - {problem}")
    if not stories:
        print(f"no US-x.y folders under {root}")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
