"""US-10.2 Local-Only Statusbar Indicator (Python half).

Scenario: indicator shows local-only by default. The statusbar item and its typed state run under
``node --test`` (``plugin/desktop/tests/desktop_ui.test.mjs``); this module covers the gateway's
``GET /settings`` the item reads: richer access is off, and so the item local-only, unless the
profile stores an explicit ``true``.
Rules: ES-1, ES-4, ES-8, BR-14, PC-3.
"""

from __future__ import annotations

import sys
import types

import httpx
import pytest
from fastapi import FastAPI

from claimcoach.api import routes
from claimcoach.api.models import SettingsResponse
from tests.test_us_6_1_diagnosis import PREFIX


def stored(monkeypatch: pytest.MonkeyPatch, settings: object | None) -> None:
    """Hermes' config reader answering ``settings`` under the plugin's entry."""
    module = types.ModuleType("hermes_cli.config")
    config = {"plugins": {"entries": {"claimcoach": {"settings": settings}}}}
    module.load_config_readonly = lambda: config  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hermes_cli", types.ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.config", module)


async def read_settings() -> SettingsResponse:
    app = FastAPI()
    app.include_router(routes.router, prefix=PREFIX)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        response = await desktop.get(f"{PREFIX}/settings")
    assert response.status_code == 200, response.text
    return SettingsResponse.model_validate_json(response.content)


# --- Scenario: Indicator shows local-only by default ---------------------------------------------


@pytest.mark.parametrize(
    "settings",
    [None, {}, {"richer_agent_access": False}, {"richer_agent_access": "yes"}, {"bogus": 1}],
)
async def test_us_10_2_indicator_local_only_default(
    monkeypatch: pytest.MonkeyPatch, settings: object | None
) -> None:
    stored(monkeypatch, settings)
    answer = await read_settings()
    assert answer.richer_agent_access is False, "the item stays local-only"
    assert answer.retention_days == 90


async def test_us_10_2_only_an_explicit_true_changes_the_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored(monkeypatch, {"richer_agent_access": True})
    assert (await read_settings()).richer_agent_access is True
