#!/usr/bin/env python3
"""Offline native protocol fixture. Produces tool calls; never runs a model."""
import json
import os
import sys
from pathlib import Path

home = Path(os.environ['CODEX_HOME'])
trace = home / 'protocol.jsonl'
turn = 0
pending = None
thread_id = 'delivery-native-thread'
thread_count = 0
# Effective feature state, mirroring the installed server's defaults.  Unknown
# config keys (for example default_tools_enabled) never touch this state; only
# a real per-thread feature overlay does.
features = {
    'shell_tool': True,
    'sleep_tool': True,
    'view_image': True,
    'goals': True,
    'multi_agent': True,
    'multi_agent_v2': False,
    'fast_mode': True,
}
# The runtime rebuilds a minimal child environment, so tests select behaviours
# with marker files inside the private runtime home instead of env vars.
ignore_overlay = (home / 'ignore_overlay_features').exists()
hold_turn_for_steer = (home / 'hold_turn_for_steer').exists()
notification_burst = int((home / 'notification_burst').read_text()) if (home / 'notification_burst').exists() else 0

def emit(value):
    with (home / 'server-events.jsonl').open('a') as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + '\n')
    print(json.dumps(value, ensure_ascii=False), flush=True)

for line in sys.stdin:
    value = json.loads(line)
    with trace.open('a') as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + '\n')
    method = value.get('method')
    request_id = value.get('id')
    params = value.get('params', {})
    if method == 'initialize':
        emit({'id': request_id, 'result': {'userAgent': 'offline-fixture'}})
    elif method == 'thread/start':
        thread_count += 1
        thread_id = 'delivery-native-thread' + (f'-{thread_count}' if thread_count > 1 else '')
        assert params['approvalPolicy'] == 'never'
        assert 'ONTOLOGY_PLATFORM_ADMIN_API_KEY' not in os.environ
        assert 'DEEPSEEK_API_KEY' not in os.environ
        if not ignore_overlay:
            overlay = (params.get('config') or {}).get('features') or {}
            for name, state in overlay.items():
                if name in features:
                    features[name] = bool(state)
        emit({'id': request_id, 'result': {'thread': {'id': thread_id}}})
    elif method == 'experimentalFeature/list':
        emit({'id': request_id, 'result': {'data': [
            {'name': name, 'enabled': state} for name, state in features.items()
        ]}})
    elif method == 'turn/start':
        turn += 1
        pending = f'turn-{turn}'
        emit({'id': request_id, 'result': {'turn': {'id': pending}}})
        emit({'method': 'item/agentMessage/delta', 'params': {'delta': 'PRIVATE-HIDDEN-CANARY'}})
        for _ in range(notification_burst):
            emit({'method': 'item/agentMessage/delta', 'params': {'delta': 'x'}})
        if not hold_turn_for_steer:
            emit({'id': 700 + turn, 'method': 'item/tool/call', 'params': {
                'threadId': thread_id, 'turnId': pending,
                'callId': f'call-{turn}', 'namespace': None, 'tool': 'emit_user_message',
                'arguments': {'kind': 'status', 'text': '正在处理业务资料。'},
            }})
    elif method == 'turn/steer':
        if pending is None or params.get('threadId') != thread_id \
                or params.get('expectedTurnId') != pending:
            emit({'id': request_id, 'error': {
                'code': -32001, 'message': 'expected turn is not active'}})
        else:
            # The steered input reaches the live turn; the turn then ends after
            # consuming it, so steered input provably precedes completion.
            emit({'id': request_id, 'result': {'turnId': pending}})
            emit({'method': 'item/agentMessage/delta', 'params': {'delta': 'PRIVATE-STEERED-CANARY'}})
            emit({'method': 'turn/completed', 'params': {'turn': {'id': pending, 'status': 'completed'}}})
            pending = None
    elif method == 'test/complete-turn':
        emit({'id': request_id, 'result': {}})
        emit({'method': 'turn/completed', 'params': {'turn': {'id': pending, 'status': 'completed'}}})
        pending = None
    elif method == 'turn/interrupt':
        emit({'id': request_id, 'result': {}})
        emit({'method': 'turn/completed', 'params': {'turn': {'id': pending, 'status': 'interrupted'}}})
        pending = None
    elif request_id is not None and 'result' in value and pending is not None:
        emit({'method': 'turn/completed', 'params': {'turn': {'id': pending, 'status': 'completed'}}})
        pending = None
