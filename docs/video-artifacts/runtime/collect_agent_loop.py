"""Read-only recovery of the actual recorded Hermes session and tool messages."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from hermes_cli.gateway_client import connect_gateway

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'docs/video-artifacts'
parser = argparse.ArgumentParser()
parser.add_argument('session')
parser.add_argument('--output-prefix', default='agent')
parser.add_argument('--surface', choices=('cli', 'desktop'), default='cli')
args = parser.parse_args()
if not args.output_prefix.replace('-', '').isalnum():
    raise SystemExit('Output prefix must contain only letters, numbers or hyphens')
SESSION = args.session
secret = os.environ.get('CUSTOM_API_KEY', '')
def clean(value):
    if isinstance(value, str):
        return value.replace(secret, '[REDACTED]') if secret else value
    if isinstance(value, list): return [clean(v) for v in value]
    if isinstance(value, dict):
        return {k: clean(v) for k,v in value.items() if k.lower() not in ('api_key','authorization','access_token','refresh_token')}
    return value

async def main():
    async with connect_gateway() as client:
        snapshot = await client.rpc('session.resume', session_id=SESSION)
        messages = [{k: clean(v) for k,v in row.items() if k in ('role','content','timestamp','tool_calls','tool_call_id','tool_name','finish_reason')} for row in snapshot.get('messages', [])]
        tools = []
        results = []
        for row in messages:
            for call in row.get('tool_calls', []):
                function = call.get('function', {})
                tools.append({'name': function.get('name'), 'arguments': function.get('arguments'), 'id':call.get('id')})
            if row['role'] == 'tool':
                results.append({'name':row.get('tool_name'),'output':row.get('content'),'tool_call_id':row.get('tool_call_id')})
        pending = [{k:v for k,v in row.items() if k in ('admission_id','status','outcome','execution_generation')} for row in snapshot.get('pending',[])]
        required = ('claimcoach_case_summary', 'claimcoach_explain_code', 'claimcoach_payer_rules')
        checked = {}
        case_id = None
        for result in results:
            if result['name'] in required:
                try:
                    body = json.loads(result['output'])
                    checked[result['name']] = body.get('ok') is True
                    if result['name'] == 'claimcoach_case_summary':
                        case_id = body.get('case_id')
                except (ValueError, AttributeError):
                    checked[result['name']] = False
        failed_tool_results = []
        for result in results:
            try:
                body = json.loads(result['output'])
            except (ValueError, TypeError):
                continue
            if isinstance(body, dict) and body.get('error'):
                failed_tool_results.append({'name':result['name'],'tool_call_id':result['tool_call_id'],'error':body['error']})
        succeeded = all(checked.get(name, False) for name in required)
        final = (messages[-1].get('content') if messages and messages[-1]['role'] == 'assistant' and not messages[-1].get('tool_calls') else None)
        receipt = {
            'session_id':SESSION,'case_id':case_id,'data':'fictional training sample',
            'runtime':f'actual Hermes Agent gateway session initiated by {args.surface}; recovered from canonical session messages',
            'endpoint':'http://127.0.0.1:8080/v1','model':'Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed',
            'running':snapshot.get('running'),'pending':pending,'message_count':len(messages),
            'tools':tools,'tool_results':results,'messages':messages,
            'required_tool_results_ok':checked, 'all_required_tools_succeeded':succeeded, 'final_answer':final,
            'failed_tool_results':failed_tool_results,
            'completed':bool(not snapshot.get('running') and not pending and final),
        }
        (OUT/f'{args.output_prefix}-loop.json').write_text(json.dumps(receipt,indent=2)+'\n')
        parts=['# Actual local Hermes tool loop','','Fictional training case. Recorded tool calls and outputs from the canonical Hermes session.','']
        for row in messages:
            if row['role']=='user': parts.extend(['## Request','',row.get('content',''),''])
            elif row['role']=='tool': parts.extend([f"## Tool response: {row.get('tool_name','unknown')}",'','```text',row.get('content',''),'```',''])
            elif row['role']=='assistant':
                for call in row.get('tool_calls',[]):
                    f=call.get('function',{})
                    parts.extend([f"Tool call: `{f.get('name')}`",'','```json',f.get('arguments',''),'```',''])
                if row.get('content'): parts.extend(['## Agent answer','',row['content'],''])
        (OUT/f'{args.output_prefix}-responses.md').write_text('\n'.join(parts))
        print(json.dumps({'running':receipt['running'],'completed':receipt['completed'],'message_count':len(messages),'calls':tools,'tool_response_count':len(results)},indent=2))
asyncio.run(main())
