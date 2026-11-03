"""Call the installed Hermes command registry against the isolated fictional case."""
import json
from pathlib import Path
from hermes_cli.plugin_command_dispatch import invoke_plugin_command
from hermes_cli.plugins import discover_plugins, get_plugin_command_handler
from tools.skills_tool import skill_view

ROOT=Path(__file__).resolve().parents[3]
CASE='case_ef4492f90f971935'
discover_plugins(force=True)
handler=get_plugin_command_handler('denial')
assert handler is not None
context={'source':None,'session_id':'claimcoach-video-command-check','session_key':'claimcoach-video-command-check','platform':'cli'}
skill=json.loads(skill_view('claimcoach:denial-triage'))
result={
 'runtime':'installed Hermes plugin command registry',
 'case_id':CASE,
 'skill':{k:skill.get(k) for k in ('success','name','readiness_status')},
 'command':'/denial',
 'guide':invoke_plugin_command(handler,'',**context),
 'case_summary':invoke_plugin_command(handler,CASE,**context),
 'note':'The slash command returns a guarded summary; the separate agent-loop receipt proves model/tool iteration.',
}
(ROOT/'docs/video-artifacts/command-receipt.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
print(json.dumps(result,indent=2,default=str))
