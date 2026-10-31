"""Fake Hermes ``PluginContext`` for the agent half: records tools and hooks.

Implements: US-1.1 and US-3.2 test harness. Mirrors ``PluginContext.register_tool`` and
``register_hook`` in Hermes Agent v0.22.5 (``hermes_cli/plugins.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from claimcoach.agent.tools import ToolHandler

__all__ = ["FakeRegistrar"]


class FakeRegistrar:
    """Records ``register_tool`` and ``register_hook`` calls the way Hermes receives them."""

    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}
        self.hooks: dict[str, list[Callable[..., Any]]] = {}

    def register_tool(
        self,
        name: str,
        toolset: str,
        schema: dict[str, Any],
        handler: ToolHandler,
        *,
        description: str = "",
    ) -> object:
        self.tools[name] = {
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
            "description": description,
        }
        return None

    def register_hook(self, hook_name: str, callback: Callable[..., Any]) -> object:
        self.hooks.setdefault(hook_name, []).append(callback)
        return None
