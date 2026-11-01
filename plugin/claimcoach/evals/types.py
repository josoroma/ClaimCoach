"""Typed eval reports, their targets, and the gate's exit codes.

Implements: US-12.1 and US-12.2 (``EvalResult`` with per-category ``Score``s), US-12.3
(``LatencyReport``, ``CaseTiming``), US-12.4 (``EgressReport``, ``EgressFinding``). Rules: ES-1,
ES-5 (eval JSON is evidence), BR-14 (a report names eval-set IDs, categories, codes, and numbers,
never a PHI value, a document, or a letter), NFR-1 to NFR-5 (the targets).
"""

from __future__ import annotations

from datetime import datetime
from fractions import Fraction
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from claimcoach.api.models import ErrorCode
from claimcoach.egress import EgressEvent

__all__ = [
    "CLASSIFICATION_TARGET",
    "DRAFT_ACCEPTANCE_TARGET",
    "EXIT_BELOW_TARGET",
    "EXIT_NOT_MEASURED",
    "EXIT_PASSED",
    "LATENCY_TARGET_SECONDS",
    "RECALL_TARGET",
    "CaseTiming",
    "EgressFinding",
    "EgressReport",
    "EvalName",
    "EvalResult",
    "LatencyReport",
    "Score",
    "StageSeconds",
    "exit_code",
]

RECALL_TARGET: Final = 0.98
"""NFR-4: redactor PHI recall on the synthetic set (release-blocking)."""
CLASSIFICATION_TARGET: Final = 0.85
"""NFR-1: denial-reason classification accuracy on the labeled de-identified set."""
DRAFT_ACCEPTANCE_TARGET: Final = 0.70
"""NFR-2: share of appeal letters accepted with only minor edits."""
LATENCY_TARGET_SECONDS: Final = 600.0
"""NFR-3: median seconds from denial upload to appeal-ready draft on the M3 Pro."""

EXIT_PASSED: Final = 0
"""The measurement ran and met its target."""
EXIT_BELOW_TARGET: Final = 1
"""The measurement ran and missed its target: the release is blocked."""
EXIT_NOT_MEASURED: Final = 2
"""The measurement could not run (worker down, models missing, a download running, bad input)."""

EvalName = Literal["redaction_recall", "classification_accuracy", "draft_acceptance"]


def exit_code(passed: bool) -> int:
    """The gate's exit code for a measurement that ran."""
    return EXIT_PASSED if passed else EXIT_BELOW_TARGET


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Score(_Strict):
    """Hits over items for one category, or for the whole set.

    Attributes:
        hits: Items the system got right (a PHI value redacted, a case classified correctly).
        total: Items scored.
        value: ``hits / total`` to four places; ``0`` for an empty category.
    """

    hits: int = Field(ge=0)
    total: int = Field(ge=0)
    value: float = Field(ge=0, le=1)

    @classmethod
    def of(cls, hits: int, total: int) -> Score:
        """Build the score of ``hits`` out of ``total``."""
        return cls(hits=hits, total=total, value=round(hits / total, 4) if total else 0.0)

    def meets(self, target: float) -> bool:
        """Whether ``hits / total`` reaches ``target``, compared exactly.

        ``value`` is rounded for display: 440/449 shows as 0.98 while it is below it.
        """
        return self.total > 0 and Fraction(self.hits, self.total) >= Fraction(str(target))


class EvalResult(_Strict):
    """A quality eval's outcome against its target (US-12.1, US-12.2).

    Attributes:
        story: The story the eval gates.
        eval: Which eval.
        dataset: The eval set's name.
        started_at: When the run began.
        finished_at: When it ended.
        metric: What ``overall.value`` measures (``recall``, ``accuracy``, ``acceptance_rate``).
        target: The value ``overall.value`` must reach.
        passed: ``overall`` reaches ``target`` (compared exactly, not as the rounded value).
        overall: Hits over all items.
        by_category: The same per category (PHI category, denial reason), sorted by name.
        misses: The items missed, as ``<item id>:<category>`` (no values), sorted.
        errors: Items that could not be scored, as ``<item id>:<error code>``; each one is a miss.
    """

    story: Literal["US-12.1", "US-12.2"]
    eval: EvalName
    dataset: str = Field(min_length=1, max_length=120)
    started_at: datetime
    finished_at: datetime
    metric: Literal["recall", "accuracy", "acceptance_rate"]
    target: float = Field(gt=0, le=1)
    passed: bool
    overall: Score
    by_category: dict[str, Score]
    misses: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class StageSeconds(_Strict):
    """Seconds one case spent in each step of the flow.

    Attributes:
        upload: Creating the case and attaching its documents.
        extract: The extraction job.
        diagnose: The diagnosis job (classification and explanation).
        draft: The drafting job.
    """

    upload: float = Field(ge=0)
    extract: float = Field(ge=0)
    diagnose: float = Field(ge=0)
    draft: float = Field(ge=0)


class CaseTiming(_Strict):
    """One benchmark case's upload-to-draft time.

    Attributes:
        case: The eval-set case ID (not the worker's case ID, which is discarded).
        kinds: Its document kinds.
        seconds: Upload to appeal-ready draft; ``None`` when the flow failed.
        stages: Per-step seconds, when the flow finished.
        error_code: Why the flow failed, when it did.
    """

    case: str
    kinds: list[str]
    seconds: float | None = Field(default=None, ge=0)
    stages: StageSeconds | None = None
    error_code: ErrorCode | None = None


class LatencyReport(_Strict):
    """The upload-to-draft benchmark (US-12.3).

    Attributes:
        story: Always ``US-12.3``.
        dataset: The benchmark set's name.
        started_at: When the run began.
        finished_at: When it ended.
        target_seconds: The median must not exceed this.
        median_seconds: Median over every case; a failed case counts as slower than any other,
            so failures can only raise it.
        passed: Every case finished and the median is within the target.
        cases: One timing per case, in set order.
    """

    story: Literal["US-12.3"] = "US-12.3"
    dataset: str = Field(min_length=1, max_length=120)
    started_at: datetime
    finished_at: datetime
    target_seconds: float = Field(gt=0)
    median_seconds: float | None = Field(ge=0)
    passed: bool
    cases: list[CaseTiming] = Field(min_length=1)


class EgressFinding(_Strict):
    """A connection to a non-loopback address, or an attempt at one.

    Attributes:
        source: Who saw it: ``audit`` (a process's socket audit hook) or ``lsof`` (a sample).
        process: The process (``worker``, ``plugin_api``, ``model:<role>``).
        pid: Its process ID.
        event: What it did; ``connect`` for an ``lsof`` connection.
        host: The remote host or address.
        port: The remote port, when known.
    """

    source: Literal["audit", "lsof"]
    process: str
    pid: int = Field(ge=0)
    event: EgressEvent
    host: str
    port: int | None = None


class EgressReport(_Strict):
    """The zero-egress check of one full case flow (US-12.4).

    Attributes:
        story: Always ``US-12.4``.
        started_at: When the flow began.
        finished_at: When it ended.
        flow_completed: Upload, extraction, diagnosis, draft, and export all finished.
        error_code: Why the flow stopped, when it did.
        processes: Every process watched, as ``<name>:<pid>`` (a process group for ``lsof``),
            sorted.
        observers: What watched each of them: ``audit`` (its own socket audit hook) and/or
            ``lsof`` (connection samples). A model server has ``lsof`` only.
        samples: How many ``lsof`` samples were taken.
        findings: Every non-loopback connection or attempt seen.
        passed: The flow completed and nothing reached beyond loopback.
    """

    story: Literal["US-12.4"] = "US-12.4"
    started_at: datetime
    finished_at: datetime
    flow_completed: bool
    error_code: ErrorCode | None = None
    processes: list[str]
    observers: dict[str, list[Literal["audit", "lsof"]]]
    samples: int = Field(ge=0)
    findings: list[EgressFinding]
    passed: bool
