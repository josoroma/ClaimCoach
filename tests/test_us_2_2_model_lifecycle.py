"""US-2.2 Lazy Start, Health Check, and Idle Unload.

Scenarios: a role's server starts on first use; an unhealthy server is not used; idle servers are
unloaded. The servers are real processes (the fake OpenAI-compatible server) on loopback ports
inside 18201-18219. Rules: PRD §8, BR-11, BR-14, ES-8.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from claimcoach.api.models import ERROR_MESSAGES, ErrorEnvelope
from claimcoach.models import manager as manager_module
from claimcoach.models.manager import (
    ModelBusyError,
    ModelManager,
    ModelUnavailableError,
    _healthy,
)
from claimcoach.models.registry import DEFAULT_REGISTRY, REGISTRY_FILE, ModelRegistry, models_home
from claimcoach.models.types import ModelRole, ModelsStatusResponse, ModelState, ModelStatus
from claimcoach.worker import __main__ as worker_main
from claimcoach.worker import launcher
from claimcoach.worker.app import create_app
from tests.conftest import REPO_ROOT
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.model_env import ModelEnv, build_model_env, fake_server_command

TOKEN = "model-test-token"
CLASSIFICATION = ModelRole.CLASSIFICATION
UNLOADED = ModelState.UNLOADED
PHI_PATH = "/cases/Jane-Doe-MRN-0042.pdf"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeClock:
    """Monotonic clock the test advances by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def _fake_server_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model servers run ``python -m tests.fakes.fake_model_server`` from the repo root."""
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))


@asynccontextmanager
async def managed(env: ModelEnv, **kwargs: Any) -> AsyncIterator[ModelManager]:
    manager = env.manager(**kwargs)
    try:
        yield manager
    finally:
        await manager.shutdown()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    result = subprocess.run(
        ["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    return "Z" not in result.stdout  # a zombie has exited


def port_open(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def status_of(manager: ModelManager, role: ModelRole) -> ModelStatus:
    return manager.role_status(role)


async def chat(base_url: str) -> httpx.Response:
    async with httpx.AsyncClient(trust_env=False) as client:
        return await client.post(
            f"{base_url}/chat/completions",
            json={"model": "fake-model", "messages": [{"role": "user", "content": "CO-197"}]},
        )


# --- Scenario: A role's server starts on first use ---------------------------------------------


async def test_us_2_2_server_starts_on_first_use(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    port = env.port(CLASSIFICATION)
    async with managed(env) as manager:
        assert not port_open(port)
        assert {m.state for m in manager.status().models} == {ModelState.UNLOADED}

        async with manager.use(CLASSIFICATION) as endpoint:
            assert endpoint.base_url == f"http://127.0.0.1:{port}/v1"
            status = status_of(manager, CLASSIFICATION)
            assert status.state is ModelState.READY
            assert status.pid is not None
            assert alive(status.pid)
            response = await chat(endpoint.base_url)
            assert response.status_code == 200
            assert response.json()["choices"][0]["message"]["content"] == '{"ok": true}'

        pid = status.pid
        command = subprocess.run(
            ["/bin/ps", "-o", "command=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        assert f"--host 127.0.0.1 --port {port}" in command
        assert status_of(manager, ModelRole.EXPLANATION).state is ModelState.UNLOADED
    assert not alive(pid)
    assert not port_open(port)


async def test_us_2_2_shared_server_started_once(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    async with managed(env) as manager:
        async with manager.use(ModelRole.PHI_DETECTION):
            first = status_of(manager, ModelRole.PHI_DETECTION).pid
        async with manager.use(CLASSIFICATION):
            second = status_of(manager, CLASSIFICATION).pid
        assert first == second
        assert status_of(manager, ModelRole.PHI_DETECTION).state is ModelState.READY


async def test_us_2_2_concurrent_first_use_starts_one_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawned: list[tuple[str, ...]] = []
    real_exec = asyncio.create_subprocess_exec

    async def counting_exec(*argv: str, **kwargs: Any) -> asyncio.subprocess.Process:
        spawned.append(argv)
        return await real_exec(*argv, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", counting_exec)
    env = build_model_env(tmp_path)
    async with managed(env) as manager:

        async def one_request() -> int:
            async with manager.use(CLASSIFICATION):
                pid = status_of(manager, CLASSIFICATION).pid
                assert pid is not None
                return pid

        pids = await asyncio.gather(*(one_request() for _ in range(3)))
    assert len(set(pids)) == 1
    assert len(spawned) == 1


async def test_us_2_2_server_runs_offline_with_private_log(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    async with managed(env) as manager:
        async with manager.use(CLASSIFICATION):
            pid = status_of(manager, CLASSIFICATION).pid
            assert pid is not None
            environ = subprocess.run(
                ["/bin/ps", "eww", "-o", "command=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            records = json.loads(manager.records_path.read_text())
        log = env.state_dir / f"{env.port(CLASSIFICATION)}.log"
        assert stat.S_IMODE(log.stat().st_mode) == 0o600
        assert stat.S_IMODE(manager.records_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(env.state_dir.stat().st_mode) == 0o700
    assert "HF_HUB_OFFLINE=1" in environ
    model = env.registry.roles[CLASSIFICATION].model_path(env.home)
    port = env.port(CLASSIFICATION)
    assert records == {str(port): {"pid": pid, "markers": [str(model), f"--port {port}"]}}
    assert json.loads(manager.records_path.read_text()) == {}


async def test_us_2_2_missing_weights_never_spawn(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    (env.registry.roles[CLASSIFICATION].model_path(env.home) / "model.safetensors").unlink()
    async with managed(env) as manager:
        with pytest.raises(ModelUnavailableError):
            async with manager.use(CLASSIFICATION):
                pytest.fail("a role without weights must not be served")
        assert status_of(manager, CLASSIFICATION).state is ModelState.UNLOADED
        assert status_of(manager, CLASSIFICATION).weights == "missing"
    assert not manager.records_path.exists()


# --- Scenario: An unhealthy server is not used -------------------------------------------------


def unhealthy_env(tmp_path: Path, *extra: str, timeout: float = 1.5) -> ModelEnv:
    spec = {"command": fake_server_command(*extra), "startup_timeout_s": timeout}
    return build_model_env(tmp_path, roles={"phi_detection": spec, "classification": spec})


async def test_us_2_2_unhealthy_server_not_used(tmp_path: Path) -> None:
    env = unhealthy_env(tmp_path, "--health", "error")
    async with managed(env) as manager:
        with pytest.raises(ModelUnavailableError):
            async with manager.use(CLASSIFICATION):
                pytest.fail("an unhealthy server must not be handed out")
        status = status_of(manager, CLASSIFICATION)
        assert status.state is ModelState.UNHEALTHY
        assert status.pid is None
        assert not port_open(env.port(CLASSIFICATION))

        app = create_app(TOKEN, manager)
        async with worker_client(app) as client:
            response = await client.post("/models/classification/load")
            body = (await client.get("/models/status")).json()
    assert response.status_code == 503
    envelope = ErrorEnvelope.model_validate_json(response.content)
    assert envelope.error.code == "model_unavailable"
    assert envelope.error.message == ERROR_MESSAGES["model_unavailable"]
    states = {m["role"]: m["state"] for m in body["models"]}
    assert states["classification"] == "unhealthy"


async def test_us_2_2_waiters_share_a_failed_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawned: list[tuple[str, ...]] = []
    real_exec = asyncio.create_subprocess_exec

    async def counting_exec(*argv: str, **kwargs: Any) -> asyncio.subprocess.Process:
        spawned.append(argv)
        return await real_exec(*argv, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", counting_exec)
    env = unhealthy_env(tmp_path, "--health", "no-data")
    async with managed(env) as manager:

        async def one_request() -> None:
            async with manager.use(CLASSIFICATION):
                pytest.fail("unreachable")

        results = await asyncio.gather(*(one_request() for _ in range(3)), return_exceptions=True)
    assert all(isinstance(r, ModelUnavailableError) for r in results)
    assert len(spawned) == 1  # one bad server costs one timeout, not three


async def test_us_2_2_ready_server_failing_health_is_replaced(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    async with managed(env) as manager:
        async with manager.use(CLASSIFICATION):
            first = status_of(manager, CLASSIFICATION).pid
        assert first is not None
        os.kill(first, signal.SIGKILL)  # the server dies between requests
        with pytest.raises(ModelUnavailableError):
            async with manager.use(CLASSIFICATION):
                pytest.fail("a dead server must not be handed out")
        assert status_of(manager, CLASSIFICATION).state is ModelState.UNHEALTHY

        async with manager.use(CLASSIFICATION):  # the next request starts a fresh server
            second = status_of(manager, CLASSIFICATION).pid
        assert second not in (None, first)


async def test_us_2_2_port_taken_by_another_process(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    port = env.port(CLASSIFICATION)
    with FakeModelServer(port=port):  # healthy, but not ClaimCoach's: never adopted
        async with managed(env) as manager:
            with pytest.raises(ModelUnavailableError):
                async with manager.use(CLASSIFICATION):
                    pytest.fail("a foreign server must not be adopted")
            assert status_of(manager, CLASSIFICATION).state is ModelState.UNHEALTHY
        assert port_open(port)  # the other process was left alone


@pytest.mark.parametrize(
    "command",
    [
        [sys.executable, "-c", "raise SystemExit(3)", "{host}", "{port}"],
        ["/nonexistent/bin/mlx_lm.server", "--host", "{host}", "--port", "{port}"],
    ],
    ids=["exits-during-start", "not-executable"],
)
async def test_us_2_2_server_that_cannot_start(tmp_path: Path, command: list[str]) -> None:
    spec = {"command": command}
    env = build_model_env(tmp_path, roles={"phi_detection": spec, "classification": spec})
    async with managed(env) as manager:
        with pytest.raises(ModelUnavailableError):
            async with manager.use(CLASSIFICATION):
                pytest.fail("unreachable")
        assert status_of(manager, CLASSIFICATION).state is ModelState.UNHEALTHY


@pytest.mark.parametrize("health", ["ok", "error", "text", "no-data"])
async def test_us_2_2_health_requires_an_openai_model_list(health: str) -> None:
    with FakeModelServer(health=health) as server:  # type: ignore[arg-type]
        assert await _healthy(server.port) is (health == "ok")
    assert await _healthy(server.port) is False  # nothing listening


async def test_us_2_2_stop_escalates_to_sigkill(tmp_path: Path) -> None:
    env = build_model_env(
        tmp_path,
        roles={"explanation": {"command": fake_server_command("--ignore-sigterm")}},
    )
    async with managed(env, term_grace=0.5) as manager:
        async with manager.use(ModelRole.EXPLANATION):
            pid = status_of(manager, ModelRole.EXPLANATION).pid
        assert pid is not None
        await manager.unload(ModelRole.EXPLANATION)
        assert not alive(pid)
        assert status_of(manager, ModelRole.EXPLANATION).state is ModelState.UNLOADED


# --- Scenario: Idle servers are unloaded -------------------------------------------------------


async def test_us_2_2_idle_servers_unloaded(tmp_path: Path) -> None:
    env = build_model_env(tmp_path, idle_timeout_s=600)
    clock = FakeClock()
    async with managed(env, clock=clock) as manager:
        async with manager.use(CLASSIFICATION):
            pid = status_of(manager, CLASSIFICATION).pid
        assert pid is not None
        clock.now += 599
        assert await manager.sweep_idle() == []
        assert status_of(manager, CLASSIFICATION).state is ModelState.READY

        clock.now += 2
        assert await manager.sweep_idle() == [env.port(CLASSIFICATION)]
        status = status_of(manager, CLASSIFICATION)
        assert status.state is ModelState.UNLOADED
        assert status.pid is None
        assert not alive(pid)


async def test_us_2_2_busy_servers_kept(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    clock = FakeClock()
    async with managed(env, clock=clock) as manager:
        async with manager.use(CLASSIFICATION):
            clock.now += 10_000
            assert await manager.sweep_idle() == []
            assert status_of(manager, CLASSIFICATION).state is ModelState.READY
            with pytest.raises(ModelBusyError):
                await manager.unload(CLASSIFICATION)
        status = await manager.unload(CLASSIFICATION)
        assert status.state is ModelState.UNLOADED
        assert (await manager.unload(CLASSIFICATION)).state is ModelState.UNLOADED


async def test_us_2_2_sweep_rechecks_before_stopping(tmp_path: Path) -> None:
    """A request that lands between the sweep's scan and its stop keeps the server."""
    env = build_model_env(tmp_path)
    clock = FakeClock()
    async with managed(env, clock=clock) as manager:
        async with manager.use(CLASSIFICATION):
            pass
        server = manager._by_role[CLASSIFICATION]
        cutoff = clock.now
        clock.now += 1
        async with manager.use(CLASSIFICATION):
            assert not await manager._stop(server, UNLOADED, only_if_idle=True)  # pinned
        assert not await manager._stop(server, UNLOADED, only_if_idle=True, used_before=cutoff)
        assert status_of(manager, CLASSIFICATION).state is ModelState.READY


async def test_us_2_2_request_never_pins_a_server_being_stopped(tmp_path: Path) -> None:
    """Review finding: the idle check and the switch to ``stopping`` are one critical section.

    An idle-stop and a request are queued on the lock in that order; the request must wait for
    the stop and get a fresh server, never an endpoint whose process is being killed.
    """
    env = build_model_env(tmp_path)
    async with managed(env) as manager:
        async with manager.use(CLASSIFICATION):
            first = status_of(manager, CLASSIFICATION).pid
        server = manager._by_role[CLASSIFICATION]
        seen: list[int | None] = []

        async def request() -> None:
            async with manager.use(CLASSIFICATION) as endpoint:
                seen.append(status_of(manager, CLASSIFICATION).pid)
                assert (await chat(endpoint.base_url)).status_code == 200

        async with manager._cond:  # both tasks queue on the lock, stop first
            stop = asyncio.create_task(manager._stop(server, UNLOADED, only_if_idle=True))
            await asyncio.sleep(0)
            req = asyncio.create_task(request())
            await asyncio.sleep(0)
        assert await stop is True
        await req
    assert seen[0] not in (None, first)


async def test_us_2_2_cancelled_start_leaves_nothing_behind(tmp_path: Path) -> None:
    """Review finding (high): a caller cancelled mid-start must not wedge the role or the guard."""
    env = build_model_env(tmp_path)
    async with managed(env) as manager:

        async def explain() -> None:
            async with manager.use(ModelRole.EXPLANATION):
                pytest.fail("cancelled before the server was healthy")

        task = asyncio.create_task(explain())
        while status_of(manager, ModelRole.EXPLANATION).pid is None:
            await asyncio.sleep(0.005)
        pid = status_of(manager, ModelRole.EXPLANATION).pid
        assert status_of(manager, ModelRole.EXPLANATION).state is ModelState.STARTING
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        status = status_of(manager, ModelRole.EXPLANATION)
        assert status.state is ModelState.UNLOADED
        assert manager._by_role[ModelRole.EXPLANATION].refcount == 0
        assert pid is not None
        assert not alive(pid)
        # Neither the role nor the memory guard is wedged: both large roles still load.
        async with manager.use(ModelRole.EXPLANATION):
            pass
        async with manager.use(ModelRole.DRAFTING):
            assert status_of(manager, ModelRole.EXPLANATION).state is ModelState.UNLOADED


async def test_us_2_2_cancelled_health_check_releases_the_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = build_model_env(tmp_path)
    async with managed(env) as manager:
        async with manager.use(CLASSIFICATION):
            pass
        gate = asyncio.Event()

        async def hanging_health(_port: int) -> bool:
            await gate.wait()
            return True

        monkeypatch.setattr(manager_module, "_healthy", hanging_health)

        async def classify() -> None:
            async with manager.use(CLASSIFICATION):
                pass

        task = asyncio.create_task(classify())
        while not manager._by_role[CLASSIFICATION].refcount:
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert manager._by_role[CLASSIFICATION].refcount == 0
        assert status_of(manager, CLASSIFICATION).state is ModelState.READY


async def test_us_2_2_group_members_are_stopped_with_the_leader(tmp_path: Path) -> None:
    """Review finding: helpers that outlive the server's main process are SIGKILLed too."""
    leader = (
        "import subprocess, sys, signal\n"
        "child = subprocess.Popen([sys.executable, '-m', 'tests.fakes.fake_model_server',"
        " '--host', sys.argv[1], '--port', sys.argv[2], '--ignore-sigterm'])\n"
        "signal.pause()\n"
    )
    spec = {"command": [sys.executable, "-c", leader, "{host}", "{port}"]}
    env = build_model_env(tmp_path, roles={"explanation": spec})
    port = env.port(ModelRole.EXPLANATION)
    async with managed(env, term_grace=0.5) as manager:
        async with manager.use(ModelRole.EXPLANATION):
            assert port_open(port)
        await manager.unload(ModelRole.EXPLANATION)
        assert not port_open(port)
    assert not [
        line
        for line in subprocess.run(
            ["/bin/ps", "-axo", "command="], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        if f"--port {port} --ignore-sigterm" in line
    ]


async def test_us_2_2_sweeper_survives_a_failed_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    manager = build_model_env(tmp_path).manager()
    calls = 0

    async def flaky() -> list[int]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(PHI_PATH)
        return []

    monkeypatch.setattr(manager, "sweep_idle", flaky)
    sweeper = asyncio.create_task(manager.run_sweeper(interval=0.01))
    while calls < 3:
        await asyncio.sleep(0.01)
    sweeper.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sweeper
    assert "idle sweep failed: OSError" in caplog.text
    assert PHI_PATH not in caplog.text


async def test_us_2_2_sweeper_runs_in_the_background(tmp_path: Path) -> None:
    env = build_model_env(tmp_path, idle_timeout_s=0.2)
    async with managed(env) as manager:
        async with manager.use(CLASSIFICATION):
            pass
        sweeper = asyncio.create_task(manager.run_sweeper())  # period = idle_timeout / 4
        try:
            for _ in range(100):
                if status_of(manager, CLASSIFICATION).state is ModelState.UNLOADED:
                    break
                await asyncio.sleep(0.05)
        finally:
            sweeper.cancel()
        assert status_of(manager, CLASSIFICATION).state is ModelState.UNLOADED


async def test_us_2_2_use_waits_for_a_stopping_server(tmp_path: Path) -> None:
    env = build_model_env(
        tmp_path, roles={"explanation": {"command": fake_server_command("--ignore-sigterm")}}
    )
    async with managed(env, term_grace=0.5) as manager:
        async with manager.use(ModelRole.EXPLANATION):
            first = status_of(manager, ModelRole.EXPLANATION).pid
        unloading = asyncio.create_task(manager.unload(ModelRole.EXPLANATION))
        while status_of(manager, ModelRole.EXPLANATION).state is not ModelState.STOPPING:
            await asyncio.sleep(0.01)
        async with manager.use(ModelRole.EXPLANATION):  # waits, then starts a new server
            second = status_of(manager, ModelRole.EXPLANATION).pid
        await unloading
    assert second not in (None, first)


# --- Worker routes and lifecycle ---------------------------------------------------------------


@asynccontextmanager
async def worker_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://w", headers=AUTH) as client:
        yield client


async def test_us_2_2_worker_model_routes(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    manager = env.manager()
    app = create_app(TOKEN, manager)
    async with app.router.lifespan_context(app), worker_client(app) as client:
        before = ModelsStatusResponse.model_validate_json(
            (await client.get("/models/status")).content
        )
        loaded = ModelStatus.model_validate_json(
            (await client.post("/models/classification/load")).content
        )
        pid = loaded.pid
        unloaded = await client.post("/models/explanation/unload")
        invalid = await client.post("/models/chat/load")
    assert before.idle_timeout_s == 600
    assert [m.role for m in before.models] == list(env.registry.roles)
    assert loaded.state is ModelState.READY
    assert unloaded.status_code == 200
    assert invalid.status_code == 422
    assert ErrorEnvelope.model_validate_json(invalid.content).error.code == "invalid_request"
    assert pid is not None
    assert not alive(pid)  # the lifespan stopped every model server on shutdown


async def test_us_2_2_worker_without_models_has_no_model_routes() -> None:
    async with worker_client(create_app(TOKEN)) as client:
        response = await client.get("/models/status")
    assert response.status_code == 404
    assert ErrorEnvelope.model_validate_json(response.content).error.code == "not_found"


async def test_us_2_2_busy_unload_route_returns_envelope(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    manager = env.manager()
    app = create_app(TOKEN, manager)
    async with (
        app.router.lifespan_context(app),
        worker_client(app) as client,
        manager.use(CLASSIFICATION),
    ):
        response = await client.post("/models/classification/unload")
    assert response.status_code == 409
    assert ErrorEnvelope.model_validate_json(response.content).error.code == "model_busy"


def test_us_2_2_worker_main_builds_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[FastAPI, dict[str, Any]]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setenv("MODELS_HOME", str(tmp_path / "Models"))
    assert worker_main.main(["--data-dir", str(tmp_path), "--port", "18201"]) == 0
    app, kwargs = calls[0]
    assert isinstance(app.state.models, ModelManager)
    assert app.state.models.models_home == tmp_path / "Models"
    assert (tmp_path / REGISTRY_FILE).is_file()
    # Review finding: in-flight loads may not hold shutdown past the launcher's SIGKILL.
    assert kwargs["timeout_graceful_shutdown"] == worker_main.GRACEFUL_SHUTDOWN
    assert worker_main.GRACEFUL_SHUTDOWN + 2 * 10.0 < launcher.STOP_TIMEOUT


async def test_us_2_2_lifespan_stops_servers_even_if_jobs_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = build_model_env(tmp_path).manager()
    app = create_app(TOKEN, manager)

    async def broken() -> None:
        raise OSError(PHI_PATH)

    monkeypatch.setattr(app.state.acquirer, "shutdown", broken)
    with pytest.raises(OSError, match="cases"):
        async with app.router.lifespan_context(app), manager.use(CLASSIFICATION):
            pid = status_of(manager, CLASSIFICATION).pid
    assert pid is not None
    assert not alive(pid)


def test_us_2_2_worker_main_rejects_invalid_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: pytest.fail("must not serve"))
    (tmp_path / REGISTRY_FILE).write_text("version: 1\nroles: {}\n")
    assert worker_main.main(["--data-dir", str(tmp_path)]) == 2
    line = json.loads(capsys.readouterr().err.splitlines()[-1])  # US-3.4: JSON on stderr
    assert line["level"] == "error"
    assert line["message"].startswith(
        "models.yaml is invalid: models.yaml: acquire: Field required"
    )
    assert not (tmp_path / "worker" / "token").exists()


# --- Orphans of a crashed worker ---------------------------------------------------------------


def detached_fake_server(port: int, model: Path, *extra: str) -> int:
    """Start a fake server that is not our child, like one a killed worker left behind.

    An intermediate Python starts it in a new session (as ``ModelManager`` does) and exits, so
    the server is re-parented to launchd. Its argv is not the registry command (as after
    ``mtplx serve`` re-executes itself); it only shares the model path and ``--port``.
    """
    argv = [
        sys.executable,
        "-m",
        "tests.fakes.fake_model_server",
        "--model",
        str(model),
        "--port",
        str(port),
        *extra,
    ]
    spawn = (
        "import subprocess, sys\n"
        "p = subprocess.Popen(sys.argv[1:], start_new_session=True,"
        " stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "print(p.pid)\n"
    )
    shell = subprocess.run(
        [sys.executable, "-c", spawn, *argv],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    pid = int(shell.stdout.strip())
    for _ in range(200):
        if port_open(port):
            break
        subprocess.run(["/bin/sleep", "0.05"], check=True)
    return pid


@pytest.mark.parametrize("extra", [(), ("--ignore-sigterm",)], ids=["sigterm", "sigkill"])
def test_us_2_2_orphans_of_a_crashed_worker_are_reaped(
    tmp_path: Path, extra: tuple[str, ...]
) -> None:
    env = build_model_env(tmp_path)
    roles = (ModelRole.DRAFTING, ModelRole.TRANSCRIPTION)
    orphans = {}
    try:
        for role in roles:
            model = env.registry.roles[role].model_path(env.home)
            orphans[role] = detached_fake_server(env.port(role), model, *extra)
        stranger = os.getpid()  # a live PID whose command line does not match its record
        records = {
            env.port(role): {
                "pid": pid,
                "markers": [
                    str(env.registry.roles[role].model_path(env.home)),
                    f"--port {env.port(role)}",
                ],
            }
            for role, pid in orphans.items()
        }
        records[18219] = {"pid": stranger, "markers": ["/m/Qwen3-14B-4bit", "--port 18219"]}
        env.state_dir.mkdir(parents=True)
        (env.state_dir / "servers.json").write_text(json.dumps(records))

        manager = ModelManager(
            env.registry, models_home=env.home, state_dir=env.state_dir, term_grace=0.5
        )
        started = time.monotonic()
        assert sorted(manager.reap_orphans()) == sorted(orphans.values())
        # One shared deadline: two orphans that ignore SIGTERM cost one grace period, not two.
        assert time.monotonic() - started < 0.5 + 1.0
        assert not any(alive(pid) for pid in orphans.values())
        assert not any(port_open(env.port(role)) for role in roles)
        assert alive(stranger)
        assert not manager.records_path.exists()
        assert manager.reap_orphans() == []
    finally:
        for pid in orphans.values():
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pid, signal.SIGKILL)


def test_us_2_2_corrupt_server_records_are_dropped(tmp_path: Path) -> None:
    env = build_model_env(tmp_path)
    manager = env.manager()
    manager.records_path.write_text("{not json")
    assert manager.reap_orphans() == []
    assert not manager.records_path.exists()


# --- Real model (opt-in: uv run pytest -m models -k us_2_2) ------------------------------------


@pytest.mark.models
async def test_us_2_2_real_drafting_server_starts_and_unloads(tmp_path: Path) -> None:
    """The shipped ``models.yaml`` command starts Bonsai 27B via ``mtplx serve`` on loopback."""
    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    home = models_home()
    spec = registry.roles[ModelRole.DRAFTING]
    if spec.weights(home) == "missing" or not spec.venv_present(home):
        pytest.skip(f"Bonsai or the mtplx venv is not under {home}")
    if port_open(spec.port):
        pytest.skip(f"port {spec.port} is in use")
    manager = ModelManager(registry, models_home=home, state_dir=tmp_path / "state")
    try:
        async with manager.use(ModelRole.DRAFTING) as endpoint:
            pid = status_of(manager, ModelRole.DRAFTING).pid
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                models = (await client.get(f"{endpoint.base_url}/models")).json()
        assert models["data"]
        assert pid is not None
        status = await manager.unload(ModelRole.DRAFTING)
    finally:
        await manager.shutdown()
    assert status.state is ModelState.UNLOADED
    assert not alive(pid)
    assert not port_open(spec.port)


async def test_us_2_2_terminate_waits_for_the_group_to_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``terminate`` returns only once the process group is gone (its port is then free)."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)", start_new_session=True
    )
    answers = iter([True, True, False])
    probes: list[int] = []

    def group_alive(pgid: int) -> bool:
        probes.append(pgid)
        return next(answers)

    monkeypatch.setattr(manager_module, "_group_alive", group_alive)
    await manager_module.terminate(process, grace=1.0)
    assert process.returncode is not None
    assert probes == [process.pid] * 3
