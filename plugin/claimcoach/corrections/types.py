"""Typed corrected-claim bodies: the remedy recommendation and the corrected-claim draft.

Implements: US-7.4 (``RemedyAdvice``: the recommended fix and what decided it;
``CorrectableField``, ``ClaimCorrection``, and ``CorrectedClaimDraft``: a list of the changes a
corrected claim needs, for the biller to make in their own billing system, never a claim form or
an 837). Rules: ES-1 (Pydantic v2, ``extra="forbid"``, frozen), BR-4 (``CorrectedClaimDraft.label``
is fixed to "draft for human review"; no body names a recipient or a channel: nothing is sent),
BR-14 (a draft holds case content: it travels worker → gateway → pane only and is never logged or
put in an event), Non-goals §5 (a change never carries a new code: a current value can only be
copied from the extraction, and only for the fields it holds).

This module imports nothing heavier than Pydantic, so the gateway can use it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from claimcoach.cases.diagnosis import (
    MAX_RULE_CARDS,
    CaseCode,
    DenialReason,
    FrequencyCode,
    Remedy,
)
from claimcoach.corpus.types import Timestamp
from claimcoach.letters.types import DRAFT_LABEL

__all__ = [
    "EXTRACTED_FIELDS",
    "FIELD_LABELS",
    "FREQUENCY_MEANINGS",
    "LINE_FIELDS",
    "MAX_CORRECTIONS",
    "NOT_IN_DOCUMENTS",
    "ClaimCorrection",
    "CorrectableField",
    "CorrectedClaimDraft",
    "CorrectionText",
    "RemedyAdvice",
    "RemedyBasis",
]

MAX_CORRECTIONS: Final = 40
"""Most changes one draft lists (design decision 3)."""
MAX_BECAUSE: Final = 20
"""Most codes one change cites."""
NOT_IN_DOCUMENTS: Final = "not in your documents"
"""How a current value the case's documents do not hold is shown (design decision 2)."""


class CorrectableField(StrEnum):
    """What a change points at on the claim (design decision 1)."""

    PROCEDURE_CODE = "procedure_code"
    MODIFIER = "modifier"
    DIAGNOSIS_CODE = "diagnosis_code"
    DIAGNOSIS_POINTER = "diagnosis_pointer"
    UNITS = "units"
    SERVICE_DATE = "service_date"
    PLACE_OF_SERVICE = "place_of_service"
    MEMBER_ID = "member_id"
    PATIENT_DEMOGRAPHICS = "patient_demographics"
    OTHER_INSURANCE = "other_insurance"
    CLAIM_DATA = "claim_data"


LINE_FIELDS: Final = frozenset(
    {
        CorrectableField.PROCEDURE_CODE,
        CorrectableField.MODIFIER,
        CorrectableField.DIAGNOSIS_POINTER,
        CorrectableField.UNITS,
        CorrectableField.SERVICE_DATE,
        CorrectableField.PLACE_OF_SERVICE,
    }
)
"""Fields of a service line; the others belong to the claim."""
EXTRACTED_FIELDS: Final = frozenset(
    {CorrectableField.PROCEDURE_CODE, CorrectableField.SERVICE_DATE}
)
"""The only fields the extraction holds a value for: a line's procedure code and service date."""
FIELD_LABELS: Final[dict[CorrectableField, str]] = {
    CorrectableField.PROCEDURE_CODE: "procedure code",
    CorrectableField.MODIFIER: "modifier",
    CorrectableField.DIAGNOSIS_CODE: "diagnosis code",
    CorrectableField.DIAGNOSIS_POINTER: "diagnosis pointer",
    CorrectableField.UNITS: "units",
    CorrectableField.SERVICE_DATE: "service date",
    CorrectableField.PLACE_OF_SERVICE: "place of service",
    CorrectableField.MEMBER_ID: "member ID",
    CorrectableField.PATIENT_DEMOGRAPHICS: "patient name, date of birth, or sex",
    CorrectableField.OTHER_INSURANCE: "other insurance",
    CorrectableField.CLAIM_DATA: "claim information",
}
"""Each field as the export names it."""
FREQUENCY_MEANINGS: Final[dict[FrequencyCode, str]] = {
    "1": "a new claim",
    "7": "a replacement of the prior claim",
    "8": "a void of the prior claim",
}
"""What each claim frequency code asks the biller to do (design decision 7)."""

CorrectionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
"""A change's action or why: plain language, not blank."""
CardKey = Annotated[str, StringConstraints(min_length=1, max_length=120)]
CurrentValue = Annotated[str, StringConstraints(min_length=1, max_length=50)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


RemedyBasis = Literal["table", "codes", "rule_card"]
"""What decided a remedy: the denial reason's row, the case's codes, or the payer's rule card."""


class RemedyAdvice(_Strict):
    """The fix a diagnosed case needs, recommended by fixed rules (US-7.4 design decision 5).

    Attributes:
        remedy: Corrected claim, appeal, either, or none (verify first).
        basis: What decided it.
        denial_reason: The diagnosis's denial reason it was decided for.
        codes: The case's codes that decided it (``codes`` basis); empty otherwise.
        rule_card: The key of the payer's ``corrected_claims`` card (``rule_card`` basis).
    """

    remedy: Remedy
    basis: RemedyBasis
    denial_reason: DenialReason
    codes: list[CaseCode] = Field(default_factory=list, max_length=MAX_BECAUSE)
    rule_card: CardKey | None = None

    @model_validator(mode="after")
    def _card_only_from_a_card(self) -> RemedyAdvice:
        if (self.rule_card is not None) != (self.basis == "rule_card"):
            raise ValueError("a rule card decides only a rule_card remedy")
        return self


class ClaimCorrection(_Strict):
    """One change the corrected claim needs.

    Attributes:
        line: The service line, from 1; none for the claim (or every line of a claim whose lines
            were not read).
        field: What to check or change.
        current_value: The value the case's documents hold for it; none when they hold none,
            shown as "not in your documents".
        because: The adjustment and remark codes that point here, as the diagnosis shows them.
        action: What to check or change, in plain language; never a new code.
        why: Why the codes point here.
    """

    line: int | None = Field(default=None, ge=1, le=999)
    field: CorrectableField
    current_value: CurrentValue | None = None
    because: list[CaseCode] = Field(default_factory=list, max_length=MAX_BECAUSE)
    action: CorrectionText
    why: CorrectionText

    @model_validator(mode="after")
    def _value_only_where_documents_hold_one(self) -> ClaimCorrection:
        if self.line is not None and self.field not in LINE_FIELDS:
            raise ValueError("a claim field has no line")
        if self.current_value is not None and (
            self.line is None or self.field not in EXTRACTED_FIELDS
        ):
            raise ValueError("only a line's procedure code or service date has a current value")
        return self


class CorrectedClaimDraft(_Strict):
    """A case's corrected-claim draft: the changes to make, for human review (US-7.4).

    Attributes:
        label: Always "draft for human review" (BR-4).
        original_claim_id: The payer's claim number, when it was read.
        frequency_code: The claim frequency code to use, as an instruction (design decision 7).
        corrections: The changes, claim-level first, then by line.
        omitted: How many more changes the codes point at than the draft lists (a claim of many
            lines): the pane and the export say so, so the biller checks every line.
        rule_cards: Keys of the payer's rule cards it was drafted with; empty when none matched.
        extraction_digest: The extraction it was drafted from (``CaseExtraction.digest``).
        diagnosed_at: When the diagnosis it was drafted from ran.
        drafted_at: When the model wrote it.
    """

    label: Literal["draft for human review"] = DRAFT_LABEL
    original_claim_id: Annotated[str, StringConstraints(min_length=1, max_length=50)] | None = None
    frequency_code: FrequencyCode
    corrections: list[ClaimCorrection] = Field(min_length=1, max_length=MAX_CORRECTIONS)
    omitted: int = Field(default=0, ge=0)
    rule_cards: list[CardKey] = Field(default_factory=list, max_length=MAX_RULE_CARDS)
    extraction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnosed_at: Timestamp
    drafted_at: Timestamp
