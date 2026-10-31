"""Regex validators for the structured PHI categories: SSN, MRN, DOB, phone, and member ID.

Implements: US-3.1 (regex validators; their matches are unioned with the model's spans and they
run again as the second-pass check over redacted output). Rules: BR-14, NFR-4 (recall first: a
false positive costs a placeholder, a miss costs a disclosure).

Names and addresses have no reliable shape, so only the PHI model finds them. DOB, MRN, and member
IDs look like ordinary dates and codes, so they match only after a label ("DOB:", "MRN",
"Member ID", "member_id"); the span is the value, not the label.

Every quantifier between a label and its value is bounded, so no input can make a pattern
backtrack for long (review finding: unbounded adjacent whitespace runs took 30 s on 400 spaces).
``test_us_3_1_validators_resist_backtracking`` keeps it so.
"""

from __future__ import annotations

import re
from typing import Final

from claimcoach.redact.types import PhiCategory, PhiSpan

__all__ = ["VALIDATORS", "find_regex_spans"]

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]{0,6}\.?"
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_DATE = (
    r"(?i:\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})"
    r"|\d{4}-\d{2}-\d{2}"
    rf"|{_MONTH}[ \t]{{1,3}}{_DAY},?[ \t]{{1,3}}\d{{4}}"
    rf"|{_DAY}[ \t-]{{1,3}}{_MONTH}[ \t-]{{1,3}}\d{{4}}"
    r"|\d{8})"
)
"""``03/04/1962``, ``1962-03-04``, ``March 4th, 1962``, ``JAN 02 1960``, ``04-MAR-1962``,
``03041962`` (the last only ever after a DOB label)."""

_ID = (
    r"(?:[A-Za-z]{2,5}[ ][0-9][0-9-]{3,20}"
    r"|(?=[A-Za-z0-9-]{0,24}\d)[A-Za-z0-9][A-Za-z0-9-]{2,24})"
)
"""An identifier value: a short letter prefix, one space, and digits (``XYZ 123456789``); or
letters, digits and dashes with at least one digit."""

_SEP = (
    r"""(?i:["']?[\s_]{0,4}(?:[:#=\u2013-]|no\.?|num(?:ber)?|\([^)\n]{0,16}\))?"""
    r"""[\s_]{0,4}[:#=]?["' \t]{0,4})"""
)
"""Between a label and its value: a few spaces or underscores, one of ``:``/``#``/``=``/``-``,
``no.``/``number``, or a format hint such as ``(MM/DD/YYYY)``, and the quotes of
``key="value"``. Every repeat is bounded."""

_W = r"[\s_]{1,3}"
"""Between the words of a label: ``Member ID``, ``member_id``, ``date_of_birth``."""

_START = r"(?<![A-Za-z])"
"""A label starts at a non-letter, so ``patient_member_id`` and ``"member_id"`` both match."""

_PHONE = r"(?:\+?1[-.\s]?)?(?:\(\d{3}\)[ \t]?|\d{3}[-.\s])\d{3}[-.\s]\d{4}"
_EXT = r"(?:[ \t]{0,2}(?:x|ext\.?)[ \t]{0,2}\d{1,5})?"


def _labeled(label: str, value: str) -> re.Pattern[str]:
    # Labels never end inside a word: "ID" must not match the start of "Identified".
    return re.compile(rf"(?i:{_START}(?:{label})(?![A-Za-z]))" + _SEP + rf"({value})")


VALIDATORS: Final[tuple[tuple[PhiCategory, re.Pattern[str]], ...]] = (
    (PhiCategory.SSN, re.compile(r"(?<![\w-])(\d{3}[-. ]\d{2}[-. ]\d{4})(?![\w-])")),
    (PhiCategory.SSN, re.compile(r"(?i)(?<![\w-])(x{3}-x{2}-\d{4})(?![\w-])")),
    (
        PhiCategory.SSN,
        _labeled(rf"SSN|SS#|social{_W}security(?:{_W}(?:no\.?|number|#))?", r"\d{9}(?!\d)"),
    ),
    (PhiCategory.PHONE, re.compile(rf"(?<![\w-])({_PHONE}{_EXT})(?![\w-])")),
    (
        PhiCategory.PHONE,
        _labeled(
            rf"phone|tel|telephone|cell|mobile|fax|callback(?:{_W}number)?", rf"\d{{10}}{_EXT}"
        ),
    ),
    (
        PhiCategory.DOB,
        _labeled(
            rf"DOB|D\.O\.B\.?|date{_W}of{_W}birth|birth[\s_]{{0,3}}date|born(?:{_W}on)?", _DATE
        ),
    ),
    (
        PhiCategory.MRN,
        _labeled(
            rf"MRN|MR#|medical{_W}record(?:{_W}(?:no\.?|number|#))?"
            rf"|patient{_W}(?:account|acct|control)(?:{_W}(?:no\.?|number|#))?"
            rf"|pat{_W}acct|account|acct|PCN",
            _ID,
        ),
    ),
    (
        PhiCategory.MEMBER_ID,
        _labeled(
            rf"(?:member|mbr|subscriber|insured|policy|patient)(?:'s)?"
            rf"(?:{_W}(?:ID|identifier|identification))?(?:{_W}(?:no\.?|number|#))?"
            rf"|medicare(?:{_W}number)?|medicaid|MBI|HICN|cert(?:ificate)?|ID",
            _ID,
        ),
    ),
)
"""``(category, pattern)``; group 1 of each pattern is the PHI value."""


def find_regex_spans(text: str) -> list[PhiSpan]:
    """Return every validator match in ``text``, ordered by position.

    Args:
        text: Any text.

    Returns:
        One span per match; overlapping matches of different validators are all returned and
        merged later by ``redact()``.
    """
    spans = [
        PhiSpan(start=match.start(1), end=match.end(1), category=category, source="regex")
        for category, pattern in VALIDATORS
        for match in pattern.finditer(text)
    ]
    return sorted(spans, key=lambda span: (span.start, span.end))
