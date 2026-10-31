"""Routes mounted by Hermes at ``/api/plugins/claimcoach/``.

Implements: US-1.3 (``router``; every route returns a typed model or the error envelope).
Rules: ES-8, PC-2, PC-4 (runs inside the gateway; proxies to the worker), BR-2 (PHI flows go
desktop pane → ``plugin_api.py`` → worker).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from claimcoach.api.client import WorkerClient, WorkerError
from claimcoach.api.models import ErrorEnvelope, HealthResponse, envelope
from claimcoach.paths import app_data_dir
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.token import read_token

__all__ = ["get_worker_client", "router"]

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorEnvelope} for status in (401, 502, 503)
}

router = APIRouter()


def get_worker_client() -> WorkerClient:
    """Build a client for the worker; one worker serves every Hermes profile on this Mac."""
    config = WorkerConfig(data_dir=app_data_dir())
    return WorkerClient(config.base_url, lambda: read_token(config.token_path))


def _error_response(exc: WorkerError) -> JSONResponse:
    return JSONResponse(envelope(exc.code).model_dump(), status_code=exc.status_code)


@router.get("/health", response_model=HealthResponse, responses=_ERRORS)
async def health(
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> HealthResponse | JSONResponse:
    """Proxy the worker's health, or answer with the error envelope."""
    try:
        return await client.health()
    except WorkerError as exc:
        return _error_response(exc)
