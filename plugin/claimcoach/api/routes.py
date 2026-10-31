"""Routes mounted by Hermes at ``/api/plugins/claimcoach/``.

Implements: US-1.3 (``router``; every route returns a typed model or the error envelope), US-2.2
and US-2.3 (``GET /models/status``, polled by the settings page), US-2.4 (``POST /models/download``
and ``POST /models/convert``, which run only with ``confirm: true``), US-3.5 (``GET /settings``
for the statusbar). Rules: ES-8, PC-2, PC-4
(runs inside the gateway; proxies to the worker), BR-1, BR-2 (PHI flows go desktop pane →
``plugin_api.py`` → worker), BR-14.

Hermes owns the FastAPI app, so its default 422 body (which echoes the rejected input) cannot be
replaced here; routes with a body read it raw and answer bad input with the envelope.
"""

from __future__ import annotations

from typing import Annotated, Any, TypeVar

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from claimcoach.api.client import WorkerClient, WorkerError
from claimcoach.api.models import ErrorEnvelope, HealthResponse, SettingsResponse, envelope
from claimcoach.models.types import (
    AcquireResult,
    ConversionRequest,
    DownloadRequest,
    ModelsStatusResponse,
)
from claimcoach.paths import app_data_dir
from claimcoach.settings import load_settings
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.token import read_token

__all__ = ["get_worker_client", "router"]

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorEnvelope} for status in (401, 409, 422, 502, 503)
}

BodyT = TypeVar("BodyT", bound=BaseModel)

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


@router.get("/settings", response_model=SettingsResponse)
def settings() -> SettingsResponse:
    """Return the settings the desktop half displays; read in the gateway, no worker needed."""
    return SettingsResponse(richer_agent_access=load_settings().richer_agent_access)


@router.get("/models/status", response_model=ModelsStatusResponse, responses=_ERRORS)
async def models_status(
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> ModelsStatusResponse | JSONResponse:
    """Proxy the status of every model role: server state, weights, venv, queued requests."""
    try:
        return await client.models_status()
    except WorkerError as exc:
        return _error_response(exc)


async def _body(request: Request, model: type[BodyT]) -> BodyT | None:
    # Only JSON: a cross-site form or text/plain POST must not be able to start a download.
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        return None
    try:
        return model.model_validate_json(await request.body())
    except ValidationError:
        return None


@router.post("/models/download", response_model=AcquireResult, responses=_ERRORS)
async def download_model(
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> AcquireResult | JSONResponse:
    """Download a role's model after the user answered; ``confirm: false`` fetches nothing."""
    body = await _body(request, DownloadRequest)
    if body is None:
        return JSONResponse(envelope("invalid_request").model_dump(), status_code=422)
    try:
        return await client.download_model(body)
    except WorkerError as exc:
        return _error_response(exc)


@router.post("/models/convert", response_model=AcquireResult, responses=_ERRORS)
async def convert_model(
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> AcquireResult | JSONResponse:
    """Convert a role's source model to local MLX 4-bit after the user answered."""
    body = await _body(request, ConversionRequest)
    if body is None:
        return JSONResponse(envelope("invalid_request").model_dump(), status_code=422)
    try:
        return await client.convert_model(body)
    except WorkerError as exc:
        return _error_response(exc)
