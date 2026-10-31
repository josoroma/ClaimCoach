"""Typed case bodies: what the pane sends and what it gets back.

Implements: US-5.1 (``CaseCreate``, ``PastedText``, ``SourceDocument``, ``Case``,
``DocumentAdded``, and the intake limits), US-5.2 (``Case`` carries the extraction and the fields
that need confirmation), US-6.1 (``Case`` carries the diagnosis and whether it is stale), US-6.3
(``Case`` carries the appeal deadline). Rules:
ES-1 (Pydantic v2, ``extra="forbid"``, frozen), BR-2 (these bodies travel pane →
``plugin_api.py`` → worker only), BR-14 (they carry case content, so they are never logged and
never reach an agent tool or an event).

This module imports nothing heavier than Pydantic, so the gateway can use it.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from claimcoach.cases.diagnosis import AppealDeadline, Diagnosis
from claimcoach.cases.extraction import CaseExtraction
from claimcoach.corpus.types import CaseId, Timestamp

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_PASTE_BODY",
    "MAX_PASTE_BYTES",
    "MAX_UPLOAD_BODY",
    "Case",
    "CaseCreate",
    "DocumentAdded",
    "PastedText",
    "SourceDocument",
    "SourceKind",
]

MAX_FILE_BYTES: Final = 16 * 1024 * 1024
"""Largest accepted file: a 20-page scanned EOB at 150 dpi is about 10 MiB."""
MAX_PASTE_BYTES: Final = 4 * 1024 * 1024
"""Largest pasted text, UTF-8 encoded (PC-3's ``ctx.files`` figure); more than any 835 claim."""
MAX_PASTE_BODY: Final = 6 * MAX_PASTE_BYTES + 1024
"""Largest ``PastedText`` JSON body read: JSON may escape a character as six bytes."""
MAX_UPLOAD_BODY: Final = MAX_FILE_BYTES + 64 * 1024
"""Largest multipart body read: the file plus its framing and headers."""

SourceKind = Literal["pdf", "image", "edi_835", "text"]
"""What a source document is, decided from its bytes (``cases.intake.sniff``)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseCreate(_Strict):
    """``POST /cases``: a new, empty case. The active profile comes from the gateway."""


class PastedText(_Strict):
    """``POST /cases/{case_id}/paste``: text the biller pasted (835 or a letter).

    Attributes:
        text: The pasted text; over ``MAX_PASTE_BYTES`` it is refused as too large.
    """

    text: str = Field(min_length=1)


class SourceDocument(_Strict):
    """A source document attached to a case.

    Attributes:
        doc_id: Opaque ID (``src_`` + 16 hex digits).
        kind: What it is, from its bytes.
        filename: The uploaded file's name, or ``None`` for pasted text (may be PHI; encrypted
            at rest and shown only in the pane).
        content_type: The declared media type, for display only.
        size_bytes: Its size.
        added_at: When it was attached.
    """

    doc_id: str = Field(pattern=r"^src_[0-9a-f]{16}$")
    kind: SourceKind
    filename: str | None = Field(default=None, min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=127)
    size_bytes: int = Field(ge=1)
    added_at: Timestamp


class Case(_Strict):
    """A case as the pane shows it.

    Attributes:
        ok: Always ``True``.
        case_id: The case.
        opened_at: When it was created.
        closed_at: When it was closed; a closed case takes no new documents.
        documents: Its source documents, oldest first.
        extraction: Its structured fields, once extraction ran (US-5.2).
        needs_confirmation: Paths of the unreadable fields the pane highlights.
        diagnosis: Its diagnosis, once diagnosis ran (US-6.1).
        diagnosis_stale: The extraction changed after the diagnosis ran (a confirmed field or a
            new extraction), so the pane asks to diagnose again.
        deadline: The appeal deadline, or why it is unknown, computed from the current
            extraction and rule cards whenever the case is read (US-6.3); none before extraction.
    """

    ok: Literal[True] = True
    case_id: CaseId
    opened_at: Timestamp
    closed_at: Timestamp | None = None
    documents: list[SourceDocument]
    extraction: CaseExtraction | None = None
    needs_confirmation: list[str] = Field(default_factory=list)
    diagnosis: Diagnosis | None = None
    diagnosis_stale: bool = False
    deadline: AppealDeadline | None = None


class DocumentAdded(_Strict):
    """The answer to an upload or a paste.

    Attributes:
        ok: Always ``True``.
        case_id: The case.
        document: The attached document.
    """

    ok: Literal[True] = True
    case_id: CaseId
    document: SourceDocument
