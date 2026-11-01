"""US-14.2 Remove the Unread models_home Setting.

Scenarios: the setting is removed; a saved models_home does not reset the other settings. Rules:
ES-1 (the settings model and ``plugin.yaml`` stay one source of truth), BR-3, BR-11 (the weights
folder comes from ``MODELS_HOME``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import uvicorn
import yaml

from claimcoach.settings import RETIRED_SETTINGS, ClaimCoachSettings, load_settings
from claimcoach.worker import __main__ as worker_main
from tests.conftest import PLUGIN_DIR
from tests.test_us_10_2_local_only_indicator import stored


# --- Scenario: The setting is removed ---
def test_us_14_2_setting_removed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    schema = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8"))
    assert "models_home" not in schema["config_schema"]
    assert "models_home" not in ClaimCoachSettings.model_fields
    assert schema["config_schema"] == ClaimCoachSettings.config_schema()
    monkeypatch.setenv("MODELS_HOME", str(tmp_path / "Weights"))
    apps: list[Any] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **_: apps.append(app))
    assert worker_main.main(["--data-dir", str(tmp_path / "data"), "--port", "18201"]) == 0
    assert apps[0].state.models.models_home == tmp_path / "Weights", "the worker reads MODELS_HOME"


# --- Scenario: A saved models_home does not reset the other settings ---
def test_us_14_2_saved_models_home_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = {
        "models_home": "/Volumes/Models",
        "retention_days": 30,
        "richer_agent_access": True,
        "share_outcome_stats": True,
        "transcription_start_hour": 20,
        "transcription_end_hour": 6,
    }
    stored(monkeypatch, saved)
    settings = load_settings()
    assert settings == ClaimCoachSettings(
        retention_days=30,
        richer_agent_access=True,
        share_outcome_stats=True,
        transcription_start_hour=20,
        transcription_end_hour=6,
    )
    assert "models_home" in RETIRED_SETTINGS
    assert RETIRED_SETTINGS.isdisjoint(ClaimCoachSettings.model_fields), "never drop a live setting"


def test_us_14_2_other_unknown_settings_still_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the retired key is dropped; any other unknown key still fails closed (US-3.5)."""
    stored(monkeypatch, {"richer_agent_access": True, "cloud_upload": True})
    assert load_settings() == ClaimCoachSettings()
