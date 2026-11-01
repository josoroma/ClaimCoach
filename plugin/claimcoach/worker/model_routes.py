"""Worker routes for local model management, mounted at ``/models`` when a manager is given.

Implements: US-2.2 (``GET /models/status``; ``POST /models/{role}/load`` is a request that needs the
role; ``POST /models/{role}/unload``), US-2.3 (status reports ``queued``), US-2.4
(``POST /models/download``; status reports weights and jobs), US-14.1 (no ``/models/convert``).
Rules:
ES-8 (typed model or envelope; ``ModelError`` is mapped in ``create_app``), BR-1, BR-14.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from claimcoach.models.acquire import Acquirer
from claimcoach.models.manager import ModelManager
from claimcoach.models.types import (
    AcquireResult,
    DownloadRequest,
    ModelRole,
    ModelsStatusResponse,
    ModelStatus,
)

__all__ = ["get_acquirer", "get_models", "router"]

router = APIRouter(prefix="/models")


def get_models(request: Request) -> ModelManager:
    """Return the worker's model manager (set by ``create_app``)."""
    return cast("ModelManager", request.app.state.models)


def get_acquirer(request: Request) -> Acquirer:
    """Return the worker's download runner (set by ``create_app``)."""
    return cast("Acquirer", request.app.state.acquirer)


Models = Annotated[ModelManager, Depends(get_models)]
Jobs = Annotated[Acquirer, Depends(get_acquirer)]


@router.get("/status", response_model=ModelsStatusResponse)
async def status(models: Models, jobs: Jobs) -> ModelsStatusResponse:
    """Report every role: server state, weights, venv, jobs, and queued requests."""
    return models.status(jobs.states())


@router.post("/download", response_model=AcquireResult)
async def download(body: DownloadRequest, jobs: Jobs) -> AcquireResult:
    """Download a role's model; only ``confirm: true`` reaches the network (BR-1)."""
    return await jobs.download(body)


@router.post("/{role}/load", response_model=ModelStatus)
async def load(role: ModelRole, models: Models) -> ModelStatus:
    """Start the role's server if needed and return once it is healthy."""
    async with models.use(role):
        pass
    return models.role_status(role)


@router.post("/{role}/unload", response_model=ModelStatus)
async def unload(role: ModelRole, models: Models) -> ModelStatus:
    """Stop the role's server now unless a request is using it."""
    return await models.unload(role)
