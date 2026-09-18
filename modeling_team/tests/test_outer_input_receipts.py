"""R3.0-016 S1 Runner-side request_id receipt tests (shared plan §5).

Every case drives the real shared admission path
:func:`modeling_team.__main__._handle_foreground_message` on the real
``TeamRunner`` CQ harness: the ``request_id`` pop, the receipt line in
``evidence/outer-input-receipts.jsonl`` for accepted and rejected outcomes,
the no-receipt cases (bad JSON, no request_id, non-string request_id, a Runner
double without ``_append_evidence``), and the digest-consistency loop with the
op-layer ledger and ``get_request_result``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modeling_team import host_ops
from modeling_team.__main__ import _handle_foreground_message
from modeling_team.competency_questions import content_digest
from modeling_team.outer_input import OuterInputFifo
from modeling_team.tests.test_r3011_runner_wiring import _CQRunner

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def cq_harness():
    harness = _CQRunner()
    runner = harness.prepare()
    yield runner
    harness.cleanup()


def _receipts_path(runner) -> Path:
    return runner.run.root / "evidence" / "outer-input-receipts.jsonl"


def _receipts(runner) -> list[dict]:
    path = _receipts_path(runner)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _foreground(runner, message: dict, *, observe_emit=None):
    """Drive one message through the real shared admission path."""

    emitted: list = []
    rejected: list = []

    def emit(envelopes) -> None:
        emitted.extend(envelopes)
        if observe_emit is not None:
            observe_emit()

    def reject(detail=None) -> None:
        rejected.append(detail or True)

    output = _handle_foreground_message(
        runner, json.dumps(message, ensure_ascii=False), emit, reject
    )
    return output, emitted, rejected


def test_request_id_is_popped_before_validation_and_rejections_get_receipts(cq_harness):
    runner = cq_harness
    # An unknown action with a request_id: rejected before dispatch, but the
    # id was already extracted and a receipt line exists.
    output, emitted, rejected = _foreground(
        runner, {"action": "cq_adjust", "request_id": "req-unknown"}
    )
    assert output == [] and emitted == [] and rejected == [True]
    (receipt,) = _receipts(runner)
    assert receipt["request_id"] == "req-unknown"
    assert receipt["action"] == "cq_adjust"
    assert receipt["outcome"] == "rejected"
    assert receipt["code"] == "invalid_outer_input"
    assert receipt["content_digest"] == content_digest({"action": "cq_adjust"})
    assert receipt["recorded_at"]


def test_accepted_cq_input_receipt_carries_the_ack_type_and_no_hidden_echo(cq_harness):
    runner = cq_harness
    seen_in_emit: list[list[dict]] = []

    def observe_emit() -> None:
        # The receipt is appended before the acknowledgement is emitted.
        seen_in_emit.append(_receipts(runner))

    output, emitted, rejected = _foreground(
        runner,
        {"action": "cq_interview", "text": "访谈输入\n第二段", "request_id": "req-cq-1"},
        observe_emit=observe_emit,
    )
    assert rejected == []
    assert [item["type"] for item in emitted] == ["cq-interview-accepted"]
    # The receipt existed already when the emit callback ran.
    assert seen_in_emit and seen_in_emit[0] and seen_in_emit[0][0]["request_id"] == "req-cq-1"
    (receipt,) = _receipts(runner)
    assert receipt["action"] == "cq_interview"
    assert receipt["outcome"] == "accepted"
    assert receipt["ack_type"] == "cq-interview-accepted"
    assert receipt["content_digest"] == content_digest(
        {"action": "cq_interview", "text": "访谈输入\n第二段"}
    )
    # The id never leaks into the interview evidence or the ack.
    interview = (runner.run.root / "evidence" / "cq-interview.jsonl").read_text("utf-8")
    assert "req-cq-1" not in interview
    assert "request_id" not in interview
    assert "request_id" not in json.dumps(emitted)


def test_rejected_cq_input_receipt_carries_the_runner_reason_code(cq_harness):
    runner = cq_harness
    # A freeze on an empty pool is the deterministic CQContractError path.
    _output, _emitted, _rejected = _foreground(
        runner, {"action": "cq_freeze", "request_id": "req-cq-2"}
    )
    (receipt,) = _receipts(runner)
    assert receipt["outcome"] == "rejected"
    assert receipt["code"] == "cq_freeze_schema_mismatch"
    assert receipt["action"] == "cq_freeze"


def test_recoverable_rejection_from_receive_outer_gets_a_receipt(cq_harness):
    runner = cq_harness
    _output, _emitted, rejected = _foreground(
        runner,
        {"action": "recover_provider", "text": "恢复说明", "request_id": "req-prov-1"},
    )
    assert rejected and rejected[0]["code"] == "invalid_provider_recovery"
    (receipt,) = _receipts(runner)
    assert receipt["outcome"] == "rejected"
    assert receipt["code"] == "invalid_provider_recovery"


def test_accepted_receive_outer_input_receipt_without_an_ack(cq_harness):
    runner = cq_harness
    # ``status`` with no pending provider wait drains to no output: the
    # accepted receipt then carries ack_type None (no invented acknowledgement).
    output, emitted, rejected = _foreground(
        runner, {"action": "status", "request_id": "req-status-1"}
    )
    assert rejected == []
    assert output == [] and emitted == []
    (receipt,) = _receipts(runner)
    assert receipt["request_id"] == "req-status-1"
    assert receipt["action"] == "status"
    assert receipt["outcome"] == "accepted"
    assert receipt.get("ack_type") is None  # no output -> no invented ack type
    assert receipt["content_digest"] == content_digest({"action": "status"})


def test_bad_json_line_leaves_no_receipt(cq_harness):
    runner = cq_harness
    emitted: list = []
    rejected: list = []
    output = _handle_foreground_message(
        runner,
        "{not json",
        lambda envelopes: emitted.extend(envelopes),
        lambda: rejected.append(True),
    )
    assert output == [] and rejected == [True]
    assert _receipts(runner) == []


def test_line_without_request_id_behaves_exactly_as_before(cq_harness):
    runner = cq_harness
    _output, _emitted, rejected = _foreground(
        runner, {"action": "cq_interview", "text": "无关联id的输入"}
    )
    assert rejected == []
    assert _receipts(runner) == []
    # The interview evidence is the only trace, identical to the pre-S1 shape.
    (record,) = [
        json.loads(line)
        for line in (runner.run.root / "evidence" / "cq-interview.jsonl")
        .read_text("utf-8")
        .splitlines()
    ]
    assert "request_id" not in record


def test_non_string_request_id_is_ignored_entirely(cq_harness):
    runner = cq_harness
    _output, _emitted, rejected = _foreground(
        runner, {"action": "status", "request_id": 123}
    )
    assert rejected == []
    assert _receipts(runner) == []  # not a correlatable id: no receipt
    # and the input itself was still processed exactly like a no-id line
    assert (runner.run.root / "evidence" / "outer-input-receipts.jsonl").exists() is False


def test_runner_double_without_append_evidence_is_not_crashed():
    # A lightweight foreground double predating the S1 hook has no
    # _append_evidence: the admission path must still work, just receiptless.
    from types import SimpleNamespace

    double = SimpleNamespace()
    rejected: list = []
    output = _handle_foreground_message(
        double,
        json.dumps({"action": "bogus", "request_id": "req-double"}),
        lambda envelopes: None,
        lambda detail=None: rejected.append(detail or True),
    )
    assert output == []
    assert rejected == [True]


def test_end_to_end_digest_consistency_with_the_op_layer(cq_harness):
    runner = cq_harness
    run_id = runner.run.run_id
    fifo = OuterInputFifo(runner.run.root / "control" / "outer-input.fifo")
    fifo.open()
    try:
        submitted = host_ops.answer_question(
            run_id,
            channel="cq_interview",
            text="端到端\n一致性",
            request_id="req-e2e",
        )
        assert submitted["status"] == "submitted"
        fifo.read_ready()
        line = fifo.pop_line()
        assert line is not None
        # The exact FIFO line goes through the real Runner admission path.
        emitted: list = []
        _handle_foreground_message(
            runner, line, lambda envelopes: emitted.extend(envelopes), lambda: None
        )
        assert [item["type"] for item in emitted] == ["cq-interview-accepted"]
        (receipt,) = _receipts(runner)
        assert receipt["request_id"] == "req-e2e"
        assert receipt["outcome"] == "accepted"
        ledger = json.loads(
            (runner.run.root / "control" / "host-requests.jsonl").read_text("utf-8")
        )
        envelope = json.loads(line)
        envelope.pop("request_id")
        assert receipt["content_digest"] == ledger["content_digest"] == content_digest(envelope)
        result = host_ops.get_request_result(run_id, request_id="req-e2e")
        assert result["outcome"] == "accepted"
        assert result["content_digest"] == ledger["content_digest"]
        assert result["consumption_evidence"] == "evidence/cq-interview.jsonl"
    finally:
        fifo.close()


# --- R3.0-016 S2: the §3.4 request_id re-injection is limited to the checkpoint branch


class _CheckpointSpy:
    """Captures the envelope each dispatch stage actually received."""

    def __init__(self, runner) -> None:
        self.checkpoint_messages: list[dict] = []
        self.outer_messages: list[dict] = []
        original = runner.receive_outer

        def receive_outer(message):
            self.outer_messages.append(dict(message))
            return original(message)

        runner.receive_outer = receive_outer
        runner._handle_checkpoint_outer = self.checkpoint

    def checkpoint(self, message: dict) -> dict:
        """A stand-in ``_handle_checkpoint_outer`` that only records."""

        self.checkpoint_messages.append(dict(message))
        return {"type": "checkpoint-spy"}


def test_checkpoint_request_id_is_reinjected_after_the_digest(cq_harness):
    """S2-CKPT-002: one request_id, two faces, and one unchanged digest."""

    runner = cq_harness
    spy = _CheckpointSpy(runner)
    envelope = {
        "action": "checkpoint",
        "command": "save",
        "kind": "materialization_progress",
        "request_id": "req-ck-1",
    }
    output, emitted, rejected = _foreground(runner, envelope)
    assert rejected == []
    assert [item["type"] for item in output] == ["checkpoint-spy"]
    assert [item["type"] for item in emitted] == ["checkpoint-spy"]
    (seen,) = spy.checkpoint_messages
    # §3.4: the id is back on the envelope for the 015 manifest provenance.
    assert seen["request_id"] == "req-ck-1"
    assert seen["kind"] == "materialization_progress"

    # The receipt digest was taken BEFORE the re-injection, so both sides of
    # the FIFO compute it over the same envelope shape.
    (receipt,) = _receipts(runner)
    assert receipt["request_id"] == "req-ck-1"
    assert receipt["action"] == "checkpoint"
    assert receipt["outcome"] == "accepted"
    assert receipt["ack_type"] == "checkpoint-spy"
    without_id = {key: value for key, value in envelope.items() if key != "request_id"}
    assert receipt["content_digest"] == content_digest(without_id)

    # The op layer's submission of the same envelope reconciles with the receipt.
    fifo = OuterInputFifo(runner.run.root / "control" / "outer-input.fifo")
    fifo.open()
    try:
        submitted = host_ops.save_checkpoint(
            runner.run.run_id,
            kind="materialization_progress",
            request_id="req-ck-2",
            repository_root=REPO_ROOT,
        )
        assert submitted["status"] == "submitted"
        ledger = json.loads(
            (runner.run.root / "control" / "host-requests.jsonl").read_text("utf-8")
        )
        assert ledger["request_id"] == "req-ck-2"
        assert ledger["content_digest"] == content_digest(
            {"action": "checkpoint", "command": "save", "kind": "materialization_progress"}
        )
        fifo.read_ready()
        line = json.loads(fifo.pop_line())
        # The same single id travels on the wire: receipt, ledger and manifest.
        assert line["request_id"] == "req-ck-2"
        assert line["command"] == "save"
    finally:
        fifo.close()


def test_reinjection_never_touches_any_other_action(cq_harness):
    """S2-CKPT-002b: only ``action == "checkpoint"`` sees the key again."""

    runner = cq_harness
    spy = _CheckpointSpy(runner)
    output, _emitted, rejected = _foreground(
        runner, {"action": "status", "request_id": "req-status-1"}
    )
    assert rejected == []
    (seen,) = spy.outer_messages
    assert "request_id" not in seen  # byte-identical envelope, as in S1
    assert spy.checkpoint_messages == []
    (receipt,) = _receipts(runner)
    assert receipt["action"] == "status"
    assert receipt["outcome"] == "accepted"
    assert receipt["content_digest"] == content_digest({"action": "status"})

    # A checkpoint line without a request_id is unchanged too: nothing is
    # injected and no receipt exists for it.
    output, _emitted, rejected = _foreground(
        runner, {"action": "checkpoint", "command": "save", "kind": "cq_frozen"}
    )
    assert rejected == []
    assert [item["type"] for item in output] == ["checkpoint-spy"]
    assert "request_id" not in spy.checkpoint_messages[-1]
    assert len(_receipts(runner)) == 1  # still only the status receipt


def test_checkpoint_rejection_receipt_keeps_the_runner_code_and_digest(cq_harness):
    """A real Runner rejection: the original code passes through and the
    receipt digest matches the submission ledger for the same request_id."""

    runner = cq_harness
    fifo = OuterInputFifo(runner.run.root / "control" / "outer-input.fifo")
    fifo.open()
    try:
        submitted = host_ops.save_checkpoint(
            runner.run.run_id,
            kind="not-a-kind",
            request_id="req-ck-bad",
            repository_root=REPO_ROOT,
        )
        assert submitted["status"] == "submitted"
        fifo.read_ready()
        line = fifo.pop_line()
        assert line is not None
        output, _emitted, rejected = _foreground(runner, json.loads(line))
        assert output == []
        assert rejected and rejected[0]["code"] == "checkpoint_invalid_kind"
        (receipt,) = _receipts(runner)
        assert receipt["request_id"] == "req-ck-bad"
        assert receipt["outcome"] == "rejected"
        assert receipt["code"] == "checkpoint_invalid_kind"
        envelope = json.loads(line)
        envelope.pop("request_id")
        assert receipt["content_digest"] == content_digest(envelope)
        result = host_ops.get_request_result(
            runner.run.run_id, request_id="req-ck-bad", repository_root=REPO_ROOT
        )
        assert result["outcome"] == "rejected"
        assert result["code"] == "checkpoint_invalid_kind"
    finally:
        fifo.close()
