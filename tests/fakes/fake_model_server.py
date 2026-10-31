"""Fake OpenAI-compatible model server for offline tests.

Implements: US-1.4 (``/v1/models`` and ``/v1/chat/completions`` with canned responses). Rules:
ES-4 (offline tests use a fake OpenAI-compatible server; real-model tests are marked ``models``).

It runs uvicorn on ``127.0.0.1`` with an ephemeral port in a daemon thread, so code under test
talks to it over a real loopback socket exactly as it would talk to ``mlx_lm.server``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

__all__ = ["DEFAULT_REPLY", "ChatMessage", "ChatRequest", "FakeModelServer"]

DEFAULT_REPLY = '{"ok": true}'


class ChatMessage(BaseModel):
    """One chat message."""

    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    """The subset of the chat-completions request the fake reads."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage]


class FakeModelServer:
    """Loopback server answering like an OpenAI-compatible endpoint.

    Args:
        replies: Canned assistant reply per model id; unknown models get ``DEFAULT_REPLY``.
    """

    def __init__(self, replies: Mapping[str, str] | None = None) -> None:
        """Build the app; call ``start()`` (or use as a context manager) to serve it."""
        self.replies: dict[str, str] = dict(replies or {})
        self.requests: list[ChatRequest] = []
        self.app = self._build_app()
        self._server = uvicorn.Server(
            uvicorn.Config(self.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self.port = 0

    @property
    def base_url(self) -> str:
        """OpenAI-style base URL, e.g. ``http://127.0.0.1:54321/v1``."""
        return f"http://127.0.0.1:{self.port}/v1"

    def _build_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/v1/models")
        def models() -> dict[str, Any]:
            ids = sorted(self.replies) or ["fake-model"]
            return {
                "object": "list",
                "data": [{"id": i, "object": "model", "owned_by": "claimcoach-fake"} for i in ids],
            }

        @app.post("/v1/chat/completions")
        def chat(request: ChatRequest) -> dict[str, Any]:
            self.requests.append(request)
            reply = self.replies.get(request.model, DEFAULT_REPLY)
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
