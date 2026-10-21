"""R4.3-030 F1/F2 offline contracts; these do not prove live token savings."""
import copy
import importlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from modeling_team.delivery import DeliverySession
from modeling_team.tests.test_delivery_decision_input import ack, read, bound_run
from modeling_team.tests.test_delivery_session import ROOT, session
from modeling_team.tests.test_delivery_wakeups import observation


def yield_args(input_id):
    return {"input_id": input_id, "phase": "cq_review",
            "waiting_for": [{"run_id": "run", "condition": "Host review receipt"}],
            "next_action": "check the actual review binding", "reason": "review is pending",
            "active_decisions": [{"decision_id": "keep-scope", "text": "retain the full scope",
                                  "source_references": ["user-test"], "replaces": []}]}


def test_host_objective_and_round_snapshot_reach_bootstrap_and_resume(tmp_path):
    host = session(tmp_path)
    host.config.update(
        delivery_objective="Use operation prefix chosen-by-host and timeout=900; close on completion.",
        authorization_budget={"total_modeling_rounds": 3, "consumed": 0, "remaining": 3,
                              "ledger_reference": "host-owned-authorization.json"},
        initial_run_id="host-chosen-run",
        freeze_started_at="2026-10-18T12:48:51+00:00",
        provider_secret="NOT-FOR-THE-MODEL",
    )
    host.record_observation(observation(), force_delivery=True)
    first = ack(host)
    context = first["core"]["task_context"]
    assert context["delivery_objective"] == host.config["delivery_objective"]
    assert context["authorization_budget"]["remaining"] == 3
    assert context["initial_run_id"] == "host-chosen-run"
    assert context["freeze_started_at"] == "2026-10-18T12:48:51+00:00"
    assert "NOT-FOR-THE-MODEL" not in json.dumps(first)
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    reopened.record_observation(observation(), force_delivery=True)
    assert ack(reopened)["core"]["task_context"] == context


def test_unchanged_host_objective_is_not_resent_but_updates_are_delivered(tmp_path):
    host = session(tmp_path)
    host.config["delivery_objective"] = "STABLE-HOST-OBJECTIVE"
    raw = observation()
    host.record_observation(raw)
    assert "STABLE-HOST-OBJECTIVE" in json.dumps(ack(host))
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "read-only"
    host.record_observation(raw)
    delta = ack(host)
    assert "STABLE-HOST-OBJECTIVE" not in json.dumps(delta)
    assert "unchanged_delivery_objective" in delta["coverage"]["omitted_sections"]
    host.config["delivery_objective"] = "UPDATED-HOST-OBJECTIVE"
    assert host.record_observation(raw)
    assert "UPDATED-HOST-OBJECTIVE" in json.dumps(ack(host)["changes"])


def test_stable_task_context_and_run_identity_are_not_resent_in_delta(tmp_path):
    host = session(tmp_path)
    host.config.update(task="task.yaml", scope="scope.yaml")
    raw = observation()
    raw["runs"]["run"]["status"]["data"]["identity"] = {"baseline": "BASELINE-IDENTITY"}
    host.record_observation(raw)
    first = ack(host)
    assert first["core"]["task_context"]["task"] == "task.yaml"
    assert first["core"]["runs"]["run"]["identity"]["baseline"] == "BASELINE-IDENTITY"
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    host.record_observation(raw)
    delta = ack(host)
    assert "task_context" not in delta["core"]
    assert "identity" not in delta["core"]["runs"]["run"]
    assert delta["core"]["runs"]["run"]["write_phase"] == "unknown"
    assert "unchanged_task_context" in delta["coverage"]["omitted_sections"]
    assert "unchanged_run_identity" in delta["coverage"]["omitted_sections"]
    host.config["task"] = "changed-task.yaml"
    host.record_observation(raw)
    changed = ack(host)
    assert changed["core"]["task_context"]["task"] == "changed-task.yaml"
    host.record_observation(raw, force_delivery=True)
    restored = ack(host)
    assert restored["core"]["task_context"]["task"] == "changed-task.yaml"
    assert restored["core"]["runs"]["run"]["identity"]["baseline"] == "BASELINE-IDENTITY"


def test_coverage_indices_share_the_packet_evidence_reference(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    packet = ack(host)
    reference = packet["evidence"]
    for section in ("collections", "history"):
        for entry in packet["coverage"][section].values():
            assert entry["evidence_ref"] == "evidence"
            assert "evidence" not in entry
    original = json.loads(read(host, reference["path"], source_ref=reference["source_ref"],
                               selection=reference["selection"])["data"]["text"])
    assert original["input_id"] == packet["input_id"]


def test_yield_is_durable_but_does_not_ack_or_manufacture_a_wakeup(tmp_path):
    host = session(tmp_path)
    host.run_ids.add("run")
    host.record_observation(observation())
    input_id = host._model_observation()["input_id"]
    pending = copy.deepcopy(host._pending_decisions)
    result = host.call_tool("yield_delivery", yield_args(input_id))
    assert result["ok"], result
    assert result["data"]["status"] == "waiting_recorded"
    assert result["data"]["end_current_turn"] is True
    assert host._pending_decisions == pending
    assert not host.record_observation(observation())
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    assert reopened.last_yield["active_decisions"][0]["decision_id"] == "keep-scope"
    assert reopened._pending_decisions[0]["input_id"] == input_id
    bad = yield_args(input_id)
    bad["waiting_for"][0]["run_id"] = "another-session"
    assert not reopened.call_tool("yield_delivery", bad)["ok"]
    assert not reopened.call_tool("yield_delivery", yield_args("unknown-input"))["ok"]


def test_yield_accepts_a_just_submitted_real_request_without_a_model_poll(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    host.record_observation(observation())
    input_id = ack(host)["input_id"]
    # A submission made after the last observed input already has a real Host
    # ledger identity. The model need not actively poll just to bind its wait.
    (root / "control/host-requests.jsonl").write_text(json.dumps({
        "request_id": "just-submitted", "content_digest": "d1", "action": "freeze_cq"}) + "\n")
    args = yield_args(input_id)
    args["waiting_for"][0]["request_id"] = "just-submitted"
    assert host.call_tool("yield_delivery", args)["ok"]
    args["waiting_for"][0]["request_id"] = "not-in-ledger"
    invalid = host.call_tool("yield_delivery", args)
    assert not invalid["ok"] and invalid["error"]["retryable"] is True


def test_v2_changes_do_not_repeat_stable_bodies_and_keep_unknown_events(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"][0]["description"] = "STABLE-BUSINESS-BODY"
    host.record_observation(raw)
    bootstrap = ack(host)
    assert bootstrap["schema_version"] == "delivery-decision-input/v2"
    assert bootstrap["mode"] == "bootstrap"
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    raw["runs"]["run"]["events"]["data"]["events"] = [
        {"source": "new-kind.jsonl", "byte_offset": 0, "data": {"error": "NEEDS-DECISION"}}]
    assert host.record_observation(raw)
    delta = ack(host)
    assert delta["mode"] == "changes" and "runs" not in delta
    assert "STABLE-BUSINESS-BODY" not in json.dumps(delta)
    assert delta["unresolved"][0]["id"] == "question-1"
    assert "NEEDS-DECISION" in json.dumps(delta["changes"])
    assert "unknown" in json.dumps(delta["core"])
    assert delta["coverage"]["omitted_sections"]


def test_model_queries_are_views_and_observe_retains_raw_results(tmp_path, monkeypatch):
    host = session(tmp_path)
    host.run_ids.add("run")
    module = importlib.import_module("modeling_team.delivery")
    original = {"run_id": "run", "recorded_state": {"state": "RUNNING"},
                "first_blocker": {"message": "must not disappear"},
                "evidence_refs": [{"path": "huge-history"}], "extra": "RAW-ONLY"}
    monkeypatch.setattr(module.host_ops_mcp, "get_run_status", lambda **kw: copy.deepcopy(original))
    result = host.call_tool("get_run_status", {"run_id": "run"})
    assert result["data"]["recorded_state"] == original["recorded_state"]
    assert "RAW-ONLY" not in json.dumps(result)
    assert result["coverage"]["source_complete"] is False
    evidence = result["evidence"]
    stored = json.loads(read(host, evidence["path"], source_ref=evidence["source_ref"],
                             selection=evidence["selection"])["data"]["text"])
    assert stored["result"]["data"] == original
    assert host.observe()["runs"]["run"]["status"]["data"] == original
    assert not host.call_tool("get_run_status", {"run_id": "run", "_model_view": False})["ok"]


def test_large_changed_value_has_body_pages_not_just_a_reference(tmp_path):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    ack(host)
    message = "完整阻塞原因" * 10000
    raw["runs"]["run"]["status"]["data"]["first_blocker"] = {"message": message}
    host.record_observation(raw)
    chunks = []
    while host._pending_decisions:
        page = ack(host)
        assert len(json.dumps(page, ensure_ascii=False).encode()) <= 32000
        chunks.append(page["page"]["text"])
    payload = json.loads("".join(chunks))
    assert payload["core"]["first_blockers"]["run"]["preview_complete"] is False
    assert any(row.get("value", {}).get("message") == message
               for row in payload["changes"] if isinstance(row.get("value"), dict))
    assert json.dumps(payload, ensure_ascii=False).count(message) == 1


def test_deadline_is_one_change_even_when_host_is_static_and_after_resume(tmp_path, monkeypatch):
    host = session(tmp_path)
    module = importlib.import_module("modeling_team.delivery")
    instant = datetime(2026, 10, 17, tzinfo=UTC)
    monkeypatch.setattr(module, "_utc_now", lambda: instant)
    host.authorization_valid_until = (instant + timedelta(seconds=1)).isoformat()
    host.config["authorization_valid_until"] = host.authorization_valid_until
    raw = observation()
    host.record_observation(raw)
    ack(host)
    instant += timedelta(seconds=2)
    assert host.record_observation(raw)
    assert "authorization_expired" in json.dumps(ack(host))
    assert not host.record_observation(raw)
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    assert not reopened.record_observation(raw)


def test_resume_bootstrap_does_not_ack_historical_unknown_input(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    original_id = host._pending_decisions[0]["input_id"]
    from modeling_team.runtimes.delivery import DeliveryRuntimeError
    class UnknownReceipt:
        def send(self, text):
            raise DeliveryRuntimeError("unknown receipt")
    assert not host._dispatch_observation(UnknownReceipt(), {
        "kind": "host_observation", "data": host._model_observation()}, steer=False)
    latest = observation()
    latest["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    host.record_observation(latest, force_delivery=True)
    bootstrap = host._bootstrap_observation()
    assert bootstrap["mode"] == "bootstrap"
    host._dispatch_observation(type("Native", (), {"send": lambda _, text: None})(),
        {"kind": "delivery_resume", "observed_state": bootstrap}, steer=False)
    assert host._pending_decisions[0]["input_id"] == original_id
    assert host._pending_decisions[0]["delivery_status"] == "unknown"
    assert len(host._pending_decisions) == 1


def test_explicit_task_and_operation_timeouts_do_not_invent_heartbeat_timeouts(tmp_path, monkeypatch):
    host = session(tmp_path)
    module = importlib.import_module("modeling_team.delivery")
    instant = datetime(2026, 10, 17, tzinfo=UTC)
    monkeypatch.setattr(module, "_utc_now", lambda: instant)
    host.config["deadline"] = (instant + timedelta(seconds=5)).isoformat()
    raw = observation()
    raw["operations"]["op"]["data"].update(started_at=instant.isoformat(),
        request_binding={"session_timeout": 5})
    host.record_observation(raw)
    ack(host)
    instant += timedelta(seconds=6)
    assert host.record_observation(raw)
    kinds = {row["kind"] for row in ack(host)["core"]["deadline_events"]}
    assert kinds == {"task_deadline_reached", "operation_timeout"}
    assert not host.record_observation(raw)
    # Completion ends the timeout wait; a retained standby is not a timeout.
    raw["operations"]["op"]["data"].update(work_state="completed", lifecycle="standby")
    host.record_observation(raw)
    assert {row["kind"] for row in ack(host)["core"]["deadline_events"]} == {"task_deadline_reached"}


@pytest.mark.parametrize("name,arguments,raw", [
    ("get_pending_actions", {"run_id": "run"}, {"run_id": "run", "items": [{
        "type": "cq_review", "bindings": {"review_id": "r1"},
        "available_actions": [{"private": "PRIVATE-CQ-BODY"}]}], "extra": "RAW-ONLY"}),
    ("get_evaluation_status", {"operation_id": "op"}, {"operation_id": "op", "status": "running",
        "work_state": "completed", "report_binding": {"valid": False, "validation_errors": ["changed"]},
        "request_binding": {"run_id": "run", "freeze_id": "f1"}, "log_tails": "RAW-ONLY"}),
    ("get_request_result", {"run_id": "run", "request_id": "r1"}, {"request_id": "r1",
        "outcome": "rejected", "code": "not_ready", "reason": "wait for production",
        "retryable": True, "next_action": "new request after readiness", "extra": "RAW-ONLY"}),
])
def test_all_model_query_views_keep_bindings_errors_and_private_boundaries(tmp_path, monkeypatch, name, arguments, raw):
    host = session(tmp_path)
    host.run_ids.add("run")
    host.operation_ids.add("op")
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.host_ops_mcp, name, lambda **kw: copy.deepcopy(raw))
    response = host.call_tool(name, arguments)
    assert response["ok"]
    assert "RAW-ONLY" not in json.dumps(response)
    assert "PRIVATE-CQ-BODY" not in json.dumps(response)
    for key in ("report_binding", "request_binding", "outcome", "code", "reason", "next_action"):
        if key in raw:
            assert response["data"][key] == raw[key]
    assert host.call_tool(name, arguments, _model_view=False)["data"] == raw


def test_paged_facts_stay_stable_across_unknown_receipt_and_newer_state(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"][0]["description"] = "正文" * 20000
    host.record_observation(raw)
    original = host._pending_decisions[0]
    first = ack(host)
    offset = original["offset"]
    original["delivery_status"] = "unknown"
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
    host.record_observation(raw)
    page = host._model_observation()
    assert page["page"]["offset"] == offset and page["delivery_status"] == "unknown"
    assert page["current_state"]["input_id"] != original["input_id"]
    chunks = [first["page"]["text"]]
    while host._pending_decisions and host._pending_decisions[0] is original:
        chunks.append(ack(host)["page"]["text"])
    decoded = json.loads("".join(chunks))
    assert decoded["runs"]["run"]["pending"]["data"]["items"][0]["description"] == "正文" * 20000


def test_old_v1_partial_input_is_converted_without_rewriting_the_record(tmp_path):
    host = session(tmp_path)
    host.record_observation(observation())
    journal = host.session_root / "session-events.jsonl"
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    original = next(row for row in records if row.get("event") == "delivery_decision_input")
    original.pop("mode")
    original.pop("continuation")
    # An old v1 offset refers to a different serialized view, so v2 starts its
    # fact projection at zero while retaining the original identity and bytes.
    records.append({"event": "delivery_input_dispatch", "input_id": original["input_id"],
                    "status": "accepted", "complete": False, "next_offset": 12000})
    journal.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records))
    before = journal.read_bytes()
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root, config=host.config, resume=True)
    assert journal.read_bytes().startswith(before)
    assert reopened._pending_decisions[0]["offset"] == 0
    view = reopened._model_observation()
    assert view["schema_version"] == "delivery-decision-input/v2"
    assert view["source_schema_version"] == "delivery-decision-input/v1"
    assert view["input_id"] == original["input_id"]


def test_bootstrap_preserves_all_original_user_constraints_and_not_whole_config(tmp_path):
    host = session(tmp_path)
    first = host.accept_user_input("保留全部业务范围；旧约束不能被最后一句覆盖")
    second = host.accept_user_input("补充：确认未知写入后再行动")
    host.config.update(objective="same goal", private_provider_token="CREDENTIAL-CANARY")
    host.record_observation(observation(), force_delivery=True)
    payload = host._bootstrap_observation()
    assert payload["core"]["task_context"]["objective"] == "same goal"
    assert "CREDENTIAL-CANARY" not in json.dumps(payload)
    assert payload["recovery_context"]["user_messages"] == [first, second]


def test_program_wait_observes_repeatedly_without_new_turns_then_wakes(tmp_path, monkeypatch):
    from modeling_team.tests.test_delivery_session import _run_delivery_with_stub, _StubNativeRuntime
    module = importlib.import_module("modeling_team.delivery")
    count = 0
    ticks = 0
    native = None
    def observe(self):
        nonlocal count
        count += 1
        if count == 8:
            self.finished = True
        raw = observation()
        if count >= 6:
            raw["runs"]["run"]["status"]["data"]["write_phase"] = "unknown"
        return raw
    def monotonic():
        nonlocal ticks
        ticks += 3
        return ticks
    class Native(_StubNativeRuntime):
        def poll(self, timeout=0):
            if not self.busy:
                return []
            data = json.loads(self.sent[-1])
            packet = data.get("observed_state") or data["data"]
            # This deterministic runtime models natural completion after the
            # local yield receipt; it makes no active Host status queries.
            result = self.handler("yield_delivery", yield_args(packet["input_id"]))
            assert result["ok"], result
            self.busy = False
            self.events.append("turn_completed")
            return [{"event": "turn_completed", "status": "completed"}]
    def factory(**kwargs):
        nonlocal native
        native = Native()
        native.handler = kwargs["tool_handler"]
        return native
    # Reuse the existing repository/input fixture; only replace its factory
    # at the point of execution, without starting a provider or production.
    original = module._run_delivery
    def run(config, **kwargs):
        monkeypatch.setattr(module, "DeliveryRuntime", factory)
        monkeypatch.setattr(module.time, "monotonic", monotonic)
        return original(config, **kwargs)
    monkeypatch.setattr(module, "_run_delivery", run)
    monkeypatch.setattr(module.DeliverySession, "observe", observe)
    # A configured input server preserves supervision even after stdin EOF.
    _, result, _ = _run_delivery_with_stub(tmp_path, monkeypatch, [], run_ids=["run"],
                                         config_overrides={"project_id": "project"})
    assert result == 0 and count == 8
    assert len(native.sent) == 2 and not native.steered
    assert native.events.count("turn_completed") == 2
    assert "interrupt" not in native.events


@pytest.mark.parametrize("data", [None, [], {"items": None}, {"items": ["damaged"]}])
def test_malformed_query_result_retains_uncertainty_and_original(tmp_path, monkeypatch, data):
    host = session(tmp_path)
    host.run_ids.add("run")
    module = importlib.import_module("modeling_team.delivery")
    monkeypatch.setattr(module.host_ops_mcp, "get_pending_actions", lambda **kw: data)
    result = host.call_tool("get_pending_actions", {"run_id": "run"})
    assert result["coverage"]["complete"] is False
    assert result["coverage"]["limitations"]
    assert result["data"] == data
