"""The appeal deadline: the denial date plus the payer rule card's appeal time limit.

Implements: US-6.3 (``compute_deadline``, pure and typed; ``appeal_deadline``, which reads the
case's denial date and the payer's ``appeal_levels`` card and says which input is missing, or
implausible, when the deadline cannot be computed). Rules: ES-1, ES-3; PRD §9 (rule cards hold the
appeal limits).

No limit is ever assumed and no implausible date is ever used (design decision 4): a wrong
deadline is worse than none. ``CaseService`` calls ``appeal_deadline`` whenever it reads a case,
so the deadline follows every confirmed date and every re-imported card without a model run.
"""

from __future__ import annotations

from datetime import date, timedelta

from claimcoach.cases.diagnosis import AppealDeadline
from claimcoach.cases.extraction import CaseExtraction
from claimcoach.corpus.bundle import RuleCard

__all__ = ["AppealDeadline", "appeal_deadline", "compute_deadline"]


def compute_deadline(denial_date: date, limit_days: int) -> date:
    """Return the last day to file an appeal (US-6.3).

    Args:
        denial_date: The date of the payer's decision, printed on the remittance or notice.
        limit_days: The payer's appeal time limit in calendar days (``RuleCard.appeal_limit_days``).

    Returns:
        ``denial_date`` plus ``limit_days`` calendar days: a 180-day limit on a 2026-10-15
        denial is due 2027-04-13.

    Raises:
        ValueError: ``limit_days`` is below 1.
        OverflowError: The result is after year 9999 (``appeal_deadline`` never gets there: it
            refuses a denial date after today).
    """
    if limit_days < 1:
        raise ValueError("an appeal limit is at least one day")
    return denial_date + timedelta(days=limit_days)


def _plausible(denial_date: date, extraction: CaseExtraction, today: date) -> bool:
    """A denial comes after its services and not after today (a misread year fails this)."""
    served = [line.service_date.value for line in extraction.lines if line.service_date.value]
    return denial_date <= today and all(denial_date >= day for day in served)


def appeal_deadline(
    extraction: CaseExtraction, cards: list[RuleCard], today: date
) -> AppealDeadline:
    """Return the case's appeal deadline, or why it is unknown.

    Inputs are checked in the order the people who fix them work: the payer and its cards
    (``no_payer``, the biller confirms it; ``no_rule_card`` and ``no_appeal_limit``, the manager
    adds them), then the denial date (``no_denial_date`` or ``implausible_denial_date``, the
    biller confirms it).

    Args:
        extraction: The case's fields; ``denial_date`` is the clock's start.
        cards: The matched payer's rule cards (``corpus.lookup.payer_rule_cards``), at most one
            per topic.
        today: This Mac's date; a denial date after it is implausible.
    """
    denial_date = extraction.denial_date.value
    if extraction.payer_name.value is None:
        return AppealDeadline(status="no_payer", denial_date=denial_date)
    if not cards:
        return AppealDeadline(status="no_rule_card", denial_date=denial_date)
    card = next((c for c in cards if c.topic == "appeal_levels"), None)
    if card is None or card.appeal_limit_days is None:
        return AppealDeadline(status="no_appeal_limit", denial_date=denial_date)
    limit, key = card.appeal_limit_days, card.key
    if denial_date is None:
        return AppealDeadline(status="no_denial_date", limit_days=limit, rule_card=key)
    if not _plausible(denial_date, extraction, today):
        return AppealDeadline(
            status="implausible_denial_date",
            denial_date=denial_date,
            limit_days=limit,
            rule_card=key,
        )
    return AppealDeadline(
        status="computed",
        due=compute_deadline(denial_date, limit),
        denial_date=denial_date,
        limit_days=limit,
        rule_card=key,
    )
