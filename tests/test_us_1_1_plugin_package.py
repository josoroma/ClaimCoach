"""US-1.1 Plugin Package Scaffold and Manifest.

Scenarios: manifest declares the v2 fields; backend manifest points at plugin_api.py; Python half
stays inert until enabled; Python half loads once enabled. Rules: PC-1, PC-2, PC-5, PC-8, ES-1.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from claimcoach.agent.tools import TOOLS, CaseSummaryParams, register_tools
from claimcoach.api.models import ERROR_MESSAGES
from claimcoach.settings import ClaimCoachSettings
from tests.conftest import HERMES_BIN, HERMES_ROOT, PLUGIN_DIR, REPO_ROOT
from tests.fakes.registrar import FakeRegistrar


def manifest() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text())
    return data


def load_agent_half() -> ModuleType:
    """Import ``plugin/__init__.py`` exactly as Hermes' directory loader does."""
    name = "hermes_plugins.claimcoach_test"
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[name]
    return module


# --- Scenario: Manifest declares the required v2 fields ----------------------------------------


def test_us_1_1_manifest_declares_v2_fields() -> None:
    data = manifest()
    assert data["name"] == "claimcoach"
    assert data["manifest_version"] == 2
    assert data["requires_hermes"] == ">=0.22.5"
    assert data["python_runtime"] == "external"
    assert data["provides_tools"] == [tool.name for tool in TOOLS]
    assert set(data["config_schema"]) == set(ClaimCoachSettings.model_fields)


@pytest.mark.hermes
def test_us_1_1_hermes_validate_accepts_package() -> None:
    if HERMES_BIN is None:
        pytest.skip("hermes CLI not on PATH")
    result = subprocess.run(
        [HERMES_BIN, "plugins", "validate", "--json", str(PLUGIN_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    report = json.loads(result.stdout)
    failed = [c for c in report["checks"] if not c["ok"]]
    assert result.returncode == 0, failed
    assert report["ok"] is True
    assert {c["name"] for c in report["checks"]} >= {"manifest", "config schema", "declared tools"}


def test_us_1_1_config_schema_matches_settings() -> None:
    assert manifest()["config_schema"] == ClaimCoachSettings.config_schema()
    defaults = {k: v["default"] for k, v in ClaimCoachSettings.config_schema().items()}
    assert ClaimCoachSettings.model_validate(defaults) == ClaimCoachSettings()


@pytest.mark.parametrize(
    "override",
    [{"retention_days": 0}, {"retention_days": 3651}, {"models_home": ""}],
)
def test_us_1_1_settings_reject_invalid_values(override: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ClaimCoachSettings.model_validate(override)


def test_us_1_1_settings_reject_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        ClaimCoachSettings.model_validate({"cloud_upload": True})


# --- Scenario: Backend manifest points at plugin_api.py ----------------------------------------


def test_us_1_1_backend_manifest_points_at_plugin_api() -> None:
    backend = json.loads((PLUGIN_DIR / "dashboard" / "manifest.json").read_text())
    assert backend["name"] == "claimcoach"
    assert backend["api"] == "plugin_api.py"
    assert (PLUGIN_DIR / "dashboard" / backend["api"]).is_file()


def test_us_1_1_package_tree_matches_prd() -> None:
    for relative in (
        "plugin.yaml",
        "__init__.py",
        "skills/denial-triage/SKILL.md",
        "dashboard/manifest.json",
        "dashboard/plugin_api.py",
        "desktop/plugin.js",
        "claimcoach/__init__.py",
    ):
        assert (PLUGIN_DIR / relative).is_file(), relative


# --- Scenarios: Python half inert until enabled / loads once enabled ---------------------------


def probe_hermes(hermes_python: Path, tmp_path: Path, *, enabled: bool) -> dict[str, Any]:
    """Discover plugins with the real Hermes loader in a throwaway ``HERMES_HOME``."""
    home = tmp_path / "hermes-home"
    (home / "plugins").mkdir(parents=True)
    (home / "plugins" / "claimcoach").symlink_to(PLUGIN_DIR, target_is_directory=True)
    config = {"plugins": {"enabled": ["claimcoach"] if enabled else []}}
    (home / "config.yaml").write_text(yaml.safe_dump(config))
    env = {**os.environ, "HERMES_HOME": str(home), "PYTHONPATH": str(HERMES_ROOT)}
    result = subprocess.run(
        [str(hermes_python), str(REPO_ROOT / "tests/hermes/probe_plugins.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    payload: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return payload


@pytest.mark.hermes
def test_us_1_1_python_half_inert_until_enabled(hermes_python: Path, tmp_path: Path) -> None:
    result = probe_hermes(hermes_python, tmp_path, enabled=False)
    assert result["tools"] == []
    assert (result["skills"], result["commands"]) == ([], [])
    assert result["claimcoach"]["enabled"] is False


@pytest.mark.hermes
def test_us_1_1_python_half_loads_once_enabled(hermes_python: Path, tmp_path: Path) -> None:
    result = probe_hermes(hermes_python, tmp_path, enabled=True)
    assert result["tools"] == sorted(manifest()["provides_tools"])
    # US-9.3, US-9.4: the playbook skill and the /denial command register with the tools.
    assert (result["skills"], result["commands"]) == (["claimcoach:denial-triage"], ["denial"])
    assert result["claimcoach"]["enabled"] is True
    assert result["claimcoach"]["error"] is None


def test_us_1_1_agent_half_registers_provided_tools() -> None:
    registrar = FakeRegistrar()
    load_agent_half().register(registrar)
    assert list(registrar.tools) == manifest()["provides_tools"]
    for name, call in registrar.tools.items():
        assert call["toolset"] == "claimcoach"
        assert call["schema"]["name"] == name
        assert call["schema"]["parameters"]["additionalProperties"] is False


# --- Tools answer with a JSON string, never an exception (PC-8, BR-3) ------------------------


def test_us_1_1_tools_answer_an_envelope_without_a_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no worker token (no worker ever started), every tool answers ``worker_unavailable``.

    US-9.1 and US-9.2 replaced the placeholder ``not_implemented`` answer with worker calls.
    """
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    registrar = FakeRegistrar()
    names = register_tools(registrar)
    args = {
        "claimcoach_explain_code": {"code": "CO-197"},
        "claimcoach_payer_rules": {"payer": "Acme Health"},
        "claimcoach_case_summary": {"case_id": "case_01"},
    }
    for name in names:
        raw = registrar.tools[name]["handler"](args[name], task_id="t1")
        assert isinstance(raw, str), "PC-8: handlers return a JSON string"
        assert json.loads(raw) == {
            "ok": False,
            "error": {
                "code": "worker_unavailable",
                "message": ERROR_MESSAGES["worker_unavailable"],
            },
        }


def test_us_1_1_tools_reject_bad_arguments_without_echoing_them() -> None:
    tool = next(t for t in TOOLS if t.params is CaseSummaryParams)
    raw = tool.handle({"case_id": "Jane Doe DOB 1970-01-01", "extra": 1})
    body = json.loads(raw)
    assert body["error"]["code"] == "invalid_request"
    assert "Jane" not in raw


# --- Bootstrap (PC-2) --------------------------------------------------------------------------


def load_bootstrap() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "bootstrap_under_test", PLUGIN_DIR / "_bootstrap.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_us_1_1_bootstrap_reuses_loaded_package() -> None:
    import claimcoach  # noqa: PLC0415

    load_bootstrap().ensure_app_package()
    assert sys.modules["claimcoach"] is claimcoach


def test_us_1_1_bootstrap_loads_package_by_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "claimcoach")
    load_bootstrap().ensure_app_package()
    loaded = sys.modules["claimcoach"]
    assert Path(str(loaded.__file__)) == PLUGIN_DIR / "claimcoach" / "__init__.py"
    assert loaded.PLUGIN_NAME == "claimcoach"


def test_us_1_1_bootstrap_refuses_foreign_package(monkeypatch: pytest.MonkeyPatch) -> None:
    foreign = ModuleType("claimcoach")
    foreign.__file__ = "/elsewhere/claimcoach/__init__.py"
    monkeypatch.setitem(sys.modules, "claimcoach", foreign)
    with pytest.raises(ImportError, match="already imported"):
        load_bootstrap().ensure_app_package()


def test_us_1_1_bootstrap_cleans_up_failed_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "claimcoach"
    broken.mkdir()
    (broken / "__init__.py").write_text("raise RuntimeError('broken package')\n")
    monkeypatch.delitem(sys.modules, "claimcoach")
    with pytest.raises(RuntimeError, match="broken package"):
        load_bootstrap().ensure_app_package(broken)
    assert "claimcoach" not in sys.modules


def test_us_1_1_bootstrap_reports_unloadable_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap = load_bootstrap()
    monkeypatch.delitem(sys.modules, "claimcoach")
    monkeypatch.setattr(bootstrap.importlib.util, "spec_from_file_location", lambda *_a, **_k: None)
    with pytest.raises(ImportError, match="cannot load"):
        bootstrap.ensure_app_package()
