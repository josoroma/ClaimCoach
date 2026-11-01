"""The denial-classification eval: accuracy of the diagnosed denial reason on a labeled set.

Implements: US-12.2 scenario "Classification eval reports accuracy" (each labeled case runs
through the app from upload to diagnosis, the diagnosed ``DenialReason`` is compared with its
label, and accuracy is reported per reason and overall; the gate fails under
``CLASSIFICATION_TARGET``). Rules: NFR-1 (85%), BR-7 (each eval case is purged after its run),
BR-14 (the report holds set IDs, reasons, and error codes only).

The whole pipeline is measured, not the classifier alone: a case whose extraction fails or reads a
code wrong is misclassified, as it would be for the biller.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from claimcoach.api.models import ErrorCode
from claimcoach.cases.diagnosis import DenialReason
from claimcoach.evals.datasets import DenialEvalSet
from claimcoach.evals.flow import CaseDriver, run_case
from claimcoach.evals.types import CLASSIFICATION_TARGET, EvalResult, Score

__all__ = ["classify_set", "run_classification", "score_classification"]

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def classify_set(
    driver: CaseDriver, denial_set: DenialEvalSet
) -> tuple[dict[str, DenialReason], dict[str, ErrorCode], list[str]]:
    """Run each case to its diagnosis.

    Returns:
        The diagnosed reason per case ID, the error code per case that failed, and the worker
        case IDs of eval cases that could not be purged afterwards.
    """
    predicted: dict[str, DenialReason] = {}
    errors: dict[str, ErrorCode] = {}
    kept: list[str] = []
    for case in denial_set.cases:
        result = await run_case(driver, case, until="diagnose")
        if result.case_id is not None and not result.discarded:
            kept.append(result.case_id)
        diagnosis = result.case.diagnosis if result.case is not None else None
        if diagnosis is not None:
            predicted[case.id] = diagnosis.denial_reason
        else:
            errors[case.id] = result.error_code or "worker_error"
    return predicted, errors, kept


def score_classification(
    denial_set: DenialEvalSet,
    predicted: Mapping[str, DenialReason],
    errors: Mapping[str, ErrorCode],
    *,
    started_at: datetime,
    finished_at: datetime,
) -> EvalResult:
    """Score diagnosed reasons against the set's labels, per labeled reason and overall.

    Args:
        denial_set: The labeled set.
        predicted: Diagnosed reason per case ID.
        errors: Error code per case ID that reached no diagnosis.
        started_at: When the run began.
        finished_at: When it ended.
    """
    hits: dict[str, int] = {}
    totals: dict[str, int] = {}
    misses: list[str] = []
    for case in denial_set.cases:
        label = case.denial_reason.value
        totals[label] = totals.get(label, 0) + 1
        if predicted.get(case.id) == case.denial_reason:
            hits[label] = hits.get(label, 0) + 1
        else:
            misses.append(f"{case.id}:{label}")
    overall = Score.of(sum(hits.values()), sum(totals.values()))
    return EvalResult(
        story="US-12.2",
        eval="classification_accuracy",
        dataset=denial_set.name,
        started_at=started_at,
        finished_at=finished_at,
        metric="accuracy",
        target=CLASSIFICATION_TARGET,
        passed=overall.meets(CLASSIFICATION_TARGET),
        overall=overall,
        by_category={r: Score.of(hits.get(r, 0), totals[r]) for r in sorted(totals)},
        misses=sorted(misses),
        errors=sorted(f"{case}:{code}" for case, code in errors.items()),
    )


async def run_classification(
    driver: CaseDriver, denial_set: DenialEvalSet, *, clock: Clock = _utc_now
) -> tuple[EvalResult, list[str]]:
    """Classify ``denial_set`` through the app and score it.

    Returns:
        The result and the worker case IDs of eval cases that could not be purged.
    """
    started = clock()
    predicted, errors, kept = await classify_set(driver, denial_set)
    result = score_classification(
        denial_set, predicted, errors, started_at=started, finished_at=clock()
    )
    return result, kept
