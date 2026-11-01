"""US-2.1 Model Role Registry in models.yaml.

Scenarios: every PRD role is registered; model directories resolve under MODELS_HOME; ports
outside the app range are rejected. Rules: BR-11, ES-1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from claimcoach.models import __main__ as models_cli
from claimcoach.models.registry import (
    DEFAULT_REGISTRY,
    REGISTRY_FILE,
    ModelRegistry,
    RegistryError,
    ensure_registry_file,
    load_registry,
    models_home,
)
from claimcoach.models.types import ModelRole
from tests.conftest import PLUGIN_DIR

PRD_ROLES = {
    "extraction",
    "phi_detection",
    "classification",
    "embedding",
    "rerank",
    "explanation",
    "drafting",
    "transcription",
}

Mutation = Callable[[dict[str, Any]], None]


def default_data() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(DEFAULT_REGISTRY.read_text())
    return data


def write_registry(tmp_path: Path, mutate: Mutation | None = None) -> Path:
    data = default_data()
    if mutate is not None:
        mutate(data)
    path = tmp_path / REGISTRY_FILE
    path.write_text(yaml.safe_dump(data))
    return path


def make_model(home: Path, model_dir: str) -> Path:
    path = home / model_dir
    path.mkdir(parents=True)
    (path / "config.json").write_text("{}")
    (path / "model.safetensors").write_bytes(b"weights")
    return path


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {
        str(p.relative_to(root)): (p.stat().st_ino, p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
    }


# --- Scenario: Every PRD role is registered ----------------------------------------------------


def test_us_2_1_every_role_registered() -> None:
    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    assert {role.value for role in registry.roles} == PRD_ROLES
    assert {role.value for role in ModelRole} == PRD_ROLES


def test_us_2_1_missing_role_rejected(tmp_path: Path) -> None:
    path = write_registry(tmp_path, lambda d: d["roles"].pop("drafting"))
    with pytest.raises(RegistryError, match=r"models\.yaml: roles: missing roles: drafting"):
        ModelRegistry.load(path)


def test_us_2_1_shared_server_roles() -> None:
    servers = ModelRegistry.load(DEFAULT_REGISTRY).servers()
    assert servers[18202] == [ModelRole.PHI_DETECTION, ModelRole.CLASSIFICATION]
    assert all(len(roles) == 1 for port, roles in servers.items() if port != 18202)


# --- Scenario: Model directories resolve under MODELS_HOME -------------------------------------


def test_us_2_1_paths_resolve_under_models_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "Models"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("MODELS_HOME", str(home))
    registry = load_registry(data_dir)
    make_model(home, registry.roles[ModelRole.DRAFTING].model_dir)
    (home / ".venvs" / "mtplx" / "bin").mkdir(parents=True)
    (home / ".venvs" / "mtplx" / "bin" / "python").write_text("")
    before = snapshot(home)

    resolved = models_home()
    for spec in registry.roles.values():
        path = spec.model_path(resolved)
        assert path.is_relative_to(home)
        if "{model}" in spec.command:  # mlx_audio.server takes it per request (US-11.1)
            assert str(path) in spec.argv(resolved, "127.0.0.1")
        spec.weights(resolved)
        spec.source_present(resolved)
        spec.venv_present(resolved)

    assert snapshot(home) == before  # nothing copied, moved, or created under MODELS_HOME
    assert not list(data_dir.rglob("*.safetensors"))
    drafting = registry.roles[ModelRole.DRAFTING]
    assert drafting.weights(resolved) == "present"
    assert drafting.venv_present(resolved)
    assert registry.roles[ModelRole.EXPLANATION].weights(resolved) == "missing"
    assert not registry.roles[ModelRole.EXPLANATION].venv_present(resolved)


def test_us_2_1_argv_fills_placeholders() -> None:
    spec = ModelRegistry.load(DEFAULT_REGISTRY).roles[ModelRole.CLASSIFICATION]
    assert spec.argv(Path("/m"), "127.0.0.1") == [
        "/m/.venvs/mlx-lm/bin/mlx_lm.server",
        "--model",
        "/m/Qwen3-8B-4bit",
        "--host",
        "127.0.0.1",
        "--port",
        "18202",
    ]


def test_us_2_1_presence_needs_config_and_weights(tmp_path: Path) -> None:
    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    rerank = registry.roles[ModelRole.RERANK]
    assert rerank.source_present(tmp_path) is False
    source = tmp_path / "Qwen3-Reranker-8B"
    source.mkdir()
    (source / "config.json").write_text("{}")
    assert rerank.source_present(tmp_path) is False  # an interrupted download has no weights
    (source / "model-00001-of-00002.safetensors").write_bytes(b"w")
    assert rerank.source_present(tmp_path) is True
    assert registry.roles[ModelRole.EXPLANATION].source_present(tmp_path) is None


@pytest.mark.parametrize(
    ("index", "shards", "expected"),
    [
        ({"weight_map": {"a": "m-1.safetensors", "b": "m-2.safetensors"}}, ["m-1"], "missing"),
        (
            {"weight_map": {"a": "m-1.safetensors", "b": "m-2.safetensors"}},
            ["m-1", "m-2"],
            "present",
        ),
        ({"weight_map": {}}, ["m-1"], "missing"),
        ({"metadata": {}}, ["m-1"], "missing"),
        ("not json", ["m-1"], "missing"),
    ],
    ids=["one-of-two-shards", "all-shards", "empty-index", "no-weight-map", "corrupt-index"],
)
def test_us_2_1_sharded_model_needs_every_shard(
    tmp_path: Path, index: object, shards: list[str], expected: str
) -> None:
    """``hf download`` lands config first and shards one by one; half a model is missing."""
    spec = ModelRegistry.load(DEFAULT_REGISTRY).roles[ModelRole.EXPLANATION]
    model = spec.model_path(tmp_path)
    model.mkdir()
    (model / "config.json").write_text("{}")
    text = index if isinstance(index, str) else json.dumps(index)
    (model / "model.safetensors.index.json").write_text(text)
    for shard in shards:
        (model / f"{shard}.safetensors").write_bytes(b"w")
    assert spec.weights(tmp_path) == expected


def test_us_2_1_models_home_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODELS_HOME", raising=False)
    assert models_home() == Path.home() / "Models"
    monkeypatch.setenv("MODELS_HOME", "~/elsewhere")
    assert models_home() == Path.home() / "elsewhere"


@pytest.mark.parametrize("model_dir", ["/abs/Qwen3-14B-4bit", "../Qwen3-14B-4bit", "~/x", "a/../b"])
def test_us_2_1_escaping_paths_rejected(tmp_path: Path, model_dir: str) -> None:
    path = write_registry(tmp_path, lambda d: d["roles"]["explanation"].update(model_dir=model_dir))
    with pytest.raises(RegistryError, match=r"roles\.explanation\.model_dir: must be a relative"):
        ModelRegistry.load(path)


def test_us_2_1_escaping_source_dir_rejected(tmp_path: Path) -> None:
    path = write_registry(
        tmp_path, lambda d: d["roles"]["rerank"]["convert"].update(source_dir="../src")
    )
    with pytest.raises(RegistryError, match=r"roles\.rerank\.convert\.source_dir"):
        ModelRegistry.load(path)


# --- Scenario: Ports outside the app range are rejected ----------------------------------------


def test_us_2_1_ports_outside_range_rejected(tmp_path: Path) -> None:
    path = write_registry(tmp_path, lambda d: d["roles"]["classification"].update(port=18300))
    with pytest.raises(RegistryError) as raised:
        ModelRegistry.load(path)
    message = str(raised.value)
    assert "roles.classification.port" in message
    assert "port 18300 is outside the allowed range 18200-18219" in message


def test_us_2_1_worker_port_reserved(tmp_path: Path) -> None:
    path = write_registry(tmp_path, lambda d: d["roles"]["extraction"].update(port=18200))
    with pytest.raises(RegistryError, match="port 18200 is reserved for the ClaimCoach worker"):
        ModelRegistry.load(path)


def test_us_2_1_conflicting_shared_port_rejected(tmp_path: Path) -> None:
    path = write_registry(tmp_path, lambda d: d["roles"]["explanation"].update(port=18201))
    with pytest.raises(RegistryError, match="share port 18201 but describe different") as raised:
        ModelRegistry.load(path)
    assert "extraction" in str(raised.value)
    assert "explanation" in str(raised.value)


# --- Commands, sources, and file errors --------------------------------------------------------


def _set_command(command: list[str]) -> Mutation:
    return lambda d: d["roles"]["drafting"].update(command=command)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_set_command(["{venv}/bin/mtplx", "--port", "{port}"]), r"placeholder\(s\) \['host'\]"),
        (_set_command(["x", "{host}", "{port}", "{home}"]), r"unknown placeholder\(s\) \['home'\]"),
        (_set_command([]), r"roles\.drafting\.command"),
        (lambda d: d["roles"]["drafting"].pop("repo_id"), "set exactly one of repo_id or convert"),
        (
            lambda d: d["roles"]["rerank"].update(repo_id="Qwen/Qwen3-Reranker-8B"),
            "set exactly one of repo_id or convert",
        ),
        (lambda d: d["roles"]["drafting"].update(venv="../x"), r"roles\.drafting\.venv"),
        (lambda d: d["roles"]["drafting"].update(gpu=True), r"roles\.drafting\.gpu"),
        (lambda d: d["roles"].update(chat=d["roles"]["drafting"]), r"roles\.chat"),
        (
            lambda d: d["acquire"].update(download=["hf", "download", "{repo_id}"]),
            r"acquire\.download: must contain the placeholder\(s\) \['target'\]",
        ),
        (
            lambda d: d["acquire"].update(convert=["convert", "{target}", "{url}"]),
            r"acquire\.convert: unknown placeholder",
        ),
        (lambda d: d.update(version=2), r"models\.yaml: version"),
    ],
    ids=[
        "command-without-host",
        "unknown-placeholder",
        "empty-command",
        "neither-repo-nor-convert",
        "both-repo-and-convert",
        "venv-escapes",
        "unknown-field",
        "unknown-role",
        "download-without-target",
        "convert-unknown-placeholder",
        "unknown-version",
    ],
)
def test_us_2_1_invalid_entries_named(tmp_path: Path, mutate: Mutation, expected: str) -> None:
    with pytest.raises(RegistryError, match=expected):
        ModelRegistry.load(write_registry(tmp_path, mutate))


def test_us_2_1_unreadable_or_malformed_file(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="cannot read the file"):
        ModelRegistry.load(tmp_path / "absent.yaml")
    bad = tmp_path / REGISTRY_FILE
    bad.write_text("roles: [unclosed")
    with pytest.raises(RegistryError, match="not valid YAML"):
        ModelRegistry.load(bad)
    bad.write_text("- just\n- a list\n")
    with pytest.raises(RegistryError, match=r"models\.yaml: <root>: "):
        ModelRegistry.load(bad)


# --- Default file written on first run ---------------------------------------------------------


def test_us_2_1_default_file_written_once(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    path = ensure_registry_file(data_dir)
    assert path == data_dir / REGISTRY_FILE
    assert path.read_bytes() == DEFAULT_REGISTRY.read_bytes()
    path.write_text(path.read_text().replace("idle_timeout_s: 600", "idle_timeout_s: 60"))
    edited = path.read_bytes()
    assert ensure_registry_file(data_dir) == path
    assert path.read_bytes() == edited
    assert ModelRegistry.load(path).idle_timeout_s == 60
    assert sorted(p.name for p in data_dir.iterdir()) == [REGISTRY_FILE]


def test_us_2_1_concurrent_first_run_keeps_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def lost_race(_src: Path, dst: Path) -> None:
        Path(dst).write_text("written by the other process")
        raise FileExistsError(dst)

    monkeypatch.setattr(os, "link", lost_race)
    path = ensure_registry_file(tmp_path)
    assert path.read_text() == "written by the other process"
    assert [p.name for p in tmp_path.iterdir()] == [REGISTRY_FILE]


# --- python -m claimcoach.models ---------------------------------------------------------------


def test_us_2_1_cli_init_and_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "Models"
    make_model(home, "Qwen3-14B-4bit")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("MODELS_HOME", str(home))

    assert models_cli.main(["init"]) == 0
    written = Path(capsys.readouterr().out.strip())
    assert written == tmp_path / "hermes" / "plugin-data" / "claimcoach" / REGISTRY_FILE

    assert models_cli.main(["check"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"MODELS_HOME={home}"
    assert len(lines) == 1 + len(ModelRole)
    explanation = next(line for line in lines if line.startswith("explanation"))
    assert "18205" in explanation
    assert "14B" in explanation
    assert "present" in explanation
    assert "no venv mlx-lm" in explanation


def test_us_2_1_cli_check_reports_invalid_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_registry(tmp_path, lambda d: d["roles"]["classification"].update(port=18300))
    assert models_cli.main(["check", "--data-dir", str(tmp_path), "--models-home", "/m"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("error: models.yaml: roles.classification.port: port 18300")


def test_us_2_1_cli_runs_as_module(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(PLUGIN_DIR), "MODELS_HOME": str(tmp_path / "Models")}
    result = subprocess.run(
        [sys.executable, "-m", "claimcoach.models", "check", "--data-dir", str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "drafting       18206  27B  missing" in result.stdout
    assert (tmp_path / REGISTRY_FILE).is_file()


def test_us_2_1_makefile_roles_match_the_enum() -> None:
    """``make models-load ROLE=…`` validates against this list before any shell runs."""
    makefile = (PLUGIN_DIR.parent / "Makefile").read_text()
    block = makefile.split("MODEL_ROLES := ", 1)[1].split("\nREQUIRE_ROLE", 1)[0]
    assert block.replace("\\", " ").split() == [role.value for role in ModelRole]
