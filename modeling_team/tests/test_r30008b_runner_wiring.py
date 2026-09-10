"""R3.0-008B wiring tests: Runner staged gates, capability path, sandbox binds.

Covers test plan S3/S4/S8/S9/S10, B3-B10 (runner/runtime layers), F1/F2 and
R3. Every expected reason code here is written independently by the test
author; fixtures stay in the placeholder/example.test namespace.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace

import pytest

from modeling_team.acceptance import RunnerAcceptanceCarrier
from modeling_team.capability_mcp import (
    COMPETENCY_QUESTION_ROLE,
    STAGED_PROTOCOL_OPERATION,
)
from modeling_team.contracts import TeamConfigurationError, load_multi_slice_team_configuration, load_task
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.staged_decisions import (
    StagedBatchForwardError,
    StagedBatchForwardUnknown,
    StagedSubmissionRejection,
    build_submission_intent,
    mark_intent_status,
    staged_decision_artifact_paths,
    write_submission_intent,
)
from modeling_team.tests.test_r30002_runner_wiring import FIXTURES, _gate_state, _role_agent
from modeling_team.tests.test_r30008b_staged_decisions import (
    _approval_entry,
    _approvals,
    _checklist,
    _conclusions,
    _confirmed_entry,
    _conclusion_entry,
    _envelope,
    _enum_command,
    _materialize_unlock,
    _stage3_slot,
    _trace,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SOURCE = REPO_ROOT / "modeling_team" / "runner.py"
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml"
SMOKE_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-decisions-smoke.yaml"
REAL_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml"
MULTI_SLICE_SMOKE = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-002-multi-slice-smoke.yaml"

PROP = "https://example.test/prop/placeholder-status"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _staged_gate_feedback(adapter) -> list[dict]:
    notices = []
    for _agent_id, delivery in adapter.messages:
        if delivery.kind == "staged-decision-gate":
            notice = json.loads(delivery.text)
            assert notice["schema_version"] == "r3-0-008b-staged-gate-feedback/v1"
            notices.append(notice)
    return notices


def _staged_reasons(adapter) -> list[str]:
    return [notice["reason_code"] for notice in _staged_gate_feedback(adapter)]


def _topology_reasons(adapter) -> list[str]:
    reasons = []
    for _agent_id, delivery in adapter.messages:
        if delivery.kind == "multi-slice-topology-gate":
            reasons.append(json.loads(delivery.text)["reason_code"])
    return reasons


def _coordinator_id(runner: TeamRunner) -> str:
    return {
        agent.package.role: agent.agent_id
        for agent in runner.run.configuration.profile.agents
    }["coordinator"]


class _StagedRunner:
    """A prepared staged runner plus its capture adapter and run root."""

    def __init__(self, tmp_path, forwarder=None) -> None:
        from modeling_team.tests.test_runner import CapturingAdapter

        self.run_id = f"r30008b-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:10]}"
        self.run_root = REPO_ROOT / "workspaces" / "modeling-runs" / self.run_id
        self.adapter = CapturingAdapter()
        self.runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=self.adapter,
            ledger_root=tmp_path / "ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
            staged_batch_forwarder=forwarder,
        )

    def prepare(self) -> None:
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=SMOKE_TASK,
            scope={"mode": "create"},
        )

    def cleanup(self) -> None:
        self.runner.cleanup()
        if self.run_root.exists():
            rmtree(self.run_root)


def _stage3_valid(run_root: Path) -> None:
    paths = staged_decision_artifact_paths(run_root)
    _write_json(paths["stage3_slot"], _stage3_slot())
    _write_json(
        run_root / "stage3-neutral-graph" / "placeholder-candidate.json",
        {"candidate": "placeholder"},
    )
    _write_json(
        paths["approvals"],
        _approvals(
            [
                _approval_entry(
                    kind="stage3_slot",
                    target_id="placeholder-scenario",
                    confirmed_enum_value=None,
                )
            ]
        ),
    )


def _materialization_valid(run_root: Path) -> None:
    paths = staged_decision_artifact_paths(run_root)
    _write_json(paths["conclusions"], _conclusions([_confirmed_entry()]))
    _write_json(
        paths["conclusions_archive_dir"] / "ac-0001.r1.json",
        _conclusion_entry(status="analyzed", revision=1),
    )
    _write_json(paths["unlock"], _materialize_unlock())
    _write_json(
        paths["approvals"],
        _approvals(
            [
                _approval_entry(),
                _approval_entry(
                    kind="stage3_slot",
                    target_id="placeholder-scenario",
                    confirmed_enum_value=None,
                ),
            ]
        ),
    )


def _open_platform_gate(staged: _StagedRunner) -> None:
    _stage3_valid(staged.run_root)
    assert staged.runner._check_staged_decision_gates() is True
    _write_json(
        staged.run_root / "scenario-map" / "topology-decision.json",
        FIXTURES["topology_decision"]["multi_ontology_plan_valid"],
    )
    _write_json(
        staged.run_root / "scenario-map" / "scenario-map.json",
        FIXTURES["scenario_map"]["valid"],
    )
    staged.runner._check_multi_slice_topology_gate()
    assert _gate_state(staged.run_root)["state"] == "open"


def _capability_args() -> dict:
    command = _enum_command()
    # No L3 node in this minimal submission: drop the semantic_value link.
    del command["payload"]["semantic_value"]
    return {
        "protocol_id": "protocol",
        "batch": _envelope([command]),
        "value_traces": [_trace()],
        "l3_nodes": [],
    }


class _ForwarderRecorder:
    def __init__(self, result=None, exc: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.result = result or {"batch_id": "platform-batch-1"}
        self.exc = exc
        self.intents_dir: Path | None = None

    def __call__(self, batch):
        intents_at_call: list[str] = []
        if self.intents_dir is not None and self.intents_dir.exists():
            intents_at_call = sorted(path.name for path in self.intents_dir.iterdir())
        self.calls.append({"batch": dict(batch), "intents_at_call": intents_at_call})
        if self.exc is not None:
            raise self.exc
        return self.result


# --- S3: stage 3 slot is a prerequisite of the topology gate -------------------


def test_s3_invalid_slot_skips_topology_check_without_latch_or_close(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        assert staged.runner._staged_decisions is True
        assert _gate_state(staged.run_root)["reason_code"] == "topology_missing_artifact"

        # No slot: the staged check intervenes, the topology check does NOT run.
        assert staged.runner._check_staged_decision_gates() is False
        assert staged.runner._multi_slice_gate_opened is False
        assert _gate_state(staged.run_root) == {
            "schema_version": "r2-3-005-candidate-platform-gate/v1",
            "state": "closed",
            "reason_code": "topology_missing_artifact",
        }
        assert _topology_reasons(staged.adapter) == []
        assert _staged_reasons(staged.adapter) == ["stage3_missing_artifact"]

        # Feedback is deduplicated across cycles.
        assert staged.runner._check_staged_decision_gates() is False
        assert _staged_reasons(staged.adapter) == ["stage3_missing_artifact"]

        # A structurally invalid slot also intervenes (typed repair code).
        _write_json(
            staged_decision_artifact_paths(staged.run_root)["stage3_slot"],
            _stage3_slot(deferred_contract="R9.9.9"),
        )
        assert staged.runner._check_staged_decision_gates() is False
        assert "stage3_schema_mismatch" in _staged_reasons(staged.adapter)
        assert staged.runner._staged_gate_killed is False

        # Once the slot is valid, the topology check runs and opens the gate.
        _stage3_valid(staged.run_root)
        assert staged.runner._check_staged_decision_gates() is True
        _write_json(
            staged.run_root / "scenario-map" / "topology-decision.json",
            FIXTURES["topology_decision"]["multi_ontology_plan_valid"],
        )
        _write_json(
            staged.run_root / "scenario-map" / "scenario-map.json",
            FIXTURES["scenario_map"]["valid"],
        )
        staged.runner._check_multi_slice_topology_gate()
        assert _gate_state(staged.run_root)["state"] == "open"
        assert staged.runner._multi_slice_gate_opened is True
    finally:
        staged.cleanup()


def test_s3_prepare_registers_staged_directories_only(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        for directory in staged_decision_directories_list(staged.run_root):
            assert directory.is_dir()
        # No staged artifact is ever pre-created: an absent file IS the gate.
        paths = staged_decision_artifact_paths(staged.run_root)
        for key in ("conclusions", "unlock", "approvals", "ledger", "checklist", "stage3_slot"):
            assert not paths[key].exists()
    finally:
        staged.cleanup()


def staged_decision_directories_list(run_root: Path) -> list[Path]:
    from modeling_team.staged_decisions import staged_decision_directories

    return staged_decision_directories(run_root)


def test_f1_non_staged_run_keeps_staged_checks_inert(tmp_path):
    from modeling_team.tests.test_runner import CapturingAdapter

    run_id = f"r30008b-conservation-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]}"
    run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
    adapter = CapturingAdapter()
    runner = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=adapter,
        ledger_root=tmp_path / "ledger",
        freeze_started_at=datetime.now(UTC).isoformat(),
    )
    try:
        runner.prepare(
            run_id=run_id,
            profile_path=REPO_ROOT / "modeling_team" / "profiles" / "base-three-agent.yaml",
            task_path=REPO_ROOT / "modeling_team" / "tasks" / "new-scope-business-slice.yaml",
            scope={"mode": "create"},
        )
        assert runner._staged_decisions is False
        assert runner._check_staged_decision_gates() is True
        assert adapter.messages == []
        with pytest.raises(StagedSubmissionRejection) as rejection:
            runner._handle_staged_submit_modeling_batch(_capability_args())
        assert rejection.value.data["reason_code"] == "staged_gate_closed"
    finally:
        runner.cleanup()
        if run_root.exists():
            rmtree(run_root)


# --- S4: capability happy path with durable intent-before-forward ordering ------


def test_s4_capability_pass_path_intent_first_receipt_backfilled(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _StagedRunner(tmp_path, forwarder=forwarder)
    forwarder.intents_dir = staged_decision_artifact_paths(staged.run_root)["intents_dir"]
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)
        result = staged.runner._handle_staged_submit_modeling_batch(_capability_args())
        assert result["ok"] is True
        assert result["batch_id"] == "platform-batch-1"
        assert result["intent_ordinal"] == 1
        assert result["receipt_ordinal"] == 1
        assert result["response_digest"].startswith("sha256:")

        # The forwarder saw exactly the verbatim batch envelope.
        assert len(forwarder.calls) == 1
        forwarded = forwarder.calls[0]["batch"]
        assert set(forwarded) == {
            "session_id",
            "client_batch_id",
            "ontology_id",
            "idempotency_key",
            "expected_workspace_version",
            "items",
            "mode",
            "lease_token",
        }
        assert "value_traces" not in forwarded
        assert "l3_nodes" not in forwarded

        # The durable intent existed BEFORE the host-side forward ran.
        assert forwarder.calls[0]["intents_at_call"] == ["intent-1.json"]

        intents_dir = staged_decision_artifact_paths(staged.run_root)["intents_dir"]
        receipts_dir = staged_decision_artifact_paths(staged.run_root)["receipts_dir"]
        intent = json.loads((intents_dir / "intent-1.json").read_text(encoding="utf-8"))
        assert intent["status"] == "receipted"
        assert intent["idempotency_key"] == "placeholder-key-1"
        receipt = json.loads((receipts_dir / "receipt-1.json").read_text(encoding="utf-8"))
        assert receipt["batch_id"] == "platform-batch-1"
        assert receipt["submitted_via"] == "protocol_staged_submit_modeling_batch"
        assert receipt["commands"] == intent["commands"]
        # The Runner stamped the additive enum_target on the receipted trace.
        assert receipt["value_traces"][0]["enum_target"] == "placeholder-enum-1"
    finally:
        staged.cleanup()


def test_s4_capability_endpoint_routes_typed_structured_results(tmp_path):
    def handler(args):
        if args.get("protocol_id") != "protocol":
            raise StagedSubmissionRejection("staged_gate_closed", "wrong actor")
        if "items" not in args.get("batch", {}):
            raise StagedSubmissionRejection("staged_submit_schema_mismatch", "items missing")
        return {"ok": True, "batch_id": "platform-batch-1"}

    carrier = RunnerAcceptanceCarrier(
        tmp_path / "carrier",
        task_id="r30008b-carrier",
        acceptance_id="acceptance",
        staged_submission_handler=handler,
        staged_protocol_capability=True,
    )
    endpoint = carrier.capability_endpoint("protocol")
    token = carrier.capability_token("protocol")

    def request(arguments):
        return endpoint.handle(
            {
                "jsonrpc": "2.0",
                "id": "s4",
                "token": token,
                "method": "tools/call",
                "params": {
                    "name": "protocol_staged_submit_modeling_batch",
                    "arguments": arguments,
                },
            }
        )

    ok_response = request(
        {
            "protocol_id": "protocol",
            "batch": _envelope([{"command_kind": "create_entity", "payload": {"entity_id": "e"}}]),
            "value_traces": [],
            "l3_nodes": [],
        }
    )
    assert ok_response["result"]["structuredContent"]["ok"] is True
    typed = request(
        {
            "protocol_id": "protocol",
            "batch": {"session_id": "placeholder-session"},
            "value_traces": [],
            "l3_nodes": [],
        }
    )
    error = typed["result"]["structuredContent"]["error"]
    assert error["reason_code"] == "staged_submit_schema_mismatch"
    opaque = request(
        {
            "protocol_id": "modeling",
            "batch": _envelope([{"command_kind": "create_entity", "payload": {"entity_id": "e"}}]),
            "value_traces": [],
            "l3_nodes": [],
        }
    )
    assert opaque["error"]["code"] == -32001

    listing = endpoint.handle(
        {"jsonrpc": "2.0", "id": "s4", "token": token, "method": "tools/list"}
    )
    names = [tool["name"] for tool in listing["result"]["tools"]]
    assert "protocol_staged_submit_modeling_batch" in names

    plain = RunnerAcceptanceCarrier(
        tmp_path / "plain-carrier",
        task_id="r30008b-plain",
        acceptance_id="acceptance",
    )
    assert "protocol_staged_submit_modeling_batch" not in plain.capability_endpoint("protocol").operations


# --- S8: skip unlock rejects enum commands, forwards non-enum payloads ----------


def test_s8_skip_unlock_rejects_enum_but_forwards_non_enum(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _StagedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        paths = staged_decision_artifact_paths(staged.run_root)
        _write_json(paths["conclusions"], _conclusions([_conclusion_entry()]))
        skip = _materialize_unlock()
        skip["mode"] = "skip"
        skip["confirmed_codes"] = None
        skip["mapping_sources"] = None
        skip["skip_reason"] = "no_schema_no_interface"
        _write_json(paths["unlock"], skip)

        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_capability_args())
        assert rejection.value.data["reason_code"] == "staged_value_materialization_locked"
        assert not (paths["intents_dir"] / "intent-1.json").exists()
        assert forwarder.calls == []

        args = _capability_args()
        args["batch"] = _envelope(
            [{"command_kind": "create_entity", "payload": {"entity_id": "placeholder-entity"}}]
        )
        result = staged.runner._handle_staged_submit_modeling_batch(args)
        assert result["ok"] is True
        assert len(forwarder.calls) == 1
    finally:
        staged.cleanup()


# --- B3/B4/B5: typed rejections and the kill-switch -----------------------------


def test_b3_closed_gate_rejects_submission_without_side_effects(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _StagedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        paths = staged_decision_artifact_paths(staged.run_root)
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_capability_args())
        assert rejection.value.data["reason_code"] == "staged_gate_closed"
        assert not paths["intents_dir"].exists() or not any(paths["intents_dir"].iterdir())
        assert forwarder.calls == []
    finally:
        staged.cleanup()


def test_b4_unconfirmed_conclusion_is_a_typed_rejection(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _StagedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        paths = staged_decision_artifact_paths(staged.run_root)
        # The unlock legitimately confirms ac-0001, but the traced conclusion
        # ac-0002 is still analyzed: the capability rejects it typed.
        _write_json(
            paths["conclusions"], _conclusions([_confirmed_entry(), _conclusion_entry(conclusion_id="ac-0002")])
        )
        _write_json(
            paths["conclusions_archive_dir"] / "ac-0001.r1.json",
            _conclusion_entry(status="analyzed", revision=1),
        )
        _write_json(paths["unlock"], _materialize_unlock())
        args = _capability_args()
        args["value_traces"] = [
            {**_trace(), "conclusion_id": "ac-0002"}
        ]
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(args)
        assert rejection.value.data["reason_code"] == "staged_conclusion_not_confirmed"
        assert forwarder.calls == []
    finally:
        staged.cleanup()


def test_b5_corrupt_receipt_triggers_kill_switch(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _StagedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        paths = staged_decision_artifact_paths(staged.run_root)
        (paths["receipts_dir"] / "receipt-1.json").write_text(
            "{broken json", encoding="utf-8"
        )
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_capability_args())
        assert rejection.value.data["reason_code"] == "staged_unreconciled_batch"
        assert staged.runner._staged_gate_killed is True
        assert _gate_state(staged.run_root)["reason_code"] == "staged_unreconciled_batch"
        assert forwarder.calls == []
    finally:
        staged.cleanup()


def test_d2_corrupt_intent_json_converges_to_typed_kill_switch_not_crash(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _StagedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        paths = staged_decision_artifact_paths(staged.run_root)
        (paths["intents_dir"] / "intent-1.json").write_text(
            "{broken json", encoding="utf-8"
        )
        # The monitor tick must not raise through the foreground loop: the
        # corrupt write-integrity artifact converges to the typed kill-switch.
        assert staged.runner._check_staged_decision_gates() is False
        assert staged.runner._staged_gate_killed is True
        assert _gate_state(staged.run_root)["reason_code"] == "staged_unreconciled_batch"
        assert "staged_unreconciled_batch" in _staged_reasons(staged.adapter)
        # The latch keeps intervening on later ticks without re-raising.
        assert staged.runner._check_staged_decision_gates() is False
        assert forwarder.calls == []
    finally:
        staged.cleanup()


# --- B6: forward failures, adjudication gating, and the pending-unknown lock ----


def test_b6_definite_forward_failure_keeps_intent_submitted(tmp_path):
    failing = _ForwarderRecorder(exc=StagedBatchForwardError("backend rejected"))
    staged = _StagedRunner(tmp_path, forwarder=failing)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_capability_args())
        assert rejection.value.data["reason_code"] == "staged_batch_forward_failed"
        intents_dir = staged_decision_artifact_paths(staged.run_root)["intents_dir"]
        intent = json.loads((intents_dir / "intent-1.json").read_text(encoding="utf-8"))
        assert intent["status"] == "submitted"
        assert staged.runner._staged_gate_killed is False
        assert staged.runner._staged_gate_killed is False

        # A later retry with a healthy forwarder reuses the same ordinal.
        staged.runner.staged_batch_forwarder = _ForwarderRecorder()
        result = staged.runner._handle_staged_submit_modeling_batch(_capability_args())
        assert result["intent_ordinal"] == 1
        assert result["receipt_ordinal"] == 1
    finally:
        staged.cleanup()


def test_b6_unknown_forward_result_latches_kill_switch(tmp_path):
    forwarder = _ForwarderRecorder(exc=StagedBatchForwardUnknown("timeout"))
    staged = _StagedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_capability_args())
        assert rejection.value.data["reason_code"] == "staged_batch_forward_unknown"
        intents_dir = staged_decision_artifact_paths(staged.run_root)["intents_dir"]
        intent = json.loads((intents_dir / "intent-1.json").read_text(encoding="utf-8"))
        assert intent["status"] == "unknown"
        assert staged.runner._staged_gate_killed is True
        assert _gate_state(staged.run_root)["reason_code"] == "staged_unreconciled_batch"
        assert "staged_unreconciled_batch" in _staged_reasons(staged.adapter)
    finally:
        staged.cleanup()


def test_b6_pending_unknown_intent_rejects_new_submissions_and_fires_monitor(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _StagedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)
        intent = mark_intent_status(
            build_submission_intent(
                1,
                idempotency_key="placeholder-key-earlier",
                client_batch_id="placeholder-batch-earlier",
                session_id="placeholder-session",
                mode="apply_atomic",
                commands=[],
                value_traces=[],
                l3_nodes=[],
            ),
            "unknown",
        )
        write_submission_intent(staged.run_root, intent)

        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_capability_args())
        assert rejection.value.data["reason_code"] == "staged_unreconciled_batch"

        # The monitor tick fires the kill-switch on the suspended intent.
        assert staged.runner._check_staged_decision_gates() is False
        assert staged.runner._staged_gate_killed is True
        assert forwarder.calls == []
    finally:
        staged.cleanup()


def test_b9_missing_forwarder_fails_closed(tmp_path):
    staged = _StagedRunner(tmp_path, forwarder=None)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)
        staged.runner.staged_batch_forwarder = None
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_capability_args())
        assert rejection.value.data["reason_code"] == "staged_batch_forward_failed"
        intents_dir = staged_decision_artifact_paths(staged.run_root)["intents_dir"]
        assert (intents_dir / "intent-1.json").exists()
    finally:
        staged.cleanup()


# --- S10: joint acceptance checklist terminal gate ------------------------------


def test_s10_terminal_gate_blocks_completed_until_checklist_valid(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        coordinator = _coordinator_id(staged.runner)
        assert staged.runner._terminal_report_guard(coordinator, status="completed") is True
        assert "acceptance_checklist_missing" in _staged_reasons(staged.adapter)
        # Deduplicated feedback.
        staged.runner._terminal_report_guard(coordinator, status="completed")
        assert _staged_reasons(staged.adapter).count("acceptance_checklist_missing") == 1
        # A blocked report always passes (T0 exit).
        assert staged.runner._terminal_report_guard(coordinator, status="blocked") is False

        _write_json(staged_decision_artifact_paths(staged.run_root)["checklist"], _checklist())
        assert staged.runner._terminal_report_guard(coordinator, status="completed") is False

        broken = _checklist()
        broken["items"] = broken["items"][:-1]
        _write_json(staged_decision_artifact_paths(staged.run_root)["checklist"], broken)
        assert staged.runner._terminal_report_guard(coordinator, status="completed") is True
        assert "acceptance_checklist_schema_mismatch" in _staged_reasons(staged.adapter)
    finally:
        staged.cleanup()


# --- S9: sandbox binds and sandbox elevation ------------------------------------


def _staged_run_root(base: Path) -> Path:
    from modeling_team.staged_decisions import staged_decision_directories

    for directory in staged_decision_directories(base):
        directory.mkdir(parents=True, exist_ok=True)
    return base


OWNED = {
    "modeling": (
        "value-semantics/conclusions",
        "value-semantics/conclusions-archive",
        "stage3-neutral-graph",
    ),
    "coordinator": (
        "value-semantics/unlock",
        "value-semantics/approvals",
        "joint-acceptance",
    ),
    "protocol": ("value-semantics/ledger",),
}


def test_s9_staged_binds_follow_the_ownership_table(tmp_path):
    base = _staged_run_root(tmp_path / "run")
    (base / "scenario-map").mkdir(exist_ok=True)
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    adapter._run_root = base
    adapter._staged_decisions_enabled = True
    # Staged tasks always ride on the multi-slice workflow, so the Coordinator
    # keeps its R3.0-006 scenario-map elevation.
    adapter._multi_slice_scenario_map_enabled = True
    try:
        for role, owned in OWNED.items():
            agent = _role_agent(base, role)
            command = adapter.namespace_command(agent)
            mounts = [
                command[index : index + 3] for index in range(len(command) - 2)
            ]
            assert ["--ro-bind", str(base / "value-semantics"), "/agent/work/value-semantics"] in mounts
            for relative in owned:
                assert [
                    "--bind",
                    str(base / relative),
                    f"/agent/work/{relative}",
                ] in mounts
            for other_role, other_owned in OWNED.items():
                if other_role == role:
                    continue
                for relative in other_owned:
                    assert f"/agent/work/{relative}" not in command
            # Runner-host-owned directories are never sandbox-bound.
            assert "/agent/work/value-semantics/submission-receipts" not in command
            assert "/agent/work/value-semantics/submission-intents" not in command
            assert adapter._thread_sandbox(agent) == "workspace-write"
    finally:
        adapter.stop()


def test_s9_non_staged_binds_and_sandbox_are_byte_identical(tmp_path):
    base = _staged_run_root(tmp_path / "run")
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    adapter._run_root = base
    adapter._staged_decisions_enabled = False
    try:
        for role in ("modeling", "protocol"):
            agent = _role_agent(base, role)
            assert adapter._staged_decision_binds(agent) == []
            command = adapter.namespace_command(agent)
            assert "/agent/work/value-semantics" not in command
            assert adapter._thread_sandbox(agent) == agent.package.runtime["codex"]["sandbox"]
    finally:
        adapter.stop()


def test_s9_staged_binds_fail_closed_when_directory_missing(tmp_path):
    base = _staged_run_root(tmp_path / "run")
    rmtree(base / "joint-acceptance")
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    adapter._run_root = base
    adapter._staged_decisions_enabled = True
    try:
        with pytest.raises(Exception, match="staged writable directory was not prepared"):
            adapter.namespace_command(_role_agent(base, "coordinator"))
    finally:
        adapter.stop()


def test_s9_staged_protocol_gets_capability_socket_and_advertisement(tmp_path):
    base = _staged_run_root(tmp_path / "run")
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    adapter._run_root = base
    adapter._staged_decisions_enabled = True
    staged_run = SimpleNamespace(
        root=base,
        run_id="r30008b-socket",
        configuration=SimpleNamespace(
            profile=SimpleNamespace(profile_id="r3-0-002-modeling-team"),
            task=SimpleNamespace(
                schema_version=2,
                task_id="r3-0-008b-staged-decisions-smoke",
                parameters={"multi_slice_workflow": True, "staged_modeling_decisions": True},
            ),
        ),
    )
    adapter._active_run = staged_run
    socket = base / "capabilities" / "protocol.sock"
    socket.parent.mkdir(parents=True, exist_ok=True)
    adapter._acceptance = SimpleNamespace(capability_socket_path=lambda role: socket)
    try:
        assert adapter._role_capability_operations("protocol") == (
            "protocol_staged_submit_modeling_batch",
        )
        command = adapter.namespace_command(_role_agent(base, "protocol"))
        assert [
            "--bind",
            str(socket),
            "/agent/home/runner-capability.sock",
        ] in [command[index : index + 3] for index in range(len(command) - 2)]
    finally:
        adapter.stop()


def test_f1_non_staged_capability_assembly_and_manifest_exclude_staged_operation(
    monkeypatch, tmp_path
):
    base = tmp_path / "ordinary"
    base.mkdir()
    (base / "sources" / "protocol").mkdir(parents=True)
    ordinary_run = SimpleNamespace(
        root=base,
        run_id="r30008b-ordinary",
        protocol_key="platform-key",
        configuration=SimpleNamespace(
            profile=SimpleNamespace(profile_id="base-three-agent"),
            task=SimpleNamespace(schema_version=2, task_id="ordinary-v2", parameters={}),
        ),
    )
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: _host_auth(base))
    try:
        agent = _role_agent(base, "protocol")
        adapter._write_config(ordinary_run, agent)
        manifest = json.loads(
            (agent.home / "runner-capabilities.json").read_text(encoding="utf-8")
        )
        assert "protocol_staged_submit_modeling_batch" not in manifest["capabilities"]

        staged_run = SimpleNamespace(
            root=base,
            run_id="r30008b-staged-manifest",
            protocol_key="platform-key",
            configuration=SimpleNamespace(
                profile=SimpleNamespace(profile_id="r3-0-002-modeling-team"),
                task=SimpleNamespace(
                    schema_version=2,
                    task_id="r3-0-008b-staged-decisions-smoke",
                    parameters={"multi_slice_workflow": True, "staged_modeling_decisions": True},
                ),
            ),
        )
        token_path = base / "protocol.token"
        token_path.write_text("placeholder-token", encoding="utf-8")
        adapter._acceptance = SimpleNamespace(capability_token_path=lambda role: token_path)
        (base / "sources" / "protocol2").mkdir(parents=True, exist_ok=True)
        staged_agent = _named_protocol_agent(base, "protocol2")
        adapter._write_config(staged_run, staged_agent)
        staged_manifest = json.loads(
            (staged_agent.home / "runner-capabilities.json").read_text(encoding="utf-8")
        )
        assert staged_manifest["capabilities"] == ["protocol_staged_submit_modeling_batch"]
        config = (staged_agent.home / "config.toml").read_text(encoding="utf-8")
        assert "runner_capability" in config
    finally:
        adapter.stop()


def _host_auth(base: Path) -> Path:
    host_auth = base / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    host_auth.chmod(0o600)
    return host_auth


def _named_protocol_agent(base: Path, name: str):
    from modeling_team.runtimes.codex import _Agent

    home, work, skills = (base / f"{name}-home", base / f"{name}-work", base / f"{name}-skills")
    for path in (home, work, skills):
        path.mkdir(parents=True, mode=0o700)
    package = SimpleNamespace(
        role="protocol",
        package_id="protocol",
        runtime={"codex": {"sandbox": "workspace-write"}},
    )
    return _Agent(
        name,
        package,
        home,
        work,
        skills,
        platform_tools=frozenset({"check_platform_health"}),
        schema_version=2,
    )


# --- B10 / F1 / F2 / R3: configuration contract and task audit ------------------


def test_b10_staged_parameter_requires_multi_slice(tmp_path):
    modified = SMOKE_TASK.read_text(encoding="utf-8").replace(
        "  multi_slice_workflow: true\n", ""
    )
    task_file = tmp_path / "staged-without-multi-slice.yaml"
    task_file.write_text(modified, encoding="utf-8")
    with pytest.raises(TeamConfigurationError, match="staged_modeling_decisions requires"):
        load_task(task_file, root=REPO_ROOT, allowed_roles={"coordinator", "modeling", "protocol"})


def test_f1_multi_slice_smoke_task_still_loads():
    configuration = load_multi_slice_team_configuration(PROFILE, MULTI_SLICE_SMOKE)
    assert configuration.task.parameters == {"multi_slice_workflow": True}


def test_f1_drain_hook_keeps_single_topology_gate_call():
    source = RUNNER_SOURCE.read_text(encoding="utf-8")
    assert source.count("self._check_multi_slice_topology_gate()") == 1
    assert "if self._check_staged_decision_gates():" in source


def test_f2_real_task_omits_direct_submit_and_declares_both_parameters():
    import yaml

    task = yaml.safe_load(REAL_TASK.read_text(encoding="utf-8"))
    assert task["parameters"] == {
        "multi_slice_workflow": True,
        "staged_modeling_decisions": True,
        "competency_question_acceptance": True,
    }
    tools = task["protocol_tools"]
    assert "submit_modeling_batch" not in tools
    assert "list_session_modeling_batches" in tools
    assert "create_build_session" in tools
    source_paths = [entry["path"] for entry in task["role_sources"]]
    assert "modeling_team/references/r3-0-008b-staged-decisions-contract.json" in source_paths


def test_r3_real_task_carries_the_double_start_gate_header():
    text = REAL_TASK.read_text(encoding="utf-8")
    header = text.split("schema_version:", 1)[0]
    assert "GATE (double)" in header
    assert "R3.0-009" in header
    assert "user-authorized" in header
    assert "Segment 1 delivery must" in header


# --- R3.0-008B endpoint liveness: the staged protocol capability is real --------
#
# A staged run is non-formal, so the formal branch that starts every private
# endpoint never ran: the protocol role declared its staged submission
# capability in the private config while no socket existed, and the runtime's
# exact-equality MCP surface check then had nothing to talk to.  These tests
# exercise the real ``RunnerCapabilityEndpoint`` over a real AF_UNIX socket at
# the exact roster-start boundary, not a mocked call name.

CQ_PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-011-competency-question.yaml"
CQ_STAGED_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml"


def _socket_request(socket_path: Path, token: str, method: str, **params) -> dict:
    """Send one JSON-RPC request to a live Runner capability socket."""

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(str(socket_path))
        client.sendall(
            (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "token": token,
                        "method": method,
                        "params": params,
                    }
                )
                + "\n"
            ).encode("utf-8")
        )
        line = client.makefile("r", encoding="utf-8").readline(1_048_577)
    assert line
    return json.loads(line)


def _socket_tools(socket_path: Path, token: str) -> list[str]:
    response = _socket_request(socket_path, token, "tools/list")
    return [tool["name"] for tool in response["result"]["tools"]]


class _RosterSocketProbe:
    """Observe the private capability sockets at the roster-start boundary.

    From inside ``start_roster`` the probe records, per role, whether the
    socket path is a real Unix socket and which tools it really serves -- i.e.
    before any roster process exists.  The Runner is attached afterwards so the
    adapter is a working adapter from construction.
    """

    def __init__(self) -> None:
        from modeling_team.tests.test_runner import CapturingAdapter

        self.runner: TeamRunner | None = None
        self.observations: list[dict[str, dict]] = []
        outer = self

        class _Adapter(CapturingAdapter):
            def start_roster(self, run, agents):
                assert outer.runner is not None
                carrier = outer.runner.acceptance
                observed: dict[str, dict] = {}
                for role in (
                    "protocol",
                    COMPETENCY_QUESTION_ROLE,
                    "coordinator",
                    "acceptance",
                ):
                    path = carrier.capability_socket_path(role)
                    live = path.exists()
                    observed[role] = {
                        "is_socket": bool(
                            live and stat.S_ISSOCK(os.lstat(path).st_mode)
                        ),
                        "tools": (
                            _socket_tools(path, carrier.capability_token(role))
                            if live
                            else []
                        ),
                    }
                outer.observations.append(observed)
                return super().start_roster(run, agents)

        self.adapter = _Adapter()

    def attach(self, runner: TeamRunner) -> None:
        self.runner = runner
        runner.adapter = self.adapter


def test_staged_protocol_capability_socket_is_live_before_roster_start(tmp_path):
    probe = _RosterSocketProbe()
    runner = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=probe.adapter,
        ledger_root=tmp_path / "ledger",
        freeze_started_at=datetime.now(UTC).isoformat(),
        staged_batch_forwarder=_ForwarderRecorder(),
    )
    probe.attach(runner)
    run_id = f"r30008b-endpoint-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]}"
    run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
    try:
        runner.prepare(
            run_id=run_id,
            profile_path=CQ_PROFILE,
            task_path=CQ_STAGED_TASK,
            scope={"mode": "create"},
        )
        carrier = runner.acceptance
        assert carrier is not None
        # The role declares exactly one private protocol capability; the
        # endpoint assembly must not widen it (the runtime asserts the live
        # MCP surface by exact equality).
        assert carrier.capability_endpoint("protocol").operations == (
            STAGED_PROTOCOL_OPERATION,
        )

        runner.start()

        assert len(probe.observations) == 1
        before_roster = probe.observations[0]
        assert before_roster["protocol"]["is_socket"] is True
        assert before_roster["protocol"]["tools"] == [STAGED_PROTOCOL_OPERATION]
        # CQ stays independently available, and no unselected role endpoint was
        # started into existence.
        assert before_roster[COMPETENCY_QUESTION_ROLE]["is_socket"] is True
        assert before_roster[COMPETENCY_QUESTION_ROLE]["tools"] == [
            "cq_publish_question_draft"
        ]
        assert before_roster["coordinator"]["is_socket"] is False
        assert before_roster["acceptance"]["is_socket"] is False

        protocol_socket = carrier.capability_socket_path("protocol")
        cq_socket = carrier.capability_socket_path(COMPETENCY_QUESTION_ROLE)
        # Both sockets stay live for the roster they were started for.
        assert _socket_tools(
            protocol_socket, carrier.capability_token("protocol")
        ) == [STAGED_PROTOCOL_OPERATION]
        assert _socket_tools(
            cq_socket, carrier.capability_token(COMPETENCY_QUESTION_ROLE)
        ) == ["cq_publish_question_draft"]
        # An unrelated role cannot borrow the protocol socket's surface.
        unrelated = _socket_request(
            protocol_socket, carrier.capability_token("coordinator"), "tools/list"
        )
        assert unrelated["error"]["code"] == -32001

        # The runtime's declared surface is what ``_require_mcp_surface``
        # compares against the live socket by exact equality: it must match
        # the socket's real ``tools/list``, not a superset.
        runtime = CodexRuntimeAdapter(repository_root=REPO_ROOT, use_bwrap=False)
        runtime._active_run = runner.run
        runtime._acceptance = carrier
        for role, declared in (
            ("protocol", (STAGED_PROTOCOL_OPERATION,)),
            (COMPETENCY_QUESTION_ROLE, ("cq_publish_question_draft",)),
            ("coordinator", ()),
            ("acceptance", ()),
        ):
            assert runtime._role_capability_operations(role, run=runner.run) == declared
        assert runtime._role_capability_operations(
            "protocol", run=runner.run
        ) == tuple(_socket_tools(protocol_socket, carrier.capability_token("protocol")))

        runner.cleanup()

        assert not protocol_socket.exists()
        assert not cq_socket.exists()
    finally:
        runner.cleanup()
        rmtree(run_root, ignore_errors=True)


def test_non_staged_non_formal_run_starts_no_capability_socket(tmp_path):
    probe = _RosterSocketProbe()
    runner = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=probe.adapter,
        ledger_root=tmp_path / "ledger",
        freeze_started_at=datetime.now(UTC).isoformat(),
    )
    probe.attach(runner)
    run_id = f"r30008b-nostaged-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]}"
    run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
    try:
        runner.prepare(
            run_id=run_id,
            profile_path=PROFILE,
            task_path=MULTI_SLICE_SMOKE,
            scope={"mode": "create"},
        )
        carrier = runner.acceptance
        assert carrier is not None

        runner.start()

        assert len(probe.observations) == 1
        observed = probe.observations[0]
        for role, state in observed.items():
            assert state["is_socket"] is False, role
            assert state["tools"] == [], role
        assert not carrier.capability_socket_path("protocol").exists()
    finally:
        runner.cleanup()
        rmtree(run_root, ignore_errors=True)
