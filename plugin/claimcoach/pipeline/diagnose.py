"""Diagnosis: a case's extraction classified into a denial reason and an appeal likelihood.

Implements: US-6.1 (``DenialReason``, ``AppealLikelihood``, and ``Diagnosis``, re-exported from
``cases.diagnosis``; the registered ``classification`` template; ``Diagnoser``, the job runner that
reads the stored extraction, asks the ``classification`` role, and stores the diagnosis), US-6.2
(``Diagnoser``'s ``explaining`` stage: the ``explanation`` role adds the explanation and checklist,
stored after the classification so a failure there keeps it). Rules:
BR-1 and BR-2 (the model is held through ``ModelManager.use`` on loopback), BR-5 (the prompt holds
this case's own fields and global code notes only), BR-10 (case facts and code notes are data
blocks of a ``BuiltPrompt``; the reply is parsed as JSON into a typed model and nothing else),
BR-14 (logs carry error types only; the diagnosis is sealed in the case).

Only the facts the label depends on reach the model (design decision 3): the payer, the amounts,
and per line the procedure code, adjustments, and remark codes. The claim number and the service
dates stay out.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import date
from typing import Annotated, Final

import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from claimcoach.cases.diagnosis import (
    REASON_GUIDE,
    AppealLikelihood,
    DenialReason,
    Diagnosis,
    Reason,
    RuleCardRef,
)
from claimcoach.cases.errors import DiagnosisFailedError
from claimcoach.cases.extraction import CaseExtraction
from claimcoach.cases.service import CaseService
from claimcoach.corpus.bundle import RuleCard, is_stale
from claimcoach.corpus.lookup import code_entries, payer_rule_cards
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import Document, utc_now
from claimcoach.events import Report
from claimcoach.models.chat import chat_completion
from claimcoach.models.manager import EndpointProvider, ModelEndpoint
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.explain import explain
from claimcoach.pipeline.facts import case_facts, code_notes_text, value_of
from claimcoach.pipeline.replies import clip, reply_object
from claimcoach.prompts.builder import DataItem, PromptParts, build_prompt, define_template

__all__ = [
    "CLASSIFICATION_TEMPLATE",
    "AppealLikelihood",
    "Classification",
    "DenialReason",
    "Diagnoser",
    "Diagnosis",
    "case_codes",
    "case_facts",
    "classify",
    "code_keys",
    "parse_classification",
]

MAX_TOKENS: Final = 1024
MAX_REASONS: Final = 5
REASON_CHARS: Final = 300
CLASSIFY_TIMEOUT: Final = 300.0
"""Seconds for one classification: an 8B model answers a short JSON object in seconds."""
MAX_CODES: Final = 200

_GUIDE: Final = "; ".join(f"{reason.value}: {text}" for reason, text in REASON_GUIDE.items())

CLASSIFICATION_TEMPLATE: Final = define_template(
    "classification",
    system=(
        "You analyze denied US health-insurance claims for a medical billing office. You classify "
        "why the claim was denied and judge whether an appeal is likely to overturn the denial, "
        "using only the case facts and code notes you are given. /no_think"
    ),
    instructions=(
        "Classify the denial described in the data. Return one JSON object and nothing else, "
        "with these keys: denial_reason (exactly one label from the list below); "
        "appeal_likelihood (low, medium, or high); reasons (a list of one to five short, "
        "plain-language sentences explaining the appeal likelihood). Labels and the reason codes "
        f"that usually signal them: {_GUIDE}. Adjustments are written as a group code and a "
        "claim adjustment reason code (CO-197 is group CO, reason 197); a remark code or a code "
        "note can point to a different label than the reason code alone. An appeal is more "
        "likely to succeed when the denial can be fixed or contested with documentation or a "
        "corrected claim, and less likely when it reflects a plan rule such as a coverage gap, "
        "an exhausted benefit, or a missed filing limit. null means a value could not be read."
    ),
)


def _label(value: object) -> object:
    """Normalize a label: ``Prior Authorization`` reads as ``prior_authorization``."""
    if isinstance(value, str):
        return "_".join(value.strip().lower().replace("-", " ").split())
    return value


def _reasons(value: object) -> object:
    """Keep the first five non-blank reasons, each clipped to 300 characters.

    Anything but a list of strings fails validation.
    """
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return [clip(item, REASON_CHARS) for item in value if item.strip()][:MAX_REASONS]
    return value


class Classification(BaseModel):
    """The classification model's reply, validated.

    Attributes:
        denial_reason: One label of the closed set.
        appeal_likelihood: ``low``, ``medium``, or ``high``.
        reasons: One to five reasons for the likelihood.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    denial_reason: Annotated[DenialReason, BeforeValidator(_label)]
    appeal_likelihood: Annotated[AppealLikelihood, BeforeValidator(_label)]
    reasons: Annotated[list[Reason], BeforeValidator(_reasons), Field(min_length=1, max_length=5)]


def parse_classification(content: str) -> Classification | None:
    """Return the reply as a ``Classification``, or ``None`` when it does not validate."""
    data = reply_object(content)
    if data is None:
        return None
    try:
        return Classification.model_validate(data)
    except ValidationError:
        return None


def _code_fields(extraction: CaseExtraction) -> Iterator[tuple[str | None, str | None, str | None]]:
    """Yield ``(group, carc, rarc)`` for every adjustment and remark code, claim level first."""
    for adjustments, remarks in [
        (extraction.adjustments, extraction.rarc_codes),
        *((line.adjustments, line.rarc_codes) for line in extraction.lines),
    ]:
        for adjustment in adjustments:
            yield value_of(adjustment.group_code), value_of(adjustment.carc), None
        for remark in remarks:
            yield None, None, value_of(remark)


def case_codes(extraction: CaseExtraction) -> list[str]:
    """Return the case's codes as the pane shows them (``CO-197``, ``197``, ``N286``), once each."""
    codes: dict[str, None] = {}
    for group, carc, rarc in _code_fields(extraction):
        if carc is not None:
            codes[f"{group}-{carc}" if group else carc] = None
        if rarc is not None:
            codes[rarc] = None
    return list(codes)[:MAX_CODES]


def code_keys(extraction: CaseExtraction) -> list[str]:
    """Return the global code-entry keys for the case's codes (``GROUP/CO``, ``CARC/197``, …)."""
    keys: dict[str, None] = {}
    for group, carc, rarc in _code_fields(extraction):
        for code_set, code in (("GROUP", group), ("CARC", carc), ("RARC", rarc)):
            if code is not None:
                keys[f"{code_set}/{code}"] = None
    return list(keys)


async def classify(
    endpoint: ModelEndpoint,
    extraction: CaseExtraction,
    notes: list[Document],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Classification:
    """Ask the classification model about one case.

    Args:
        endpoint: The ``classification`` role, held through ``ModelManager.use``.
        extraction: The case's fields.
        notes: Global code entries for the case's codes.
        transport: Optional httpx transport (tests).

    Raises:
        DiagnosisFailedError: The reply does not validate.
        ModelUnavailableError: The model did not answer.
    """
    data = (
        DataItem(label="case_facts", text=json.dumps(case_facts(extraction), indent=1)),
        DataItem(label="code_notes", text=code_notes_text(notes)),
    )
    prompt = build_prompt(PromptParts(template=CLASSIFICATION_TEMPLATE, data=data))
    reply = await chat_completion(
        endpoint, prompt, max_tokens=MAX_TOKENS, timeout=CLASSIFY_TIMEOUT, transport=transport
    )
    classification = parse_classification(reply.content)
    if classification is None:
        raise DiagnosisFailedError
    return classification


class Diagnoser:
    """Diagnoses an extracted case and stores the result with it.

    Args:
        cases: Where the extraction is read and the diagnosis stored.
        models: ``ModelManager.use`` (or a test double).
        transport: Optional httpx transport for the model calls (tests).
    """

    def __init__(
        self,
        cases: CaseService,
        models: EndpointProvider,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Keep the collaborators; nothing runs until ``run``."""
        self.cases = cases
        self.models = models
        self._transport = transport

    async def run(self, profile: str, case_id: str, report: Report) -> Diagnosis:
        """Diagnose the case, store the diagnosis after each step, and report progress.

        ``classifying`` (0), then ``explaining`` (0.5) once the classification is stored, then
        ``done`` (1) once the explanation and checklist are stored with it.

        Raises:
            NotExtractedError: The case has no extraction.
            DiagnosisFailedError: A model's reply did not validate; nothing of that step is
                stored.
            ModelUnavailableError: A model is missing or stopped answering.
            ModelBusyError: The memory guard kept a model queued too long.
            CorpusError: The case store failed (for example the case was closed meanwhile).
        """
        report("classifying", 0.0)
        extraction = await asyncio.to_thread(self.cases.extraction_of, profile, case_id)
        notes, cards = await asyncio.to_thread(
            _references, self.cases.corpus.global_store(), extraction
        )
        async with self.models(ModelRole.CLASSIFICATION) as endpoint:
            classification = await classify(endpoint, extraction, notes, transport=self._transport)
        today = date.today()
        diagnosis = Diagnosis(
            denial_reason=classification.denial_reason,
            appeal_likelihood=classification.appeal_likelihood,
            likelihood_reasons=classification.reasons,
            codes=case_codes(extraction),
            extraction_digest=extraction.digest(),
            diagnosed_at=utc_now(),
            rule_cards=[_reference(card, today) for card in cards],
        )
        await asyncio.to_thread(self.cases.save_diagnosis, profile, case_id, diagnosis)
        report("explaining", 0.5)
        async with self.models(ModelRole.EXPLANATION) as endpoint:
            explanation, checklist = await explain(
                endpoint, extraction, diagnosis, notes, cards, transport=self._transport
            )
        diagnosis = diagnosis.model_copy(
            update={"explanation": explanation, "checklist": checklist}
        )
        await asyncio.to_thread(self.cases.save_diagnosis, profile, case_id, diagnosis)
        report("done", 1.0)
        return diagnosis


def _references(
    store: CorpusStore, extraction: CaseExtraction
) -> tuple[list[Document], list[RuleCard]]:
    """The global code notes and payer rule cards for the case (store reads: run in a thread)."""
    return (
        code_entries(store, code_keys(extraction)),
        payer_rule_cards(store, value_of(extraction.payer_name)),
    )


def _reference(card: RuleCard, today: date) -> RuleCardRef:
    return RuleCardRef(
        key=card.key,
        payer=card.payer,
        topic=card.topic,
        source=card.source,
        verified_on=card.verified_on,
        stale=is_stale(card.verified_on, today),
    )
