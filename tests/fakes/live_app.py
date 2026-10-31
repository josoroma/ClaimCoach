"""Serve an ASGI app on a real loopback port in a background thread.

Implements: US-3.2 and US-3.4 test harness. The guard calls the worker from its own thread and
event loop, as it does inside the Hermes gateway, so the worker must run on a real socket rather
than an in-process ASGI transport.
"""

from __future__ import annotations

import threading
import time
from types import TracebackType

import uvicorn
from fastapi import FastAPI

__all__ = ["LiveApp"]


class LiveApp:
    """``with LiveApp(app) as live:`` serves ``app`` on ``live.base_url`` until the block ends.

    Args:
        app: The ASGI app.
        port: Port on 127.0.0.1; ``0`` picks a free one.
    """

    def __init__(self, app: FastAPI, port: int = 0) -> None:
        """Configure uvicorn without touching the logging configuration."""
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, access_log=False)
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self.port = 0

    @property
    def base_url(self) -> str:
        """Root URL, e.g. ``http://127.0.0.1:18210``."""
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> LiveApp:
        """Start serving and wait until the socket is bound."""
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            if time.monotonic() > deadline:
                raise TimeoutError("app did not start")
            time.sleep(0.01)
        self.port = self._server.servers[0].sockets[0].getsockname()[1]
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop serving."""
        self._server.should_exit = True
        self._thread.join(timeout=10)
