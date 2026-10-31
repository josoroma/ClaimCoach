"""Run under the Hermes gateway venv: discover plugins and print the ClaimCoach tools it registered.

US-1.1 integration probe. Invoked by ``tests/test_us_1_1_plugin_package.py`` with ``HERMES_HOME``
pointing at a throwaway home whose ``plugins/claimcoach`` links to this repo's ``plugin/``. Uses
the same discovery entry point the gateway calls at startup (``hermes_cli.plugins``).
"""

import json

from hermes_cli.plugins import discover_plugins, get_plugin_manager

discover_plugins(force=True)
manager = get_plugin_manager()
plugins = {str(p["name"]): p for p in manager.list_plugins()}
tools = sorted(n for n in manager._plugin_tool_names if n.startswith("claimcoach"))
print(json.dumps({"tools": tools, "claimcoach": plugins.get("claimcoach")}, default=str))  # noqa: T201
