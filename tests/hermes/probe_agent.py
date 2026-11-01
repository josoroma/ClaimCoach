"""Run under the Hermes gateway venv: load the ClaimCoach skill and run /denial through Hermes.

US-9.3 and US-9.4 integration probe. Invoked by ``tests/test_us_9_3_skill.py`` and
``tests/test_us_9_4_denial_command.py`` with ``HERMES_HOME`` pointing at a throwaway home whose
``plugins/claimcoach`` links to this repo's ``plugin/`` (no worker runs there). Prints one JSON
object:

- ``skill``: the decoded result of ``skill_view("claimcoach:denial-triage")``;
- ``denial``: ``/denial`` with no argument, through ``invoke_plugin_command``;
- ``denial_case``: ``/denial <argv[1]>``, which needs the worker (it is not running).

argv: ``<case id argument>``.
"""

import json
import sys

from hermes_cli.plugin_command_dispatch import invoke_plugin_command
from hermes_cli.plugins import discover_plugins, get_plugin_command_handler
from tools.skills_tool import skill_view

discover_plugins(force=True)
handler = get_plugin_command_handler("denial")
context = {"source": None, "session_id": "s1", "session_key": "k1", "platform": "cli"}


def run(raw_args: str) -> object:
    return None if handler is None else invoke_plugin_command(handler, raw_args, **context)


payload = {
    "skill": json.loads(skill_view("claimcoach:denial-triage")),
    "denial": run(""),
    "denial_case": run(sys.argv[1]),
}
print(json.dumps(payload, default=str))  # noqa: T201
