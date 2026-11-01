"""Write eval reports to the evidence folder and summarize them for the terminal.

Implements: US-12.1 ("writes the eval JSON to evidence/US-12.1/"; "reports recall per PHI
category"), US-12.2 to US-12.4 (the same for their reports). Rules: ES-5 (eval JSON beside the
test report), BR-14 (a summary repeats what the report holds: IDs, categories, numbers, codes).

A report is written to a temporary file and renamed over the old one, so a run that dies midway
never leaves half a JSON file in the evidence folder.
"""

from __future__ import annotations

import os
from pathlib import Path

from claimcoach.evals.types import EgressReport, EvalResult, LatencyReport

__all__ = ["summarize", "write_report"]

Report = EvalResult | LatencyReport | EgressReport


def write_report(report: Report, out: Path, filename: str) -> Path:
    """Write ``report`` as ``<out>/<story>/<filename>`` and return that path.

    Args:
        report: The typed report.
        out: The evidence root (``evidence/``).
        filename: The report's file name, e.g. ``redaction-recall.json``.
    """
    folder = out / report.story
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    tmp = target.with_name(f".{filename}.{os.getpid()}.tmp")
    try:
        tmp.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


def _verdict(passed: bool) -> str:
    return "PASS" if passed else "BLOCKED"


def summarize(report: Report) -> list[str]:
    """The report as terminal lines: the verdict first, then what it rests on."""
    if isinstance(report, EvalResult):
        lines = [
            f"{report.story} {report.eval}: {report.metric} {report.overall.value:.4f} "
            f"({report.overall.hits}/{report.overall.total}), target {report.target:.2f}: "
            f"{_verdict(report.passed)}"
        ]
        lines += [
            f"  {name:<26} {score.value:.4f} ({score.hits}/{score.total})"
            for name, score in report.by_category.items()
        ]
        lines += [f"  missed {miss}" for miss in report.misses]
        lines += [f"  error  {error}" for error in report.errors]
        return lines
    if isinstance(report, LatencyReport):
        median = "unbounded" if report.median_seconds is None else f"{report.median_seconds:.1f} s"
        lines = [
            f"{report.story} latency: median {median} over {len(report.cases)} cases, "
            f"target {report.target_seconds:.0f} s: {_verdict(report.passed)}"
        ]
        for timing in report.cases:
            took = f"{timing.seconds:.1f} s" if timing.seconds is not None else timing.error_code
            lines.append(f"  {timing.case:<16} {'+'.join(timing.kinds):<22} {took}")
        return lines
    lines = [
        f"{report.story} egress: flow {'completed' if report.flow_completed else 'stopped'}"
        f"{f' ({report.error_code})' if report.error_code else ''}, {report.samples} samples of "
        f"{', '.join(report.processes)}, {len(report.findings)} non-loopback: "
        f"{_verdict(report.passed)}"
    ]
    lines += [
        f"  {f.source} {f.process}:{f.pid} {f.event} {f.host}"
        f"{f':{f.port}' if f.port is not None else ''}"
        for f in report.findings
    ]
    return lines
