"""Typed appeal-draft bodies: what drafting stores and what the pane sends and gets back.

Implements: US-7.1 (``DRAFT_LABEL``, ``DraftRequest``, ``AppealDraft``), US-7.2 (``DraftEdit``,
``ExportFormat``, ``ExportRequest``, ``ExportedFile``). Rules: ES-1 (Pydantic v2,
``extra="forbid"``, frozen), BR-4 (``AppealDraft.label`` is fixed to "draft for human review", so a
draft without it does not validate; no body here names a recipient or a channel: nothing is sent),
BR-14 (a draft holds case content: it travels worker → gateway → pane only and is never logged or
put in an event).

This module imports nothing heavier than Pydantic, so the gateway can use it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from claimcoach.corpus.types import CaseId, Timestamp

__all__ = [
    "DRAFT_LABEL",
    "MAX_LETTER_CHARS",
    "AppealDraft",
    "DraftEdit",
    "DraftRequest",
    "ExportFormat",
    "ExportRequest",
    "ExportedFile",
    "LetterText",
    "TemplateId",
]

DRAFT_LABEL: Final = "draft for human review"
"""The label every draft carries wherever it is shown or exported (BR-4, PRD §10)."""
MAX_LETTER_CHARS: Final = 20_000
"""Longest letter: a two-page appeal is about 6000 characters."""

LetterText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_LETTER_CHARS)
]
"""A letter's text, not blank."""
TemplateId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")]
"""A letter template's ID, as imported (US-4.3)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DraftRequest(_Strict):
    """``POST /cases/{case_id}/draft``: draft the case's appeal letter (US-7.1).

    Attributes:
        template_id: The letter template to draft from; by default the case's denial reason
            picks one (``appeal-<reason>``, else ``appeal``).
    """

    template_id: TemplateId | None = None


class AppealDraft(_Strict):
    """A case's appeal letter, as drafted and then edited by the biller (US-7.1, US-7.2).

    Attributes:
        label: Always "draft for human review" (BR-4).
        text: The letter.
        template_id: The template it was drafted from.
        rule_cards: Keys of the payer's rule cards it was drafted with; empty when none matched.
        extraction_digest: The extraction it was drafted from (``CaseExtraction.digest``).
        diagnosed_at: When the diagnosis it was drafted from ran.
        drafted_at: When the model drafted it.
        edited_at: When the biller last saved edited text.
    """

    label: Literal["draft for human review"] = DRAFT_LABEL
    text: LetterText
    template_id: TemplateId
    rule_cards: list[Annotated[str, StringConstraints(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=5
    )
    extraction_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnosed_at: Timestamp
    drafted_at: Timestamp
    edited_at: Timestamp | None = None


class DraftEdit(_Strict):
    """``POST /cases/{case_id}/draft/text``: the biller's text for the draft (US-7.2).

    Attributes:
        text: The whole letter as the pane editor holds it.
    """

    text: LetterText


class ExportFormat(StrEnum):
    """The file formats a draft exports to (US-7.2)."""

    PDF = "pdf"
    DOCX = "docx"


class ExportRequest(_Strict):
    """``POST /cases/{case_id}/export``: export the stored draft (US-7.2).

    Attributes:
        format: PDF or DOCX. The stored draft is exported, never text from the request.
    """

    format: ExportFormat


class ExportedFile(_Strict):
    """An export, written on this Mac for the biller to save (US-7.2 design decision 4).

    Attributes:
        ok: Always ``True``.
        case_id: The case.
        format: The file format.
        path: Where the file is, for the host's save dialog (no PHI: the profile home, the case
            ID, and a random suffix).
        filename: The name the save dialog suggests.
        size_bytes: The file's size.
        expires_at: When the file is deleted.
    """

    ok: Literal[True] = True
    case_id: CaseId
    format: ExportFormat
    path: str = Field(min_length=1)
    filename: str = Field(pattern=r"^appeal-draft-[A-Za-z0-9_-]{1,64}\.(pdf|docx)$")
    size_bytes: int = Field(ge=1)
    expires_at: Timestamp
