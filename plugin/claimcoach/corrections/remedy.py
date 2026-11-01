"""The remedy a denial needs, by fixed rules: a corrected claim, an appeal, either, or neither.

Implements: US-7.4 (``recommended_remedy``: design decision 5, the PM-approved routing table, the
code splits of eligibility and missing-information denials, and the payer's ``corrected_claims``
rule card overriding the table; ``frequency_code``: design decision 7; ``case_code_uses``: each of
the case's codes with the line it is on, which the draft plans its changes from). Rules: no model
takes part (the routing is pure and tested), BR-14 (nothing here logs).
"""

from __future__ import annotations

from typing import Final, NamedTuple

from claimcoach.cases.diagnosis import DenialReason, Diagnosis, FrequencyCode, Remedy
from claimcoach.cases.extraction import Adjustment, CaseExtraction, Extracted
from claimcoach.corpus.bundle import RuleCard
from claimcoach.corrections.types import MAX_BECAUSE, RemedyAdvice

__all__ = [
    "ATTACHMENT_CODES",
    "CLAIM_DATA_RARCS",
    "REMEDY_TABLE",
    "CodeUse",
    "case_code_uses",
    "corrected_claims_card",
    "frequency_code",
    "recommended_remedy",
]

REMEDY_TABLE: Final[dict[DenialReason, Remedy]] = {
    DenialReason.CODING_ERROR: Remedy.CORRECTED_CLAIM,
    DenialReason.MISSING_INFORMATION: Remedy.EITHER,
    DenialReason.ELIGIBILITY: Remedy.EITHER,
    DenialReason.BUNDLING: Remedy.EITHER,
    DenialReason.COORDINATION_OF_BENEFITS: Remedy.EITHER,
    DenialReason.MEDICAL_NECESSITY: Remedy.APPEAL,
    DenialReason.PRIOR_AUTHORIZATION: Remedy.APPEAL,
    DenialReason.TIMELY_FILING: Remedy.APPEAL,
    DenialReason.NON_COVERED_SERVICE: Remedy.APPEAL,
    DenialReason.DUPLICATE_CLAIM: Remedy.NONE,
    DenialReason.OTHER: Remedy.NONE,
}
"""The remedy per denial reason (SPECS.md US-7.4, PM-approved 2026-11-01). Eligibility and
missing information are ``either`` until their codes settle them."""

CLAIM_DATA_RARCS: Final = frozenset({"M51", "M53", "M76", "M77", "MA61", "N382", "MA130"})
"""Remark codes saying the claim's own data is missing or invalid: a corrected claim fixes them."""
ATTACHMENT_CODES: Final = frozenset({"252", "226", "227", "M127", "N29", "N706"})
"""CARCs and RARCs asking for documentation or records: an appeal or reconsideration sends them."""
UNIDENTIFIED_PATIENT: Final = frozenset({"31"})
"""CARC 31: the patient cannot be identified as the payer's insured (a member ID to correct)."""
TERMINATED_COVERAGE: Final = frozenset({"27"})
"""CARC 27: expenses incurred after coverage terminated (verify coverage first)."""
UNPROCESSABLE: Final = "MA130"
"""RARC MA130: the claim is unprocessable and has no appeal rights; submit a new claim."""


class CodeUse(NamedTuple):
    """One of the case's codes where it appears.

    Attributes:
        line: The service line it is on, from 1; ``None`` for a claim-level code.
        code: The CARC or RARC as read (``197``, ``N286``).
        shown: As the diagnosis shows it (``CO-197``, ``N286``).
    """

    line: int | None
    code: str
    shown: str


def _adjustment_use(line: int | None, adjustment: Adjustment) -> CodeUse | None:
    carc, group = adjustment.carc.value, adjustment.group_code.value
    if carc is None:
        return None
    return CodeUse(line, carc, f"{group}-{carc}" if group else carc)


def _uses(
    line: int | None, adjustments: list[Adjustment], remarks: list[Extracted[str]]
) -> list[CodeUse]:
    found = [_adjustment_use(line, adjustment) for adjustment in adjustments]
    found += [CodeUse(line, r.value, r.value) for r in remarks if r.value is not None]
    return [use for use in found if use is not None]


def case_code_uses(extraction: CaseExtraction) -> list[CodeUse]:
    """Every readable CARC and RARC of the case, claim-level first, then line by line."""
    uses = _uses(None, extraction.adjustments, extraction.rarc_codes)
    for number, line in enumerate(extraction.lines, 1):
        uses += _uses(number, line.adjustments, line.rarc_codes)
    return uses


def corrected_claims_card(cards: list[RuleCard]) -> RuleCard | None:
    """The payer's ``corrected_claims`` card among its rule cards, if it has one."""
    return next((card for card in cards if card.topic == "corrected_claims"), None)


def _shown(uses: list[CodeUse], codes: frozenset[str]) -> list[str]:
    shown = dict.fromkeys(use.shown for use in uses if use.code in codes)
    return list(shown)[:MAX_BECAUSE]


def _split(
    reason: DenialReason,
    uses: list[CodeUse],
    to_correct: frozenset[str],
    other: tuple[frozenset[str], Remedy],
) -> RemedyAdvice:
    """Settle ``reason`` by its codes: a corrected claim, the ``other`` remedy, or either."""
    correcting, (other_codes, other_remedy) = _shown(uses, to_correct), other
    against = _shown(uses, other_codes)
    if correcting and not against:
        return RemedyAdvice(
            remedy=Remedy.CORRECTED_CLAIM, basis="codes", denial_reason=reason, codes=correcting
        )
    if against and not correcting:
        return RemedyAdvice(remedy=other_remedy, basis="codes", denial_reason=reason, codes=against)
    if correcting:  # both: the codes do not settle it
        codes = (correcting + against)[:MAX_BECAUSE]
        return RemedyAdvice(remedy=Remedy.EITHER, basis="codes", denial_reason=reason, codes=codes)
    return RemedyAdvice(remedy=REMEDY_TABLE[reason], basis="table", denial_reason=reason)


def recommended_remedy(
    diagnosis: Diagnosis, extraction: CaseExtraction, cards: list[RuleCard]
) -> RemedyAdvice:
    """Recommend the fix for a diagnosed case (design decision 5); no model takes part.

    Args:
        diagnosis: The case's current diagnosis.
        extraction: The extraction it diagnosed.
        cards: The payer's rule cards (``corpus.lookup.payer_rule_cards``).

    Returns:
        The remedy, with what decided it: the payer's ``corrected_claims`` card when it names the
        denial reason, else the case's codes for eligibility and missing information, else the
        denial reason's row of ``REMEDY_TABLE``.
    """
    reason = diagnosis.denial_reason
    card = corrected_claims_card(cards)
    if card is not None and reason in card.remedies:
        return RemedyAdvice(
            remedy=card.remedies[reason],
            basis="rule_card",
            denial_reason=reason,
            rule_card=card.key,
        )
    uses = case_code_uses(extraction)
    if reason is DenialReason.ELIGIBILITY:
        return _split(reason, uses, UNIDENTIFIED_PATIENT, (TERMINATED_COVERAGE, Remedy.NONE))
    if reason is DenialReason.MISSING_INFORMATION:
        return _split(reason, uses, CLAIM_DATA_RARCS, (ATTACHMENT_CODES, Remedy.APPEAL))
    return RemedyAdvice(remedy=REMEDY_TABLE[reason], basis="table", denial_reason=reason)


def frequency_code(extraction: CaseExtraction, cards: list[RuleCard]) -> FrequencyCode:
    """The claim frequency code a corrected claim uses (design decision 7).

    The payer's ``corrected_claims`` card decides when it names one; otherwise an unprocessable
    claim (RARC MA130) is resubmitted as new (1) and any other as a replacement (7).
    """
    card = corrected_claims_card(cards)
    if card is not None and card.frequency_code is not None:
        return card.frequency_code
    unprocessable = any(use.code == UNPROCESSABLE for use in case_code_uses(extraction))
    return "1" if unprocessable else "7"
