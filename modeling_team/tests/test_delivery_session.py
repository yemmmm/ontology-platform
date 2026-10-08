"""Public conversation and Host-private tool boundary checks."""
import importlib
import fcntl
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def session(tmp_path):
    module = importlib.import_module('modeling_team.delivery')
    source = tmp_path / 'business.md'
    source.write_text('经确认：退货不计入销售额。')
    return module.DeliverySession(
        repository_root=ROOT, session_root=tmp_path / 'session',
        config={'session_id': 'test-delivery', 'model_profile': 'openai-sol-medium',
                'authorization_reference': 'user-test', 'allowed_sources': [str(source)],
                'allowed_operations': ['read'], 'run_ids': []},
    )


def test_only_explicit_business_messages_reach_public_channel(tmp_path):
    host = session(tmp_path)
    assert host.call_tool('emit_user_message', {'kind': 'status', 'text': '正在建模。'})['ok']
    assert host.drain_messages() == [{'kind': 'status', 'text': '正在建模。'}]
    assert host.call_tool('emit_user_message', {'kind': 'tool', 'text': 'PRIVATE'})['ok'] is False
    assert host.drain_messages() == []


def test_host_control_and_private_path_arguments_are_not_model_selected(tmp_path):
    host = session(tmp_path)
    assert host.call_tool('start_run', {'run_id': 'unauthorized'})['ok'] is False
    assert host.call_tool('get_run_status', {'run_id': 'other'})['ok'] is False
    assert host.call_tool('read_delivery_artifact', {'path': '/etc/passwd'})['ok'] is False
    for tool in host.tool_specs():
        assert 'repository_root' not in tool['inputSchema'].get('properties', {})
        assert 'host_session_ref' not in tool['inputSchema'].get('properties', {})


def test_business_input_retains_original_text_and_explicit_model_inheritance(tmp_path):
    host = session(tmp_path)
    text = '第一行\n第二行  原始空格'
    packet = host.accept_user_input(text)
    assert packet['text'] == text
    assert packet['source_reference']
    assert 'question_delivery_id' not in packet
    record = json.loads((host.session_root / 'session.json').read_text())
    assert record['model_binding_source'] == 'coordinator'
    assert record['model_binding']['model'] == 'gpt-6.1-sol'
    assert json.loads((host.session_root / 'user-input.jsonl').read_text()) == packet


def test_artifact_reader_returns_exact_approved_business_source(tmp_path):
    host = session(tmp_path)
    result = host.call_tool('read_delivery_artifact', {'path': str(tmp_path / 'business.md')})
    assert result['ok'] and result['data']['text'] == '经确认：退货不计入销售额。'


def test_resumption_preserves_revocation_and_interruption_history(tmp_path):
    host = session(tmp_path)
    host.allowed_operations.update({'supervise', 'evaluation', 'repair'})
    host.apply_user_control('撤回预算')
    host._save('supervision_interrupted', reason='offline observation')
    module = importlib.import_module('modeling_team.delivery')
    config = dict(host.config, allowed_operations=['read', 'supervise', 'evaluation', 'repair'])
    restored = module.DeliverySession(repository_root=ROOT, session_root=host.session_root,
                                      config=config, resume=True)
    assert restored.allowed_operations == {'read', 'supervise'}
    events = [json.loads(line) for line in (host.session_root / 'session-events.jsonl').read_text().splitlines()]
    assert any(event.get('reason') == 'offline observation' for event in events)


def test_active_owner_rejects_second_wrapper_before_native_start(tmp_path):
    module = importlib.import_module('modeling_team.delivery')
    config = tmp_path / 'config.yaml'
    config.write_text('session_id: owner-test\n')
    parent = tmp_path / 'workspaces/delivery-sessions'
    parent.mkdir(parents=True)
    with (parent / '.supervisor-owner-test.lock').open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='active supervisor'):
            module.run_delivery(config, repository_root=tmp_path, resume=True)


def test_bound_private_artifacts_and_unknown_request_ledger_are_readable(tmp_path, monkeypatch):
    host = session(tmp_path)
    module = importlib.import_module('modeling_team.delivery')
    root = tmp_path / 'run'
    (root / 'competency-questions/private').mkdir(parents=True)
    (root / 'control').mkdir()
    cq = root / 'competency-questions/private/draft.json'
    cq.write_text('{"private": "CQ-CANARY"}')
    (root / 'control/host-requests.jsonl').write_text('{"request_id":"unknown-request"}\n')
    (root / 'state.json').write_text('{"platform_binding":{"project_id":"p","ontology_ids":["o"]}}')
    host.run_ids.add('bound-run')
    monkeypatch.setattr(module, 'resolve_run_root', lambda *args, **kwargs: (root, tmp_path))
    assert host.call_tool('read_delivery_artifact', {'path': str(cq)})['data']['text'] == cq.read_text()
    ledger = host.call_tool('read_delivery_artifact', {'path': str(root / 'control/host-requests.jsonl')})
    assert 'unknown-request' in ledger['data']['text']
    assert {'project_id': 'p', 'ontology_ids': ['o']} in host._readback_scopes()
    assert host.drain_messages() == []
