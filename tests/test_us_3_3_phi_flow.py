"""US-3.3: PHI flows bypass the agent transcript (Python half).

Rules: BR-2, PC-4. The pane scenarios run under ``node --test``
(``plugin/desktop/tests/case_pane.test.mjs``); this module checks the other end of the flow: the
gateway routes and the app package import only the standard library, their declared dependencies,
``claimcoach``, and an allowlist of Hermes modules (config, events, data dirs) — never the session
store, agent loop, tool dispatch, or gateway transports.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from tests.conftest import PLUGIN_DIR

THIRD_PARTY = frozenset({"fastapi", "httpx", "pydantic", "starlette", "uvicorn", "yaml"})
"""Declared dependencies (pyproject ``[project] dependencies``) and starlette, fastapi's base."""

HERMES_ALLOWED = frozenset(
    {"hermes_cli.config", "hermes_cli.plugin_events", "hermes_constants", "plugins.plugin_storage"}
)
"""The only Hermes modules ClaimCoach may import: config read, event broadcast, data dirs. Nothing
that reaches the session store, the agent loop, tool dispatch, or a gateway transport."""


def allowed(module: str) -> bool:
    top = module.split(".", 1)[0]
    return (
        top in sys.stdlib_module_names
        or top in THIRD_PARTY
        or top == "claimcoach"
        or module in HERMES_ALLOWED
    )


SOURCES = [
    *sorted(p for p in (PLUGIN_DIR / "claimcoach").rglob("*.py") if "__pycache__" not in p.parts),
    PLUGIN_DIR / "dashboard" / "plugin_api.py",
    PLUGIN_DIR / "__init__.py",
]


def imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(PLUGIN_DIR)))
def test_us_3_3_case_processing_adds_nothing_to_sessions_backend(path: Path) -> None:
    for module in imported_modules(path):
        assert allowed(module), f"{path.name} imports {module}"


@pytest.mark.parametrize(
    "module",
    ["hermes_state", "hermes_state_messages", "hermes_cli.active_sessions", "run_agent", "tools"],
)
def test_us_3_3_scan_rejects_agent_surfaces(module: str) -> None:
    assert not allowed(module)


def test_us_3_3_scan_sees_every_module() -> None:
    assert len(SOURCES) > 20
    assert any(path.name == "plugin_api.py" for path in SOURCES)
    assert "claimcoach.agent.guard" in imported_modules(PLUGIN_DIR / "claimcoach/agent/tools.py")
