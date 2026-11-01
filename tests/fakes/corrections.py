"""Helpers for corrected-claim tests: the drafting model's reply and a payer's corrected-claim card.

Implements: US-7.4 test harness (ES-4: offline; a fake OpenAI-compatible server stands in for
Ternary-Bonsai-2-27B and answers a corrected-claim prompt with one action and why per planned
change, any other prompt with the appeal letter). Nothing here names a person.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any, Final

from claimcoach.corpus.bundle import CorpusBundle, RuleCard
from tests.fakes.drafting import LETTER, letter_reply
from tests.fakes.fake_model_server import ChatRequest

__all__ = [
    "ACTION",
    "WHY",
    "corrected_claims_card",
    "correction_reply",
    "drafting_responder",
]

ACTION: Final = "Check this field against the claim you sent and the visit's documentation."
WHY: Final = "The payer's codes on this line say the claim's information did not match."
CORRECTION_MARK: Final = "corrected-claim changes"
"""Words of the ``correction_draft`` template's system text, which the letter template lacks."""


def correction_reply(count: int, action: str = ACTION, why: str = WHY, **changes: Any) -> str:
    """The JSON the drafting model answers for ``count`` planned changes, plus top-level changes."""
    items = [{"index": index, "action": action, "why": why} for index in range(count)]
    return json.dumps({"corrections": items} | changes)


def _prompt(request: ChatRequest) -> str:
    return "\n".join(str(message.content) for message in request.messages)


def drafting_responder(
    action: str = ACTION, why: str = WHY, letter: str = LETTER
) -> Callable[[ChatRequest], str]:
    """A drafting fake: a corrected-claim prompt gets one action and why per planned change (the
    planned changes are the prompt's ``"index":`` entries); any other prompt gets the letter."""

    def answer(request: ChatRequest) -> str:
        prompt = _prompt(request)
        if CORRECTION_MARK in prompt:
            return correction_reply(prompt.count('"index":'), action, why)
        return letter_reply(letter)

    return answer


def corrected_claims_card(payer: str = "ACME Health", **fields: Any) -> CorpusBundle:
    """A bundle with one ``corrected_claims`` card for ``payer`` holding ``fields``."""
    card = RuleCard.model_validate(
        {
            "kind": "rule_card",
            "payer": payer,
            "topic": "corrected_claims",
            "title": f"{payer} corrected claims",
            "body": "Corrected claims use frequency code 7 and the original claim number.",
            "source": "Synthetic provider manual, section 4",
            "verified_on": date(2026, 9, 15),
            **fields,
        }
    )
    return CorpusBundle(items=[card])
