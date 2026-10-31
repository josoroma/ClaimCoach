"""US-3.5: Richer agent access when the Hermes model is local (setting only).

Rules: BR-3, PC-5. SPECS.md leaves the scope of "richer access" open, so this story delivers the
setting (off by default), its manifest entry, the ``GET /settings`` route, and the statusbar
(``plugin/desktop/tests/statusbar.test.mjs``) — and proves the setting grants nothing yet.
"""

from __future__ import annotations

import os
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi import FastAPI

from claimcoach.api.models import SettingsResponse
from claimcoach.api.routes import router
from claimcoach.settings import ClaimCoachSettings, load_settings
from tests.conftest import HERMES_ROOT, PLUGIN_DIR, REPO_ROOT


def fake_hermes_config(monkeypatch: pytest.MonkeyPatch, config: object) -> None:
    module = types.ModuleType("hermes_cli.config")
    module.load_config_readonly = lambda: config  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_cli", types.ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.config", module)


async def get_settings() -> SettingsResponse:
    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/claimcoach")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        response = await client.get("/api/plugins/claimcoach/settings")
    assert response.status_code == 200
    return SettingsResponse.model_validate_json(response.content)


# --- Scenario: Richer access is off by default ---


async def test_us_3_5_richer_access_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text())
    assert manifest["config_schema"]["richer_agent_access"]["default"] is False
    assert ClaimCoachSettings().richer_agent_access is False
    assert load_settings().richer_agent_access is False  # outside the gateway: defaults
    fake_hermes_config(monkeypatch, {"plugins": {"enabled": ["claimcoach"]}})  # fresh install
    assert load_settings().richer_agent_access is False
    assert (await get_settings()).richer_agent_access is False


@pytest.mark.parametrize(
    "config",
    [
        None,
        {"plugins": "broken"},
        {"plugins": {"entries": {"claimcoach": {"settings": {"richer_agent_access": "maybe"}}}}},
        {"plugins": {"entries": {"claimcoach": {"settings": {"cloud_upload": True}}}}},
        {"plugins": {"entries": {"claimcoach": ["not", "a", "mapping"]}}},
        {"plugins": {"entries": {"claimcoach": {"settings": {"richer_agent_access": "yes"}}}}},
        {"plugins": {"entries": {"claimcoach": {"settings": {"richer_agent_access": 1}}}}},
        {"plugins": {"entries": {"claimcoach": {"settings": {"richer_agent_access": "true"}}}}},
    ],
)
def test_us_3_5_unreadable_settings_read_as_off(
    monkeypatch: pytest.MonkeyPatch, config: object
) -> None:
    fake_hermes_config(monkeypatch, config)
    assert load_settings() == ClaimCoachSettings()


async def test_us_3_5_settings_route_reports_the_stored_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: dict[str, Any] = {"richer_agent_access": True, "retention_days": 30}
    fake_hermes_config(monkeypatch, {"plugins": {"entries": {"claimcoach": {"settings": stored}}}})
    assert load_settings() == ClaimCoachSettings(richer_agent_access=True, retention_days=30)
    assert (await get_settings()).richer_agent_access is True


def test_us_3_5_setting_grants_nothing_yet() -> None:
    """Until SPECS.md US-3.5 is clarified, only display code may read the setting."""
    readers = sorted(
        str(path.relative_to(PLUGIN_DIR))
        for path in PLUGIN_DIR.rglob("*")
        if path.suffix in {".py", ".js"}
        and "__pycache__" not in path.parts
        and "tests" not in path.parts
        and "richer_agent_access" in path.read_text(encoding="utf-8")
    )
    assert readers == [
        "claimcoach/api/models.py",
        "claimcoach/api/routes.py",
        "claimcoach/settings.py",
        "desktop/plugin.js",
    ]


@pytest.mark.hermes
@pytest.mark.parametrize("stored", [None, True, False])
def test_us_3_5_real_hermes_config_is_read(
    hermes_python: Path, tmp_path: Path, stored: bool | None
) -> None:
    """``load_settings`` reads ``plugins.entries.claimcoach.settings`` through Hermes itself."""
    home = tmp_path / "hermes-home"
    home.mkdir()
    entry = {} if stored is None else {"claimcoach": {"settings": {"richer_agent_access": stored}}}
    (home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"entries": entry}}))
    env = {
        **os.environ,
        "HERMES_HOME": str(home),
        "PYTHONPATH": os.pathsep.join([str(PLUGIN_DIR), str(HERMES_ROOT)]),
    }
    code = (
        "from claimcoach.settings import load_settings; print(load_settings().richer_agent_access)"
    )
    result = subprocess.run(
        [str(hermes_python), "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    assert result.stdout.strip().splitlines()[-1] == str(stored is True)
