"""Case creation and source-document intake over a profile's encrypted user store.

Implements: US-5.1 (``CaseService``: create a case, open it with its source documents, attach an
uploaded file or pasted text), US-5.2 (the sources extraction reads, the stored extraction, and
field confirmation), US-6.1 (the extraction diagnosis reads, the stored diagnosis, and whether it is
stale), US-6.3 (the appeal deadline, computed whenever a case is read), US-7.1 (what drafting reads:
the extraction and its current diagnosis; the stored draft and whether it is stale), US-7.2 (the
biller's edits to the draft, and the draft an export renders), US-8.1 (recording the case's
outcome, which closes it; the case shows its outcome), US-8.2 (the outcome's de-identified
snapshot is taken from the extraction and its current diagnosis), US-11.1 (payer-call recordings
are sealed into the case, queued for after-hours transcription, and shown with their job and
transcript; the scheduler reads a recording and stores its transcript), US-7.4 (the remedy
recommended whenever a case is read; the stored corrected-claim draft, whether it is stale, and
the draft an export renders), US-10.1 (``list_cases``:
the profile's newest cases for the pane's list, not audited because no content is read). Rules:
BR-2 (runs in the worker; the pane reaches it through ``plugin_api.py``), BR-6 and BR-13 (files
are sealed into the profile's user scope), BR-7 (they are case items, deleted by the retention
purge), BR-14 (nothing here logs content).

Methods open stores and may prompt the Keychain, so routes call them off the event loop.
"""

from __future__ import annotations

import re
import secrets
import threading
from datetime import date, datetime
from typing import Final

from pydantic import ValidationError

from claimcoach.calls.audio import sniff_audio
from claimcoach.calls.queue import TranscriptionQueue
from claimcoach.calls.types import (
    CallAdded,
    CallRecording,
    CallTranscript,
    PayerCall,
    TranscriptionQueued,
    new_call_id,
    transcript_item_id,
)
from claimcoach.cases.diagnosis import AppealDeadline, Diagnosis
from claimcoach.cases.errors import (
    CallNotFoundError,
    DocumentTooLargeError,
    DraftEditedError,
    FieldError,
    NoDocumentsError,
    NotCorrectedError,
    NotDiagnosedError,
    NotDraftedError,
    NotExtractedError,
)
from claimcoach.cases.extraction import CaseExtraction, FieldConfirmation
from claimcoach.cases.intake import UploadedFile, sniff, text_kind
from claimcoach.cases.models import (
    MAX_LISTED_CASES,
    MAX_PASTE_BYTES,
    Case,
    CaseList,
    DocumentAdded,
    SourceDocument,
    SourceKind,
)
from claimcoach.corpus.bundle import RuleCard
from claimcoach.corpus.errors import CaseClosedError, CaseNotFoundError, ProfileNotFoundError
from claimcoach.corpus.lookup import payer_rule_cards
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import (
    MAX_FEATURES_CHARS,
    AuditAction,
    CaseItem,
    CaseOutcome,
    CaseRecord,
    OutcomeRecord,
    utc_now,
)
from claimcoach.corrections.remedy import recommended_remedy
from claimcoach.corrections.types import CorrectedClaimDraft, RemedyAdvice
from claimcoach.events import CASE_ID_PATTERN, new_case_id
from claimcoach.letters.types import AppealDraft, DraftEdit
from claimcoach.models.manager import ModelUnavailableError
from claimcoach.outcomes.features import outcome_features
from claimcoach.pipeline.deadline import appeal_deadline

__all__ = [
    "CORRECTION_ITEM",
    "DIAGNOSIS_ITEM",
    "DRAFT_ITEM",
    "EXTRACTION_ITEM",
    "PASTE_CONTENT_TYPE",
    "CaseService",
    "new_source_id",
]

PASTE_CONTENT_TYPE: Final = "text/plain; charset=utf-8"
EXTRACTION_ITEM: Final = "extraction"
"""The item ID of a case's one extraction."""
DIAGNOSIS_ITEM: Final = "diagnosis"
"""The item ID of a case's one diagnosis."""
DRAFT_ITEM: Final = "draft"
"""The item ID of a case's one appeal draft (US-7.1)."""
CORRECTION_ITEM: Final = "correction"
"""The item ID of a case's one corrected-claim draft (US-7.4)."""


def new_source_id() -> str:
    """Return a new opaque source-document ID."""
    return f"src_{secrets.token_hex(8)}"


class CaseService:
    """Cases of every profile, stored in each profile's user scope.

    Args:
        corpus: The worker's corpus service (it opens the user stores).
        transcriptions: The payer-call transcription queue (US-11.1); without it calls can be
            attached but not queued.
    """

    def __init__(
        self, corpus: CorpusService, transcriptions: TranscriptionQueue | None = None
    ) -> None:
        """Keep the corpus service; no store opens until a call needs it."""
        self.corpus = corpus
        self.transcriptions = transcriptions
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

    def list_cases(self, profile: str) -> CaseList:
        """Return the profile's newest cases, without case content (not audited; US-10.1).

        A profile without a user scope has no cases yet.

        Raises:
            InvalidProfileError: ``profile`` is not a Hermes profile name.
        """
        try:
            store = self.store(profile)
        except ProfileNotFoundError:
            return CaseList(cases=[])
        return CaseList(cases=store.case_index(MAX_LISTED_CASES))

    def open(self, profile: str, case_id: str) -> Case:
        """Return the case with its source documents (audited ``case_opened``).

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
        """
        store = self.store(profile)
        return self._view(store, store.open_case(case_id))

    def _view(
        self, store: CorpusStore, record: CaseRecord, extraction: CaseExtraction | None = None
    ) -> Case:
        """The case as the pane shows it, read from ``store`` (not audited).

        ``extraction`` is the one just stored, when the caller has it, so it is not read again
        outside the case lock.
        """
        case_id = record.case_id
        extraction = extraction or self.extraction(store, case_id)
        diagnosis = self.diagnosis(store, case_id)
        cards = self.payer_cards(extraction)
        return _case(
            record,
            self.documents(store, case_id),
            extraction,
            diagnosis,
            deadline=self.deadline(extraction, cards),
            remedy=self.remedy(extraction, diagnosis, cards),
            draft=self.draft(store, case_id),
            correction=self.correction(store, case_id),
            outcome=store.outcome(case_id),
            calls=self.calls(store, case_id),
        )

    def payer_cards(self, extraction: CaseExtraction | None) -> list[RuleCard]:
        """Return the global rule cards of the extraction's payer; none when it was not read."""
        payer = None if extraction is None else extraction.payer_name.value
        return payer_rule_cards(self.corpus.global_store(), payer) if payer else []

    def deadline(
        self, extraction: CaseExtraction | None, cards: list[RuleCard] | None = None
    ) -> AppealDeadline | None:
        """Return the appeal deadline for ``extraction`` under today's global rule cards (US-6.3).

        Computed on every read, never stored: a confirmed denial date or a re-imported card shows
        at once, without running a model. ``cards`` are the payer's, when the caller read them.
        """
        if extraction is None:
            return None
        cards = self.payer_cards(extraction) if cards is None else cards
        return appeal_deadline(extraction, cards, date.today())

    @staticmethod
    def remedy(
        extraction: CaseExtraction | None, diagnosis: Diagnosis | None, cards: list[RuleCard]
    ) -> RemedyAdvice | None:
        """Return the remedy recommended for a current diagnosis (US-7.4 design decision 6).

        Computed on every read from the payer's ``cards``; a missing or stale diagnosis has none.
        """
        if (
            extraction is None
            or diagnosis is None
            or diagnosis.extraction_digest != extraction.digest()
        ):
            return None
        return recommended_remedy(diagnosis, extraction, cards)

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

    @staticmethod
    def diagnosis(store: CorpusStore, case_id: str) -> Diagnosis | None:
        """Return the case's stored diagnosis, if diagnosis ran (not audited)."""
        items = store.case_items(case_id, "diagnosis")
        return Diagnosis.model_validate_json(items[0].payload) if items else None

    @staticmethod
    def draft(store: CorpusStore, case_id: str) -> AppealDraft | None:
        """Return the case's stored appeal draft, if drafting ran (not audited; US-7.1)."""
        items = store.case_items(case_id, "draft")
        return AppealDraft.model_validate_json(items[0].payload) if items else None

    @staticmethod
    def correction(store: CorpusStore, case_id: str) -> CorrectedClaimDraft | None:
        """Return the case's stored corrected-claim draft, if one was drafted (not audited)."""
        items = store.case_items(case_id, "correction")
        return CorrectedClaimDraft.model_validate_json(items[0].payload) if items else None

    @staticmethod
    def recordings(store: CorpusStore, case_id: str) -> list[CallRecording]:
        """Return the case's call recordings, oldest first (not audited; US-11.1)."""
        return [
            CallRecording.model_validate_json(item.payload)
            for item in store.case_items(case_id, "call")
        ]

    def calls(self, store: CorpusStore, case_id: str) -> list[PayerCall]:
        """Return the case's calls with their latest job and transcript (not audited; US-11.1)."""
        jobs = (
            {}
            if self.transcriptions is None or store.profile is None
            else self.transcriptions.for_case(store.profile, case_id)
        )
        transcripts = {
            transcript.call_id: transcript
            for transcript in (
                CallTranscript.model_validate_json(item.payload)
                for item in store.case_items(case_id, "transcript")
            )
        }
        return [
            PayerCall(
                recording=recording,
                transcription=jobs.get(recording.call_id),
                transcript=transcripts.get(recording.call_id),
            )
            for recording in self.recordings(store, case_id)
        ]

    def _recording(self, store: CorpusStore, case_id: str, call_id: str) -> CallRecording:
        for recording in self.recordings(store, case_id):
            if recording.call_id == call_id:
                return recording
        raise CallNotFoundError

    def add_call(self, profile: str, case_id: str, upload: UploadedFile) -> CallAdded:
        """Attach a payer-call recording; its format comes from its bytes (audited ``call_added``).

        Raises:
            UnsupportedAudioError: Not WAV, MP3, FLAC, or M4A audio.
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
        """
        store = self._require_open(profile, case_id)
        recording = CallRecording(
            call_id=new_call_id(),
            format=sniff_audio(upload.data),
            filename=upload.filename,
            content_type=upload.content_type,
            size_bytes=len(upload.data),
            added_at=utc_now(),
        )
        item = CaseItem(
            case_id=case_id,
            item_id=recording.call_id,
            kind="call",
            created_at=recording.added_at,
            payload=recording.model_dump_json().encode(),
        )
        store.put_case_item(item, upload.data, audit=AuditAction.CALL_ADDED)
        return CallAdded(case_id=case_id, call=recording)

    def check_call(self, profile: str, case_id: str, call_id: str) -> None:
        """Refuse a transcription of a call that is not in an open case (US-11.1).

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
            CallNotFoundError: No such call in the case.
        """
        self._recording(self._require_open(profile, case_id), case_id, call_id)

    def queue_transcription(self, profile: str, case_id: str, call_id: str) -> TranscriptionQueued:
        """Queue the call for its profile's after-hours window, or return its pending job.

        Raises:
            ModelUnavailableError: This worker has no transcription queue.
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
            CallNotFoundError: No such call in the case.
        """
        if self.transcriptions is None:
            raise ModelUnavailableError
        self.check_call(profile, case_id, call_id)
        job = self.transcriptions.enqueue(profile, case_id, call_id)
        return TranscriptionQueued(case_id=case_id, job=job)

    def call_audio(self, profile: str, case_id: str, call_id: str) -> tuple[CallRecording, bytes]:
        """Return a recording with its bytes, for transcription (not audited; US-11.1).

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            CaseClosedError: The case closed (or was purged) while the job waited.
            CallNotFoundError: No such call in the case.
        """
        store = self._require_open(profile, case_id)
        recording = self._recording(store, case_id, call_id)
        data = store.case_item_data(case_id, call_id)
        if data is None:
            raise CallNotFoundError
        return recording, data

    def save_transcript(self, profile: str, case_id: str, transcript: CallTranscript) -> None:
        """Store a call's transcript, replacing an earlier one (audited ``call_transcribed``).

        Raises:
            CaseClosedError: The case closed while the call was transcribed.
        """
        item = CaseItem(
            case_id=case_id,
            item_id=transcript_item_id(transcript.call_id),
            kind="transcript",
            created_at=transcript.transcribed_at,
            payload=transcript.model_dump_json().encode(),
        )
        self.store(profile).put_case_item(item, audit=AuditAction.CALL_TRANSCRIBED)

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

    def check_open(self, profile: str, case_id: str) -> None:
        """Refuse a job's work on a case that closed after the job was started (US-8.1).

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
        """
        self._require_open(profile, case_id)

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

    def check_diagnosable(self, profile: str, case_id: str) -> None:
        """Refuse diagnosis before a job starts: the case must be open and extracted (US-6.1).

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case, or an ID events cannot carry (not ``new_case_id``).
            CaseClosedError: The case is closed or purged.
            NotExtractedError: The case has no extraction yet.
        """
        if not re.fullmatch(CASE_ID_PATTERN, case_id):
            raise CaseNotFoundError
        store = self._require_open(profile, case_id)
        if self.extraction(store, case_id) is None:
            raise NotExtractedError

    def check_draftable(self, profile: str, case_id: str) -> None:
        """Refuse drafting before a job starts: the case must be open and diagnosed (US-7.1).

        ``letters.draft.Drafter.check`` adds the diagnosis and template checks.

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case, or an ID events cannot carry (not ``new_case_id``).
            CaseClosedError: The case is closed or purged.
        """
        if not re.fullmatch(CASE_ID_PATTERN, case_id):
            raise CaseNotFoundError
        self._require_open(profile, case_id)

    def draft_inputs(self, profile: str, case_id: str) -> tuple[CaseExtraction, Diagnosis]:
        """Return the extraction and the diagnosis of it that a draft reads (not audited; US-7.1).

        Raises:
            NotDiagnosedError: No extraction, no diagnosis, or the diagnosis is stale (the fields
                changed since it ran).
        """
        store = self.store(profile)
        extraction = self.extraction(store, case_id)
        diagnosis = self.diagnosis(store, case_id)
        if (
            extraction is None
            or diagnosis is None
            or diagnosis.extraction_digest != extraction.digest()
        ):
            raise NotDiagnosedError
        return extraction, diagnosis

    def save_draft(
        self,
        profile: str,
        case_id: str,
        draft: AppealDraft,
        *,
        started: datetime | None = None,
    ) -> None:
        """Store the case's draft, replacing the previous one (audited ``case_drafted``; US-7.1).

        Args:
            profile: The case's profile.
            case_id: The case.
            draft: The new draft.
            started: When the draft job started; edits saved since then are kept.

        Raises:
            DraftEditedError: The biller saved edits after ``started``; nothing is replaced.
            CaseClosedError: The case was closed while drafting ran.
        """
        store = self.store(profile)
        with self._case_lock(profile, case_id):
            current = self.draft(store, case_id) if started is not None else None
            edited = None if current is None else current.edited_at
            if started is not None and edited is not None and edited >= started:
                raise DraftEditedError
            store.put_case_item(_draft_item(case_id, draft), audit=AuditAction.CASE_DRAFTED)

    def edit_draft(self, profile: str, case_id: str, edit: DraftEdit) -> Case:
        """Store the biller's text as the draft's text (audited ``draft_edited``; US-7.2).

        The draft's label, template, and provenance are kept; ``edited_at`` is now.

        Raises:
            NotDraftedError: The case has no draft.
            CaseNotFoundError: No such case.
            CaseClosedError: The case is closed or purged.
        """
        store = self._require_open(profile, case_id)
        with self._case_lock(profile, case_id):
            current = self.draft(store, case_id)
            if current is None:
                raise NotDraftedError
            edited = AppealDraft.model_validate(
                current.model_dump() | {"text": edit.text, "edited_at": utc_now()}
            )
            store.put_case_item(_draft_item(case_id, edited), audit=AuditAction.DRAFT_EDITED)
        return self._view(store, store.case_record(case_id))

    def save_correction(self, profile: str, case_id: str, draft: CorrectedClaimDraft) -> None:
        """Store the case's corrected-claim draft, replacing the previous one (US-7.4).

        Audited ``correction_drafted``.

        Raises:
            CaseClosedError: The case was closed while drafting ran.
        """
        store = self.store(profile)
        with self._case_lock(profile, case_id):
            store.put_case_item(
                _correction_item(case_id, draft), audit=AuditAction.CORRECTION_DRAFTED
            )

    def record_outcome(self, profile: str, case_id: str, outcome: CaseOutcome) -> Case:
        """Store how the case ended and close it (audited ``outcome_recorded``; US-8.1).

        A closed or purged case takes a later outcome, which corrects the first; its close date
        is kept, so the retention clock does not restart. The de-identified snapshot (US-8.2)
        is taken now; a purged case keeps the one taken before.

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
        """
        store = self.store(profile)
        with self._case_lock(profile, case_id):
            features = outcome_features(
                self.extraction(store, case_id), self.diagnosis(store, case_id)
            )
            snapshot = None if features is None else features.model_dump_json()
            if features is not None and len(features.model_dump_json()) > MAX_FEATURES_CHARS:
                # A claim of hundreds of lines: kept for the summary, too large to export.
                snapshot = features.model_copy(update={"facts": None}).model_dump_json()
            store.record_outcome(case_id, outcome, features=snapshot)
        return self._view(store, store.case_record(case_id))

    def record_export(self, profile: str, case_id: str) -> None:
        """Audit that the case's draft was written to a file (``draft_exported``; US-7.2)."""
        self.store(profile).record(case_id, AuditAction.DRAFT_EXPORTED)

    def draft_of(self, profile: str, case_id: str) -> AppealDraft:
        """Return the draft an export renders (not audited; US-7.2). A closed case still exports.

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            NotDraftedError: The case has no draft (or its content was purged).
        """
        store = self.store(profile)
        store.case_record(case_id)
        draft = self.draft(store, case_id)
        if draft is None:
            raise NotDraftedError
        return draft

    def record_correction_export(self, profile: str, case_id: str) -> None:
        """Audit that the corrected-claim draft was written to a file (``correction_exported``)."""
        self.store(profile).record(case_id, AuditAction.CORRECTION_EXPORTED)

    def correction_of(self, profile: str, case_id: str) -> tuple[CorrectedClaimDraft, bool]:
        """Return the corrected-claim draft an export renders, and whether it is stale (US-7.4).

        Not audited. A closed case still exports; a stale draft exports with a warning.

        Raises:
            ProfileNotFoundError: The profile has no user scope.
            CaseNotFoundError: No such case.
            NotCorrectedError: The case has no corrected-claim draft (or its content was purged).
        """
        store = self.store(profile)
        store.case_record(case_id)
        correction = self.correction(store, case_id)
        if correction is None:
            raise NotCorrectedError
        extraction = self.extraction(store, case_id)
        digest = None if extraction is None else extraction.digest()
        return correction, _stale(correction, digest, self.diagnosis(store, case_id))

    def extraction_of(self, profile: str, case_id: str) -> CaseExtraction:
        """Return the extraction a diagnosis reads (not audited: the job, not a person, reads it).

        Raises:
            NotExtractedError: The case has no extraction.
        """
        extraction = self.extraction(self.store(profile), case_id)
        if extraction is None:
            raise NotExtractedError
        return extraction

    def save_diagnosis(self, profile: str, case_id: str, diagnosis: Diagnosis) -> None:
        """Store the case's diagnosis, replacing the previous one (audited ``case_diagnosed``).

        Raises:
            CaseClosedError: The case was closed while diagnosis ran.
        """
        item = CaseItem(
            case_id=case_id,
            item_id=DIAGNOSIS_ITEM,
            kind="diagnosis",
            created_at=utc_now(),
            payload=diagnosis.model_dump_json().encode(),
        )
        self.store(profile).put_case_item(item, audit=AuditAction.CASE_DIAGNOSED)

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
        return self._view(store, store.case_record(case_id), confirmed)

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


def _draft_item(case_id: str, draft: AppealDraft) -> CaseItem:
    return CaseItem(
        case_id=case_id,
        item_id=DRAFT_ITEM,
        kind="draft",
        created_at=utc_now(),
        payload=draft.model_dump_json().encode(),
    )


def _correction_item(case_id: str, draft: CorrectedClaimDraft) -> CaseItem:
    return CaseItem(
        case_id=case_id,
        item_id=CORRECTION_ITEM,
        kind="correction",
        created_at=utc_now(),
        payload=draft.model_dump_json().encode(),
    )


def _stale(
    drafted: AppealDraft | CorrectedClaimDraft | None,
    digest: str | None,
    diagnosis: Diagnosis | None,
) -> bool:
    """A draft is stale once the fields or the diagnosis it was drafted from changed (US-7.1)."""
    return drafted is not None and (
        drafted.extraction_digest != digest
        or diagnosis is None
        or drafted.diagnosed_at != diagnosis.diagnosed_at
    )


def _case(  # noqa: PLR0913 - the case and each of its items
    record: CaseRecord,
    documents: list[SourceDocument],
    extraction: CaseExtraction | None = None,
    diagnosis: Diagnosis | None = None,
    *,
    deadline: AppealDeadline | None = None,
    remedy: RemedyAdvice | None = None,
    draft: AppealDraft | None = None,
    correction: CorrectedClaimDraft | None = None,
    outcome: OutcomeRecord | None = None,
    calls: list[PayerCall] | None = None,
) -> Case:
    digest = None if extraction is None else extraction.digest()
    stale = diagnosis is not None and diagnosis.extraction_digest != digest
    return Case(
        case_id=record.case_id,
        opened_at=record.opened_at,
        closed_at=record.closed_at,
        documents=documents,
        extraction=extraction,
        needs_confirmation=[] if extraction is None else extraction.needs_confirmation(),
        diagnosis=diagnosis,
        diagnosis_stale=stale,
        deadline=deadline,
        draft=draft,
        draft_stale=_stale(draft, digest, diagnosis),
        remedy=remedy,
        correction=correction,
        correction_stale=_stale(correction, digest, diagnosis),
        outcome=outcome,
        calls=calls or [],
    )
