"""Pinned DSH process and SDK, deterministic local Messages server, no external LLM."""
import json
import threading
import time
from pathlib import Path

import pytest

from modeling_team.model_routing import load_team_model_profile, resolve_delivery_model_binding
from modeling_team.runtimes.delivery import DeliveryRuntimeError
from modeling_team.runtimes.dsh_delivery import DSHDeliveryRuntime, validate_delivery_runtime
from modeling_team.tests.test_dsh_runtime import LocalMessagesProvider, wait_until

ROOT = Path(__file__).resolve().parents[2]
SPEC = {"name": "delivery_probe", "description": "Engineering probe.",
        "inputSchema": {"type": "object", "properties": {}}}


@pytest.fixture
def runtime(tmp_path):
    binding, _ = resolve_delivery_model_binding(load_team_model_profile(ROOT, "dsh-deepseek-flash-low"))
    value = DSHDeliveryRuntime(binding=binding, home=tmp_path / "native",
        instructions="Engineering fixture only.", tools=[SPEC],
        tool_handler=lambda name, args, **kwargs: {"ok": False, "error": {"code": "test"},
            "coverage": {"complete": False}, "continuation": {"offset": 3}},
        session_id="engineering-delivery", provider_factory=LocalMessagesProvider)
    try:
        value.start()
        value.provider.tool_name = SPEC["name"]
        value.provider.tool_arguments = {}
        yield value
    finally:
        value.close()


def settle(runtime):
    wait_until(lambda: not runtime.busy)
    return runtime.poll(0)


def test_runtime_selection_defaults_and_precise_setting_errors():
    codex, _ = resolve_delivery_model_binding(load_team_model_profile(ROOT, "openai-sol-medium"))
    dsh, _ = resolve_delivery_model_binding(load_team_model_profile(ROOT, "dsh-deepseek-flash-low"))
    assert validate_delivery_runtime({}, codex) == "codex"
    assert validate_delivery_runtime({"runtime": "dsh"}, dsh) == "dsh"
    with pytest.raises(ValueError, match="unsupported-runtime-provider"):
        validate_delivery_runtime({"runtime": "dsh"}, codex)
    for field in ("service_tier", "model_context_window", "model_auto_compact_token_limit"):
        with pytest.raises(ValueError, match=f"field={field}"):
            validate_delivery_runtime({"runtime": "dsh", field: 1}, dsh)


def test_real_tools_json_call_identity_and_turn_end(runtime):
    calls = []
    registered = runtime.provider.usage_bindings[runtime.runtime_session_id]
    assert registered["role"] == "delivery"
    assert registered["session_id"] == "engineering-delivery"
    assert registered["process_instance"] == runtime.process_instance
    handler = runtime.tool_handler
    runtime.tool_handler = lambda name, args, **kw: (calls.append((name, args, kw)) or handler(name, args))
    receipt = runtime.send(json.dumps({"kind": "user_input", "message_id": "user-1", "text": "test"}))
    events = settle(runtime)
    row = runtime.dispatch_status()[0]
    assert receipt["message_id"] == row["message_id"]
    assert row["state"] == "settled" and row["claimed_seq"] < row["turn_end_seq"]
    assert any(event["event"] == "activity_ended" for event in events)
    assert runtime.thread_id is None
    assert calls[0][2]["call_identity"].startswith(f"engineering-delivery:{runtime.runtime_session_id}:")
    requests = runtime.provider.requests
    assert len(requests) == 2
    assert requests[0]["tools"] == [{"name": SPEC["name"], "description": SPEC["description"],
                                       "input_schema": SPEC["inputSchema"]}]
    blocks = [block for message in requests[1]["messages"] for block in message.get("content", [])
              if block.get("type") == "tool_result"]
    result = json.loads(blocks[0]["content"][0]["text"])
    assert result == {"ok": False, "error": {"code": "test"},
                      "coverage": {"complete": False}, "continuation": {"offset": 3}}
    time.sleep(.15)
    assert len(requests) == 2  # no-change wait has no inference


def test_provider_failure_is_failed_activity_and_exposes_safe_code(runtime):
    runtime.provider.fail = True
    runtime.send(json.dumps({'text': 'engineering failure'}))
    events = settle(runtime)
    error = next(event for event in events if event['event'] == 'provider_error')
    assert error['code'] == 'QUOTA' and error['http_status'] == 402
    ended = next(event for event in events if event['event'] == 'activity_ended')
    assert ended['reason']['kind'] == 'error'
    assert ended['status'] == 'failed'
    assert len(runtime.provider.requests) == 1


def test_context_error_classification_reaches_real_dsh_without_automatic_replay(runtime):
    runtime.provider.fail = True
    runtime.provider.failure_status = 400
    runtime.provider.failure_body = {'type': 'error', 'error': {
        'type': 'invalid_request_error', 'code': 'context_window_exceeded',
        'message': 'DeepSeek HTTP 400: context window exceeded'}}
    runtime.send(json.dumps({'text': 'engineering context failure'}))
    events = settle(runtime)
    error = next(event for event in events if event['event'] == 'provider_error')
    assert error['code'] == 'CONTEXT_WINDOW_EXCEEDED' and error['http_status'] == 400
    assert len(runtime.provider.requests) == 1


def test_delivery_instantiates_native_compaction_dependencies(runtime):
    actual = runtime._rpc('host/inspect', {})
    assert actual.get('services') == {'tokenMeter': True, 'compaction': True}


def test_context_failure_after_history_does_not_start_summary_or_replay(runtime):
    runtime.provider.tool_calls = False
    runtime.send(json.dumps({'text': 'Prior authorized history. ' * 2_000}))
    settle(runtime)
    runtime.provider.fail = True
    runtime.provider.failure_status = 400
    runtime.provider.failure_body = {'type': 'error', 'error': {
        'type': 'invalid_request_error', 'code': 'context_window_exceeded',
        'message': 'context window exceeded'}}
    runtime.send(json.dumps({'text': 'Continue the same task.'}))
    events = settle(runtime)
    assert next(e for e in events if e['event'] == 'provider_error')['code'] == 'CONTEXT_WINDOW_EXCEEDED'
    assert len(runtime.provider.requests) == 2  # original history + failed request only


def test_delivery_compacts_pressure_in_original_session_before_next_request(runtime):
    runtime.provider.tool_calls = False
    runtime.provider.input_tokens = 400_000
    identity = runtime.runtime_session_id
    history = 'COMPACT_OLD_HISTORY ' * 32_000
    runtime.send(json.dumps({'kind': 'user_input', 'text': history}))
    settle(runtime)
    assert len(runtime.provider.requests) == 1
    runtime.provider.input_tokens = 800_000
    recent = 'RETAIN_LATEST_HISTORY ' * 30_000
    runtime.send(json.dumps({'kind': 'user_input', 'text': recent}))
    settle(runtime)
    assert len(runtime.provider.requests) == 2
    runtime.send(json.dumps({'kind': 'user_input', 'text': 'Continue the same authorized task.'}))
    settle(runtime)
    events = []
    for line in (runtime.home / 'dsh-wire.jsonl').read_text().splitlines():
        event = json.loads(line).get('frame', {}).get('params', {}).get('event', {})
        if event.get('type', '').startswith('compaction/'):
            events.append(event)
    assert any(e['type'] == 'compaction/end' and not e['data'].get('error') for e in events)
    assert runtime.runtime_session_id == identity
    assert len(runtime.provider.requests) == 4  # two chats, native summary, next chat
    assert 'COMPACT_OLD_HISTORY' not in json.dumps(runtime.provider.requests[-1])
    assert 'RETAIN_LATEST_HISTORY' in json.dumps(runtime.provider.requests[-1])
    assert len(json.dumps(runtime.provider.requests[-1])) < (len(history) + len(recent)) * .75
    assert 'Continue the same authorized task.' in json.dumps(runtime.provider.requests[-1])
    assert all(r['model'] == 'deepseek-flash' for r in runtime.provider.requests)
    assert all(r.get('output_config', {}).get('effort') == 'low' for r in runtime.provider.requests)


def test_bad_tool_json_can_continue_original_dsh_session_after_explicit_correction(runtime):
    calls = []
    runtime.tool_handler = lambda *a, **k: calls.append(1)
    runtime.provider.invalid_tool_json = True
    identity = runtime.runtime_session_id
    runtime.send(json.dumps({'text': 'engineering malformed tool arguments'}))
    events = settle(runtime)
    assert next(event for event in events if event['event'] == 'provider_error')['code'] == 'MALFORMED_RESPONSE'
    assert not calls and len(runtime.provider.requests) == 1
    runtime.provider.invalid_tool_json = False
    runtime.provider.tool_calls = False
    runtime.send(json.dumps({'text': 'explicit correction; continue the same goal'}))
    events = settle(runtime)
    assert runtime.runtime_session_id == identity
    assert any(event['event'] == 'activity_ended' and event['status'] == 'ended' for event in events)
    assert len(runtime.provider.requests) == 2 and not calls


def test_active_steer_claims_next_step_and_keeps_original_source(runtime):
    provider = runtime.provider
    provider.hold = threading.Event()
    runtime.send(json.dumps({"text": "first"}))
    wait_until(lambda: len(provider.requests) == 1)
    text = "第一行\n第二行  原始空格"
    receipt = runtime.steer(json.dumps({"kind": "user_input", "message_id": "u2", "text": text,
        "source_reference": "user-original", "sender": {"kind": "user"}}))
    row = runtime.dispatch_status()[1]
    assert row["state"] == "queued"
    assert row["message_id"] == receipt["message_id"]
    assert len(provider.requests) == 1
    provider.hold.set()
    settle(runtime)
    rows = runtime.dispatch_status()
    assert rows[1]["state"] == "settled"
    assert rows[0]["turn_start_seq"] == rows[1]["turn_start_seq"]
    user_blocks = [block for request in provider.requests for message in request["messages"]
                   if message["role"] == "user" for block in message["content"]
                   if block.get("type") == "text" and "host_dispatch_id" in block.get("text", "")]
    payloads = [json.loads(block["text"])["payload"] for block in user_blocks]
    assert any(p.get("text") == text and p.get("source_reference") == "user-original" for p in payloads)


def test_control_stays_responsive_during_host_tool_and_cancel_preserves_inbox(runtime):
    entered, release = threading.Event(), threading.Event()
    def tool(name, args, **kwargs):
        entered.set()
        release.wait(5)
        return {"ok": True}
    runtime.tool_handler = tool
    runtime.send(json.dumps({"text": "tool wait"}))
    assert entered.wait(5)
    receipt = runtime.steer(json.dumps({"message_id": "control", "text": "revoke"}))
    result = runtime.interrupt()
    assert result == {"cancelSubmitted": True, "keepInbox": True}
    assert runtime.process.poll() is None and receipt["message_id"]
    release.set()
    wait_until(lambda: runtime._inflight == 0)
    assert (runtime.home / "dsh-tools.jsonl").exists()


def test_persisted_resume_keeps_original_session_and_queued_input(runtime):
    runtime.provider.tool_calls = False
    runtime.send(json.dumps({"message_id": "u1", "text": "original constraints"}))
    settle(runtime)
    runtime._rpc("host/checkpoint", {"sessionId": runtime.runtime_session_id})
    original = runtime.runtime_session_id
    instance = runtime.process_instance
    runtime.close()
    restored = DSHDeliveryRuntime(binding=runtime.binding, home=runtime.home, instructions=runtime.instructions,
        tools=[SPEC], tool_handler=runtime.tool_handler, session_id=runtime.session_id,
        provider_factory=LocalMessagesProvider, resume=True)
    try:
        restored.start()
        assert restored.runtime_session_id == original and restored.process_instance != instance
        assert not restored.provider.requests
        assert restored.dispatch_status()[0]["state"] == "settled"
        restored.send(json.dumps({"text": "new authorized input"}))
        settle(restored)
    finally:
        restored.close()


def test_process_exit_is_failure_never_idle(runtime):
    runtime.process.kill()
    runtime.process.wait(3)
    assert runtime.busy
    with pytest.raises(DeliveryRuntimeError, match="process exited"):
        runtime.poll(0)


def test_unresolved_event_gap_is_unknown_not_permanent_idle(runtime):
    runtime.projection.append({"seq": 900, "type": "turn/start", "data": {}})
    assert runtime.busy
    with pytest.raises(DeliveryRuntimeError, match="event-sequence-unresolved"):
        runtime.poll(0)


def test_dsh_resume_preserves_original_task_scope_and_sources(tmp_path):
    from modeling_team.delivery import DeliverySession
    config = {"session_id": "scope", "runtime": "dsh", "model_profile": "dsh-deepseek-flash-low",
              "authorization_reference": "engineering", "allowed_operations": ["read"], "scope": "original"}
    host = DeliverySession(repository_root=ROOT, session_root=tmp_path / "session", config=config)
    with pytest.raises(ValueError, match="original DSH task/scope/source"):
        DeliverySession(repository_root=ROOT, session_root=host.session_root,
                        config={**config, "scope": "expanded"}, resume=True)


def test_lost_enqueue_receipt_reconciles_from_original_durable_envelope(runtime):
    runtime.provider.tool_calls = False
    receipt = runtime.send(json.dumps({"message_id": "lost-response", "text": "do not duplicate"}))
    settle(runtime)
    row = dict(runtime.dispatches[receipt["dispatch_id"]])
    row.pop("message_id")
    row["state"] = "unknown"
    runtime._record("dispatch", **row)
    runtime.close()
    restored = DSHDeliveryRuntime(binding=runtime.binding, home=runtime.home, instructions=runtime.instructions,
        tools=[SPEC], tool_handler=runtime.tool_handler, session_id=runtime.session_id,
        provider_factory=LocalMessagesProvider, resume=True)
    try:
        restored.start()
        assert not restored.provider.requests
        assert restored.dispatch_status()[0]["message_id"] == receipt["message_id"]
        assert restored.dispatch_status()[0]["state"] == "settled"
    finally:
        restored.close()


def test_unknown_tool_effect_blocks_recovery_without_new_prompt(runtime):
    runtime.provider.tool_calls = False
    runtime.send(json.dumps({"text": "persist session"}))
    settle(runtime)
    runtime._record("tools", state="admitted", call_identity="native-unknown-effect")
    runtime.close()
    restored = DSHDeliveryRuntime(binding=runtime.binding, home=runtime.home, instructions=runtime.instructions,
        tools=[SPEC], tool_handler=runtime.tool_handler, session_id=runtime.session_id,
        provider_factory=LocalMessagesProvider, resume=True)
    with pytest.raises(DeliveryRuntimeError, match="native-unknown-effect"):
        restored.start()
    assert restored.runtime_session_id == runtime.runtime_session_id
    assert not restored.provider.requests
    assert restored.process.poll() is not None


def test_interrupted_activity_and_queued_input_restore_without_duplicate(runtime):
    import os
    import signal
    runtime.provider.tool_calls = False
    runtime.provider.hold = threading.Event()
    first = runtime.send(json.dumps({"message_id": "first", "text": "original"}))
    wait_until(lambda: len(runtime.provider.requests) == 1)
    queued = runtime.steer(json.dumps({"message_id": "queued", "text": "retain exact input"}))
    assert runtime.dispatch_status()[1]["state"] == "queued"
    runtime._rpc("host/checkpoint", {"sessionId": runtime.runtime_session_id})
    os.killpg(runtime.process.pid, signal.SIGKILL)
    runtime.process.wait(3)
    runtime.provider.hold.set()
    runtime.close()
    restored = DSHDeliveryRuntime(binding=runtime.binding, home=runtime.home, instructions=runtime.instructions,
        tools=[SPEC], tool_handler=runtime.tool_handler, session_id=runtime.session_id,
        provider_factory=LocalMessagesProvider, resume=True)
    try:
        restored.start()
        rows = restored.dispatch_status()
        assert len(rows) == 2
        assert rows[0]["message_id"] == first["message_id"]
        assert rows[0]["state"] == "settled"  # interrupted outcome is retained separately
        assert rows[0]["reason"]["kind"] != "completed"
        assert rows[1]["message_id"] == queued["message_id"]
        assert rows[1]["state"] in {"queued", "settled"}
        assert not restored.provider.requests  # restore itself supplies no new task
    finally:
        restored.close()


def test_complete_delivery_tool_set_and_private_mounts(tmp_path):
    import subprocess
    from modeling_team.delivery import DeliverySession
    host = DeliverySession(repository_root=ROOT, session_root=tmp_path / "session", config={
        "session_id": "full-tools", "runtime": "dsh", "model_profile": "dsh-deepseek-flash-low",
        "authorization_reference": "engineering-only", "allowed_operations": ["read"]})
    runtime = DSHDeliveryRuntime(binding=host.binding, home=host.session_root / "native",
        instructions="Engineering private boundary.", tools=host.tool_specs(), tool_handler=host.call_tool,
        session_id=host.session_id, provider_factory=LocalMessagesProvider)
    try:
        runtime.start()
        runtime.provider.tool_calls = False
        runtime.send(json.dumps({"text": "inspect exact tools"}))
        settle(runtime)
        assert {tool["name"]: tool["input_schema"] for tool in runtime.provider.requests[0]["tools"]} == {
            tool["name"]: tool["inputSchema"] for tool in host.tool_specs()}
        command = runtime.namespace_command()
        marker = command.index("--")
        script = "import fs from 'node:fs'; console.log(JSON.stringify({repo:fs.existsSync(process.argv[1]),key:process.env.DEEPSEEK_API_KEY,home:process.env.HOME}));"
        probe = subprocess.run(command[:marker + 1] + ["/agent/node", "--input-type=module", "-e",
            script, str(ROOT)], capture_output=True, text=True, timeout=10)
        assert probe.returncode == 0, probe.stderr
        assert json.loads(probe.stdout) == {"repo": False, "home": "/agent/home"}
        assert not {"submit_cq_review", "prepare_repair_task", "start_repair", "verify_repair"} & {
            t["name"] for t in host.tool_specs()}
    finally:
        runtime.close()


def test_delivery_session_restores_unknown_page_without_resending_and_keeps_constraints(tmp_path):
    from modeling_team.delivery import DeliverySession
    from modeling_team.tests.test_delivery_session import session
    host = session(tmp_path)
    host.record_observation({"runs": {}, "operations": {}, "repair_verifications": {}}, force_delivery=True)
    data = host._bootstrap_observation()
    row = {"dispatch_id": "lost-page", "state": "queued", "message_id": "native-message",
           "payload": {"kind": "delivery_start", "observed_state": data}}
    host.reconcile_native_inputs([row])
    assert not host._pending_decisions
    restored = DeliverySession(repository_root=ROOT, session_root=host.session_root, config=host.config, resume=True)
    assert not restored._pending_decisions
    changed = {**host.config, "runtime": "dsh", "model_profile": "dsh-deepseek-flash-low"}
    with pytest.raises(ValueError, match="cannot change original Delivery runtime"):
        DeliverySession(repository_root=ROOT, session_root=host.session_root, config=changed, resume=True)


def test_dsh_pause_uses_host_control_and_revoke_blocks_cached_tools(tmp_path, monkeypatch):
    from modeling_team.tests.test_delivery_session import session
    import modeling_team.delivery as module
    host = session(tmp_path)
    host.run_ids.add("dsh-production")
    host.allowed_operations.update({"production", "supervise", "evaluation"})
    monkeypatch.setattr(module.host_ops_mcp, "get_run_status", lambda **kw: {
        "identity": {"runtime": "dsh"}})
    calls = []
    monkeypatch.setattr(module.host_ops_mcp, "pause_run", lambda **kw: calls.append(kw) or {"status": "submitted"})
    result = host.apply_user_control("暂停", source_reference="original-control")
    assert result["status"] == "pending" and calls[0]["source_reference"] == "original-control"
    assert host.activity == "pause_pending"
    assert not host.call_tool("start_evaluation", {})["ok"]
    host.run_ids.clear()
    host.apply_user_control("撤回预算")
    assert "production" not in host.allowed_operations and "evaluation" not in host.allowed_operations
    assert not host.call_tool("start_run", {})["ok"]


def test_native_consumption_preserves_conversation_reception_meaning(tmp_path):
    from modeling_team.tests.test_delivery_conversation import log, message
    ledger = log(tmp_path)
    payload = message()
    ledger.receive(payload)
    receipt = {"runtime": "dsh", "runtime_session_id": "s", "message_id": "native", "state": "queued"}
    ledger.append("dispatch_result", message_id=payload["message_id"], status="accepted_by_native", native_receipt=receipt)
    ledger.append("native_consumption", message_id=payload["message_id"], native_receipt={**receipt, "state": "claimed"})
    view = ledger.receipt(payload["message_id"])
    assert view["dispatch"] == "accepted_by_native" and view["native_receipt"]["state"] == "claimed"


@pytest.mark.parametrize("control,expected", [("原文补充\n", 2), ("停止\n", 0)])
def test_real_dsh_host_loop_eof_and_stop_without_extra_inference(tmp_path, monkeypatch, control, expected):
    import io
    import shutil
    import sys
    import modeling_team.delivery as module
    for relative in ("modeling_team/model-profiles/dsh-deepseek-flash-low.yaml",
                     "modeling_team/agent-packages/delivery/instructions.md",
                     "modeling_team/skills/delivery/SKILL.md"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    def provider(credential, **kwargs):
        value = LocalMessagesProvider(credential, **kwargs)
        value.tool_calls = False
        return value
    instances = []
    def factory(**kwargs):
        kwargs.update(repository_root=ROOT, profile=None, provider_factory=provider)
        value = DSHDeliveryRuntime(**kwargs)
        instances.append(value)
        return value
    monkeypatch.setattr(module, "DSHDeliveryRuntime", factory)
    monkeypatch.setattr(sys, "stdin", io.StringIO(control))
    config = {"session_id": "loop", "runtime": "dsh", "model_profile": "dsh-deepseek-flash-low",
              "authorization_reference": "engineering", "allowed_operations": ["read"]}
    assert module._run_delivery(config, repository_root=tmp_path, resume=False) == expected
    state = json.loads((tmp_path / "workspaces/delivery-sessions/loop/session.json").read_text())
    assert state["runtime_identity"]["runtime"] == "dsh" and state["native_thread_id"] is None
    runtime = instances[0]
    assert runtime.process.poll() is not None
    if expected == 0:
        assert len(runtime.dispatches) == 1
        assert state["state"] == "stopped"
    else:
        assert state["state"] == "supervision_interrupted"
        assert any(row["payload"].get("text") == "原文补充" for row in runtime.dispatches.values())
