"""The single httpx client the gateway uses to reach the worker.

Implements: US-1.3 (one ``WorkerClient`` with typed methods; ``httpx.HTTPError`` and
``ValidationError`` caught explicitly, no bare ``except``), US-2.2 and US-2.4 (model status,
download, and conversion calls; the worker's own model error codes reach the desktop half), US-3.2
(``redact`` for the agent-tool guard).
Rules: ES-1, ES-8, PC-4 (the gateway only proxies; heavy work runs in the worker), BR-14 (a relayed
error keeps only its code; the message is the fixed one for that code).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from claimcoach.api.models import ErrorCode, ErrorEnvelope, HealthResponse
from claimcoach.models.types import (
    AcquireResult,
    ConversionRequest,
    DownloadRequest,
    ModelsStatusResponse,
)
from claimcoach.redact.types import RedactRequest, RedactResponse

__all__ = [
    "RELAYED_CODES",
    "InvalidWorkerResponseError",
    "WorkerClient",
    "WorkerError",
    "WorkerFailedError",
    "WorkerRejectedError",
    "WorkerUnauthorizedError",
    "WorkerUnavailableError",
]

ModelT = TypeVar("ModelT", bound=BaseModel)

RELAYED_CODES: Final[dict[ErrorCode, int]] = {
    "invalid_request": 422,
    "model_unavailable": 503,
    "model_busy": 409,
    "conversion_unavailable": 409,
}
"""Worker error codes the desktop half acts on, with the status the gateway answers them with."""


class WorkerError(Exception):
    """A worker call failed; ``code`` and ``status_code`` say how to answer the desktop half."""

    code: ErrorCode = "worker_error"
    status_code: int = 502


class WorkerUnavailableError(WorkerError):
    """The worker is not running, not reachable, or has not issued a token yet."""

    code = "worker_unavailable"
    status_code = 503


class WorkerUnauthorizedError(WorkerError):
    """The worker rejected the bearer token."""

    code = "unauthorized"
    status_code = 401


class WorkerFailedError(WorkerError):
    """The worker answered with an error status."""

    code = "worker_error"
    status_code = 502


class WorkerRejectedError(WorkerError):
    """The worker refused the request with one of ``RELAYED_CODES``."""

    def __init__(self, code: ErrorCode) -> None:
        """Keep the worker's code and its gateway status; never the worker's message."""
        super().__init__(code)
        self.code = code
        self.status_code = RELAYED_CODES[code]


class InvalidWorkerResponseError(WorkerError):
    """The worker answered 2xx with a body that does not match the expected model."""

    code = "invalid_worker_response"
    status_code = 502


class WorkerClient:
    """Typed calls to the worker's HTTP API.

    Args:
        base_url: Root URL of the worker, e.g. ``http://127.0.0.1:18200``.
        token_provider: Returns the current per-launch token, or ``None`` before the first launch.
            Called on every request because the token changes on every worker start.
        transport: Optional httpx transport (tests pass an ``ASGITransport``).
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        token_provider: Callable[[], str | None],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 5.0,
    ) -> None:
        """Store the connection settings; no connection is opened until a call."""
        self._base_url = base_url
        self._token_provider = token_provider
        self._transport = transport
        self._timeout = timeout

    async def health(self) -> HealthResponse:
        """Return the worker's health.

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("GET", "/health", HealthResponse)

    async def models_status(self) -> ModelsStatusResponse:
        """Return the status of every model role.

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("GET", "/models/status", ModelsStatusResponse)

    async def download_model(self, request: DownloadRequest) -> AcquireResult:
        """Ask the worker to download a role's model (only runs when ``confirm`` is true).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("POST", "/models/download", AcquireResult, request)

    async def convert_model(self, request: ConversionRequest) -> AcquireResult:
        """Ask the worker to convert a role's model locally (only when ``confirm`` is true).

        Raises:
            WorkerError: The call failed; the subclass names why.
        """
        return await self._request("POST", "/models/convert", AcquireResult, request)

    async def redact(self, request: RedactRequest) -> RedactResponse:
        """Ask the worker to redact a text with its local PHI model and validators.

        Raises:
            WorkerError: The call failed; the subclass names why. No text is returned then.
        """
        return await self._request("POST", "/redact", RedactResponse, request)

    async def _request(
        self,
        method: Literal["GET", "POST"],
        path: str,
        model: type[ModelT],
        body: BaseModel | None = None,
    ) -> ModelT:
        token = self._token_provider()
        if token is None:
            raise WorkerUnavailableError
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                transport=self._transport,
                timeout=self._timeout,
                trust_env=False,  # never route the token or case data through a proxy
            ) as client:
                headers = {"Authorization": f"Bearer {token}"}
                content = None
                if body is not None:
                    headers["Content-Type"] = "application/json"
                    content = body.model_dump_json()
                response = await client.request(method, path, headers=headers, content=content)
        except httpx.HTTPError as exc:
            raise WorkerUnavailableError from exc
        if response.status_code == httpx.codes.UNAUTHORIZED:
            raise WorkerUnauthorizedError
        if response.is_error:
            raise _rejection(response)
        try:
            return model.model_validate_json(response.content)
        except ValidationError as exc:
            raise InvalidWorkerResponseError from exc


def _rejection(response: httpx.Response) -> WorkerError:
    """Relay a worker error whose envelope carries a code the desktop half acts on.

    The status must be the one that code is answered with, so an unexpected failure that happens
    to carry such a code still maps to ``worker_error``.
    """
    try:
        code = ErrorEnvelope.model_validate_json(response.content).error.code
    except ValidationError:
        return WorkerFailedError()
    if RELAYED_CODES.get(code) == response.status_code:
        return WorkerRejectedError(code)
    return WorkerFailedError()
