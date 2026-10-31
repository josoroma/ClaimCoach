"""Exact lookups in the global corpus for what a case names: its codes and its payer.

Implements: US-6.1 (``code_entries``: the code knowledge-base entries for a case's CARC, RARC, and
group codes, read by key), US-6.2 (``rule_card_of``; ``payer_rule_cards``: the rule cards of the
payer whose name matches the case's payer), US-7.1 (``letter_template``: the first stored of the
template IDs a draft asks for). Rules: BR-5 (only the global scope is read here, never
another case), BR-14 (nothing here logs content; a malformed card is logged by error type).

The keys are the ones ``CodeEntry.key`` gives at import (US-4.3): ``CARC/197``, ``RARC/N286``,
``GROUP/CO``. A case's codes are exact keys, so they are read, not searched by similarity. Payers
match by whole words at the start of the name (US-6.2 design decision 4): a card's payer matches
when its words begin the case's payer name, and the card payer with the most words wins.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Final, get_args

from claimcoach.corpus.bundle import STRUCTURED_CARD_FIELDS, LetterTemplate, RuleCard, payer_words
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import CorpusScope, Document
from claimcoach.logs import get_logger

__all__ = ["code_entries", "letter_template", "payer_rule_cards", "payer_words", "rule_card_of"]

_TOPICS: Final = get_args(RuleCard.model_fields["topic"].annotation)
_log = get_logger("claimcoach.corpus")


def code_entries(store: CorpusStore, keys: Sequence[str]) -> list[Document]:
    """Return the global code entries with these keys, in the order of ``keys``.

    Args:
        store: The global scope.
        keys: ``<code_set>/<CODE>`` keys; duplicates and keys with no entry are skipped.

    Raises:
        CorpusError: ``store`` is not the global scope.
    """
    if store.scope is not CorpusScope.GLOBAL:
        raise CorpusError("code entries live in the global scope")
    found = {document.metadata.get("key"): document for document in store.documents(kind="code")}
    return [found[key] for key in dict.fromkeys(keys) if key in found]


def rule_card_of(document: Document) -> RuleCard:
    """Return the rule card a global ``rule_card`` document was imported from.

    Raises:
        KeyError: The metadata lacks a card field.
        ValueError: A structured field is not JSON, or the card does not validate.
    """
    metadata = document.metadata
    fields = {
        name: json.loads(value) if name in STRUCTURED_CARD_FIELDS else value
        for name, value in metadata.items()
        if name in RuleCard.model_fields
    }
    return RuleCard.model_validate(
        {
            "kind": "rule_card",
            "payer": metadata["payer"],
            "title": document.title,
            "body": document.text,
            **fields,
        }
    )


def _without_article(words: tuple[str, ...]) -> tuple[str, ...]:
    """``The ACME Health Plan`` reads as ``ACME Health Plan``."""
    return words[1:] if words[:1] == ("the",) else words


def payer_rule_cards(store: CorpusStore, payer: str | None) -> list[RuleCard]:
    """Return the matched payer's rule cards, one per topic, in topic order.

    A card's payer matches when its words begin the case's payer name (a leading ``the`` is
    ignored), and the card payer with the most words wins: ``ACME Health`` matches ``ACME HEALTH
    PLAN`` and beats ``ACME``, while ``Medicare`` never matches ``AETNA MEDICARE ADVANTAGE``. Two
    spellings of one payer (``Aetna``, ``AETNA``) are the same payer: per topic the most recently
    verified card is kept, so at most one card per topic is returned. A card whose stored form
    does not validate is skipped.

    Args:
        store: The global scope.
        payer: The case's payer name; ``None`` (unreadable) matches nothing.

    Raises:
        CorpusError: ``store`` is not the global scope.
    """
    if store.scope is not CorpusScope.GLOBAL:
        raise CorpusError("rule cards live in the global scope")
    words = _without_article(payer_words(payer or ""))
    longest = 0
    by_topic: dict[str, RuleCard] = {}
    for document in store.documents(kind="rule_card"):
        try:
            card = rule_card_of(document)
        except (KeyError, ValueError) as exc:  # pydantic's ValidationError is a ValueError
            _log.warning("a stored rule card did not validate: %s", type(exc).__name__)
            continue
        card_words = _without_article(payer_words(card.payer))
        if not card_words or words[: len(card_words)] != card_words:
            continue
        if len(card_words) > longest:
            longest, by_topic = len(card_words), {}
        if len(card_words) == longest:
            kept = by_topic.get(card.topic)
            if kept is None or (card.verified_on, card.key) > (kept.verified_on, kept.key):
                by_topic[card.topic] = card
    return [by_topic[topic] for topic in _TOPICS if topic in by_topic]


def letter_template(store: CorpusStore, template_ids: Sequence[str]) -> LetterTemplate | None:
    """Return the first of ``template_ids`` the global corpus holds, or ``None`` (US-7.1).

    A stored template that does not validate is skipped, as a malformed rule card is.

    Raises:
        CorpusError: ``store`` is not the global scope.
    """
    if store.scope is not CorpusScope.GLOBAL:
        raise CorpusError("letter templates live in the global scope")
    found: dict[str, LetterTemplate] = {}
    for document in store.documents(kind="letter_template"):
        try:
            template = LetterTemplate.model_validate(
                {
                    "kind": "letter_template",
                    "template_id": document.metadata["key"],
                    "title": document.title,
                    "body": document.text,
                    "source": document.metadata["source"],
                    "verified_on": document.metadata["verified_on"],
                }
            )
        except (KeyError, ValueError) as exc:  # pydantic's ValidationError is a ValueError
            _log.warning("a stored letter template did not validate: %s", type(exc).__name__)
            continue
        found[template.template_id] = template
    return next((found[name] for name in template_ids if name in found), None)
