"""Reproduce the bounded Delivery cost failures without provider/model calls."""
import copy
import json
from types import SimpleNamespace

import pytest

from modeling_team.competency_questions import content_digest
from modeling_team.delivery import DeliverySession
from modeling_team.outer_input import OuterInputFifo
from modeling_team.tests.test_delivery_decision_input import ack, bound_run, read
from modeling_team.tests.test_delivery_phase_threads import PhaseRuntime, ready
from modeling_team.tests.test_delivery_session import ROOT, session
from modeling_team.tests.test_delivery_token_reduction import yield_args
from modeling_team.tests.test_delivery_wakeups import _events_page, observation


def deferred(offset, delivery_id="delivery-8", detail="provider wait is active"):
    return {"source": "deliveries.jsonl", "byte_offset": offset,
            "data": {"event": "delivery-deferred", "delivery_id": delivery_id,
                     "recipient_id": "coordinator", "detail": detail,
                     "recorded_at": f"time-{offset}"}}


def test_repeated_deferred_delivery_does_not_queue_more_decisions_after_resume(tmp_path):
    host = session(tmp_path)
    raw = observation()
    host.record_observation(raw)
    ack(host)
    raw["runs"]["run"]["events"] = _events_page([deferred(1)], next_cursor="first")
    assert host.record_observation(raw)
    first = ack(host)
    assert "delivery-8" in json.dumps(first)
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    for offset in range(2, 22):
        raw["runs"]["run"]["events"] = _events_page([deferred(offset)], next_cursor=str(offset))
        assert not reopened.record_observation(raw)
    assert not reopened._pending_decisions
    for offset, delivery_id, detail in [(22, "delivery-9", "provider wait is active"),
                                        (23, "delivery-9", "different failure")]:
        raw["runs"]["run"]["events"] = _events_page(
            [deferred(offset, delivery_id, detail)], next_cursor=str(offset))
        assert reopened.record_observation(raw)
        ack(reopened)


def test_deferred_control_binding_changes_are_not_silenced(tmp_path):
    host = session(tmp_path)
    raw = observation()
    for epoch in (1, 2):
        event = deferred(epoch)
        event["data"]["control_epoch"] = epoch
        raw["runs"]["run"]["events"] = _events_page([event], next_cursor=str(epoch))
        assert host.record_observation(raw)
        ack(host)


def test_deferred_error_after_actual_delivery_is_visible_again(tmp_path):
    host = session(tmp_path)
    raw = observation()
    events = [deferred(1), {"source": "deliveries.jsonl", "byte_offset": 2,
              "data": {"type": "delivery", "delivery_id": "delivery-8",
                       "recipient_id": "coordinator", "text": "delivered"}}, deferred(3)]
    for event in events:
        raw["runs"]["run"]["events"] = _events_page([event], next_cursor=str(event["byte_offset"]))
        assert host.record_observation(raw)
        ack(host)


def test_large_decision_continues_the_v2_view_instead_of_raw_bookkeeping(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"][0]["description"] = "业务范围" * 12000
    host.record_observation(raw)
    journal = host.session_root / "session-events.jsonl"
    original = journal.read_bytes()
    first = host._model_observation()
    ref = first["read_original"]
    assert ref["path"] != str(journal)
    pieces = []
    result = read(host, ref["path"], source_ref=ref["source_ref"], selection=ref["selection"])
    while True:
        assert result["ok"], result
        data = result["data"]
        pieces.append(data["text"])
        if data["read_complete"]:
            break
        result = read(host, data["path"], **data["continuation"])
    view = json.loads("".join(pieces))
    assert view["schema_version"] == "delivery-decision-input/v2"
    assert view["input_id"] == first["input_id"]
    assert view["runs"]["run"]["pending"]["data"]["items"][0]["description"] == "业务范围" * 12000
    assert "fingerprint_state" not in view and "decision_event_state" not in view
    assert view["evidence"]["path"] == str(journal)
    assert journal.read_bytes().startswith(original)
    remaining = first["read_remaining"]
    rest = read(host, remaining["path"], source_ref=remaining["source_ref"],
                selection=remaining["selection"], max_bytes=16384)["data"]
    assert rest["returned_range"]["offset"] == first["page"]["next_offset"]


def test_historical_page_keeps_current_authorization_visible(tmp_path):
    host = session(tmp_path)
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"][0]["description"] = "旧页" * 20000
    host.record_observation(raw)
    ack(host)  # This historical input has actually begun delivery.
    assert host._pending_decisions[0]["offset"] > 0
    host._last_current["session"]["budget_control"] = {"authorized_amount": "6", "epoch": 4}
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "read-only"
    host.record_observation(raw)
    # This is the current binding snapshot, independent of the old page's bytes.
    host._last_current["session"]["budget_control"] = {"authorized_amount": "6", "epoch": 4}
    page = host._model_observation()
    assert page["current_state"]["budget_control"]["authorized_amount"] == "6"
    assert page["current_state"]["runs"]["run"]["write_phase"] == "read-only"


def test_rejected_recovery_is_a_terminal_receipt_and_cannot_be_waited_on(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    request = {"request_id": "recovery-2", "action": "recover_provider", "content_digest": "d"}
    (root / "control/host-requests.jsonl").write_text(json.dumps(request) + "\n")
    raw = observation()
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    host.record_observation(raw)
    ack(host)
    (root / "evidence/outer-input-receipts.jsonl").write_text(json.dumps({
        **request, "outcome": "rejected", "code": "provider_wait_not_pending"}) + "\n")
    assert host.record_observation(raw)
    packet = ack(host)
    projected = host._last_current["runs"]["run"]["requests"]["data"]
    assert projected["pending"] == []
    assert projected["settled"][0]["result"]["data"]["outcome"] == "rejected"
    assert packet["request_results"][0]["code"] == "provider_wait_not_pending"
    args = yield_args(packet["input_id"])
    args["waiting_for"] = [{"run_id": "run", "request_id": "recovery-2", "condition": "receipt"}]
    refused = host.call_tool("yield_delivery", args)
    assert not refused["ok"] and refused["error"]["code"] == "delivery_wait_already_rejected"
    assert refused["error"]["receipt"]["code"] == "provider_wait_not_pending"
    raw["runs"]["run"]["status"]["data"]["write_phase"] = "read-only"
    host.record_observation(raw)
    assert ack(host)["request_results"] == []
    reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                               config=host.config, resume=True)
    reopened.record_observation(raw, force_delivery=True)
    assert ack(reopened)["request_results"][0]["outcome"] == "rejected"


def test_rejected_freeze_does_not_offer_a_phase_boundary(tmp_path, monkeypatch):
    host, root = bound_run(tmp_path, monkeypatch)
    host.config["phase_thread_boundaries"] = ["production"]
    rows = [{"request_id": "freeze", "action": "cq_freeze", "content_digest": "f"},
            {"request_id": "notify", "action": "instruction", "content_digest": "n"}]
    (root / "control/host-requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (root / "evidence/outer-input-receipts.jsonl").write_text("".join(json.dumps({
        **r, "outcome": "rejected" if r["request_id"] == "freeze" else "accepted"
    }) + "\n" for r in rows))
    raw = observation()
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    host.record_observation(raw)
    assert "phase_thread_handoff" not in ack(host)["core"]


@pytest.mark.parametrize("supplied", ["omitted", None, "explicit-issue-resolution"])
def test_issue_resolution_has_stable_identity_and_does_not_block_phase_switch(
    tmp_path, monkeypatch, supplied,
):
    host, raw = ready(tmp_path, monkeypatch)
    host.allowed_operations.add("supervise")
    root = tmp_path / "run"
    args = {"run_id": "run", "issue_id": "issue-1", "reporter_id": "coordinator",
            "control_epoch": 1, "resolution_type": "guidance", "resolution_text": "Continue original scope."}
    if supplied != "omitted":
        args["request_id"] = supplied
    fifo = OuterInputFifo(root / "control/outer-input.fifo")
    fifo.open()
    try:
        result = host.call_tool("resolve_issue", args, call_identity="native-issue-1")
        assert result["ok"], result
        request_id = result["data"]["request_id"]
        assert request_id
        if isinstance(supplied, str) and supplied != "omitted":
            assert request_id == supplied
        fifo.read_ready()
        envelope = json.loads(fifo.pop_line())
        assert envelope.pop("request_id") == request_id
        retry = host.call_tool("resolve_issue", copy.deepcopy(args), call_identity="native-issue-1")
        assert retry["ok"] and retry["data"]["idempotent"]
        fifo.read_ready()
        assert fifo.pop_line() is None
        with (root / "evidence/outer-input-receipts.jsonl").open("a") as stream:
            stream.write(json.dumps({"request_id": request_id, "action": "issue_resolution",
                "content_digest": content_digest(envelope), "outcome": "accepted"}) + "\n")
        raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
        host.record_observation(raw)
        packet = ack(host)
        boundary = yield_args(packet["input_id"])
        boundary["waiting_for"] = [{"operation_id": "op", "condition": "independent report"}]
        boundary["thread_boundary"] = {"phase": "acceptance", "run_id": "run",
                                       "request_ids": ["handoff"]}
        assert host.call_tool("yield_delivery", boundary)["ok"]
        assert host.maybe_switch_phase_thread(PhaseRuntime())
    finally:
        fifo.close()


@pytest.mark.parametrize("epoch,message_id", [(4, "budget-3-old"), (5, "budget-4-current")])
def test_stale_budget_confirmation_is_actionable_without_conversation(tmp_path, epoch, message_id):
    host = session(tmp_path)
    state = {"epoch": epoch}
    recorded = []
    host.budget = SimpleNamespace(show=lambda **kw: state,
                                  record_control=lambda *a, **kw: recorded.append((a, kw)))
    host._budget_control_message = {"request_id": "budget-4-current", "epoch": 4, "action": "pause"}
    result = host.call_tool("record_flow_confirmation", {
        "message_id": message_id, "action": "pause", "status": "effective",
        "evidence_references": ["actual-acknowledgement"],
    })
    assert not result["ok"] and result["error"]["code"] == "budget_control_stale"
    assert result["error"]["budget_epoch"] == epoch
    assert result["error"]["current_control"] == (
        {"message_id": "budget-4-current", "action": "pause", "epoch": 4} if epoch == 4 else None
    )
    assert recorded == []


def test_flow_confirmation_names_wrong_evidence_shape_without_echoing_values(tmp_path):
    host = session(tmp_path)
    result = host.call_tool("record_flow_confirmation", {
        "message_id": "budget-current", "action": "pause", "status": "effective",
        "evidence_references": [{"budget_ref": "PRIVATE-INSTANCE"}],
    })
    assert not result["ok"] and result["error"]["code"] == "flow_confirmation_invalid"
    assert result["error"]["field"] == "evidence_references.0"
    assert result["error"]["expected"] == "string"
    assert "PRIVATE-INSTANCE" not in json.dumps(result)


def test_current_budget_confirmation_records_only_the_delivery_owner(tmp_path):
    host = session(tmp_path)
    recorded = []
    host.budget = SimpleNamespace(show=lambda **kw: {"epoch": 4},
                                  record_control=lambda *a, **kw: recorded.append((a, kw)))
    host._budget_control_message = {"request_id": "budget-4-current", "epoch": 4, "action": "pause"}
    result = host.call_tool("record_flow_confirmation", {
        "message_id": "budget-4-current", "action": "pause", "status": "effective",
        "evidence_references": ["Delivery stopped scheduling; actual acknowledgement"],
    })
    assert result["ok"], result
    assert recorded[0][0] == ("delivery:" + host.session_id, 4, "effective")


def test_view_reference_cannot_read_another_sessions_projection(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    first, second = session(tmp_path / "one"), session(tmp_path / "two")
    raw = observation()
    raw["runs"]["run"]["pending"]["data"]["items"][0]["description"] = "body" * 15000
    first.record_observation(raw)
    ref = first._model_observation()["read_original"]
    result = read(second, ref["path"], source_ref=ref["source_ref"], selection=ref["selection"])
    assert not result["ok"] and result["error"]["code"] == "artifact_forbidden"
