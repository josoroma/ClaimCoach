"""Typed parameters and results of the ClaimCoach agent tools.

Implements: US-9.1 (``ExplainCodeParams``/``ExplainCodeResult``, ``PayerRulesParams``/
``PayerRulesResult``: global reference material only), US-9.2 (``CaseSummaryParams`` takes a case
ID and nothing else; ``CaseSummaryResult`` holds codes, the payer as its rule cards name it, the
case's status, and enums — never case text). Rules: ES-1 (Pydantic v2, ``extra="forbid"``,
frozen; the tool JSON schemas are generated from the parameter models), BR-3 (tools take and
return only IDs, codes, payer names, and redacted summaries), PC-8.

This module imports nothing heavier than Pydantic, so the gateway can use it.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from claimcoach.cases.diagnosis import AppealLikelihood, CaseCode, DeadlineStatus, DenialReason
from claimcoach.corpus.types import CaseId, CaseOutcome

__all__ = [
    "MAX_REFERENCE_CHARS",
    "CaseStage",
    "CaseSummaryParams",
    "CaseSummaryResult",
    "CodeExplanation",
    "ExplainCodeParams",
    "ExplainCodeResult",
    "PayerRuleCard",
    "PayerRulesParams",
    "PayerRulesResult",
    "ToolParams",
    "ToolResult",
]

MAX_REFERENCE_CHARS: Final = 4000
"""Longest reference text one entry or card returns; longer text is cut and flagged
``truncated``, so a result always fits one redaction call (``MAX_TEXT_CHARS``)."""

Text = Annotated[str, StringConstraints(min_length=1, max_length=MAX_REFERENCE_CHARS)]
Title = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Source = Annotated[str, StringConstraints(min_length=1, max_length=500)]
PayerName = Annotated[str, StringConstraints(min_length=1, max_length=80)]
"""A payer as the global corpus's rule cards name it."""


class ToolParams(BaseModel):
    """Base of every tool's arguments: unknown keys are refused, never ignored."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolResult(BaseModel):
    """Base of every tool's result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: Literal[True] = True


class ExplainCodeParams(ToolParams):
    """Arguments of ``claimcoach_explain_code``."""

    code: str = Field(
        min_length=1,
        max_length=16,
        pattern=r"^[A-Za-z0-9-]+$",
        description="CARC, RARC, or group code, e.g. CO-197, 197, N290, or CO.",
    )


class PayerRulesParams(ToolParams):
    """Arguments of ``claimcoach_payer_rules``."""

    payer: str = Field(min_length=1, max_length=120, description="Payer name.")


class CaseSummaryParams(ToolParams):
    """Arguments of ``claimcoach_case_summary``; a case ID only, never case content (BR-3)."""

    case_id: CaseId = Field(description="ClaimCoach case ID.")


class CodeExplanation(BaseModel):
    """One global code entry.

    Attributes:
        code_set: ``CARC``, ``RARC``, or ``GROUP``.
        code: The code within its set (``197``, ``N290``, ``CO``).
        title: The entry's title.
        explanation: The entry's text, at most ``MAX_REFERENCE_CHARS``.
        truncated: The stored text was longer and was cut.
        source: Where the entry comes from.
        verified_on: When the manager last verified it.
        stale: Verified longer ago than ``STALE_AFTER_DAYS``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    code_set: Literal["CARC", "RARC", "GROUP"]
    code: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{1,8}$")]
    title: Title
    explanation: Text
    truncated: bool = False
    source: Source
    verified_on: date
    stale: bool


class ExplainCodeResult(ToolResult):
    """What ``claimcoach_explain_code`` answers.

    Attributes:
        code: The code as asked, normalized (``co-197`` → ``CO-197``).
        entries: The global entries for it: the group code's, then the reason or remark code's.
    """

    code: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9-]{1,16}$")]
    entries: list[CodeExplanation] = Field(min_length=1, max_length=2)


class PayerRuleCard(BaseModel):
    """One payer rule card.

    Attributes:
        payer: The card's payer.
        topic: What the rule is about.
        title: The card's title.
        body: The rule, at most ``MAX_REFERENCE_CHARS``.
        truncated: The stored rule was longer and was cut.
        required_documents: On a ``required_docs`` card, what an appeal needs.
        appeal_limit_days: On an ``appeal_levels`` card, the days from the denial to appeal.
        source: Where the rule comes from.
        verified_on: When the manager last verified it.
        stale: Verified longer ago than ``STALE_AFTER_DAYS``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    payer: PayerName
    topic: Literal["timely_filing", "appeal_levels", "required_docs", "submission", "other"]
    title: Title
    body: Text
    truncated: bool = False
    required_documents: list[Annotated[str, StringConstraints(max_length=200)]] = Field(
        default_factory=list, max_length=30
    )
    appeal_limit_days: int | None = Field(default=None, ge=1, le=3650)
    source: Source
    verified_on: date
    stale: bool


class PayerRulesResult(ToolResult):
    """What ``claimcoach_payer_rules`` answers: the matched payer's cards, one per topic.

    Attributes:
        payer: The payer as its cards name it (the asked name is never echoed).
        cards: The cards, in topic order.
    """

    payer: PayerName
    cards: list[PayerRuleCard] = Field(min_length=1, max_length=5)


CaseStage = Literal["intake", "extracted", "diagnosed", "drafted"]
"""How far the case got: documents only, fields extracted, diagnosed, or an appeal drafted."""


class CaseSummaryResult(ToolResult):
    """What ``claimcoach_case_summary`` answers: a case reduced to codes, names, and enums.

    Attributes:
        case_id: The case.
        status: ``open``, or ``closed`` once its outcome was recorded.
        stage: How far the case got.
        outcome: How it ended, once recorded.
        payer: The payer as the global rule cards name it; ``None`` when no card matches (the
            printed name is never returned).
        codes: The case's adjustment and remark codes (``CO-197``, ``N286``).
        denial_reason: The diagnosis's denial family, when the case was diagnosed.
        appeal_likelihood: The diagnosis's appeal likelihood, when the case was diagnosed.
        diagnosis_stale: The fields changed after the diagnosis, so it may be out of date.
        deadline: Whether the appeal deadline is known, or which input it lacks (no dates).
        documents: How many source documents the case holds.
        needs_confirmation: How many fields the biller still has to confirm.
    """

    case_id: CaseId
    status: Literal["open", "closed"]
    stage: CaseStage
    outcome: CaseOutcome | None = None
    payer: PayerName | None = None
    codes: list[CaseCode] = Field(default_factory=list, max_length=200)
    denial_reason: DenialReason | None = None
    appeal_likelihood: AppealLikelihood | None = None
    diagnosis_stale: bool = False
    deadline: DeadlineStatus | None = None
    documents: int = Field(ge=0)
    needs_confirmation: int = Field(ge=0)
