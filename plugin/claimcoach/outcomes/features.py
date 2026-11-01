"""The de-identified snapshot stored with a case's outcome.

Implements: US-8.2 (``OutcomeFeatures``: the payer as its global rule cards name it, the denial
reason, and the codes of a current diagnosis; ``outcome_features`` builds it when the outcome is
recorded), US-8.3 (``ClaimFacts``: what the classification model read, minus the claim number, the
dates, the payer's printed name, and the dollar amounts, each charge reduced to whether it was
paid; the appeal likelihood). Rules: ES-1 (Pydantic v2,
``extra="forbid"``, frozen), BR-7 (the snapshot outlives the case's content, so nothing in it is
case text: the payer is a global corpus name, reasons and payments are enums, codes are
pattern-checked values), BR-14.

This module imports nothing heavier than Pydantic, so the gateway can use it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from claimcoach.cases.diagnosis import AppealLikelihood, CaseCode, DenialReason, Diagnosis
from claimcoach.cases.extraction import (
    Adjustment,
    CarcCode,
    CaseExtraction,
    ClaimLine,
    GroupCode,
    ProcedureCode,
    RarcCode,
)

__all__ = [
    "AdjustmentFacts",
    "ClaimFacts",
    "LineFacts",
    "OutcomeFeatures",
    "PayerKey",
    "Payment",
    "claim_facts",
    "outcome_features",
    "payment",
]

PayerKey = Annotated[str, StringConstraints(min_length=1, max_length=80)]
"""A payer as the global corpus's rule cards name it (``RuleCardRef.payer``)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Payment = Literal["none", "partial", "full"]
"""What was paid of a charge: nothing, part of it, or all of it (or more). Amounts are not kept."""


def payment(billed: Decimal | None, paid: Decimal | None) -> Payment | None:
    """Reduce a charge and its payment to a ``Payment``; ``None`` when either is unreadable."""
    if billed is None or paid is None:
        return None
    if paid <= 0:
        return "none"
    return "partial" if paid < billed else "full"


class AdjustmentFacts(_Strict):
    """One adjustment as the classifier read it, without its amount; ``None`` where unreadable."""

    group_code: GroupCode | None = None
    carc: CarcCode | None = None


class LineFacts(_Strict):
    """One service line as the classifier read it, without its date of service or amounts."""

    procedure_code: ProcedureCode | None = None
    payment: Payment | None = None
    adjustments: list[AdjustmentFacts] = Field(default_factory=list, max_length=99)
    remark_codes: list[RarcCode] = Field(default_factory=list, max_length=99)


class ClaimFacts(_Strict):
    """What the classification model reads of a claim, reduced to codes and payment status.

    The adjustments, remark codes, and lines of ``pipeline.facts.case_facts``, with each amount
    pair reduced to a ``Payment`` (US-8.3 design decision 1); no payer name, claim number, date, or
    dollar amount.
    """

    payment: Payment | None = None
    adjustments: list[AdjustmentFacts] = Field(default_factory=list, max_length=99)
    remark_codes: list[RarcCode] = Field(default_factory=list, max_length=99)
    lines: list[LineFacts] = Field(default_factory=list, max_length=999)


def _adjustments(adjustments: list[Adjustment]) -> list[AdjustmentFacts]:
    return [AdjustmentFacts(group_code=a.group_code.value, carc=a.carc.value) for a in adjustments]


def _line(line: ClaimLine) -> LineFacts:
    return LineFacts(
        procedure_code=line.procedure_code.value,
        payment=payment(line.billed_amount.value, line.paid_amount.value),
        adjustments=_adjustments(line.adjustments),
        remark_codes=[code.value for code in line.rarc_codes if code.value is not None],
    )


def claim_facts(extraction: CaseExtraction) -> ClaimFacts:
    """Return the classifier's view of the claim with nothing that names, dates, or prices it."""
    return ClaimFacts(
        payment=payment(extraction.billed_amount.value, extraction.paid_amount.value),
        adjustments=_adjustments(extraction.adjustments),
        remark_codes=[code.value for code in extraction.rarc_codes if code.value is not None],
        lines=[_line(line) for line in extraction.lines],
    )


class OutcomeFeatures(BaseModel):
    """What the manager's summary groups an outcome by; no case text, no identifier.

    Attributes:
        payer: The payer as its global rule cards name it; ``None`` when no card matched the
            case's payer (the extracted payer name is never stored: it is case text).
        denial_reason: The current diagnosis's denial family; ``None`` without one.
        codes: The adjustment and remark codes that diagnosis read.
        appeal_likelihood: The diagnosis's appeal likelihood (US-8.3).
        facts: What the classification model read (US-8.3); ``None`` without a current diagnosis
            and for outcomes recorded before US-8.3.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    payer: PayerKey | None = None
    denial_reason: DenialReason | None = None
    codes: list[CaseCode] = Field(default_factory=list, max_length=200)
    appeal_likelihood: AppealLikelihood | None = None
    facts: ClaimFacts | None = None


def outcome_features(
    extraction: CaseExtraction | None, diagnosis: Diagnosis | None
) -> OutcomeFeatures | None:
    """Return the snapshot of a case whose outcome is being recorded.

    Only a diagnosis of the case's current fields counts: a stale one may name another reason.

    Returns:
        The snapshot, or ``None`` when the case has no extraction (it may have been purged), so
        a stored snapshot is kept.
    """
    if extraction is None:
        return None
    if diagnosis is None or diagnosis.extraction_digest != extraction.digest():
        return OutcomeFeatures()
    payer = diagnosis.rule_cards[0].payer if diagnosis.rule_cards else None
    return OutcomeFeatures(
        payer=payer,
        denial_reason=diagnosis.denial_reason,
        codes=list(diagnosis.codes),
        appeal_likelihood=diagnosis.appeal_likelihood,
        facts=claim_facts(extraction),
    )
