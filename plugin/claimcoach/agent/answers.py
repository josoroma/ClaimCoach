"""What the agent tools answer, computed in the worker from the global corpus and the case store.

Implements: US-9.1 (``code_keys`` reads ``CO-197`` as the ``GROUP/CO`` and ``CARC/197`` entries;
``explain_code`` and ``payer_rules`` answer from the global scope only), US-9.2 (``case_summary``:
a case reduced to its codes, its payer as the rule cards name it, its status, and enums; every
summary is audited ``case_summarized``). Rules: BR-3 (results hold IDs, codes, payer names, and
enums), BR-5 (reference answers read the global scope; a summary reads only the asking profile's
case), BR-14 (nothing here logs), PC-4 (runs in the worker; the gateway only proxies).

Only the worker imports this module: it reads SQLite stores. The gateway half of the tools is
``claimcoach.agent.tools``.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Final

from claimcoach.agent.types import (
    MAX_REFERENCE_CHARS,
    CaseStage,
    CaseSummaryResult,
    CodeExplanation,
    ExplainCodeResult,
    PayerRuleCard,
    PayerRulesResult,
)
from claimcoach.cases.service import CaseService
from claimcoach.corpus.bundle import RuleCard, is_stale
from claimcoach.corpus.errors import (
    CaseNotFoundError,
    CodeNotFoundError,
    PayerNotFoundError,
    ProfileNotFoundError,
)
from claimcoach.corpus.lookup import code_entries, payer_rule_cards
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import AuditAction, Document
from claimcoach.pipeline.diagnose import case_codes

__all__ = ["case_summary", "code_keys", "explain_code", "payer_rules"]

_GROUP: Final = re.compile(r"^(?:CO|PR|OA|PI|CR)$")
_RARC: Final = re.compile(r"^(?:MA|M|N)\d{1,3}$")
_CARC: Final = re.compile(r"^(?:\d{1,3}|[A-Z]\d{1,2})$")
"""The same shapes as ``GroupCode``, ``RarcCode``, and ``CarcCode``; no CARC starts with M or N."""


def _reason_key(code: str) -> str | None:
    if _RARC.fullmatch(code):
        return f"RARC/{code}"
    if _CARC.fullmatch(code):
        return f"CARC/{code}"
    return None


def code_keys(code: str) -> list[str]:
    """Return the global code-entry keys a code names, group first; ``[]`` for no code shape.

    ``CO-197`` → ``GROUP/CO``, ``CARC/197``; ``197`` → ``CARC/197``; ``n286`` → ``RARC/N286``;
    ``CO`` → ``GROUP/CO``. Codes keep their digits as typed, as ``CodeEntry.key`` does; the lookup
    tries the other zero paddings (``_spellings``).
    """
    parts = code.strip().upper().split("-")
    if len(parts) == 1:
        if _GROUP.fullmatch(parts[0]):
            return [f"GROUP/{parts[0]}"]
        reason = _reason_key(parts[0])
        return [] if reason is None else [reason]
    if len(parts) == 2 and _GROUP.fullmatch(parts[0]):
        reason = _reason_key(parts[1])
        return [] if reason is None else [f"GROUP/{parts[0]}", reason]
    return []


def _spellings(key: str) -> list[str]:
    """``key`` and, for a numeric CARC, its other zero paddings: ``CARC/16``, ``CARC/016``.

    A bundle may import ``016`` or ``16``; both name the same reason code.
    """
    code_set, code = key.split("/", 1)
    if code_set != "CARC" or not code.isdigit():
        return [key]
    number = str(int(code))
    return list(dict.fromkeys([key, *(f"CARC/{number.zfill(width)}" for width in (1, 2, 3))]))


def _cut(text: str) -> tuple[str, bool]:
    """``text`` cut to ``MAX_REFERENCE_CHARS``, and whether it was cut."""
    return text[:MAX_REFERENCE_CHARS], len(text) > MAX_REFERENCE_CHARS


def _explanation(document: Document, today: date) -> CodeExplanation:
    code_set, code = document.metadata["key"].split("/", 1)
    verified_on = date.fromisoformat(document.metadata["verified_on"])
    explanation, truncated = _cut(document.text)
    return CodeExplanation.model_validate(
        {
            "code_set": code_set,
            "code": code,
            "title": document.title,
            "explanation": explanation,
            "truncated": truncated,
            "source": document.metadata["source"],
            "verified_on": verified_on,
            "stale": is_stale(verified_on, today),
        }
    )


def explain_code(store: CorpusStore, code: str, today: date) -> ExplainCodeResult:
    """Return the global entries for ``code``: the group code's, then the reason code's.

    The code's own entry must be stored (``CO-999`` is not answered with ``CO`` alone); a group
    entry that is missing is left out.

    Args:
        store: The global scope.
        code: The code as the agent asked for it.
        today: The date the stale flag is computed for.

    Raises:
        CodeNotFoundError: The code has no code shape, or no entry for it is stored.
        CorpusError: ``store`` is not the global scope.
    """
    keys = code_keys(code)
    found = [code_entries(store, _spellings(key))[:1] for key in keys]
    # The asked code itself (the reason code of ``CO-197``) must be known; its group need not be.
    if not found or not found[-1]:
        raise CodeNotFoundError
    documents = [document for entry in found for document in entry]
    return ExplainCodeResult(
        code="-".join(key.split("/", 1)[1] for key in keys),
        entries=[_explanation(document, today) for document in documents],
    )


def _card(card: RuleCard, today: date) -> PayerRuleCard:
    body, truncated = _cut(card.body)
    return PayerRuleCard(
        payer=card.payer,
        topic=card.topic,
        title=card.title,
        body=body,
        truncated=truncated,
        required_documents=list(card.required_documents),
        appeal_limit_days=card.appeal_limit_days,
        source=card.source,
        verified_on=card.verified_on,
        stale=is_stale(card.verified_on, today),
    )


def payer_rules(store: CorpusStore, payer: str, today: date) -> PayerRulesResult:
    """Return the rule cards of the payer ``payer`` names, one per topic (US-6.2's matching).

    Args:
        store: The global scope.
        payer: The payer name as the agent asked for it; it is never echoed.
        today: The date the stale flag is computed for.

    Raises:
        PayerNotFoundError: No card's payer matches.
        CorpusError: ``store`` is not the global scope.
    """
    cards = payer_rule_cards(store, payer)
    if not cards:
        raise PayerNotFoundError
    return PayerRulesResult(payer=cards[0].payer, cards=[_card(card, today) for card in cards])


def _stage(extracted: bool, diagnosed: bool, drafted: bool) -> CaseStage:
    """The furthest step the case reached."""
    if drafted:
        return "drafted"
    if diagnosed:
        return "diagnosed"
    return "extracted" if extracted else "intake"


def case_summary(cases: CaseService, profile: str, case_id: str) -> CaseSummaryResult:
    """Return ``profile``'s case ``case_id`` reduced to codes, names, and enums (audited).

    The payer is the name of the global rule cards that match the extracted payer, so the
    printed name (which a misread could fill with a patient's name) never leaves the worker. No
    claim number, date, amount, or document text is read into the result.

    Raises:
        CaseNotFoundError: No such case in this profile (also when it has no user scope yet).
    """
    try:
        store = cases.store(profile)
    except ProfileNotFoundError:
        raise CaseNotFoundError from None  # a profile with no cases has no such case either
    store.record(case_id, AuditAction.CASE_SUMMARIZED)
    record = store.case_record(case_id)
    extraction = cases.extraction(store, case_id)
    diagnosis = cases.diagnosis(store, case_id)
    draft = cases.draft(store, case_id)
    deadline = cases.deadline(extraction)
    printed_payer = None if extraction is None else extraction.payer_name.value
    cards = payer_rule_cards(cases.corpus.global_store(), printed_payer) if printed_payer else []
    outcome = store.outcome(case_id)
    return CaseSummaryResult(
        case_id=record.case_id,
        status="open" if record.closed_at is None else "closed",
        stage=_stage(extraction is not None, diagnosis is not None, draft is not None),
        outcome=None if outcome is None else outcome.outcome,
        payer=cards[0].payer if cards else None,
        codes=case_codes(extraction) if extraction is not None else [],
        denial_reason=None if diagnosis is None else diagnosis.denial_reason,
        appeal_likelihood=None if diagnosis is None else diagnosis.appeal_likelihood,
        diagnosis_stale=(
            diagnosis is not None
            and (extraction is None or diagnosis.extraction_digest != extraction.digest())
        ),
        deadline=None if deadline is None else deadline.status,
        documents=len(cases.documents(store, case_id)),
        needs_confirmation=0 if extraction is None else len(extraction.needs_confirmation()),
    )
