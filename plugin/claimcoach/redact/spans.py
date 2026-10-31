"""Replace PHI spans with category placeholders, then check the output a second time.

Implements: US-3.1 (``redact()``: none of the detected PHI strings remain). Rules: BR-3, BR-14,
NFR-4. Pure functions over text and spans: no model, no I/O, so logging (US-3.4) can use them.

``redact()`` runs three passes over what it is given (US-3.1 design decisions 2 and 3):

1. **Propagation.** Every detected value is redacted wherever else it occurs (whole word, any
   case), and each word of a detected name is redacted on its own, so "Jane Doe" also removes the
   later "Ms. Doe".
2. **Replacement.** Overlapping spans are merged and each merged range becomes the placeholder of
   its longest span's category, e.g. ``[NAME]``.
3. **Second pass.** The regex validators run again over the redacted text; anything they find
   (PHI the caller's spans missed) is redacted too and counted in ``second_pass_hits``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from claimcoach.redact.types import (
    PLACEHOLDERS,
    PhiCategory,
    PhiSpan,
    RedactionResult,
    SpanSource,
)
from claimcoach.redact.validators import find_regex_spans

__all__ = ["locate", "locate_parts", "merge_spans", "name_parts", "redact"]

_NAME_PART: Final = re.compile(r"[^\W\d_][\w'-]{2,}")
"""A word of a name worth propagating on its own: three or more characters, not a digit."""

_NAME_STOPWORDS: Final = frozenset({"the", "and", "for", "von", "van", "del", "der"})


_SHORT_NAME_PART: Final = re.compile(r"(?<![^\W\d_])[^\W\d_]{2}(?![^\W\d_])")
"""A two-letter word of a name (Li, Ng, Wu): too common to redact everywhere."""

_TITLES: Final = r"(?:mr|ms|mrs|mx|dr|miss)\.?"

_DISTINCTIVE: Final = re.compile(r"\w*\d\w*|[^\W\d_]{4,}")
"""Words of an unlocatable value still worth redacting: any with a digit, or 4+ letters."""


def name_parts(value: str) -> list[str]:
    """Words of a detected name redacted on their own (≥ 3 letters, not a stopword)."""
    return [p for p in _NAME_PART.findall(value) if p.lower() not in _NAME_STOPWORDS]


def locate(
    text: str, value: str, category: PhiCategory, source: SpanSource = "model"
) -> list[PhiSpan]:
    """Return a span for every whole-word, case-insensitive occurrence of ``value`` in ``text``.

    Args:
        text: The document.
        value: A PHI value.
        category: Its category.
        source: ``model`` or ``propagated``.

    Returns:
        Spans in document order; empty when ``value`` does not occur.
    """
    words = re.findall(r"\w+", value)
    # Models rewrite layout: "12 Elm St, Springfield" for "12 ELM ST\nSPRINGFIELD". Words of the
    # value, in order, separated by up to 8 non-word characters, also count as the value.
    loose = r"[\W_]{1,8}".join(re.escape(word) for word in words) if len(words) > 1 else None
    body = re.escape(value) if loose is None else f"{re.escape(value)}|{loose}"
    pattern = re.compile(rf"(?<!\w)(?:{body})(?!\w)", re.IGNORECASE)
    return [
        PhiSpan(start=m.start(), end=m.end(), category=category, source=source)
        for m in pattern.finditer(text)
    ]


def locate_parts(text: str, value: str, category: PhiCategory) -> list[PhiSpan]:
    """Locate the distinctive words of a value that does not occur as a whole.

    A value the model reported but ``locate`` cannot find may still be PHI written differently;
    its words with a digit, or of four or more letters, are redacted where they occur.
    """
    return [
        span
        for word in dict.fromkeys(_DISTINCTIVE.findall(value))
        for span in locate(text, word, category)
    ]


def _short_name_spans(text: str, value: str) -> list[PhiSpan]:
    """Two-letter name words, only where context marks them as a name.

    After a title ("Ms. Li") or before a comma and another word of the same name ("LI, JANE").
    """
    others = [re.escape(part) for part in name_parts(value)]
    found: list[PhiSpan] = []
    for short in dict.fromkeys(_SHORT_NAME_PART.findall(value)):
        word = re.escape(short)
        contexts = [rf"\b{_TITLES}[ \t]{{1,3}}({word})\b"]
        if others:
            contexts.append(rf"\b({word}),[ \t]{{0,3}}(?:{'|'.join(others)})\b")
        for context in contexts:
            found += [
                PhiSpan(
                    start=m.start(1), end=m.end(1), category=PhiCategory.NAME, source="propagated"
                )
                for m in re.finditer(context, text, re.IGNORECASE)
            ]
    return found


def merge_spans(spans: Iterable[PhiSpan]) -> list[PhiSpan]:
    """Merge overlapping spans; a merged span takes the category of its longest member.

    Args:
        spans: Spans over one text, in any order.

    Returns:
        Non-overlapping spans in text order.
    """
    merged: list[tuple[int, int, PhiSpan]] = []  # (start, end, longest member)
    for span in sorted(spans, key=lambda s: (s.start, -s.end)):
        if merged and span.start < merged[-1][1]:
            start, end, longest = merged[-1]
            if span.end - span.start > longest.end - longest.start:
                longest = span
            merged[-1] = (start, max(end, span.end), longest)
        else:
            merged.append((span.start, span.end, span))
    return [
        PhiSpan(start=start, end=end, category=longest.category, source=longest.source)
        for start, end, longest in merged
    ]


def _propagate(text: str, spans: list[PhiSpan]) -> list[PhiSpan]:
    found: list[PhiSpan] = []
    seen: set[str] = set()
    for span in spans:
        value = text[span.start : span.end]
        parts = [value]
        if span.category is PhiCategory.NAME:
            parts += name_parts(value)
            found += _short_name_spans(text, value)
        for part in parts:
            if part.lower() not in seen:
                seen.add(part.lower())
                found += locate(text, part, span.category, "propagated")
    return found


def _replace(text: str, spans: list[PhiSpan]) -> str:
    pieces: list[str] = []
    cursor = 0
    for span in spans:
        pieces += [text[cursor : span.start], PLACEHOLDERS[span.category]]
        cursor = span.end
    pieces.append(text[cursor:])
    return "".join(pieces)


def redact(text: str, spans: Iterable[PhiSpan]) -> RedactionResult:
    """Replace every PHI span in ``text`` with its category placeholder.

    Args:
        text: The original text.
        spans: Detected spans (model, regex, or both) as offsets into ``text``.

    Returns:
        The redacted text, the merged spans over ``text``, and the second-pass hit count.
    """
    detected = list(spans)
    merged = merge_spans(detected + _propagate(text, detected))
    first_pass = _replace(text, merged)
    leftovers = merge_spans(
        PhiSpan(start=s.start, end=s.end, category=s.category, source="second_pass")
        for s in find_regex_spans(first_pass)
    )
    return RedactionResult(
        text=_replace(first_pass, leftovers),
        spans=tuple(merged),
        second_pass_hits=len(leftovers),
    )
