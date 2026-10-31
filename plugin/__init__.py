"""ClaimCoach agent half: Hermes calls ``register(ctx)`` once ``claimcoach`` is enabled.

Implements: US-1.1 (unified package; Python half inert until ``hermes plugins enable claimcoach``).
Rules: PC-1, PC-2, PC-8, BR-3.

Hermes imports this file only when ``claimcoach`` is in ``plugins.enabled`` (PC-1), so importing it
has no side effects beyond making the app package importable.
"""

from __future__ import annotations

from ._bootstrap import ensure_app_package

ensure_app_package()

from claimcoach.agent.tools import ToolRegistrar, register_tools  # noqa: E402

__all__ = ["register"]


def register(ctx: ToolRegistrar) -> None:
    """Register ClaimCoach's agent-side contributions with Hermes.

    Args:
        ctx: Hermes plugin context.
    """
    register_tools(ctx)
