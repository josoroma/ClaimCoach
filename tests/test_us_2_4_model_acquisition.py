"""US-2.4 Missing-Model Detection and Confirmed Download.

Scenarios: missing models are reported; download requires confirmation; declined download makes
no network call. US-14.1 removed the reranker and its local conversion, and their tests with them.
Requests go desktop → gateway routes → ``WorkerClient`` → worker app → ``Acquirer``; the download
tool is the offline fake in ``tests/fakes/fake_hf.py``. Rules: BR-1, BR-11, BR-14, ES-8.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import stat
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from claimcoach.api import routes
from claimcoach.api.client import (
    RELAYED_CODES,
    WorkerClient,
    WorkerFailedError,
    WorkerRejectedError,
)
from claimcoach.api.models import ERROR_MESSAGES, ErrorCode, ErrorEnvelope, envelope
from claimcoach.models.acquire import Acquirer
from claimcoach.models.manager import ModelManager, ModelUnavailableError
from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry
from claimcoach.models.types import (
    AcquireResult,
    DownloadRequest,
    ModelRole,
    ModelsStatusResponse,
    ModelStatus,
)
from claimcoach.worker.app import create_app
from tests.conftest import REPO_ROOT
from tests.fakes.model_env import ModelEnv, build_model_env

TOKEN = "acquire-test-token"
PREFIX = "/api/plugins/claimcoach"
EXPLANATION = ModelRole.EXPLANATION
PHI = "Jane Doe MRN 0042"
FAKE_HF = [sys.executable, "-m", "tests.fakes.fake_hf"]
JSON = {"Content-Type": "application/json"}


def use_fake_hf(data: dict[str, Any]) -> None:
    data["acquire"] = {"download": [*FAKE_HF, "download", "{repo_id}", "--local-dir", "{target}"]}


@pytest.fixture
def hf_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log = tmp_path / "fake-hf.jsonl"
    monkeypatch.setenv("FAKE_HF_LOG", str(log))
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    return log


def calls(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


@pytest.fixture
def env(tmp_path: Path) -> ModelEnv:
    env = build_model_env(tmp_path, mutate=use_fake_hf)
    shutil.rmtree(env.registry.roles[EXPLANATION].model_path(env.home))
    return env


class Stack:
    """The desktop half's view: gateway router → WorkerClient → worker app (with lifespan)."""

    def __init__(self, manager: ModelManager) -> None:
        self.manager = manager
        self.worker = create_app(TOKEN, manager)
        client = WorkerClient(
            "http://worker", lambda: TOKEN, transport=httpx.ASGITransport(app=self.worker)
        )
        self.gateway = FastAPI()
        self.gateway.include_router(routes.router, prefix=PREFIX)
        self.gateway.dependency_overrides[routes.get_worker_client] = lambda: client
        self._desktop = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.gateway), base_url="http://gateway"
        )

    async def status(self) -> dict[ModelRole, ModelStatus]:
        response = await self._desktop.get(f"{PREFIX}/models/status")
        assert response.status_code == 200, response.text
        body = ModelsStatusResponse.model_validate_json(response.content)
        return {m.role: m for m in body.models}

    async def post(
        self, path: str, body: object, content_type: str = "application/json"
    ) -> httpx.Response:
        content = body if isinstance(body, str) else json.dumps(body)
        return await self._desktop.post(
            f"{PREFIX}{path}", content=content, headers={"Content-Type": content_type}
        )

    async def wait_idle(self, role: ModelRole) -> ModelStatus:
        for _ in range(400):
            status = (await self.status())[role]
            if status.acquire != "downloading":
                return status
            await asyncio.sleep(0.025)
        pytest.fail(f"{role} job did not finish")


@asynccontextmanager
async def stack(env: ModelEnv, **kwargs: Any) -> AsyncIterator[Stack]:
    s = Stack(env.manager(**kwargs))
    async with s.worker.router.lifespan_context(s.worker), s._desktop:
        yield s


def acquirer_of(s: Stack) -> Acquirer:
    acquirer: Acquirer = s.worker.state.acquirer
    return acquirer


def assert_envelope(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = ErrorEnvelope.model_validate_json(response.content)
    assert body.error.code == code
    assert body.error.message == ERROR_MESSAGES[body.error.code]


class SpawnSpy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.argv: list[tuple[str, ...]] = []
        real = asyncio.create_subprocess_exec

        async def spy(*argv: str, **kwargs: Any) -> asyncio.subprocess.Process:
            self.argv.append(argv)
            return await real(*argv, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)


# --- Scenario: Missing models are reported -----------------------------------------------------


async def test_us_2_4_missing_models_reported(env: ModelEnv) -> None:
    async with stack(env) as s:
        status = await s.status()
    assert status[EXPLANATION].weights == "missing"
    present = {role for role, m in status.items() if m.weights == "present"}
    assert present == set(ModelRole) - {EXPLANATION}
    assert all(m.acquire is None for m in status.values())


# --- Scenario: Download requires confirmation --------------------------------------------------


async def test_us_2_4_download_requires_confirmation(env: ModelEnv, hf_log: Path) -> None:
    async with stack(env) as s:
        response = await s.post("/models/download", {"role": "explanation", "confirm": True})
        assert AcquireResult.model_validate_json(response.content).outcome == "started"
        assert (await s.status())[EXPLANATION].acquire in ("downloading", None)
        status = await s.wait_idle(EXPLANATION)
        again = await s.post("/models/download", {"role": "explanation", "confirm": True})
    assert status.weights == "present"
    assert status.acquire is None
    target = env.registry.roles[EXPLANATION].model_path(env.home)
    assert target.is_relative_to(env.home)
    assert calls(hf_log) == [
        {
            "argv": ["download", "mlx-community/Qwen3-14B-4bit", "--local-dir", str(target)],
            "offline": False,
        }
    ]
    assert AcquireResult.model_validate_json(again.content).outcome == "present"
    assert len(calls(hf_log)) == 1  # a present model is never fetched again
    log = env.state_dir / "acquire-explanation.log"
    assert stat.S_IMODE(log.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "body",
    [
        {"role": "explanation"},
        {"role": "explanation", "confirm": "yes"},
        {"role": "explanation", "confirm": 1},
        {"role": "explanation", "confirm": True, "note": PHI},
        {"role": PHI, "confirm": True},
        "not json " + PHI,
    ],
)
async def test_us_2_4_missing_confirmation_flag(
    env: ModelEnv, hf_log: Path, monkeypatch: pytest.MonkeyPatch, body: object
) -> None:
    spy = SpawnSpy(monkeypatch)
    async with stack(env) as s:
        gateway = await s.post("/models/download", body)
        transport = httpx.ASGITransport(app=s.worker)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://w",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ) as worker:
            direct = await worker.post(
                "/models/download",
                content=body if isinstance(body, str) else json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
    for response in (gateway, direct):
        assert_envelope(response, 422, "invalid_request")
        assert PHI not in response.text
    assert spy.argv == []
    assert calls(hf_log) == []


@pytest.mark.usefixtures("hf_log")
async def test_us_2_4_download_in_progress_and_shutdown(
    env: ModelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_HF_SLEEP", "30")
    async with stack(env, term_grace=0.5) as s:
        first = await s.post("/models/download", {"role": "explanation", "confirm": True})
        second = await s.post("/models/download", {"role": "explanation", "confirm": True})
        assert (await s.status())[EXPLANATION].acquire == "downloading"
        jobs = acquirer_of(s)
    # Leaving the lifespan stopped the job; hf resumes on the next confirmed download.
    assert AcquireResult.model_validate_json(first.content).outcome == "started"
    assert AcquireResult.model_validate_json(second.content).outcome == "in_progress"
    assert jobs.states() == {EXPLANATION: "failed"}
    assert not jobs._processes


async def test_us_2_4_roles_sharing_a_directory_share_one_download(
    env: ModelEnv, hf_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """phi_detection and classification share Qwen3-8B-4bit: one ``hf download``, not two."""
    shutil.rmtree(env.registry.roles[ModelRole.CLASSIFICATION].model_path(env.home))
    monkeypatch.setenv("FAKE_HF_SLEEP", "0.5")
    async with stack(env) as s:
        first = await s.post("/models/download", {"role": "phi_detection", "confirm": True})
        second = await s.post("/models/download", {"role": "classification", "confirm": True})
        during = await s.status()
        after = await s.wait_idle(ModelRole.CLASSIFICATION)
    assert AcquireResult.model_validate_json(first.content).outcome == "started"
    assert AcquireResult.model_validate_json(second.content).outcome == "in_progress"
    assert during[ModelRole.PHI_DETECTION].acquire == "downloading"
    assert during[ModelRole.CLASSIFICATION].acquire == "downloading"
    assert after.weights == "present"
    assert len(calls(hf_log)) == 1


@pytest.mark.usefixtures("hf_log")
@pytest.mark.parametrize("knob", ["FAKE_HF_EXIT", "FAKE_HF_EMPTY"])
async def test_us_2_4_failed_download_reported_then_retried(
    env: ModelEnv, monkeypatch: pytest.MonkeyPatch, knob: str
) -> None:
    monkeypatch.setenv(knob, "1")
    async with stack(env) as s:
        await s.post("/models/download", {"role": "explanation", "confirm": True})
        failed = await s.wait_idle(EXPLANATION)
        monkeypatch.delenv(knob)
        await s.post("/models/download", {"role": "explanation", "confirm": True})
        retried = await s.wait_idle(EXPLANATION)
    assert failed.acquire == "failed"
    assert failed.weights == "missing"
    assert retried.acquire is None
    assert retried.weights == "present"


async def test_us_2_4_default_commands_use_the_model_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shipped template runs ``hf`` from ``$MODELS_HOME/.venvs/mlx-lm``."""
    spawned: list[tuple[str, ...]] = []

    async def refuse(*argv: str, **_kwargs: Any) -> asyncio.subprocess.Process:
        spawned.append(argv)
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", refuse)
    home = tmp_path / "Models"
    manager = ModelManager(
        ModelRegistry.load(DEFAULT_REGISTRY), models_home=home, state_dir=tmp_path / "state"
    )
    jobs = Acquirer(manager)
    await jobs.download(DownloadRequest(role=EXPLANATION, confirm=True))
    await jobs.shutdown()
    venv = home / ".venvs" / "mlx-lm" / "bin"
    assert spawned == [
        (
            str(venv / "hf"),
            "download",
            "mlx-community/Qwen3-14B-4bit",
            "--local-dir",
            str(home / "Qwen3-14B-4bit"),
        ),
    ]
    assert jobs.states() == {EXPLANATION: "failed"}


# --- Scenario: Declined download makes no network call -----------------------------------------


async def test_us_2_4_declined_download_no_network(
    env: ModelEnv, hf_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The autouse socket guard fails the test on any non-loopback connect or DNS lookup from this
    # process; the spy proves no download process (which the guard cannot see) was started.
    spy = SpawnSpy(monkeypatch)
    async with stack(env) as s:
        download = await s.post("/models/download", {"role": "explanation", "confirm": False})
        status = await s.status()
    assert AcquireResult.model_validate_json(download.content).outcome == "declined"
    assert spy.argv == []
    assert calls(hf_log) == []
    assert status[EXPLANATION].weights == "missing"
    assert status[EXPLANATION].acquire is None


# --- Gateway client: relayed worker codes ------------------------------------------------------


def mock_client(response: httpx.Response) -> WorkerClient:
    return WorkerClient(
        "http://worker", lambda: TOKEN, transport=httpx.MockTransport(lambda _r: response)
    )


@pytest.mark.parametrize("code", sorted(RELAYED_CODES))
async def test_us_2_4_client_relays_worker_codes(code: ErrorCode) -> None:
    body = envelope(code).model_dump()
    body["error"]["message"] = PHI  # the gateway rebuilds the fixed message
    client = mock_client(httpx.Response(RELAYED_CODES[code], json=body))
    with pytest.raises(WorkerRejectedError) as raised:
        await client.download_model(DownloadRequest(role=EXPLANATION, confirm=True))
    assert raised.value.code == code
    assert raised.value.status_code == RELAYED_CODES[code]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json=envelope("not_found").model_dump()),
        httpx.Response(409, text=PHI),
        httpx.Response(500, json=envelope("model_busy").model_dump()),
    ],
)
async def test_us_2_4_client_does_not_relay_other_errors(response: httpx.Response) -> None:
    with pytest.raises(WorkerFailedError):
        await mock_client(response).models_status()


async def test_us_2_4_gateway_routes_answer_worker_unavailable() -> None:
    client = WorkerClient("http://worker", lambda: None)
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    app.dependency_overrides[routes.get_worker_client] = lambda: client
    transport = httpx.ASGITransport(app=app)
    body = json.dumps({"role": "explanation", "confirm": True})
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        responses = [
            await desktop.get(f"{PREFIX}/models/status"),
            await desktop.post(f"{PREFIX}/models/download", content=body, headers=JSON),
        ]
    for response in responses:
        assert_envelope(response, 503, "worker_unavailable")


# --- Review regressions ------------------------------------------------------------------------


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", ""])
async def test_us_2_4_gateway_accepts_only_json_bodies(
    env: ModelEnv, hf_log: Path, monkeypatch: pytest.MonkeyPatch, content_type: str
) -> None:
    """A cross-site ``text/plain`` or form POST can never start a download."""
    spy = SpawnSpy(monkeypatch)
    body = {"role": "explanation", "confirm": True}
    async with stack(env) as s:
        download = await s.post("/models/download", body, content_type)
        charset = await s.post("/models/download", body, "application/json; charset=utf-8")
        await s.wait_idle(EXPLANATION)
    assert_envelope(download, 422, "invalid_request")
    assert AcquireResult.model_validate_json(charset.content).outcome == "started"
    assert len(spy.argv) == 1
    assert len(calls(hf_log)) == 1


async def test_us_2_4_interrupted_multi_shard_download_is_resumed(
    env: ModelEnv, hf_log: Path
) -> None:
    """Review finding: one shard of two is not a model; the next confirmed download resumes."""
    target = env.registry.roles[EXPLANATION].model_path(env.home)
    target.mkdir()
    (target / "config.json").write_text("{}")
    index = {
        "weight_map": {
            "a": "model-00001-of-00002.safetensors",
            "b": "model-00002-of-00002.safetensors",
        }
    }
    (target / "model.safetensors.index.json").write_text(json.dumps(index))
    (target / "model-00001-of-00002.safetensors").write_bytes(b"first shard")
    async with stack(env) as s:
        assert (await s.status())[EXPLANATION].weights == "missing"
        response = await s.post("/models/download", {"role": "explanation", "confirm": True})
        await s.wait_idle(EXPLANATION)
    assert AcquireResult.model_validate_json(response.content).outcome == "started"
    assert len(calls(hf_log)) == 1


async def test_us_2_4_no_server_starts_from_a_directory_being_written(env: ModelEnv) -> None:
    async with stack(env) as s:
        target = env.registry.roles[ModelRole.DRAFTING].model_path(env.home)
        s.manager.begin_job(target)
        with pytest.raises(ModelUnavailableError):
            async with s.manager.use(ModelRole.DRAFTING):
                pytest.fail("must not serve a model a job is writing")
        await s.manager.end_job(target)


@pytest.mark.usefixtures("hf_log")
async def test_us_2_4_failed_shared_download_marks_every_sharing_role(
    env: ModelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.rmtree(env.registry.roles[ModelRole.CLASSIFICATION].model_path(env.home))
    monkeypatch.setenv("FAKE_HF_EXIT", "1")
    async with stack(env) as s:
        await s.post("/models/download", {"role": "phi_detection", "confirm": True})
        await s.wait_idle(ModelRole.PHI_DETECTION)
        status = await s.status()
    assert status[ModelRole.PHI_DETECTION].acquire == "failed"
    assert status[ModelRole.CLASSIFICATION].acquire == "failed"
