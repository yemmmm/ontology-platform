"""Read-only reacceptance retains production and every previous attempt."""

import copy
import json
from pathlib import Path

import pytest

from modeling_team import __main__ as main_module, host_ops, host_ops_mcp
from modeling_team.competency_questions import CQContractError
from modeling_team.contracts import TeamConfigurationError
from modeling_team.outer_input import OuterInputFifo
from modeling_team.tests.test_host_ops_mcp import _Run
from modeling_team.tests.test_r3012_completion import (
    _CompletionRunner,
    _SettledTransport,
    _completion,
    _freeze,
    _handoff_message,
    _verdict_entry,
    _write_report,
)
from modeling_team.tests.test_r3012_handoff import _write_unknown_intent


@pytest.fixture
def scene(monkeypatch):
    harness = _CompletionRunner(cq_semantic=True)
    runner = harness.runner
    frozen = _freeze(runner)
    runner.transport = _SettledTransport(runner, "completed")
    monkeypatch.setattr(runner, "_cq_scope_binding", lambda: {
        "project_id": "project-fixture", "ontology_ids": ["ontology-fixture"]})
    first = runner.handle_cq_outer_input(_handoff_message(frozen))
    try:
        yield runner, frozen, first
    finally:
        harness.cleanup()


def retry_message(frozen, retry_of="attempt-0001"):
    return {**_handoff_message(frozen), "retry_of": retry_of}


def test_new_attempt_flows_through_cli_host_binding_and_completion(scene):
    runner, frozen, first = scene
    original_handoff = Path(first["model_handoff"]).read_bytes()
    original_report, digest = _write_report(runner, frozen)
    old_report_path = runner.run.root / first["report_directory"] / "batch-report.json"
    runner.handle_cq_outer_input(_completion(runner, frozen, report_digest=digest, cq_verdict="fail"))

    new = runner.handle_cq_outer_input(retry_message(frozen))
    assert new["acceptance_attempt_id"] == "attempt-0002"
    assert new["acceptance_phase"] == "acceptance_pending"
    assert "cq-acceptance-wait" in runner._cq_wait_windows.open_kinds()
    assert runner._cq_write_admission.phase == "read-only"
    assert Path(first["model_handoff"]).read_bytes() == original_handoff
    assert old_report_path.read_bytes() == original_report
    assert new["model_handoff"] != first["model_handoff"]
    handoff = json.loads(Path(new["model_handoff"]).read_text())
    assert handoff["retry_of"] == "attempt-0001"
    assert handoff["scope_binding"] == json.loads(original_handoff)["scope_binding"]

    binding = host_ops._cq_completion_binding(runner.run.root, None)
    assert binding["acceptance_attempt_id"] == "attempt-0002"
    pending, _ = host_ops._cq_pending(runner.run.root)
    closure = next(row for row in pending if row["type"] == "cq_acceptance_closure")
    assert closure["status"] == "acceptance_pending"
    assert closure["bindings"]["acceptance_attempt_id"] == "attempt-0002"

    contract = json.loads((runner.run.root / "acceptance-v3/run-contract.json").read_text())
    report_dir, _ = main_module._cq_consume_production_handoff(
        runner.run.root, handoff, contract=contract,
        batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"])
    assert report_dir == runner.run.root / new["report_directory"]
    public_dir, _ = main_module._cq_consume_production_handoff(
        runner.run.root, handoff, contract=contract,
        batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"],
        question_visibility="public")
    assert public_dir.name == "attempt-0002" and public_dir != report_dir
    forged = copy.deepcopy(handoff)
    forged["scope_binding"]["project_id"] = "wrong-project"
    with pytest.raises(TeamConfigurationError, match="does not match"):
        main_module._cq_consume_production_handoff(
            runner.run.root, forged, contract=contract,
            batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"])

    _report, digest = _write_report(runner, frozen, verdicts=[_verdict_entry()])
    completion = _completion(runner, frozen, report_digest=digest, cq_verdict="pass",
                             acceptance_attempt_id="attempt-0002")
    result = runner.handle_cq_outer_input(completion)
    assert result["cq_verdict"] == "pass"
    assert old_report_path.read_bytes() == original_report
    assert Path(first["model_handoff"]).read_bytes() == original_handoff
    with pytest.raises(CQContractError) as stale:
        runner.handle_cq_outer_input({**completion, "acceptance_attempt_id": "attempt-0001"})
    assert stale.value.data["reason_code"] == "cq_review_stale"


def test_repeated_retry_request_returns_the_same_new_attempt(scene):
    runner, frozen, _ = scene
    _write_report(runner, frozen)
    first_retry = runner.handle_cq_outer_input(retry_message(frozen))
    repeated = runner.handle_cq_outer_input(retry_message(frozen))
    ordinary_duplicate = runner.handle_cq_outer_input(_handoff_message(frozen))
    assert repeated["idempotent"] and ordinary_duplicate["idempotent"]
    for result in (repeated, ordinary_duplicate):
        assert result["acceptance_attempt_id"] == first_retry["acceptance_attempt_id"]
        assert result["model_handoff"] == first_retry["model_handoff"]


def test_retry_keeps_unfinished_attempt_and_stale_identity_recoverable(scene):
    runner, frozen, _ = scene
    with pytest.raises(CQContractError) as unfinished:
        runner.handle_cq_outer_input(retry_message(frozen))
    assert unfinished.value.data["reason_code"] == "cq_acceptance_report_mismatch"
    _write_report(runner, frozen)
    with pytest.raises(CQContractError) as stale:
        runner.handle_cq_outer_input(retry_message(frozen, "attempt-9999"))
    assert stale.value.data["reason_code"] == "cq_review_stale"
    assert runner._cq_acceptance_attempt["acceptance_attempt_id"] == "attempt-0001"


def test_retry_does_not_bypass_unknown_writes(scene):
    runner, frozen, _ = scene
    _write_report(runner, frozen)
    _write_unknown_intent(runner)
    with pytest.raises(CQContractError) as unsafe:
        runner.handle_cq_outer_input(retry_message(frozen))
    assert unsafe.value.data["reason_code"] == "cq_unknown_write_pending"
    assert runner._cq_acceptance_attempt["acceptance_attempt_id"] == "attempt-0001"


def test_host_mcp_forwards_explicit_retry_to_the_real_fifo():
    with _Run("cq-retry-wire") as run:
        fifo = OuterInputFifo(run.root / "control/outer-input.fifo")
        fifo.open()
        try:
            result = host_ops_mcp.tool_complete_cq_handoff(
                run.run_id, freeze_id="batch", freeze_digest="sha256:" + "a" * 64,
                retry_of="attempt-0001", request_id="retry-0002")
            assert result["ok"]
            fifo.read_ready()
            envelope = json.loads(fifo.pop_line())
            assert envelope["action"] == "cq_handoff_complete"
            assert envelope["retry_of"] == "attempt-0001"
            assert envelope["request_id"] == "retry-0002"
        finally:
            fifo.close()


def test_host_mcp_preserves_existing_positional_request_id():
    with _Run("cq-legacy-wire") as run:
        fifo = OuterInputFifo(run.root / "control/outer-input.fifo")
        fifo.open()
        try:
            result = host_ops_mcp.tool_complete_cq_handoff(
                run.run_id, "batch", "sha256:" + "a" * 64, None, "legacy-request")
            assert result["ok"]
            fifo.read_ready()
            envelope = json.loads(fifo.pop_line())
            assert envelope["request_id"] == "legacy-request"
            assert "retry_of" not in envelope
        finally:
            fifo.close()
