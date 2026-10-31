"""US-1.2 Worker Sidecar with Per-Launch Token.

Scenarios: worker binds to loopback on the first port of the range; worker writes a per-launch
token in the plugin data dir; requests without the token are rejected. Rules: PRD §7.9, BR-11,
ES-8, BR-14.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from pydantic import ValidationError

from claimcoach.api.models import ERROR_MESSAGES
from claimcoach.worker import __main__ as worker_main
from claimcoach.worker import launcher
from claimcoach.worker.app import create_app, get_health
from claimcoach.worker.config import WorkerConfig, WorkerHandle, default_worker_python
from claimcoach.worker.token import issue_token, read_token
from tests.conftest import PLUGIN_DIR, free_port_in_range, python_for_worker

TOKEN = "test-token"
PHI = "Jane Doe SSN 123-45-6789"


def worker_config(tmp_path: Path, port: int | None = None) -> WorkerConfig:
    return WorkerConfig(
        data_dir=tmp_path / "plugin-data" / "claimcoach",
        port=port or free_port_in_range(),
        python=python_for_worker(),
    )


@pytest.fixture
def running_worker(tmp_path: Path) -> Iterator[tuple[WorkerConfig, WorkerHandle]]:
    config = worker_config(tmp_path)
    handle = launcher.start_worker(config)
    try:
        yield config, handle
    finally:
        launcher.stop_worker(config)


def listening_addresses(pid: int) -> list[str]:
    lsof = shutil.which("lsof")
    if lsof is None:
        pytest.skip("lsof not available")
    result = subprocess.run(
        [lsof, "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-F", "n"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line[1:] for line in result.stdout.splitlines() if line.startswith("n")]


# --- Scenario: Worker binds to loopback on the first port of the range -------------------------


def test_us_1_2_worker_binds_loopback(
    running_worker: tuple[WorkerConfig, WorkerHandle],
) -> None:
    config, handle = running_worker
    assert listening_addresses(handle.pid) == [f"127.0.0.1:{config.port}"]
    assert handle.base_url == f"http://127.0.0.1:{config.port}"


def test_us_1_2_default_bind_is_first_port_of_range(tmp_path: Path) -> None:
    config = WorkerConfig(data_dir=tmp_path)
    assert (config.host, config.port) == ("127.0.0.1", 18200)


@pytest.mark.parametrize(
    "override", [{"host": "0.0.0.0"}, {"port": 18199}, {"port": 18220}, {"extra": True}]
)
def test_us_1_2_config_rejects_non_loopback_or_out_of_range(
    tmp_path: Path, override: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        WorkerConfig.model_validate({"data_dir": tmp_path, **override})


def test_us_1_2_worker_python_follows_models_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELS_HOME", "/Volumes/Models")
    assert default_worker_python() == Path("/Volumes/Models/.venvs/claimcoach/bin/python")
    monkeypatch.delenv("MODELS_HOME")
    assert default_worker_python() == Path.home() / "Models/.venvs/claimcoach/bin/python"


# --- Scenario: Worker writes a per-launch token in the plugin data dir -------------------------


def test_us_1_2_worker_writes_per_launch_token(tmp_path: Path) -> None:
    config = worker_config(tmp_path)
    tokens = []
    for _ in range(2):
        launcher.start_worker(config)
        try:
            assert config.token_path.is_relative_to(config.data_dir)
            assert stat.S_IMODE(config.token_path.stat().st_mode) == 0o600
            assert stat.S_IMODE(config.log_path.stat().st_mode) == 0o600
            tokens.append(read_token(config.token_path))
        finally:
            assert launcher.stop_worker(config) is True
        assert not config.token_path.exists(), "stop removes the token"
    assert None not in tokens
    assert tokens[0] != tokens[1]


def test_us_1_2_issue_token_is_random_and_private(tmp_path: Path) -> None:
    path = tmp_path / "state" / "token"
    first, second = issue_token(path), issue_token(path)
    assert first != second
    assert len(first) >= 43, "32 bytes of entropy, URL-safe base64"
    assert read_token(path) == second
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["token"], "no temp file left behind"


def test_us_1_2_issue_token_replaces_stale_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "token"
    stale = tmp_path / f".token.{os.getpid()}.tmp"
    stale.write_text("stale")
    assert read_token(path) is None
    token = issue_token(path)
    assert read_token(path) == token
    assert not stale.exists()


def test_us_1_2_read_token_treats_empty_file_as_missing(tmp_path: Path) -> None:
    path = tmp_path / "token"
    path.write_text("\n")
    assert read_token(path) is None


def test_us_1_2_read_token_treats_unreadable_file_as_missing(tmp_path: Path) -> None:
    directory = tmp_path / "token-dir"
    directory.mkdir()
    corrupt = tmp_path / "token-bytes"
    corrupt.write_bytes(b"\xff\xfe\x00")
    assert read_token(directory) is None
    assert read_token(corrupt) is None


# --- Scenario: Requests without the token are rejected -----------------------------------------


def worker_client(app: Any) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://worker")


@pytest.mark.parametrize("path", ["/health", "/cases", "/nope"])
@pytest.mark.parametrize("header", [None, "Bearer wrong", f"Basic {TOKEN}", TOKEN])
async def test_us_1_2_requests_without_token_rejected(path: str, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    async with worker_client(create_app(TOKEN)) as client:
        response = await client.get(path, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "ok": False,
        "error": {"code": "unauthorized", "message": ERROR_MESSAGES["unauthorized"]},
    }


async def test_us_1_2_valid_token_reaches_routes() -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with worker_client(create_app(TOKEN)) as client:
        health = await client.get("/health", headers=headers)
        missing = await client.get("/nope", headers=headers)
    assert health.status_code == 200
    assert health.json() == {"ok": True, "status": "ok", "version": "0.1.0"}
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_us_1_2_framework_errors_use_the_envelope() -> None:
    from pydantic import BaseModel  # noqa: PLC0415

    class Body(BaseModel):
        case_id: int

    app = create_app(TOKEN)

    @app.post("/echo")
    def echo(body: Body) -> Body:
        return body

    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with worker_client(app) as client:
        wrong_method = await client.post("/health", headers=headers)
        invalid = await client.post("/echo", headers=headers, json={"case_id": PHI})
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "invalid_request"
    assert invalid.status_code == 422
    assert invalid.json() == {
        "ok": False,
        "error": {"code": "invalid_request", "message": ERROR_MESSAGES["invalid_request"]},
    }
    assert PHI not in invalid.text, "FastAPI's default 422 would echo the input"


async def test_us_1_2_previous_launch_token_rejected(tmp_path: Path) -> None:
    config = worker_config(tmp_path)
    launcher.start_worker(config)
    previous = read_token(config.token_path)
    launcher.stop_worker(config)
    launcher.start_worker(config)
    try:
        current = read_token(config.token_path)
        async with httpx.AsyncClient(base_url=config.base_url, trust_env=False) as client:
            stale = await client.get("/health", headers={"Authorization": f"Bearer {previous}"})
            fresh = await client.get("/health", headers={"Authorization": f"Bearer {current}"})
    finally:
        launcher.stop_worker(config)
    assert previous != current
    assert stale.status_code == 401
    assert fresh.status_code == 200


async def test_us_1_2_unhandled_error_is_generic(caplog: pytest.LogCaptureFixture) -> None:
    def explode() -> Any:
        raise RuntimeError(PHI)

    app = create_app(TOKEN)
    app.dependency_overrides[get_health] = explode
    # raise_app_exceptions=True: the test fails if the exception escapes the app (where Starlette
    # would log its traceback and message to worker.log).
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as client:
        response = await client.get("/health", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert PHI not in response.text
    assert "Traceback" not in response.text
    assert "unhandled RuntimeError on GET /health" in caplog.text
    assert PHI not in caplog.text


def test_us_1_2_worker_hides_api_docs() -> None:
    app = create_app(TOKEN)
    assert (app.docs_url, app.redoc_url, app.openapi_url) == (None, None, None)


# --- python -m claimcoach.worker ---------------------------------------------------------------


def test_us_1_2_serve_issues_token_and_binds_loopback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda _app, **kw: calls.append(kw))
    assert worker_main.main(["--data-dir", str(tmp_path), "--port", "18201"]) == 0
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 18201
    assert read_token(tmp_path / "worker" / "token") is not None


def test_us_1_2_serve_rejects_out_of_range_port(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        worker_main.main(["--data-dir", str(tmp_path), "--port", "8080"])


# --- Launcher ----------------------------------------------------------------------------------


def test_us_1_2_start_is_idempotent(running_worker: tuple[WorkerConfig, WorkerHandle]) -> None:
    config, handle = running_worker
    assert launcher.start_worker(config) == handle
    assert launcher.worker_status(config) == handle


def test_us_1_2_stop_worker_started_by_another_process(tmp_path: Path) -> None:
    """``make worker-start`` then ``make worker-stop`` run in different processes."""
    config = worker_config(tmp_path)
    env = {**os.environ, "PYTHONPATH": str(PLUGIN_DIR)}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "claimcoach.worker.launcher",
            "start",
            "--data-dir",
            str(config.data_dir),
            "--port",
            str(config.port),
            "--python",
            sys.executable,
        ],
        env=env,
        capture_output=True,
        check=True,
        timeout=60,
    )
    handle = launcher.worker_status(config)
    assert handle is not None
    assert handle.pid not in launcher._SPAWNED
    assert launcher.stop_worker(config) is True
    assert launcher.worker_status(config) is None


def test_us_1_2_health_probe_handles_nothing_listening(tmp_path: Path) -> None:
    # Readiness polling hits this before uvicorn binds; covered here so it is not timing-dependent.
    assert launcher._healthy(worker_config(tmp_path), "token") is False


def test_us_1_2_status_without_worker(tmp_path: Path) -> None:
    config = worker_config(tmp_path)
    assert launcher.worker_status(config) is None
    assert launcher.stop_worker(config) is False


def test_us_1_2_status_clears_stale_pid_file(tmp_path: Path) -> None:
    config = worker_config(tmp_path)
    config.state_dir.mkdir(parents=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    stale = WorkerHandle(
        pid=dead.pid,
        base_url=config.base_url,
        token_path=config.token_path,
        started_at=datetime.now(UTC),
    )
    config.pid_path.write_text(stale.model_dump_json())
    assert launcher.worker_status(config) is None
    assert not config.pid_path.exists()


def test_us_1_2_status_clears_corrupt_pid_file(tmp_path: Path) -> None:
    config = worker_config(tmp_path)
    config.state_dir.mkdir(parents=True)
    config.pid_path.write_text("{not json")
    assert launcher.worker_status(config) is None
    assert not config.pid_path.exists()


def test_us_1_2_start_reports_crashing_worker(tmp_path: Path) -> None:
    config = worker_config(tmp_path).model_copy(update={"python": Path("/usr/bin/false")})
    with pytest.raises(launcher.WorkerStartError, match="exited with code 1"):
        launcher.start_worker(config)
    assert launcher.worker_status(config) is None


def test_us_1_2_start_times_out_and_stops_process(tmp_path: Path) -> None:
    config = worker_config(tmp_path)
    with pytest.raises(launcher.WorkerStartError, match="not healthy within"):
        launcher.start_worker(config, ready_timeout=0.0)
    assert launcher.worker_status(config) is None
    assert not config.token_path.exists(), "no token left behind for a dead worker"


def test_us_1_2_start_kills_worker_that_ignores_sigterm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stubborn = tmp_path / "stubborn-python"
    trapped = tmp_path / "trap-installed"
    stubborn.write_text(f"#!/bin/sh\ntrap '' TERM\n: > '{trapped}'\nwhile :; do sleep 1; done\n")
    stubborn.chmod(0o700)
    config = worker_config(tmp_path).model_copy(update={"python": stubborn})
    monkeypatch.setattr(launcher, "TERM_GRACE", 0.2)
    with pytest.raises(launcher.WorkerStartError, match="not healthy within"):
        launcher.start_worker(config, ready_timeout=1.5)
    assert trapped.exists(), "SIGTERM was sent only after the stub started ignoring it"
    assert launcher.worker_status(config) is None


def test_us_1_2_stop_escalates_to_sigkill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = worker_config(tmp_path)
    config.state_dir.mkdir(parents=True)
    stubborn = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, sys, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print('ready', flush=True)\n"
            "time.sleep(60)\n",
        ],
        stdout=subprocess.PIPE,
    )
    assert stubborn.stdout is not None
    assert stubborn.stdout.readline().strip() == b"ready"
    handle = WorkerHandle(
        pid=stubborn.pid,
        base_url=config.base_url,
        token_path=config.token_path,
        started_at=datetime.now(UTC),
    )
    config.pid_path.write_text(handle.model_dump_json())
    # Register it as launcher-spawned so stop_worker reaps it like a real worker.
    monkeypatch.setitem(launcher._SPAWNED, stubborn.pid, stubborn)
    assert launcher.stop_worker(config, timeout=0.2) is True
    assert stubborn.returncode == -signal.SIGKILL
    stubborn.stdout.close()


@pytest.mark.parametrize("foreign", ["sleep", "pid1"])
def test_us_1_2_status_never_adopts_an_unrelated_process(tmp_path: Path, foreign: str) -> None:
    """A reused PID in a stale worker.json must not count as running or be signalled."""
    config = worker_config(tmp_path)
    config.state_dir.mkdir(parents=True)
    other = subprocess.Popen(["/bin/sleep", "30"]) if foreign == "sleep" else None
    try:
        handle = WorkerHandle(
            pid=other.pid if other else 1,
            base_url=config.base_url,
            token_path=config.token_path,
            started_at=datetime.now(UTC),
        )
        config.pid_path.write_text(handle.model_dump_json())
        assert launcher.worker_status(config) is None
        assert not config.pid_path.exists()
        config.pid_path.write_text(handle.model_dump_json())
        assert launcher.stop_worker(config) is False
        if other:
            assert other.poll() is None, "stop_worker must not signal an unrelated process"
    finally:
        if other:
            other.kill()
            other.wait()


def test_us_1_2_launcher_cli_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("MODELS_HOME", str(tmp_path / "models"))
    port = str(free_port_in_range())
    args = ["--port", port, "--python", sys.executable]

    assert launcher.main(["status", *args]) == 1
    assert capsys.readouterr().out.strip() == "not running"

    assert launcher.main(["start", *args]) == 0
    started = WorkerHandle.model_validate_json(capsys.readouterr().out)
    assert started.token_path == tmp_path / "hermes/plugin-data/claimcoach/worker/token"

    assert launcher.main(["status", *args]) == 0
    assert WorkerHandle.model_validate_json(capsys.readouterr().out) == started

    assert launcher.main(["stop", *args]) == 0
    assert capsys.readouterr().out.strip() == "stopped"
    assert launcher.main(["stop", *args]) == 0
    assert capsys.readouterr().out.strip() == "not running"

    # Default interpreter comes from MODELS_HOME, which has no worker venv here.
    assert launcher.main(["start", "--port", port]) == 1
    out = capsys.readouterr().out
    assert "models/.venvs/claimcoach/bin/python not found; run make worker-venv" in out


def test_us_1_2_launcher_runs_as_module(tmp_path: Path) -> None:
    env = {**os.environ, "HERMES_HOME": str(tmp_path), "PYTHONPATH": str(PLUGIN_DIR)}
    result = subprocess.run(
        [sys.executable, "-m", "claimcoach.worker.launcher", "status"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout.strip() == "not running"


def test_us_1_2_handle_round_trips_as_json(tmp_path: Path) -> None:
    handle = WorkerHandle(
        pid=123,
        base_url="http://127.0.0.1:18200",
        token_path=tmp_path / "token",
        started_at=datetime(2026, 10, 30, tzinfo=UTC),
    )
    assert WorkerHandle.model_validate(json.loads(handle.model_dump_json())) == handle
