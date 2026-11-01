"""The upload-to-draft latency benchmark on this Mac.

Implements: US-12.3 (each benchmark case runs through the app from its first upload to an
appeal-ready draft; the ``LatencyReport`` holds every case's time and step times and the median;
the gate fails when the median exceeds ``LATENCY_TARGET_SECONDS``). Rules: NFR-3 (median ≤ 10 min
on the M3 Pro), BR-12 (cases run one after another, as a biller works, so the memory guard loads
models in sequence), BR-7 (each eval case is purged after its run), BR-14 (times, kinds, and error
codes only).

A case that fails counts as slower than every other (design decision 2), so a failure can raise
the median but never lower it; the gate also fails unless every case finished.
"""

from __future__ import annotations

import math
import statistics
import time
from collections.abc import Callable
from datetime import UTC, datetime

from claimcoach.evals.datasets import DenialCase, DenialEvalSet
from claimcoach.evals.flow import CaseDriver, run_case
from claimcoach.evals.types import LATENCY_TARGET_SECONDS, CaseTiming, LatencyReport

__all__ = ["benchmark_cases", "median_seconds", "run_latency"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def benchmark_cases(denial_set: DenialEvalSet, limit: int | None = None) -> list[DenialCase]:
    """Pick ``limit`` cases (all by default), alternating document kinds so each mix is timed.

    Cases are taken round-robin by their first document's kind, in set order.
    """
    by_kind: dict[str, list[DenialCase]] = {}
    for case in denial_set.cases:
        by_kind.setdefault(case.documents[0].kind, []).append(case)
    queues = list(by_kind.values())
    picked: list[DenialCase] = []
    while any(queues):
        for queue in queues:
            if queue:
                picked.append(queue.pop(0))
    return picked[:limit] if limit is not None else picked


def median_seconds(timings: list[CaseTiming]) -> float | None:
    """The median upload-to-draft seconds; failed cases count as infinitely slow.

    Returns:
        The median, or ``None`` when failures make it unbounded.
    """
    median = statistics.median(
        math.inf if timing.seconds is None else timing.seconds for timing in timings
    )
    return None if math.isinf(median) else median


async def run_latency(
    driver: CaseDriver,
    denial_set: DenialEvalSet,
    *,
    limit: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall: Callable[[], datetime] = _utc_now,
) -> tuple[LatencyReport, list[str]]:
    """Time each benchmark case from upload to draft.

    Args:
        driver: How to reach the app.
        denial_set: The benchmark set.
        limit: How many cases to run (all by default).
        clock: Monotonic seconds (tests).
        wall: The current UTC time (tests).

    Returns:
        The report and the worker case IDs of eval cases that could not be purged.
    """
    started = wall()
    timings: list[CaseTiming] = []
    kept: list[str] = []
    for case in benchmark_cases(denial_set, limit):
        result = await run_case(driver, case, until="draft", clock=clock)
        if result.case_id is not None and not result.discarded:
            kept.append(result.case_id)
        timings.append(
            CaseTiming(
                case=case.id,
                kinds=case.kinds,
                seconds=result.seconds,
                stages=result.stages,
                error_code=result.error_code,
            )
        )
    median = median_seconds(timings)
    finished = all(timing.seconds is not None for timing in timings)
    report = LatencyReport(
        dataset=denial_set.name,
        started_at=started,
        finished_at=wall(),
        target_seconds=LATENCY_TARGET_SECONDS,
        median_seconds=median,
        passed=finished and median is not None and median <= LATENCY_TARGET_SECONDS,
        cases=timings,
    )
    return report, kept
