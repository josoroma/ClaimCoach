"""US-14.1 Remove Unused Retrieval and the Reranker.

Scenarios: the reranker is not a model role; an existing models.yaml still loads; no conversion
route or command remains; the corpus index is kept. Rules: BR-1 (the only remaining model fetch
is a confirmed download), BR-5 (the index search still filters by case), BR-11.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.routing import APIRoute

from claimcoach.api.models import ERROR_MESSAGES
from claimcoach.api.routes import router as gateway
from claimcoach.corpus.bundle import CorpusBundle
from claimcoach.corpus.errors import CorpusError
from claimcoach.models.acquire import Acquirer
from claimcoach.models.manager import ModelManager
from claimcoach.models.registry import (
    DEFAULT_REGISTRY,
    REGISTRY_FILE,
    ModelRegistry,
    RegistryError,
    load_registry,
)
from claimcoach.models.types import ModelRole, ModelStatus
from claimcoach.worker import model_routes
from tests.conftest import REPO_ROOT
from tests.doc_checks import make_targets
from tests.fakes.corpus import MODEL_ID, make_service, vectors_for
from tests.fakes.fake_model_server import FakeModelServer

RETIRED_ROLE: dict[str, Any] = {
    "convert": {
        "source_repo_id": "Qwen/Qwen3-Reranker-8B",
        "source_dir": "Qwen3-Reranker-8B",
        "q_bits": 4,
    },
    "model_dir": "Qwen3-Reranker-8B-MLX-4bit",
    "venv": "mlx-lm",
    "command": [
        "{venv}/bin/mlx_lm.server",
        "--model",
        "{model}",
        "--host",
        "{host}",
        "--port",
        "{port}",
    ],
    "port": 18204,
    "tier_b": 8,
}
"""The ``rerank`` role exactly as every ``models.yaml`` before US-14.1 declared it."""
RETIRED_CONVERT = [
    "{models_home}/.venvs/mlx-lm/bin/mlx_lm.convert",
    "--hf-path",
    "{source}",
    "--mlx-path",
    "{target}",
    "-q",
    "--q-bits",
    "{q_bits}",
]


def _old_registry(data_dir: Path) -> Path:
    """Write a pre-US-14.1 ``models.yaml``: today's default plus the retired role and command."""
    data = yaml.safe_load(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    data["roles"]["rerank"] = RETIRED_ROLE
    data["acquire"]["convert"] = RETIRED_CONVERT
    data_dir.mkdir(parents=True)
    path = data_dir / REGISTRY_FILE
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


# --- Scenario: The reranker is not a model role ---
def test_us_14_1_no_rerank_role(tmp_path: Path) -> None:
    assert "rerank" not in {role.value for role in ModelRole}
    default = yaml.safe_load(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    assert "rerank" not in default["roles"]
    assert set(default["acquire"]) == {"download"}, "no conversion recipe"
    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    manager = ModelManager(registry, models_home=tmp_path / "Models", state_dir=tmp_path / "s")
    listed = {status.role.value for status in manager.status().models}
    assert listed == {role.value for role in ModelRole}
    assert "rerank" not in listed
    assert "source_present" not in ModelStatus.model_fields


# --- Scenario: An existing models.yaml still loads ---
def test_us_14_1_old_registry_still_loads(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    path = _old_registry(data_dir)
    before = path.read_bytes()
    registry = load_registry(data_dir)
    assert registry.roles == ModelRegistry.load(DEFAULT_REGISTRY).roles, "every other role as is"
    assert registry.acquire == ModelRegistry.load(DEFAULT_REGISTRY).acquire
    assert path.read_bytes() == before, "the file is not rewritten"


@pytest.mark.parametrize(
    ("section", "key"),
    [("roles", "reranker"), ("acquire", "convert_all")],
)
def test_us_14_1_only_the_retired_keys_are_dropped(tmp_path: Path, section: str, key: str) -> None:
    path = _old_registry(tmp_path / "data")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data[section][key] = RETIRED_ROLE if section == "roles" else RETIRED_CONVERT
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(RegistryError, match=rf"{section}\.{key}"):
        ModelRegistry.load(path)


def test_us_14_1_a_non_mapping_registry_is_still_refused(tmp_path: Path) -> None:
    path = tmp_path / REGISTRY_FILE
    for text in ("- a list\n", "roles: [rerank]\nacquire: convert\n"):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(RegistryError):
            ModelRegistry.load(path)


# --- Scenario: No conversion route or command remains ---
def test_us_14_1_no_conversion_route_or_target() -> None:
    gateway_paths = {route.path for route in gateway.routes if isinstance(route, APIRoute)}
    worker_paths = {
        route.path for route in model_routes.router.routes if isinstance(route, APIRoute)
    }
    for paths in (gateway_paths, worker_paths):
        assert "/models/download" in paths
        assert not [path for path in paths if "convert" in path]
    targets = make_targets(REPO_ROOT / "Makefile")
    assert "models-download" in targets
    assert "models-convert" not in targets
    assert "rerank" not in (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "conversion_unavailable" not in ERROR_MESSAGES
    assert not hasattr(Acquirer, "convert")


# --- Scenario: The corpus index is kept ---
async def test_us_14_1_index_kept(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    service = make_service(tmp_path, corpus_server)
    card = {
        "kind": "code",
        "code_set": "CARC",
        "code": "197",
        "title": "Precertification absent",
        "body": "Precertification, authorization, or notification absent.",
        "source": "X12 CARC list",
        "verified_on": "2026-09-01",
    }
    corpus_server.embedding_requests.clear()
    result = await service.import_bundle(CorpusBundle.model_validate({"items": [card]}))
    text = f"{card['title']}\n{card['body']}"
    assert [r.input for r in corpus_server.embedding_requests] == [[text]], "import embeds"
    assert result.chunks >= 1
    index = service.global_store().index_info()
    assert index.embedding_model_id == MODEL_ID
    assert index.vectors == result.chunks
    hits = service.global_store().search(vectors_for([text])[0], 1)
    assert hits[0][0].startswith("code:CARC/197")
    assert hits[0][1] == pytest.approx(1.0), "the stored vector is the chunk's own embedding"
    user = service.user_store("default", create=True)
    user.create_case("case-a")
    with pytest.raises(CorpusError):
        user.search(vectors_for(["x"])[0], 5)
    assert user.search(vectors_for(["x"])[0], 5, case_id="case-a") == []
