"""Agent tool declarations and their registration with Hermes.

Implements: US-1.1 (the ``provides_tools`` in ``plugin.yaml`` register once the plugin is enabled),
US-3.2 (every handler is registered wrapped in ``redact_tool_result``, and the
``transform_tool_result`` hook is registered with the tools), US-9.1 (``claimcoach_explain_code``
and ``claimcoach_payer_rules`` answer from the global corpus), US-9.2 (``claimcoach_case_summary``
answers a case ID with the case reduced to codes, names, and enums), US-9.3 and US-9.4
(``register_agent`` also registers the ``denial-triage`` skill and the ``/denial`` command).
Rules: ES-1 (tool JSON schemas are generated from Pydantic models; results are typed), PC-4 (the
handlers only proxy to the loopback worker), PC-7, PC-8 (handlers return a JSON string), BR-3
(tools take and return only IDs, codes, payer names, and enums, and each handler redacts its own
result).

A handler never raises and never echoes its arguments: bad arguments get ``invalid_request``, a
worker refusal its own fixed envelope (``code_not_found``, ``case_not_found``, …), and a worker
that is down or too slow ``worker_unavailable``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

from pydantic import ValidationError

from claimcoach.agent.commands import CommandRegistrar, register_commands
from claimcoach.agent.guard import (
    Handler,
    HookRegistrar,
    Scrubber,
    redact_tool_result,
    register_guard_hook,
    run_blocking,
    worker_client,
)
from claimcoach.agent.skills import SkillRegistrar, register_skills
from claimcoach.agent.types import (
    CaseSummaryParams,
    CaseSummaryResult,
    ExplainCodeParams,
    ExplainCodeResult,
    PayerRulesParams,
    PayerRulesResult,
    ToolParams,
    ToolResult,
)
from claimcoach.api.client import CASE_TIMEOUT, WorkerClient, WorkerError
from claimcoach.api.models import envelope
from claimcoach.corpus.paths import active_profile

__all__ = [
    "CASE_SUMMARY",
    "TOOLS",
    "TOOLSET",
    "TOOL_TIMEOUT",
    "AgentRegistrar",
    "CaseSummaryParams",
    "Connect",
    "ExplainCodeParams",
    "PayerRulesParams",
    "ToolHandler",
    "ToolRegistrar",
    "ToolSpec",
    "guarded_handler",
    "register_agent",
    "register_tools",
]

TOOLSET: Final = "claimcoach"
TOOL_TIMEOUT: Final = CASE_TIMEOUT + 5.0
"""Seconds one tool call may take; past the worker call's own timeout, so that one fires first."""

ToolHandler = Callable[..., str]
"""Hermes calls ``handler(args, **kwargs)`` and expects a JSON string back (PC-8)."""

Connect = Callable[[], WorkerClient]
"""Returns a client for the worker; tests pass one for a test worker."""

ToolCall = Callable[[WorkerClient, Any], Awaitable[ToolResult]]
"""Asks the worker for a tool's answer, given its validated parameters."""


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


class AgentRegistrar(ToolRegistrar, HookRegistrar, SkillRegistrar, CommandRegistrar, Protocol):
    """Everything ``register_agent`` needs from Hermes' ``PluginContext``."""


def _connect() -> WorkerClient:
    return worker_client(CASE_TIMEOUT)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One agent tool: its name, description, parameter and result models, and its worker call."""

    name: str
    description: str
    params: type[ToolParams]
    result: type[ToolResult]
    call: ToolCall

    def schema(self) -> dict[str, Any]:
        """Return the Hermes tool schema generated from the parameter model."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.params.model_json_schema(),
        }

    def handle(
        self,
        args: Mapping[str, Any],
        *,
        connect: Connect | None = None,
        **_context: Any,  # noqa: ANN401
    ) -> str:
        """Validate ``args``, ask the worker, and answer with the typed result as JSON.

        Args:
            args: Tool arguments supplied by the agent.
            connect: Returns the worker client; defaults to the one the gateway uses.
            **_context: Hermes call context (task id, session); unused.

        Returns:
            The result's JSON, or a fixed error envelope (never the arguments).
        """
        try:
            params = self.params.model_validate(args)
        except ValidationError:
            # Never echo the arguments back: the agent transcript may leave the Mac (BR-3).
            return envelope("invalid_request").model_dump_json()
        client = (connect or _connect)()
        try:
            result = run_blocking(lambda: self.call(client, params), TOOL_TIMEOUT)
        except WorkerError as exc:
            return envelope(exc.code).model_dump_json()
        except TimeoutError:
            return envelope("worker_unavailable").model_dump_json()
        return result.model_dump_json()


async def _explain_code(client: WorkerClient, params: ExplainCodeParams) -> ExplainCodeResult:
    return await client.explain_code(params)


async def _payer_rules(client: WorkerClient, params: PayerRulesParams) -> PayerRulesResult:
    return await client.payer_rules(params)


async def _case_summary(client: WorkerClient, params: CaseSummaryParams) -> CaseSummaryResult:
    # The active Hermes profile is the biller; a case of another profile is not found (BR-5).
    return await client.case_summary(active_profile(), params)


CASE_SUMMARY: Final = ToolSpec(
    "claimcoach_case_summary",
    "Return a redacted summary of a ClaimCoach case by case ID: its status, stage, codes, payer "
    "(as the rule cards name it), denial reason, and appeal likelihood. No case text or PHI.",
    CaseSummaryParams,
    CaseSummaryResult,
    _case_summary,
)

TOOLS: Final[tuple[ToolSpec, ...]] = (
    ToolSpec(
        "claimcoach_explain_code",
        "Explain a denial code (CARC/RARC/group, e.g. CO-197) from the ClaimCoach global corpus.",
        ExplainCodeParams,
        ExplainCodeResult,
        _explain_code,
    ),
    ToolSpec(
        "claimcoach_payer_rules",
        "Return the payer rule cards (filing limits, appeal levels, required documents) from the "
        "ClaimCoach global corpus.",
        PayerRulesParams,
        PayerRulesResult,
        _payer_rules,
    ),
    CASE_SUMMARY,
)


def guarded_handler(
    tool: ToolSpec, scrubber: Scrubber | None = None, connect: Connect | None = None
) -> Handler:
    """Return ``tool``'s handler as Hermes calls it, behind the PHI guard.

    Args:
        tool: The tool.
        scrubber: Redaction call for the guard; defaults to the worker's ``/redact``.
        connect: Returns the worker client; defaults to the one the gateway uses.
    """
    handle = tool.handle  # bound now: what was registered is what runs

    def handler(args: Mapping[str, Any], **context: Any) -> str:  # noqa: ANN401
        return handle(args, connect=connect, **context)

    return redact_tool_result(handler, scrubber=scrubber)


def register_tools(
    ctx: ToolRegistrar, scrubber: Scrubber | None = None, connect: Connect | None = None
) -> list[str]:
    """Register every ClaimCoach agent tool with Hermes, each behind the PHI guard.

    Args:
        ctx: Hermes plugin context.
        scrubber: Redaction call for the guard; defaults to the worker's ``/redact``.
        connect: Returns the worker client; defaults to the one the gateway uses.

    Returns:
        Names of the registered tools, in declaration order.
    """
    for tool in TOOLS:
        ctx.register_tool(
            name=tool.name,
            toolset=TOOLSET,
            schema=tool.schema(),
            handler=guarded_handler(tool, scrubber, connect),
            description=tool.description,
        )
    return [tool.name for tool in TOOLS]


def register_agent(
    ctx: AgentRegistrar, scrubber: Scrubber | None = None, connect: Connect | None = None
) -> list[str]:
    """Register the guarded tools, the second guard, the skill, and the ``/denial`` command.

    Args:
        ctx: Hermes plugin context.
        scrubber: Redaction call for the guards; defaults to the worker's ``/redact``.
        connect: Returns the worker client; defaults to the one the gateway uses.

    Returns:
        Names of the registered tools.
    """
    names = register_tools(ctx, scrubber, connect)
    register_guard_hook(ctx, scrubber)
    register_skills(ctx)
    register_commands(ctx, guarded_handler(CASE_SUMMARY, scrubber, connect))
    return names
