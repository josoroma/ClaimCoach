"""Bounded in-memory ledger of PHI values found in this process, for scrubbing logs.

Implements: US-3.4 (the redaction filter removes names and addresses the model found earlier).
Rules: BR-14. Values live only in this process's memory: never logged, persisted, or returned.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from collections.abc import Iterable
from typing import Final

from claimcoach.redact.spans import name_parts
from claimcoach.redact.types import PhiCategory, PhiSpan

__all__ = ["LEDGER", "LEDGER_SIZE", "PhiLedger"]

LEDGER_SIZE: Final = 10_000


class PhiLedger:
    """Bounded, in-memory set of PHI values found by the redactor in this process.

    It exists only so logs can drop values that have no regex shape (names, addresses). It is
    never written anywhere and holds at most ``size`` values, oldest evicted first.

    Args:
        size: Maximum number of values.
    """

    def __init__(self, size: int = LEDGER_SIZE) -> None:
        """Create an empty ledger."""
        self._size = size
        self._values: OrderedDict[str, PhiCategory] = OrderedDict()
        self._lock = threading.Lock()

    def remember(self, text: str, spans: Iterable[PhiSpan]) -> None:
        """Add the values of ``spans`` in ``text``, and each word of a name on its own.

        Values of fewer than 3 characters are skipped. Name words are kept so a later log line
        quoting only "Vandermeer" or "VANDERMEER, AVERY" is scrubbed too.

        Args:
            text: The text the spans index into.
            spans: Detected spans.
        """
        with self._lock:
            for span in spans:
                value = text[span.start : span.end].strip()
                words = name_parts(value) if span.category is PhiCategory.NAME else []
                for item in (value, *words):
                    if len(item) >= 3:
                        self._values[item.lower()] = span.category
                        self._values.move_to_end(item.lower())
            while len(self._values) > self._size:
                self._values.popitem(last=False)

    def spans(self, text: str) -> list[PhiSpan]:
        """Return a span for every whole-word occurrence of a remembered value in ``text``."""
        with self._lock:
            values = list(self._values.items())
        lowered = text.lower()
        found: list[PhiSpan] = []
        for value, category in values:
            if value in lowered:
                found += [
                    PhiSpan(start=m.start(), end=m.end(), category=category, source="propagated")
                    for m in re.finditer(rf"(?<!\w){re.escape(value)}(?!\w)", text, re.IGNORECASE)
                ]
        return found

    def clear(self) -> None:
        """Forget every value."""
        with self._lock:
            self._values.clear()


LEDGER: Final = PhiLedger()
"""The process-wide ledger the worker's redactor feeds."""
