"""Typed PHI categories, spans, redaction results, and the ``/redact`` REST bodies.

Implements: US-3.1 (``PhiCategory``, ``PhiSpan``, ``RedactionResult``; ``RedactRequest`` and
``RedactResponse`` for the worker's ``POST /redact``). Rules: ES-1, BR-14 (a response carries the
redacted text and counts only, never a span's original text).

This module imports neither httpx nor model code so the gateway can use it (PC-4).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "MAX_TEXT_CHARS",
    "PLACEHOLDERS",
    "PhiCategory",
    "PhiSpan",
    "RedactRequest",
    "RedactResponse",
    "RedactionResult",
    "SpanSource",
]

MAX_TEXT_CHARS: Final = 200_000
"""Largest text one ``/redact`` call accepts (a long EOB is ~30 000 characters)."""


class PhiCategory(StrEnum):
    """What kind of PHI a span is (PRD §4 synthetic set, plus ``other``)."""

    NAME = "name"
    DOB = "dob"
    MRN = "mrn"
    MEMBER_ID = "member_id"
    SSN = "ssn"
    ADDRESS = "address"
    PHONE = "phone"
    OTHER = "other"
    """An identifier the model flagged under a category outside the seven; still redacted."""


PLACEHOLDERS: Final[dict[PhiCategory, str]] = {
    category: f"[{category.value.upper()}]" for category in PhiCategory
}
"""Replacement text per category, e.g. ``[NAME]``."""

SpanSource = Literal["model", "regex", "propagated", "second_pass"]
"""Who found a span: the PHI model, a regex validator, the propagation of a found value to its
other occurrences, or the second-pass check over the redacted output."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PhiSpan(_Strict):
    """A half-open character range ``[start, end)`` of PHI in a text.

    Attributes:
        start: Offset of the first character.
        end: Offset after the last character.
        category: What kind of PHI it is.
        source: Who found it.
    """

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    category: PhiCategory
    source: SpanSource

    @model_validator(mode="after")
    def _non_empty(self) -> PhiSpan:
        if self.end <= self.start:
            raise ValueError("a span must end after it starts")
        return self


class RedactionResult(_Strict):
    """A redacted text and what was removed from it.

    Attributes:
        text: The input with every span replaced by its category placeholder.
        spans: Merged spans, as offsets into the input text.
        second_pass_hits: PHI the second-pass regex check found in the output of the first pass
            (US-3.1 decision 3); these are redacted too.
    """

    text: str
    spans: tuple[PhiSpan, ...]
    second_pass_hits: int = Field(ge=0)

    def counts(self) -> dict[PhiCategory, int]:
        """Return the number of redacted spans per category (second-pass hits excluded)."""
        counts: dict[PhiCategory, int] = {}
        for span in self.spans:
            counts[span.category] = counts.get(span.category, 0) + 1
        return counts


class RedactRequest(_Strict):
    """Body of ``POST /redact`` on the worker."""

    text: str = Field(max_length=MAX_TEXT_CHARS)


class RedactResponse(_Strict):
    """Success body of ``POST /redact``: the redacted text and per-category counts only.

    Attributes:
        ok: Always ``True``.
        text: Redacted text.
        counts: Redacted spans per category.
        second_pass_hits: PHI caught by the second-pass check.
    """

    ok: Literal[True] = True
    text: str
    counts: dict[PhiCategory, int]
    second_pass_hits: int = Field(ge=0)

    @classmethod
    def from_result(cls, result: RedactionResult) -> RedactResponse:
        """Build the response for ``result``."""
        return cls(
            text=result.text, counts=result.counts(), second_pass_hits=result.second_pass_hits
        )
