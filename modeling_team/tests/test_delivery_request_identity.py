"""Delivery instructions retain a queryable identity through FIFO and phase handoff."""
import json

import pytest

from modeling_team.competency_questions import content_digest
from modeling_team.delivery import DeliverySession
from modeling_team.outer_input import OuterInputFifo
from modeling_team.tests.test_delivery_decision_input import ack, bound_run
from modeling_team.tests.test_delivery_phase_threads import PhaseRuntime, ready
from modeling_team.tests.test_delivery_session import ROOT
from modeling_team.tests.test_delivery_token_reduction import yield_args
from modeling_team.tests.test_delivery_wakeups import observation


@pytest.mark.parametrize("supplied", ["omitted", None, "explicit-notification"])
def test_instruction_identity_survives_resume_and_does_not_replay_fifo(
    tmp_path, monkeypatch, supplied
):
    host, root = bound_run(tmp_path, monkeypatch)
    host.allowed_operations.add("supervise")
    args = {"run_id": "run", "kind": "delivery_guidance", "text": "The CQ pool is frozen.",
            "source_reference": "approved-freeze", "authorization_reference": host.authorization}
    if supplied != "omitted":
        args["request_id"] = supplied
    fifo = OuterInputFifo(root / "control/outer-input.fifo")
    fifo.open()
    try:
        submitted = host.call_tool("submit_instruction", args, call_identity="native-notify-1")
        assert submitted["ok"], submitted
        request_id = submitted["data"]["request_id"]
        assert request_id
        if isinstance(supplied, str) and supplied != "omitted":
            assert request_id == supplied
        assert args.get("request_id") == (None if supplied == "omitted" else supplied)
        fifo.read_ready()
        envelope = json.loads(fifo.pop_line())
        assert envelope.pop("request_id") == request_id
        reopened = DeliverySession(repository_root=ROOT, session_root=host.session_root,
                                   config=host.config, resume=True)
        reopened.allowed_operations.add("supervise")
        uncertain = reopened.call_tool("submit_instruction", args, call_identity="native-notify-1")
        assert uncertain["ok"], uncertain
        assert uncertain["data"]["request_id"] == request_id
        assert uncertain["data"]["status"] == "submitted"
        assert uncertain["data"]["idempotent"] is True
        fifo.read_ready()
        assert fifo.pop_line() is None
        receipt = {"request_id": request_id, "action": "instruction", "outcome": "accepted",
                   "content_digest": content_digest(envelope)}
        (root / "evidence/outer-input-receipts.jsonl").write_text(json.dumps(receipt) + "\n")
        retried = reopened.call_tool("submit_instruction", args, call_identity="native-notify-1")
        assert retried["ok"], retried
        assert retried["data"]["request_id"] == request_id
        assert retried["data"]["idempotent"] is True
        fifo.read_ready()
        assert fifo.pop_line() is None
        ledger = root / "control/host-requests.jsonl"
        assert len(ledger.read_text().splitlines()) == 1
        raw = observation()
        raw["runs"]["run"]["request_ledger"] = reopened._observe_request_ledger("run")
        reopened.record_observation(raw)
        projected = reopened._last_current["runs"]["run"]["requests"]["data"]
        assert not projected["pending"]
        assert projected["settled"][0]["request_id"] == request_id
    finally:
        fifo.close()


def test_generated_notification_identity_allows_a_real_production_boundary(tmp_path, monkeypatch):
    host, raw = ready(tmp_path, monkeypatch)
    host.allowed_operations.add("supervise")
    host.config["phase_thread_boundaries"] = ["production"]
    root = tmp_path / "run"
    freeze = {"request_id": "freeze", "action": "cq_freeze", "content_digest": "f"}
    (root / "control/host-requests.jsonl").write_text(json.dumps(freeze) + "\n")
    receipts = root / "evidence/outer-input-receipts.jsonl"
    receipts.write_text(json.dumps({**freeze, "outcome": "accepted"}) + "\n")
    fifo = OuterInputFifo(root / "control/outer-input.fifo")
    fifo.open()
    try:
        result = host.call_tool("submit_instruction", {
            "run_id": "run", "kind": "delivery_guidance", "text": "Frozen; continue production.",
            "source_reference": "freeze", "authorization_reference": host.authorization,
        }, call_identity="native-freeze-notification")
        assert result["ok"], result
        request_id = result["data"]["request_id"]
        assert request_id
        fifo.read_ready()
        envelope = json.loads(fifo.pop_line())
        assert envelope.pop("request_id") == request_id
        with receipts.open("a") as handle:
            handle.write(json.dumps({"request_id": request_id, "action": "instruction",
                "content_digest": content_digest(envelope), "outcome": "accepted"}) + "\n")
        raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
        host.record_observation(raw)
        packet = ack(host)
        hint = packet["core"]["phase_thread_handoff"]
        assert hint["notification_request_ids"] == [request_id]
        args = yield_args(packet["input_id"])
        args["thread_boundary"] = {**hint["thread_boundary"], "request_ids": ["freeze", request_id]}
        assert host.call_tool("yield_delivery", args)["ok"]
        runtime = PhaseRuntime()
        assert host.maybe_switch_phase_thread(runtime)
        assert runtime.switches == 1
    finally:
        fifo.close()


def test_legacy_null_identity_is_locatable_and_does_not_offer_an_unsafe_handoff(
    tmp_path, monkeypatch
):
    host, raw = ready(tmp_path, monkeypatch)
    ledger = tmp_path / "run/control/host-requests.jsonl"
    with ledger.open("a") as handle:
        handle.write(json.dumps({"action": "instruction", "request_id": None,
                                 "content_digest": "legacy-guidance"}) + "\n")
    original = ledger.read_bytes()
    raw["runs"]["run"]["request_ledger"] = host._observe_request_ledger("run")
    host.record_observation(raw)
    packet = ack(host)
    pending = next(r for r in packet["unresolved"] if r.get("kind") == "request")
    assert pending["error"]["code"] == "request_identity_missing"
    assert "do not resend" in pending["error"]["next_action"]
    hint = packet["core"]["phase_thread_handoff"]
    assert hint["status"] == "deferred" and "thread_boundary" not in hint
    assert hint["blocker"]["run_id"] == "run"
    assert hint["blocker"]["ledger_ref"]["path"] == str(ledger)
    assert hint["blocker"]["ledger_ref"]["byte_offset"] > 0
    args = yield_args(packet["input_id"])
    assert host.call_tool("yield_delivery", args)["ok"]
    runtime = PhaseRuntime()
    assert not host.maybe_switch_phase_thread(runtime)
    assert not runtime.switches
    assert ledger.read_bytes() == original
