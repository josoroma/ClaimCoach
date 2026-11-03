#!/usr/bin/env python3
"""Run a Python artifact inside the installed Hermes dependency environment."""
import json
import subprocess
import sys
from pathlib import Path
from workspace import env

runtime = json.loads(subprocess.check_output([str(Path.home() / '.local/bin/hermes'), '--print-runtime-command'], env=env(), text=True))
expected = "runpy.run_module('hermes_cli.main', run_name='__main__', alter_sys=True)"
if runtime[-1].count(expected) != 1:
    raise SystemExit('The installed Hermes launcher format changed; inspect before proceeding')
runtime[-1] = runtime[-1].replace(expected, "script=sys.argv.pop(1); runpy.run_path(script, run_name='__main__')")
raise SystemExit(subprocess.call([*runtime, *sys.argv[1:]], env=env()))
