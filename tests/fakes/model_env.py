"""A throwaway ``MODELS_HOME`` and ``models.yaml`` whose servers are fake-model-server processes.

Implements: US-2.2 to US-2.4 test harness (ES-4: offline, real loopback sockets, real processes).
Every role gets a model dir with ``config.json`` and a weights file, and a command that runs
``python -m tests.fakes.fake_model_server`` on a free port inside 18201-18219.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from claimcoach.models.manager import ModelManager
from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry
from claimcoach.models.types import ModelRole
from tests.conftest import free_port_in_range

__all__ = ["ModelEnv", "build_model_env", "fake_server_command"]


def fake_server_command(*extra: str) -> list[str]:
    """Server argv template running the fake model server (``{host}``/``{port}`` filled later)."""
    return [
        sys.executable,
        "-m",
        "tests.fakes.fake_model_server",
        "--host",
        "{host}",
        "--port",
        "{port}",
        *extra,
    ]


def _free_ports(count: int) -> list[int]:
    ports: list[int] = []
    candidate = 18201
    while len(ports) < count:
        port = free_port_in_range(candidate)
        ports.append(port)
        candidate = port + 1
    return ports


@dataclass
class ModelEnv:
    """A test ``MODELS_HOME``, state dir, and registry."""

    home: Path
    state_dir: Path
    registry: ModelRegistry

    def manager(self, **kwargs: Any) -> ModelManager:
        """Build a manager over this environment."""
        return ModelManager(
            self.registry, models_home=self.home, state_dir=self.state_dir, **kwargs
        )

    def port(self, role: ModelRole) -> int:
        """The port the registry gave ``role``."""
        return self.registry.roles[role].port


def build_model_env(
    tmp_path: Path,
    *,
    roles: Mapping[str, Mapping[str, Any]] | None = None,
    mutate: Callable[[dict[str, Any]], None] | None = None,
    **top: Any,
) -> ModelEnv:
    """Build the environment.

    Args:
        tmp_path: The test's temporary directory.
        roles: Per-role overrides merged into the generated spec (e.g. a ``command``).
        mutate: Final edit of the raw YAML data.
        **top: Top-level overrides such as ``idle_timeout_s``.
    """
    data: dict[str, Any] = yaml.safe_load(DEFAULT_REGISTRY.read_text())
    old_ports = sorted({spec["port"] for spec in data["roles"].values()})
    new_port = dict(zip(old_ports, _free_ports(len(old_ports)), strict=True))
    home = tmp_path / "Models"
    for name, spec in data["roles"].items():
        spec["port"] = new_port[spec["port"]]
        spec["command"] = fake_server_command()
        spec["startup_timeout_s"] = 15
        spec.update((roles or {}).get(name, {}))
        model = home / spec["model_dir"]
        model.mkdir(parents=True, exist_ok=True)
        (model / "config.json").write_text("{}")
        (model / "model.safetensors").write_bytes(b"fake weights")
    data.update(top)
    if mutate is not None:
        mutate(data)
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(data))
    return ModelEnv(home=home, state_dir=tmp_path / "state", registry=ModelRegistry.load(path))
