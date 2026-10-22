"""Exercise the Delivery native wire boundary using an offline subprocess.

The offline double in tests/fixtures/delivery/codex_app_server.py mirrors the
verified behavior of the installed Codex app-server (/agent/bin/real-codex
0.161.0): unknown ``thread/start`` config keys are accepted and silently
ignored, ``experimentalFeature/list`` reports the thread's refreshed feature
state, and ``turn/steer`` delivers input into the currently active turn while
rejecting a stale ``expectedTurnId``.  Those facts are why a request flag such
as ``default_tools_enabled`` could never prove the effective tool boundary,
why ``DeliveryRuntime.start`` fails closed unless the running server reports
the native tool features as off, and busy-turn input now waits for natural completion before starting a new turn.
"""
from __future__ import annotations

import importlib
import json
import os
import time
import tomllib
from pathlib import Path

import pytest

from modeling_team.model_routing import load_team_model_profile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'modeling_team/tests/fixtures/delivery/codex_app_server.py'

EXPECTED_BOUNDARY_CONFIG = {
    'web_search': 'disabled',
    'features': {
        'shell_tool': False,
        'sleep_tool': False,
        'view_image': False,
        'goals': False,
        'multi_agent': False,
        'multi_agent_v2': False,
    },
    'tools': {
        'experimental_request_user_input': {'enabled': False},
        'update_plan': {'enabled': False},
    },
}


def _messages(runtime) -> list[dict]:
    return [
        json.loads(line)
        for line in (runtime.home / 'protocol.jsonl').read_text().splitlines()
    ]


def _drive_turn(runtime, text: str) -> list[dict]:
    runtime.send(text)
    observed: list[dict] = []
    deadline = time.monotonic() + 3
    while runtime.busy and time.monotonic() < deadline:
        observed.extend(runtime.poll(0.05))
    return observed


def _runtime(module, profile, home: Path, **overrides):
    settings = dict(
        binding=profile.binding_for('coordinator'), home=home,
        instructions='You are an independent Delivery.',
        tools=[{'name': 'emit_user_message', 'description': 'Business output.',
                'inputSchema': {'type': 'object', 'properties': {}}}],
        tool_handler=lambda name, args: {'ok': True},
        codex_binary=str(FIXTURE), authenticate=False,
    )
    settings.update(overrides)
    return module.DeliveryRuntime(**settings)


def test_phase_thread_uses_same_process_and_ignores_old_completion(tmp_path):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    runtime = _runtime(module, profile, tmp_path / 'native')
    try:
        runtime.start()
        old = runtime.thread_id
        pid = runtime.process.pid
        identity = runtime.new_thread()
        assert identity['runtime_session_id'] != old
        assert runtime.process.pid == pid
        starts = [v['params'] for v in _messages(runtime) if v.get('method') == 'thread/start']
        assert len(starts) == 2 and starts[0] == starts[1]
        runtime.send('New phase with authoritative handoff facts.')
        assert runtime.busy
        runtime._handle({'method': 'turn/completed', 'params': {
            'threadId': old, 'turn': {'id': 'old-turn', 'status': 'completed'}}})
        assert runtime.busy
        runtime._handle({'method': 'thread/tokenUsage/updated', 'params': {
            'threadId': old, 'turnId': 'old-turn', 'tokenUsage': {'total': {
                'inputTokens': 123, 'outputTokens': 7}}}})
        usage = json.loads((runtime.home / 'usage-events.jsonl').read_text().splitlines()[-1])
        assert usage['thread_id'] == old and usage['runtime_session_id'] == old
        with pytest.raises(module.DeliveryRuntimeError, match='busy'):
            runtime.new_thread()
    finally:
        runtime.close()


@pytest.mark.parametrize('profile_id,external', [
    ('openai-sol-medium', False), ('glm-flash-high', True),
])
def test_delivery_context_override_is_root_config_and_keeps_tool_boundary(
    tmp_path, profile_id, external,
):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, profile_id)
    runtime = _runtime(
        module, profile, tmp_path / 'native',
        model_context_window=544000, model_auto_compact_token_limit=489600,
        provider_base_url='http://127.0.0.1:1/' if external else None,
    )
    try:
        runtime.start()
        config = tomllib.loads((runtime.home / 'config.toml').read_text())
        assert config['model_context_window'] == 544000
        assert config['model_auto_compact_token_limit'] == 489600
        assert config['model'] == profile.binding_for('coordinator').model
        if external:
            catalog = json.loads(Path(config['model_catalog_json']).read_text())
            assert len(catalog['models']) == 1
            metadata = catalog['models'][0]
            assert metadata['slug'] == config['model']
            assert metadata['context_window'] == 544000
            assert metadata['max_context_window'] == 544000
            assert metadata['effective_context_window_percent'] == 95
        else:
            assert 'model_catalog_json' not in config
        thread = next(x['params'] for x in _messages(runtime)
                      if x.get('method') == 'thread/start')
        assert thread['config'] == EXPECTED_BOUNDARY_CONFIG
        assert thread['sandbox'] == 'read-only'
    finally:
        runtime.close()


@pytest.mark.parametrize('external', [False, True])
def test_delivery_default_leaves_model_context_settings_unset(tmp_path, external):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    runtime = _runtime(module, profile, tmp_path / 'native',
                       provider_base_url='http://127.0.0.1:1/' if external else None)
    try:
        runtime.start()
        config = tomllib.loads((runtime.home / 'config.toml').read_text())
        assert 'model_context_window' not in config
        assert 'model_auto_compact_token_limit' not in config
        assert 'model_catalog_json' not in config
    finally:
        runtime.close()


@pytest.mark.parametrize('setting,value', [
    ('model_context_window', 0),
    ('model_context_window', True),
    ('model_auto_compact_token_limit', '489600'),
])
def test_delivery_rejects_invalid_context_config_before_native_start(tmp_path, setting, value):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    runtime = _runtime(module, profile, tmp_path / 'native', **{setting: value})
    with pytest.raises(module.DeliveryRuntimeError, match=f'{setting} must be a positive integer'):
        runtime.start()
    assert runtime.process is None


def test_native_thread_tool_dispatch_and_private_message_boundary(tmp_path, monkeypatch):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    calls = []
    monkeypatch.setenv('ONTOLOGY_PLATFORM_ADMIN_API_KEY', 'ADMIN-CANARY')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'PROVIDER-CANARY')
    runtime = _runtime(module, profile, tmp_path / 'native',
                       tool_handler=lambda name, args: calls.append((name, args)) or {'ok': True})
    try:
        runtime.start()
        assert runtime.thread_id == 'delivery-native-thread'
        observed = _drive_turn(runtime, '用户只提供业务资料。')
        assert not runtime.busy
        assert calls == [('emit_user_message', {'kind': 'status', 'text': '正在处理业务资料。'})]
        assert 'PRIVATE-HIDDEN-CANARY' not in json.dumps(observed)
        messages = _messages(runtime)
        thread = next(x['params'] for x in messages if x.get('method') == 'thread/start')
        assert thread['model'] == profile.binding_for('coordinator').model
        assert thread['baseInstructions'] == ''
        assert thread['developerInstructions'] == 'You are an independent Delivery.'
        assert thread['dynamicTools'][0]['type'] == 'function'
        assert thread['dynamicTools'][0]['inputSchema'] == {'type': 'object', 'properties': {}}
        # The boundary projection uses only keys the installed app-server
        # actually honors; the previous fake flag is gone entirely.
        assert thread['config'] == EXPECTED_BOUNDARY_CONFIG
        assert 'default_tools_enabled' not in thread['config']
        # Effective state is confirmed against the running server for this
        # exact thread, after thread/start and before any turn.
        feature_call = next(
            x for x in messages if x.get('method') == 'experimentalFeature/list')
        assert feature_call['params']['threadId'] == 'delivery-native-thread'
        assert messages.index(feature_call) > max(
            i for i, x in enumerate(messages) if x.get('method') == 'thread/start')
        response = next(x for x in messages if x.get('id') == 701 and 'result' in x)
        assert response['result']['success'] is True
        assert response['result']['contentItems'][0]['type'] == 'inputText'
    finally:
        runtime.close()
    assert runtime.process.poll() is not None


def test_start_fails_closed_when_server_ignores_boundary_config(tmp_path):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    runtime = _runtime(module, profile, tmp_path / 'native', instructions='Delivery')
    (tmp_path / 'native').mkdir(parents=True)
    (tmp_path / 'native' / 'ignore_overlay_features').write_text('')
    with pytest.raises(module.DeliveryRuntimeError, match='native tool boundary'):
        runtime.start()
    assert runtime.process.poll() is not None
    # thread/start itself was accepted by the server: an accepted request is
    # not evidence of an effective boundary, only the reported feature state is.
    messages = _messages(runtime)
    assert any(x.get('method') == 'thread/start' for x in messages)
    reported = next(
        x for x in messages if x.get('method') == 'experimentalFeature/list')
    assert reported['params']['threadId'] == 'delivery-native-thread'
    assert not any(x.get('method') == 'turn/start' for x in messages)


def test_unsupported_fake_request_flag_alone_cannot_prove_boundary(tmp_path, monkeypatch):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    # The legacy request shape: a config key the installed app-server accepts
    # and silently ignores.  The offline double accepts it exactly the same way.
    monkeypatch.setattr(
        module, '_NATIVE_TOOL_BOUNDARY_CONFIG',
        {'default_tools_enabled': False, 'web_search': 'disabled'})
    runtime = _runtime(module, profile, tmp_path / 'native', instructions='Delivery')
    with pytest.raises(module.DeliveryRuntimeError, match='native tool boundary'):
        runtime.start()
    assert runtime.process.poll() is not None
    messages = _messages(runtime)
    thread = next(x['params'] for x in messages if x.get('method') == 'thread/start')
    assert thread['config']['default_tools_enabled'] is False
    # The server accepted the request and still reports the native builtins on:
    # the effective check, not the request flag, is what fails the start.
    feature_call = next(
        x for x in messages if x.get('method') == 'experimentalFeature/list')
    assert feature_call['params']['threadId'] == 'delivery-native-thread'
    assert not any(x.get('method') == 'turn/start' for x in messages)


def test_explicit_service_tier_wins_over_ambient(tmp_path, monkeypatch):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    monkeypatch.setenv('MODELING_TEAM_CODEX_SERVICE_TIER', 'fast')
    runtime = _runtime(module, profile, tmp_path / 'native', instructions='Delivery',
                       tools=[], tool_handler=lambda *_: {}, service_tier='default')
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
    runtime = _runtime(module, profile, tmp_path / 'native', instructions='Delivery',
                       tools=[], tool_handler=lambda *_: {'ok': True})
    try:
        runtime.start()
        for text in ['生产已结束。', '继续独立验收。']:
            _drive_turn(runtime, text)
            assert not runtime.busy
        assert runtime.thread_id == 'delivery-native-thread'
        # Idle turns are ordinary turn/start calls; nothing was steered.
        messages = _messages(runtime)
        assert len([x for x in messages if x.get('method') == 'turn/start']) == 2
        assert not any(x.get('method') == 'turn/steer' for x in messages)
    finally:
        runtime.close()


def test_busy_turn_input_waits_for_completed_native_turn(tmp_path):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    native = tmp_path / 'native'
    native.mkdir(parents=True)
    (native / 'hold_turn_for_steer').write_text('')
    runtime = _runtime(module, profile, native)
    try:
        runtime.start()
        runtime.send('首轮业务输入。')
        runtime.steer('排队的技术补充。')
        runtime.poll(0.05)
        assert runtime.busy and runtime.turn_id == 'turn-1'
        assert not any(x.get('method') in {'turn/steer', 'turn/interrupt'} for x in _messages(runtime))
        assert len([x for x in _messages(runtime) if x.get('method') == 'turn/start']) == 1
        runtime._rpc('test/complete-turn', {})
        deadline = time.monotonic() + 2
        while runtime.turn_id == 'turn-1' and time.monotonic() < deadline:
            runtime.poll(0.05)
        assert runtime.turn_id == 'turn-2'
        messages = _messages(runtime)
        starts = [x for x in messages if x.get('method') == 'turn/start']
        assert len(starts) == 2
        assert starts[1]['params']['input'][0]['text'] == '排队的技术补充。'
        assert len([x for x in messages if x.get('method') == 'thread/start']) == 1
        assert not any(x.get('method') in {'turn/steer', 'turn/interrupt'} for x in messages)
    finally:
        runtime.close()


def test_input_after_completed_turn_starts_next_turn_without_stale_steer(tmp_path):
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    runtime = _runtime(module, profile, tmp_path / 'native')
    try:
        runtime.start()
        _drive_turn(runtime, '首轮业务输入。')
        runtime.steer('迟到的排队输入。')
        runtime.poll(0)
        assert runtime.turn_id == 'turn-2'
        messages = _messages(runtime)
        assert not any(x.get('method') == 'turn/steer' for x in messages)
        assert len([x for x in messages if x.get('method') == 'turn/start']) == 2
        assert len([x for x in messages if x.get('method') == 'thread/start']) == 1
    finally:
        runtime.close()


REAL_CODEX_BOUNDARY_ENV = 'MODELING_TEAM_DELIVERY_LIVE_CODEX_BOUNDARY'
REAL_CODEX_BOUNDARY_BINARY = '/agent/bin/real-codex'
# Native builtins the boundary projection removes on the installed server.
# ``request_user_input_async`` and the catalog code-mode/collaboration surfaces
# of models like gpt-6.1-sol are model-forced on this build and remain a
# documented live-runtime limit, so they are asserted only by the manual probe
# evidence, not by this opt-in check.
FORBIDDEN_NATIVE_TOOLS = (
    'exec_command', 'write_stdin', 'view_image', 'sleep',
    'get_goal', 'create_goal', 'update_goal', 'update_plan',
    'request_user_input',
)


def _captured_tool_names(request_bodies: list[str]) -> set[str]:
    """Structurally collect every offered tool name from Responses requests.

    Covers flat top-level ``tools`` and the ``additional_tools`` namespaces
    (direct tools plus ``### `name` `` nested sections) used by catalog
    code-mode models; prose examples inside descriptions do not match.
    """
    import re

    names: set[str] = set()
    for body in request_bodies:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            continue
        for tool in parsed.get('tools', []):
            if tool.get('name'):
                names.add(tool['name'])
        for item in parsed.get('input', []):
            if item.get('type') != 'additional_tools':
                continue
            for namespace in item.get('tools', []):
                for sub in namespace.get('tools', []):
                    if sub.get('name'):
                        names.add(sub['name'])
                    names.update(re.findall(
                        r'^### `([a-zA-Z_0-9]+)`', sub.get('description') or '',
                        re.MULTILINE))
    return names


def test_live_real_codex_server_honors_boundary(tmp_path):
    """Opt-in live check against the installed app-server; skips by default.

    Runs the real DeliveryRuntime start (including the effective-feature
    verification) plus one generic canary turn against a loopback Responses
    provider that captures the outbound model request.  No Codex subscription
    auth, no real provider, no business input, no semantic start.
    """
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    pytest.importorskip('http.server')
    if os.environ.get(REAL_CODEX_BOUNDARY_ENV) != '1':
        pytest.skip(f'set {REAL_CODEX_BOUNDARY_ENV}=1 to probe the real server')
    if not Path(REAL_CODEX_BOUNDARY_BINARY).exists():
        pytest.skip('installed real-codex app-server not present')

    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'openai-sol-medium')
    bodies: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def _read_body(self) -> bytes:
            length = int(self.headers.get('content-length') or 0)
            return self.rfile.read(length) if length else b''

        def do_GET(self):
            self._read_body()
            payload = json.dumps({'data': [{'id': 'boundary-probe-model'}]}).encode()
            self.send_response(200)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            bodies.append(self._read_body().decode('utf-8', 'replace'))
            payload = json.dumps({'error': {'message': 'probe-capture-complete',
                                            'type': 'probe'}}).encode()
            self.send_response(500)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with socket.socket() as probe_socket:
        probe_socket.bind(('127.0.0.1', 0))
        port = probe_socket.getsockname()[1]
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    runtime = _runtime(
        module, profile, tmp_path / 'native',
        instructions='Independent Delivery boundary probe.',
        codex_binary=REAL_CODEX_BOUNDARY_BINARY, service_tier='default',
        provider_base_url=f'http://127.0.0.1:{port}/')
    try:
        runtime.start()
        runtime.send('boundary probe canary')
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not bodies:
            runtime.poll(0.2)
    finally:
        runtime.close()
        server.shutdown()
    names = _captured_tool_names(bodies)
    assert bodies, 'no outbound model request was captured'
    assert 'emit_user_message' in names, sorted(names)
    leaked = sorted(set(FORBIDDEN_NATIVE_TOOLS) & names)
    assert not leaked, f'native builtins still offered: {leaked}'


def test_real_codex_external_delivery_context_window(tmp_path):
    """Verify usable capacity, not just accepted TOML, with a loopback model."""
    import shutil
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    if os.environ.get(REAL_CODEX_BOUNDARY_ENV) != '1':
        pytest.skip(f'set {REAL_CODEX_BOUNDARY_ENV}=1 to probe the real server')
    executable = shutil.which('codex')
    if executable is None:
        pytest.skip('Codex app-server not installed')
    module = importlib.import_module('modeling_team.runtimes.delivery')
    profile = load_team_model_profile(ROOT, 'glm-flash-high')
    bodies = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            bodies.append(json.loads(self.rfile.read(int(self.headers['content-length']))))
            item = {'id': 'msg-window-probe', 'type': 'message', 'role': 'assistant',
                    'status': 'completed', 'content': [
                        {'type': 'output_text', 'text': 'probe-ok', 'annotations': []}]}
            response = {'id': 'window-probe-response', 'object': 'response',
                        'model': 'glm-5.3-flash', 'status': 'completed',
                        'created_at': int(time.time()), 'output': [item], 'usage': {
                            'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12,
                            'input_tokens_details': {'cached_tokens': 0},
                            'output_tokens_details': {'reasoning_tokens': 0}}}
            events = [
                {'type': 'response.created', 'response': {
                    **response, 'status': 'in_progress', 'output': []}},
                {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                {'type': 'response.completed', 'response': response},
            ]
            payload = ''.join('data: ' + json.dumps(event) + '\n\n'
                              for event in events).encode()
            self.send_response(200)
            self.send_header('content-type', 'text/event-stream')
            self.send_header('content-length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    runtime = _runtime(
        module, profile, tmp_path / 'native', codex_binary=executable,
        provider_base_url=f'http://127.0.0.1:{server.server_port}/',
        model_context_window=544000, model_auto_compact_token_limit=489600,
    )
    try:
        runtime.start()
        runtime.send('window probe OLD_PHASE_WINDOW_PROBE')
        deadline = time.monotonic() + 20
        while runtime.busy and time.monotonic() < deadline:
            runtime.poll(0.1)
        assert not runtime.busy
        windows = []
        for path in runtime.home.rglob('rollout-*.jsonl'):
            for line in path.read_text().splitlines():
                record = json.loads(line)
                payload = record.get('payload', {})
                if record['type'] == 'event_msg' and payload.get('type') == 'token_count':
                    if payload.get('info'):
                        windows.append(payload['info']['model_context_window'])
        assert windows and set(windows) == {516800}, windows
        assert len(bodies) == 1
        assert bodies[0]['model'] == 'glm-5.3-flash'
        assert bodies[0]['reasoning']['effort'] == 'high'
        assert _captured_tool_names([json.dumps(bodies[0])]) == {'emit_user_message'}
        original = runtime.thread_id
        pid = runtime.process.pid
        runtime.new_thread()
        assert runtime.thread_id != original and runtime.process.pid == pid
        runtime.send('phase two current facts only')
        deadline = time.monotonic() + 20
        while runtime.busy and time.monotonic() < deadline:
            runtime.poll(0.1)
        assert not runtime.busy and len(bodies) == 2
        assert 'OLD_PHASE_WINDOW_PROBE' not in json.dumps(bodies[1])
        assert 'phase two current facts only' in json.dumps(bodies[1])
        assert _captured_tool_names([json.dumps(bodies[1])]) == {'emit_user_message'}
    finally:
        runtime.close()
        server.shutdown()
        server.server_close()
