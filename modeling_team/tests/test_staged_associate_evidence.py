"""``protocol_staged_associate_evidence``: the staged evidence-repost projection.

The R3.0-008B staged channel originally projected exactly one platform write,
``submit_modeling_batch``.  A staged run's final retrieval gate is scored against
the lineage of materialized items, and the owner-authorized evidence that has to
back a structural triple can only be attached through
``associate_evidence_reference`` -- so without this second projection the gate
is constructively unsatisfiable for every run that materializes before the owner
answers (auth010 start4 item e80f85b1).  These tests lock the projection's
surface: the advertised operation set, the typed dispatch, the Runner gate, the
delivery contract, and the prompt/contract files the Protocol role reads.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from shutil import rmtree

import pytest

from modeling_team.acceptance import RunnerAcceptanceCarrier
from modeling_team.capability_mcp import (
    CAPABILITY_TOOL_SCHEMAS,
    PROTOCOL_OPERATIONS,
    ROLE_OPERATIONS,
    STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION,
    STAGED_PROTOCOL_OPERATION,
    STAGED_PROTOCOL_OPERATIONS,
    STAGED_PROTOCOL_RUN_OPERATIONS,
    STAGED_UNIFIED_PROTOCOL_OPERATIONS,
    UNIFIED_PROTOCOL_RUN_OPERATIONS,
    UNIFIED_PROTOCOL_OPERATIONS,
)
from modeling_team.contracts import repository_root
from modeling_team.runner import TeamRunner
from modeling_team.staged_decisions import (
    StagedBatchForwardError,
    StagedBatchForwardUnknown,
    StagedSubmissionRejection,
)
from modeling_team.tests.test_r30008b_runner_wiring import (
    MULTI_SLICE_SMOKE,
    PROFILE,
    _StagedRunner,
    _socket_request,
)

REPO_ROOT = repository_root()
INSTRUCTIONS = REPO_ROOT / "modeling_team" / "agent-packages" / "protocol" / "instructions.md"
CONTRACT_008B = REPO_ROOT / "modeling_team" / "references" / "r3-0-008b-staged-decisions-contract.json"
CONTRACT_009 = REPO_ROOT / "modeling_team" / "references" / "r3-0-009-unified-graph-contract.json"


def _association(**overrides) -> dict:
    """One owner-authorized evidence repost envelope, in the platform tool's shape."""

    payload = {
        "project_id": "project-1",
        "ontology_id": "ontology-1",
        "target_type": "modeling_item",
        "target_id": "item-e80f85b1",
        "evidence": [
            {
                "document_name": "owner-answer-2026-09-12.md",
                "excerpt": "customer is a class of party",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _argument_envelope(**overrides) -> dict:
    payload = {"protocol_id": "protocol", "association": _association()}
    payload.update(overrides)
    return payload


# --- the advertised surface -----------------------------------------------------


def test_staged_protocol_operation_set_pairs_submission_with_evidence_repost():
    # R4.0-012 removes source-tracing reposts from the active staged surface.
    assert STAGED_PROTOCOL_RUN_OPERATIONS == (
        STAGED_PROTOCOL_OPERATION,
    )
    assert STAGED_PROTOCOL_OPERATIONS == (*PROTOCOL_OPERATIONS, *STAGED_PROTOCOL_RUN_OPERATIONS)
    assert UNIFIED_PROTOCOL_RUN_OPERATIONS == (
        *STAGED_PROTOCOL_RUN_OPERATIONS,
        "protocol_execute_approved_plans",
        "protocol_inspect_associations",
        "protocol_check_plan_coverage",
    )
    assert UNIFIED_PROTOCOL_OPERATIONS == (*PROTOCOL_OPERATIONS, *UNIFIED_PROTOCOL_RUN_OPERATIONS)
    # The role registry is a validation superset, not an endpoint permission grant.
    assert ROLE_OPERATIONS["protocol"] == UNIFIED_PROTOCOL_OPERATIONS
    assert STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION not in UNIFIED_PROTOCOL_OPERATIONS
    assert STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION not in CAPABILITY_TOOL_SCHEMAS


def test_associate_evidence_schema_mirrors_the_platform_tool_arguments():
    """The retired evidence-repost operation has no active schema."""

    assert STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION not in CAPABILITY_TOOL_SCHEMAS


def test_capability_endpoint_declares_and_dispatches_the_evidence_operation(tmp_path):
    def submission_handler(args):
        return {"ok": True, "batch_id": "platform-batch-1"}

    carrier = RunnerAcceptanceCarrier(
        tmp_path / "carrier",
        task_id="staged-associate",
        acceptance_id="acceptance",
        staged_submission_handler=submission_handler,
        staged_protocol_capability=True,
    )
    endpoint = carrier.capability_endpoint("protocol")
    token = carrier.capability_token("protocol")
    assert endpoint.operations == STAGED_PROTOCOL_RUN_OPERATIONS

    listing = endpoint.handle(
        {"jsonrpc": "2.0", "id": "list", "token": token, "method": "tools/list"}
    )
    names = [tool["name"] for tool in listing["result"]["tools"]]
    assert names == list(STAGED_PROTOCOL_RUN_OPERATIONS)

    for operation in set(UNIFIED_PROTOCOL_RUN_OPERATIONS) - set(STAGED_PROTOCOL_RUN_OPERATIONS):
        denied = endpoint.handle({
            "jsonrpc": "2.0", "id": operation, "token": token, "method": "tools/call",
            "params": {"name": operation, "arguments": {"protocol_id": "protocol"}},
        })
        assert denied["error"]["code"] == -32001

    unified = RunnerAcceptanceCarrier(
        tmp_path / "unified", task_id="staged-unified", acceptance_id="acceptance",
        staged_submission_handler=submission_handler, staged_protocol_capability=True,
        staged_plan_handler=lambda args: {"status": "COMPLETE"},
    )
    unified_endpoint = unified.capability_endpoint("protocol")
    # R4.0-024: a staged unified surface also advertises the association catalog,
    # matching what the runtime advertises for the same run shape.
    assert unified_endpoint.operations == STAGED_UNIFIED_PROTOCOL_OPERATIONS
    unified_listing = unified_endpoint.handle({
        "jsonrpc": "2.0", "id": "list", "token": unified.capability_token("protocol"),
        "method": "tools/list",
    })
    assert [tool["name"] for tool in unified_listing["result"]["tools"]] == list(
        STAGED_UNIFIED_PROTOCOL_OPERATIONS
    )

    retired = endpoint.handle(
        {
            "jsonrpc": "2.0",
            "id": "call",
            "token": token,
            "method": "tools/call",
            "params": {"name": STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION, "arguments": _argument_envelope()},
        }
    )
    assert retired["error"]["code"] == -32001

    # A non-staged carrier advertises neither staged operation.
    plain = RunnerAcceptanceCarrier(
        tmp_path / "plain", task_id="staged-associate-plain", acceptance_id="acceptance"
    )
    assert STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION not in plain.capability_endpoint(
        "protocol"
    ).operations


# --- the Runner gate ------------------------------------------------------------


class _EvidenceForwarderRecorder:
    def __init__(self, result=None, exc: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.result = result if result is not None else {"items": [{"id": "a-1"}], "total": 1}
        self.exc = exc

    def __call__(self, association):
        self.calls.append(dict(association))
        if self.exc is not None:
            raise self.exc
        return self.result


def test_staged_associate_evidence_requires_staged_decisions(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        # A staged run that never bound the evidence forwarder stays fail-closed
        # with a typed reason instead of an opaque capability error.
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_associate_evidence(_argument_envelope())
        assert rejection.value.data["reason_code"] == "staged_evidence_forward_failed"
    finally:
        staged.cleanup()

    from modeling_team.tests.test_runner import CapturingAdapter

    delta = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]
    plain = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=CapturingAdapter(),
        ledger_root=tmp_path / "ledger",
        freeze_started_at=datetime.now(UTC).isoformat(),
    )
    run_id = f"r30008b-nostaged-evidence-{delta}"
    run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
    try:
        plain.prepare(
            run_id=run_id,
            profile_path=PROFILE,
            task_path=MULTI_SLICE_SMOKE,
            scope={"mode": "create"},
        )
        assert plain._staged_decisions is False
        with pytest.raises(StagedSubmissionRejection) as rejection:
            plain._handle_staged_associate_evidence(_argument_envelope())
        assert rejection.value.data["reason_code"] == "staged_gate_closed"
    finally:
        plain.cleanup()
        rmtree(run_root, ignore_errors=True)


def test_staged_associate_evidence_forwards_verbatim_after_materialization(tmp_path):
    forwarder = _EvidenceForwarderRecorder()
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        staged.runner.staged_evidence_forwarder = forwarder
        association = _association()
        result = staged.runner._handle_staged_associate_evidence(
            {"protocol_id": "protocol", "association": association}
        )
        assert result == {"items": [{"id": "a-1"}], "total": 1}

        # Verbatim envelope, protocol identity stripped: the Runner owns the
        # credential, so the role id is never part of the platform payload.
        assert forwarder.calls == [association]
        assert "protocol_id" not in forwarder.calls[0]

        # The evidence surface is not materialization: no intent, receipt or
        # unlock artifact is created or required, and the platform gate stays
        # exactly as prepare left it.
        assert not (staged.run_root / "staged-decisions" / "intents").exists()
        assert not (staged.run_root / "staged-decisions" / "receipts").exists()

        # The CQ freeze ordering binds materialization only: a selected CQ run
        # whose pool is still unfrozen can still repost evidence.
        staged.runner._competency_questions = True
        staged.runner._cq_freeze = None
        assert staged.runner._handle_staged_associate_evidence(
            _argument_envelope()
        ) == {"items": [{"id": "a-1"}], "total": 1}
        assert len(forwarder.calls) == 2
    finally:
        staged.cleanup()


def test_staged_associate_evidence_rejects_the_write_integrity_latch(tmp_path):
    forwarder = _EvidenceForwarderRecorder()
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        staged.runner.staged_evidence_forwarder = forwarder
        staged.runner._staged_gate_kill_switch("staged_unreconciled_batch", "fixture break")
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_associate_evidence(_argument_envelope())
        assert rejection.value.data["reason_code"] == "staged_gate_closed"
        assert "closed" in rejection.value.data["detail"]
        assert forwarder.calls == []
    finally:
        staged.cleanup()


@pytest.mark.parametrize(
    "association",
    [
        {"ontology_id": "ontology-1", "target_type": "modeling_item", "target_id": "item-1"},
        _association(project_id=""),
        _association(ontology_id="   "),
        _association(target_type=""),
        _association(target_id=""),
        _association(target_type="resource"),
        _association(evidence_reference_ids="not-a-list"),
        _association(evidence=[{"document_name": "d.md"}]),
        _association(evidence=[]),
        _association(evidence=None, evidence_reference_ids=[]),
    ],
)
def test_staged_associate_evidence_requires_a_legal_ontology_and_target(
    tmp_path, association
):
    """Only the declared shape reaches the host-side write forwarder."""

    forwarder = _EvidenceForwarderRecorder()
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        staged.runner.staged_evidence_forwarder = forwarder
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_associate_evidence(
                {"protocol_id": "protocol", "association": association}
            )
        assert rejection.value.data["reason_code"] == "staged_submit_schema_mismatch"
        assert forwarder.calls == []
    finally:
        staged.cleanup()


@pytest.mark.parametrize(
    ("exc", "reason_code"),
    [
        (StagedBatchForwardError("backend refused before any write"), "staged_evidence_forward_failed"),
        (StagedBatchForwardUnknown("no usable reply"), "staged_evidence_forward_unknown"),
        (RuntimeError("unexpected host failure"), "staged_evidence_forward_failed"),
    ],
)
def test_staged_associate_evidence_types_forwarder_failures(tmp_path, exc, reason_code):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        staged.runner.staged_evidence_forwarder = _EvidenceForwarderRecorder(exc=exc)
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_associate_evidence(_argument_envelope())
        assert rejection.value.data["reason_code"] == reason_code
        # An indeterminate association is retry-safe (the platform association
        # is idempotent by (target, reference)), so no kill switch is latched.
        assert staged.runner._staged_gate_killed is False
    finally:
        staged.cleanup()


def test_staged_associate_evidence_returns_the_forwarder_payload_shape(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        staged.runner.staged_evidence_forwarder = _EvidenceForwarderRecorder(
            result={"items": "not-a-mapping"}
        )
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_associate_evidence(_argument_envelope())
        assert rejection.value.data["reason_code"] == "staged_evidence_forward_failed"
    finally:
        staged.cleanup()


def test_staged_associate_evidence_travels_the_live_protocol_socket(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        forwarder = _EvidenceForwarderRecorder()
        staged.runner.staged_evidence_forwarder = forwarder
        endpoint = staged.runner.acceptance.capability_endpoint("protocol")
        endpoint.start()
        try:
            response = _socket_request(
                endpoint.socket_path,
                endpoint.token,
                "tools/call",
                name=STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION,
                arguments=_argument_envelope(),
            )
        finally:
            endpoint.stop()
        assert response["error"]["code"] == -32001
        assert forwarder.calls == []
    finally:
        staged.cleanup()


# --- the authority surface the Protocol role actually reads ---------------------


def test_protocol_instructions_declare_the_evidence_repost_contract():
    instructions = INSTRUCTIONS.read_text(encoding="utf-8")
    assert STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION not in instructions
    staged_section = instructions.split("## Staged modeling decisions (R3.0-008B)", 1)[1]
    assert "associate_evidence_reference" not in staged_section


def test_staged_contract_files_enumerate_both_staged_operations():
    contract = json.loads(CONTRACT_008B.read_text(encoding="utf-8"))
    assert contract["staged_submission_capability"]["operation"] == STAGED_PROTOCOL_OPERATION
    assert "staged_evidence_capability" not in contract

    unified = json.loads(CONTRACT_009.read_text(encoding="utf-8"))
    assert unified["submission_capability"]["operation"] == STAGED_PROTOCOL_OPERATION
    assert "evidence_capability" not in unified
