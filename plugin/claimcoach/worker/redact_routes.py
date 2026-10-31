"""Worker route that redacts a text with the local PHI model and the regex validators.

Implements: US-3.1 (``POST /redact``), US-3.2 (the agent-tool guard and hook call it). Rules: BR-2
(PHI goes gateway → worker → local model only), BR-14 (the response is the redacted text and
counts; a failure is the ``model_unavailable``, ``model_busy`` or ``redaction_failed`` envelope,
mapped from ``ModelError`` in ``create_app``), ES-8.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from claimcoach.redact.redactor import Redactor
from claimcoach.redact.types import RedactRequest, RedactResponse

__all__ = ["get_redactor", "router"]

router = APIRouter()


def get_redactor(request: Request) -> Redactor:
    """Return the worker's redactor (set by ``create_app``)."""
    return cast("Redactor", request.app.state.redactor)


@router.post("/redact", response_model=RedactResponse)
async def redact(
    body: RedactRequest, redactor: Annotated[Redactor, Depends(get_redactor)]
) -> RedactResponse:
    """Return ``body.text`` with every PHI span replaced by its category placeholder."""
    return RedactResponse.from_result(await redactor.redact_text(body.text))
