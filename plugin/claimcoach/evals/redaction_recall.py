"""The redactor recall release gate: every seeded PHI value must be gone from the redacted text.

Implements: US-12.1 (each synthetic document goes through the running worker's ``POST /redact``,
the full redactor of US-3.1 with the local PHI model; recall is scored per PHI category and
overall into a typed ``EvalResult``; the gate passes at ``RECALL_TARGET`` or above). Rules: NFR-4
(98% on the synthetic set is release-blocking), BR-14 (the report names document IDs and
categories, never a value), BR-1 (loopback only).

A unit is one distinct value of one category in one document. It counts as recalled when neither
the value nor any of its distinctive words remains in the redacted text as a whole word, in any
case, which is what a reader of a log would see: ``[ADDRESS], Port Ellery, OR 80210`` still leaks
the town and ZIP. A word is distinctive when it occurs in the original document only inside PHI
(``Port`` and ``80210`` do; the word ``or`` of a letter's prose does not). A document the worker
could not redact misses all its units.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Final

from claimcoach.api.client import WorkerClient, WorkerError
from claimcoach.api.models import ErrorCode
from claimcoach.evals.datasets import PhiEvalDocument, PhiEvalSet
from claimcoach.evals.types import RECALL_TARGET, EvalResult, Score
from claimcoach.redact.types import RedactRequest

__all__ = ["MIN_WORD", "leaked", "leaks", "redact_set", "run_redaction", "score_redaction"]

Clock = Callable[[], datetime]
MIN_WORD: Final = 2
"""Shortest word of a value that is checked on its own (a two-letter surname counts)."""
_WORD: Final = re.compile(r"\w+")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _whole(value: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(value)}(?!\w)", re.IGNORECASE)


def leaks(value: str, text: str) -> bool:
    """Return whether ``value`` still occurs in ``text`` as a whole word, ignoring case.

    Whole words, so a seeded two-letter surname ("Li") is not found inside "list".
    """
    return _whole(value).search(text) is not None


def _background(document: PhiEvalDocument) -> str:
    """The document with every seeded value removed: the text that is not PHI."""
    text = document.text
    values = {v for vs in document.phi.values() for v in vs}
    for value in sorted(values, key=len, reverse=True):
        text = _whole(value).sub(" ", text)
    return text


def leaked(value: str, background: str, redacted: str) -> bool:
    """Whether ``value``, or a word of it found only inside PHI, remains in ``redacted``.

    Args:
        value: A seeded PHI value.
        background: Its document without PHI (``_background``).
        redacted: The redacted document.
    """
    if leaks(value, redacted):
        return True
    words = {w for w in _WORD.findall(value) if len(w) >= MIN_WORD and not leaks(w, background)}
    return any(leaks(word, redacted) for word in words)


async def redact_set(
    client: WorkerClient, phi_set: PhiEvalSet
) -> tuple[dict[str, str], dict[str, ErrorCode]]:
    """Redact every document of ``phi_set`` with the worker.

    Returns:
        The redacted text of each document that worked, and the error code of each that failed.
    """
    redacted: dict[str, str] = {}
    errors: dict[str, ErrorCode] = {}
    for document in phi_set.documents:
        try:
            response = await client.redact(RedactRequest(text=document.text))
        except WorkerError as exc:
            errors[document.id] = exc.code
        else:
            redacted[document.id] = response.text
    return redacted, errors


def score_redaction(
    phi_set: PhiEvalSet,
    redacted: Mapping[str, str],
    errors: Mapping[str, ErrorCode],
    *,
    started_at: datetime,
    finished_at: datetime,
) -> EvalResult:
    """Score the redacted texts of ``phi_set`` against its seeded values.

    Args:
        phi_set: The eval set.
        redacted: Redacted text per document ID.
        errors: Error code per document ID the worker could not redact.
        started_at: When the run began.
        finished_at: When it ended.
    """
    hits: dict[str, int] = {}
    totals: dict[str, int] = {}
    misses: set[str] = set()
    for document in phi_set.documents:
        text = redacted.get(document.id)
        background = _background(document)
        for category, values in document.phi.items():
            for value in dict.fromkeys(values):
                totals[category] = totals.get(category, 0) + 1
                if text is not None and not leaked(value, background, text):
                    hits[category] = hits.get(category, 0) + 1
                else:
                    misses.add(f"{document.id}:{category}")
    overall = Score.of(sum(hits.values()), sum(totals.values()))
    return EvalResult(
        story="US-12.1",
        eval="redaction_recall",
        dataset=phi_set.name,
        started_at=started_at,
        finished_at=finished_at,
        metric="recall",
        target=RECALL_TARGET,
        passed=overall.meets(RECALL_TARGET),
        overall=overall,
        by_category={c: Score.of(hits.get(c, 0), totals[c]) for c in sorted(totals)},
        misses=sorted(misses),
        errors=sorted(f"{doc}:{code}" for doc, code in errors.items()),
    )


async def run_redaction(
    client: WorkerClient, phi_set: PhiEvalSet, *, clock: Clock = _utc_now
) -> EvalResult:
    """Redact ``phi_set`` with the running worker and score its recall.

    Args:
        client: The worker client.
        phi_set: The synthetic PHI set.
        clock: The current UTC time (tests).
    """
    started = clock()
    redacted, errors = await redact_set(client, phi_set)
    return score_redaction(phi_set, redacted, errors, started_at=started, finished_at=clock())
