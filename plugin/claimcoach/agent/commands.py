"""The ``/denial`` slash command: start denial work from the Hermes chat.

Implements: US-9.4 (``/denial`` with no argument answers how to start, PHI-free; ``/denial <case
ID>`` answers that case's summary through the guarded ``claimcoach_case_summary`` handler, as
text). Rules: BR-2 (the reply sends documents to the ClaimCoach pane, never the chat), BR-3 (a
case is named by its ID; the reply holds codes, rule-card payer names, and enums only), BR-14
(an argument that is not a case ID is never echoed; nothing raises out of the handler, since
Hermes would show the exception text).

The reply is rendered only from a ``CaseSummaryResult`` that validates after redaction, or from a
fixed error message, so it holds nothing the typed summary does not.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Final, Protocol

from pydantic import ValidationError

from claimcoach.agent.types import CaseSummaryResult
from claimcoach.api.models import ERROR_MESSAGES, ErrorEnvelope
from claimcoach.logs import get_logger

__all__ = [
    "COMMAND_NAME",
    "USAGE",
    "CommandRegistrar",
    "denial_command",
    "register_commands",
    "render_summary",
]

COMMAND_NAME: Final = "denial"
_CASE_ID: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

USAGE: Final = """\
/denial: start denial work with ClaimCoach.
1. Open the ClaimCoach pane, create a case, and add the EOB, 835, or denial letter there. Never \
paste claim documents or patient details into this chat.
2. Run /denial <case ID> for the case's redacted summary: status, codes, payer, denial reason.
3. Ask about a code (CO-197) or a payer's rules; answers come from the ClaimCoach global corpus \
and the claimcoach:denial-triage playbook."""
"""What ``/denial`` answers without a case ID, or with something that is not one."""

_NEXT: Final = {
    "intake": "Process the case in the ClaimCoach pane to extract its fields.",
    "extracted": "Confirm any highlighted fields, then diagnose the case in the pane.",
    "diagnosed": "Draft the appeal in the pane.",
    "drafted": "Review the draft in the pane, then export it for human review.",
}
_DEADLINE: Final = {
    "computed": "known (see the pane)",
    "no_payer": "unknown: the payer was not read",
    "no_rule_card": "unknown: no rule card for this payer",
    "no_appeal_limit": "unknown: the payer's cards give no appeal limit",
    "no_denial_date": "unknown: the denial date was not read",
    "implausible_denial_date": "unknown: check the denial date",
}

_log = get_logger("claimcoach.agent")

SummaryHandler = Callable[..., str]
"""The guarded ``claimcoach_case_summary`` handler: ``handler(args) -> JSON string``."""


class CommandRegistrar(Protocol):
    """The slice of Hermes' ``PluginContext`` that command registration uses."""

    def register_command(  # noqa: D102 - mirrors Hermes' signature
        self,
        name: str,
        handler: Callable[..., Any],
        description: str = "",
        args_hint: str = "",
        argument_mode: str | None = None,
    ) -> object: ...


def render_summary(summary: CaseSummaryResult) -> str:
    """Return a case summary as the chat shows it."""
    lines = [f"ClaimCoach case {summary.case_id}: {summary.status}, {summary.stage}"]
    lines.append(f"Payer: {summary.payer or 'no rule card matches the payer'}")
    lines.append(f"Codes: {', '.join(summary.codes) or 'none read yet'}")
    if summary.denial_reason is not None and summary.appeal_likelihood is not None:
        stale = " (diagnosis out of date: diagnose again)" if summary.diagnosis_stale else ""
        lines.append(
            f"Denial reason: {summary.denial_reason.value}; "
            f"appeal likelihood: {summary.appeal_likelihood.value}{stale}"
        )
    if summary.deadline is not None:
        lines.append(f"Appeal deadline: {_DEADLINE[summary.deadline]}")
    lines.append(f"Documents: {summary.documents}; fields to confirm: {summary.needs_confirmation}")
    if summary.outcome is not None:
        lines.append(f"Outcome: {summary.outcome.value}")
    else:
        lines.append(f"Next: {_NEXT[summary.stage]}")
    return "\n".join(lines)


def _reply(raw: str) -> str:
    """Render the guarded handler's JSON: a summary, or a known envelope's fixed message."""
    try:
        return ERROR_MESSAGES[ErrorEnvelope.model_validate_json(raw).error.code]
    except ValidationError:
        pass
    try:
        return render_summary(CaseSummaryResult.model_validate_json(raw))
    except ValidationError:
        # Redaction changed a field so it no longer validates: show nothing of it.
        return ERROR_MESSAGES["redaction_failed"]


def denial_command(summarize: SummaryHandler) -> Callable[[str], str]:
    """Build the ``/denial`` handler over the guarded case-summary handler.

    Args:
        summarize: The guarded ``claimcoach_case_summary`` handler.

    Returns:
        ``handler(raw_args) -> str``; it never raises.
    """

    def denial(raw_args: str) -> str:
        case_id = raw_args.strip()
        if not _CASE_ID.fullmatch(case_id):
            return USAGE
        try:
            return _reply(summarize({"case_id": case_id}))
        except Exception as exc:  # noqa: BLE001 - Hermes would show the exception text
            _log.error("/denial failed: %s", type(exc).__name__)
            return ERROR_MESSAGES["internal_error"]

    return denial


def register_commands(ctx: CommandRegistrar, summarize: SummaryHandler) -> str:
    """Register ``/denial`` with Hermes.

    Args:
        ctx: Hermes plugin context.
        summarize: The guarded ``claimcoach_case_summary`` handler.

    Returns:
        The command's name.
    """
    ctx.register_command(
        COMMAND_NAME,
        denial_command(summarize),
        description="Start denial work with ClaimCoach, or summarize a case by ID (no PHI).",
        args_hint="[case ID]",
    )
    return COMMAND_NAME
