"""What a case's diagnosis prompts may read: its facts and the global reference text for them.

Implements: US-6.1 (``case_facts``: the payer, the amounts, and per line the procedure code,
adjustments, and remark codes; ``code_notes_text``), US-6.2 (``rule_cards_text``,
``required_documents_text``). Rules: BR-5 (only this case's own fields and global reference text),
BR-10 (callers put each text in a data block), data minimization (US-6.1 design decision 3: the
claim number and the service dates stay out).
"""

from __future__ import annotations

from typing import Any, Final

from claimcoach.cases.extraction import Adjustment, CaseExtraction, Extracted
from claimcoach.corpus.bundle import RuleCard
from claimcoach.corpus.types import Document

__all__ = [
    "CARD_CHARS",
    "MAX_NOTES",
    "NOTE_CHARS",
    "case_facts",
    "code_notes_text",
    "required_documents_text",
    "rule_cards_text",
    "value_of",
]

MAX_NOTES: Final = 20
NOTE_CHARS: Final = 2000
"""Characters of one code note sent to a model: a code's meaning fits in far less."""
CARD_CHARS: Final = 4000
"""Characters of one rule card's body sent to a model (US-6.2 design decision 5)."""


def value_of(field: Extracted[Any]) -> str | None:
    """A field's value as text, or ``None`` when it is unreadable."""
    return None if field.value is None else str(field.value)


def _adjustment(adjustment: Adjustment) -> dict[str, str | None]:
    return {
        "group_code": value_of(adjustment.group_code),
        "carc": value_of(adjustment.carc),
        "amount": value_of(adjustment.amount),
    }


def case_facts(extraction: CaseExtraction) -> dict[str, Any]:
    """Return what a diagnosis prompt may read: no claim number and no service dates."""
    return {
        "payer": value_of(extraction.payer_name),
        "billed_amount": value_of(extraction.billed_amount),
        "paid_amount": value_of(extraction.paid_amount),
        "claim_adjustments": [_adjustment(a) for a in extraction.adjustments],
        "claim_remark_codes": [value_of(code) for code in extraction.rarc_codes],
        "lines": [
            {
                "procedure_code": value_of(line.procedure_code),
                "billed_amount": value_of(line.billed_amount),
                "paid_amount": value_of(line.paid_amount),
                "adjustments": [_adjustment(a) for a in line.adjustments],
                "remark_codes": [value_of(code) for code in line.rarc_codes],
            }
            for line in extraction.lines
        ],
    }


def code_notes_text(notes: list[Document]) -> str:
    """The global code entries for the case's codes, one paragraph each."""
    if not notes:
        return "No code notes are on file for these codes."
    return "\n\n".join(
        f"{note.metadata.get('key', note.doc_id)}: {note.title}\n{note.text[:NOTE_CHARS]}"
        for note in notes[:MAX_NOTES]
    )


def rule_cards_text(cards: list[RuleCard]) -> str:
    """The payer's rule cards with their provenance, one paragraph each (US-6.2)."""
    if not cards:
        return "No rule card is on file for this payer."
    return "\n\n".join(
        f"{card.key} (source: {card.source}; verified on {card.verified_on.isoformat()}): "
        f"{card.title}\n{card.body[:CARD_CHARS]}"
        for card in cards
    )


def required_documents_text(documents: list[str]) -> str:
    """The required documents numbered from 1, as the checklist reply refers to them (US-6.2)."""
    if not documents:
        return "No required documents are listed for this payer."
    return "\n".join(f"{number}. {document}" for number, document in enumerate(documents, 1))
