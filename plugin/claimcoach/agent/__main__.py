"""``python -m claimcoach.agent tools|call|skill|denial``: the agent half, run by an operator.

Implements: US-9.1 and US-9.2 (``tools`` lists each tool's parameter schema and result model,
offline; ``call`` runs a tool through its guarded handler against the running worker), US-9.3
(``skill`` prints the playbook as Hermes registers it), US-9.4 (``denial`` runs the ``/denial``
handler). Rules: BR-3 (``call`` and ``denial`` print only what the guarded handlers return, which
the agent would see), BR-11 (``--port`` inside ClaimCoach's range; the token goes only to the
worker the launcher recorded), BR-14 (bad arguments are refused without echoing them).
Operated through ``make agent-tools``, ``make agent-call``, ``make agent-skill``, and
``make agent-denial``.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from typing import Final

from claimcoach.agent.commands import COMMAND_NAME, denial_command
from claimcoach.agent.guard import GUARD_TIMEOUT, worker_scrubber
from claimcoach.agent.skills import SKILL_PATH, read_frontmatter
from claimcoach.agent.tools import CASE_SUMMARY, TOOLS, TOOLSET, guarded_handler
from claimcoach.api.client import WorkerClient
from claimcoach.cli import port_arg, port_client
from claimcoach.settings import PORT_RANGE

__all__ = ["main"]

Out = Callable[[str], object]
_TOOLS: Final = {tool.name: tool for tool in TOOLS}


def _tools(out: Out) -> int:
    for tool in TOOLS:
        out(f"{tool.name}  (toolset {TOOLSET}, result {tool.result.__name__})")
        out(f"  {tool.description}")
        out(f"  parameters: {json.dumps(tool.params.model_json_schema(), sort_keys=True)}")
    frontmatter = read_frontmatter(SKILL_PATH)
    out(f"skill: {TOOLSET}:{frontmatter['name']}  ({SKILL_PATH})")
    out(f"command: /{COMMAND_NAME} [case ID]")
    return 0


def _skill(out: Out) -> int:
    out(f"# {TOOLSET}:{read_frontmatter(SKILL_PATH)['name']}  ({SKILL_PATH})")
    out(SKILL_PATH.read_text(encoding="utf-8"))
    return 0


def _call(name: str, raw: str, connect: Callable[[], WorkerClient], out: Out) -> int:
    try:
        args = json.loads(raw)
    except ValueError:
        out("error: --args is not JSON")  # never echoed: it may be what the agent would send
        return 2
    if not isinstance(args, dict):
        out("error: --args is not a JSON object")
        return 2
    handler = guarded_handler(_TOOLS[name], worker_scrubber(GUARD_TIMEOUT, connect), connect)
    result = handler(args)
    out(json.dumps(json.loads(result), indent=2))
    return 0 if json.loads(result).get("ok") is True else 1


def _denial(case_id: str, connect: Callable[[], WorkerClient], out: Out) -> int:
    summarize = guarded_handler(CASE_SUMMARY, worker_scrubber(GUARD_TIMEOUT, connect), connect)
    out(denial_command(summarize)(case_id))
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    out: Out = print,
    connect: Callable[[int], WorkerClient] = port_client,
) -> int:
    """Run the command.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.
        out: Where lines go; defaults to ``print``.
        connect: Returns the worker client for a port; tests pass one for a test worker.

    Returns:
        ``0`` on success; ``1`` when a tool answered an error envelope; ``2`` for bad arguments.
    """
    parser = argparse.ArgumentParser(prog="python -m claimcoach.agent", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tools", help="list the tools, the skill, and the command (offline)")
    commands.add_parser("skill", help="print the denial-triage skill")
    call = commands.add_parser("call", help="call a tool through its PHI guard")
    call.add_argument("tool", choices=sorted(_TOOLS))
    call.add_argument("--args", default="{}", help="the tool arguments as a JSON object")
    denial = commands.add_parser("denial", help="run /denial [case ID]")
    denial.add_argument("case_id", nargs="?", default="")
    for sub in (call, denial):
        sub.add_argument(
            "--port",
            type=port_arg,
            default=PORT_RANGE.start,
            help="the worker's port (default: %(default)s)",
        )
    args = parser.parse_args(argv)
    if args.command == "tools":
        return _tools(out)
    if args.command == "skill":
        return _skill(out)
    port: int = args.port
    if args.command == "call":
        return _call(args.tool, args.args, lambda: connect(port), out)
    return _denial(args.case_id, lambda: connect(port), out)


if __name__ == "__main__":
    raise SystemExit(main())
