"""Run under the Hermes gateway venv: call ClaimCoach tools through Hermes' real tool dispatch.

US-3.2 integration probe. Invoked by ``tests/test_us_3_2_tool_guard.py`` with ``HERMES_HOME``
pointing at a throwaway home whose ``plugins/claimcoach`` links to this repo's ``plugin/`` and
whose ClaimCoach token matches a live test worker. Prints one JSON object:

- ``handler``: the result of ``model_tools.handle_function_call`` for a handler that leaks the
  seeded case, with ClaimCoach's ``transform_tool_result`` hook registered;
- ``failing_hook``: the same call after the hook list is replaced by a hook that raises (PC-7:
  Hermes fails open to the handler's result);
- ``hooks``: how many ``transform_tool_result`` callbacks ClaimCoach registered.

argv: ``<plugin dir> <case json file>``.
"""

import json
import sys
from pathlib import Path
from typing import Any, NoReturn

plugin_dir, case_file = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(plugin_dir))
from _bootstrap import ensure_app_package  # noqa: E402

ensure_app_package(plugin_dir / "claimcoach")
from claimcoach.agent import tools  # noqa: E402

case = case_file.read_text()


def leak(_self: object, _args: object, **_context: Any) -> str:
    return case


tools.ToolSpec.handle = leak  # type: ignore[method-assign,assignment]  # registration below wraps this leaking handler

from hermes_cli.plugins import discover_plugins, get_plugin_manager  # noqa: E402
from model_tools import handle_function_call  # noqa: E402

discover_plugins(force=True)
manager = get_plugin_manager()
hooks = manager._hooks.get("transform_tool_result", [])
handler = handle_function_call("claimcoach_case_summary", {"case_id": "case_01"}, task_id="t1")


def broken(**_payload: Any) -> NoReturn:
    raise RuntimeError("hook failed")


manager._hooks["transform_tool_result"] = [broken]
failing = handle_function_call("claimcoach_case_summary", {"case_id": "case_01"}, task_id="t2")
print(json.dumps({"handler": handler, "failing_hook": failing, "hooks": len(hooks)}))  # noqa: T201
