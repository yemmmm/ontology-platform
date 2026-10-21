"""Independent R4.3-029 engineering counterexamples; no Provider or live service."""
import json
import multiprocessing

import pytest

from modeling_team import host_ops
from modeling_team import delivery as delivery_module
from modeling_team.competency_questions import CQContractError
from modeling_team.delivery import DeliverySession
from modeling_team.delivery_host_actions import (
    append_session_event, host_action_state, record_host_action_result, request_host_action,
)
from modeling_team.tests.test_delivery_session import ROOT, _StubNativeRuntime, session
from modeling_team.tests.test_delivery_wakeups import _events_page, observation
from modeling_team.tests.test_host_ops import _make_run, _open_fifo, _pop_fifo_line
from modeling_team.tests.test_r3011_runner_wiring import _CQRunner, _draft, _question
from modeling_team.tests.test_r23009_resolution_reaches_modeling import _runner_with_pending_issue


def _request(host, request_id="repair-1"):
    return request_host_action(host.session_root, host.session_id, {"run"}, host.authorization, {
        "request_id": request_id, "run_id": "run", "kind": "platform_repair", "bindings": {},
        "expected_behavior": "bound applied revision visible", "actual_behavior": "revision absent",
        "write_state": "unknown", "hypotheses": ["projection stale", "filter legitimate"],
    })


def test_host_result_original_is_readable_only_via_its_bound_current_session(tmp_path):
    host = session(tmp_path)
    _request(host)
    folder = host.session_root / "host-results"
    folder.mkdir()
    original = folder / "report.json"
    original.write_text('{"checked":"write reconciled","limitations":[]}')
    record_host_action_result(host.session_root, "repair-1", "completed", original)
    result = host.call_tool("read_delivery_artifact", {"path": str(original)})
    assert result["ok"], result
    assert result["data"]["text"] == original.read_text()
    other = folder / "unbound.json"
    other.write_text('{"unbound":true}')
    assert not host.call_tool("read_delivery_artifact", {"path": str(other)})["ok"]
    relative = "host-results/report.json"
    assert host.call_tool("read_delivery_artifact", {"path": relative})["ok"]
    original.write_text('{"checked":"tampered"}')
    changed = host.call_tool("read_delivery_artifact", {"path": relative})
    assert not changed["ok"] and changed["error"]["code"] == "host_result_changed"
    original.unlink()
    missing = host.call_tool("read_delivery_artifact", {"path": relative})
    assert not missing["ok"] and missing["error"]["code"] == "artifact_unavailable"


def test_unknown_event_keeps_locator_and_does_not_inject_full_business_body(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["events"] = _events_page([{
        "source": "future-runtime-notification.jsonl", "byte_offset": 42,
        "data": {"event": "new_status", "status": "blocked", "text": "UNNECESSARY FULL BODY"},
    }], next_cursor="next")
    assert host.record_observation(raw)
    packet = host._model_observation()
    assert "UNNECESSARY FULL BODY" not in json.dumps(packet)
    event = packet["runs"]["run"]["events"]["data"]["events"][0]
    assert event["source"] == "future-runtime-notification.jsonl"
    assert event["byte_offset"] == 42
    assert "UNNECESSARY FULL BODY" in (host.session_root / "observation.json").read_text()


def test_host_completed_is_not_issue_recovery_or_write_reconciliation(tmp_path):
    host = session(tmp_path)
    host.run_ids.add("run")
    _request(host)
    folder = host.session_root / "host-results"
    folder.mkdir()
    original = folder / "report.json"
    original.write_text('{"status":"completed"}')
    record_host_action_result(host.session_root, "repair-1", "completed", original)
    before = observation()
    before["runs"]["run"]["status"]["data"]["first_blocker"] = {"classification": "platform-contract"}
    host.record_observation(before)
    packet = host._model_observation()
    assert packet["runs"]["run"]["status"]["data"]["first_blocker"]
    assert not host.reconciled_runs
    assert not host.verification_ids
    assert not host.call_tool("record_host_action_result", {"request_id": "repair-1"})["ok"]


def test_platform_repair_rejects_unverified_material_evidence(tmp_path, monkeypatch):
    host = session(tmp_path)
    host.run_ids.add("run")
    host.allowed_operations.add("supervise")
    monkeypatch.setattr(delivery_module.host_ops_mcp, "get_pending_actions", lambda **_: {"items": []})
    result = host.call_tool("request_host_action", {
        "request_id": "unbound-material", "run_id": "run", "kind": "platform_repair", "bindings": {},
        "evidence_references": [{"material_id": "not-an-authorized-material"}],
    })
    assert not result["ok"], result


def test_platform_repair_accepts_authorized_public_material_and_rejects_private_cq(tmp_path, monkeypatch):
    host = session(tmp_path)
    host.run_ids.add("run")
    host.allowed_operations.add("supervise")
    monkeypatch.setattr(delivery_module.host_ops_mcp, "get_pending_actions", lambda **_: {"items": []})
    public = next(iter(host.sources))
    publication = host.handoff_materials.publish("delivery", "runner", str(public))
    args = {"request_id": "public-evidence", "run_id": "run", "kind": "platform_repair",
            "bindings": {}, "evidence_references": [{"material_id": publication["material_id"]}]}
    assert host.call_tool("request_host_action", args)["ok"]
    private = tmp_path / "competency-questions" / "private" / "draft.json"
    private.parent.mkdir(parents=True)
    private.write_text('{"question":"PRIVATE CQ"}')
    host.handoff_materials.register_actor("delivery", {str(private): private}, {"runner"})
    private_package = host.handoff_materials.publish("delivery", "runner", str(private))
    args.update(request_id="private-evidence",
                evidence_references=[{"material_id": private_package["material_id"]}])
    rejected = host.call_tool("request_host_action", args)
    assert not rejected["ok"] and rejected["error"]["code"] == "host_action_evidence_forbidden"


def test_host_pending_and_unacknowledged_result_survive_delivery_resume(tmp_path):
    host = session(tmp_path)
    _request(host)
    host.record_observation(observation())
    folder = host.session_root / "host-results"
    folder.mkdir()
    original = folder / "blocked.json"
    original.write_text('{"limitation":"original verification unavailable"}')
    record_host_action_result(host.session_root, "repair-1", "blocked", original)
    assert host.record_observation(observation())
    restored = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    assert len(restored._pending_decisions) == 2
    assert host_action_state(restored.session_root)["unresolved"][0]["request_id"] == "repair-1"
    latest = restored._model_observation()
    # Unsent observations are coalesced, so the unresolved Host result is
    # present in the first current input rather than behind an old snapshot.
    assert any(row.get("request_id") == "repair-1" and row.get("status") == "blocked"
               for row in latest["unresolved"])
    assert "repair-1" in json.dumps(latest["changes"])
    assert restored._dispatch_observation(_StubNativeRuntime(), {"data": latest}, steer=False)
    assert not restored._pending_decisions
    assert host_action_state(restored.session_root)["unresolved"][0]["status"] == "blocked"


def _append_parallel(root, index, output):
    records = []
    for sequence in range(15):
        event = {"event": "parallel-check", "worker": index, "sequence": sequence, "value": "中" * 100}
        offset, length = append_session_event(root, event)
        records.append((offset, length, event))
    output.put(records)


def test_cross_process_journal_offsets_locate_exact_noninterleaved_lines(tmp_path):
    context = multiprocessing.get_context("fork")
    root = tmp_path / "parallel"
    root.mkdir(mode=0o700)
    output = context.Queue()
    workers = [context.Process(target=_append_parallel, args=(root, i, output)) for i in range(3)]
    for worker in workers:
        worker.start()
    records = [record for _ in workers for record in output.get(timeout=15)]
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0
    raw = (root / "session-events.jsonl").read_bytes()
    assert len(raw.splitlines()) == 45
    for offset, length, event in records:
        assert json.loads(raw[offset:offset + length]) == event


def test_direct_host_issue_recovery_does_not_require_delivery_verification_ids(tmp_path):
    repo, root = _make_run(tmp_path, "run-1")
    runner, issue = _runner_with_pending_issue(tmp_path, reporter="protocol", wire_issue_events=True)
    runner.run.root = root
    host = session(tmp_path)
    assert not host.verification_ids
    fifo = _open_fifo(root)
    try:
        submitted = host_ops.resolve_issue("run-1", repository_root=repo,
            issue_id=issue["issue_id"], reporter_id="protocol", control_epoch=1,
            resolution_type="repair_completed", repair_component="external_service",
            before_digest="sha256:before", after_digest="sha256:after",
            verification_reference="retained-host-verification.json", mutation_reconciliation="reconciled")
        assert submitted["status"] == "submitted"
        runner.receive_outer(_pop_fifo_line(fifo))
    finally:
        fifo.close()
    ledger = runner.transport.issue_ledger
    assert ledger.state == "resume_sent"
    assert ledger.active.resolution.verification_reference == "retained-host-verification.json"
    assert not host.verification_ids


def test_host_review_then_delivery_freeze_uses_original_pool_contract(tmp_path):
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        marker = "PRIVATE QUESTION MUST STAY HOST ONLY"
        runner._publish_cq_question_draft({"cq_id": "competency-question", "draft": _draft([
            _question("cq-public"), _question("cq-hidden", visibility="hidden", question=marker),
        ])})
        host = session(tmp_path)
        host.run_ids.add(runner.run.run_id)
        host.allowed_operations.add("supervise")
        pending = host.call_tool("get_pending_actions", {"run_id": runner.run.run_id})
        assert pending["ok"], pending
        binding = next(i for i in pending["data"]["items"] if i["type"] == "cq_review")["bindings"]
        arguments = {"request_id": "cq-host-request", "run_id": runner.run.run_id,
                     "kind": "cq_review", "bindings": binding}
        assert host.call_tool("request_host_action", arguments)["ok"]
        assert marker not in (host.session_root / "session-events.jsonl").read_text()
        assert "submit_cq_review" not in {s["name"] for s in host.tool_specs()}
        fifo = _open_fifo(runner.run.root)
        try:
            assert host.call_tool("freeze_cq", {"run_id": runner.run.run_id})["ok"]
            with pytest.raises(CQContractError):
                runner.handle_cq_outer_input(_pop_fifo_line(fifo))
            # Stale Host review is rejected by the original digest guard.
            host_ops.submit_cq_review(runner.run.run_id, review_id=binding["review_id"],
                question_id="cq-public", decision="approve", content_version=binding["content_version"],
                content_digest_value="sha256:" + "f" * 64)
            with pytest.raises(CQContractError):
                runner.handle_cq_outer_input(_pop_fifo_line(fifo))
            for question_id in binding["question_ids"]:
                host_ops.submit_cq_review(runner.run.run_id, review_id=binding["review_id"],
                    question_id=question_id, decision="approve", content_version=binding["content_version"],
                    content_digest_value=binding["content_digest"], note="authorized Host review")
                accepted = runner.handle_cq_outer_input(_pop_fifo_line(fifo))
                assert accepted["type"] == "cq-review-accepted"
            assert host.call_tool("freeze_cq", {"run_id": runner.run.run_id})["ok"]
            runner.handle_cq_outer_input(_pop_fifo_line(fifo))
        finally:
            fifo.close()
        assert runner._cq_freeze["ordering"] == ["cq-public", "cq-hidden"]
    finally:
        harness.cleanup()
