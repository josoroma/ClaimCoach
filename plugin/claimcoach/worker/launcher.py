"""Start, stop, and inspect the worker process.

Implements: US-1.2 (``WorkerConfig``/``WorkerHandle``; the launcher never reuses a previous
launch's token). Rules: PRD §7.9 worker decision, BR-11. Operated through
``docs/runbooks/worker-start-stop-health.md``.

Usage::

    python -m claimcoach.worker.launcher start|stop|status [--data-dir DIR] [--port N] [--python PY]
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx
from pydantic import ValidationError

from claimcoach.paths import app_data_dir
from claimcoach.settings import PORT_RANGE
from claimcoach.worker.config import WorkerConfig, WorkerHandle, default_worker_python
from claimcoach.worker.token import read_token

__all__ = [
    "WorkerStartError",
    "main",
    "start_worker",
    "stop_worker",
    "worker_status",
]

APP_ROOT: Final = Path(__file__).resolve().parents[2]
"""``plugin/``: put on the worker's ``PYTHONPATH`` so it runs the code next to this file."""


TERM_GRACE: Final = 5.0
"""Seconds a worker that failed to start gets to exit after SIGTERM before SIGKILL."""

_PS: Final = "/bin/ps"

_SPAWNED: dict[int, subprocess.Popen[bytes]] = {}
"""Workers started by this process. Holding the ``Popen`` lets us reap them (an exited child stays
a zombie) and keeps ``Popen.__del__`` from warning that a detached worker is still running."""


class WorkerStartError(RuntimeError):
    """The worker did not become healthy."""


def _is_worker(pid: int) -> bool:
    """Return whether ``pid`` is a live ClaimCoach worker.

    A PID file can outlive its process (crash, reboot), and the OS may reuse the PID for an
    unrelated program. Checking the command line keeps ``status`` honest and ``stop`` from
    signalling a process ClaimCoach does not own.
    """
    process = _SPAWNED.get(pid)
    if process is not None:
        return process.poll() is None
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [_PS, "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    return " -m claimcoach.worker " in f" {result.stdout.strip()} "


def _healthy(config: WorkerConfig, token: str) -> bool:
    try:
        response = httpx.get(
            f"{config.base_url}/health",
            headers={"Authorization": f"Bearer {token}"},
            timeout=1.0,
            trust_env=False,  # never route the token through an environment proxy
        )
    except httpx.HTTPError:
        return False
    return response.status_code == httpx.codes.OK


def worker_status(config: WorkerConfig) -> WorkerHandle | None:
    """Return the running worker's handle, clearing a stale PID file.

    Args:
        config: Worker configuration.

    Returns:
        The handle, or ``None`` when no worker is running.
    """
    try:
        handle = WorkerHandle.model_validate_json(config.pid_path.read_bytes())
    except FileNotFoundError:
        return None
    except ValidationError:
        config.pid_path.unlink()
        return None
    if not _is_worker(handle.pid):
        config.pid_path.unlink()
        return None
    return handle


def _wait_ready(process: subprocess.Popen[bytes], config: WorkerConfig, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            raise WorkerStartError(f"worker exited with code {code}; see {config.log_path}")
        token = read_token(config.token_path)
        if token is not None and _healthy(config, token):
            return
        time.sleep(0.05)
    raise WorkerStartError(f"worker not healthy within {timeout:g}s; see {config.log_path}")


def start_worker(config: WorkerConfig, *, ready_timeout: float = 15.0) -> WorkerHandle:
    """Start the worker and wait until it answers ``/health`` with its new token.

    Starting is idempotent: a running worker's handle is returned as is.

    Args:
        config: Worker configuration.
        ready_timeout: Seconds to wait for the worker to become healthy.

    Returns:
        Handle of the running worker.

    Raises:
        WorkerStartError: The process exited or did not become healthy in time; it is stopped.
    """
    running = worker_status(config)
    if running is not None:
        return running
    if not config.python.is_file():
        raise WorkerStartError(
            f"worker interpreter {config.python} not found; run make worker-venv"
        )
    config.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Drop the previous launch's token so readiness can only succeed with the new one.
    config.token_path.unlink(missing_ok=True)
    env = {**os.environ, "PYTHONPATH": str(APP_ROOT)}
    log_fd = os.open(config.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.fchmod(log_fd, 0o600)  # an older log may have been created with a wider mode
    with os.fdopen(log_fd, "ab") as log:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [
                str(config.python),
                "-m",
                "claimcoach.worker",
                "--data-dir",
                str(config.data_dir),
                "--port",
                str(config.port),
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        _wait_ready(process, config, ready_timeout)
    except WorkerStartError:
        process.terminate()
        try:
            process.wait(timeout=TERM_GRACE)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        # The token was issued before the bind; don't leave one behind for a dead worker.
        config.token_path.unlink(missing_ok=True)
        raise
    _SPAWNED[process.pid] = process
    handle = WorkerHandle(
        pid=process.pid,
        base_url=config.base_url,
        token_path=config.token_path,
        started_at=datetime.now(UTC),
    )
    config.pid_path.write_text(handle.model_dump_json(), encoding="utf-8")
    return handle


def _wait_gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while _is_worker(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def stop_worker(config: WorkerConfig, *, timeout: float = 10.0) -> bool:
    """Stop the running worker with SIGTERM and remove its PID and token files.

    Args:
        config: Worker configuration.
        timeout: Seconds to wait before escalating to SIGKILL.

    Returns:
        ``True`` if a worker was running.
    """
    handle = worker_status(config)
    if handle is None:
        return False
    with suppress(ProcessLookupError):  # it may exit between the check and the signal
        os.kill(handle.pid, signal.SIGTERM)
    if not _wait_gone(handle.pid, timeout):
        with suppress(ProcessLookupError):
            os.kill(handle.pid, signal.SIGKILL)
        _wait_gone(handle.pid, TERM_GRACE)
    _SPAWNED.pop(handle.pid, None)
    config.pid_path.unlink(missing_ok=True)
    config.token_path.unlink(missing_ok=True)
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point used by the Makefile and the runbook.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` on success; ``1`` when ``status`` finds no worker or ``start`` fails.
    """
    parser = argparse.ArgumentParser(prog="python -m claimcoach.worker.launcher")
    parser.add_argument("command", choices=("start", "stop", "status"))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--port", type=int, default=PORT_RANGE.start)
    parser.add_argument("--python", type=Path, default=None)
    args = parser.parse_args(argv)
    config = WorkerConfig(
        data_dir=args.data_dir or app_data_dir(),
        port=args.port,
        python=args.python or default_worker_python(),
    )
    if args.command == "start":
        try:
            handle = start_worker(config)
        except WorkerStartError as exc:
            print(f"error: {exc}")  # noqa: T201
            return 1
        print(handle.model_dump_json())  # noqa: T201
        return 0
    if args.command == "stop":
        stopped = stop_worker(config)
        print("stopped" if stopped else "not running")  # noqa: T201
        return 0
    handle_or_none = worker_status(config)
    if handle_or_none is None:
        print("not running")  # noqa: T201
        return 1
    print(handle_or_none.model_dump_json())  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
