"""Run under the Hermes gateway venv: discover plugins and print the ClaimCoach tools it registered.

US-1.1, US-9.3, and US-9.4 integration probe. Invoked by ``tests/test_us_1_1_plugin_package.py``
with ``HERMES_HOME`` pointing at a throwaway home whose ``plugins/claimcoach`` links to this repo's
``plugin/``. Uses the same discovery entry point the gateway calls at startup
(``hermes_cli.plugins``).
"""

import json

from hermes_cli.plugins import discover_plugins, get_plugin_manager

discover_plugins(force=True)
manager = get_plugin_manager()
plugins = {str(p["name"]): p for p in manager.list_plugins()}
tools = sorted(n for n in manager._plugin_tool_names if n.startswith("claimcoach"))
# US-4.3: the ``hermes claimcoach`` CLI command, registered through register_cli_command.
cli = sorted(n for n, c in manager._cli_commands.items() if c.get("plugin") == "claimcoach")
# US-9.3 and US-9.4: the skill and the slash command.
skills = sorted(n for n in manager._plugin_skills if n.startswith("claimcoach:"))
commands = sorted(n for n, c in manager._plugin_commands.items() if c.get("plugin") == "claimcoach")
payload = {
    "tools": tools,
    "cli_commands": cli,
    "skills": skills,
    "commands": commands,
    "claimcoach": plugins.get("claimcoach"),
}
print(json.dumps(payload, default=str))  # noqa: T201
