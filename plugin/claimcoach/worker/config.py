"""Typed worker configuration and the handle of a running worker.

Implements: US-1.2 (``WorkerConfig``, ``WorkerHandle``). Rules: ES-1, BR-11 (ports 18200-18219,
weights under ``MODELS_HOME``), PRD §7.9 (venv ``~/Models/.venvs/claimcoach``, ``127.0.0.1:18200``).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from claimcoach.settings import PORT_RANGE

__all__ = ["LOOPBACK", "WorkerConfig", "WorkerHandle", "default_worker_python"]

LOOPBACK: Literal["127.0.0.1"] = "127.0.0.1"


def default_worker_python() -> Path:
    """Return the worker venv interpreter: ``$MODELS_HOME/.venvs/claimcoach/bin/python``."""
    models_home = Path(os.environ.get("MODELS_HOME") or "~/Models").expanduser()
    return models_home / ".venvs" / "claimcoach" / "bin" / "python"


class WorkerConfig(BaseModel):
    """How to run the worker.

    ``host`` is a literal so a configuration can never bind a non-loopback interface.

    Attributes:
        host: Bind address; always ``127.0.0.1``.
        port: Bind port inside ClaimCoach's range.
        data_dir: ClaimCoach plugin data dir; the worker keeps its token and PID file here.
        python: Interpreter of the worker venv.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: Literal["127.0.0.1"] = LOOPBACK
    port: int = Field(default=PORT_RANGE.start, ge=PORT_RANGE.start, le=PORT_RANGE.stop - 1)
    data_dir: Path
    python: Path = Field(default_factory=default_worker_python)

    @property
    def base_url(self) -> str:
        """Root URL of the worker's HTTP API."""
        return f"http://{self.host}:{self.port}"

    @property
    def state_dir(self) -> Path:
        """Directory that holds the worker's token, PID file, and log."""
        return self.data_dir / "worker"

    @property
    def token_path(self) -> Path:
        """Per-launch bearer token file (mode 0600)."""
        return self.state_dir / "token"

    @property
    def pid_path(self) -> Path:
        """JSON-serialized ``WorkerHandle`` of the running worker."""
        return self.state_dir / "worker.json"

    @property
    def log_path(self) -> Path:
        """Worker stdout/stderr."""
        return self.state_dir / "worker.log"


class WorkerHandle(BaseModel):
    """A started worker process.

    Attributes:
        pid: Process ID.
        base_url: Root URL of its HTTP API.
        token_path: Where its bearer token is stored.
        started_at: When the launcher saw it become healthy.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    pid: int = Field(gt=0)
    base_url: str
    token_path: Path
    started_at: datetime
