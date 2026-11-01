"""The reference number and the rep's instructions, read from a call's transcript.

Implements: US-11.1 (``reference_number``: the last reference, confirmation, or ticket number
spoken, with spoken digit groups joined; ``rep_instructions``: the statements that tell the biller
what to do, in order, without repeats). Fixed rules, not a model: the same transcript always gives
the same notes, and the pane shows them for the biller to check against the transcript (design
decision 4). Rules: BR-14 (nothing here logs).
"""

from __future__ import annotations

import re
from typing import Final

from claimcoach.calls.types import MAX_INSTRUCTIONS

__all__ = ["MAX_INSTRUCTION_CHARS", "reference_number", "rep_instructions"]

MAX_INSTRUCTION_CHARS: Final = 500
_REFERENCE_CHARS: Final = range(4, 33)
_PREFIX_CHARS: Final = 4
"""A letters-only token is kept only as a short prefix (``REF``, ``CN``) before the digits."""
_CUE: Final = re.compile(
    r"\b(?:call\s+)?(?:reference|ref|confirmation|ticket)\b\s*"
    r"(?:number|num|no\.?|#|id)?(?:\s+for\s+(?:this|the|your|today's)\s+call)?"
    r"\s*(?:is|was|:)?\s*",
    re.IGNORECASE,
)
_TOKEN: Final = re.compile(r"[A-Z0-9][A-Z0-9-]*")
_STOP: Final = ".,;:!?"
_SENTENCE: Final = re.compile(r"(?<=[.!?])\s+")
_INSTRUCTION: Final = re.compile(
    r"\b(?:you(?:'ll| will)? (?:need|have|must|should|can|may) to|you need|you must|you should"
    r"|please|resubmit|re-submit|submit|send|fax|mail|attach|include|call (?:us )?back"
    r"|corrected claim|reconsideration|within \d+|timely filing|deadline|appeal)\b",
    re.IGNORECASE,
)


def _reference_at(tail: str) -> str | None:
    """The number that starts ``tail`` (the words after a cue), or ``None``."""
    tokens: list[str] = []
    for word in tail.split():
        token = word.rstrip(_STOP)
        if not _TOKEN.fullmatch(token):
            break
        if token.isalpha() and (tokens or len(token) > _PREFIX_CHARS):
            break  # a word after the number, or a word that is not a prefix
        tokens.append(token)
        if token != word:
            break  # punctuation ends the number
    joined = "".join(tokens)
    if len(joined) in _REFERENCE_CHARS and any(char.isdigit() for char in joined):
        return joined
    return None


def reference_number(text: str) -> str | None:
    """Return the last reference number spoken in ``text``, or ``None``.

    A number follows a cue ("reference number is", "call ref #", "confirmation number",
    "ticket"); spoken groups are joined ("8 4 1 7 2" → ``84172``); it is 4-32 characters with at
    least one digit. The last one wins: reps repeat it as the call ends, and an earlier mention is
    often a previous call's.
    """
    found = None
    for cue in _CUE.finditer(text):
        number = _reference_at(text[cue.end() : cue.end() + 120])
        if number is not None:
            found = number
    return found


def rep_instructions(text: str) -> list[str]:
    """Return up to ten statements in ``text`` that tell the biller what to do, in order.

    A statement is kept when it holds an instruction cue ("you need to", "please", "resubmit",
    "fax", "within 30 days", ...); questions are not instructions. Each is at most 500 characters;
    a repeated statement is kept once.
    """
    instructions: list[str] = []
    for raw in _SENTENCE.split(text):
        sentence = " ".join(raw.split())[:MAX_INSTRUCTION_CHARS]
        if not sentence or sentence.endswith("?") or not _INSTRUCTION.search(sentence):
            continue
        if sentence not in instructions:
            instructions.append(sentence)
        if len(instructions) == MAX_INSTRUCTIONS:
            break
    return instructions
