"""US-10.3 Settings Page for Models, Corpus, and Retention (Python half).

Scenarios: settings page registers when supported; settings degrade when unsupported (both under
``node --test``, ``plugin/desktop/tests/desktop_ui.test.mjs``); retention setting is saved (here:
``POST /settings/retention`` through Hermes' plugin-settings writer, read back by the worker's
retention reader; the real writer runs in Hermes' own Python under the ``hermes`` marker). Also:
the refusals, ``GET /settings``, and the profile-filtered ``GET /corpus/status``.
Rules: ES-1, ES-4, ES-8, BR-7, BR-13, BR-14, PC-3, PC-5.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import types
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi import FastAPI

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.api.models import SettingsResponse
from claimcoach.corpus.crypto import InMemoryKeyProvider, key_account
from claimcoach.corpus.retention import RetentionPolicy
from claimcoach.corpus.types import CorpusScope, CorpusStatusResponse, ScopeStatus
from claimcoach.settings import PLUGIN_DIR, load_retention_days
from tests.conftest import HERMES_ROOT
from tests.conftest import PLUGIN_DIR as REPO_PLUGIN_DIR
from tests.fakes.corpus import make_service
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_6_1_diagnosis import PREFIX, assert_envelope

Saver = Callable[[str, Path, dict[str, Any]], list[str]]


def config_of(home: Path) -> dict[str, Any]:
    path = home / "config.yaml"
    loaded = yaml.safe_load(path.read_text()) if path.exists() else None
    return loaded if isinstance(loaded, dict) else {}


def fake_hermes(
    monkeypatch: pytest.MonkeyPatch, home: Path, saver: Saver | None = None
) -> list[Any]:
    """Hermes' config reader and plugin-settings writer over ``home/config.yaml``."""
    calls: list[Any] = []

    def save(plugin_id: str, plugin_dir: Path, values: dict[str, Any]) -> list[str]:
        calls.append((plugin_id, plugin_dir, values))
        config = config_of(home)
        entry = config.setdefault("plugins", {}).setdefault("entries", {}).setdefault(plugin_id, {})
        entry.setdefault("settings", {}).update(values)
        (home / "config.yaml").write_text(yaml.safe_dump(config))
        return list(values)

    package = types.ModuleType("hermes_cli")
    reader = types.ModuleType("hermes_cli.config")
    reader.load_config_readonly = lambda: config_of(home)  # type: ignore[attr-defined]
    writer = types.ModuleType("hermes_cli.plugins_settings")
    writer.save_plugin_settings = saver or save  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_cli", package)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", reader)
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins_settings", writer)
    return calls


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def gateway(client: WorkerClient | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    if client is not None:
        app.dependency_overrides[routes.get_worker_client] = lambda: client
    return app


@pytest.fixture
async def desktop() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=gateway())
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        yield desktop


async def save(desktop: httpx.AsyncClient, body: object) -> httpx.Response:
    return await desktop.post(f"{PREFIX}/settings/retention", json=body)


# --- Scenario: Retention setting is saved --------------------------------------------------------


async def test_us_10_3_retention_saved(
    desktop: httpx.AsyncClient, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_hermes(monkeypatch, home)
    assert load_retention_days(home) == 90

    response = await save(desktop, {"retention_days": 30})

    assert response.status_code == 200, response.text
    answer = SettingsResponse.model_validate_json(response.content)
    assert (answer.retention_days, answer.richer_agent_access) == (30, False)
    assert calls == [("claimcoach", PLUGIN_DIR, {"retention_days": 30})]
    assert REPO_PLUGIN_DIR.resolve() == PLUGIN_DIR, "Hermes checks the save against plugin.yaml"
    # The worker reads the profile's config.yaml on each purge run (US-4.5).
    assert load_retention_days(home) == 30
    policy = RetentionPolicy.for_profile(home)
    assert policy is not None
    assert policy.days == 30
    shown = await desktop.get(f"{PREFIX}/settings")
    assert SettingsResponse.model_validate_json(shown.content).retention_days == 30


# --- Scenario: Retention cannot be saved ---------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"retention_days": 0},
        {"retention_days": 3651},
        {"retention_days": "30"},
        {"retention_days": True},
        {"retention_days": 30.5},
        {"retention_days": 30, "richer_agent_access": True},
        {},
        [30],
    ],
)
async def test_us_10_3_retention_refusals(
    desktop: httpx.AsyncClient, home: Path, monkeypatch: pytest.MonkeyPatch, body: object
) -> None:
    calls = fake_hermes(monkeypatch, home)
    assert_envelope(await save(desktop, body), 422, "invalid_request")
    assert calls == []
    assert not (home / "config.yaml").exists()


async def test_us_10_3_retention_needs_json(
    desktop: httpx.AsyncClient, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_hermes(monkeypatch, home)
    form = await desktop.post(f"{PREFIX}/settings/retention", data={"retention_days": "30"})
    assert_envelope(form, 422, "invalid_request")
    big = await desktop.post(
        f"{PREFIX}/settings/retention",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": str(2**30)},
    )
    assert_envelope(big, 413, "document_too_large")
    assert calls == []


def refusing(error: Exception) -> Saver:
    def save(_plugin_id: str, _plugin_dir: Path, _values: dict[str, Any]) -> list[str]:
        raise error

    return save


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (PermissionError("Plugin setting 'x' is administrator-managed"), 403, "settings_managed"),
        (ValueError("'retention_days' should be number"), 503, "settings_unavailable"),
    ],
)
async def test_us_10_3_hermes_refuses_the_save(  # noqa: PLR0917 - fixtures and parameters
    desktop: httpx.AsyncClient,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    status: int,
    code: str,
) -> None:
    fake_hermes(monkeypatch, home, refusing(error))
    response = await save(desktop, {"retention_days": 30})
    assert_envelope(response, status, code)
    assert "administrator-managed" not in response.text
    assert "should be number" not in caplog.text, "Hermes' message is never logged"


async def test_us_10_3_outside_hermes_nothing_is_saved(
    desktop: httpx.AsyncClient, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins_settings", None)  # import fails
    assert_envelope(await save(desktop, {"retention_days": 30}), 503, "settings_unavailable")
    assert not (home / "config.yaml").exists()


# --- Corpus status shows this profile only -------------------------------------------------------


def scope(scope_kind: CorpusScope, profile: str | None, cases: int) -> ScopeStatus:
    return ScopeStatus(
        scope=scope_kind,
        profile=profile,
        path=f"/hermes/{profile or 'global'}",
        encrypted=scope_kind is CorpusScope.USER,
        cases=cases,
    )


async def test_us_10_3_corpus_status_shows_this_profile_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profiles" / "biller-b"))
    status = CorpusStatusResponse(
        global_scope=scope(CorpusScope.GLOBAL, None, 0),
        user_scopes=[
            scope(CorpusScope.USER, "default", 7),
            scope(CorpusScope.USER, "biller-b", 2),
        ],
    )

    def worker(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/corpus/status"
        return httpx.Response(200, content=status.model_dump_json())

    client = WorkerClient("http://worker", lambda: "t", transport=httpx.MockTransport(worker))
    transport = httpx.ASGITransport(app=gateway(client))
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        response = await desktop.get(f"{PREFIX}/corpus/status")
    assert response.status_code == 200, response.text
    answer = CorpusStatusResponse.model_validate_json(response.content)
    assert [s.profile for s in answer.user_scopes] == ["biller-b"]
    assert answer.global_scope == status.global_scope
    assert "/hermes/default" not in response.text


async def test_us_10_3_corpus_status_when_the_worker_is_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    transport = httpx.ASGITransport(app=gateway(WorkerClient("http://worker", lambda: None)))
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        assert_envelope(await desktop.get(f"{PREFIX}/corpus/status"), 503, "worker_unavailable")


# --- The real Hermes writer, in the gateway's Python ---------------------------------------------


@pytest.mark.hermes
def test_us_10_3_retention_saved_with_hermes(hermes_python: Path, tmp_path: Path) -> None:
    """The gateway route saves through Hermes' own writer; the worker's reader sees it."""
    home = tmp_path / "hermes-home"
    home.mkdir()
    script = (
        "import importlib.util, json, sys\n"
        "from pathlib import Path\n"
        "from fastapi import FastAPI\n"
        "from fastapi.testclient import TestClient\n"
        f"spec = importlib.util.spec_from_file_location('hermes_dashboard_plugin_claimcoach', "
        f"{str(REPO_PLUGIN_DIR / 'dashboard' / 'plugin_api.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = mod\n"
        "spec.loader.exec_module(mod)\n"
        "from claimcoach.settings import load_retention_days\n"
        "app = FastAPI()\n"
        "app.include_router(mod.router, prefix='/p')\n"
        "client = TestClient(app)\n"
        "saved = client.post('/p/settings/retention', json={'retention_days': 30})\n"
        "refused = client.post('/p/settings/retention', json={'retention_days': 0})\n"
        "home = Path(sys.argv[1])\n"
        "print(json.dumps({'saved': [saved.status_code, saved.json()],\n"
        "                  'refused': refused.status_code,\n"
        "                  'worker_reads': load_retention_days(home)}))\n"
    )
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONPATH": str(HERMES_ROOT)}
    result = subprocess.run(
        [str(hermes_python), "-c", script, str(home)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["saved"][0] == 200, payload
    assert payload["saved"][1]["retention_days"] == 30
    assert payload["refused"] == 422
    assert payload["worker_reads"] == 30
    stored = yaml.safe_load((home / "config.yaml").read_text())
    assert stored["plugins"]["entries"]["claimcoach"]["settings"]["retention_days"] == 30


# --- Review regressions --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "shown"),
    [
        ({"retention_days": 30, "transcription_start_hour": 30}, 30),
        ({"retention_days": 5000}, None),
        ({"retention_days": "30"}, 30),
        ({}, 90),
    ],
)
async def test_us_10_3_page_shows_the_period_the_purge_uses(
    desktop: httpx.AsyncClient,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    settings: dict[str, Any],
    shown: int | None,
) -> None:
    """Review: another invalid key made the page show 90 while the worker purged at 30."""
    fake_hermes(monkeypatch, home)
    config = {"plugins": {"entries": {"claimcoach": {"settings": settings}}}}
    (home / "config.yaml").write_text(yaml.safe_dump(config))
    answer = SettingsResponse.model_validate_json((await desktop.get(f"{PREFIX}/settings")).content)
    assert answer.retention_days == shown
    assert load_retention_days(home) == shown, "the worker's purge reads the same value"


async def test_us_10_3_outside_hermes_the_default_period_is_shown(
    desktop: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "hermes_cli.config", None)
    answer = SettingsResponse.model_validate_json((await desktop.get(f"{PREFIX}/settings")).content)
    assert answer.retention_days == 90


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("could not parse config.yaml: api_key: sk-SECRET123"),
        OSError(28, "No space left on device: sk-SECRET123"),
        PermissionError(13, "Permission denied: sk-SECRET123"),
    ],
)
async def test_us_10_3_a_failed_save_is_an_envelope_without_its_text(
    desktop: httpx.AsyncClient,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    """Review: a malformed config made the route a raw 500 quoting config lines."""
    fake_hermes(monkeypatch, home, refusing(error))
    response = await save(desktop, {"retention_days": 30})
    assert_envelope(response, 503, "settings_unavailable")
    assert "SECRET" not in response.text
    assert "SECRET" not in caplog.text
    assert type(error).__name__ in caplog.text


async def test_us_10_3_a_save_stuck_on_the_config_lock_times_out(
    desktop: httpx.AsyncClient, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()

    def stuck(_plugin_id: str, _plugin_dir: Path, _values: dict[str, Any]) -> list[str]:
        release.wait(5)
        return []

    fake_hermes(monkeypatch, home, stuck)
    monkeypatch.setattr(routes, "SAVE_TIMEOUT", 0.05)
    try:
        assert_envelope(await save(desktop, {"retention_days": 30}), 503, "settings_unavailable")
    finally:
        release.set()


def test_us_10_3_worker_reports_only_the_asked_profile(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    """Review: the gateway filtered after the worker had read every profile's key."""

    class Recording(InMemoryKeyProvider):
        def __init__(self) -> None:
            super().__init__()
            self.asked: list[str] = []

        def key_for(self, account: str, *, create: bool) -> bytes:
            self.asked.append(account)
            return super().key_for(account, create=create)

    keys = Recording()
    first = make_service(tmp_path / "hermes", corpus_server, keys=keys)
    first.user_store("default", create=True)
    first.user_store("biller-b", create=True)
    first.close()
    keys.asked.clear()
    service = make_service(tmp_path / "hermes", corpus_server, keys=keys)
    try:
        status = service.status("biller-b")
        assert [scope.profile for scope in status.user_scopes] == ["biller-b"]
        assert keys.asked == [key_account("biller-b")], "no other profile's key was read"
        assert len(service.status().user_scopes) == 2
    finally:
        service.close()


@pytest.mark.hermes
def test_us_10_3_malformed_config_with_hermes(hermes_python: Path, tmp_path: Path) -> None:
    """Review: the real writer's parser error becomes the envelope, without the config's text."""
    home = tmp_path / "hermes-home"
    home.mkdir()
    (home / "config.yaml").write_text("model: [unclosed\napi_key: sk-SECRET123\n")
    script = (
        "import importlib.util, json, sys\n"
        "from fastapi import FastAPI\n"
        "from fastapi.testclient import TestClient\n"
        f"spec = importlib.util.spec_from_file_location('hermes_dashboard_plugin_claimcoach', "
        f"{str(REPO_PLUGIN_DIR / 'dashboard' / 'plugin_api.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = mod\n"
        "spec.loader.exec_module(mod)\n"
        "app = FastAPI()\n"
        "app.include_router(mod.router, prefix='/p')\n"
        "answer = TestClient(app).post('/p/settings/retention', json={'retention_days': 30})\n"
        "print(json.dumps({'status': answer.status_code, 'body': answer.text}))\n"
    )
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONPATH": str(HERMES_ROOT)}
    result = subprocess.run(
        [str(hermes_python), "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == 503, payload
    assert '"settings_unavailable"' in payload["body"]
    assert "SECRET" not in result.stdout + result.stderr
    assert "sk-SECRET123" in (home / "config.yaml").read_text(), "the config is left as it was"
