"""Typed corpus records and the REST bodies of the worker's corpus routes.

Implements: US-4.1 (``CorpusScope``, ``Document``, ``Chunk``, ``CaseRecord``, ``IndexInfo``,
``ScopeStatus``, ``ReindexRequest``), US-4.4 (``RetrievalQuery`` with a required ``case_id``,
``RetrievedChunk``), US-4.5 (``CaseOutcome``, ``OutcomeRecord``, ``PurgeRequest``,
``PurgeReport``), US-4.6 (``AuditAction``, ``AuditEntry``), US-5.1 (``CaseItem``,
``CaseItemKind``), US-5.2 (``case_extracted`` and ``field_confirmed`` audit actions), US-6.1 (the
``diagnosis`` case item and the ``case_diagnosed`` audit action), US-7.1 (the ``draft`` case item
and the ``case_drafted`` audit action), US-7.2 (the ``draft_edited`` and ``draft_exported`` audit
actions). Rules:
ES-1 (Pydantic v2, ``extra="forbid"``, frozen), BR-5, BR-7, BR-14 (status and audit bodies carry
IDs, counts, and dates only; document text appears only in ``Document``, ``Chunk``,
``RetrievedChunk``, and ``CaseItem``, which never leave the worker).

This module imports neither SQLite nor numpy, so the gateway and the Hermes CLI can use it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)

__all__ = [
    "DEFAULT_PROFILE",
    "PROFILE_PATTERN",
    "AuditAction",
    "AuditEntry",
    "AuditResponse",
    "CaseId",
    "CaseItem",
    "CaseItemKind",
    "CaseOutcome",
    "CaseRecord",
    "Chunk",
    "CorpusScope",
    "CorpusStatusResponse",
    "Document",
    "DocumentKind",
    "IndexInfo",
    "OutcomeRecord",
    "ProfileName",
    "PurgeReport",
    "PurgeRequest",
    "PurgeResponse",
    "ReindexRequest",
    "ReindexResult",
    "RetrievalQuery",
    "RetrievedChunk",
    "ScopeStatus",
    "utc_now",
]

DEFAULT_PROFILE: Final = "default"
"""Hermes' name for the profile whose home is the Hermes root itself."""


def utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must carry a timezone")
    return value.astimezone(UTC)


Timestamp = Annotated[datetime, AfterValidator(_aware)]
"""An aware datetime, normalized to UTC."""

CaseId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
"""Opaque case identifier; never derived from PHI."""

PROFILE_PATTERN: Final = r"^[a-z0-9][a-z0-9_-]{0,63}$"
"""Hermes' own ``PROFILE_ID_RE``; it also keeps ``/`` and ``..`` out of every path built from it."""

ProfileName = Annotated[str, StringConstraints(pattern=PROFILE_PATTERN)]
"""A Hermes profile name."""

_OPAQUE_ID: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class CorpusScope(StrEnum):
    """The two corpus scopes of PRD §9."""

    GLOBAL = "global"
    USER = "user"


DocumentKind = Literal[
    "rule_card", "code", "letter_template", "source", "extracted", "draft", "note"
]
"""What a document is. The first three live in the global scope, the rest in a case."""

GLOBAL_KINDS: Final[frozenset[str]] = frozenset({"rule_card", "code", "letter_template"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Document(_Strict):
    """One stored document.

    Attributes:
        doc_id: Stable ID (``kind:key`` in the global scope, random in the user scope).
        scope: Scope it lives in.
        case_id: Owning case; required in the user scope, absent in the global scope.
        kind: What the document is.
        title: Short title (may be PHI in the user scope; encrypted there).
        text: Full text (encrypted in the user scope).
        metadata: Provenance and other string fields (encrypted in the user scope).
        created_at: When it was stored.
    """

    doc_id: str = Field(min_length=1, max_length=200)
    scope: CorpusScope
    case_id: CaseId | None = None
    kind: DocumentKind
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: Timestamp = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _scope_consistent(self) -> Document:
        if self.scope is CorpusScope.USER:
            if self.case_id is None or self.kind in GLOBAL_KINDS:
                raise ValueError("a user-scope document belongs to a case and is case content")
            if not _OPAQUE_ID.fullmatch(self.doc_id):
                # Stored in plaintext, so never a filename or anything else that may be PHI.
                raise ValueError("a user-scope document ID is opaque")
        elif self.case_id is not None or self.kind not in GLOBAL_KINDS:
            raise ValueError("a global-scope document has no case and is reference material")
        return self


class Chunk(_Strict):
    """A retrievable slice of a document.

    Attributes:
        chunk_id: Stable ID (``<doc_id>#<ordinal>``).
        doc_id: Owning document.
        scope: Scope it lives in.
        case_id: Owning case in the user scope.
        kind: The owning document's kind.
        ordinal: Position in the document.
        text: Chunk text (encrypted in the user scope).
    """

    chunk_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    scope: CorpusScope
    case_id: CaseId | None = None
    kind: DocumentKind
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)


class CaseRecord(_Strict):
    """A case's lifecycle dates; no case content.

    Attributes:
        case_id: The case.
        opened_at: When it was created.
        closed_at: When it was closed; starts the retention clock (BR-7).
        purged_at: When its content was purged.
    """

    case_id: CaseId
    opened_at: Timestamp
    closed_at: Timestamp | None = None
    purged_at: Timestamp | None = None


CaseItemKind = Literal["source", "extraction", "diagnosis", "draft"]
"""A case item: an attached source file (US-5.1), the case's structured extraction (US-5.2), its
diagnosis (US-6.1), or its appeal draft (US-7.1)."""


class CaseItem(_Strict):
    """A case item's sealed payload, opened; the item's bytes are read separately.

    Attributes:
        case_id: Owning case.
        item_id: Opaque ID, unique within the case.
        kind: What the item is.
        created_at: When it was first stored.
        payload: The item's JSON description (PHI; encrypted at rest).
    """

    case_id: CaseId
    item_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    kind: CaseItemKind
    created_at: Timestamp
    payload: bytes


class CaseOutcome(StrEnum):
    """How a case ended (PRD §6 story 5, US-8.1)."""

    OVERTURNED = "overturned"
    UPHELD = "upheld"
    WRITTEN_OFF = "written_off"


class OutcomeRecord(_Strict):
    """A case's outcome: an enum and a date, de-identified by construction (BR-7).

    Attributes:
        case_id: The case.
        outcome: How it ended.
        recorded_at: When the biller recorded it.
    """

    case_id: CaseId
    outcome: CaseOutcome
    recorded_at: Timestamp


class IndexInfo(_Strict):
    """What a scope's vector index was built with.

    Attributes:
        embedding_model_id: Model that produced the stored vectors.
        configured_model_id: Model ``models.yaml`` configures now.
        dimension: Vector length, once the first vector is stored.
        vectors: Stored vectors.
        missing_vectors: Chunks without a vector (an interrupted write or a mid-write backup).
        needs_reindex: The two model IDs differ (searches and inserts are refused until reindex)
            or some chunks have no vector.
    """

    embedding_model_id: str
    configured_model_id: str
    dimension: int | None
    vectors: int = Field(ge=0)
    missing_vectors: int = Field(default=0, ge=0)
    needs_reindex: bool


class ScopeStatus(_Strict):
    """One scope as ``GET /corpus/status`` reports it.

    Attributes:
        scope: The scope.
        profile: Profile of a user scope.
        path: Scope directory.
        available: Whether the store opened; ``False`` when its key is missing or wrong.
        encrypted: Whether stored content is encrypted at rest.
        cases: Cases in a user scope.
        documents: Stored documents.
        chunks: Stored chunks.
        index: The vector index; absent when the store did not open.
    """

    scope: CorpusScope
    profile: ProfileName | None = None
    path: str
    available: bool = True
    encrypted: bool
    cases: int = Field(default=0, ge=0)
    documents: int = Field(default=0, ge=0)
    chunks: int = Field(default=0, ge=0)
    index: IndexInfo | None = None


class CorpusStatusResponse(_Strict):
    """Both scopes' status.

    Attributes:
        ok: Always ``True``.
        global_scope: The global scope.
        user_scopes: Every profile's user scope that exists.
    """

    ok: Literal[True] = True
    global_scope: ScopeStatus
    user_scopes: list[ScopeStatus]


class ReindexRequest(_Strict):
    """Re-embed one scope under the configured embedding model.

    Attributes:
        scope: Scope to reindex.
        profile: Profile of a user scope.
    """

    scope: CorpusScope
    profile: ProfileName = DEFAULT_PROFILE


class ReindexResult(_Strict):
    """What a reindex did.

    Attributes:
        ok: Always ``True``.
        chunks: Chunks re-embedded.
        embedding_model_id: Model the index now records.
    """

    ok: Literal[True] = True
    chunks: int = Field(ge=0)
    embedding_model_id: str


class RetrievalQuery(_Strict):
    """A retrieval request; ``case_id`` is required so no query can span cases (BR-5).

    Attributes:
        text: What to look for (stays in the worker).
        case_id: The current case; only its user-scope chunks are candidates.
        k: Chunks to return.
        candidates: Nearest chunks per scope passed to the reranker.
    """

    text: str = Field(min_length=1, max_length=8000)
    case_id: CaseId
    k: int = Field(default=8, ge=1, le=50)
    candidates: int = Field(default=32, ge=1, le=200)


class RetrievedChunk(_Strict):
    """A chunk retrieval returned.

    Attributes:
        chunk: The chunk.
        score: Reranker relevance; higher is better.
    """

    chunk: Chunk
    score: float


class AuditAction(StrEnum):
    """Case-level actions the audit log records (US-4.6)."""

    CASE_CREATED = "case_created"
    CASE_OPENED = "case_opened"
    DOCUMENT_ADDED = "document_added"
    CASE_EXTRACTED = "case_extracted"
    """Extraction stored the case's structured fields (US-5.2)."""
    FIELD_CONFIRMED = "field_confirmed"
    """The biller confirmed a field's value (US-5.2)."""
    CASE_DIAGNOSED = "case_diagnosed"
    """Diagnosis stored the case's denial reason and appeal likelihood (US-6.1)."""
    CASE_DRAFTED = "case_drafted"
    """Drafting stored the case's appeal draft (US-7.1)."""
    DRAFT_EDITED = "draft_edited"
    """The biller saved edited text for the case's draft (US-7.2)."""
    DRAFT_EXPORTED = "draft_exported"
    """The case's draft was written to a PDF or DOCX file for the biller to save (US-7.2)."""
    CASE_CLOSED = "case_closed"
    OUTCOME_RECORDED = "outcome_recorded"
    CASE_PURGED = "case_purged"
    """By the retention policy (US-4.5)."""
    CASE_PURGED_ON_REQUEST = "case_purged_on_request"
    """By an approved single-case purge (phi-purge runbook)."""


class AuditEntry(_Strict):
    """One audit entry; no PHI.

    Attributes:
        seq: Position in the log.
        at: When it happened.
        action: What happened.
        case_id: The case.
        profile: Hermes profile (the biller) that did it.
    """

    seq: int = Field(ge=1)
    at: Timestamp
    action: AuditAction
    case_id: CaseId
    profile: ProfileName


class AuditResponse(_Strict):
    """Audit entries, oldest first.

    Attributes:
        ok: Always ``True``.
        entries: The entries.
    """

    ok: Literal[True] = True
    entries: list[AuditEntry]


class PurgeRequest(_Strict):
    """Run the retention purge now, or purge one case on request.

    Attributes:
        profile: Profile whose user scope to purge; every profile when omitted.
        case_id: Purge this case now, whatever its retention date.
        confirm: Required for a single-case purge (privacy-officer approval, phi-purge runbook).
    """

    profile: ProfileName | None = None
    case_id: CaseId | None = None
    confirm: StrictBool = False

    @model_validator(mode="after")
    def _single_case_confirmed(self) -> PurgeRequest:
        if self.case_id is not None and (self.profile is None or not self.confirm):
            raise ValueError("a single-case purge names its profile and needs confirm: true")
        return self


class PurgeReport(_Strict):
    """What one purge run removed from one profile's user scope.

    Attributes:
        profile: The profile.
        cases: Cases whose content was purged.
        documents: Documents deleted.
        chunks: Chunks deleted.
        vectors: Vectors deleted.
    """

    profile: ProfileName
    cases: list[CaseId]
    documents: int = Field(ge=0)
    chunks: int = Field(ge=0)
    vectors: int = Field(ge=0)


class PurgeResponse(_Strict):
    """Every profile's purge report.

    Attributes:
        ok: Always ``True``.
        reports: One per profile purged.
        skipped: Profiles not purged this run (store or settings unreadable); retried next run.
    """

    ok: Literal[True] = True
    reports: list[PurgeReport]
    skipped: list[ProfileName] = Field(default_factory=list)
