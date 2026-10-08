"""Exercise the Delivery native wire boundary using an offline subprocess."""
from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

from modeling_team.model_routing import load_team_model_profile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'modeling_team/tests/fixtures/delivery/codex_app_server.py'


def test_native_thread_tool_dispatch_and_private_message_boundary(tmp_path, monkeypatch):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    calls = []
    monkeypatch.setenv('ONTOLOGY_PLATFORM_ADMIN_API_KEY', 'ADMIN-CANARY')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'PROVIDER-CANARY')
    runtime = module.DeliveryRuntime(
        binding=profile.binding_for('coordinator'), home=tmp_path / 'native',
        instructions='You are an independent Delivery.',
        tools=[{'name': 'emit_user_message', 'description': 'Business output.',
                'inputSchema': {'type': 'object', 'properties': {}}}],
        tool_handler=lambda name, args: calls.append((name, args)) or {'ok': True},
        codex_binary=str(FIXTURE), authenticate=False,
    )
    try:
        runtime.start()
        assert runtime.thread_id == 'delivery-native-thread'
        runtime.send('用户只提供业务资料。')
        deadline = time.monotonic() + 3
        observed = []
        while runtime.busy and time.monotonic() < deadline:
            observed.extend(runtime.poll(0.05))
        assert not runtime.busy
        assert calls == [('emit_user_message', {'kind': 'status', 'text': '正在处理业务资料。'})]
        assert 'PRIVATE-HIDDEN-CANARY' not in json.dumps(observed)
        messages = [json.loads(line) for line in (runtime.home / 'protocol.jsonl').read_text().splitlines()]
        thread = next(x['params'] for x in messages if x.get('method') == 'thread/start')
        assert thread['model'] == profile.binding_for('coordinator').model
        assert thread['baseInstructions'] == ''
        assert thread['developerInstructions'] == 'You are an independent Delivery.'
        assert thread['dynamicTools'][0]['type'] == 'function'
        assert thread['config']['default_tools_enabled'] is False
        response = next(x for x in messages if x.get('id') == 701 and 'result' in x)
        assert response['result']['success'] is True
        assert response['result']['contentItems'][0]['type'] == 'inputText'
    finally:
        runtime.close()
    assert runtime.process.poll() is not None


def test_explicit_service_tier_wins_over_ambient(tmp_path, monkeypatch):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    monkeypatch.setenv('MODELING_TEAM_CODEX_SERVICE_TIER', 'fast')
    runtime = module.DeliveryRuntime(
        binding=profile.binding_for('coordinator'), home=tmp_path / 'native',
        instructions='Delivery', tools=[], tool_handler=lambda *_: {},
        codex_binary=str(FIXTURE), service_tier='default', authenticate=False,
    )
    try:
        runtime.start()
        text = (runtime.home / 'config.toml').read_text()
        assert 'service_tier = "fast"' not in text
        assert 'ADMIN-CANARY' not in text
    finally:
        runtime.close()


def test_native_turn_remains_independent_across_multiple_turns(tmp_path):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    runtime = module.DeliveryRuntime(
        binding=profile.binding_for('coordinator'), home=tmp_path / 'native',
        instructions='Delivery', tools=[], tool_handler=lambda *_: {'ok': True},
        codex_binary=str(FIXTURE), authenticate=False,
    )
    try:
        runtime.start()
        for text in ['生产已结束。', '继续独立验收。']:
            runtime.send(text)
            deadline = time.monotonic() + 3
            while runtime.busy and time.monotonic() < deadline:
                runtime.poll(0.05)
            assert not runtime.busy
        assert runtime.thread_id == 'delivery-native-thread'
    finally:
        runtime.close()
