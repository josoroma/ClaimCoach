"""Explanation: a diagnosed case in plain language, with its missing-documentation checklist.

Implements: US-6.2 (``Explanation`` and ``ChecklistItem``, re-exported from ``cases.diagnosis``;
the registered ``explanation`` template; ``explain``, which asks the ``explanation`` role and builds
the checklist from the payer's ``required_docs`` card by item number). Rules: BR-1 and BR-2 (the
model is held through ``ModelManager.use`` on loopback), BR-5 (the prompt holds this case's own
fields and global reference text only), BR-10 (every per-call text is a data block; the reply is
parsed as JSON into a typed model and nothing else), BR-14.

The model never writes a checklist item: it picks item numbers from the card's numbered list, and
the card supplies the words (design decision 2).
"""

from __future__ import annotations

import json
from typing import Annotated, Final

import httpx
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)

from claimcoach.cases.diagnosis import REASON_GUIDE, ChecklistItem, Diagnosis, Explanation, Reason
from claimcoach.cases.errors import DiagnosisFailedError
from claimcoach.cases.extraction import CaseExtraction
from claimcoach.corpus.bundle import RuleCard
from claimcoach.corpus.types import Document
from claimcoach.models.chat import chat_completion
from claimcoach.models.manager import ModelEndpoint
from claimcoach.pipeline.facts import (
    case_facts,
    code_notes_text,
    required_documents_text,
    rule_cards_text,
)
from claimcoach.pipeline.replies import clip, clipped, each_valid, reply_object
from claimcoach.prompts.builder import DataItem, PromptParts, build_prompt, define_template

__all__ = [
    "EXPLANATION_TEMPLATE",
    "ChecklistItem",
    "Explanation",
    "ExplanationReply",
    "checklist_from",
    "explain",
    "parse_explanation",
    "required_documents",
]

MAX_TOKENS: Final = 1536
EXPLAIN_TIMEOUT: Final = 600.0
"""Seconds for one explanation: a 14B model writes a few hundred tokens in well under a minute."""

EXPLANATION_TEMPLATE: Final = define_template(
    "explanation",
    system=(
        "You coach an entry-level medical biller through a denied US health-insurance claim. You "
        "explain denials in plain language, without unexplained jargon, using only the case "
        "facts, the classification, the code notes, and the payer's rule cards you are given. "
        "/no_think"
    ),
    instructions=(
        "Explain the denial described in the data. Return one JSON object and nothing else, with "
        "these keys: explanation (two to five plain-language sentences: what the payer decided, "
        "what the codes mean, and what the biller can do next); root_cause (one or two sentences "
        "naming the most likely underlying cause); checklist (a list of objects with item, the "
        "number of a document in the required-documents list, and why, one short sentence on why "
        "this appeal needs it). Choose only numbers from the required-documents list, and only "
        "the documents this appeal needs; use an empty list when no list is given. Never name a "
        "document that is not on the list. null means a value could not be read."
    ),
)


def _why(value: object) -> str | None:
    """A reason that is blank or not text is no reason; a long one is clipped to 300 characters."""
    return (clip(value, 300) or None) if isinstance(value, str) else None


class _Entry(BaseModel):
    """One checklist entry as the model answered it."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    item: StrictInt
    why: Annotated[Reason | None, BeforeValidator(_why)] = None


Entries = Annotated[list[_Entry], BeforeValidator(each_valid(TypeAdapter(_Entry)))]


class ExplanationReply(BaseModel):
    """The explanation model's reply, validated.

    Attributes:
        explanation: The plain-language explanation.
        root_cause: The likely root cause.
        checklist: Entries that name a document by its number; malformed ones are dropped.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    explanation: Annotated[
        str,
        BeforeValidator(clipped(2000)),
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    ]
    root_cause: Annotated[
        str,
        BeforeValidator(clipped(500)),
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ]
    checklist: Entries = Field(default_factory=list)

    def as_explanation(self) -> Explanation:
        """The explanation and root cause as stored on the diagnosis."""
        return Explanation(explanation=self.explanation, root_cause=self.root_cause)


def parse_explanation(content: str) -> ExplanationReply | None:
    """Return the reply as an ``ExplanationReply``, or ``None`` when it does not validate."""
    data = reply_object(content)
    if data is None:
        return None
    try:
        return ExplanationReply.model_validate(data)
    except ValidationError:
        return None


def required_documents(cards: list[RuleCard]) -> list[str]:
    """The required documents of the payer's ``required_docs`` card, in the card's order."""
    return next((card.required_documents for card in cards if card.topic == "required_docs"), [])


def checklist_from(entries: list[_Entry], documents: list[str]) -> list[ChecklistItem]:
    """Build the checklist from the model's item numbers; the card supplies every document's text.

    Numbers outside the list and repeats are dropped, and the card's order is kept. When the card
    lists documents but no entry names one, every document is listed without a reason.
    """
    chosen: dict[int, str | None] = {}
    for entry in entries:
        if 1 <= entry.item <= len(documents) and entry.item not in chosen:
            chosen[entry.item] = entry.why
    if not chosen:
        return [ChecklistItem(document=document) for document in documents]
    return [ChecklistItem(document=documents[n - 1], why=chosen[n]) for n in sorted(chosen)]


def _classification(diagnosis: Diagnosis) -> str:
    return json.dumps(
        {
            "denial_reason": diagnosis.denial_reason.value,
            "meaning": REASON_GUIDE[diagnosis.denial_reason],
            "appeal_likelihood": diagnosis.appeal_likelihood.value,
            "reasons": diagnosis.likelihood_reasons,
        },
        indent=1,
    )


async def explain(  # noqa: PLR0913 - one request: endpoint, the case, its references, transport
    endpoint: ModelEndpoint,
    extraction: CaseExtraction,
    diagnosis: Diagnosis,
    notes: list[Document],
    cards: list[RuleCard],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[Explanation, list[ChecklistItem]]:
    """Ask the explanation model about one classified case.

    Args:
        endpoint: The ``explanation`` role, held through ``ModelManager.use``.
        extraction: The case's fields.
        diagnosis: The case's classification.
        notes: Global code entries for the case's codes.
        cards: The payer's rule cards (``corpus.lookup.payer_rule_cards``).
        transport: Optional httpx transport (tests).

    Returns:
        The explanation and the checklist.

    Raises:
        DiagnosisFailedError: The reply does not validate.
        ModelUnavailableError: The model did not answer.
    """
    documents = required_documents(cards)
    data = (
        DataItem(label="case_facts", text=json.dumps(case_facts(extraction), indent=1)),
        DataItem(label="classification", text=_classification(diagnosis)),
        DataItem(label="code_notes", text=code_notes_text(notes)),
        DataItem(label="rule_cards", text=rule_cards_text(cards)),
        DataItem(label="required_documents", text=required_documents_text(documents)),
    )
    prompt = build_prompt(PromptParts(template=EXPLANATION_TEMPLATE, data=data))
    reply = await chat_completion(
        endpoint, prompt, max_tokens=MAX_TOKENS, timeout=EXPLAIN_TIMEOUT, transport=transport
    )
    parsed = parse_explanation(reply.content)
    if parsed is None:
        raise DiagnosisFailedError
    return parsed.as_explanation(), checklist_from(parsed.checklist, documents)
