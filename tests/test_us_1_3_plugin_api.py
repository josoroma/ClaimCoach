"""US-1.3 Thin Typed plugin_api Proxy and Error Envelope.

Scenarios: health route proxies to a running worker; worker unavailable returns the error
envelope; unhandled worker errors are mapped, not leaked. Rules: ES-1, ES-8, PC-2, PC-4, BR-14.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from claimcoach.api import routes
from claimcoach.api.client import (
    InvalidWorkerResponseError,
    WorkerClient,
    WorkerFailedError,
    WorkerUnauthorizedError,
    WorkerUnavailableError,
)
from claimcoach.api.models import ERROR_MESSAGES, ErrorEnvelope, HealthResponse, envelope
from claimcoach.worker import launcher
from claimcoach.worker.app import create_app, get_health
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.token import issue_token, read_token
from tests.conftest import PLUGIN_DIR, free_port_in_range, python_for_worker

TOKEN = "proxy-test-token"
PHI = "Jane Doe DOB 1970-01-01 MRN 0042"
PREFIX = "/api/plugins/claimcoach"
GATEWAY_ROUTES = {"/health", "/models/status", "/models/download", "/models/convert"}
"""US-1.3 health plus the EPIC-2 model routes (US-2.2 status, US-2.4 download/convert)."""


def gateway_app(client: WorkerClient) -> FastAPI:
    """Mount the router the way Hermes does, with the worker client swapped in."""
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    app.dependency_overrides[routes.get_worker_client] = lambda: client
    return app


def asgi_worker_client(worker: FastAPI, token: str | None = TOKEN) -> WorkerClient:
    transport = httpx.ASGITransport(app=worker, raise_app_exceptions=False)
    return WorkerClient("http://worker", lambda: token, transport=transport)


async def desktop_get(app: FastAPI, path: str = "/health") -> httpx.Response:
    """Call the gateway the way ``ctx.rest`` does."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        return await client.get(f"{PREFIX}{path}")


def assert_envelope(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status
    body = ErrorEnvelope.model_validate_json(response.content)
    assert body.error.code == code
    assert body.error.message == ERROR_MESSAGES[body.error.code]


# --- Scenario: Health route proxies to a running worker ----------------------------------------


async def test_us_1_3_health_proxies_to_worker() -> None:
    response = await desktop_get(gateway_app(asgi_worker_client(create_app(TOKEN))))
    assert response.status_code == 200
    assert HealthResponse.model_validate_json(response.content) == HealthResponse(version="0.1.0")


async def test_us_1_3_health_proxies_to_running_worker_process(tmp_path: Path) -> None:
    config = WorkerConfig(data_dir=tmp_path, port=free_port_in_range(), python=python_for_worker())
    launcher.start_worker(config)
    try:
        client = WorkerClient(config.base_url, lambda: read_token(config.token_path))
        response = await desktop_get(gateway_app(client))
    finally:
        launcher.stop_worker(config)
    assert response.status_code == 200
    HealthResponse.model_validate_json(response.content)


# --- Scenario: Worker unavailable returns the error envelope -----------------------------------


async def test_us_1_3_worker_unavailable_returns_envelope() -> None:
    port = free_port_in_range()
    client = WorkerClient(f"http://127.0.0.1:{port}", lambda: TOKEN, timeout=1.0)
    assert_envelope(await desktop_get(gateway_app(client)), 503, "worker_unavailable")


async def test_us_1_3_missing_token_returns_envelope() -> None:
    client = asgi_worker_client(create_app(TOKEN), token=None)
    assert_envelope(await desktop_get(gateway_app(client)), 503, "worker_unavailable")


# --- Scenario: Unhandled worker errors are mapped, not leaked ----------------------------------


async def test_us_1_3_unhandled_errors_mapped() -> None:
    def explode() -> Any:
        raise RuntimeError(PHI)

    worker = create_app(TOKEN)
    worker.dependency_overrides[get_health] = explode
    response = await desktop_get(gateway_app(asgi_worker_client(worker)))
    assert_envelope(response, 502, "worker_error")
    assert PHI not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


async def test_us_1_3_rejected_token_maps_to_unauthorized() -> None:
    client = asgi_worker_client(create_app(TOKEN), token="stale")
    assert_envelope(await desktop_get(gateway_app(client)), 401, "unauthorized")


async def test_us_1_3_worker_response_validation_failure_is_not_leaked() -> None:
    # The worker's own response_model rejects this body, so the worker answers its generic 500.
    def leaky() -> Any:
        return {"ok": True, "status": "ok", "version": "", "debug": PHI}

    worker = create_app(TOKEN)
    worker.dependency_overrides[get_health] = leaky
    response = await desktop_get(gateway_app(asgi_worker_client(worker)))
    assert_envelope(response, 502, "worker_error")
    assert PHI not in response.text


async def test_us_1_3_invalid_worker_body_maps_to_envelope() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "status": "ok", "debug": PHI})

    response = await desktop_get(gateway_app(mock_client(handler)))
    assert_envelope(response, 502, "invalid_worker_response")
    assert PHI not in response.text


# --- WorkerClient ------------------------------------------------------------------------------


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> WorkerClient:
    return WorkerClient("http://worker", lambda: TOKEN, transport=httpx.MockTransport(handler))


async def test_us_1_3_client_sends_bearer_token() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        return httpx.Response(200, json={"ok": True, "status": "ok", "version": "9.9.9"})

    assert (await mock_client(handler).health()).version == "9.9.9"
    assert seen == [f"Bearer {TOKEN}"]


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(401, json=envelope("unauthorized").model_dump()), WorkerUnauthorizedError),
        (httpx.Response(404, text="not found"), WorkerFailedError),
        (httpx.Response(500, text=PHI), WorkerFailedError),
        (httpx.Response(200, text="not json"), InvalidWorkerResponseError),
        (httpx.Response(200, json={"ok": True, "status": "down"}), InvalidWorkerResponseError),
    ],
)
async def test_us_1_3_client_maps_worker_responses(
    response: httpx.Response, error: type[Exception]
) -> None:
    with pytest.raises(error):
        await mock_client(lambda _request: response).health()


async def test_us_1_3_client_maps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(WorkerUnavailableError):
        await mock_client(handler).health()


def test_us_1_3_error_codes_have_fixed_messages() -> None:
    for code, message in ERROR_MESSAGES.items():
        assert envelope(code).model_dump() == {
            "ok": False,
            "error": {"code": code, "message": message},
        }


# --- Default dependency and gateway loading (PC-2, PC-4) ---------------------------------------


async def test_us_1_3_default_client_reads_current_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    client = routes.get_worker_client()
    assert client._base_url == "http://127.0.0.1:18200"
    assert client._token_provider() is None
    token = issue_token(tmp_path / "plugin-data/claimcoach/worker/token")
    assert client._token_provider() == token


@pytest.mark.parametrize("home", ["root", "root/profiles/alice"])
def test_us_1_3_worker_dir_is_profile_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, home: str
) -> None:
    """One worker serves every profile, so the gateway and the Makefile must agree on its dir."""
    from claimcoach.paths import app_data_dir  # noqa: PLC0415

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / home))
    assert app_data_dir() == (tmp_path / "root/plugin-data/claimcoach").resolve()


def test_us_1_3_worker_dir_uses_hermes_root_in_gateway(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from claimcoach.paths import app_data_dir  # noqa: PLC0415

    constants = ModuleType("hermes_constants")
    constants.get_default_hermes_root = lambda: tmp_path / "hermes-root"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)
    assert app_data_dir() == (tmp_path / "hermes-root/plugin-data/claimcoach").resolve()


def test_us_1_3_data_dir_follows_hermes_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from claimcoach.paths import plugin_data_dir  # noqa: PLC0415

    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert plugin_data_dir() == (tmp_path / ".hermes/plugin-data/claimcoach").resolve()


def test_us_1_3_data_dir_uses_hermes_storage_in_gateway(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from claimcoach.paths import plugin_data_dir  # noqa: PLC0415

    storage = ModuleType("plugins.plugin_storage")
    storage.plugin_data_dir = lambda name: tmp_path / "profile" / name  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "plugins", ModuleType("plugins"))
    monkeypatch.setitem(sys.modules, "plugins.plugin_storage", storage)
    assert plugin_data_dir() == (tmp_path / "profile" / "claimcoach").resolve()


def load_plugin_api() -> ModuleType:
    """Import ``plugin_api.py`` exactly as ``hermes_cli.web_server_dashboard`` does."""
    name = "hermes_dashboard_plugin_claimcoach"
    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR / "dashboard" / "plugin_api.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_us_1_3_plugin_api_loads_standalone() -> None:
    module = load_plugin_api()
    assert module.router is routes.router
    assert {r.path for r in module.router.routes if isinstance(r, APIRoute)} == GATEWAY_ROUTES


def test_us_1_3_plugin_api_reports_missing_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_a, **_k: None)
    source = (PLUGIN_DIR / "dashboard" / "plugin_api.py").read_text()
    namespace: dict[str, Any] = {"__file__": str(PLUGIN_DIR / "dashboard" / "plugin_api.py")}
    with pytest.raises(ImportError, match="cannot load"):
        exec(compile(source, "plugin_api.py", "exec"), namespace)  # noqa: S102


@pytest.mark.hermes
def test_us_1_3_plugin_api_loads_in_gateway_python(hermes_python: Path) -> None:
    """The gateway runs Python 3.11 with its own fastapi/httpx/pydantic (PC-4)."""
    script = (
        "import importlib.util, json, sys\n"
        f"spec = importlib.util.spec_from_file_location('hermes_dashboard_plugin_claimcoach', "
        f"{str(PLUGIN_DIR / 'dashboard' / 'plugin_api.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = mod\n"
        "spec.loader.exec_module(mod)\n"
        "print(json.dumps({'python': sys.version_info[:2], "
        "'routes': sorted(r.path for r in mod.router.routes)}))\n"
    )
    result = subprocess.run(
        [str(hermes_python), "-c", script], capture_output=True, text=True, check=True, timeout=60
    )
    payload = json.loads(result.stdout)
    assert payload["routes"] == sorted(GATEWAY_ROUTES)
    # Tripwire: if Hermes moves its gateway to a newer Python, revisit the 3.11 floor
    # (pyproject target-version / python_version, ADR-0001 Consequences).
    assert payload["python"] == [3, 11]


async def test_us_1_3_token_never_goes_through_an_http_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A proxy in the environment must not see the bearer token (or, later, PHI)."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "all_proxy"):
        monkeypatch.setenv(var, "http://127.0.0.1:9")  # discard port: any proxied call fails
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    config = WorkerConfig(data_dir=tmp_path, port=free_port_in_range(), python=python_for_worker())
    launcher.start_worker(config)
    try:
        client = WorkerClient(config.base_url, lambda: read_token(config.token_path))
        response = await desktop_get(gateway_app(client))
    finally:
        launcher.stop_worker(config)
    assert response.status_code == 200, response.text
