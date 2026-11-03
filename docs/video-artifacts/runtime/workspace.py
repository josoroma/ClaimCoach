#!/usr/bin/env python3
"""Configure and open the dedicated, local ClaimCoach demonstration workspace."""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / '.local'
HERMES_STATE = STATE / 'hermes'
HERMES_SOURCE = Path.home() / '.hermes/hermes-agent'
MODEL = Path.home() / 'Models/Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed'
KEY = Path.home() / 'sites/legalizer/.local/model/api-key'


def env():
    result = dict(os.environ)
    for name in ('ELECTRON_RUN_AS_NODE', 'CUSTOM_BASE_URL', 'OPENAI_BASE_URL', 'OPENROUTER_BASE_URL'):
        result.pop(name, None)
    result.update(HERMES_HOME=str(HERMES_STATE), MODELS_HOME=str(Path.home() / 'Models'),
                  HERMES_DESKTOP_USER_DATA_DIR=str(STATE / 'desktop'),
                  HERMES_DESKTOP_APP_NAME='Hermes ClaimCoach', HERMES_DESKTOP_CWD=str(ROOT),
                  HERMES_TUI_TOOLSETS='claimcoach,skills', CUSTOM_API_KEY=KEY.read_text().strip())
    return result


def init():
    os.umask(0o077)
    HERMES_STATE.mkdir(parents=True, exist_ok=True)
    config_file = HERMES_STATE / 'config.yaml'
    if not config_file.exists():
        route = {'provider': 'custom', 'model': str(MODEL), 'base_url': 'http://127.0.0.1:8080/v1',
                 'api_key': KEY.read_text().strip(), 'fallback_chain': []}
        config = {
            'model': {**route, 'default': str(MODEL), 'context_length': 64000},
            'fallback_providers': [], 'fallback_model': [],
            'auxiliary': {task: dict(route) for task in ('compression', 'vision', 'approval',
                'title_generation', 'skills_hub', 'mcp', 'curator', 'background_review',
                'triage_specifier', 'tts_audio_tags', 'review', 'memory_query_rewrite',
                'voice_chat', 'kanban_decomposer', 'profile_describer', 'goal_judge',
                'monitor', 'moa_reference', 'moa_aggregator')},
            'delegation': {**route, 'api_mode': 'chat_completions', 'fallback_providers': []},
            'terminal': {'backend': 'local', 'cwd': str(ROOT)},
            'plugins': {'enabled': ['claimcoach']},
            'agent': {'max_turns': 8, 'reasoning_effort': 'none'},
        }
        config_file.write_text(json.dumps(config, indent=2) + '\n')
        config_file.chmod(0o600)
    plugins = HERMES_STATE / 'plugins'
    plugins.mkdir(exist_ok=True)
    link = plugins / 'claimcoach'
    if not link.exists():
        link.symlink_to(ROOT / 'plugin', target_is_directory=True)
    registry = HERMES_STATE / 'plugin-data/claimcoach/models.yaml'
    if not registry.exists():
        script = '''
import pathlib, sys, yaml
root, destination, key = map(pathlib.Path, sys.argv[1:])
config = yaml.safe_load((root/'plugin/claimcoach/models/models.default.yaml').read_text())
shared = dict(repo_id='Youssofal/Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed',
    model_dir='Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed', venv='claimcoach',
    command=['{venv}/bin/python', str(root/'docs/video-artifacts/runtime/local_model_bridge.py'),
        '--host','{host}','--port','{port}','--model','{model}','--key-file',str(key)],
    port=18206, tier_b=27, startup_timeout_s=60)
for role in ('phi_detection','classification','explanation','drafting'):
    config['roles'][role] = dict(shared)
config['roles']['embedding']['command'] = ['{venv}/bin/python',
    str(root/'docs/video-artifacts/runtime/embedding_server.py'),
    '--host','{host}','--port','{port}','--model','{model}']
destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_text(yaml.safe_dump(config, sort_keys=False))
'''
        subprocess.run([str(Path.home() / 'Models/.venvs/claimcoach/bin/python'), '-c',
                        script, str(ROOT), str(registry), str(KEY)], check=True)
    print('Dedicated ClaimCoach workspace configured; all model routes are loopback.')


if __name__ == '__main__':
    init()
    command = sys.argv[1] if len(sys.argv) > 1 else 'init'
    if command == 'start':
        request = Request('http://127.0.0.1:8080/v1/models',
                          headers={'Authorization': 'Bearer ' + KEY.read_text().strip()})
        with build_opener(ProxyHandler({})).open(request, timeout=10) as response:
            if not json.load(response).get('data'):
                raise SystemExit('Start the existing local Bonsai server before this workspace.')
        subprocess.run(['make', 'start'], cwd=ROOT, env=env(), check=True)
        command = 'desktop'
    if command == 'desktop':
        os.execve(str(Path.home() / '.local/bin/hermes'), ['hermes', 'desktop', '--skip-build',
                  '--hermes-root', str(HERMES_SOURCE), '--cwd', str(ROOT), '--local'], env())
    elif command == 'hermes':
        raise SystemExit(subprocess.call([str(Path.home() / '.local/bin/hermes'), *sys.argv[2:]], env=env()))
    elif command == 'make':
        raise SystemExit(subprocess.call(['make', *sys.argv[2:]], cwd=ROOT, env=env()))
