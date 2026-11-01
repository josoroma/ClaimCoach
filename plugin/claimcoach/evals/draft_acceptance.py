"""The draft-acceptance eval: how many appeal drafts the manager approved with only minor edits.

Implements: US-12.2 (the manager review rubric, design decision 2: a draft is "accepted with only
minor edits" when the letter the manager approved keeps at least ``MINOR_EDIT_SIMILARITY`` of the
draft's words in order, and at least that share of the approved letter is the draft's words; the
share of such drafts must reach ``DRAFT_ACCEPTANCE_TARGET``). Rules: NFR-2 (70%), BR-14 (the
report holds review IDs and denial reasons, never a letter).

``similarity`` is the smaller of the two shares, over word and punctuation tokens with case and
spacing ignored; the words in order are ``difflib``'s matching blocks. Cutting a quarter of the
draft fails it (0.75 kept), and so does adding a third more text (0.75 of the letter is the
draft's); rewording a salutation or a sentence passes.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

from claimcoach.evals.datasets import DraftReviewSet
from claimcoach.evals.types import DRAFT_ACCEPTANCE_TARGET, EvalResult, Score

__all__ = ["MINOR_EDIT_SIMILARITY", "UNLABELED", "score_drafts", "similarity"]

MINOR_EDIT_SIMILARITY: Final = 0.85
"""The least word-level similarity between draft and approved letter that counts as minor edits."""
UNLABELED: Final = "unlabeled"
"""The category of reviews that name no denial reason."""
_WORD = re.compile(r"\w+|[^\w\s]")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def similarity(draft: str, final: str) -> float:
    """How much of each letter is the other's words in order, the smaller share (0 to 1).

    Args:
        draft: The model's letter.
        final: The letter the manager approved.

    Returns:
        ``min(kept / draft words, kept / final words)``, where ``kept`` counts the draft's words
        that remain in order; 1 for an unchanged letter.
    """
    before, after = _WORD.findall(draft.lower()), _WORD.findall(final.lower())
    if not before or not after:
        return float(before == after)
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    kept = sum(block.size for block in matcher.get_matching_blocks())
    return min(kept / len(before), kept / len(after))


def score_drafts(
    reviews: DraftReviewSet, *, clock: Callable[[], datetime] = _utc_now
) -> EvalResult:
    """Apply the rubric to every review and score the acceptance rate, per denial reason.

    Args:
        reviews: The manager's reviews.
        clock: The current UTC time (tests).
    """
    started = clock()
    hits: dict[str, int] = {}
    totals: dict[str, int] = {}
    misses: list[str] = []
    for review in reviews.reviews:
        category = review.denial_reason.value if review.denial_reason else UNLABELED
        totals[category] = totals.get(category, 0) + 1
        if similarity(review.draft, review.final) >= MINOR_EDIT_SIMILARITY:
            hits[category] = hits.get(category, 0) + 1
        else:
            misses.append(f"{review.id}:{category}")
    overall = Score.of(sum(hits.values()), sum(totals.values()))
    return EvalResult(
        story="US-12.2",
        eval="draft_acceptance",
        dataset=reviews.name,
        started_at=started,
        finished_at=clock(),
        metric="acceptance_rate",
        target=DRAFT_ACCEPTANCE_TARGET,
        passed=overall.meets(DRAFT_ACCEPTANCE_TARGET),
        overall=overall,
        by_category={c: Score.of(hits.get(c, 0), totals[c]) for c in sorted(totals)},
        misses=sorted(misses),
    )
