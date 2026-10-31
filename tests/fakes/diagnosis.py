"""Helpers for diagnosis tests: role-routed fake models, model replies, code notes, rule cards.

Implements: US-6.1 test harness (ES-4: offline; one fake OpenAI-compatible server per model role
stands in for Qwen3-8B, so each role answers its own prompt), US-6.2 (the explanation reply for
Qwen3-14B and ACME's rule cards). Nothing here names a person.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, timedelta
from typing import Any, Final

from claimcoach.corpus.bundle import CodeEntry, CorpusBundle, RuleCard
from claimcoach.models.manager import ModelEndpoint, ModelUnavailableError
from claimcoach.models.types import ModelRole

__all__ = [
    "ACME_DOCUMENTS",
    "CLASSIFICATION",
    "CODE_BUNDLE",
    "EXPLANATION",
    "RULE_BUNDLE",
    "classification_reply",
    "explanation_reply",
    "role_models",
    "rule_card",
]

CLASSIFICATION: Final[dict[str, Any]] = {
    "denial_reason": "prior_authorization",
    "appeal_likelihood": "high",
    "reasons": [
        "The payer denied the line for a missing authorization (CO-197).",
        "Payers often accept a retroactive authorization with the medical records.",
    ],
}
"""What a good classification model answers for the synthetic CO-197 / N286 case."""


def classification_reply(**changes: Any) -> str:
    """The JSON the classification model answers, with top-level ``changes`` applied."""
    return json.dumps(CLASSIFICATION | changes)


EXPLANATION: Final[dict[str, Any]] = {
    "explanation": (
        "The payer refused the visit because no authorization was on file for it. Ask the payer "
        "whether a retroactive authorization is possible, then appeal with the records."
    ),
    "root_cause": "The authorization was not requested before the visit.",
    "checklist": [
        {"item": 3, "why": "Shows the visit was medically necessary."},
        {"item": 1, "why": "The appeal must cite the denial."},
    ],
}
"""What a good explanation model answers for the synthetic case with ACME's rule cards."""


def explanation_reply(**changes: Any) -> str:
    """The JSON the explanation model answers, with top-level ``changes`` applied."""
    return json.dumps(EXPLANATION | changes)


def _code(code_set: str, code: str, title: str, body: str) -> CodeEntry:
    return CodeEntry.model_validate(
        {
            "kind": "code",
            "code_set": code_set,
            "code": code,
            "title": title,
            "body": body,
            "source": "Synthetic code list for tests",
            "verified_on": date(2026, 9, 1),
        }
    )


CODE_BUNDLE: Final = CorpusBundle(
    items=[
        _code("CARC", "197", "Precertification absent", "Authorization was not obtained."),
        _code("RARC", "N286", "Referring provider identifier", "The referring NPI is missing."),
        _code("GROUP", "CO", "Contractual obligation", "The provider may not bill the patient."),
        _code("CARC", "18", "Duplicate claim", "Exact duplicate claim or service."),
    ]
)
"""Code notes for the synthetic case's codes, plus one (CARC 18) the case does not have."""


ACME_DOCUMENTS: Final = (
    "Copy of the denial notice or remittance",
    "Prior authorization number or retro-authorization request",
    "Medical records for the date of service",
    "Signed appeal form",
)
"""The documents ACME's required_docs card lists, in its order."""


def rule_card(payer: str, topic: str, **extra: Any) -> RuleCard:
    """A rule card for ``payer`` on ``topic``, verified 30 days ago (not stale) unless changed."""
    return RuleCard.model_validate(
        {
            "kind": "rule_card",
            "payer": payer,
            "topic": topic,
            "title": f"{payer} {topic.replace('_', ' ')}",
            "body": f"Synthetic {topic.replace('_', ' ')} rule for {payer}.",
            "source": f"{payer} provider manual (synthetic)",
            "verified_on": date.today() - timedelta(days=30),
        }
        | extra
    )


RULE_BUNDLE: Final = CorpusBundle(
    items=[
        rule_card("ACME Health", "required_docs", required_documents=list(ACME_DOCUMENTS)),
        rule_card("ACME Health", "appeal_levels"),
        rule_card("ACME", "required_docs", required_documents=["Wrong card: fewer words"]),
        rule_card("Other Payer", "required_docs", required_documents=["Another payer's form"]),
    ]
)
"""ACME Health's cards, a shorter "ACME" payer the longest match must beat, and another payer."""


def role_models(
    urls: Mapping[ModelRole, str],
) -> Callable[[ModelRole], AbstractAsyncContextManager[ModelEndpoint]]:
    """A ``ModelManager.use`` stand-in routing each role to its own server; others are missing."""

    @asynccontextmanager
    async def use(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        if role not in urls:
            raise ModelUnavailableError
        yield ModelEndpoint(role=role, base_url=urls[role])

    return use
