"""R3.0-014 mechanical tests: dry-run first, translation review, gated apply.

Covers the shared test plan M-cases that are mechanically decidable without a
live platform or a semantic run:

* M1  — a dry-run passes with rejected/old/format-drifted translation history;
* M2  — an apply is rejected, in order, by the translation gate then the proof
        gate, before any intent or forwarder call;
* M3  — an ``ok``-only forwarder result writes a receipt but never a proof, so
        the apply gate fails closed on the missing record;
* M5/M24 — the capability response passes the Attempt facts through verbatim;
* M6/M7/M28/M29 — the translation matrix (exact key, current Coordinator,
        conflicts, drifted entries as history);
* M10-M13 — the proof matrix (content hash, workspace timepoint, idempotency
        key reuse, validated status);
* M16 — pure workspace-version drift is typed; a proof without a workspace
        timepoint stays usable;
* M21 — the 008B staged path writes no proof and gains no gate;
* plus a cross-check that ``platform_content_hash`` equals the backend
  service's own ``_hash(_content(payload))`` over the same envelope.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modeling_team.staged_decisions import (
    ATTEMPT_PROOF_EVENT,
    ATTEMPT_PROOF_FIELDS,
    ATTEMPT_PROOF_SCHEMA,
    StagedDecisionArtifactError,
    StagedSubmissionRejection,
    build_attempt_proof,
    platform_content_hash,
    read_attempt_proofs,
    staged_decision_artifact_paths,
    unified_dry_run_proof_issue,
    unified_translation_issue,
)
from modeling_team.tests.test_r30008b_runner_wiring import (
    _capability_args,
    _materialization_valid,
    _open_platform_gate,
    _write_json,
    _StagedRunner,
)
from modeling_team.tests.test_r30009_runner_wiring import (
    _batch_items,
    _open_platform_gate_unified,
    _stage_unified,
    _unified_args,
    _UnifiedRunner,
)

PLAN_REF = "stage3-neutral-graph/materialization-plans/plan-1-r1.json"
DIGEST = "sha256:" + "a" * 64


def _dry_run_batch() -> dict:
    return _unified_args(_batch_items(), PLAN_REF)["batch"]


def _apply_batch(key: str = "placeholder-key-2") -> dict:
    batch = _unified_args(_batch_items(), PLAN_REF, mode="apply_atomic")["batch"]
    batch["idempotency_key"] = key
    return batch


def _apply_args(key: str = "placeholder-key-2") -> dict:
    """Apply arguments with a fresh idempotency key, never the dry-run's."""

    args = _unified_args(_batch_items(), PLAN_REF, mode="apply_atomic")
    args["batch"]["idempotency_key"] = key
    return args


def _translation_approvals(*entries) -> dict:
    return {
        "schema_version": "r3-0-009-approvals/v2",
        "scenario_id": "placeholder-scenario",
        "maintained_by": "coordinator",
        "entries": [],
        "decisions": [],
        "translation_approvals": list(entries),
    }


def _entry(**overrides) -> dict:
    entry = {
        "plan_ref": PLAN_REF,
        "projection_digest": DIGEST,
        "approved_by": "coordinator-agent-1",
        "decision": "approved",
        "reason": "translation reviewed",
    }
    entry.update(overrides)
    return entry


def _proof(**overrides) -> dict:
    record = {
        "schema_version": ATTEMPT_PROOF_SCHEMA,
        "event": ATTEMPT_PROOF_EVENT,
        "intent_ordinal": 1,
        "receipt_ordinal": 1,
        "plan_ref": PLAN_REF,
        "projection_digest": DIGEST,
        "batch_id": "platform-batch-1",
        "attempt_id": "platform-attempt-dry-run",
        "client_batch_id": _dry_run_batch()["client_batch_id"],
        "idempotency_key": "placeholder-key-1",
        "mode": "dry_run",
        "attempt_status": "validated",
        "content_hash": platform_content_hash(_dry_run_batch()),
        "workspace_before_version": "1",
        "response_digest": "sha256:" + "b" * 64,
        "recorded_at": "2026-01-01T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def _write_proofs(run_root: Path, *records) -> Path:
    evidence = run_root / "evidence" / "staged-decisions.jsonl"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    with evidence.open("a", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return evidence


# --- the local content hash is the platform's own hash ------------------------


def test_platform_content_hash_matches_the_backend_service_hash():
    from app.api.schemas import ModelingBatchSubmit
    from app.services.modeling_batches import ModelingBatchService
    from app.services.modeling_batches import _hash as backend_hash

    ontology_id = "ont-hash-check"
    items = [
        {
            "client_item_id": "placeholder-item-2",
            "command_kind": "create_entity",
            "payload": {"entity_id": "placeholder-entity-2", "label": "two", "class_iris": []},
            "depends_on": ["placeholder-item-1", "placeholder-item-1"],
        },
        {
            "client_item_id": "placeholder-item-1",
            "command_kind": "create_entity",
            "payload": {"entity_id": "placeholder-entity-1", "label": "one", "class_iris": []},
        },
    ]
    payload = ModelingBatchSubmit(
        client_batch_id="placeholder-batch-1",
        ontology_id=ontology_id,
        idempotency_key="placeholder-key-1",
        expected_workspace_version="1",
        mode="dry_run",
        items=items,
    )
    backend_hash_value = backend_hash(ModelingBatchService._content(payload))
    # Item order, duplicate and unsorted set-valued lists never change the hash
    # on either side, so a dry-run proof and a same-content apply hash identically.
    assert platform_content_hash({"ontology_id": ontology_id, "items": items}) == backend_hash_value
    assert platform_content_hash(
        {"ontology_id": ontology_id, "items": [items[1], items[0]]}
    ) == backend_hash_value
    # Mode, key, lease and workspace version stay outside the content hash.
    assert platform_content_hash(
        {
            "ontology_id": ontology_id,
            "items": items,
            "mode": "apply_atomic",
            "idempotency_key": "another-key",
            "lease_token": "lease",
            "expected_workspace_version": "9",
        }
    ) == backend_hash_value


# --- M6/M7/M28/M29: the apply-time translation matrix -------------------------


def test_translation_gate_matrix():
    # An empty translation history is a legal approvals file for the dry-run
    # stage, but the apply-time gate still reports it: nothing releases an
    # apply except a current approval for the exact plan key.
    assert unified_translation_issue(
        _translation_approvals(), plan_ref=PLAN_REF, projection_digest=DIGEST,
        coordinator_id="coordinator-agent-1",
    ).reason_code == "approval_missing"

    cases = [
        ([_entry(decision="rejected")], "approval_missing"),
        ([_entry(decision="deferred")], "approval_missing"),
        ([_entry(approved_by="someone-else")], "approval_missing"),
        ([_entry(plan_ref="stage3-neutral-graph/materialization-plans/plan-0-r1.json")], "approval_missing"),
        ([_entry(projection_digest="sha256:" + "c" * 64)], "approval_missing"),
        ([_entry(decision="approved"), _entry(decision="rejected")], "approval_conflict"),
        ([_entry(), _entry(approved_by="coordinator-agent-2")], "approval_conflict"),
        ([{"plan_ref": PLAN_REF, "projection_digest": DIGEST}], "approval_missing"),
    ]
    for entries, expected in cases:
        issue = unified_translation_issue(
            _translation_approvals(*entries), plan_ref=PLAN_REF, projection_digest=DIGEST,
            coordinator_id="coordinator-agent-1",
        )
        assert issue is not None and issue.reason_code == expected, (entries, expected)

    # Equivalent repeats are one decision; drifted entries are skipped history.
    assert unified_translation_issue(
        _translation_approvals(_entry(), _entry(), {"extra": 1}),
        plan_ref=PLAN_REF, projection_digest=DIGEST, coordinator_id="coordinator-agent-1",
    ) is None

    assert unified_translation_issue(
        _translation_approvals(), plan_ref="", projection_digest=DIGEST,
        coordinator_id="coordinator-agent-1",
    ).reason_code == "missing_candidate_reference"
    assert unified_translation_issue(
        _translation_approvals(), plan_ref=PLAN_REF, projection_digest="",
        coordinator_id="coordinator-agent-1",
    ).reason_code == "missing_candidate_reference"
    # Without a resolvable current Coordinator the gate cannot fire safely.
    assert unified_translation_issue(
        _translation_approvals(), plan_ref=PLAN_REF, projection_digest=DIGEST,
        coordinator_id="",
    ).reason_code == "missing_candidate_reference"
    assert unified_translation_issue(
        {"schema_version": "r3-0-009-approvals/v2", "translation_approvals": "nope"},
        plan_ref=PLAN_REF, projection_digest=DIGEST, coordinator_id="coordinator-agent-1",
    ).reason_code == "unified_schema_mismatch"
    assert unified_translation_issue(
        None, plan_ref=PLAN_REF, projection_digest=DIGEST, coordinator_id="coordinator-agent-1",
    ).reason_code == "unified_schema_mismatch"


# --- M10-M13/M16: the apply-time dry-run proof matrix -------------------------


def test_dry_run_proof_gate_matrix(tmp_path):
    apply_batch = _apply_batch()

    # No proof at all: fail closed, never "assume it was fine".
    assert unified_dry_run_proof_issue(
        tmp_path, apply_batch, plan_ref=PLAN_REF, projection_digest=DIGEST
    ).reason_code == "dry_run_proof_missing"

    _write_proofs(tmp_path, _proof())
    assert unified_dry_run_proof_issue(
        tmp_path, apply_batch, plan_ref=PLAN_REF, projection_digest=DIGEST
    ) is None

    cases = [
        (_proof(attempt_status="validation_failed"), "dry_run_proof_not_validated"),
        (_proof(content_hash="0" * 64), "dry_run_proof_content_mismatch"),
        (_proof(workspace_before_version="0"), "dry_run_proof_workspace_mismatch"),
        (_proof(mode="apply_atomic"), "dry_run_proof_missing"),
        (_proof(plan_ref="stage3-neutral-graph/materialization-plans/plan-0-r1.json"), "dry_run_proof_missing"),
        (_proof(projection_digest="sha256:" + "c" * 64), "dry_run_proof_missing"),
        (_proof(client_batch_id="another-client-batch"), "dry_run_proof_missing"),
        ({**_proof(), "unexpected_field": 1}, "dry_run_proof_missing"),
    ]
    for index, (record, expected) in enumerate(cases):
        run_root = tmp_path / f"case-{index}-{expected}"
        run_root.mkdir()
        _write_proofs(run_root, record)
        issue = unified_dry_run_proof_issue(
            run_root, apply_batch, plan_ref=PLAN_REF, projection_digest=DIGEST
        )
        assert issue is not None and issue.reason_code == expected, (record, expected)

    # The apply reusing the dry-run's idempotency key is a typed conflict.
    same_key = _apply_batch(key="placeholder-key-1")
    assert unified_dry_run_proof_issue(
        tmp_path, same_key, plan_ref=PLAN_REF, projection_digest=DIGEST
    ).reason_code == "idempotency_conflict"

    # A proof with no workspace timepoint stays usable for the apply (M16).
    _write_proofs(tmp_path, _proof(workspace_before_version=None))
    assert unified_dry_run_proof_issue(
        tmp_path, apply_batch, plan_ref=PLAN_REF, projection_digest=DIGEST
    ) is None

    # An unparsable evidence file is a reconciliation failure, not empty history.
    run_root = tmp_path / "case-unparsable"
    run_root.mkdir()
    _write_proofs(run_root, _proof())
    with (run_root / "evidence" / "staged-decisions.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{not json\n")
    with pytest.raises(StagedDecisionArtifactError) as failure:
        unified_dry_run_proof_issue(run_root, apply_batch, plan_ref=PLAN_REF, projection_digest=DIGEST)
    assert failure.value.reason_code == "staged_unreconciled_batch"


def test_read_attempt_proofs_keeps_only_the_closed_schema(tmp_path):
    assert read_attempt_proofs(tmp_path) == []
    _write_proofs(
        tmp_path,
        {"schema_version": "other/v1", "event": "unrelated"},
        {**_proof(), "extra": 1},
        _proof(attempt_id="platform-attempt-2"),
    )
    proofs = read_attempt_proofs(tmp_path)
    assert [proof["attempt_id"] for proof in proofs] == ["platform-attempt-2"]


# --- M3/M5/M24: proof building requires complete Attempt identity -------------


def test_build_attempt_proof_requires_complete_platform_identity():
    batch = _dry_run_batch()

    def result(**overrides):
        data = {
            "batch_id": "platform-batch-1",
            "client_batch_id": batch["client_batch_id"],
            "attempt_id": "platform-attempt-dry-run",
            "idempotency_key": batch["idempotency_key"],
            "mode": "dry_run",
            "attempt_status": "validated",
            "content_hash": platform_content_hash(batch),
            "workspace": {"before_version": "1"},
        }
        data.update(overrides)
        return data

    proof = build_attempt_proof(
        intent_ordinal=1, receipt_ordinal=1, plan_ref=PLAN_REF, projection_digest=DIGEST,
        batch=batch, result=result(), response_digest="sha256:" + "b" * 64,
    )
    assert proof is not None
    assert set(proof) == set(ATTEMPT_PROOF_FIELDS)
    assert proof["schema_version"] == ATTEMPT_PROOF_SCHEMA
    assert proof["event"] == ATTEMPT_PROOF_EVENT

    # A result without the read-back-verified identity is never a proof.
    for field in ("batch_id", "attempt_id", "mode", "attempt_status", "content_hash"):
        assert build_attempt_proof(
            intent_ordinal=1, receipt_ordinal=1, plan_ref=PLAN_REF, projection_digest=DIGEST,
            batch=batch, result=result(**{field: ""}), response_digest="sha256:x",
        ) is None, field
    # A mode the batch did not request, or not a batch mode at all.
    assert build_attempt_proof(
        intent_ordinal=1, receipt_ordinal=1, plan_ref=PLAN_REF, projection_digest=DIGEST,
        batch=batch, result=result(mode="apply_atomic"), response_digest="sha256:x",
    ) is None
    assert build_attempt_proof(
        intent_ordinal=1, receipt_ordinal=1, plan_ref=PLAN_REF, projection_digest=DIGEST,
        batch=batch, result=result(mode="apply_partial"), response_digest="sha256:x",
    ) is None
    # The idempotency key falls back to the submitted envelope's.
    fallback = build_attempt_proof(
        intent_ordinal=1, receipt_ordinal=1, plan_ref=PLAN_REF, projection_digest=DIGEST,
        batch=batch, result=result(idempotency_key=None), response_digest="sha256:x",
    )
    assert fallback["idempotency_key"] == batch["idempotency_key"]
    # A result with no workspace block still proves the attempt, timepoint-free.
    no_workspace = build_attempt_proof(
        intent_ordinal=1, receipt_ordinal=1, plan_ref=PLAN_REF, projection_digest=DIGEST,
        batch=batch, result={key: value for key, value in result().items() if key != "workspace"},
        response_digest="sha256:x",
    )
    assert no_workspace["workspace_before_version"] is None


# --- Runner integration: the staged order through the real handler ------------


def _attempt_forwarder(*, content_hash=None, attempt_status="validated", workspace_before="1"):
    """A forwarder whose reply carries the full read-back-verified identity."""

    calls: list[dict] = []

    def forward(batch):
        calls.append(dict(batch))
        return {
            "batch_id": "platform-batch-1",
            "client_batch_id": batch["client_batch_id"],
            "attempt_id": f"platform-attempt-{batch['mode']}",
            "idempotency_key": batch["idempotency_key"],
            "mode": batch["mode"],
            "attempt_status": attempt_status,
            "content_hash": content_hash or platform_content_hash(batch),
            "workspace": {"before_version": workspace_before},
        }

    return forward, calls


def _approvals_path(staged) -> Path:
    return staged_decision_artifact_paths(staged.run_root, unified=True)["approvals"]


def _record_translation_approval(staged, plan) -> None:
    approvals = json.loads(_approvals_path(staged).read_text(encoding="utf-8"))
    approvals["translation_approvals"] = [
        {
            "plan_ref": PLAN_REF,
            "projection_digest": plan["projection_digest"],
            "approved_by": staged.runner._multi_slice_role_ids()["coordinator"],
            "decision": "approved",
            "reason": "translation reviewed",
        }
    ]
    _write_json(_approvals_path(staged), approvals)


def test_dry_run_passes_over_rejected_translation_history_and_writes_the_proof(tmp_path):
    forwarder, calls = _attempt_forwarder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _candidate, plan = _stage_unified(staged.run_root)
        # Rejected translation history for this very plan must not gate a dry-run.
        approvals = json.loads(_approvals_path(staged).read_text(encoding="utf-8"))
        approvals["translation_approvals"] = [
            {
                "plan_ref": PLAN_REF,
                "projection_digest": plan["projection_digest"],
                "approved_by": "coordinator-agent-1",
                "decision": "rejected",
                "reason": "history",
            }
        ]
        _write_json(_approvals_path(staged), approvals)
        _open_platform_gate_unified(staged)

        response = staged.runner._handle_staged_submit_modeling_batch(
            _unified_args(_batch_items(), PLAN_REF)
        )

        # M1: the dry-run went through; M5/M24: the Attempt facts pass through.
        assert response["ok"] is True
        assert response["mode"] == "dry_run"
        assert response["attempt_id"] == "platform-attempt-dry_run"
        assert response["attempt_status"] == "validated"
        assert response["content_hash"] == platform_content_hash(
            _unified_args(_batch_items(), PLAN_REF)["batch"]
        )
        assert calls[0]["mode"] == "dry_run"
        assert "lease_token" not in calls[0]

        # The Runner wrote its own proof into host evidence, bound to the plan.
        proofs = read_attempt_proofs(staged.run_root)
        assert [proof["attempt_id"] for proof in proofs] == ["platform-attempt-dry_run"]
        proof = proofs[0]
        assert proof["plan_ref"] == PLAN_REF
        assert proof["projection_digest"] == plan["projection_digest"]
        assert proof["mode"] == "dry_run"
        assert proof["attempt_status"] == "validated"
        assert proof["receipt_ordinal"] == 1
    finally:
        staged.cleanup()


def test_apply_is_gated_translation_then_proof_before_any_write(tmp_path):
    forwarder, calls = _attempt_forwarder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _candidate, plan = _stage_unified(staged.run_root)
        _open_platform_gate_unified(staged)

        # No translation approval at all: the apply stops at the translation gate.
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_unified_args(_batch_items(), PLAN_REF, mode="apply_atomic"))
        assert rejection.value.data["reason_code"] == "approval_missing"
        assert calls == []
        intents_dir = staged_decision_artifact_paths(staged.run_root, unified=True)["intents_dir"]
        assert not intents_dir.exists() or not list(intents_dir.iterdir())

        # The approval exists but no dry-run proof does: the proof gate fires.
        _record_translation_approval(staged, plan)
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_unified_args(_batch_items(), PLAN_REF, mode="apply_atomic"))
        assert rejection.value.data["reason_code"] == "dry_run_proof_missing"
        assert calls == []

        # A wrong approver is also a typed translation rejection (M29).
        approvals = json.loads(_approvals_path(staged).read_text(encoding="utf-8"))
        approvals["translation_approvals"][0]["approved_by"] = "someone-else"
        _write_json(_approvals_path(staged), approvals)
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_unified_args(_batch_items(), PLAN_REF, mode="apply_atomic"))
        assert rejection.value.data["reason_code"] == "approval_missing"
        assert calls == []

        # The real dry-run, the Coordinator's current approval, then the apply.
        _record_translation_approval(staged, plan)
        assert staged.runner._handle_staged_submit_modeling_batch(
            _unified_args(_batch_items(), PLAN_REF)
        )["ok"] is True
        apply_args = _unified_args(_batch_items(), PLAN_REF, mode="apply_atomic")
        apply_args["batch"]["idempotency_key"] = "placeholder-key-2"
        response = staged.runner._handle_staged_submit_modeling_batch(apply_args)

        assert response["ok"] is True
        assert response["mode"] == "apply_atomic"
        assert response["attempt_id"] == "platform-attempt-apply_atomic"
        assert [call["mode"] for call in calls] == ["dry_run", "apply_atomic"]
        assert calls[1]["lease_token"] == "placeholder-lease"
        assert calls[1]["items"] == calls[0]["items"]
    finally:
        staged.cleanup()


def test_stub_forwarder_receipt_is_not_a_proof_and_the_apply_fails_closed(tmp_path):
    from modeling_team.tests.test_r30008b_runner_wiring import _ForwarderRecorder

    forwarder = _ForwarderRecorder()  # only {"batch_id": ...}: a bare receipt
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _candidate, plan = _stage_unified(staged.run_root)
        _open_platform_gate_unified(staged)

        response = staged.runner._handle_staged_submit_modeling_batch(
            _unified_args(_batch_items(), PLAN_REF)
        )
        assert response["ok"] is True
        # M3: the receipt exists but no Attempt fact was identifiable, so no
        # proof was written and none may be invented.
        assert read_attempt_proofs(staged.run_root) == []
        assert "attempt_id" not in response
        assert "content_hash" not in response

        _record_translation_approval(staged, plan)
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_unified_args(_batch_items(), PLAN_REF, mode="apply_atomic"))
        assert rejection.value.data["reason_code"] == "dry_run_proof_missing"
    finally:
        staged.cleanup()


def test_apply_rejects_a_not_validated_or_content_mismatched_dry_run(tmp_path):
    _candidate, plan = None, None
    for attempt_status, content_hash, expected in (
        ("validation_failed", None, "dry_run_proof_not_validated"),
        (None, "0" * 64, "dry_run_proof_content_mismatch"),
    ):
        forwarder, _calls = _attempt_forwarder(
            attempt_status=attempt_status or "validated", content_hash=content_hash
        )
        staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
        try:
            staged.prepare()
            _candidate, plan = _stage_unified(staged.run_root)
            _open_platform_gate_unified(staged)
            assert staged.runner._handle_staged_submit_modeling_batch(
                _unified_args(_batch_items(), PLAN_REF)
            )["ok"] is True
            _record_translation_approval(staged, plan)
            with pytest.raises(StagedSubmissionRejection) as rejection:
                staged.runner._handle_staged_submit_modeling_batch(_apply_args())
            assert rejection.value.data["reason_code"] == expected
        finally:
            staged.cleanup()
            _candidate, plan = None, None


def test_apply_rejects_reusing_the_dry_run_idempotency_key(tmp_path):
    forwarder, _calls = _attempt_forwarder()
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _candidate, plan = _stage_unified(staged.run_root)
        _open_platform_gate_unified(staged)
        assert staged.runner._handle_staged_submit_modeling_batch(
            _unified_args(_batch_items(), PLAN_REF)
        )["ok"] is True
        _record_translation_approval(staged, plan)
        # Same idempotency key as the dry-run: a typed conflict, not a replay.
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(
                _unified_args(_batch_items(), PLAN_REF, mode="apply_atomic")
            )
        assert rejection.value.data["reason_code"] == "idempotency_conflict"
    finally:
        staged.cleanup()


def test_workspace_drift_is_typed_and_a_timepoint_free_proof_stays_usable(tmp_path):
    # M16: the dry-run was taken at another workspace version.
    forwarder, _calls = _attempt_forwarder(workspace_before="0")
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    try:
        staged.prepare()
        _candidate, plan = _stage_unified(staged.run_root)
        _open_platform_gate_unified(staged)
        assert staged.runner._handle_staged_submit_modeling_batch(
            _unified_args(_batch_items(), PLAN_REF)
        )["ok"] is True
        _record_translation_approval(staged, plan)
        with pytest.raises(StagedSubmissionRejection) as rejection:
            staged.runner._handle_staged_submit_modeling_batch(_apply_args())
        assert rejection.value.data["reason_code"] == "dry_run_proof_workspace_mismatch"
    finally:
        staged.cleanup()

    # A forwarder result with no workspace block still proves the attempt.
    def forward(batch):
        return {
            "batch_id": "platform-batch-1",
            "client_batch_id": batch["client_batch_id"],
            "attempt_id": "platform-attempt-dry_run",
            "idempotency_key": batch["idempotency_key"],
            "mode": batch["mode"],
            "attempt_status": "validated",
            "content_hash": platform_content_hash(batch),
        }

    staged = _UnifiedRunner(tmp_path, forwarder=forward)
    try:
        staged.prepare()
        _candidate, plan = _stage_unified(staged.run_root)
        _open_platform_gate_unified(staged)
        assert staged.runner._handle_staged_submit_modeling_batch(
            _unified_args(_batch_items(), PLAN_REF)
        )["ok"] is True
        _record_translation_approval(staged, plan)
        apply_args = _unified_args(_batch_items(), PLAN_REF, mode="apply_atomic")
        apply_args["batch"]["idempotency_key"] = "placeholder-key-2"
        assert staged.runner._handle_staged_submit_modeling_batch(apply_args)["ok"] is True
    finally:
        staged.cleanup()


# --- M21: the 008B staged path is untouched ------------------------------------


def test_008b_submission_writes_no_proof_and_gains_no_gate(tmp_path):
    def forward(batch):
        return {
            "batch_id": "platform-batch-1",
            "attempt_id": "platform-attempt-1",
            "mode": batch["mode"],
            "attempt_status": "validated",
            "content_hash": "0" * 64,
        }

    staged = _StagedRunner(tmp_path, forwarder=forward)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)

        response = staged.runner._handle_staged_submit_modeling_batch(_capability_args())

        assert response["ok"] is True
        # No plan_ref, no translation approvals, no proof: the legacy staged
        # contract writes only its intent and receipt.
        assert read_attempt_proofs(staged.run_root) == []
        receipts_dir = staged_decision_artifact_paths(staged.run_root)["receipts_dir"]
        receipts = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(receipts_dir.iterdir())]
        assert len(receipts) == 1
        assert receipts[0]["schema_version"] == "r3-0-008b-submission-receipt/v1"
        assert "plan_ref" not in receipts[0]
    finally:
        staged.cleanup()
