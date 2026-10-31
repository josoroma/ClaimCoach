"""The single httpx client the gateway uses to reach the worker.

Implements: US-1.3 (one ``WorkerClient`` with typed methods; ``httpx.HTTPError`` and
``ValidationError`` caught explicitly, no bare ``except``). Rules: ES-1, ES-8, PC-4 (the gateway
only proxies; heavy work runs in the worker).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from claimcoach.api.models import ErrorCode, HealthResponse

__all__ = [
    "InvalidWorkerResponseError",
    "WorkerClient",
    "WorkerError",
    "WorkerFailedError",
    "WorkerUnauthorizedError",
    "WorkerUnavailableError",
]

ModelT = TypeVar("ModelT", bound=BaseModel)


class WorkerError(Exception):
    """A worker call failed; ``code`` and ``status_code`` say how to answer the desktop half."""

    code: ClassVar[ErrorCode]
    status_code: ClassVar[int]


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
        return await self._get("/health", HealthResponse)

    async def _get(self, path: str, model: type[ModelT]) -> ModelT:
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
                response = await client.get(path, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            raise WorkerUnavailableError from exc
        if response.status_code == httpx.codes.UNAUTHORIZED:
            raise WorkerUnauthorizedError
        if response.is_error:
            raise WorkerFailedError
        try:
            return model.model_validate_json(response.content)
        except ValidationError as exc:
            raise InvalidWorkerResponseError from exc
