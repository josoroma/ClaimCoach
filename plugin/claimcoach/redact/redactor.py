"""Detect and redact PHI with the local model and the regex validators.

Implements: US-3.1 (``Redactor``: model spans unioned with regex spans, then ``redact()``),
US-3.4 (every value it redacts is remembered in the process ``PhiLedger`` for log scrubbing).
Rules: BR-3, BR-14, NFR-4.
"""

from __future__ import annotations

import asyncio

from claimcoach.redact.detector import PhiDetector
from claimcoach.redact.ledger import LEDGER, PhiLedger
from claimcoach.redact.spans import redact
from claimcoach.redact.types import PhiSpan, RedactionResult
from claimcoach.redact.validators import find_regex_spans

__all__ = ["Redactor"]


def _redact_all(text: str, spans: list[PhiSpan]) -> RedactionResult:
    return redact(text, spans + find_regex_spans(text))


class Redactor:
    """Detect and redact PHI in one call: the union of model and regex spans, then ``redact()``.

    Args:
        detector: The PHI model detector.
        ledger: Where found values are remembered for log scrubbing (US-3.4).
    """

    def __init__(self, detector: PhiDetector, ledger: PhiLedger = LEDGER) -> None:
        """Keep the detector and the ledger."""
        self._detector = detector
        self._ledger = ledger

    async def redact_text(self, text: str) -> RedactionResult:
        """Return ``text`` with all PHI the model or the validators find replaced.

        Raises:
            ModelError: The PHI model could not run or its reply was unusable; nothing is
                returned, so callers fail closed.
        """
        spans = await self._detector.detect(text)
        # CPU-bound regex work runs off the event loop, so /health stays responsive meanwhile.
        result = await asyncio.to_thread(_redact_all, text, spans)
        self._ledger.remember(text, result.spans)
        return result
