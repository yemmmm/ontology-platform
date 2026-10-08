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

def emit(value):
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
        assert params['config']['default_tools_enabled'] is False
        assert params['approvalPolicy'] == 'never'
        assert 'ONTOLOGY_PLATFORM_ADMIN_API_KEY' not in os.environ
        assert 'DEEPSEEK_API_KEY' not in os.environ
        emit({'id': request_id, 'result': {'thread': {'id': 'delivery-native-thread'}}})
    elif method == 'turn/start':
        turn += 1
        pending = f'turn-{turn}'
        emit({'id': request_id, 'result': {'turn': {'id': pending}}})
        emit({'method': 'item/agentMessage/delta', 'params': {'delta': 'PRIVATE-HIDDEN-CANARY'}})
        emit({'id': 700 + turn, 'method': 'item/tool/call', 'params': {
            'threadId': 'delivery-native-thread', 'turnId': pending,
            'callId': f'call-{turn}', 'namespace': None, 'tool': 'emit_user_message',
            'arguments': {'kind': 'status', 'text': '正在处理业务资料。'},
        }})
    elif method == 'turn/interrupt':
        emit({'id': request_id, 'result': {}})
        emit({'method': 'turn/completed', 'params': {'turn': {'id': pending, 'status': 'interrupted'}}})
    elif request_id is not None and 'result' in value:
        emit({'method': 'turn/completed', 'params': {'turn': {'id': pending, 'status': 'completed'}}})
