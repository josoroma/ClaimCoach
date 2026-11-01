"""Routes mounted by Hermes at ``/api/plugins/claimcoach/``.

Implements: US-1.3 (``router``; every route returns a typed model or the error envelope), US-2.2 and
US-2.3 (``GET /models/status``, polled by the settings page), US-2.4 (``POST /models/download`` and
``POST /models/convert``, which run only with ``confirm: true``), US-3.5 (``GET /settings`` for the
statusbar), US-5.1 (``POST /cases``, ``GET /cases/{case_id}``, ``POST /cases/{case_id}/documents``
forwarding the raw upload body, ``POST /cases/{case_id}/paste``; the active profile is passed to the
worker), US-5.2 (``POST /cases/{case_id}/process`` starts extraction and relays its progress events;
``POST /cases/{case_id}/fields`` confirms a value), US-6.1 (``POST /cases/{case_id}/diagnose``
starts a diagnosis and relays its events), US-7.1 (``POST /cases/{case_id}/draft`` starts a draft
and relays its events), US-7.2 (``POST /cases/{case_id}/draft/text`` saves the biller's edits;
``POST /cases/{case_id}/export`` answers where the exported file is, for the host's save dialog),
US-8.1 (``POST /cases/{case_id}/outcome`` records how the case ended, which closes it), US-8.2
(``GET /outcomes/summary`` is the manager's weekly summary of opted-in profiles' de-identified
outcomes), US-8.3 (``POST /outcomes/export`` writes the manager-approved fine-tune export). Rules:
ES-8, PC-2, PC-4 (runs inside the gateway; proxies to the worker), BR-1, BR-2 (PHI flows go desktop
pane → ``plugin_api.py`` → worker), BR-4 (no route sends, submits, or transmits a draft or case
content; every route here proxies to the loopback worker, and ``test_us_7_3_no_transmitting_route``
pins the route set), BR-14.

Hermes owns the FastAPI app, so its default 422 body (which echoes the rejected input) cannot be
replaced here; routes with a body read it raw and answer bad input with the envelope.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Final, TypeVar

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from claimcoach.api.client import WorkerClient, WorkerError
from claimcoach.api.models import (
    ErrorCode,
    ErrorEnvelope,
    HealthResponse,
    SettingsResponse,
    envelope,
)
from claimcoach.api.relay import start_relay
from claimcoach.cases.errors import CaseError
from claimcoach.cases.extraction import FieldConfirmation, JobStarted
from claimcoach.cases.intake import read_limited
from claimcoach.cases.models import (
    MAX_PASTE_BODY,
    MAX_UPLOAD_BODY,
    Case,
    CaseCreate,
    DocumentAdded,
    OutcomeRequest,
    PastedText,
)
from claimcoach.corpus.paths import active_profile
from claimcoach.events import EventSink, hermes_sink
from claimcoach.letters.types import (
    MAX_LETTER_CHARS,
    DraftEdit,
    DraftRequest,
    ExportedFile,
    ExportRequest,
)
from claimcoach.models.types import (
    AcquireResult,
    ConversionRequest,
    DownloadRequest,
    ModelsStatusResponse,
)
from claimcoach.outcomes.types import FineTuneExport, FineTuneExportRequest, WeeklySummary
from claimcoach.paths import app_data_dir
from claimcoach.settings import load_settings
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.token import read_token

__all__ = ["get_event_sink", "get_worker_client", "router"]

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 413, 415, 422, 502, 503)
}
_CASE_ID: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_WEEK: Final = re.compile(r"^[0-9]{4}-W[0-9]{2}$")
"""The shape of an ISO week; the worker checks that the week exists."""
SMALL_BODY: Final = 64 * 1024
"""Largest JSON body of a case action other than a paste or a draft (an empty object, a field)."""
MAX_DRAFT_BODY: Final = 12 * MAX_LETTER_CHARS + 1024
"""Largest ``DraftEdit`` JSON body read: JSON may escape one character as twelve bytes."""

BodyT = TypeVar("BodyT", bound=BaseModel)

router = APIRouter()


def get_worker_client() -> WorkerClient:
    """Build a client for the worker; one worker serves every Hermes profile on this Mac."""
    config = WorkerConfig(data_dir=app_data_dir())
    return WorkerClient(config.base_url, lambda: read_token(config.token_path))


def get_event_sink() -> EventSink | None:
    """Return Hermes' ``broadcast_plugin_event`` (``None`` outside the gateway)."""
    return hermes_sink()


def _envelope(code: ErrorCode, status_code: int) -> JSONResponse:
    return JSONResponse(envelope(code).model_dump(), status_code=status_code)


def _error_response(exc: WorkerError | CaseError) -> JSONResponse:
    return _envelope(exc.code, exc.status_code)


def _invalid() -> JSONResponse:
    return _envelope("invalid_request", 422)


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


async def _body(request: Request, model: type[BodyT], limit: int | None = None) -> BodyT | None:
    """Return the JSON body as ``model``, or ``None`` when it is not valid JSON of that shape.

    Raises:
        DocumentTooLargeError: The body is over ``limit``.
    """
    # Only JSON: a cross-site form or text/plain POST must not be able to start a download.
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        return None
    if limit is None:
        raw = await request.body()
    else:
        raw = await read_limited(request.stream(), limit, request.headers.get("content-length"))
    try:
        return model.model_validate_json(raw)
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


@router.post("/cases", response_model=Case, responses=_ERRORS)
async def create_case(
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> Case | JSONResponse:
    """Create an open, empty case in the active profile."""
    try:
        if await _body(request, CaseCreate, SMALL_BODY) is None:
            return _invalid()
        return await client.create_case(active_profile())
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)


@router.get("/cases/{case_id}", response_model=Case, responses=_ERRORS)
async def open_case(
    case_id: str,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> Case | JSONResponse:
    """Return a case of the active profile with its source documents."""
    if not _CASE_ID.fullmatch(case_id):
        return _invalid()
    try:
        return await client.get_case(active_profile(), case_id)
    except WorkerError as exc:
        return _error_response(exc)


@router.post("/cases/{case_id}/documents", response_model=DocumentAdded, responses=_ERRORS)
async def add_document(
    case_id: str,
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> DocumentAdded | JSONResponse:
    """Forward a ``ctx.rest`` upload to the worker unparsed (bounded, in memory)."""
    content_type = request.headers.get("content-type", "")
    if not _CASE_ID.fullmatch(case_id) or not content_type.lower().startswith(
        "multipart/form-data"
    ):
        return _invalid()
    try:
        body = await read_limited(
            request.stream(), MAX_UPLOAD_BODY, request.headers.get("content-length")
        )
        return await client.upload_document(active_profile(), case_id, body, content_type)
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)


@router.post("/cases/{case_id}/paste", response_model=DocumentAdded, responses=_ERRORS)
async def paste(
    case_id: str,
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> DocumentAdded | JSONResponse:
    """Attach pasted text (835 or a letter) to a case of the active profile."""
    if not _CASE_ID.fullmatch(case_id):
        return _invalid()
    try:
        body = await _body(request, PastedText, MAX_PASTE_BODY)
        if body is None:
            return _invalid()
        return await client.paste_text(active_profile(), case_id, body)
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)


async def _start_job(
    case_id: str,
    request: Request,
    start: Callable[[str, str], Awaitable[JobStarted]],
    relay: Callable[[JobStarted], object],
) -> JobStarted | JSONResponse:
    """Start a case job with ``start`` and relay its events; an empty JSON body is required."""
    try:
        if not _CASE_ID.fullmatch(case_id) or await _body(request, CaseCreate, SMALL_BODY) is None:
            return _invalid()
        started = await start(active_profile(), case_id)
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)
    relay(started)
    return started


@router.post("/cases/{case_id}/process", response_model=JobStarted, responses=_ERRORS)
async def process_case(
    case_id: str,
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
    sink: Annotated[EventSink | None, Depends(get_event_sink)],
) -> JobStarted | JSONResponse:
    """Start extracting the case; its progress arrives as ``plugin.claimcoach.case.progress``."""
    return await _start_job(
        case_id, request, client.start_extraction, lambda job: start_relay(client, job, sink)
    )


@router.post("/cases/{case_id}/diagnose", response_model=JobStarted, responses=_ERRORS)
async def diagnose_case(
    case_id: str,
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
    sink: Annotated[EventSink | None, Depends(get_event_sink)],
) -> JobStarted | JSONResponse:
    """Start diagnosing the case; its progress arrives as ``plugin.claimcoach.case.progress``."""
    return await _start_job(
        case_id, request, client.start_diagnosis, lambda job: start_relay(client, job, sink)
    )


@router.post("/cases/{case_id}/draft", response_model=JobStarted, responses=_ERRORS)
async def draft_case(
    case_id: str,
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
    sink: Annotated[EventSink | None, Depends(get_event_sink)],
) -> JobStarted | JSONResponse:
    """Start drafting the appeal; progress arrives as ``plugin.claimcoach.case.progress``.

    The body is ``{}`` (the denial reason picks the template) or names a ``template_id``.
    """
    try:
        body = await _body(request, DraftRequest, SMALL_BODY)
        if not _CASE_ID.fullmatch(case_id) or body is None:
            return _invalid()
        started = await client.start_draft(active_profile(), case_id, body)
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)
    start_relay(client, started, sink)
    return started


@router.post("/cases/{case_id}/draft/text", response_model=Case, responses=_ERRORS)
async def edit_draft(
    case_id: str,
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> Case | JSONResponse:
    """Store the biller's edited text as the case's draft."""
    try:
        body = await _body(request, DraftEdit, MAX_DRAFT_BODY)
        if not _CASE_ID.fullmatch(case_id) or body is None:
            return _invalid()
        return await client.edit_draft(active_profile(), case_id, body)
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)


@router.post("/cases/{case_id}/export", response_model=ExportedFile, responses=_ERRORS)
async def export_draft(
    case_id: str,
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> ExportedFile | JSONResponse:
    """Export the stored draft as PDF or DOCX; the answer says where the file is on this Mac."""
    try:
        body = await _body(request, ExportRequest, SMALL_BODY)
        if not _CASE_ID.fullmatch(case_id) or body is None:
            return _invalid()
        return await client.export_draft(active_profile(), case_id, body)
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)


@router.post("/cases/{case_id}/outcome", response_model=Case, responses=_ERRORS)
async def record_outcome(
    case_id: str,
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> Case | JSONResponse:
    """Store how the case ended (overturned, upheld, or written off); the case closes."""
    try:
        body = await _body(request, OutcomeRequest, SMALL_BODY)
        if not _CASE_ID.fullmatch(case_id) or body is None:
            return _invalid()
        return await client.record_outcome(active_profile(), case_id, body)
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)


@router.post("/cases/{case_id}/fields", response_model=Case, responses=_ERRORS)
async def confirm_field(
    case_id: str,
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> Case | JSONResponse:
    """Store the biller's value for one field as confirmed."""
    try:
        body = await _body(request, FieldConfirmation, SMALL_BODY)
        if not _CASE_ID.fullmatch(case_id) or body is None:
            return _invalid()
        return await client.confirm_field(active_profile(), case_id, body)
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)


@router.get("/outcomes/summary", response_model=WeeklySummary, responses=_ERRORS)
async def weekly_summary(
    client: Annotated[WorkerClient, Depends(get_worker_client)],
    week: str | None = None,
) -> WeeklySummary | JSONResponse:
    """The manager's weekly summary: de-identified outcomes of opted-in profiles only (US-8.2).

    ``week`` is an ISO week (``2026-W44``); the last completed week by default.
    """
    if week is not None and not _WEEK.fullmatch(week):
        return _invalid()
    try:
        return await client.weekly_summary(week)
    except WorkerError as exc:
        return _error_response(exc)


@router.post("/outcomes/export", response_model=FineTuneExport, responses=_ERRORS)
async def export_fine_tune(
    request: Request,
    client: Annotated[WorkerClient, Depends(get_worker_client)],
) -> FineTuneExport | JSONResponse:
    """Write the de-identified fine-tune export; refused without the manager's approval (US-8.3).

    The body is ``{"approval": {"manager": "<name>", "approved": true}}``.
    """
    try:
        body = await _body(request, FineTuneExportRequest, SMALL_BODY)
        if body is None:
            return _invalid()
        return await client.export_fine_tune(body)
    except (CaseError, WorkerError) as exc:
        return _error_response(exc)
