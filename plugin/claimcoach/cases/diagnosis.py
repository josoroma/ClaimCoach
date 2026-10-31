"""A case's diagnosis: the denial reason, the appeal likelihood, and the reasons for it.

Implements: US-6.1 (``DenialReason``, a closed set, with ``REASON_GUIDE``; ``AppealLikelihood``;
``Diagnosis`` with one to five reasons, the codes it read, and the digest of the extraction it was
based on), US-6.2 (``Explanation``, ``ChecklistItem``, ``RuleCardRef``), US-6.3 (``AppealDeadline``
and its ``DeadlineStatus``). Rules: ES-1
(Pydantic v2, ``extra="forbid"``, frozen), BR-14 (a diagnosis holds case content: it travels
worker → gateway → pane only and is never logged or put in an event).

This module imports nothing heavier than Pydantic, so the gateway can use it.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from claimcoach.corpus.types import Timestamp

__all__ = [
    "REASON_GUIDE",
    "AppealDeadline",
    "AppealLikelihood",
    "CaseCode",
    "ChecklistItem",
    "DeadlineStatus",
    "DenialReason",
    "Diagnosis",
    "Explanation",
    "Reason",
    "RuleCardRef",
]


class DenialReason(StrEnum):
    """Why the claim was denied: one family per kind of fix (design decision 1).

    ``REASON_GUIDE`` describes each family and the CARCs that usually signal it.
    """

    ELIGIBILITY = "eligibility"
    PRIOR_AUTHORIZATION = "prior_authorization"
    MEDICAL_NECESSITY = "medical_necessity"
    CODING_ERROR = "coding_error"
    MISSING_INFORMATION = "missing_information"
    DUPLICATE_CLAIM = "duplicate_claim"
    TIMELY_FILING = "timely_filing"
    NON_COVERED_SERVICE = "non_covered_service"
    BUNDLING = "bundling"
    COORDINATION_OF_BENEFITS = "coordination_of_benefits"
    OTHER = "other"


REASON_GUIDE: Final[dict[DenialReason, str]] = {
    DenialReason.ELIGIBILITY: "the patient was not covered on the date of service (CARC 27, 26, "
    "31, 109, 177)",
    DenialReason.PRIOR_AUTHORIZATION: "authorization, precertification, or a referral was "
    "missing (CARC 197, 15, 62, 198)",
    DenialReason.MEDICAL_NECESSITY: "the payer judged the service not medically necessary "
    "(CARC 50, 56, 151, 167)",
    DenialReason.CODING_ERROR: "procedure, modifier, or diagnosis codes are invalid or "
    "inconsistent (CARC 4, 5, 6, 11, 181, 182)",
    DenialReason.MISSING_INFORMATION: "the claim lacked information or an attachment (CARC 16, "
    "252, 226, 227)",
    DenialReason.DUPLICATE_CLAIM: "the payer already processed this service (CARC 18)",
    DenialReason.TIMELY_FILING: "the claim arrived after the filing limit (CARC 29)",
    DenialReason.NON_COVERED_SERVICE: "the plan does not cover the service or a benefit limit "
    "was reached (CARC 96, 204, 49, 119)",
    DenialReason.BUNDLING: "the service is included in another service on the claim (CARC 97, "
    "234, 236)",
    DenialReason.COORDINATION_OF_BENEFITS: "another payer is primary or must be billed first "
    "(CARC 22, 23)",
    DenialReason.OTHER: "none of the families above fits",
}
"""Each denial family and the reason codes that usually signal it; guidance, not rules."""


class AppealLikelihood(StrEnum):
    """How likely an appeal is to overturn the denial (PRD §6 story 3)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
"""One reason for the appeal likelihood, in plain language."""

CaseCode = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{1,5}(?:-[A-Z0-9]{1,5})?$")]
"""A code the diagnosis read: an adjustment as ``CO-197`` (or ``197`` without its group code), or
a remark code such as ``N286``."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Explanation(_Strict):
    """The denial in plain language (US-6.2).

    Attributes:
        explanation: What the denial means and what the biller can do, in plain language.
        root_cause: The likely underlying cause, in one or two sentences.
    """

    explanation: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    root_cause: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class ChecklistItem(_Strict):
    """One missing document the appeal needs, from the payer's rule card (US-6.2).

    Attributes:
        document: The document, exactly as the rule card lists it.
        why: Why this appeal needs it, when the model said.
    """

    document: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    why: Reason | None = None


class RuleCardRef(_Strict):
    """A rule card the diagnosis used, with its provenance (US-6.2, PRD §11).

    Attributes:
        key: ``<payer>/<topic>``.
        payer: The card's payer.
        topic: What the card is about.
        source: Where the rule comes from.
        verified_on: When it was last verified.
        stale: It was verified more than 180 days before the diagnosis ran.
    """

    key: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    payer: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    topic: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    source: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    verified_on: date
    stale: bool


DeadlineStatus = Literal[
    "computed",
    "no_payer",
    "no_rule_card",
    "no_appeal_limit",
    "no_denial_date",
    "implausible_denial_date",
]
"""Whether the deadline was computed, or which input it lacks (US-6.3 design decision 4)."""


class AppealDeadline(_Strict):
    """When the appeal must be filed, or why that is unknown (US-6.3).

    Attributes:
        status: ``computed``, or the first missing input: an unreadable payer, no rule card for
            the payer, no appeal limit on the payer's cards, no readable denial date, or a denial
            date after today or before a service date.
        due: The last day to file: ``denial_date`` plus ``limit_days`` calendar days.
        denial_date: The date the clock counts from, when read.
        limit_days: The appeal time limit, when a card gives one.
        rule_card: The key of the card that gives the limit.
    """

    status: DeadlineStatus
    due: date | None = None
    denial_date: date | None = None
    limit_days: int | None = Field(default=None, ge=1, le=3650)
    rule_card: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None

    @model_validator(mode="after")
    def _due_only_when_computed(self) -> AppealDeadline:
        computed = self.status == "computed"
        if (self.due is not None) != computed:
            raise ValueError("only a computed deadline has a due date")
        if not computed:
            return self
        if self.denial_date is None or self.limit_days is None or self.rule_card is None:
            raise ValueError("a computed deadline names its date, limit, and card")
        if self.due != self.denial_date + timedelta(days=self.limit_days):
            raise ValueError("a computed deadline is its denial date plus its limit")
        return self


class Diagnosis(_Strict):
    """What the classification model concluded about one case.

    Attributes:
        denial_reason: The denial family.
        appeal_likelihood: How likely an appeal is to succeed.
        likelihood_reasons: Why, one to five plain-language reasons.
        codes: The adjustment and remark codes the classification read, in case order.
        extraction_digest: ``CaseExtraction.digest()`` of the extraction it read; when the case's
            extraction no longer has this digest, the diagnosis is stale.
        diagnosed_at: When it ran.
        explanation: The plain-language explanation and root cause, once the explanation step
            ran (US-6.2).
        checklist: Missing documents, drawn only from the payer's rule card (US-6.2).
        rule_cards: The payer's rule cards the diagnosis used (US-6.2); empty when none matched.
    """

    denial_reason: DenialReason
    appeal_likelihood: AppealLikelihood
    likelihood_reasons: list[Reason] = Field(min_length=1, max_length=5)
    codes: list[CaseCode] = Field(default_factory=list, max_length=200)
    extraction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnosed_at: Timestamp
    explanation: Explanation | None = None
    checklist: list[ChecklistItem] = Field(default_factory=list, max_length=30)
    rule_cards: list[RuleCardRef] = Field(default_factory=list, max_length=5)
