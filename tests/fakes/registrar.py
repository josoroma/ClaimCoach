"""Fake Hermes ``PluginContext`` for the agent half: records tools, hooks, skills, and commands.

Implements: US-1.1, US-3.2, US-4.3, US-9.3, and US-9.4 test harness. Mirrors
``PluginContext.register_tool``, ``register_hook``, ``register_cli_command``, ``register_skill``
(``hermes_cli/plugins_content.py``), and ``register_command`` in Hermes Agent v0.22.5
(``hermes_cli/plugins.py``).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from claimcoach.agent.tools import ToolHandler

__all__ = ["FakeRegistrar"]


class FakeRegistrar:
    """Records registrations the way Hermes receives them."""

    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}
        self.hooks: dict[str, list[Callable[..., Any]]] = {}
        self.cli_commands: dict[str, dict[str, Any]] = {}
        self.skills: dict[str, dict[str, Any]] = {}
        self.commands: dict[str, dict[str, Any]] = {}

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

    def register_cli_command(
        self,
        name: str,
        help: str,  # noqa: A002 - Hermes' parameter name
        setup_fn: Callable[[argparse.ArgumentParser], None],
        handler_fn: Callable[[argparse.Namespace], None] | None = None,
        description: str = "",
    ) -> object:
        self.cli_commands[name] = {
            "help": help,
            "setup_fn": setup_fn,
            "handler_fn": handler_fn,
            "description": description,
        }
        return None

    def register_skill(
        self,
        name: str,
        path: Path,
        description: str = "",
        frontmatter: Mapping[str, Any] | None = None,
    ) -> object:
        if ":" in name:
            raise ValueError("the namespace is derived from the plugin name")
        if not Path(path).exists():
            raise FileNotFoundError(path)
        self.skills[f"claimcoach:{name}"] = {
            "path": Path(path),
            "description": description,
            "frontmatter": dict(frontmatter or {}),
        }
        return None

    def register_command(
        self,
        name: str,
        handler: Callable[..., Any],
        description: str = "",
        args_hint: str = "",
        argument_mode: str | None = None,
    ) -> object:
        self.commands[name] = {
            "handler": handler,
            "description": description,
            "args_hint": args_hint,
            "argument_mode": argument_mode,
        }
        return None
