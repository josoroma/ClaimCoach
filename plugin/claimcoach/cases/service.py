"""Case creation and source-document intake over a profile's encrypted user store.

Implements: US-5.1 (``CaseService``: create a case, open it with its source documents, attach an
uploaded file or pasted text), US-5.2 (the sources extraction reads, the stored extraction, and
field confirmation). Rules: BR-2 (runs in the worker; the pane reaches it through
``plugin_api.py``), BR-6 and BR-13 (files are sealed into the profile's user scope), BR-7 (they are
case items, deleted by the retention purge), BR-14 (nothing here logs content).

Methods open stores and may prompt the Keychain, so routes call them off the event loop.
"""

from __future__ import annotations

import re
import secrets
import threading
from typing import Final

from pydantic import ValidationError

from claimcoach.cases.errors import DocumentTooLargeError, FieldError, NoDocumentsError
from claimcoach.cases.extraction import CaseExtraction, FieldConfirmation
from claimcoach.cases.intake import UploadedFile, sniff, text_kind
from claimcoach.cases.models import MAX_PASTE_BYTES, Case, DocumentAdded, SourceDocument, SourceKind
from claimcoach.corpus.errors import CaseClosedError, CaseNotFoundError
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import AuditAction, CaseItem, CaseRecord, utc_now
from claimcoach.events import CASE_ID_PATTERN, new_case_id

__all__ = ["EXTRACTION_ITEM", "PASTE_CONTENT_TYPE", "CaseService", "new_source_id"]

PASTE_CONTENT_TYPE: Final = "text/plain; charset=utf-8"
EXTRACTION_ITEM: Final = "extraction"
"""The item ID of a case's one extraction."""


def new_source_id() -> str:
    """Return a new opaque source-document ID."""
    return f"src_{secrets.token_hex(8)}"


class CaseService:
    """Cases of every profile, stored in each profile's user scope.

    Args:
        corpus: The worker's corpus service (it opens the user stores).
    """

    def __init__(self, corpus: CorpusService) -> None:
        """Keep the corpus service; no store opens until a call needs it."""
        self.corpus = corpus
        self._guard = threading.Lock()
        self._case_locks: dict[tuple[str, str], threading.Lock] = {}

    def _case_lock(self, profile: str, case_id: str) -> threading.Lock:
        """One lock per case: a confirmation and an extraction never interleave read and write."""
        with self._guard:
            return self._case_locks.setdefault((profile, case_id), threading.Lock())

    def store(self, profile: str) -> CorpusStore:
        """Return ``profile``'s user store; reading never creates one.

        Raises:
            ProfileNotFoundError: The profile has no user scope.
        """
        return self.corpus.user_store(profile)

    def create(self, profile: str) -> Case:
        """Create an open, empty case; the first case creates the profile's user scope."""
        record = self.corpus.user_store(profile, create=True).create_case(new_case_id())
        return _case(record, [])

    def open(self, profile: str, case_id: str) -> Case:
        """Return the case with its source documents (audited ``case_opened``).

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
        """
        store = self.store(profile)
        record = store.open_case(case_id)
        return _case(record, self.documents(store, case_id), self.extraction(store, case_id))

    @staticmethod
    def documents(store: CorpusStore, case_id: str) -> list[SourceDocument]:
        """Return the case's source documents, oldest first (not audited)."""
        return [
            SourceDocument.model_validate_json(item.payload)
            for item in store.case_items(case_id, "source")
        ]

    @staticmethod
    def extraction(store: CorpusStore, case_id: str) -> CaseExtraction | None:
        """Return the case's stored extraction, if extraction ran (not audited)."""
        items = store.case_items(case_id, "extraction")
        return CaseExtraction.model_validate_json(items[0].payload) if items else None

    def sources(self, profile: str, case_id: str) -> list[tuple[SourceDocument, bytes]]:
        """Return the case's source documents with their bytes, for extraction (US-5.2)."""
        store = self.store(profile)
        sources = []
        for document in self.documents(store, case_id):
            data = store.case_item_data(case_id, document.doc_id)
            if data is not None:
                sources.append((document, data))
        return sources

    def _require_open(self, profile: str, case_id: str) -> CorpusStore:
        """Return the profile's store once the case is known to exist and be open.

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
        """
        store = self.store(profile)
        record = store.case_record(case_id)
        if record.closed_at is not None or record.purged_at is not None:
            raise CaseClosedError
        return store

    def check_extractable(self, profile: str, case_id: str) -> None:
        """Refuse extraction before a job starts: the case must be open and hold a document.

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case, or an ID events cannot carry (not ``new_case_id``).
            CaseClosedError: The case is closed or purged.
            NoDocumentsError: The case has no source document.
        """
        if not re.fullmatch(CASE_ID_PATTERN, case_id):
            raise CaseNotFoundError
        store = self._require_open(profile, case_id)
        if not store.case_items(case_id, "source"):
            raise NoDocumentsError

    def save_extraction(self, profile: str, case_id: str, extraction: CaseExtraction) -> None:
        """Store the case's extraction, keeping every value the biller confirmed before.

        Raises:
            CaseClosedError: The case was closed while extraction ran.
        """
        store = self.store(profile)
        with self._case_lock(profile, case_id):
            previous = self.extraction(store, case_id)
            if previous is not None:
                extraction = extraction.keep_confirmed(previous)
            item = _extraction_item(case_id, extraction)
            store.put_case_item(item, audit=AuditAction.CASE_EXTRACTED)

    def confirm_field(self, profile: str, case_id: str, confirmation: FieldConfirmation) -> Case:
        """Store the biller's value for one field as ``confirmed`` (audited ``field_confirmed``).

        Raises:
            FieldError: No extraction yet, no such field, or a value not valid for the field.
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
        """
        store = self._require_open(profile, case_id)
        with self._case_lock(profile, case_id):
            current = self.extraction(store, case_id)
            if current is None:
                raise FieldError
            try:
                confirmed = current.confirm(confirmation.path, confirmation.value)
            except (KeyError, ValidationError) as exc:
                raise FieldError from exc
            item = _extraction_item(case_id, confirmed)
            store.put_case_item(item, audit=AuditAction.FIELD_CONFIRMED)
        return _case(store.case_record(case_id), self.documents(store, case_id), confirmed)

    def add_file(self, profile: str, case_id: str, upload: UploadedFile) -> DocumentAdded:
        """Attach an uploaded file; its kind comes from its bytes.

        Raises:
            UnsupportedDocumentError: Not a PDF, PNG, JPEG, or UTF-8 text.
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
        """
        self._require_open(profile, case_id)  # a closed case answers case_closed, whatever the file
        document = _source(sniff(upload.data), upload.filename, upload.content_type, upload.data)
        return self._attach(profile, case_id, document, upload.data)

    def add_text(self, profile: str, case_id: str, text: str) -> DocumentAdded:
        """Attach pasted text, as ``edi_835`` when it is an 835 interchange.

        Raises:
            DocumentTooLargeError: Over ``MAX_PASTE_BYTES``.
            UnsupportedDocumentError: Blank text.
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
        """
        self._require_open(profile, case_id)
        data = text.encode("utf-8")
        if len(data) > MAX_PASTE_BYTES:
            raise DocumentTooLargeError
        document = _source(text_kind(text), None, PASTE_CONTENT_TYPE, data)
        return self._attach(profile, case_id, document, data)

    def _attach(
        self, profile: str, case_id: str, document: SourceDocument, data: bytes
    ) -> DocumentAdded:
        item = CaseItem(
            case_id=case_id,
            item_id=document.doc_id,
            kind="source",
            created_at=document.added_at,
            payload=document.model_dump_json().encode(),
        )
        self.store(profile).put_case_item(item, data, audit=AuditAction.DOCUMENT_ADDED)
        return DocumentAdded(case_id=case_id, document=document)


def _source(
    kind: SourceKind, filename: str | None, content_type: str, data: bytes
) -> SourceDocument:
    return SourceDocument(
        doc_id=new_source_id(),
        kind=kind,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        added_at=utc_now(),
    )


def _extraction_item(case_id: str, extraction: CaseExtraction) -> CaseItem:
    return CaseItem(
        case_id=case_id,
        item_id=EXTRACTION_ITEM,
        kind="extraction",
        created_at=utc_now(),
        payload=extraction.model_dump_json().encode(),
    )


def _case(
    record: CaseRecord, documents: list[SourceDocument], extraction: CaseExtraction | None = None
) -> Case:
    return Case(
        case_id=record.case_id,
        opened_at=record.opened_at,
        closed_at=record.closed_at,
        documents=documents,
        extraction=extraction,
        needs_confirmation=[] if extraction is None else extraction.needs_confirmation(),
    )
