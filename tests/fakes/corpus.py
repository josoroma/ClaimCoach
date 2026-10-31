"""Helpers for corpus tests: a corpus service over the fake model server and a temp Hermes root.

Implements: US-4.1 to US-4.6 test harness (ES-4: offline; the fake OpenAI-compatible server stands
in for Qwen3-Embedding-8B and Qwen3-Reranker-8B, ``InMemoryKeyProvider`` for the Keychain).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

import httpx
import numpy as np
from fastapi import FastAPI

from claimcoach.api.client import WorkerClient
from claimcoach.corpus.crypto import InMemoryKeyProvider, KeyProvider
from claimcoach.corpus.embed import Embedder, Reranker, embedding_model_id
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.store import CorpusStore, Vectors, split_text
from claimcoach.corpus.types import CorpusScope, Document, utc_now
from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry
from claimcoach.worker.app import create_app
from tests.fakes.fake_model_server import EMBED_DIM, FakeModelServer, fake_embedding
from tests.fakes.phi import static_models

__all__ = [
    "MODEL_ID",
    "TOKEN",
    "add_case_document",
    "corpus_client",
    "make_service",
    "vectors_for",
]

TOKEN: Final = "corpus-test-token"
MODEL_ID: Final = embedding_model_id(ModelRegistry.load(DEFAULT_REGISTRY))
"""The embedding model the default ``models.yaml`` configures (Qwen3-Embedding-8B)."""


def vectors_for(texts: list[str]) -> Vectors:
    """The fake server's embeddings of ``texts`` as a float32 matrix."""
    return np.asarray([fake_embedding(t) for t in texts], dtype=np.float32).reshape(-1, EMBED_DIM)


def make_service(
    root: Path,
    server: FakeModelServer,
    *,
    keys: KeyProvider | None = None,
    model_id: str = MODEL_ID,
) -> CorpusService:
    """A corpus service over ``root`` whose models are the fake server."""
    models = static_models(server.base_url)
    return CorpusService(
        root,
        keys or InMemoryKeyProvider(),
        Embedder(models),
        Reranker(models),
        embedding_model_id=model_id,
    )


def add_case_document(
    store: CorpusStore,
    case_id: str,
    text: str,
    *,
    title: str = "Denial letter",
    closed_days_ago: int | None = None,
    now: datetime | None = None,
    create: bool = True,
) -> Document:
    """Create ``case_id`` (optionally closed some days ago) and store one source document."""
    when = now or utc_now()
    if create:
        store.create_case(case_id, at=when - timedelta(days=400))
    document = Document(
        doc_id=f"{case_id}-src-{len(text)}",
        scope=CorpusScope.USER,
        case_id=case_id,
        kind="source",
        title=title,
        text=text,
    )
    chunks = split_text(text)
    store.put_document(document, chunks, vectors_for(chunks))
    if closed_days_ago is not None:
        store.close_case(case_id, at=when - timedelta(days=closed_days_ago))
    return document


@contextmanager
def corpus_client(service: CorpusService) -> Iterator[tuple[WorkerClient, FastAPI]]:
    """A ``WorkerClient`` over the worker app that serves ``service`` (no lifespan)."""
    app = create_app(TOKEN, corpus=service)
    transport = httpx.ASGITransport(app=app)
    yield WorkerClient("http://worker", lambda: TOKEN, transport=transport), app
