"""US-2.3 Memory Guard and Queueing.

Scenarios: two large models are never resident together; Voxtral loads only alone; queued work
reports its state. Residency is observed on real fake-server processes: at the instant each
server is spawned the test records which other servers are still alive. Rules: BR-12, NFR-7.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.api.models import ErrorEnvelope
from claimcoach.models.manager import ModelBusyError, ModelManager
from claimcoach.models.memory_guard import MemoryGuard, SizeTier
from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry, ResidencyPolicy
from claimcoach.models.types import ModelRole, ModelsStatusResponse, ModelState
from claimcoach.worker.app import create_app
from tests.conftest import REPO_ROOT
from tests.fakes.model_env import ModelEnv, build_model_env

TOKEN = "guard-test-token"
EXPLANATION = ModelRole.EXPLANATION  # Qwen3-14B
DRAFTING = ModelRole.DRAFTING  # Bonsai 27B
TRANSCRIPTION = ModelRole.TRANSCRIPTION  # Voxtral 24B, runs_alone


@pytest.fixture(autouse=True)
def _fake_server_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))


class SpawnLog:
    """Records, for every server spawned, which other servers were alive at that instant."""

    def __init__(self, env: ModelEnv) -> None:
        self.env = env
        self.manager: ModelManager | None = None
        self.spawns: list[tuple[int, set[int]]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_exec = asyncio.create_subprocess_exec

        async def spawn(*argv: str, **kwargs: Any) -> asyncio.subprocess.Process:
            assert self.manager is not None
            port = int(argv[argv.index("--port") + 1])
            alive = {
                s.port
                for s in self.manager._servers.values()
                if s.process is not None and s.process.returncode is None
            }
            listening = {p for p in self.manager._servers if _listening(p)}
            assert alive == listening  # a process is alive exactly while its port answers
            self.spawns.append((port, alive))
            return await real_exec(*argv, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    def alive_when_started(self, role: ModelRole) -> set[ModelRole]:
        port = self.env.port(role)
        (alive,) = [alive for spawned, alive in self.spawns if spawned == port]
        return {r for r, spec in self.env.registry.roles.items() if spec.port in alive}


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


@asynccontextmanager
async def guarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **top: Any
) -> AsyncIterator[tuple[ModelManager, SpawnLog]]:
    env = build_model_env(tmp_path, **top)
    log = SpawnLog(env)
    log.install(monkeypatch)
    manager = env.manager()
    log.manager = manager
    try:
        yield manager, log
    finally:
        await manager.shutdown()


async def warm(manager: ModelManager, role: ModelRole) -> None:
    async with manager.use(role):
        pass


async def wait_for_state(manager: ModelManager, role: ModelRole, state: ModelState) -> None:
    for _ in range(400):
        if manager.role_status(role).state is state:
            return
        await asyncio.sleep(0.025)
    pytest.fail(f"{role} never reached {state}")


# --- The rule ----------------------------------------------------------------------------------

SMALL = SizeTier(port=18202, tier_b=8, runs_alone=False)
EMBED = SizeTier(port=18203, tier_b=8, runs_alone=False)
MEDIUM = SizeTier(port=18205, tier_b=14, runs_alone=False)
LARGE = SizeTier(port=18206, tier_b=27, runs_alone=False)
ALONE = SizeTier(port=18207, tier_b=24, runs_alone=True)


@pytest.mark.parametrize(
    ("candidate", "resident", "blockers"),
    [
        (SMALL, [], []),
        (SMALL, [EMBED, MEDIUM], []),
        (MEDIUM, [SMALL, EMBED], []),
        (LARGE, [SMALL, MEDIUM], [MEDIUM]),
        (MEDIUM, [LARGE], [LARGE]),
        (LARGE, [LARGE], []),  # the candidate itself is not a blocker
        (ALONE, [], []),
        (ALONE, [SMALL, EMBED], [SMALL, EMBED]),
        (SMALL, [ALONE], [ALONE]),
        (MEDIUM, [ALONE], [ALONE]),
    ],
)
def test_us_2_3_residency_rule(
    candidate: SizeTier, resident: list[SizeTier], blockers: list[SizeTier]
) -> None:
    guard = MemoryGuard(ResidencyPolicy(large_tier_b=14))
    assert guard.blockers(candidate, resident) == blockers


def test_us_2_3_tiers_come_from_models_yaml() -> None:
    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    guard = MemoryGuard.from_registry(registry)
    large = {r for r, s in registry.roles.items() if guard.is_large(SizeTier.of(s))}
    assert large == {EXPLANATION, DRAFTING, TRANSCRIPTION}
    assert [r for r, s in registry.roles.items() if s.runs_alone] == [TRANSCRIPTION]


# --- Scenario: Two large models are never resident together ------------------------------------


async def test_us_2_3_two_large_models_never_resident(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with guarded(tmp_path, monkeypatch) as (manager, log):
        await warm(manager, EXPLANATION)
        await warm(manager, ModelRole.CLASSIFICATION)  # an 8B may stay next to the 14B
        assert manager.role_status(EXPLANATION).state is ModelState.READY

        async with manager.use(DRAFTING):
            assert manager.role_status(EXPLANATION).state is ModelState.UNLOADED
            assert manager.role_status(ModelRole.CLASSIFICATION).state is ModelState.READY
    assert EXPLANATION not in log.alive_when_started(DRAFTING)
    assert ModelRole.CLASSIFICATION in log.alive_when_started(DRAFTING)


async def test_us_2_3_busy_large_server_finishes_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with guarded(tmp_path, monkeypatch) as (manager, log):
        drafting_done = asyncio.Event()

        async def draft() -> None:
            async with manager.use(DRAFTING):
                drafting_done.set()

        async with manager.use(EXPLANATION) as explanation:
            drafting = asyncio.create_task(draft())
            await wait_for_state(manager, DRAFTING, ModelState.QUEUED)
            async with httpx.AsyncClient(trust_env=False) as client:
                response = await client.get(f"{explanation.base_url}/models")
            assert response.status_code == 200  # the explanation request still completes
            assert not drafting_done.is_set()
        await drafting
    assert EXPLANATION not in log.alive_when_started(DRAFTING)


async def test_us_2_3_concurrent_large_loads_admit_one_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with guarded(tmp_path, monkeypatch) as (manager, log):
        await asyncio.gather(warm(manager, EXPLANATION), warm(manager, DRAFTING))
    assert EXPLANATION not in log.alive_when_started(DRAFTING)
    assert DRAFTING not in log.alive_when_started(EXPLANATION)


# --- Scenario: Voxtral loads only alone --------------------------------------------------------


async def test_us_2_3_voxtral_loads_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with guarded(tmp_path, monkeypatch) as (manager, log):
        await warm(manager, ModelRole.EMBEDDING)  # idle: evicted at once
        transcribed = asyncio.Event()

        async def transcribe() -> None:
            async with manager.use(TRANSCRIPTION):
                transcribed.set()
                # While Voxtral is resident nothing else may start.
                waiting = asyncio.create_task(warm(manager, ModelRole.CLASSIFICATION))
                await wait_for_state(manager, ModelRole.CLASSIFICATION, ModelState.QUEUED)
            await waiting

        async with manager.use(ModelRole.CLASSIFICATION):  # busy: kept until released
            job = asyncio.create_task(transcribe())
            await wait_for_state(manager, TRANSCRIPTION, ModelState.QUEUED)
            await wait_for_state(manager, ModelRole.EMBEDDING, ModelState.UNLOADED)
            assert manager.role_status(ModelRole.CLASSIFICATION).state is ModelState.READY
            assert not transcribed.is_set()
        await job
    assert log.alive_when_started(TRANSCRIPTION) == set()
    classification_starts = [
        alive for port, alive in log.spawns if port == log.env.port(ModelRole.CLASSIFICATION)
    ]
    assert log.env.port(TRANSCRIPTION) not in classification_starts[-1]


# --- Scenario: Queued work reports its state ---------------------------------------------------


def gateway(manager: ModelManager) -> tuple[FastAPI, FastAPI]:
    worker = create_app(TOKEN, manager)
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(app=worker))
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/plugins/claimcoach")
    app.dependency_overrides[routes.get_worker_client] = lambda: client
    return app, worker


async def desktop_poll(app: FastAPI) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        return await desktop.get("/api/plugins/claimcoach/models/status")


async def test_us_2_3_queued_work_reports_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with guarded(tmp_path, monkeypatch) as (manager, _log):
        app, worker = gateway(manager)
        async with worker.router.lifespan_context(worker), manager.use(EXPLANATION):
            draft = asyncio.create_task(warm(manager, DRAFTING))
            await wait_for_state(manager, DRAFTING, ModelState.QUEUED)
            response = await desktop_poll(app)
        await draft
        after = await desktop_poll(app)
    assert response.status_code == 200
    roles = {m.role: m for m in ModelsStatusResponse.model_validate_json(response.content).models}
    assert roles[DRAFTING].state is ModelState.QUEUED
    assert roles[DRAFTING].queued_requests == 1
    assert roles[EXPLANATION].state is ModelState.READY
    done = {m.role: m for m in ModelsStatusResponse.model_validate_json(after.content).models}
    assert done[DRAFTING].queued_requests == 0


async def test_us_2_3_queue_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with guarded(tmp_path, monkeypatch, queue_timeout_s=0.3) as (manager, log):
        worker = create_app(TOKEN, manager)
        transport = httpx.ASGITransport(app=worker)
        async with (
            manager.use(EXPLANATION),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://worker",
                headers={"Authorization": f"Bearer {TOKEN}"},
            ) as client,
        ):
            with pytest.raises(ModelBusyError):
                await warm(manager, DRAFTING)
            response = await client.post("/models/drafting/load")
        status = manager.role_status(DRAFTING)
    assert response.status_code == 409
    assert ErrorEnvelope.model_validate_json(response.content).error.code == "model_busy"
    assert status.state is ModelState.UNLOADED
    assert status.queued_requests == 0
    assert all(port != log.env.port(DRAFTING) for port, _ in log.spawns)


async def test_us_2_3_queued_load_is_not_starved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding: new requests for the blocker wait behind the queued load, not re-pin it."""
    async with guarded(tmp_path, monkeypatch) as (manager, _log):
        served: list[ModelRole] = []

        async def serve(role: ModelRole) -> None:
            async with manager.use(role):
                served.append(role)

        async with manager.use(EXPLANATION):
            draft = asyncio.create_task(serve(DRAFTING))
            await wait_for_state(manager, DRAFTING, ModelState.QUEUED)
            late = asyncio.create_task(serve(EXPLANATION))  # steady 14B traffic
            await asyncio.sleep(0.2)
            assert manager._by_role[EXPLANATION].refcount == 1  # the late request did not pin
        await asyncio.gather(draft, late)
    assert served == [DRAFTING, EXPLANATION]
