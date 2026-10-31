"""Drafting: a diagnosed case's appeal letter, from the payer's rule cards and a letter template.

Implements: US-7.1 (``DraftRequest`` and ``AppealDraft``, re-exported from ``letters.types``; the
registered ``appeal_draft`` template; ``template_ids``, the template a draft asks for;
``draft_letter``, which asks the ``drafting`` role; ``Drafter``, the job runner that reads the
case's current diagnosis, drafts, and stores the draft). Rules: BR-1 and BR-2 (the model is held
through ``ModelManager.use`` on loopback), BR-4 (the draft is stored with the fixed label "draft for
human review"; nothing here sends it anywhere), BR-5 (the prompt holds this case's own fields and
global reference text only), BR-10 (every per-call text is a data block; the reply is parsed as
JSON into a typed model and nothing else), BR-12 (the 27B model loads under the memory guard),
BR-14 (logs carry error types only; the draft is sealed in the case).
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Final

import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, ValidationError

from claimcoach.cases.diagnosis import REASON_GUIDE, DenialReason, Diagnosis
from claimcoach.cases.errors import DraftingFailedError, NoLetterTemplateError
from claimcoach.cases.extraction import CaseExtraction
from claimcoach.cases.service import CaseService
from claimcoach.corpus.bundle import LetterTemplate, RuleCard
from claimcoach.corpus.lookup import letter_template, payer_rule_cards
from claimcoach.corpus.types import utc_now
from claimcoach.events import Report
from claimcoach.letters.types import DRAFT_LABEL, MAX_LETTER_CHARS, AppealDraft, DraftRequest
from claimcoach.logs import get_logger
from claimcoach.models.chat import chat_completion
from claimcoach.models.manager import EndpointProvider, ModelEndpoint
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.facts import (
    letter_facts,
    required_documents_text,
    rule_cards_text,
    value_of,
)
from claimcoach.pipeline.replies import clipped, reply_object
from claimcoach.prompts.builder import DataItem, PromptParts, build_prompt, define_template

__all__ = [
    "DRAFT_LABEL",
    "DRAFT_TEMPLATE",
    "AppealDraft",
    "DraftRequest",
    "Drafter",
    "LetterReply",
    "draft_letter",
    "parse_letter",
    "template_ids",
]

MAX_TOKENS: Final = 8192
"""Completion budget: room for a letter of ``MAX_LETTER_CHARS`` (about 5000 tokens) as JSON; a
two-page letter is about 1500."""
DRAFT_TIMEOUT: Final = 1800.0
"""Seconds for one draft: a 27B model writes a letter in a few minutes."""
TEMPLATE_CHARS: Final = 8000
"""Characters of a template's body sent to the model."""
DEFAULT_TEMPLATE: Final = "appeal"

_log = get_logger("claimcoach.letters")

DRAFT_TEMPLATE: Final = define_template(
    "appeal_draft",
    system=(
        "You draft appeal letters for a medical billing office, for a person to review, edit, and "
        "send. You write formal, factual, courteous letters to a health-insurance payer, using "
        "only the case facts, the diagnosis, the payer's rule cards, and the letter template you "
        "are given. /no_think"
    ),
    instructions=(
        "Draft the appeal letter for the denied claim described in the data. Follow the letter "
        "template's structure and wording where it fits this case. Cite the claim number, the "
        "denial date, the dates of service, the procedure codes, and the adjustment and remark "
        "codes as they appear in the case facts. Argue from the diagnosis and the payer's rule "
        "cards; never invent a rule, a date, an amount, or a document. Write a bracketed "
        "placeholder for anything the data does not give, such as [Patient name], [Member ID], "
        "[Provider name and NPI], [Practice address], and [Signature]. List the enclosures from "
        "the enclosures list, in its order. Return one JSON object and nothing else, with one key: "
        "letter (the whole letter as plain text, paragraphs separated by blank lines). null means "
        "a value could not be read."
    ),
)


class LetterReply(BaseModel):
    """The drafting model's reply, validated.

    Attributes:
        letter: The letter, clipped to ``MAX_LETTER_CHARS``; not blank.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    letter: Annotated[
        str,
        BeforeValidator(clipped(MAX_LETTER_CHARS)),
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_LETTER_CHARS),
    ]


def parse_letter(content: str) -> str | None:
    """Return the letter in a reply, or ``None`` when the reply does not validate."""
    data = reply_object(content)
    if data is None:
        return None
    try:
        return LetterReply.model_validate(data).letter
    except ValidationError:
        return None


def template_ids(reason: DenialReason, request: DraftRequest) -> list[str]:
    """The template IDs a draft asks for, best first (design decision 3).

    The requested one only; otherwise ``appeal-<reason>`` (``prior_authorization`` as
    ``appeal-prior-authorization``), then ``appeal``.
    """
    if request.template_id is not None:
        return [request.template_id]
    return [f"{DEFAULT_TEMPLATE}-{reason.value.replace('_', '-')}", DEFAULT_TEMPLATE]


def _diagnosis_text(diagnosis: Diagnosis) -> str:
    explanation = diagnosis.explanation
    return json.dumps(
        {
            "denial_reason": diagnosis.denial_reason.value,
            "meaning": REASON_GUIDE[diagnosis.denial_reason],
            "appeal_likelihood": diagnosis.appeal_likelihood.value,
            "reasons": diagnosis.likelihood_reasons,
            "explanation": None if explanation is None else explanation.explanation,
            "root_cause": None if explanation is None else explanation.root_cause,
        },
        indent=1,
    )


def _template_text(template: LetterTemplate) -> str:
    return f"{template.template_id}: {template.title}\n{template.body[:TEMPLATE_CHARS]}"


async def draft_letter(  # noqa: PLR0913 - one request: endpoint, the case, its references, transport
    endpoint: ModelEndpoint,
    extraction: CaseExtraction,
    diagnosis: Diagnosis,
    cards: list[RuleCard],
    template: LetterTemplate,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Ask the drafting model for one case's appeal letter.

    Args:
        endpoint: The ``drafting`` role, held through ``ModelManager.use``.
        extraction: The case's fields.
        diagnosis: The case's current diagnosis.
        cards: The payer's rule cards (``corpus.lookup.payer_rule_cards``).
        template: The letter template.
        transport: Optional httpx transport (tests).

    Returns:
        The letter text.

    Raises:
        DraftingFailedError: The reply holds no usable letter.
        ModelUnavailableError: The model did not answer.
    """
    enclosures = [item.document for item in diagnosis.checklist]
    data = (
        DataItem(label="case_facts", text=json.dumps(letter_facts(extraction), indent=1)),
        DataItem(label="diagnosis", text=_diagnosis_text(diagnosis)),
        DataItem(label="enclosures", text=required_documents_text(enclosures)),
        DataItem(label="rule_cards", text=rule_cards_text(cards)),
        DataItem(label="letter_template", text=_template_text(template)),
    )
    prompt = build_prompt(PromptParts(template=DRAFT_TEMPLATE, data=data))
    reply = await chat_completion(
        endpoint, prompt, max_tokens=MAX_TOKENS, timeout=DRAFT_TIMEOUT, transport=transport
    )
    letter = parse_letter(reply.content)
    if letter is None:
        if reply.truncated:  # the operator can tell a cut-off letter from an unusable one
            _log.warning("drafting reply stopped at max_tokens before the letter ended")
        raise DraftingFailedError
    return letter


class Drafter:
    """Drafts a diagnosed case's appeal letter and stores it with the case.

    Args:
        cases: Where the diagnosis is read and the draft stored.
        models: ``ModelManager.use`` (or a test double).
        request: The draft request (which template); the route binds it with ``for_request``.
        transport: Optional httpx transport for the model call (tests).
    """

    def __init__(
        self,
        cases: CaseService,
        models: EndpointProvider,
        request: DraftRequest | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Keep the collaborators; nothing runs until ``run``."""
        self.cases = cases
        self.models = models
        self.request = request or DraftRequest()
        self._transport = transport

    def for_request(self, request: DraftRequest) -> Drafter:
        """Return a drafter for one request, sharing this one's collaborators."""
        return Drafter(self.cases, self.models, request, transport=self._transport)

    def check(self, profile: str, case_id: str) -> None:
        """Refuse drafting before a job starts (design decision 2; store reads: run in a thread).

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case, or an ID events cannot carry.
            CaseClosedError: The case is closed or purged.
            NotDiagnosedError: The case has no diagnosis of its current fields.
            NoLetterTemplateError: No requested template is in the global corpus.
        """
        self._inputs(profile, case_id)

    def _inputs(
        self, profile: str, case_id: str
    ) -> tuple[CaseExtraction, Diagnosis, list[RuleCard], LetterTemplate]:
        """The case's fields and diagnosis, the payer's rule cards, and the template to use.

        The case must still be open: a case closed after Draft appeal never loads the model.
        """
        self.cases.check_draftable(profile, case_id)
        extraction, diagnosis = self.cases.draft_inputs(profile, case_id)
        store = self.cases.corpus.global_store()
        template = letter_template(store, template_ids(diagnosis.denial_reason, self.request))
        if template is None:
            raise NoLetterTemplateError
        cards = payer_rule_cards(store, value_of(extraction.payer_name))
        return extraction, diagnosis, cards, template

    async def run(self, profile: str, case_id: str, report: Report) -> AppealDraft:
        """Draft the case's letter, store it, and report progress: ``drafting`` (0), ``done`` (1).

        Raises:
            CaseClosedError: The case is closed (checked before the model loads).
            NotDiagnosedError: The case has no diagnosis of its current fields.
            NoLetterTemplateError: No requested template is in the global corpus.
            DraftingFailedError: The model's reply held no letter; nothing is stored.
            DraftEditedError: The biller saved edits while the model wrote; they are kept.
            ModelUnavailableError: The model is missing or stopped answering.
            ModelBusyError: The memory guard kept the model queued too long.
            CorpusError: The case store failed (for example the case was closed meanwhile).
        """
        started = utc_now()
        report("drafting", 0.0)
        extraction, diagnosis, cards, template = await asyncio.to_thread(
            self._inputs, profile, case_id
        )
        async with self.models(ModelRole.DRAFTING) as endpoint:
            text = await draft_letter(
                endpoint, extraction, diagnosis, cards, template, transport=self._transport
            )
        draft = AppealDraft(
            text=text,
            template_id=template.template_id,
            rule_cards=[card.key for card in cards],
            extraction_digest=extraction.digest(),
            diagnosed_at=diagnosis.diagnosed_at,
            drafted_at=utc_now(),
        )
        # Edits the biller saved while the model wrote are kept (US-7.2 decision 1).
        await asyncio.to_thread(
            lambda: self.cases.save_draft(profile, case_id, draft, started=started)
        )
        report("done", 1.0)
        return draft
