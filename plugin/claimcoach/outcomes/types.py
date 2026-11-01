"""Typed bodies of the manager's weekly summary.

Implements: US-8.2 (``IsoWeek``, ``OutcomeCounts`` with the total and the overturn rate,
``CategoryRow``, ``CodeRow``, ``WeeklySummary``), US-8.3 (``ExportApproval``,
``FineTuneExportRequest``, ``FineTuneRecord``, ``FineTuneExport``, ``ExportNotApprovedError``).
Rules: ES-1 (Pydantic v2, ``extra="forbid"``, frozen), BR-14 (counts, enums, codes, rule-card payer
names, and profile names only).

This module imports nothing heavier than Pydantic, so the gateway can use it.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, ClassVar, Final, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from claimcoach.api.models import ErrorCode
from claimcoach.cases.diagnosis import AppealLikelihood, CaseCode, DenialReason
from claimcoach.cases.errors import CaseError
from claimcoach.corpus.types import CaseOutcome, ProfileName, Timestamp
from claimcoach.outcomes.features import ClaimFacts, PayerKey

_COUNTS: Final = ("overturned", "upheld", "written_off")

__all__ = [
    "FINE_TUNE_FORMAT",
    "ISO_WEEK",
    "WEEK_YEARS",
    "CategoryRow",
    "CodeRow",
    "ExportApproval",
    "ExportNotApprovedError",
    "FineTuneExport",
    "FineTuneExportRequest",
    "FineTuneRecord",
    "IsoWeek",
    "ManagerName",
    "OutcomeCounts",
    "WeeklySummary",
]

FINE_TUNE_FORMAT: Final = "claimcoach-fine-tune-1"
"""The ``format`` of every record of a fine-tune export; a new layout gets a new name."""

_WEEK_PATTERN: Final = r"^[0-9]{4}-W(?:0[1-9]|[1-4][0-9]|5[0-3])$"
"""ASCII digits only: ``\\d`` would accept any script's digits."""
WEEK_YEARS: Final = range(1970, 9999)
"""Years a summary can cover; outside them a week's bounds cannot be computed in every zone."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _real_week(value: str) -> str:
    year, week = value.split("-W")
    if int(year) not in WEEK_YEARS:
        raise ValueError("the week is outside the years a summary covers")
    date.fromisocalendar(int(year), int(week), 1)  # W53 exists in some years only
    return value


IsoWeek = Annotated[str, StringConstraints(pattern=_WEEK_PATTERN), AfterValidator(_real_week)]
"""An ISO 8601 week, ``2026-W44``: Monday 00:00 to the next Monday 00:00 (design decision 4)."""

ISO_WEEK: Final = TypeAdapter(IsoWeek)
"""Validates a week given as text."""


class OutcomeCounts(BaseModel):
    """How many outcomes of each kind, and the share that were overturned.

    ``total`` and ``overturn_rate`` are derived from the three counts when the model is built;
    a body that states them must state them consistently.

    Attributes:
        overturned: Denials overturned on appeal.
        upheld: Denials the payer upheld.
        written_off: Denials written off.
        total: Every outcome counted.
        overturn_rate: Overturned outcomes over all of them, to four places; ``None`` when there
            are none.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    overturned: int = Field(default=0, ge=0)
    upheld: int = Field(default=0, ge=0)
    written_off: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    overturn_rate: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="before")
    @classmethod
    def _derive(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        counts = [data.get(name, 0) for name in _COUNTS]
        if not all(type(count) is int for count in counts):
            return data  # field validation reports it
        total = sum(counts)
        derived = {"total": total, "overturn_rate": round(counts[0] / total, 4) if total else None}
        if any(name in data and data[name] != value for name, value in derived.items()):
            raise ValueError("total and overturn_rate must match the counts")
        return data | derived


class CategoryRow(OutcomeCounts):
    """Outcomes of one payer and denial reason.

    Attributes:
        payer: The payer as its rule cards name it; ``None`` when no card matched.
        denial_reason: The denial family; ``None`` for cases without a current diagnosis.
    """

    payer: PayerKey | None
    denial_reason: DenialReason | None


class CodeRow(OutcomeCounts):
    """Outcomes of one payer and one adjustment or remark code.

    Attributes:
        payer: The payer as its rule cards name it; ``None`` when no card matched.
        code: The code (``CO-197``, ``N286``); a case counts once per code it carried.
    """

    payer: PayerKey | None
    code: CaseCode


class WeeklySummary(BaseModel):
    """The manager's weekly denial-pattern summary (PRD §6 story 7).

    Attributes:
        ok: Always ``True``.
        week: The ISO week summarized.
        starts_at: Its first instant.
        ends_at: The first instant after it.
        timezone: The time zone the week was judged in.
        profiles: The opted-in profiles whose outcomes were read.
        not_shared: How many profiles have not opted in; nothing of theirs was read.
        unreadable: Opted-in profiles whose outcomes could not be read this time.
        totals: Every outcome of the week.
        by_category: Per payer and denial reason, most outcomes first.
        by_code: Per payer and code, most outcomes first.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True
    week: IsoWeek
    starts_at: Timestamp
    ends_at: Timestamp
    timezone: str = Field(min_length=1, max_length=64)
    profiles: list[ProfileName]
    not_shared: int = Field(ge=0)
    unreadable: list[ProfileName] = Field(default_factory=list)
    totals: OutcomeCounts
    by_category: list[CategoryRow] = Field(default_factory=list)
    by_code: list[CodeRow] = Field(default_factory=list)


def _printable(value: str) -> str:
    # Not only ASCII controls: U+0085, U+2028, and U+2029 split a log line for many readers.
    if not value.isprintable():
        raise ValueError("a manager name is printable text on one line")
    return value


ManagerName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(_printable),
]
"""Who approved an export, as they typed it: printable text on one line, 1 to 80 characters."""


class ExportApproval(_Strict):
    """The manager's explicit approval of one fine-tune export (US-8.3 design decision 3).

    Attributes:
        manager: Who approves it; recorded with the export.
        approved: Must be ``true``; anything else exports nothing.
    """

    manager: ManagerName
    approved: StrictBool


class FineTuneExportRequest(_Strict):
    """``POST /outcomes/export``: an export runs only with an approval that says ``true``.

    Attributes:
        approval: The manager's approval; without it nothing is read or written.
    """

    approval: ExportApproval | None = None


class FineTuneRecord(_Strict):
    """One de-identified case/outcome pair: what the classifier read, its label, and the outcome.

    Attributes:
        format: Always ``FINE_TUNE_FORMAT``.
        payer: The payer as its global rule cards name it, when one matched.
        facts: Amounts, adjustments, remark codes, and lines; no claim number, no date, no name.
        codes: The adjustment and remark codes the diagnosis read.
        denial_reason: The diagnosis's denial family (the classification label).
        appeal_likelihood: The diagnosis's appeal likelihood.
        outcome: How the case ended.
    """

    format: Literal["claimcoach-fine-tune-1"]
    payer: PayerKey | None = None
    facts: ClaimFacts
    codes: list[CaseCode] = Field(default_factory=list, max_length=200)
    denial_reason: DenialReason
    appeal_likelihood: AppealLikelihood | None = None
    outcome: CaseOutcome


class FineTuneExport(_Strict):
    """Where an approved export was written and what it holds.

    Attributes:
        ok: Always ``True``.
        path: The file, on this Mac (owner-only; kept until the manager deletes it).
        filename: Its name.
        records: Pairs written.
        unlabeled: Outcomes left out: no current diagnosis, or recorded before US-8.3.
        withheld: Pairs a PHI validator matched, left out (expected to be 0).
        profiles: The opted-in profiles read.
        unreadable: Opted-in profiles whose outcomes could not be read.
        approved_by: Who approved it.
        approved_at: When.
    """

    ok: Literal[True] = True
    path: str = Field(min_length=1)
    filename: str = Field(pattern=r"^fine-tune-\d{8}T\d{6}Z-[0-9a-f]{8}\.jsonl$")
    records: int = Field(ge=0)
    unlabeled: int = Field(ge=0)
    withheld: int = Field(ge=0)
    profiles: list[ProfileName]
    unreadable: list[ProfileName] = Field(default_factory=list)
    approved_by: ManagerName
    approved_at: Timestamp


class ExportNotApprovedError(CaseError):
    """A fine-tune export was asked for without the manager's approval (US-8.3)."""

    code: ClassVar[ErrorCode] = "export_not_approved"
    status_code: ClassVar[int] = 403
