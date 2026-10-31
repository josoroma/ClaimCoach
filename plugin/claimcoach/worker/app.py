"""The worker's FastAPI app: bearer-token gate, health route, envelope-only error responses.

Implements: US-1.2 (requests without the token get 401 + envelope), US-1.3 (worker side of
``/health``; unhandled errors become a generic envelope), US-2.2 (model routes, idle sweeper and
model-server shutdown in the lifespan), US-3.1 (``POST /redact`` with the PHI model), US-3.4
(a request ID per request, in every log line and the ``X-Request-ID`` header), US-4.1 to US-4.6
(``/corpus`` routes; the scheduled retention purge runs in the lifespan), US-5.1 (``/cases``
routes over the corpus's user stores), US-5.2 (extraction jobs and ``/jobs`` events; running jobs
are cancelled on shutdown), US-6.1 (diagnosis jobs share the registry and its model provider),
US-7.1 (the drafter, whose draft jobs share the registry), US-7.2 (exports and their sweeper).
Rules: ES-8
(every response is a typed model or the envelope), BR-14 (no exception text or request content in
responses or logs).
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from claimcoach import __version__
from claimcoach.api.models import ErrorCode, HealthResponse, envelope
from claimcoach.cases.errors import CaseError
from claimcoach.cases.service import CaseService
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.retention import RetentionJob
from claimcoach.corpus.service import CorpusService
from claimcoach.letters.draft import Drafter
from claimcoach.letters.export import Exports
from claimcoach.logs import get_logger, new_request_id, request_id_var
from claimcoach.models.acquire import Acquirer
from claimcoach.models.manager import EndpointProvider, ModelError, ModelManager
from claimcoach.pipeline.diagnose import Diagnoser
from claimcoach.pipeline.extract import Extractor
from claimcoach.pipeline.jobs import JobRegistry
from claimcoach.redact.detector import PhiDetector
from claimcoach.redact.redactor import Redactor
from claimcoach.worker import case_routes, corpus_routes, model_routes, redact_routes

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


async def _shutdown(steps: list[Callable[[], Awaitable[None]]]) -> None:
    """Run every step, even when an earlier one raises."""
    if steps:
        try:
            await steps[0]()
        finally:
            await _shutdown(steps[1:])


def _lifespan(
    tasks: list[Callable[[], Coroutine[Any, Any, None]]],
    shutdowns: list[Callable[[], Awaitable[None]]],
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        running = [asyncio.create_task(task()) for task in tasks]
        try:
            yield
        finally:
            try:
                for task in running:
                    task.cancel()
                # A task that already died is reported by type only, and never skips the rest.
                for outcome in await asyncio.gather(*running, return_exceptions=True):
                    if isinstance(outcome, Exception):
                        _log.error("background task ended: %s", type(outcome).__name__)
            finally:
                await _shutdown(shutdowns)

    return lifespan


def _closer(corpus: CorpusService) -> Callable[[], Awaitable[None]]:
    async def close() -> None:
        corpus.close()

    return close


def _mount_corpus(
    app: FastAPI,
    corpus: CorpusService,
    pipeline_models: EndpointProvider | None,
    tasks: list[Callable[[], Coroutine[Any, Any, None]]],
    shutdowns: list[Callable[[], Awaitable[None]]],
) -> None:
    """Mount the corpus and case routes, the scheduled purge, case jobs, and the stores' close."""
    app.state.corpus = corpus
    tasks.append(RetentionJob(corpus.purge_all).run)
    cases = CaseService(corpus)
    app.state.cases = cases
    exports = Exports(corpus.root)
    app.state.exports = exports
    tasks.append(exports.run)  # expired exports go even when nobody exports again
    shutdowns.append(exports.shutdown)  # and every export goes when the worker stops (BR-6)
    if pipeline_models is not None:
        jobs = JobRegistry(
            Extractor(cases, pipeline_models), diagnoser=Diagnoser(cases, pipeline_models)
        )
        app.state.jobs = jobs
        app.state.drafter = Drafter(cases, pipeline_models)
        shutdowns.append(jobs.shutdown)  # cancel extraction before the stores close
        app.include_router(case_routes.jobs_router)
    shutdowns.append(_closer(corpus))
    app.include_router(corpus_routes.router)
    app.include_router(case_routes.router)


def create_app(
    token: str,
    models: ModelManager | None = None,
    *,
    redactor: Redactor | None = None,
    corpus: CorpusService | None = None,
    pipeline_models: EndpointProvider | None = None,
) -> FastAPI:
    """Build the worker app that accepts only ``Authorization: Bearer <token>``.

    Args:
        token: This launch's bearer token.
        models: The model manager; when given, the ``/models`` and ``/redact`` routes are mounted
            and the app's lifespan runs the idle sweeper and stops every model server on shutdown.
        redactor: The redactor behind ``/redact``; defaults to the PHI model of ``models``. Tests
            pass one over a fake model server to get ``/redact`` without a model manager.
        corpus: The corpus scopes; when given, the ``/corpus`` and ``/cases`` routes are mounted,
            the lifespan runs the scheduled retention purge (US-4.5), and the stores close on
            shutdown.
        pipeline_models: The model provider of the case pipeline (extraction, US-5.2;
            classification, US-6.1); defaults to ``models.use``. With ``corpus`` it mounts the
            case jobs. Tests pass one over fake model servers.

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

    async def coded_error(_request: Request, exc: Exception) -> Response:
        # Each of these error types names its own fixed envelope code and status.
        coded = cast("ModelError | CorpusError | CaseError", exc)
        return _error(coded.code, coded.status_code)

    for coded_type in (ModelError, CorpusError, CaseError):
        app.add_exception_handler(coded_type, coded_error)

    app.include_router(router)
    tasks: list[Callable[[], Coroutine[Any, Any, None]]] = []
    shutdowns: list[Callable[[], Awaitable[None]]] = []
    if models is not None:
        jobs = Acquirer(models)
        app.state.models = models
        app.state.acquirer = jobs
        tasks.append(models.run_sweeper)

        async def stop_jobs() -> None:
            # Looked up at shutdown: ``app.state.acquirer`` is the one object that is stopped.
            await app.state.acquirer.shutdown()

        # Never leave a model server behind (US-2.2): the manager shuts down after the jobs.
        shutdowns += [stop_jobs, models.shutdown]
        redactor = redactor or Redactor(PhiDetector(models.use))
        app.include_router(model_routes.router)
    if redactor is not None:
        app.state.redactor = redactor
        app.include_router(redact_routes.router)
    if corpus is not None:
        if pipeline_models is None and models is not None:
            pipeline_models = models.use
        _mount_corpus(app, corpus, pipeline_models, tasks, shutdowns)
    if tasks:
        app.router.lifespan_context = _lifespan(tasks, shutdowns)
    return app
