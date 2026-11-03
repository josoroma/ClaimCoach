#!/usr/bin/env python3
"""Record an actual local Hermes tool loop against the isolated synthetic case."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
import time
from pathlib import Path

from workspace import ROOT, env

parser = argparse.ArgumentParser()
parser.add_argument('--case', required=True)
args = parser.parse_args()
if not re.fullmatch(r'case_[0-9a-f]{16}', args.case):
    raise SystemExit('A valid ClaimCoach case ID is required')
out = ROOT / 'docs/video-artifacts'
query = out / 'agent-prompt.txt'
query.write_text(
    f'Use the ClaimCoach plugin to triage fictional training case {args.case}. '
    'First call skill_view for claimcoach:denial-triage. Then call claimcoach_case_summary '
    'for that case. Use claimcoach_explain_code for CO-197 and claimcoach_payer_rules '
    'for Northstar Demo Health. Read the actual tool outputs and give a concise next-step '
    'checklist for the ClaimCoach pane. Clearly label the payer policy as fictional. '
    'Do not invent missing authorization evidence. Do not use any other tools or alter '
    'the case. There is no need to send or submit anything.\n'
)
child_env = env()
secret = child_env['CUSTOM_API_KEY']
def clean(value):
    if isinstance(value, str):
        return value.replace(secret, '[REDACTED]')
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if not any(part in k.lower() for part in ('api_key', 'authorization', 'token_secret'))}
    return value

command = [str(Path.home() / '.local/bin/hermes'), 'chat', '--query-file', str(query),
           '--oneshot', '--cli', '--source', 'cli', '-t', 'claimcoach,skills', '--format', 'stream-json',
           '--max-turns', '8', '--reasoning', 'none']
start = time.monotonic()
events = []
# Diagnostics may include environment details; retain them only in memory and
# keep the publishable receipt restricted to the protocol's explicit fields.
process = subprocess.Popen(command, cwd=ROOT, env=child_env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, bufsize=1)
assert process.stdout is not None
# Drain diagnostics concurrently so a full stderr pipe cannot stall inference.
diagnostic_chunks = []
def drain_diagnostics():
    if process.stderr:
        for line in process.stderr:
            diagnostic_chunks.append(line)
            if len(diagnostic_chunks) > 100:
                del diagnostic_chunks[:-100]
diagnostic_thread = threading.Thread(target=drain_diagnostics, daemon=True)
diagnostic_thread.start()
allowed = {
    'system': ('type', 'subtype', 'model', 'session_id', 'timestamp'),
    'tool_use': ('type', 'name', 'tool_call_id', 'input', 'timestamp'),
    'tool_result': ('type', 'name', 'tool_call_id', 'output', 'duration_ms', 'is_error', 'timestamp'),
    'result': ('type', 'session_id', 'exit_code', 'text', 'tokens', 'duration_ms', 'timestamp', 'error'),
}
for line in process.stdout:
    try:
        event = json.loads(line)
    except ValueError:
        continue
    kind = event.get('type')
    if kind not in allowed:
        continue
    event = clean({k: event[k] for k in allowed[kind] if k in event})
    events.append(event)
    if kind in ('tool_use', 'tool_result'):
        print(json.dumps({'event': kind, 'tool': event.get('name'), 'is_error': event.get('is_error')}), flush=True)
code = process.wait(timeout=30)
diagnostic_thread.join(timeout=5)
diagnostics = clean(''.join(diagnostic_chunks))
if code:
    print(diagnostics[-2500:])
results = [e for e in events if e['type'] == 'result']
used = []
for event in events:
    if event['type'] == 'tool_use':
        used.append(event['name'])
        if event['name'] == 'tool_call':
            for call in event.get('input', {}).get('calls', []):
                if isinstance(call, dict) and isinstance(call.get('name'), str):
                    used.append(call['name'])
    elif event['type'] == 'tool_result' and event.get('name', '').startswith('claimcoach_'):
        if event['name'] not in used:
            used.append(event['name'])
required = {'skill_view', 'claimcoach_case_summary', 'claimcoach_explain_code', 'claimcoach_payer_rules'}
checks = {}
for event in events:
    if event['type'] == 'tool_result' and event.get('name') in required:
        try:
            body = json.loads(event.get('output', ''))
            checks[event['name']] = body.get('ok', body.get('success')) is True
        except (ValueError, AttributeError):
            checks[event['name']] = False
all_succeeded = all(checks.get(name, False) for name in required)
receipt = {
    'case_id': args.case, 'data': 'fictional training sample',
    'runtime': 'Hermes Agent CLI actual model/tool loop',
    'endpoint': 'http://127.0.0.1:8080/v1',
    'model': 'Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed',
    'requested_toolsets': ['claimcoach', 'skills'],
    'elapsed_seconds': round(time.monotonic() - start, 3), 'process_exit_code': code,
    'tools_called': used, 'all_required_tools_called': required.issubset(set(used)),
    'required_tool_results_ok': checks, 'all_required_tools_succeeded': all_succeeded,
    'completed': bool(results and results[-1].get('exit_code') == 0 and all_succeeded),
    'events': events,
}
(out / 'agent-loop.json').write_text(json.dumps(receipt, indent=2) + '\n')
parts = ['# Actual local Hermes tool loop', '', 'Fictional training case. This is a recorded runtime receipt, not a scripted response.', '']
for event in events:
    if event['type'] == 'tool_use':
        parts.extend([f"## Tool: {event['name']}", '', '```json', json.dumps(event.get('input', {}), indent=2), '```', ''])
    elif event['type'] == 'tool_result':
        parts.extend(['Tool response:', '', '```text', event.get('output', ''), '```', ''])
    elif event['type'] == 'result':
        parts.extend(['## Agent answer', '', event.get('text', ''), ''])
(out / 'agent-responses.md').write_text('\n'.join(parts))
print(json.dumps({k: v for k, v in receipt.items() if k != 'events'}, indent=2))
raise SystemExit(0 if receipt['completed'] and receipt['all_required_tools_called'] else 1)
