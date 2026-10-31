"""Typed REST bodies: the error envelope and the health response.

Implements: US-1.2 (worker 401 envelope), US-1.3 (``ApiError``, ``ErrorEnvelope``,
``HealthResponse``), US-2.2 to US-2.4 (model error codes), US-3.1 and US-3.2
(``redaction_failed``), US-3.5 (``SettingsResponse``), US-4.1 (``index_stale``,
``case_not_found``, ``profile_not_found``), US-4.2 (``corpus_unavailable``), US-5.1
(``document_too_large``, ``unsupported_document``, ``case_closed``), US-5.2
(``no_documents``, ``job_not_found``, ``extraction_failed``, ``processing_timeout``). Rules: ES-1
(Pydantic v2 for every REST body), ES-8 (typed success model or the envelope ``{"ok": false,
"error": {"code", "message"}}``), BR-14 (messages are fixed strings and never carry document text).
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ERROR_MESSAGES",
    "ApiError",
    "ErrorCode",
    "ErrorEnvelope",
    "HealthResponse",
    "SettingsResponse",
    "envelope",
]

ErrorCode = Literal[
    "invalid_request",
    "not_found",
    "unauthorized",
    "worker_unavailable",
    "worker_error",
    "invalid_worker_response",
    "not_implemented",
    "internal_error",
    "model_unavailable",
    "model_busy",
    "conversion_unavailable",
    "redaction_failed",
    "corpus_unavailable",
    "index_stale",
    "case_not_found",
    "profile_not_found",
    "document_too_large",
    "unsupported_document",
    "case_closed",
    "no_documents",
    "job_not_found",
    "extraction_failed",
    "processing_timeout",
]
"""Closed set of error codes the desktop half can switch on."""

ERROR_MESSAGES: Final[dict[ErrorCode, str]] = {
    "invalid_request": "The request did not match the expected parameters.",
    "not_found": "No such ClaimCoach route.",
    "unauthorized": "The request is missing a valid ClaimCoach worker token.",
    "worker_unavailable": "The ClaimCoach worker is not running.",
    "worker_error": "The ClaimCoach worker failed to complete the request.",
    "invalid_worker_response": "The ClaimCoach worker returned an unexpected response.",
    "not_implemented": "This ClaimCoach feature is not available yet.",
    "internal_error": "ClaimCoach hit an internal error.",
    "model_unavailable": "The local model for this step is missing or not responding.",
    "model_busy": "The local model is busy; try again when the current work finishes.",
    "conversion_unavailable": "This model cannot be converted until its source model is present.",
    "redaction_failed": "PHI redaction could not complete, so no result was returned.",
    "corpus_unavailable": "The ClaimCoach corpus store could not be opened.",
    "index_stale": "The corpus index was built with another embedding model; reindex it first.",
    "case_not_found": "No such case in this profile.",
    "profile_not_found": "This profile has no ClaimCoach case store.",
    "document_too_large": "The document is larger than ClaimCoach accepts (16 MiB per file).",
    "unsupported_document": "ClaimCoach accepts PDF, PNG, JPEG, and plain-text documents only.",
    "case_closed": "This case is closed, so it takes no new documents or changes.",
    "no_documents": "Add a source document to the case before processing it.",
    "job_not_found": "No such ClaimCoach job.",
    "extraction_failed": "The documents could not be read; enter the case fields by hand.",
    "processing_timeout": "Processing took too long and was stopped; process the case again.",
}
"""One fixed, PHI-free message per code; no caller text is ever echoed (BR-14)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApiError(_Strict):
    """Machine-readable error detail.

    Attributes:
        code: Stable error code.
        message: Fixed human-readable message for that code.
    """

    code: ErrorCode
    message: str = Field(min_length=1)


class ErrorEnvelope(_Strict):
    """The only failure body any ClaimCoach route returns."""

    ok: Literal[False] = False
    error: ApiError


class HealthResponse(_Strict):
    """Worker health as seen by the desktop half.

    Attributes:
        ok: Always ``True`` for a success body.
        status: Worker status.
        version: ClaimCoach version the worker runs.
    """

    ok: Literal[True] = True
    status: Literal["ok"] = "ok"
    version: str = Field(min_length=1)


class SettingsResponse(_Strict):
    """The settings the desktop half shows (US-3.5: the statusbar's richer-access flag).

    Attributes:
        ok: Always ``True``.
        richer_agent_access: Whether the user turned richer agent access on.
    """

    ok: Literal[True] = True
    richer_agent_access: bool


def envelope(code: ErrorCode) -> ErrorEnvelope:
    """Build the error envelope for ``code`` with its fixed message.

    Args:
        code: Stable error code.

    Returns:
        The envelope; callers serialize it with ``model_dump()``.
    """
    return ErrorEnvelope(error=ApiError(code=code, message=ERROR_MESSAGES[code]))
