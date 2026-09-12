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
import inspect
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
    # The staged run's protocol surface is exactly these two operations, in this
    # order, and the role registry carries the same pair on top of the formal set.
    assert STAGED_PROTOCOL_RUN_OPERATIONS == (
        STAGED_PROTOCOL_OPERATION,
        STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION,
    )
    assert STAGED_PROTOCOL_OPERATIONS == (*PROTOCOL_OPERATIONS, *STAGED_PROTOCOL_RUN_OPERATIONS)
    assert ROLE_OPERATIONS["protocol"] == STAGED_PROTOCOL_OPERATIONS
    assert STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION in CAPABILITY_TOOL_SCHEMAS


def test_associate_evidence_schema_mirrors_the_platform_tool_arguments():
    """The advertised envelope is the platform tool's own parameter set."""

    from app.mcp.tools.evidence import register_evidence

    captured: dict[str, object] = {}

    class _RecorderServer:
        def tool(self):
            def decorator(function):
                captured[function.__name__] = function
                return function

            return decorator

    register_evidence(_RecorderServer())
    function = captured.get("associate_evidence_reference")
    assert function is not None, "the backend must register associate_evidence_reference"
    platform_params = set(inspect.signature(function).parameters) - {"actor"}

    schema = CAPABILITY_TOOL_SCHEMAS[STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION]
    assert set(schema["properties"]) == {"protocol_id", "association"}
    assert schema["required"] == ["protocol_id", "association"]
    association = schema["properties"]["association"]
    assert set(association["properties"]) == platform_params
    assert set(association["required"]) == {
        "project_id",
        "ontology_id",
        "target_type",
        "target_id",
    }
    assert association["additionalProperties"] is False

    # Every optional platform argument stays optional here.
    for key in platform_params - set(association["required"]):
        assert key not in schema["required"]


def test_capability_endpoint_declares_and_dispatches_the_evidence_operation(tmp_path):
    seen: list[dict] = []

    def submission_handler(args):
        return {"ok": True, "batch_id": "platform-batch-1"}

    def association_handler(args):
        seen.append(dict(args))
        if args["association"].get("target_id") == "rejected":
            raise StagedSubmissionRejection("staged_evidence_forward_failed", "fixture refusal")
        return {"items": [{"id": "association-1"}], "total": 1}

    carrier = RunnerAcceptanceCarrier(
        tmp_path / "carrier",
        task_id="staged-associate",
        acceptance_id="acceptance",
        staged_submission_handler=submission_handler,
        staged_association_handler=association_handler,
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

    def call(arguments):
        return endpoint.handle(
            {
                "jsonrpc": "2.0",
                "id": "call",
                "token": token,
                "method": "tools/call",
                "params": {"name": STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION, "arguments": arguments},
            }
        )

    ok = call(_argument_envelope())
    assert ok["result"]["structuredContent"]["ok"] is True
    assert ok["result"]["structuredContent"]["data"]["total"] == 1
    assert seen[0]["protocol_id"] == "protocol"

    typed = call(_argument_envelope(association=_association(target_id="rejected")))
    error = typed["result"]["structuredContent"]["error"]
    assert error["reason_code"] == "staged_evidence_forward_failed"

    # A foreign actor identity is the same opaque rejection as every other role.
    foreign = call(_argument_envelope(protocol_id="modeling"))
    assert foreign["error"]["code"] == -32001

    # The schema is enforced at the endpoint: an unknown association key, an
    # unknown envelope key and a missing envelope never reach the handler.
    for arguments in (
        _argument_envelope(association={**_association(), "actor": "forged"}),
        _argument_envelope(association="not-a-mapping"),
        {"protocol_id": "protocol"},
        _argument_envelope(unexpected="key"),
    ):
        rejected = call(arguments)
        assert rejected["error"]["code"] == -32001, arguments

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
        assert response["result"]["structuredContent"]["ok"] is True
        assert forwarder.calls == [_association()]
    finally:
        staged.cleanup()


# --- the authority surface the Protocol role actually reads ---------------------


def test_protocol_instructions_declare_the_evidence_repost_contract():
    instructions = INSTRUCTIONS.read_text(encoding="utf-8")
    assert STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION in instructions
    staged_section = instructions.split("## Staged modeling decisions (R3.0-008B)", 1)[1]
    # The whole staged section, sub-headings included: the evidence repost contract
    # lives in its own `###` block and must be read by the Protocol role as part of
    # the staged capability surface, not as a separate topic.
    evidence_section = staged_section.split("\n## ", 1)[0]
    assert "associate_evidence_reference" in evidence_section
    assert "modeling_item" in evidence_section
    # Only owner-authorized evidence may be reposted: the owner's own answer or
    # an approved business-package document, quoted verbatim, with the source
    # named; never self-authored evidence and never frozen CQ pool content.
    assert "owner" in evidence_section.lower()
    assert "document_name" in evidence_section
    assert "self-authored" in evidence_section or "自著" in evidence_section
    assert "frozen" in evidence_section


def test_staged_contract_files_enumerate_both_staged_operations():
    contract = json.loads(CONTRACT_008B.read_text(encoding="utf-8"))
    operations = [
        contract["staged_submission_capability"]["operation"],
        contract["staged_evidence_capability"]["operation"],
    ]
    assert operations == list(STAGED_PROTOCOL_RUN_OPERATIONS)
    assert (
        contract["staged_evidence_capability"]["platform_tool"]
        == "associate_evidence_reference"
    )
    assert contract["staged_evidence_capability"]["target_type"] == "modeling_item"
    for code in ("staged_evidence_forward_failed", "staged_evidence_forward_unknown"):
        assert code in contract["staged_evidence_capability"]["failure_reason_codes"]

    unified = json.loads(CONTRACT_009.read_text(encoding="utf-8"))
    assert unified["submission_capability"]["operation"] == STAGED_PROTOCOL_OPERATION
    # 009 extends 008B in place and shares the same role-private surface.
    assert unified["evidence_capability"]["operation"] == (
        STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION
    )
