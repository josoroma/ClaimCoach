"""Corrected-claim drafting: the changes, planned by fixed rules and explained by the model.

Implements: US-7.4 (``plan_corrections``: design decisions 2 and 3, the lines, fields, current
values, and codes, from the case's codes and extraction only; the registered ``correction_draft``
template; ``parse_corrections``: design decision 4, which refuses a reply that names a code the
case's documents do not hold; ``Corrector``, the ``correct`` job runner that reads the case's
current diagnosis, drafts, and stores the draft). Rules: BR-1 and BR-2 (the model is held through
``ModelManager.use`` on loopback), BR-4 (the draft is stored with the fixed label "draft for human
review"; nothing here sends it anywhere), BR-5 (the prompt holds this case's own fields and global
reference text only), BR-10 (every per-call text is a data block; the reply is parsed as JSON into
a typed model and nothing else), BR-12 (the 27B model loads under the memory guard), BR-14 (logs
carry error types only; the draft is sealed in the case), Non-goals §5 (no new CPT, HCPCS, ICD-10,
or modifier value is ever proposed).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated, Final

import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from claimcoach.cases.diagnosis import Diagnosis
from claimcoach.cases.errors import CorrectionFailedError
from claimcoach.cases.extraction import CaseExtraction, ClaimLine
from claimcoach.cases.service import CaseService
from claimcoach.corpus.bundle import RuleCard
from claimcoach.corpus.lookup import payer_rule_cards
from claimcoach.corpus.types import utc_now
from claimcoach.corrections.remedy import case_code_uses, frequency_code
from claimcoach.corrections.types import (
    EXTRACTED_FIELDS,
    LINE_FIELDS,
    MAX_BECAUSE,
    MAX_CORRECTIONS,
    NOT_IN_DOCUMENTS,
    ClaimCorrection,
    CorrectableField,
    CorrectedClaimDraft,
    CorrectionText,
)
from claimcoach.events import Report
from claimcoach.logs import get_logger
from claimcoach.models.chat import chat_completion
from claimcoach.models.manager import EndpointProvider, ModelEndpoint
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.facts import letter_facts, rule_cards_text, value_of
from claimcoach.pipeline.replies import clipped, reply_object
from claimcoach.prompts.builder import DataItem, PromptParts, build_prompt, define_template

__all__ = [
    "CODE_FIELDS",
    "CORRECTION_TEMPLATE",
    "Corrector",
    "PlannedCorrection",
    "allowed_codes",
    "draft_corrections",
    "parse_corrections",
    "plan_corrections",
]

MAX_TOKENS: Final = 8192
"""Completion budget: 40 changes of two 500-character texts as JSON is about 6000 tokens."""
CORRECTION_TIMEOUT: Final = 1800.0
"""Seconds for one draft: a 27B model writes it in a few minutes."""
TEXT_CHARS: Final = 500

_F = CorrectableField
CODE_FIELDS: Final[dict[str, tuple[CorrectableField, ...]]] = {
    "4": (_F.MODIFIER, _F.PROCEDURE_CODE),
    "5": (_F.PROCEDURE_CODE, _F.PLACE_OF_SERVICE),
    "6": (_F.PROCEDURE_CODE, _F.PATIENT_DEMOGRAPHICS),
    "7": (_F.PROCEDURE_CODE, _F.PATIENT_DEMOGRAPHICS),
    "11": (_F.DIAGNOSIS_POINTER, _F.DIAGNOSIS_CODE),
    "22": (_F.OTHER_INSURANCE,),
    "23": (_F.OTHER_INSURANCE,),
    "31": (_F.MEMBER_ID, _F.PATIENT_DEMOGRAPHICS),
    "97": (_F.MODIFIER,),
    "181": (_F.PROCEDURE_CODE, _F.SERVICE_DATE),
    "182": (_F.MODIFIER, _F.SERVICE_DATE),
    "234": (_F.MODIFIER,),
    "236": (_F.MODIFIER, _F.PROCEDURE_CODE),
    "M51": (_F.PROCEDURE_CODE,),
    "M53": (_F.UNITS,),
    "M76": (_F.DIAGNOSIS_CODE,),
    "M77": (_F.PLACE_OF_SERVICE,),
    "MA61": (_F.MEMBER_ID,),
    "N382": (_F.MEMBER_ID,),
    "MA130": (_F.CLAIM_DATA,),
}
"""The fields each CARC or RARC points at (design decision 3). CARCs are digits or a letter and
digits other than M and N, so the two code sets never share a key."""

_CODE_SHAPED: Final = re.compile(
    r"\b(?:\d{4}[0-9FTU]|[A-V]\d{4}|[A-TV-Z]\d[0-9A-Z](?:\.?[0-9A-Z]{1,4})?)\b"
)
"""A CPT or HCPCS code, or an ICD-10 code with or without its dot: values the draft may only
repeat from the case's documents."""
_MODIFIER_WORD: Final = r"(?i:\bmod(?:ifier)?s?\b)"
_MODIFIERS: Final = (
    re.compile(_MODIFIER_WORD + r"[\s:\"'(\[-]{0,4}[0-9A-Z]{2}\b"),
    re.compile(r"(?<![0-9A-Za-z])-?[0-9A-Z]{2}[\"')\]]?\s+" + _MODIFIER_WORD),
    re.compile(r"\b(?:\d{4}[0-9FTU]|[A-V]\d{4})-[0-9A-Z]{2}\b"),
    re.compile(r"\b(?:XE|XS|XP|XU|GA|GY|GZ|KX|LT|RT|TC|QW|GT|GQ)\b"),
)
"""A modifier value: next to the word modifier (``modifier-59``, ``a 59 modifier``, ``mod "25"``),
after a procedure code (``99213-25``), or a letter modifier on its own (``XS``). The case's
documents never hold a modifier, so the draft may never name one (design decision 2)."""
NOT_CODES: Final = frozenset({"X12", "P2P"})
"""Code-shaped words that name no code: the X12 standard, peer-to-peer review."""

_log = get_logger("claimcoach.corrections")

CORRECTION_TEMPLATE: Final = define_template(
    "correction_draft",
    system=(
        "You explain corrected-claim changes for a medical billing office. A person reviews "
        "each change and makes it in their own billing system. You write short, factual, plain "
        "sentences, using only the case facts, the diagnosis, the planned changes, and the "
        "payer's rule cards you are given. /no_think"
    ),
    instructions=(
        "For every planned change in the data, write what the biller should check or change "
        "(action) and why the payer's codes point there (why). Say what to check and where, "
        "never which new value to enter: never write a procedure, HCPCS, diagnosis, or modifier "
        "code, or any other code or value, that the data does not hold. Never say to send, "
        "submit, or transmit anything. Return one JSON object and nothing else, with one key: "
        "corrections (a list with one object per planned change, each with index, the change's "
        "index from the data; action, at most 500 characters; and why, at most 500 characters)."
    ),
)


@dataclass(frozen=True)
class PlannedCorrection:
    """A change planned by the fixed rules, before the model explains it.

    Attributes:
        line: The service line, from 1; ``None`` for the claim.
        field: What it points at.
        current_value: The extraction's value for it, when it holds one.
        because: The codes that point here, as the diagnosis shows them.
    """

    line: int | None
    field: CorrectableField
    current_value: str | None = None
    because: tuple[str, ...] = ()


@dataclass
class _Plan:
    lines: list[ClaimLine]
    found: dict[tuple[int | None, CorrectableField], list[str]] = field(default_factory=dict)

    def add(self, line: int | None, target: CorrectableField, code: str) -> None:
        codes = self.found.setdefault((line, target), [])
        if code not in codes:
            codes.append(code)

    def point(self, line: int | None, target: CorrectableField, code: str) -> None:
        """A claim-level code points at every line for a line field (the claim's lines read)."""
        if target not in LINE_FIELDS:
            self.add(None, target, code)
        elif line is not None or not self.lines:
            self.add(line, target, code)
        else:
            for number in range(1, len(self.lines) + 1):
                self.add(number, target, code)


def _current(lines: list[ClaimLine], line: int | None, target: CorrectableField) -> str | None:
    if line is None or target not in EXTRACTED_FIELDS:
        return None
    read = lines[line - 1]
    return value_of(
        read.procedure_code if target is CorrectableField.PROCEDURE_CODE else read.service_date
    )


def plan_corrections(extraction: CaseExtraction, diagnosis: Diagnosis) -> list[PlannedCorrection]:
    """The changes the case's codes point at (design decision 3), claim-level first, then by line.

    Current values come from the extraction only (design decision 2). When no code maps to a
    field, one claim-level ``claim_data`` change cites the diagnosis's codes. Every change is
    returned; the draft keeps the first ``MAX_CORRECTIONS`` and counts the rest.
    """
    plan = _Plan(extraction.lines)
    for use in case_code_uses(extraction):
        for target in CODE_FIELDS.get(use.code, ()):
            plan.point(use.line, target, use.shown)
    if not plan.found:
        return [
            PlannedCorrection(
                None, CorrectableField.CLAIM_DATA, None, tuple(diagnosis.codes[:MAX_BECAUSE])
            )
        ]
    ordered = sorted(plan.found.items(), key=lambda item: item[0][0] or 0)  # stable: first seen
    return [
        PlannedCorrection(
            line, target, _current(extraction.lines, line, target), tuple(codes[:MAX_BECAUSE])
        )
        for (line, target), codes in ordered
    ]


def _amounts(extraction: CaseExtraction) -> Iterable[Decimal | None]:
    yield extraction.billed_amount.value
    yield extraction.paid_amount.value
    for adjustment in extraction.adjustments:
        yield adjustment.amount.value
    for line in extraction.lines:
        yield line.billed_amount.value
        yield line.paid_amount.value
        yield from (adjustment.amount.value for adjustment in line.adjustments)


def allowed_codes(extraction: CaseExtraction) -> frozenset[str]:
    """What a code-shaped value in the draft may be: a code or amount the case's documents hold.

    The procedure codes, CARCs, RARCs (as read and as shown), the claim number, and each amount's
    whole and cents digits.
    """
    allowed = {value_of(line.procedure_code) for line in extraction.lines}
    allowed.add(value_of(extraction.claim_id))
    for use in case_code_uses(extraction):
        allowed |= {use.code, use.shown}
    for amount in _amounts(extraction):
        if amount is not None:
            allowed |= set(re.findall(r"\d+", f"{abs(amount):.2f}"))
    return frozenset(code for code in allowed if code is not None)


def _invents(text: str, allowed: frozenset[str]) -> bool:
    """Whether ``text`` names a modifier, or a code-shaped value the case's documents lack."""
    if any(pattern.search(text) for pattern in _MODIFIERS):
        return True
    return any(
        code not in allowed and code not in NOT_CODES
        for code in (match.group(0) for match in _CODE_SHAPED.finditer(text))
    )


class _ReplyItem(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    index: int = Field(ge=0, strict=True)
    action: Annotated[CorrectionText, BeforeValidator(clipped(TEXT_CHARS))]
    why: Annotated[CorrectionText, BeforeValidator(clipped(TEXT_CHARS))]


class CorrectionReply(BaseModel):
    """The drafting model's reply, validated.

    Attributes:
        corrections: One action and why per planned change.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    corrections: list[_ReplyItem] = Field(max_length=MAX_CORRECTIONS)


def parse_corrections(
    content: str, count: int, allowed: frozenset[str]
) -> list[tuple[str, str]] | None:
    """Return each planned change's ``(action, why)``, in plan order, or ``None`` when unusable.

    A reply is unusable when it is not the expected JSON, does not answer every index from 0 to
    ``count - 1`` exactly once, or names a code-shaped value outside ``allowed`` (design
    decision 4: the parser, not the prompt, keeps new codes out).
    """
    data = reply_object(content)
    if data is None:
        return None
    try:
        reply = CorrectionReply.model_validate(data)
    except ValidationError:
        return None
    by_index = {item.index: item for item in reply.corrections}
    if len(by_index) != len(reply.corrections) or sorted(by_index) != list(range(count)):
        return None
    texts = [(by_index[index].action, by_index[index].why) for index in range(count)]
    if any(_invents(text, allowed) for pair in texts for text in pair):
        return None
    return texts


def _planned_text(planned: list[PlannedCorrection]) -> str:
    return json.dumps(
        [
            {
                "index": index,
                "line": "claim" if change.line is None else change.line,
                "field": change.field.value,
                "current_value": change.current_value or NOT_IN_DOCUMENTS,
                "codes": list(change.because),
            }
            for index, change in enumerate(planned)
        ],
        indent=1,
    )


def _diagnosis_text(diagnosis: Diagnosis) -> str:
    explanation = diagnosis.explanation
    return json.dumps(
        {
            "denial_reason": diagnosis.denial_reason.value,
            "codes": diagnosis.codes,
            "root_cause": None if explanation is None else explanation.root_cause,
        },
        indent=1,
    )


async def draft_corrections(  # noqa: PLR0913 - one request: endpoint, the case, its plan, transport
    endpoint: ModelEndpoint,
    extraction: CaseExtraction,
    diagnosis: Diagnosis,
    cards: list[RuleCard],
    planned: list[PlannedCorrection],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[tuple[str, str]]:
    """Ask the drafting model for each planned change's action and why.

    Args:
        endpoint: The ``drafting`` role, held through ``ModelManager.use``.
        extraction: The case's fields.
        diagnosis: The case's current diagnosis.
        cards: The payer's rule cards.
        planned: The changes from ``plan_corrections``.
        transport: Optional httpx transport (tests).

    Returns:
        ``(action, why)`` per planned change, in plan order.

    Raises:
        CorrectionFailedError: The reply is unusable or names a code the documents do not hold.
        ModelUnavailableError: The model did not answer.
    """
    data = (
        DataItem(label="case_facts", text=json.dumps(letter_facts(extraction), indent=1)),
        DataItem(label="diagnosis", text=_diagnosis_text(diagnosis)),
        DataItem(label="planned_changes", text=_planned_text(planned)),
        DataItem(label="rule_cards", text=rule_cards_text(cards)),
    )
    prompt = build_prompt(PromptParts(template=CORRECTION_TEMPLATE, data=data))
    reply = await chat_completion(
        endpoint, prompt, max_tokens=MAX_TOKENS, timeout=CORRECTION_TIMEOUT, transport=transport
    )
    texts = parse_corrections(reply.content, len(planned), allowed_codes(extraction))
    if texts is None:
        if reply.truncated:  # the operator can tell a cut-off reply from an unusable one
            _log.warning("correction reply stopped at max_tokens before it ended")
        raise CorrectionFailedError
    return texts


class Corrector:
    """Drafts a diagnosed case's corrected claim and stores it with the case.

    Args:
        cases: Where the diagnosis is read and the draft stored.
        models: ``ModelManager.use`` (or a test double).
        transport: Optional httpx transport for the model call (tests).
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

    def check(self, profile: str, case_id: str) -> None:
        """Refuse drafting before a job starts (store reads: run in a thread).

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case, or an ID events cannot carry.
            CaseClosedError: The case is closed or purged.
            NotDiagnosedError: The case has no diagnosis of its current fields.
        """
        self._inputs(profile, case_id)

    def _inputs(
        self, profile: str, case_id: str
    ) -> tuple[CaseExtraction, Diagnosis, list[RuleCard]]:
        """The case's fields and current diagnosis, and the payer's rule cards.

        The case must still be open: a case closed after the request never loads the model.
        """
        self.cases.check_draftable(profile, case_id)
        extraction, diagnosis = self.cases.draft_inputs(profile, case_id)
        cards = payer_rule_cards(self.cases.corpus.global_store(), value_of(extraction.payer_name))
        return extraction, diagnosis, cards

    async def run(self, profile: str, case_id: str, report: Report) -> CorrectedClaimDraft:
        """Draft the case's corrected claim, store it, and report ``drafting`` (0), ``done`` (1).

        Raises:
            CaseClosedError: The case is closed (checked before the model loads).
            NotDiagnosedError: The case has no diagnosis of its current fields.
            CorrectionFailedError: The model's reply was unusable; nothing is stored.
            ModelUnavailableError: The model is missing or stopped answering.
            ModelBusyError: The memory guard kept the model queued too long.
            CorpusError: The case store failed (for example the case was closed meanwhile).
        """
        report("drafting", 0.0)
        extraction, diagnosis, cards = await asyncio.to_thread(self._inputs, profile, case_id)
        everything = plan_corrections(extraction, diagnosis)
        planned = everything[:MAX_CORRECTIONS]  # the rest are counted, never silently dropped
        async with self.models(ModelRole.DRAFTING) as endpoint:
            texts = await draft_corrections(
                endpoint, extraction, diagnosis, cards, planned, transport=self._transport
            )
        draft = CorrectedClaimDraft(
            original_claim_id=value_of(extraction.claim_id),
            frequency_code=frequency_code(extraction, cards),
            corrections=[
                ClaimCorrection(
                    line=change.line,
                    field=change.field,
                    current_value=change.current_value,
                    because=list(change.because),
                    action=action,
                    why=why,
                )
                for change, (action, why) in zip(planned, texts, strict=True)
            ],
            omitted=len(everything) - len(planned),
            rule_cards=[card.key for card in cards],
            extraction_digest=extraction.digest(),
            diagnosed_at=diagnosis.diagnosed_at,
            drafted_at=utc_now(),
        )
        await asyncio.to_thread(self.cases.save_correction, profile, case_id, draft)
        report("done", 1.0)
        return draft
