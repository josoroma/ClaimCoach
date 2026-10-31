"""Helpers for drafting tests: the drafting model's reply and the letter templates.

Implements: US-7.1 test harness (ES-4: offline; a fake OpenAI-compatible server stands in for
Ternary-Bonsai-2-27B), US-7.2 (a letter with accented, typographic, and CJK text to export).
Nothing here names a person: the letter keeps the placeholders a real draft would.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Final

from claimcoach.corpus.bundle import CorpusBundle, LetterTemplate

__all__ = ["LETTER", "TEMPLATE_BUNDLE", "letter_reply", "letter_template"]

LETTER: Final = (
    "[Practice address]\n"
    "\n"
    "ACME Health Plan, Appeals Unit\n"
    "\n"
    "Re: Appeal of claim CLAIM-77, denied 2026-10-15\n"
    "Patient: [Patient name], member ID [Member ID]\n"
    "\n"
    "To the appeals reviewer:\n"
    "\n"
    "We appeal the denial of procedure 99213 on 2026-09-01 (CO-197, N286). A retroactive "
    "authorization was requested; the enclosed records show the visit was medically necessary.\n"
    "\n"
    "Enclosures:\n"
    "1. Copy of the denial notice or remittance\n"
    "2. Medical records for the date of service\n"
    "\n"
    "Sincerely,\n"
    "[Signature]\n"
    "[Provider name and NPI]"
)
"""What a good drafting model answers for the synthetic CO-197 case."""


def letter_reply(letter: object = LETTER, **changes: Any) -> str:
    """The JSON the drafting model answers, with ``letter`` and top-level ``changes``."""
    return json.dumps({"letter": letter} | changes)


def letter_template(template_id: str, body: str | None = None) -> LetterTemplate:
    """A letter template named ``template_id``."""
    return LetterTemplate.model_validate(
        {
            "kind": "letter_template",
            "template_id": template_id,
            "title": f"Template {template_id}",
            "body": body or f"Synthetic {template_id} letter: [Date] … Re: claim [Claim number].",
            "source": "Synthetic templates for tests",
            "verified_on": date(2026, 9, 1),
        }
    )


TEMPLATE_BUNDLE: Final = CorpusBundle(
    items=[
        letter_template(
            "appeal", "General appeal: state the claim, the denial, and why it is wrong."
        ),
        letter_template(
            "appeal-prior-authorization",
            "Prior-authorization appeal: cite the retro-authorization request and the records.",
        ),
        letter_template("corrected-claim", "Corrected claim cover letter."),
    ]
)
"""A general appeal template, one for prior-authorization denials, and an unrelated one."""
