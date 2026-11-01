"""Corpus embeddings (Qwen3-Embedding-8B) on a local server.

Implements: US-4.1 (``Embedder``; ``embedding_model_id`` is what each index records), US-14.1 (no
reranker and no query embedding: no case flow used retrieval). Rules: BR-1 (loopback only: endpoints
come from ``ModelManager.use``; proxies are never honored), BR-11, BR-14 (errors carry no text or
model output).

Embeddings use the OpenAI ``POST /v1/embeddings`` shape; documents are embedded as they are.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, TypeVar

import httpx
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claimcoach.corpus.store import Vectors
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.manager import EndpointProvider, ModelUnavailableError
from claimcoach.models.registry import ModelRegistry
from claimcoach.models.types import ModelRole

__all__ = ["Embedder", "embedding_model_id"]

BATCH: Final = 16
"""Texts per embeddings request."""


def embedding_model_id(registry: ModelRegistry) -> str:
    """Return the ID an index records: the ``embedding`` role's model directory."""
    return registry.roles[ModelRole.EMBEDDING].model_dir


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class _Embedding(_Loose):
    index: int = Field(ge=0)
    embedding: list[float] = Field(min_length=1)


class _Embeddings(_Loose):
    data: list[_Embedding]


ReplyT = TypeVar("ReplyT", bound=_Loose)


async def _post(
    url: str,
    body: dict[str, object],
    model: type[ReplyT],
    *,
    timeout: float,
    transport: httpx.AsyncBaseTransport | None,
) -> ReplyT:
    try:
        async with httpx.AsyncClient(
            timeout=timeout, transport=transport, trust_env=False
        ) as client:
            response = await client.post(url, json=body)
        response.raise_for_status()
        return model.model_validate_json(response.content)
    except (httpx.HTTPError, ValidationError) as exc:
        raise ModelUnavailableError from exc


class Embedder:
    """Embed texts with the ``embedding`` role.

    Args:
        models: ``ModelManager.use`` (or a test double with the same shape).
        timeout: Seconds per request.
        transport: Optional httpx transport for tests.
    """

    def __init__(
        self,
        models: EndpointProvider,
        *,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Store the model provider; no model is started until a call."""
        self._models = models
        self._timeout = timeout
        self._transport = transport

    async def embed_documents(self, texts: Sequence[str]) -> Vectors:
        """Return one float32 row per text, in order.

        Raises:
            ModelUnavailableError: The server is missing, failed, or answered with the wrong
                number of vectors or with vectors of different lengths.
        """
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        rows: list[list[float]] = []
        async with self._models(ModelRole.EMBEDDING) as endpoint:
            for start in range(0, len(texts), BATCH):
                batch = list(texts[start : start + BATCH])
                reply = await _post(
                    f"{endpoint.base_url}/embeddings",
                    {"model": DEFAULT_MODEL_ID, "input": batch},
                    _Embeddings,
                    timeout=self._timeout,
                    transport=self._transport,
                )
                data = sorted(reply.data, key=lambda item: item.index)
                if [item.index for item in data] != list(range(len(batch))):
                    raise ModelUnavailableError
                rows += [item.embedding for item in data]
        if len({len(row) for row in rows}) != 1:
            raise ModelUnavailableError
        return np.asarray(rows, dtype=np.float32)
