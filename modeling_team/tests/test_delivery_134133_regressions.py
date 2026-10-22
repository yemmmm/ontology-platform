"""Offline regressions for the retained 134133 Delivery latency/input failures."""

import copy
import importlib
import json
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import pytest

from modeling_team.delivery_host_actions import (
    append_session_event,
    host_action_state,
    record_host_action_result,
    request_host_action,
)
from modeling_team.tests.test_delivery_host_actions import _platform_request
from modeling_team.tests.test_delivery_paged_phase_handoff import ready
from modeling_team.tests.test_delivery_runtime import _runtime
from modeling_team.tests.test_delivery_session import ROOT, session
from modeling_team.tests.test_delivery_wakeups import observation
from modeling_team.model_routing import load_team_model_profile


def test_native_notification_burst_does_not_starve_tool_or_completion(tmp_path, monkeypatch):
    module = importlib.import_module("modeling_team.runtimes.delivery")
    profile = load_team_model_profile(ROOT, "openai-sol-medium")
    calls, sent = [], []
    runtime = _runtime(module, profile, tmp_path / "native",
                       tool_handler=lambda name, args: calls.append((name, args)) or {"ok": True})
    runtime.thread_id, runtime._turn_id, runtime.busy = "thread", "turn", True
    frames = deque([{"method": "item/agentMessage/delta", "params": {"delta": "x"}}] * 100)
    frames.extend([
        {"id": 123, "method": "item/tool/call", "params": {
            "threadId": "thread", "callId": "call", "tool": "emit_user_message",
            "arguments": {"message": "actual work result"}}},
        {"method": "turn/completed", "params": {
            "threadId": "thread", "turn": {"id": "turn", "status": "completed"}}},
    ])
    monkeypatch.setattr(runtime, "_read", lambda timeout: frames.popleft() if frames else None)
    monkeypatch.setattr(runtime, "_write", sent.append)

    events = runtime.poll(0)

    assert calls == [("emit_user_message", {"message": "actual work result"})]
    assert sent[0]["id"] == 123 and sent[0]["result"]["success"]
    assert events == [{"event": "turn_completed", "status": "completed"}]
    assert not runtime.busy and not frames


def test_native_drain_is_bounded_so_user_control_can_run(tmp_path, monkeypatch):
    module = importlib.import_module("modeling_team.runtimes.delivery")
    runtime = _runtime(module, load_team_model_profile(ROOT, "openai-sol-medium"),
                       tmp_path / "native")
    frames = deque({"method": "item/agentMessage/delta"} for _ in range(10000))
    monkeypatch.setattr(runtime, "_read", lambda timeout: frames.popleft() if frames else None)
    runtime.poll(0)
    assert 1 < 10000 - len(frames) < 10000


def test_native_pipe_burst_reaches_declared_tool_in_one_poll(tmp_path):
    module = importlib.import_module("modeling_team.runtimes.delivery")
    home = tmp_path / "native"
    home.mkdir()
    (home / "notification_burst").write_text("32")
    calls = []
    runtime = _runtime(module, load_team_model_profile(ROOT, "openai-sol-medium"), home,
                       tool_handler=lambda name, args: calls.append(name) or {"ok": True})
    try:
        runtime.start()
        runtime.send("Exercise the existing native pipe without a provider.")
        deadline = time.monotonic() + 3
        while '"item/tool/call"' not in (home / "server-events.jsonl").read_text():
            assert time.monotonic() < deadline, "offline native fixture did not emit the tool call"
            time.sleep(.005)
        runtime.poll(.05)
        assert calls == ["emit_user_message"]
        while runtime.busy:
            assert time.monotonic() < deadline, "native completion was not received"
            runtime.poll(.05)
    finally:
        runtime.close()


def test_host_projection_parses_only_appended_rows_and_retains_exact_results(tmp_path, monkeypatch):
    module = importlib.import_module("modeling_team.delivery_host_actions")
    root = tmp_path / "session"
    for index in range(10):
        append_session_event(root, {"state": "active", "unrelated_body": "x" * 10000,
                                    "index": index})
    request_host_action(root, "delivery-1", {"run-1"}, "auth-1", _platform_request(root))
    expected = host_action_state(root)
    parsed = []
    original = module.json.loads

    def loads(raw, *args, **kwargs):
        parsed.append(len(raw))
        return original(raw, *args, **kwargs)

    monkeypatch.setattr(module.json, "loads", loads)
    assert host_action_state(root) == expected
    assert parsed == []
    append_session_event(root, {"state": "active", "new_only": True})
    assert host_action_state(root) == expected
    assert len(parsed) == 1
    results = root / "host-results"
    results.mkdir()
    path = results / "done.json"
    path.write_text('{"result":"retained private evidence"}')
    record_host_action_result(root, "repair-1", "completed", path)
    state = host_action_state(root)
    assert state["pending"] == []
    assert state["completed"][0]["result_ref"]["path"] == "host-results/done.json"
    ref = state["completed"][0]["journal_ref"]
    raw = (root / "session-events.jsonl").read_bytes()
    assert original(raw[ref["byte_offset"]:ref["byte_offset"] + ref["byte_length"]])["request_id"] == "repair-1"
    state["requests"]["repair-1"]["checked"].append("caller mutation")
    assert "caller mutation" not in host_action_state(root)["requests"]["repair-1"]["checked"]


def test_host_projection_keeps_corruption_and_retries_an_incomplete_tail(tmp_path):
    root = tmp_path / "session"
    append_session_event(root, {"event": "unrelated"})
    assert host_action_state(root)["history_complete"]
    path = root / "session-events.jsonl"
    with path.open("ab") as handle:
        handle.write(b'{"event":"partial"')
    assert not host_action_state(root)["history_complete"]
    with path.open("ab") as handle:
        handle.write(b'}\ninvalid-json\n')
    state = host_action_state(root)
    assert not state["history_complete"]
    assert any(item.startswith("corrupt_event:") for item in state["limitations"])
    assert not any(item.startswith("incomplete_tail:") for item in state["limitations"])


@pytest.mark.parametrize("replacement", [False, True])
def test_host_projection_rebuilds_after_journal_repair_or_replacement(tmp_path, replacement):
    root = tmp_path / "session"
    request_host_action(root, "delivery-1", {"run-1"}, "auth-1", _platform_request(root))
    assert host_action_state(root)["pending"]
    path = root / "session-events.jsonl"
    if replacement:
        other = root / "repaired.jsonl"
        other.write_text('{"event":"repaired"}\n')
        other.replace(path)
    else:
        path.write_text('{"event":"repaired"}\n')
    state = host_action_state(root)
    assert state["history_complete"] and state["pending"] == []


def test_host_projection_sees_external_host_result_after_cached_pending(tmp_path):
    root = tmp_path / "session"
    request_host_action(root, "delivery-1", {"run-1"}, "auth-1", _platform_request(root))
    assert len(host_action_state(root)["pending"]) == 1
    results = root / "host-results"
    results.mkdir()
    path = results / "external.json"
    path.write_text('{"verification":"external Host result"}')
    completed = subprocess.run([
        sys.executable, "-m", "modeling_team.delivery_host_actions",
        "--session-root", str(root), "--request-id", "repair-1", "--status", "completed",
        "--result-path", str(path),
    ], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    state = host_action_state(root)
    assert state["pending"] == [] and state["completed"][0]["source"] == "host_agent"


def test_host_projection_does_not_keep_same_size_rewritten_history(tmp_path):
    root = tmp_path / "session"
    request_host_action(root, "delivery-1", {"run-1"}, "auth-1", _platform_request(root))
    assert "repair-1" in host_action_state(root)["requests"]
    path = root / "session-events.jsonl"
    raw = path.read_bytes()
    repaired = raw.replace(b'"request_id":"repair-1"', b'"request_id":"repair-2"')
    assert len(repaired) == len(raw) and repaired != raw
    path.write_bytes(repaired)
    assert set(host_action_state(root)["requests"]) == {"repair-2"}


def test_session_snapshot_does_not_duplicate_pending_packet_index(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    pending = copy.deepcopy(host._pending_decisions)
    host._save("active")
    assert json.loads((host.session_root / "session.json").read_text())["delivery_inputs"] == pending
    records = [json.loads(line) for line in (host.session_root / "session-events.jsonl").read_text().splitlines()]
    snapshots = [row for row in records if "supervisor_pid" in row]
    assert snapshots and all("delivery_inputs" not in row for row in snapshots)
    assert any(row.get("event") == "delivery_decision_input" for row in records)
    module = importlib.import_module("modeling_team.delivery")
    restored = module.DeliverySession(repository_root=ROOT, session_root=host.session_root,
                                      config=host.config, resume=True)
    assert restored._pending_decisions == pending


def test_phase_decision_precedes_routine_activity_and_details_remain_readable(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    original = host._periodic_review

    def review(**kwargs):
        result = original(**kwargs)
        result["activity"] = [{"run_id": "run", "actor": "modeling", "operation": str(index),
                                "status": "observed", "count": 1,
                                "first": {"detail": "ROUTINE-DETAIL-" * 50}}
                               for index in range(100)]
        result["retries"] = [{"run_id": "run", "failure_count": 1,
                               "latest_result": {"status": "unknown", "code": "retain-real-error"}}]
        return result

    monkeypatch.setattr(host, "_periodic_review", review)
    host.record_observation(raw, force_delivery=True)
    packet = host._model_observation()
    if "page" in packet:
        prefix = packet["page"]["text"].encode()
        view = json.loads(Path(packet["read_original"]["path"]).read_text())
    else:
        view = packet
        prefix = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode()[:12000]
    assert b'"phase_thread_handoff"' in prefix
    assert "ROUTINE-DETAIL-" not in json.dumps(view)
    assert "retain-real-error" in json.dumps(view)
    assert sum(row["count"] for row in view["periodic_review"]["activity"]) == 100
    ref = view["evidence"]
    with Path(ref["path"]).open("rb") as handle:
        handle.seek(ref["selection"]["offset"])
        retained = json.loads(handle.read(ref["selection"]["length"]))
    assert len(retained["periodic_review"]["activity"]) == 100
    assert retained["periodic_review"]["activity"][0]["first"]["detail"].startswith("ROUTINE-DETAIL-")
