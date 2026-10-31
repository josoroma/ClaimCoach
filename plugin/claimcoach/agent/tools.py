"""Agent tool declarations and their registration with Hermes.

Implements: US-1.1 (the ``provides_tools`` in ``plugin.yaml`` register once the plugin is enabled).
Rules: ES-1 (tool JSON schemas are generated from Pydantic models), PC-8 (handlers return a JSON
string), BR-3 (tools take and return only IDs, codes, and payer names).

The handlers answer with the ``not_implemented`` envelope until EPIC-9 (US-9.1, US-9.2) delivers
their behavior. Answering instead of raising keeps Hermes from logging a traceback and gives the
agent a stable, PHI-free result.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claimcoach.api.models import envelope

__all__ = [
    "TOOLS",
    "TOOLSET",
    "CaseSummaryParams",
    "ExplainCodeParams",
    "PayerRulesParams",
    "ToolHandler",
    "ToolRegistrar",
    "ToolSpec",
    "register_tools",
]

TOOLSET: Final = "claimcoach"

ToolHandler = Callable[..., str]
"""Hermes calls ``handler(args, **kwargs)`` and expects a JSON string back (PC-8)."""


class ToolRegistrar(Protocol):
    """The slice of Hermes' ``PluginContext`` that tool registration uses."""

    def register_tool(  # noqa: D102 - mirrors Hermes' signature
        self,
        name: str,
        toolset: str,
        schema: dict[str, Any],
        handler: ToolHandler,
        *,
        description: str = "",
    ) -> object: ...


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExplainCodeParams(_Params):
    """Arguments of ``claimcoach_explain_code``."""

    code: str = Field(
        min_length=1,
        max_length=16,
        pattern=r"^[A-Za-z0-9-]+$",
        description="CARC, RARC, or group code, e.g. CO-197 or N290.",
    )


class PayerRulesParams(_Params):
    """Arguments of ``claimcoach_payer_rules``."""

    payer: str = Field(min_length=1, max_length=120, description="Payer name.")


class CaseSummaryParams(_Params):
    """Arguments of ``claimcoach_case_summary``; a case ID only, never case content (BR-3)."""

    case_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="ClaimCoach case ID.",
    )


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One agent tool: its name, description, and parameter model."""

    name: str
    description: str
    params: type[_Params]

    def schema(self) -> dict[str, Any]:
        """Return the Hermes tool schema generated from the parameter model."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.params.model_json_schema(),
        }

    def handle(self, args: Mapping[str, Any], **_context: Any) -> str:  # noqa: ANN401
        """Validate ``args`` and answer with a JSON error envelope.

        Args:
            args: Tool arguments supplied by the agent.
            **_context: Hermes call context (task id, session); unused.

        Returns:
            JSON ``invalid_request`` envelope for bad arguments, otherwise ``not_implemented``.
        """
        try:
            self.params.model_validate(args)
        except ValidationError:
            # Never echo the arguments back: the agent transcript may leave the Mac (BR-3).
            return envelope("invalid_request").model_dump_json()
        return envelope("not_implemented").model_dump_json()


TOOLS: Final[tuple[ToolSpec, ...]] = (
    ToolSpec(
        "claimcoach_explain_code",
        "Explain a denial code (CARC/RARC/group) from the ClaimCoach global corpus.",
        ExplainCodeParams,
    ),
    ToolSpec(
        "claimcoach_payer_rules",
        "Return the payer rule card (filing limits, appeal levels, required documents).",
        PayerRulesParams,
    ),
    ToolSpec(
        "claimcoach_case_summary",
        "Return a redacted summary of a ClaimCoach case by case ID.",
        CaseSummaryParams,
    ),
)


def register_tools(ctx: ToolRegistrar) -> list[str]:
    """Register every ClaimCoach agent tool with Hermes.

    Args:
        ctx: Hermes plugin context.

    Returns:
        Names of the registered tools, in declaration order.
    """
    for tool in TOOLS:
        ctx.register_tool(
            name=tool.name,
            toolset=TOOLSET,
            schema=tool.schema(),
            handler=tool.handle,
            description=tool.description,
        )
    return [tool.name for tool in TOOLS]
