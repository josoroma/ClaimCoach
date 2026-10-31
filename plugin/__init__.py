"""ClaimCoach agent half: Hermes calls ``register(ctx)`` once ``claimcoach`` is enabled.

Implements: US-1.1 (unified package; Python half inert until ``hermes plugins enable claimcoach``),
US-3.2 (tools register behind the PHI guard, plus the ``transform_tool_result`` hook), US-4.3
(``hermes claimcoach corpus …`` registers through ``register_cli_command``).
Rules: PC-1, PC-2, PC-7, PC-8, BR-3.

Hermes imports this file only when ``claimcoach`` is in ``plugins.enabled`` (PC-1), so importing it
has no side effects beyond making the app package importable.
"""

from __future__ import annotations

from typing import Protocol

from ._bootstrap import ensure_app_package

ensure_app_package()

from claimcoach.agent.tools import AgentRegistrar, register_agent  # noqa: E402
from claimcoach.cli import CliRegistrar, register_cli  # noqa: E402

__all__ = ["PluginRegistrar", "register"]


class PluginRegistrar(AgentRegistrar, CliRegistrar, Protocol):
    """Everything ``register`` needs from Hermes' ``PluginContext``."""


def register(ctx: PluginRegistrar) -> None:
    """Register ClaimCoach's agent-side contributions and its CLI command with Hermes.

    Args:
        ctx: Hermes plugin context.
    """
    register_agent(ctx)
    register_cli(ctx)
