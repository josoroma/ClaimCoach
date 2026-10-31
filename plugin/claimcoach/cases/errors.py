"""Case request errors and the envelope codes the worker answers them with.

Implements: US-5.1 (``MalformedUploadError``, ``UnsupportedDocumentError``,
``DocumentTooLargeError``), US-5.2 (``NoDocumentsError``, ``FieldError``, ``JobNotFoundError``),
US-6.1 (``NotExtractedError``, ``DiagnosisFailedError``).
Rules: ES-8 (each error maps to one fixed envelope code), BR-14 (no error carries content).
"""

from __future__ import annotations

from typing import ClassVar

from claimcoach.api.models import ErrorCode

__all__ = [
    "CaseError",
    "DiagnosisFailedError",
    "DocumentTooLargeError",
    "FieldError",
    "JobNotFoundError",
    "MalformedUploadError",
    "NoDocumentsError",
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
