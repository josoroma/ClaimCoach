"""PHI span detection with Qwen3-8B (the ``phi_detection`` role).

Implements: US-3.1 (JSON span prompt; spans carry a ``PhiCategory``). Rules: BR-2 (the document
goes only to the local model held through ``ModelManager.use``), BR-10 (the prompt is built with
the US-3.6 data-block encoder), BR-14 (a failure raises without model output or document text).

The model is asked to copy each PHI value verbatim rather than to count character offsets, which
small models get wrong; the detector then locates every occurrence of each value in the document.
A value is matched exactly or with its words in order across layout changes (line breaks,
commas); a value that still does not occur contributes its distinctive words (any with a digit,
or of 4+ letters); a value with none of those in the document is dropped as a hallucination.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import ClassVar, Final

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from claimcoach.logs import get_logger
from claimcoach.models.chat import chat_completion
from claimcoach.models.manager import ModelEndpoint, ModelError
from claimcoach.models.types import ModelRole
from claimcoach.prompts.builder import DataItem, PromptParts, build_prompt, define_template
from claimcoach.redact.spans import locate, locate_parts
from claimcoach.redact.types import PhiCategory, PhiSpan

__all__ = [
    "CHUNK_CHARS",
    "PHI_TEMPLATE",
    "EndpointProvider",
    "PhiDetector",
    "RedactionFailedError",
    "chunk_text",
    "parse_reply",
]

CHUNK_CHARS: Final = 6000
"""Characters of document per model call (~1 500 tokens), cut at line boundaries."""

TOTAL_TIMEOUT: Final = 300.0
"""Seconds one document's detection may take across all its chunks."""

MAX_TOKENS: Final = 2048
"""Reply budget per chunk; a truncated reply fails the detection rather than being trusted."""

EndpointProvider = Callable[[ModelRole], AbstractAsyncContextManager[ModelEndpoint]]
"""``ModelManager.use``: holds a role's server for the duration of the context."""

PHI_TEMPLATE: Final = define_template(
    "phi_detection",
    system=(
        "You find protected health information (PHI) in medical billing documents and answer "
        "with JSON only. /no_think"
    ),
    instructions=(
        "List every PHI value in the document below. Categories: name (any person's name, in "
        "every form it appears, e.g. 'Jane Doe' and 'DOE, JANE'), dob (date of birth), mrn "
        "(medical record or patient account number), member_id (member, subscriber, or policy "
        "ID), ssn, address (street address, city, state, ZIP), phone. Copy each value exactly as "
        "written in the document, one entry per distinct value. Do not include claim numbers, "
        "denial codes, amounts, or payer names. Answer with only this JSON object: "
        '{"spans": [{"text": "<value copied from the document>", "category": "<category>"}]}. '
        'If there is no PHI, answer {"spans": []}.'
    ),
)

_ALIASES: Final[dict[str, PhiCategory]] = {
    "person": PhiCategory.NAME,
    "patient_name": PhiCategory.NAME,
    "date_of_birth": PhiCategory.DOB,
    "birth_date": PhiCategory.DOB,
    "medical_record_number": PhiCategory.MRN,
    "account_number": PhiCategory.MRN,
    "member": PhiCategory.MEMBER_ID,
    "subscriber_id": PhiCategory.MEMBER_ID,
    "policy_id": PhiCategory.MEMBER_ID,
    "social_security_number": PhiCategory.SSN,
    "phone_number": PhiCategory.PHONE,
    "telephone": PhiCategory.PHONE,
}
_log = get_logger("claimcoach.redact")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class RedactionFailedError(ModelError):
    """The PHI model's reply could not be used, so nothing may be treated as redacted."""

    code = "redaction_failed"
    status_code: ClassVar[int] = 503


class _ModelSpan(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    text: str
    category: str


class _ModelReply(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    spans: list[_ModelSpan]


def _category(raw: str) -> PhiCategory:
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return PhiCategory(key)
    except ValueError:
        # Recall first: a value the model flagged under an unknown label is still redacted.
        return _ALIASES.get(key, PhiCategory.OTHER)


def parse_reply(content: str) -> list[tuple[str, PhiCategory]]:
    """Parse the model's JSON reply into ``(value, category)`` pairs.

    Args:
        content: Raw assistant reply; a ``<think>`` block and text around the JSON are ignored.

    Returns:
        The values the model reported, stripped, without empty ones.

    Raises:
        RedactionFailedError: The reply holds no JSON object of the expected shape.
    """
    content = _THINK.sub("", content)
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise RedactionFailedError
    try:
        reply = _ModelReply.model_validate_json(content[start : end + 1])
    except ValidationError as exc:
        raise RedactionFailedError from exc
    return [
        (span.text.strip(), _category(span.category)) for span in reply.spans if span.text.strip()
    ]


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split ``text`` into pieces of at most ``size`` characters, preferring line boundaries.

    Args:
        text: The document.
        size: Maximum characters per piece.

    Returns:
        Pieces that concatenate back to ``text``.
    """
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        rest = line
        while len(rest) > size:  # a single overlong line is cut hard
            if current:
                chunks.append(current)
                current = ""
            chunks.append(rest[:size])
            rest = rest[size:]
        if len(current) + len(rest) > size:
            chunks.append(current)
            current = ""
        current += rest
    if current:
        chunks.append(current)
    return chunks


class PhiDetector:
    """Find PHI spans in a document with the ``phi_detection`` model.

    Args:
        models: ``ModelManager.use`` (or a test double with the same shape).
        chunk_chars: Characters per model call.
        timeout: Seconds per model call.
        total_timeout: Seconds for the whole document; past it detection fails closed and the
            model is released, so one huge upload cannot hold it (and the memory guard) for long.
        transport: Optional httpx transport for tests.
    """

    def __init__(
        self,
        models: EndpointProvider,
        *,
        chunk_chars: int = CHUNK_CHARS,
        timeout: float = 120.0,
        total_timeout: float = TOTAL_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Store the model provider; no model is started until ``detect``."""
        self._models = models
        self._chunk_chars = chunk_chars
        self._timeout = timeout
        self._total_timeout = total_timeout
        self._transport = transport

    async def detect(self, text: str) -> list[PhiSpan]:
        """Return the model's PHI spans, located at every occurrence in ``text``.

        Args:
            text: The document.

        Returns:
            Spans with ``source="model"``, in document order.

        Raises:
            ModelUnavailableError: The model is missing or not responding.
            ModelBusyError: The memory guard kept the model queued too long.
            RedactionFailedError: A reply was truncated or not the expected JSON.
        """
        if not text.strip():
            return []
        try:
            async with asyncio.timeout(self._total_timeout):
                values = await self._ask(text)
        except TimeoutError as exc:
            raise RedactionFailedError from exc
        spans: list[PhiSpan] = []
        unlocated = 0
        for value, category in values.items():
            found = locate(text, value, category)
            if not found:
                found = locate_parts(text, value, category)
                unlocated += not found
            spans += found
        if unlocated:
            # A count only: the values are PHI or hallucinations, neither belongs in a log.
            _log.info("%d PHI values from the model were not found in the document", unlocated)
        return sorted(spans, key=lambda span: (span.start, span.end))

    async def _ask(self, text: str) -> dict[str, PhiCategory]:
        values: dict[str, PhiCategory] = {}
        async with self._models(ModelRole.PHI_DETECTION) as endpoint:
            for chunk in chunk_text(text, self._chunk_chars):
                prompt = build_prompt(
                    PromptParts(
                        template=PHI_TEMPLATE, data=(DataItem(label="document", text=chunk),)
                    )
                )
                reply = await chat_completion(
                    endpoint,
                    prompt,
                    max_tokens=MAX_TOKENS,
                    timeout=self._timeout,
                    transport=self._transport,
                )
                if reply.truncated:
                    raise RedactionFailedError
                for value, category in parse_reply(reply.content):
                    values.setdefault(value, category)
        return values
