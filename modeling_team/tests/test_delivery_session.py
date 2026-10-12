"""Public conversation and Host-private tool boundary checks."""
import importlib
import fcntl
import json
import os
import sys
import time
from pathlib import Path

import pytest

from modeling_team.runtimes.delivery import DeliveryRuntimeError

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


@pytest.mark.parametrize("kind", ["evaluation", "repair", "verification"])
def test_finish_conclusion_cannot_hide_unfinished_bound_owner(tmp_path, kind):
    host = session(tmp_path)
    original = host.call_tool
    operation_id = "unfinished"
    if kind == "verification":
        host.verification_ids.add(operation_id)
    else:
        host.operation_ids.add(operation_id)
        host.operation_kinds[operation_id] = kind
    closed = False
    def call(name, arguments, **kwargs):
        if name in {"get_evaluation_status", "get_repair_status", "get_repair_verification_status"}:
            data = {"status": "running", "work_state": "working", "process": {"state": "running"}}
            if closed:
                data.update(status="exited", exit_code=0, work_state="completed", process={"state": "exited"})
            return {"ok": True, "data": data}
        return original(name, arguments, **kwargs)
    host.call_tool = call
    result = host.call_tool("finish_delivery", {"conclusion": "known conclusion"})
    assert result["ok"] and result["data"]["pending_owners"] == [operation_id]
    assert host.activity == "read_only_wait" and host.work_result == "known conclusion"
    closed = True
    assert host.call_tool("finish_delivery", {"conclusion": "known conclusion"})["ok"]
    assert host.activity == "standby"


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


class _StubNativeRuntime:
    """Offline stand-in for DeliveryRuntime inside the _run_delivery loop.

    Holds the first turn open (busy) until the expected number of steers has
    been delivered onto it, mirroring a long-running turn that must not starve
    later sourced input.  ``steer_failures`` simulates the end-of-turn race by
    rejecting the first steers exactly like a stale ``expectedTurnId``.
    """

    def __init__(self, *, steers_to_complete: int = 1, steer_failures: int = 0):
        self.events: list[str] = []
        self.sent: list[str] = []
        self.steered: list[str] = []
        self.steer_attempts = 0
        self.thread_id = 'stub-thread'
        self.turn_id = 'turn-1'
        self.busy = False
        self.process = _StubProcess()
        self._steers_to_complete = steers_to_complete
        self._steer_failures = steer_failures
        self._hold = True
        self._hold_deadline = 0.0

    def start(self):
        self.events.append('start')
        # Hold the first turn open long enough for queued input to arrive and
        # be steered, then self-complete so a broken route still fails fast.
        self._hold_deadline = time.monotonic() + 5

    def send(self, text):
        self.events.append('send')
        self.sent.append(text)
        self.busy = True

    def steer(self, text):
        self.events.append('steer')
        self.steer_attempts += 1
        if self.steer_attempts <= self._steer_failures:
            self._hold = False
            raise DeliveryRuntimeError('Delivery native RPC failed: turn/steer')
        self.steered.append(text)
        if len(self.steered) >= self._steers_to_complete:
            self._hold = False

    def poll(self, timeout: float = 0) -> list[dict]:
        if self.busy:
            if not self._hold or time.monotonic() > self._hold_deadline:
                self.busy = False
                self.events.append('turn_completed')
                return [{'event': 'turn_completed', 'status': 'completed'}]
            time.sleep(0.005)
        return []

    def interrupt(self):
        self.events.append('interrupt')
        self._hold = False

    def close(self):
        self.events.append('close')


class _StubProcess:
    pid = os.getpid()

    def poll(self):
        return 0


def _run_delivery_with_stub(tmp_path, monkeypatch, lines, *, run_ids=None, **stub_kwargs):
    import shutil
    module = importlib.import_module('modeling_team.delivery')
    # Minimal repository layout under tmp_path: the real profile (the loader
    # rejects symlinks) plus placeholder instruction sources, with writable
    # workspaces for the private session state.
    profiles = tmp_path / 'modeling_team/model-profiles'
    profiles.mkdir(parents=True)
    shutil.copyfile(ROOT / 'modeling_team/model-profiles/openai-sol-medium.yaml',
                    profiles / 'openai-sol-medium.yaml')
    package = tmp_path / 'modeling_team/agent-packages/delivery'
    package.mkdir(parents=True)
    (package / 'instructions.md').write_text('stub delivery instructions')
    skill = tmp_path / 'modeling_team/skills/delivery'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('stub delivery skill')
    stub = _StubNativeRuntime(**stub_kwargs)
    monkeypatch.setattr(module, 'DeliveryRuntime', lambda **kwargs: stub)
    read_fd, write_fd = os.pipe()
    monkeypatch.setattr(sys, 'stdin', os.fdopen(read_fd, 'r'))
    for line in lines:
        os.write(write_fd, (line + '\n').encode())
    os.close(write_fd)
    config = {'session_id': 'steer-probe', 'model_profile': 'openai-sol-medium',
              'authorization_reference': 'user-test', 'allowed_sources': [],
              'allowed_operations': ['read'], 'run_ids': run_ids or []}
    result = module._run_delivery(config, repository_root=tmp_path, resume=False)
    return stub, result, json.loads(
        (tmp_path / 'workspaces/delivery-sessions/steer-probe/session.json').read_text())


def test_run_delivery_steers_queued_input_into_the_active_turn_in_order(tmp_path, monkeypatch):
    stub, result, record = _run_delivery_with_stub(
        tmp_path, monkeypatch,
        ['第一条排队的技术补充。', '第二条排队的技术补充。'], steers_to_complete=2)
    # Both packets were steered onto the one still-active turn, in arrival
    # order, before that turn completed; none was sent as a new turn.
    assert result == 2
    assert len(stub.steered) == 2
    assert '第一条排队的技术补充。' in stub.steered[0]
    assert '第二条排队的技术补充。' in stub.steered[1]
    assert stub.events.index('steer') < stub.events.index('turn_completed')
    # Original sourcing metadata rides along unchanged.
    packet = json.loads(stub.steered[0])
    assert packet['text'] == '第一条排队的技术补充。'
    assert packet['kind'] == 'user_input'
    assert packet['authorization_reference'] == 'user-test'
    assert packet['source_reference'].startswith('delivery:steer-probe:')
    assert not any('排队的技术补充' in text for text in stub.sent[1:])
    assert record['native_thread_id'] == 'stub-thread'


def test_run_delivery_pause_is_sourced_guidance_without_forced_interrupt(tmp_path, monkeypatch):
    stub, result, record = _run_delivery_with_stub(tmp_path, monkeypatch, ['暂停'])
    assert 'interrupt' not in stub.events
    packet = json.loads(stub.steered[0])
    assert packet['text'] == '暂停'
    assert 'host_control_result' not in packet
    events = [json.loads(line) for line in (
        tmp_path / 'workspaces/delivery-sessions/steer-probe/session-events.jsonl'
    ).read_text().splitlines()]
    assert not any(entry.get('state') == 'paused' for entry in events)


def test_run_delivery_keeps_packet_queued_when_steer_hits_completed_turn(tmp_path, monkeypatch):
    stub, result, record = _run_delivery_with_stub(
        tmp_path, monkeypatch, ['迟到的排队输入。'], steer_failures=1)
    # The stale steer was attempted exactly once and was not fatal: the packet
    # stayed queued and was delivered by an ordinary turn/start once idle.
    assert stub.steer_attempts == 1
    assert stub.steered == []
    assert any('迟到的排队输入。' in text for text in stub.sent[1:])
    packet = json.loads(next(text for text in stub.sent[1:] if '迟到的排队输入。' in text))
    assert packet['source_reference'].startswith('delivery:steer-probe:')
    assert stub.events.index('steer') < stub.events.index('turn_completed')


def test_bound_public_feedback_body_and_retained_response_are_readable(tmp_path):
    import hashlib
    host = session(tmp_path)
    host.repository_root = tmp_path
    host.run_ids = {"bound"}
    root = tmp_path / "workspaces/modeling-runs/bound/early-feedback/feedback-1"
    root.mkdir(parents=True)
    for name, text in (("feedback.json", '{"status":"partial","answer":"unknown"}'),
                       ("platform-responses/read-1.json", '{"ok":true,"data":{"rows":[]}}')):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        result = host.call_tool("read_delivery_artifact", {"path": str(path)})
        assert result["ok"], result
        assert result["data"]["text"] == text
        assert result["data"]["content_digest"] == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        # The reader reports actual content; it cannot bless a stale binding digest.
        old_digest = result["data"]["content_digest"]
        path.write_text(text + "\n")
        changed = host.call_tool("read_delivery_artifact", {"path": str(path)})
        assert changed["data"]["content_digest"] != old_digest


@pytest.mark.parametrize("outside", ["other-run", "host-path", "symlink", "oversize", "directory"])
def test_public_feedback_reader_preserves_existing_file_boundaries(tmp_path, outside):
    host = session(tmp_path)
    host.repository_root = tmp_path
    host.run_ids = {"bound"}
    root = tmp_path / "workspaces/modeling-runs/bound/early-feedback/feedback-1"
    root.mkdir(parents=True)
    path = root / "feedback.json"
    if outside == "other-run":
        path = tmp_path / "workspaces/modeling-runs/other/early-feedback/feedback.json"
        path.parent.mkdir(parents=True)
        path.write_text("private")
    elif outside == "host-path":
        path = tmp_path / "private.json"
        path.write_text("private")
    elif outside == "symlink":
        target = tmp_path / "private.json"
        target.write_text("private")
        path.symlink_to(target)
    elif outside == "oversize":
        path.write_text("x" * 2_000_001)
    else:
        path.mkdir()
    result = host.call_tool("read_delivery_artifact", {"path": str(path)})
    assert result["ok"] is False, result
