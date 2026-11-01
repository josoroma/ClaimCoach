"""Fake OpenAI-compatible model server for offline tests.

Implements: US-1.4 (``/v1/models`` and ``/v1/chat/completions`` with canned responses). Rules:
ES-4 (offline tests use a fake OpenAI-compatible server; real-model tests are marked ``models``).

It runs uvicorn on ``127.0.0.1`` with an ephemeral port in a daemon thread, so code under test
talks to it over a real loopback socket exactly as it would talk to ``mlx_lm.server``.

US-2.2 also launches it as a model-server *process* from ``models.yaml``::

    python -m tests.fakes.fake_model_server --host 127.0.0.1 --port 18202 [--health error]
        [--ignore-sigterm] [--reply-file PATH]

US-3.1 passes ``--model default_model --reply-file reply.json`` to stand in for the PHI model (a
file, because ``models.yaml`` reads ``{...}`` in a command as a placeholder).

US-5.2 accepts OpenAI content parts (text plus ``image_url``) for the vision model.

US-12.2 adds ``responders``: a model ID mapped to a function of the request, for a fake that answers
each prompt on its own (a classifier that reads the case's codes).

US-4.1 and US-4.4 add ``/v1/embeddings`` (a deterministic hashed bag of words, ``EMBED_DIM``
long, so texts that share words are near each other). ``embed_overrides`` pins the vector of an
exact input text, so a test can make one chunk the nearest neighbour of a query.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import signal
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, get_args

import uvicorn
from fastapi import FastAPI, Response
from pydantic import BaseModel, ConfigDict

__all__ = [
    "DEFAULT_REPLY",
    "EMBED_DIM",
    "ChatMessage",
    "ChatRequest",
    "EmbeddingsRequest",
    "FakeModelServer",
    "Health",
    "fake_embedding",
    "main",
]

Health = Literal["ok", "error", "text", "no-data"]
"""How ``/v1/models`` answers: a model list, HTTP 503, plain text, or JSON without ``data``."""

DEFAULT_REPLY = '{"ok": true}'
EMBED_DIM = 64
_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def fake_embedding(text: str) -> list[float]:
    """Hashed bag of words: each word adds 1 to one of ``EMBED_DIM`` slots."""
    vector = [0.0] * EMBED_DIM
    for word in _words(text):
        vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
    return vector


class ChatMessage(BaseModel):
    """One chat message."""

    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]]
    """Text, or OpenAI content parts (``text`` and ``image_url``; US-5.2 page images)."""


class ChatRequest(BaseModel):
    """The subset of the chat-completions request the fake reads."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage]


class EmbeddingsRequest(BaseModel):
    """The subset of the embeddings request the fake reads."""

    model_config = ConfigDict(extra="allow")

    model: str
    input: list[str]


class FakeModelServer:
    """Loopback server answering like an OpenAI-compatible endpoint.

    Args:
        replies: Canned assistant reply per model id; unknown models get ``DEFAULT_REPLY``.
        port: Port to bind; ``0`` picks a free one.
        health: How ``/v1/models`` answers.
    """

    def __init__(
        self, replies: Mapping[str, str] | None = None, *, port: int = 0, health: Health = "ok"
    ) -> None:
        """Build the app; call ``start()`` (or use as a context manager) to serve it."""
        self.replies: dict[str, str] = dict(replies or {})
        self.responders: dict[str, Callable[[ChatRequest], str]] = {}
        self.requests: list[ChatRequest] = []
        self.embedding_requests: list[EmbeddingsRequest] = []
        self.embed_overrides: dict[str, list[float]] = {}
        self.health = health
        self.app = self._build_app()
        self._server = uvicorn.Server(
            uvicorn.Config(
                self.app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"
            )
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self.port = 0

    @property
    def base_url(self) -> str:
        """OpenAI-style base URL, e.g. ``http://127.0.0.1:54321/v1``."""
        return f"http://127.0.0.1:{self.port}/v1"

    def _build_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/v1/models", response_model=None)
        def models() -> dict[str, Any] | Response:
            if self.health == "error":
                return Response("loading", status_code=503)
            if self.health == "text":
                return Response("not json", media_type="text/plain")
            if self.health == "no-data":
                return {"object": "list"}
            ids = sorted(self.replies) or ["fake-model"]
            return {
                "object": "list",
                "data": [{"id": i, "object": "model", "owned_by": "claimcoach-fake"} for i in ids],
            }

        @app.post("/v1/chat/completions")
        def chat(request: ChatRequest) -> dict[str, Any]:
            self.requests.append(request)
            responder = self.responders.get(request.model)
            fixed = self.replies.get(request.model, DEFAULT_REPLY)
            reply = responder(request) if responder else fixed
            return {
                "id": f"chatcmpl-fake-{len(self.requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }

        @app.post("/v1/embeddings")
        def embeddings(request: EmbeddingsRequest) -> dict[str, Any]:
            self.embedding_requests.append(request)
            return {
                "object": "list",
                "model": request.model,
                "data": [
                    {
                        "object": "embedding",
                        "index": index,
                        "embedding": self.embed_overrides.get(text) or fake_embedding(text),
                    }
                    for index, text in enumerate(request.input)
                ],
            }

        return app

    def start(self, timeout: float = 10.0) -> FakeModelServer:
        """Serve in a background thread and wait until the socket is bound."""
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if time.monotonic() > deadline:
                raise TimeoutError("fake model server did not start")
            time.sleep(0.01)
        self.port = self._server.servers[0].sockets[0].getsockname()[1]
        return self

    def stop(self) -> None:
        """Ask uvicorn to exit and join the thread."""
        self._server.should_exit = True
        self._thread.join(timeout=10)

    def __enter__(self) -> FakeModelServer:
        """Start serving."""
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop serving."""
        self.stop()


def main(argv: Sequence[str] | None = None) -> int:
    """Serve until SIGTERM, like a model server the worker launched."""
    parser = argparse.ArgumentParser(prog="python -m tests.fakes.fake_model_server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--model", default="fake-model")
    parser.add_argument("--health", choices=get_args(Health), default="ok")
    parser.add_argument("--ignore-sigterm", action="store_true")
    parser.add_argument("--reply-file", type=Path, help="assistant reply for --model")
    args = parser.parse_args(argv)
    if args.host != "127.0.0.1":
        parser.error("the fake only binds 127.0.0.1")
    stop = threading.Event()
    if args.ignore_sigterm:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    else:
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    reply = args.reply_file.read_text() if args.reply_file else DEFAULT_REPLY
    server = FakeModelServer({args.model: reply}, port=args.port, health=args.health)
    server.start()
    stop.wait()
    server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
