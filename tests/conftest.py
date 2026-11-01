"""Shared pytest fixtures: socket guard, fake model server, repo paths, worker helpers.

Implements: US-1.4 (offline harness). Rules: ES-4, NFR-11.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from claimcoach import logs
from claimcoach.egress import EGRESS_AUDIT
from tests.fakes import socket_guard
from tests.fakes.fake_model_server import FakeModelServer

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "plugin"
HERMES_ROOT = Path(os.environ.get("CLAIMCOACH_HERMES_ROOT", Path.home() / ".hermes/hermes-agent"))
HERMES_PYTHON = HERMES_ROOT / "venv" / "bin" / "python"
HERMES_BIN = shutil.which("hermes")


@pytest.fixture(autouse=True)
def _socket_guard(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that reaches beyond loopback, unless it is a real-model test (ES-4)."""
    if request.node.get_closest_marker("allow_network"):
        if not request.node.get_closest_marker("models"):
            pytest.fail("allow_network is only valid on tests also marked models")
        return
    socket_guard.install(monkeypatch)


@pytest.fixture(autouse=True)
def _idle_egress_audit() -> Iterator[None]:
    """Stop the socket audit hook's records after each test (the hook itself cannot be removed;
    the worker entry point and the US-12.4 check start it in this process)."""
    yield
    EGRESS_AUDIT.stop()


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Undo ``configure_logging`` (worker entry points replace the root handlers)."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    hooks = (sys.excepthook, threading.excepthook, logs._process_job_id)
    yield
    sys.excepthook, threading.excepthook, logs._process_job_id = hooks
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    for handler in handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(level)
    logging.captureWarnings(capture=False)


@pytest.fixture(scope="session")
def fake_model_server() -> Iterator[FakeModelServer]:
    """A running fake OpenAI-compatible server shared by the session."""
    with FakeModelServer({"qwen3-8b": '{"label": "CO-197"}'}) as server:
        yield server


@pytest.fixture(scope="module")
def corpus_server() -> Iterator[FakeModelServer]:
    """A fake embedding server for one corpus test module (US-4.x)."""
    with FakeModelServer() as server:
        yield server


@pytest.fixture
def hermes_python() -> Path:
    """The Hermes gateway interpreter; skips when Hermes Agent is not installed."""
    if not HERMES_PYTHON.exists():
        pytest.skip(f"Hermes Agent venv not found at {HERMES_PYTHON}")
    return HERMES_PYTHON


def free_port_in_range(preferred: int = 18200, stop: int = 18220) -> int:
    """Return ``preferred`` when it is free, else the next free port below ``stop``."""
    for port in range(preferred, stop):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    pytest.skip(f"no free port in {preferred}-{stop - 1}")


def python_for_worker() -> Path:
    """The interpreter tests launch the worker with: this venv, which has the worker deps."""
    return Path(sys.executable)
