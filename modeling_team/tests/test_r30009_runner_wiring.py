"""R3.0-009 Runner wiring tests: unified directories, submit-path bindings.

Covers test plan S13/S10/S18-side runner layers and the design §9.2 acceptance
timing: the plan is compared against the payloads actually forwarded, the
projection is closed against the published candidate and approvals, the intent
is written before forwarding and never leaks a Runner-private field into the
platform envelope, and the receipt copies the saved bindings.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree

import pytest

from modeling_team.contracts import load_multi_slice_team_configuration
from modeling_team.runner import TeamRunner
from modeling_team.staged_decisions import (
    StagedSubmissionRejection,
    build_decision_binding,
    build_identity_binding,
    build_submission_intent,
    candidate_item_digest,
    canonical_json_digest,
    projection_digest,
    staged_decision_artifact_paths,
    staged_decision_directories,
    write_submission_intent,
)
from modeling_team.tests.test_r30002_runner_wiring import FIXTURES, _gate_state
from modeling_team.tests.test_r30008b_runner_wiring import (
    _capability_args,
    _ForwarderRecorder,
    _materialization_valid,
    _write_json,
)
from modeling_team.tests.test_r30008b_staged_decisions import _approval_entry
from modeling_team.tests.test_runner import CapturingAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml"
SMOKE_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-decisions-smoke.yaml"
UNIFIED_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-009-unified-graph-real.yaml"


def _candidate() -> dict:
    return {
        "schema_version": "r3-0-009-unified-graph/v1",
        "scenario_id": "placeholder-scenario",
        "candidate_id": "cand-1",
        "revision": 2,
        "items": [
            {
                "item_id": "item-entity",
                "item_kind": "entity",
                "business_meaning": "placeholder meaning",
                "value": {"label": "placeholder"},
                "relation_endpoints": None,
                "evidence_refs": ["ev-1"],
                "slice_ids": ["slice-1"],
                "shared_scope": None,
                "unknowns": [],
            }
        ],
        "explicit_unknowns": [],
    }


def _unified_approvals(candidate: dict) -> dict:
    return {
        "schema_version": "r3-0-009-approvals/v1",
        "scenario_id": "placeholder-scenario",
        "maintained_by": "coordinator",
        "entries": [
            _approval_entry(),
            _approval_entry(
                kind="stage3_slot", target_id="placeholder-scenario", confirmed_enum_value=None
            ),
        ],
        "decisions": [
            {
                "decision_id": "decision-1",
                "target_kind": "commonality_node",
                "target_id": "item-entity",
                "candidate_id": "cand-1",
                "content_revision": 2,
                "content_digest": candidate_item_digest(candidate["items"][0]),
                "decision": "approved",
                "reason": "confirmed by business",
                "evidence_refs": ["ev-1"],
                "slice_ids": ["slice-1"],
                "shared_scope": None,
                "scope": None,
            }
        ],
        "translation_approvals": [
            {
                "plan_ref": "stage3-neutral-graph/materialization-plans/plan-1-r1.json",
                "projection_digest": "sha256:" + "0" * 64,
                "approved_by": "coordinator",
                "decision": "approved",
                "reason": "projection approved",
            }
        ],
    }


def _projection(candidate: dict, batch_items: list[dict]) -> dict:
    from modeling_team.staged_decisions import build_approval_projection

    return build_approval_projection(
        task_id="r3-0-009-unified-graph-real",
        scenario_id=candidate["scenario_id"],
        session_id="placeholder-session",
        client_batch_id="placeholder-batch-1",
        ontology_id="https://example.test/ontology/placeholder",
        candidate_id=candidate["candidate_id"],
        candidate_revision=candidate["revision"],
        candidate_digest=canonical_json_digest(candidate["items"]),
        items=batch_items,
        decision_bindings=[
            build_decision_binding(
                command_index=0,
                client_item_id="placeholder-item-1",
                candidate_item_ids=["item-entity"],
                candidate_revision=candidate["revision"],
                candidate_content_digests={
                    "item-entity": candidate_item_digest(candidate["items"][0])
                },
                decision_ids=["decision-1"],
            )
        ],
        identity_bindings=[
            build_identity_binding(
                candidate_item_id="item-entity",
                resource_iri="http://example.test/entity/placeholder-1",
                evidence_ref="ev-1",
            )
        ],
    )


def _batch_items() -> list[dict]:
    return [
        {
            "client_item_id": "placeholder-item-1",
            "command_kind": "create_entity",
            "payload": {"entity_id": "placeholder-entity-1", "label": "placeholder", "class_iris": []},
        }
    ]


class _UnifiedRunner:
    """A prepared 009 runner plus its capture adapter and run root."""

    def __init__(self, tmp_path, forwarder=None) -> None:
        self.run_id = f"r30009-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:10]}"
        self.run_root = REPO_ROOT / "workspaces" / "modeling-runs" / self.run_id
        self.adapter = CapturingAdapter()
        self.runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=self.adapter,
            ledger_root=tmp_path / "ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
            staged_batch_forwarder=forwarder,
        )

    def prepare(self, task_path: Path = UNIFIED_TASK) -> None:
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=task_path,
            scope={"mode": "create"},
        )

    def cleanup(self) -> None:
        self.runner.cleanup()
        if self.run_root.exists():
            rmtree(self.run_root)


def _open_platform_gate_unified(staged: _UnifiedRunner) -> None:
    """Open the shared gate with the 009 slot/approvals in place."""

    _materialization_valid(staged.run_root)
    _stage_unified(staged.run_root)
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


def _stage_unified(run_root: Path) -> tuple[dict, dict]:
    """Publish candidate, plan and 009 approvals, then return (candidate, plan)."""

    candidate = _candidate()
    items = _batch_items()
    projection = _projection(candidate, items)
    plan = {
        "schema_version": "r3-0-009-materialization-plan/v1",
        "plan_id": "plan-1",
        "revision": 1,
        "projection": projection,
        "projection_digest": projection_digest(projection),
    }
    paths = staged_decision_artifact_paths(run_root, unified=True)
    _write_json(paths["candidates_dir"] / "cand-1-r2.json", candidate)
    _write_json(paths["materialization_plans_dir"] / "plan-1-r1.json", plan)
    _write_json(paths["approvals"], _unified_approvals(candidate))
    # The 009 slot names the unified contract and the published candidate.
    slot = {
        "schema_version": "r3-0-009-stage3-slot/v1",
        "scenario_id": candidate["scenario_id"],
        "produced_by": "modeling",
        "approved_by": "coordinator",
        "candidate_artifacts": ["stage3-neutral-graph/candidates/cand-1-r2.json"],
        "candidate_contract": "r3-0-009-unified-graph/v1",
        "slot_note": "neutral slot",
    }
    _write_json(paths["stage3_slot"], slot)
    _write_json(
        run_root / "stage3-neutral-graph" / "placeholder-candidate.json",
        {"candidate": "placeholder"},
    )
    return candidate, plan


def _unified_args(batch_items: list[dict], plan_ref: str | None) -> dict:
    args = _capability_args()
    args["batch"]["items"] = batch_items
    if plan_ref is None:
        args.pop("plan_ref", None)
    else:
        args["plan_ref"] = plan_ref
    return args


# --- S13: the Task parameter selects the 009 contract -------------------------


def test_s13_unified_task_selects_the_009_contract(tmp_path):
    config = load_multi_slice_team_configuration(PROFILE, UNIFIED_TASK, root=REPO_ROOT)
    assert config.task.parameters["unified_semantic_graph"] is True
    staged = _UnifiedRunner(tmp_path)
    try:
        staged.prepare()
        assert staged.runner._staged_decisions is True
        assert staged.runner._unified_graph is True
        directories = {path.name for path in staged_decision_directories(staged.run_root, unified=True)}
        for name in ("candidates", "materialization-plans"):
            assert (staged.run_root / "stage3-neutral-graph" / name).is_dir()
        assert "candidates" in directories and "materialization-plans" in directories
    finally:
        staged.cleanup()


def test_s13_008b_task_keeps_the_unified_flow_disabled(tmp_path):
    staged = _UnifiedRunner(tmp_path)
    try:
        staged.prepare(SMOKE_TASK)
        assert staged.runner._staged_decisions is True
        assert staged.runner._unified_graph is False
        assert not (staged.run_root / "stage3-neutral-graph" / "candidates").exists()
        assert not (staged.run_root / "stage3-neutral-graph" / "materialization-plans").exists()
        paths = staged_decision_artifact_paths(staged.run_root, unified=False)
        assert "candidates_dir" not in paths
    finally:
        staged.cleanup()


# --- 009 submit path ---------------------------------------------------------


def test_unified_submission_requires_a_plan_ref(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _open_platform_gate_unified(staged)
        args = _unified_args(_batch_items(), None)
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(args)
        assert rejection.value.data["reason_code"] == "missing_candidate_reference"
        assert forwarder.calls == []
        assert not staged_decision_artifact_paths(staged.run_root)["intents_dir"].exists() or not list(
            staged_decision_artifact_paths(staged.run_root)["intents_dir"].iterdir()
        )
    finally:
        staged.cleanup()


def test_unified_submission_rejects_payload_drift_before_any_write(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        candidate, _plan = _stage_unified(staged.run_root)
        _open_platform_gate_unified(staged)
        ref = "stage3-neutral-graph/materialization-plans/plan-1-r1.json"
        drifted = [
            {
                **_batch_items()[0],
                "payload": {**_batch_items()[0]["payload"], "label": "changed"},
            }
        ]
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_unified_args(drifted, ref))
        assert rejection.value.data["reason_code"] == "approval_content_mismatch"
        assert forwarder.calls == []
        intents_dir = staged_decision_artifact_paths(staged.run_root)["intents_dir"]
        assert list(intents_dir.iterdir()) == []
        assert candidate["candidate_id"] == "cand-1"
    finally:
        staged.cleanup()


def test_unified_submission_rejects_a_stale_candidate_revision(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        candidate, plan = _stage_unified(staged.run_root)
        _open_platform_gate_unified(staged)
        stale_candidate = {**candidate, "revision": 3}
        paths = staged_decision_artifact_paths(staged.run_root, unified=True)
        (paths["candidates_dir"] / "cand-1-r2.json").unlink()
        _write_json(paths["candidates_dir"] / "cand-1-r3.json", stale_candidate)
        ref = "stage3-neutral-graph/materialization-plans/plan-1-r1.json"
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_unified_args(_batch_items(), ref))
        assert rejection.value.data["reason_code"] == "approval_stale"
        assert forwarder.calls == []
        assert plan["plan_id"] == "plan-1"
    finally:
        staged.cleanup()


def test_unified_submission_closes_receipt_against_the_saved_intent(tmp_path):
    forwarder = _ForwarderRecorder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    forwarder.intents_dir = staged_decision_artifact_paths(staged.run_root, unified=True)["intents_dir"]
    try:
        staged.prepare()
        _candidate_artifact, plan = _stage_unified(staged.run_root)
        _open_platform_gate_unified(staged)
        ref = "stage3-neutral-graph/materialization-plans/plan-1-r1.json"
        result = staged.runner._handle_staged_submit_modeling_batch(_unified_args(_batch_items(), ref))
        assert result["ok"] is True

        # The platform envelope carries none of the Runner-private bindings.
        forwarded = forwarder.calls[0]["batch"]
        for field in ("plan_ref", "projection", "projection_digest", "decision_bindings"):
            assert field not in forwarded
        assert forwarder.calls[0]["intents_at_call"] == ["intent-1.json"]

        paths = staged_decision_artifact_paths(staged.run_root, unified=True)
        intent = json.loads((paths["intents_dir"] / "intent-1.json").read_text(encoding="utf-8"))
        assert intent["schema_version"] == "r3-0-009-submission-intent/v1"
        assert intent["plan_ref"] == ref
        assert intent["projection_digest"] == plan["projection_digest"]
        assert intent["projection"] == plan["projection"]
        assert intent["decision_bindings"] == plan["projection"]["decision_bindings"]
        assert intent["status"] == "receipted"

        receipt = json.loads((paths["receipts_dir"] / "receipt-1.json").read_text(encoding="utf-8"))
        assert receipt["schema_version"] == "r3-0-009-submission-receipt/v1"
        assert receipt["plan_ref"] == intent["plan_ref"]
        assert receipt["projection_digest"] == intent["projection_digest"]
        assert receipt["decision_bindings"] == intent["decision_bindings"]
        assert "projection" not in receipt
    finally:
        staged.cleanup()


def test_legacy_intent_is_never_retrofitted_with_009_bindings(tmp_path):
    staged = _UnifiedRunner(tmp_path)
    try:
        staged.prepare(SMOKE_TASK)
        intent = build_submission_intent(
            1,
            idempotency_key="placeholder-key-1",
            client_batch_id="placeholder-client-batch-1",
            session_id="placeholder-session-1",
            mode="dry_run",
            commands=[],
            value_traces=[],
            l3_nodes=[],
        )
        paths = staged_decision_artifact_paths(staged.run_root)
        paths["intents_dir"].mkdir(parents=True, exist_ok=True)
        write_submission_intent(staged.run_root, intent)
        stored = json.loads((paths["intents_dir"] / "intent-1.json").read_text(encoding="utf-8"))
        assert stored["schema_version"] == "r3-0-008b-submission-intent/v1"
        assert set(stored) == {
            "schema_version",
            "ordinal",
            "idempotency_key",
            "client_batch_id",
            "session_id",
            "mode",
            "commands",
            "value_traces",
            "l3_nodes",
            "status",
        }
    finally:
        staged.cleanup()


def test_stage3_gate_accepts_the_unified_slot_contract(tmp_path):
    staged = _UnifiedRunner(tmp_path)
    try:
        staged.prepare()
        _stage_unified(staged.run_root)
        assert staged.runner._check_staged_decision_gates() is True
        assert _gate_state(staged.run_root)["reason_code"] == "topology_missing_artifact"
        reasons = [
            json.loads(delivery.text)["reason_code"]
            for _agent, delivery in staged.adapter.messages
            if delivery.kind == "staged-decision-gate"
        ]
        assert "stage3_schema_mismatch" not in reasons
    finally:
        staged.cleanup()
