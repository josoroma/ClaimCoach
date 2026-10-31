"""The worker's FastAPI app: bearer-token gate, health route, envelope-only error responses.

Implements: US-1.2 (requests without the token get 401 + envelope), US-1.3 (worker side of
``/health``; unhandled errors become a generic envelope), US-2.2 (model routes, idle sweeper and
model-server shutdown in the lifespan), US-3.1 (``POST /redact`` with the PHI model), US-3.4
(a request ID per request, in every log line and the ``X-Request-ID`` header). Rules: ES-8
(every response is a typed model or the envelope), BR-14 (no exception text or request content in
responses or logs).
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from claimcoach import __version__
from claimcoach.api.models import ErrorCode, HealthResponse, envelope
from claimcoach.logs import get_logger, new_request_id, request_id_var
from claimcoach.models.acquire import Acquirer
from claimcoach.models.manager import ModelError, ModelManager
from claimcoach.redact.detector import PhiDetector
from claimcoach.redact.redactor import Redactor
from claimcoach.worker import model_routes, redact_routes

__all__ = ["create_app", "get_health", "router"]

router = APIRouter()
_log = get_logger("claimcoach.worker")


def get_health() -> HealthResponse:
    """Return the worker's health; a dependency so later stories can add checks."""
    return HealthResponse(version=__version__)


@router.get("/health", response_model=HealthResponse)
def health(status: Annotated[HealthResponse, Depends(get_health)]) -> HealthResponse:
    """Report that the worker is up."""
    return status


def _error(
    code: ErrorCode, status_code: int, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(envelope(code).model_dump(), status_code=status_code, headers=headers)


def _lifespan(
    models: ModelManager, jobs: Acquirer
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        sweeper = asyncio.create_task(models.run_sweeper())
        try:
            yield
        finally:
            sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper
            try:
                await jobs.shutdown()
            finally:
                await models.shutdown()  # never leave a model server behind (US-2.2)

    return lifespan


def create_app(
    token: str, models: ModelManager | None = None, *, redactor: Redactor | None = None
) -> FastAPI:
    """Build the worker app that accepts only ``Authorization: Bearer <token>``.

    Args:
        token: This launch's bearer token.
        models: The model manager; when given, the ``/models`` and ``/redact`` routes are mounted
            and the app's lifespan runs the idle sweeper and stops every model server on shutdown.
        redactor: The redactor behind ``/redact``; defaults to the PHI model of ``models``. Tests
            pass one over a fake model server to get ``/redact`` without a model manager.

    Returns:
        The ASGI app.
    """
    app = FastAPI(
        title="ClaimCoach worker",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    expected = f"Bearer {token}".encode()

    # Middleware, not a route dependency: it also covers unknown paths and every future route.
    @app.middleware("http")
    async def require_token(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = new_request_id()
        token = request_id_var.set(request_id)  # every log line of this request carries it
        try:
            return await _serve(request, call_next, request_id)
        finally:
            request_id_var.reset(token)

    async def _serve(
        request: Request, call_next: Callable[[Request], Awaitable[Response]], request_id: str
    ) -> Response:
        supplied = request.headers.get("authorization", "").encode()
        if not secrets.compare_digest(supplied, expected):
            _log.warning("rejected %s %s: bad token", request.method, request.url.path)
            response: Response = _error("unauthorized", 401, {"WWW-Authenticate": "Bearer"})
        else:
            try:
                response = await call_next(request)
            except Exception as exc:  # noqa: BLE001 - outermost boundary: always the envelope
                # Caught here so it never reaches Starlette's ServerErrorMiddleware, which would
                # log the traceback and message (possibly document text). Type only.
                _log.error(
                    "unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path
                )
                response = _error("internal_error", 500)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> Response:
        # Starlette's own 404/405 bodies are plain text; answer with the envelope instead.
        code: ErrorCode = "not_found" if exc.status_code == 404 else "invalid_request"
        return _error(code, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> Response:
        # FastAPI's default 422 body echoes the rejected input, which may be case content (BR-14).
        return _error("invalid_request", 422)

    @app.exception_handler(ModelError)
    async def model_error(_request: Request, exc: ModelError) -> Response:
        return _error(exc.code, exc.status_code)

    app.include_router(router)
    if models is not None:
        jobs = Acquirer(models)
        app.state.models = models
        app.state.acquirer = jobs
        app.router.lifespan_context = _lifespan(models, jobs)
        redactor = redactor or Redactor(PhiDetector(models.use))
        app.include_router(model_routes.router)
    if redactor is not None:
        app.state.redactor = redactor
        app.include_router(redact_routes.router)
    return app
