"""Case request errors and the envelope codes the worker answers them with.

Implements: US-5.1 (``MalformedUploadError``, ``UnsupportedDocumentError``,
``DocumentTooLargeError``), US-5.2 (``NoDocumentsError``, ``FieldError``, ``JobNotFoundError``),
US-6.1 (``NotExtractedError``, ``DiagnosisFailedError``), US-7.1 (``NotDiagnosedError``,
``NoLetterTemplateError``, ``DraftingFailedError``), US-7.2 (``NotDraftedError``,
``DraftEditedError``).
Rules: ES-8 (each error maps to one fixed envelope code), BR-14 (no error carries content).
"""

from __future__ import annotations

from typing import ClassVar

from claimcoach.api.models import ErrorCode

__all__ = [
    "CaseError",
    "DiagnosisFailedError",
    "DocumentTooLargeError",
    "DraftEditedError",
    "DraftingFailedError",
    "FieldError",
    "JobNotFoundError",
    "MalformedUploadError",
    "NoDocumentsError",
    "NoLetterTemplateError",
    "NotDiagnosedError",
    "NotDraftedError",
    "NotExtractedError",
    "UnsupportedDocumentError",
]


class CaseError(Exception):
    """A case request was refused; ``code`` and ``status_code`` say how the worker answers."""

    code: ClassVar[ErrorCode] = "invalid_request"
    status_code: ClassVar[int] = 422


class MalformedUploadError(CaseError):
    """The body is not one ``multipart/form-data`` part named ``file``."""


class UnsupportedDocumentError(CaseError):
    """The bytes are not a PDF, PNG, JPEG, or UTF-8 text."""

    code: ClassVar[ErrorCode] = "unsupported_document"
    status_code: ClassVar[int] = 415


class DocumentTooLargeError(CaseError):
    """The file or the pasted text is over the limit."""

    code: ClassVar[ErrorCode] = "document_too_large"
    status_code: ClassVar[int] = 413


class NoDocumentsError(CaseError):
    """Extraction needs at least one source document."""

    code: ClassVar[ErrorCode] = "no_documents"
    status_code: ClassVar[int] = 409


class FieldError(CaseError):
    """No such field, no extraction yet, or a value that is not valid for the field."""


class JobNotFoundError(CaseError):
    """No job with that ID (it never existed, or it ended more than ten minutes ago)."""

    code: ClassVar[ErrorCode] = "job_not_found"
    status_code: ClassVar[int] = 404


class NotExtractedError(CaseError):
    """Diagnosis needs the case's extraction, and the case has none yet."""

    code: ClassVar[ErrorCode] = "not_extracted"
    status_code: ClassVar[int] = 409


class DiagnosisFailedError(CaseError):
    """The classification model's reply did not validate as a diagnosis."""

    code: ClassVar[ErrorCode] = "diagnosis_failed"
    status_code: ClassVar[int] = 502


class NotDiagnosedError(CaseError):
    """Drafting needs a diagnosis of the case's current fields (US-7.1)."""

    code: ClassVar[ErrorCode] = "not_diagnosed"
    status_code: ClassVar[int] = 409


class NoLetterTemplateError(CaseError):
    """No letter template in the global corpus matches the draft request (US-7.1)."""

    code: ClassVar[ErrorCode] = "no_letter_template"
    status_code: ClassVar[int] = 409


class DraftingFailedError(CaseError):
    """The drafting model's reply held no usable letter (US-7.1)."""

    code: ClassVar[ErrorCode] = "drafting_failed"
    status_code: ClassVar[int] = 502


class DraftEditedError(CaseError):
    """The biller saved edits while a draft job ran; the job keeps them (US-7.2)."""

    code: ClassVar[ErrorCode] = "draft_edited"
    status_code: ClassVar[int] = 409


class NotDraftedError(CaseError):
    """Editing or exporting needs the case's draft, and the case has none yet (US-7.2)."""

    code: ClassVar[ErrorCode] = "not_drafted"
    status_code: ClassVar[int] = 409
