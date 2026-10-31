"""Typed REST bodies: the error envelope and the health response.

Implements: US-1.2 (worker 401 envelope), US-1.3 (``ApiError``, ``ErrorEnvelope``,
``HealthResponse``), US-2.2 to US-2.4 (model error codes). Rules: ES-1 (Pydantic v2 for every
REST body), ES-8 (typed success model or the envelope ``{"ok": false, "error": {"code",
"message"}}``), BR-14 (messages are fixed strings and never carry document text).
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


def envelope(code: ErrorCode) -> ErrorEnvelope:
    """Build the error envelope for ``code`` with its fixed message.

    Args:
        code: Stable error code.

    Returns:
        The envelope; callers serialize it with ``model_dump()``.
    """
    return ErrorEnvelope(error=ApiError(code=code, message=ERROR_MESSAGES[code]))
