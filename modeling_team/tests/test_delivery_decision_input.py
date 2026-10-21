"""R4.3-022 real files/receipts and offline Delivery dispatch contracts (A1-A4)."""
import copy
import importlib
import json

import pytest

from modeling_team.delivery import DeliverySession
from modeling_team.runtimes.delivery import DeliveryRuntimeError
from modeling_team.tests.test_delivery_session import ROOT, _StubNativeRuntime, session
from modeling_team.tests.test_delivery_wakeups import observation, _events_page, _receipt_event, changed_value


def read(host, path, **args):
    return host.call_tool("read_delivery_artifact", {"path": str(path), **args})


def ack(host):
    data = host._model_observation()
    assert host._dispatch_observation(_StubNativeRuntime(), {"kind": "host_observation", "data": data}, steer=False)
    return data


def bound_run(tmp_path, monkeypatch):
    host = session(tmp_path)
    root = tmp_path / "run"
    (root / "control").mkdir(parents=True)
    (root / "evidence").mkdir()
    (root / "state.json").write_text('{"state":"RUNNING"}')
    for name in ("modeling_team.delivery", "modeling_team.host_ops"):
        monkeypatch.setattr(importlib.import_module(name), "resolve_run_root", lambda *a, **k: (root, tmp_path))
    host.run_ids.add("run")
    return host, root


@pytest.mark.parametrize("key", ["observed_at", "evidence_refs", "ordinal", "stdout_tail", "heartbeat_count"])
def test_business_keys_are_not_recursive_noise(tmp_path, key):
    host = session(tmp_path)
    initial = observation()
    initial["runs"]["run"]["pending"]["data"]["items"][0][key] = "business-1"
    host.record_observation(initial)
    initial["runs"]["run"]["pending"]["data"]["items"][0][key] = "business-2"
    assert host.record_observation(initial)
    assert changed_value(ack(host), "runs", "run", "pending", "data", "items", 0, key) == "business-2"


def test_request_receipt_projection_preserves_uncertain_rejected_conflict_and_legacy(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    ledger = [{"request_id": name, "action": "submit_cq_review", "content_digest": name}
              for name in ("accepted", "rejected", "conflict", "unknown")]
    ledger += [{"action": "legacy"}]
    path = root / "control/host-requests.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in ledger))
    receipts = [{"request_id": "accepted", "outcome": "accepted", "content_digest": "accepted"},
                {"request_id": "rejected", "outcome": "rejected", "content_digest": "rejected",
                 "code": "cq-input-rejected", "message": "业务限定必须保留", "next_action": "fix draft"},
                {"request_id": "conflict", "outcome": "accepted", "content_digest": "different"}]
    (root / "evidence/outer-input-receipts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in receipts))
    raw = observation()
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    host.record_observation(raw)
    data = ack(host)["runs"]["run"]["requests"]["data"]
    assert data["settled_index"]["total"] == 2
    pending = data["pending"]
    assert {row.get("request_id") for row in pending} == {None, "conflict", "unknown"}
    settled = host._last_current["runs"]["run"]["requests"]["data"]["settled"]
    rejected = next(row for row in settled if row.get("request_id") == "rejected")
    assert rejected["result"]["data"]["receipt"]["message"] == "业务限定必须保留"
    assert next(row for row in pending if row.get("request_id") == "conflict")["result"]["error"]["code"] == "request_id_conflict"
    assert next(row for row in pending if row.get("request_id") == "unknown")["result"]["data"]["outcome"] == "unknown"
    assert next(row for row in pending if row.get("request_id") is None)["outcome"] == "uncorrelated"


def test_large_ledger_retained_and_settled_history_not_resent(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    rows = [{"request_id": f"r{i}", "content_digest": f"d{i}", "body": "历史" * 350} for i in range(1100)]
    ledger = root / "control/host-requests.jsonl"
    ledger.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    (root / "evidence/outer-input-receipts.jsonl").write_text("".join(json.dumps({
        "request_id": row["request_id"], "content_digest": row["content_digest"], "outcome": "accepted"}) + "\n" for row in rows))
    assert ledger.stat().st_size > 2_000_000
    raw = observation()
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    assert raw["runs"]["run"]["request_ledger"]["data"]["text"] == ledger.read_text()
    host.record_observation(raw)
    payload = ack(host)
    assert payload["runs"]["run"]["requests"]["data"]["settled_index"]["total"] == 1100
    assert len(json.dumps(payload, ensure_ascii=False).encode()) < 32768
    assert "历史" not in json.dumps(payload, ensure_ascii=False)
    assert not host.record_observation(raw)
    assert read(host, ledger)["error"]["code"] == "artifact_selection_invalid"


def test_partial_and_corrupt_ledger_are_not_complete(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    (root / "control/host-requests.jsonl").write_bytes(b'{"request_id":"partial"}\nBAD\n{"request_id":"half"}')
    raw = observation()
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    host.record_observation(raw)
    data = ack(host)["runs"]["run"]["requests"]["data"]
    assert data["coverage"]["complete"] is False
    assert len([row for row in data["limitations"] if row["code"] == "request_ledger_corrupt"]) == 2


def test_byte_pages_preserve_chinese_and_prefix_identity(tmp_path):
    host = session(tmp_path)
    path = host.session_root / "session-events.jsonl"
    before = path.read_bytes()
    result = read(host, path, selection={"kind": "bytes", "offset": 0}, max_bytes=1)
    assert result["ok"]
    data = result["data"]
    path.write_bytes(before + b'{}\n')
    chunks = [data["text"]]
    while not data["read_complete"]:
        result = read(host, path, **data["continuation"], max_bytes=71)
        assert result["ok"]
        data = result["data"]
        chunks.append(data["text"])
    assert "".join(chunks).encode() == before
    assert data["source_ref"]["byte_length"] == len(before)
    path.write_bytes(b'X' + path.read_bytes()[1:])
    assert read(host, path, source_ref=data["source_ref"], selection={"kind": "bytes", "offset": 0})["error"]["code"] == "artifact_changed"


def test_json_literal_paths_null_missing_and_changed_source(tmp_path):
    host = session(tmp_path)
    source = next(iter(host.sources))
    source.write_text(json.dumps({"reports": [{"verdict": None}], "a.b": "中" * 17000, "secret": "private"}, ensure_ascii=False))
    paths = [["reports", 0, "verdict"], ["absent"], ["a.b"]]
    result = read(host, source, selection={"kind": "json", "paths": paths}, max_bytes=7)
    assert result["ok"]
    data, chunks = result["data"], [result["data"]["text"]]
    while not data["read_complete"]:
        result = read(host, source, **data["continuation"])
        assert result["ok"]
        data = result["data"]
        chunks.append(data["text"])
    fields = json.loads("".join(chunks))["fields"]
    assert fields[0]["found"] and fields[0]["value"] is None
    assert fields[1]["found"] is False and "value" not in fields[1]
    assert fields[2]["value"] == "中" * 17000
    assert not data["source_complete"] and data["omitted"]["other_source_fields"]
    source.write_text('{}')
    assert read(host, source, source_ref=data["source_ref"], selection={"kind": "json", "paths": paths})["error"]["code"] == "artifact_changed"


@pytest.mark.parametrize("args", [
    {"selection": {"kind": "json", "paths": []}},
    {"selection": {"kind": "json", "paths": [[True]]}},
    {"selection": {"kind": "json", "paths": [[-1]]}},
    {"selection": {"kind": "bytes", "offset": -1}},
    {"selection": {"kind": "bytes", "offset": 1}},
    {"selection": {"kind": "json", "paths": [["x"]], "filter": "*"}},
    {"selection": {"kind": "bytes"}, "max_bytes": 16385},
])
def test_invalid_selection_is_recoverable(tmp_path, args):
    host = session(tmp_path)
    source = next(iter(host.sources))
    result = read(host, source, **args)
    assert result["error"]["code"] == "artifact_selection_invalid"
    assert result["error"]["retryable"] is True
    assert read(host, source)["ok"]


def test_corruption_unavailable_and_forbidden_are_distinct(tmp_path):
    host = session(tmp_path)
    source = next(iter(host.sources))
    source.write_text('bad JSON')
    assert read(host, source, selection={"kind": "json", "paths": [["x"]]})["error"]["code"] == "artifact_corrupt"
    assert read(host, source, selection={"kind": "bytes"})["ok"]
    source.unlink()
    assert read(host, source)["error"]["code"] == "artifact_unavailable"
    source.write_bytes(b'\xff')
    assert read(host, source)["error"]["code"] == "artifact_corrupt"
    result = read(host, tmp_path / "forbidden")
    assert result["error"]["code"] == "artifact_forbidden"
    assert "content_digest" not in result["error"]


def test_continuation_cannot_switch_json_paths(tmp_path):
    host = session(tmp_path)
    source = next(iter(host.sources))
    source.write_text('{"a":"long", "b":"other"}')
    data = read(host, source, selection={"kind": "json", "paths": [["a"]]}, max_bytes=1)["data"]
    assert read(host, source, source_ref=data["source_ref"], selection={"kind": "json", "paths": [["b"]]})["error"]["code"] == "artifact_selection_invalid"


def test_unreceived_changes_survive_later_observations_and_resume(tmp_path):
    host = session(tmp_path)
    first = observation()
    host.record_observation(first)
    second = copy.deepcopy(first)
    second["runs"]["run"]["pending"]["data"]["items"] = []
    second["runs"]["run"]["events"] = _events_page([_receipt_event(100, "E2")], next_cursor="c2")
    host.record_observation(second)
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root, config=host.config, resume=True)
    assert len(reopened._pending_decisions) == 2
    last = ack(reopened)
    assert last["runs"]["run"]["pending"]["data"]["items"] == []
    assert any(row.get("identity") == "question-1" and row["change"] == "removed"
               for row in last["changes"])
    assert any(row["path"][-1] == "items" for row in last["changes"])
    assert not reopened._pending_decisions


def test_backlogged_observations_deliver_latest_state_with_all_unseen_events(tmp_path):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    for index in range(1, 6):
        raw["runs"]["run"]["status"]["data"]["write_phase"] = f"phase-{index}"
        raw["runs"]["run"]["events"] = _events_page(
            [_receipt_event(index * 100, f"unseen-{index}")], next_cursor=f"c{index}")
        host.record_observation(raw)
    before = (host.session_root / "session-events.jsonl").read_bytes()
    latest = ack(host)
    assert latest["runs"]["run"]["status"]["data"]["write_phase"] == "phase-5"
    assert len(latest["runs"]["run"]["events"]["data"]["events"]) >= 5
    assert not host._pending_decisions
    assert (host.session_root / "session-events.jsonl").read_bytes().startswith(before)
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    assert not reopened._pending_decisions


def test_latest_host_result_is_delivered_before_waiting_on_closed_request(tmp_path):
    from modeling_team.delivery_host_actions import request_host_action, record_host_action_result
    from modeling_team.tests.test_delivery_host_actions import _platform_request
    host = session(tmp_path)
    host.run_ids.add("run")
    raw = observation()
    host.record_observation(raw)
    request_host_action(host.session_root, host.session_id, host.run_ids, host.authorization,
                        _platform_request(host.session_root, run_id="run"))
    host.record_observation(raw)
    result_file = host.session_root / "host-results/repaired.json"
    result_file.parent.mkdir()
    result_file.write_text('{"diagnosis":"PRIVATE-HOST-BODY"}')
    record_host_action_result(host.session_root, "repair-1", "completed", result_file)
    host.record_observation(raw)
    latest = ack(host)
    assert latest["host_actions"]["completed"][0]["request_id"] == "repair-1"
    assert "PRIVATE-HOST-BODY" not in json.dumps(latest)
    waiting = host.call_tool("yield_delivery", {"input_id": latest["input_id"],
        "phase": "production", "waiting_for": [{"run_id": "run", "host_request_id": "repair-1",
                                                  "condition": "Host repair result"}],
        "next_action": "continue remaining work", "reason": "wait for repair", "active_decisions": []})
    assert waiting["error"]["code"] == "delivery_host_action_completed"
    assert waiting["error"]["result_ref"]["path"] == "host-results/repaired.json"
    assert "PRIVATE-HOST-BODY" not in json.dumps(waiting)


def test_partial_and_unknown_inputs_keep_their_original_identity(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"] *= 1000
    host.record_observation(raw)
    first = ack(host)
    original = copy.deepcopy(host._pending_decisions[0])
    assert original["offset"] > 0
    raw["runs"]["run"]["pending"]["data"]["items"] = []
    host.record_observation(raw)
    data = host._model_observation()
    assert data["input_id"] == first["input_id"]
    assert host._pending_decisions[0] == original
    host._pending_decisions[0]["delivery_status"] = "unknown"
    assert host._model_observation()["delivery_status"] == "unknown"


@pytest.mark.parametrize("failure_last", [False, True])
def test_coalescing_preserves_unseen_read_errors_and_event_bodies(tmp_path, failure_last):
    host = session(tmp_path)
    raw = observation()
    failed = {"ok": False, "error": {"code": "artifact_unavailable", "reason": "read failed"}}
    events = _events_page([_receipt_event(100, "unseen-receipt")], next_cursor="later")
    for page in ([events, failed] if failure_last else [failed, events]):
        raw["runs"]["run"]["events"] = page
        host.record_observation(raw)
    data = ack(host)
    assert "unseen-receipt" in json.dumps(data)
    assert any(row.get("historical") and row.get("value") == failed for row in data["changes"])


def test_unknown_dispatch_keeps_input_and_does_not_claim_acceptance(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    class LostReceipt:
        def send(self, text):
            raise DeliveryRuntimeError("lost")
    packet = {"kind": "host_observation", "data": host._model_observation()}
    assert not host._dispatch_observation(LostReceipt(), packet, steer=False)
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root, config=host.config, resume=True)
    assert reopened._model_observation()["delivery_status"] == "unknown"
    assert len(reopened._pending_decisions) == 1


def test_oversized_pending_input_pages_cover_all_values(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"] = [{"id": str(i), "unknown_write": True,
        "description": "业务条件" * 40} for i in range(130)]
    host.record_observation(raw)
    chunks = []
    while host._pending_decisions:
        data = ack(host)
        assert len(json.dumps(data, ensure_ascii=False).encode()) <= 32768
        chunks.append(data["page"]["text"])
    content = json.loads("".join(chunks))
    assert len(content["runs"]["run"]["pending"]["data"]["items"]) == 130
    assert all(item["unknown_write"] for item in content["runs"]["run"]["pending"]["data"]["items"])


def test_only_bound_operation_files_are_readable_and_private_not_published(tmp_path):
    host = session(tmp_path)
    host.repository_root = tmp_path
    directory = tmp_path / ".delivery-ops"
    directory.mkdir()
    log = directory / "bound.err.log"
    log.write_text("HOST-PRIVATE-CANARY")
    record = directory / "bound.json"
    record.write_text(json.dumps({"operation_id": "bound", "log_paths": {"stderr": str(log)}}))
    host.operation_ids.add("bound")
    assert read(host, log)["data"]["text"] == "HOST-PRIVATE-CANARY"
    assert read(host, record)["ok"]
    adjacent = directory / "other.err.log"
    adjacent.write_text("not bound")
    assert read(host, adjacent)["error"]["code"] == "artifact_forbidden"
    log.unlink()
    log.symlink_to(adjacent)
    assert read(host, log)["error"]["code"] == "artifact_forbidden"
    assert host.drain_messages() == []


def test_stable_operations_are_indexed_but_invalid_reports_and_control_remain(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["operations"] = {f"done-{i}": {"ok": True, "data": {
        "operation_id": f"done-{i}", "status": "exited", "request_binding": {"private": "历史" * 200},
        "report_binding": {"valid": True, "path": f"report-{i}", "content_digest": str(i)}}}
        for i in range(100)}
    raw["operations"]["invalid"] = {"ok": True, "data": {"status": "exited",
        "report_status": "new_report_rejected", "report_binding": {"valid": False,
        "validation_errors": ["binding changed"]}}}
    raw["operations"]["controlled"] = {"ok": True, "data": {"status": "exited",
        "report_binding": {"valid": True}, "control_receipts": {"pause": {"status": "unknown"}}}}
    host.record_observation(raw)
    data = ack(host)
    assert data["operation_history"]["operations"]["total"] == 100
    assert set(data["operations"]) == {"invalid", "controlled"}
    assert "历史" not in json.dumps(data, ensure_ascii=False)
    assert data["operations"]["invalid"]["data"]["report_binding"]["valid"] is False
    raw["operations"]["done-1"]["data"]["report_binding"]["content_digest"] = "changed"
    host.record_observation(raw)
    assert changed_value(ack(host), "operations", "done-1", "data", "report_binding", "content_digest") == "changed"


def test_exact_event_locator_uses_source_offset_not_page_line(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    path = root / 'evidence/settled.jsonl'
    prefix = b'{"old":true}\n' * 50
    line = '{"business":"完整业务事件"}\n'.encode()
    path.write_bytes(prefix + line)
    event = {"source": "settled.jsonl", "line_no": 1, "byte_offset": len(prefix),
             "data": {"business": "完整业务事件"}}
    raw = observation()
    raw['runs']['run']['events'] = _events_page([event], next_cursor='c')
    host.record_observation(raw)
    located = ack(host)['runs']['run']['events']['data']['events'][0]
    result = read(host, path, source_ref=located['source_ref'], selection=located['selection'])
    assert result['data']['text'].encode() == line
    assert located['byte_length'] == len(line)
    assert result['data']['source_complete'] is False


def test_resume_uses_journal_when_session_save_was_interrupted(tmp_path, monkeypatch):
    host = session(tmp_path)
    original_save = host._save
    monkeypatch.setattr(host, '_save', lambda *a, **k: (_ for _ in ()).throw(OSError('save interrupted')))
    host._event_cursors['run'] = 'cursor-after-page'
    with pytest.raises(OSError, match='save interrupted'):
        host.record_observation(observation())
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root, config=host.config, resume=True)
    assert reopened._event_cursors['run'] == 'cursor-after-page'
    assert len(reopened._pending_decisions) == 1
    monkeypatch.setattr(host, '_save', original_save)
    packet = {'kind': 'host_observation', 'data': host._model_observation()}
    monkeypatch.setattr(host, '_save', lambda *a, **k: (_ for _ in ()).throw(OSError('ack save interrupted')))
    with pytest.raises(OSError, match='ack save interrupted'):
        host._dispatch_observation(_StubNativeRuntime(), packet, steer=False)
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root, config=host.config, resume=True)
    assert not reopened._pending_decisions


def test_event_cursor_not_saved_until_observation_and_input_are_retained(tmp_path, monkeypatch):
    host = session(tmp_path)
    monkeypatch.setattr(host, 'call_tool', lambda *a, **k: _events_page([], next_cursor='new-cursor'))
    host._observe_run_events('run')
    assert host._event_cursors['run'] == 'new-cursor'
    assert json.loads((host.session_root / 'session.json').read_text())['event_cursors'] == {}
    host.record_observation(observation())
    assert json.loads((host.session_root / 'session.json').read_text())['event_cursors']['run'] == 'new-cursor'


def test_resume_rebuilds_current_input_even_when_last_input_was_accepted(tmp_path):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    ack(host)
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root, config=host.config, resume=True)
    assert not reopened.record_observation(raw)
    assert reopened.record_observation(raw, force_delivery=True)
    assert ack(reopened)["runs"]["run"]["status"]["data"]["recorded_state"]["state"] == "RUNNING"


def test_undelivered_historical_input_is_merged_with_current_unknown_write(tmp_path):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    host.record_observation(raw)
    data = host._model_observation()
    assert data["runs"]["run"]["status"]["data"]["write_phase"] == "unknown"
    assert data["core"]["runs"]["run"]["write_phase"] == "unknown"
    assert len(host._pending_decisions) == 1


def test_large_blocker_has_body_in_bounded_pages_and_original_reference(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["status"]["data"]["first_blocker"] = {"message": "原始阻塞" * 5000}
    host.record_observation(raw)
    payload = host._model_observation()
    chunks = []
    while host._pending_decisions:
        chunks.append(ack(host)["page"]["text"])
    complete = json.loads("".join(chunks))
    assert complete["core"]["first_blockers"]["run"]["preview_complete"] is False
    assert complete["runs"]["run"]["status"]["data"]["first_blocker"]["message"] == "原始阻塞" * 5000
    evidence = payload["evidence"]
    result = read(host, evidence["path"], source_ref=evidence["source_ref"], selection=evidence["selection"])
    assert result["ok"]


def test_r4329_host_request_validates_live_cq_binding(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    host.allowed_operations.add("supervise")
    module = importlib.import_module("modeling_team.delivery")
    binding = {"review_id": "r1", "content_version": 2, "content_digest": "digest-2",
               "question_ids": ["q1"], "phase": "slice-review",
               "review_snapshot_ref": "competency-questions/reviews/r1.json"}
    monkeypatch.setattr(module.host_ops_mcp, "get_pending_actions", lambda **kw: {
        "items": [{"type": "cq_review", "bindings": binding}], "run_id": "run"})
    args = {"request_id": "cq-host", "run_id": "run", "kind": "cq_review",
            "bindings": dict(binding, content_digest="stale")}
    stale = host.call_tool("request_host_action", args)
    assert not stale["ok"] and stale["error"]["code"] == "host_action_binding_stale"
    args["bindings"] = binding
    result = host.call_tool("request_host_action", args)
    assert result["ok"], result
    assert host.call_tool("request_host_action", args)["ok"]
    monkeypatch.setattr(module.host_ops_mcp, "get_pending_actions", lambda **kw: {"items": []})
    assert host.call_tool("request_host_action", args)["ok"]
    changed = dict(args, bindings=dict(binding, content_digest="different"))
    assert not host.call_tool("request_host_action", changed)["ok"]
    records = [json.loads(line) for line in (host.session_root / "session-events.jsonl").read_text().splitlines()]
    assert sum(row.get("event") == "host_action_request" for row in records) == 1
    assert not host.call_tool("submit_cq_review", {})["ok"]
    host.allowed_operations.discard("supervise")
    assert not host.call_tool("request_host_action", args)["ok"]


def test_r4329_host_result_wakes_and_survives_undelivered_resume(tmp_path, monkeypatch):
    from modeling_team.delivery_host_actions import record_host_action_result
    host, root = bound_run(tmp_path, monkeypatch)
    host.allowed_operations.add("supervise")
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.host_ops_mcp, "get_pending_actions", lambda **kw: {"items": []})
    args = {"request_id": "repair-host", "run_id": "run", "kind": "platform_repair",
            "bindings": {}, "expected_behavior": "current revision readback",
            "actual_behavior": "stale revision", "write_state": "unknown"}
    result = host.call_tool("request_host_action", args)
    assert result["ok"], result
    host.record_observation(observation())
    ack(host)
    results_dir = host.session_root / "host-results"
    results_dir.mkdir(exist_ok=True)
    original = results_dir / "repair.json"
    original.write_text(json.dumps({"request_id": "repair-host", "session_id": host.session_id,
        "run_id": "run", "status": "completed", "limitations": "engineering only"}))
    record_host_action_result(host.session_root, "repair-host", "completed", original)
    assert host.record_observation(observation())
    packet = host._model_observation()
    assert "repair-host" in json.dumps(packet["changes"])
    assert not (root / "control/host-requests.jsonl").exists()
    resumed = DeliverySession(repository_root=ROOT, session_root=host.session_root,
        config=host.config, resume=True)
    assert resumed._model_observation()["input_id"] == packet["input_id"]
    assert resumed._model_observation()["changes"] == packet["changes"]

    # A completed result is delivered once, then retained through a precise index.
    ack(host)
    later = observation()
    later["runs"]["run"]["status"]["data"]["stage"]["phase"] = "handoff"
    assert host.record_observation(later)
    later_packet = ack(host)
    assert "repair-host" not in json.dumps(later_packet["changes"])
    history = later_packet["coverage"]["history"]["host_actions"]
    assert history["total"] == 1
    assert history["evidence_ref"] == "evidence"
    evidence = later_packet["evidence"]
    original = json.loads(read(host, evidence["path"], source_ref=evidence["source_ref"],
                              selection=evidence["selection"])["data"]["text"])
    assert original["snapshot"]["host_actions"]["completed"][0]["request_id"] == "repair-host"


def test_completed_standby_operation_is_indexed_after_completion_delivery(tmp_path):
    host = session(tmp_path)
    raw = observation()
    operation = raw["operations"]["op"]["data"]
    operation.update(work_state="working", lifecycle="active", report_binding={"valid": True})
    host.record_observation(raw)
    ack(host)
    operation.update(work_state="completed", lifecycle="standby",
                     consult_replies=[{"role": "consumer", "text": "RETAINED-REPLY"}])
    assert host.record_observation(raw)
    assert changed_value(ack(host), "operations", "op", "data", "work_state") == "completed"
    raw["runs"]["run"]["status"]["data"].update(write_phase="unknown")
    assert host.record_observation(raw)
    payload = ack(host)
    assert "op" not in payload["core"]["operations"]
    assert payload["coverage"]["history"]["operations"]["total"] == 1
    assert payload["core"]["runs"]["run"]["write_phase"] == "unknown"
    assert "RETAINED-REPLY" not in json.dumps(payload)
    operation["report_binding"]["valid"] = False
    assert host.record_observation(raw)
    assert changed_value(ack(host), "operations", "op", "data", "report_binding", "valid") is False
    operation["report_binding"]["valid"] = True
    operation["control_receipts"] = {"consult": {"status": "unknown"}}
    assert host.record_observation(raw)
    ack(host)
    raw["runs"]["run"]["status"]["data"]["stage"]["phase"] = "another-step"
    host.record_observation(raw)
    assert "op" in ack(host)["core"]["operations"]


def test_finish_standby_has_queryable_receipt_and_native_retry_reuses_request(tmp_path, monkeypatch):
    from modeling_team.competency_questions import content_digest
    from modeling_team.outer_input import OuterInputFifo

    host, root = bound_run(tmp_path, monkeypatch)
    host.allowed_operations.add("supervise")
    fifo = OuterInputFifo(root / "control/outer-input.fifo")
    fifo.open()
    try:
        result = host.call_tool("finish_delivery", {"conclusion": "work complete"},
                                call_identity="native-finish-call")
        assert result["ok"], result
        standby = result["data"]["runs"]["run"]["data"]
        assert standby["request_id"]
        assert standby["receipt_tracking"]["via"] == "host_observation"
        assert "yield_delivery" in standby["receipt_tracking"]["next_action"]
        assert "next_query" not in standby
        fifo.read_ready()
        envelope = json.loads(fifo.pop_line())
        assert envelope.pop("request_id") == standby["request_id"]
        (root / "evidence/outer-input-receipts.jsonl").write_text(json.dumps({
            "request_id": standby["request_id"], "outcome": "accepted", "action": "standby",
            "content_digest": content_digest(envelope), "ack_type": "standby-accepted",
        }) + "\n")
        queried = host.call_tool("get_request_result", {
            "run_id": "run", "request_id": standby["request_id"]})
        assert queried["data"]["outcome"] == "accepted"
        retried = host.call_tool("finish_delivery", {"conclusion": "work complete"},
                                 call_identity="native-finish-call")
        assert retried["data"]["runs"]["run"]["data"]["idempotent"] is True
        fifo.read_ready()
        assert fifo.pop_line() is None
    finally:
        fifo.close()
