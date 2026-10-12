"""Recovery contracts through actual native capabilities; no semantic start or live writes."""
# ruff: noqa: F811 - shared pytest fixture names are also test parameter names

from copy import deepcopy

import pytest

from modeling_team.checkpoint_recovery import (
    CompletedOperation, build_plan_mappings, build_role_packets, check_resume_submission, read_write_tail,
    reconcile_write_tail,
)
from modeling_team.checkpoints import CheckpointError, save_checkpoint
from modeling_team.staged_decisions import (
    StagedBatchForwardError, read_submission_intents, read_submission_receipts,
)
from modeling_team.tests.test_r30009_plan_ref_capability_schema import _protocol_capability
from modeling_team.tests.test_r30015_resume import (
    CONFIGURATION, FakeCursorPlatform, _attempt, _batch, _manifest_of,
    _plan_mapping_manifest, _readback, _seed_chain_intent, _write_json,
)
from modeling_team.tests.test_v43_production_refs import (
    PLAN1, PLAN2,
    call,
    execute_args,
    production,  # noqa: F401 - shared pytest fixture
)


def _recovering_apply(production):
    original = production.runner.staged_batch_forwarder
    retained = {}

    def forward(batch):
        if batch["mode"] == "dry_run":
            return original(batch)
        if not retained:
            result = dict(original(batch))
            result.update(attempt_status="recovering", created_batch=True, created_attempt=True)
            retained.update(batch=deepcopy(batch), result=result, forward_base=original)
            return result
        assert batch == retained["batch"]
        production.calls.append(deepcopy(batch))
        return {**retained["result"], "attempt_status": "applied",
                "created_batch": False, "created_attempt": False}

    production.runner.staged_batch_forwarder = forward
    return retained


def _submit_args(production, retained):
    return {"protocol_id": execute_args(production)["protocol_id"], "plan_ref": PLAN1,
            "batch": deepcopy(retained["batch"]), "value_traces": [], "l3_nodes": []}


def test_receipted_recovering_attempt_continues_same_request_without_new_identity(production):
    retained = _recovering_apply(production)
    with _protocol_capability(production) as endpoint:
        first = call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "plan_refs": [PLAN1],
        })
        assert first["error"]["reason_code"] == "staged_plan_apply_incomplete"
        before = read_submission_receipts(production.run_root)
        version = dict(production.versions)
        recovered = call(endpoint, "protocol_staged_submit_modeling_batch",
                         _submit_args(production, retained))
        assert recovered.get("attempt_status") == "applied", recovered
        assert recovered["attempt_id"] == retained["result"]["attempt_id"]
        assert recovered["batch_id"] == retained["result"]["batch_id"]
        assert recovered["created_batch"] is False and recovered["created_attempt"] is False
        assert production.versions == version
        assert len(read_submission_intents(production.run_root)) == 2
        after = read_submission_receipts(production.run_root)
        assert after[:len(before)] == before
        assert len(after) == len(before) + 1
        assert after[-1]["intent_ordinal"] == before[-1]["intent_ordinal"]
        replay = call(endpoint, "protocol_staged_submit_modeling_batch",
                      _submit_args(production, retained))
        assert replay["error"]["reason_code"] == "staged_conclusion_already_materialized"
        assert len(production.calls) == 3  # dry-run, original apply, same Attempt recovery
        continued = call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "plan_refs": [PLAN1],
        })
        assert continued["completed"][0]["status"] == "already_applied", continued
        assert len(production.calls) == 3


@pytest.mark.parametrize("field,value", [("lease_token", "replacement-lease"),
                                         ("expected_model_revision", 999),
                                         ("idempotency_key", "replacement-key")])
def test_same_attempt_recovery_rejects_changed_original_request(production, field, value):
    retained = _recovering_apply(production)
    with _protocol_capability(production) as endpoint:
        call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "plan_refs": [PLAN1],
        })
        args = _submit_args(production, retained)
        args["batch"][field] = value
        result = call(endpoint, "protocol_staged_submit_modeling_batch", args)
        assert result["error"]["reason_code"] == "staged_recovery_request_mismatch", result
        assert len(production.calls) == 2


def test_unrelated_ontology_can_continue_while_original_attempt_needs_recovery(production):
    retained = _recovering_apply(production)
    with _protocol_capability(production) as endpoint:
        call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "plan_refs": [PLAN1],
        })
        original = production.runner.staged_batch_forwarder

        def forward(batch):
            if batch["ontology_id"] == retained["batch"]["ontology_id"]:
                return original(batch)
            return retained["forward_base"](batch)

        production.runner.staged_batch_forwarder = forward
        result = call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "plan_refs": [PLAN2],
        })
        assert result["ok"] is True, result
        assert result["completed"][0]["status"] == "applied"


@pytest.mark.parametrize("failure", ["changed_attempt", "prewrite_refusal", "missing_original"])
def test_recovery_failure_keeps_original_write_unresolved(production, failure):
    retained = _recovering_apply(production)
    with _protocol_capability(production) as endpoint:
        call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "plan_refs": [PLAN1],
        })
        before = read_submission_receipts(production.run_root)
        if failure == "changed_attempt":
            original = production.runner.staged_batch_forwarder

            def forward(batch):
                return {**original(batch), "attempt_id": "unexpected-new-attempt"}

            production.runner.staged_batch_forwarder = forward
        elif failure == "prewrite_refusal":
            def forward(_batch):
                raise StagedBatchForwardError("original Build Session is temporarily unavailable")

            production.runner.staged_batch_forwarder = forward
        else:
            records = production.runner.acceptance.protocol_list_platform_artifacts(
                protocol_id=execute_args(production)["protocol_id"],
            )["artifacts"]
            for record in records:
                if record["tool"] == "submit_modeling_batch" and record["request_arguments"]["mode"] == "apply_atomic":
                    (production.run_root / record["artifact_path"]).unlink()
        result = call(endpoint, "protocol_staged_submit_modeling_batch", _submit_args(production, retained))
        expected = {"changed_attempt": "staged_batch_forward_unknown",
                    "prewrite_refusal": "staged_unreconciled_batch",
                    "missing_original": "staged_recovery_request_mismatch"}
        assert result["error"]["reason_code"] == expected[failure], result
        assert read_submission_receipts(production.run_root) == before
        intents = read_submission_intents(production.run_root)
        assert intents[-1]["status"] == ("unknown" if failure == "changed_attempt" else "receipted")


def test_recovery_packet_shares_completed_item_facts_and_limits_review_to_remaining_content():
    completed = CompletedOperation(
        origin_run_id="successor", session_id="session", batch_id="batch-success",
        attempt_id="attempt-success", client_item_id="item-covered",
        client_batch_id="successor-plan", mode="apply_atomic", resource_ids=("resource-1",),
    )
    reconciliation = {"completed": [completed],
                      "completed_client_batches": {"successor-plan": "batch-success"},
                      "pending_new_dry_run": [{"client_batch_id": "historical-pending"}],
                      "recoverable_new_batch": []}
    manifest = {"stage_facts": {}, "artifacts": [], "kind": "materialization_progress"}
    packets = build_role_packets(manifest, reconciliation, [], {}, {})
    for role in ("host", "coordinator", "modeling", "protocol"):
        assert packets[role]["completed_scope"]["items"] == [completed.index_entry()]
    for role in ("coordinator", "modeling", "protocol"):
        note = packets[role]["translation_review"]["note"]
        assert "only genuinely remaining content" in note
        assert "covered content stays history" in note
    assert "items" not in packets["competency-question"]["completed_scope"]


def test_successor_readback_locates_actual_resources_without_erasing_pending_history(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _seed_chain_intent(source, 1, key="old-dry", client_batch_id="historical-pending",
                       session_id="session-1", mode="dry_run")
    _seed_chain_intent(source, 2, key="successor-apply", client_batch_id="successor-plan",
                       session_id="session-1", batch_id="batch-success")
    batches = [_batch("batch-old", client_batch_id="historical-pending",
                      attempts=[_attempt("dry-attempt", mode="dry_run", status="validated")]),
               _batch("batch-success", client_batch_id="successor-plan")]
    before = read_write_tail([source])
    reconciled = reconcile_write_tail([source], before, _readback(FakeCursorPlatform(
        session_batches={"session-1": batches})), ontology_ids=[])
    assert reconciled["blocked"] == []
    assert reconciled["pending_new_dry_run"][0]["client_batch_id"] == "historical-pending"
    assert reconciled["completed"][0].resource_ids == ("res://item-1",)
    assert read_write_tail([source]) == before


@pytest.mark.parametrize("batches,completed,expected", [
    (["cb-done"], {"cb-done": "batch-1"}, "completed_do_not_resubmit"),
    (["cb-done", "cb-todo"], {"cb-done": "batch-1"}, "unfinished_submit_through_new_session"),
])
def test_current_projection_plan_mapping_requires_all_own_batches_completed(
    tmp_path, batches, completed, expected,
):
    package, source = _plan_mapping_manifest(tmp_path)
    ref = "stage3-neutral-graph/materialization-plans/plan-0001.json"
    projection = {"candidate_id": "cand-1", "candidate_revision": 2,
                  "items": [{"client_item_id": "item-1"}],
                  "decision_bindings": [{"decision_id": "d1"}], "identity_bindings": []}
    payload = {"projection": projection}
    if len(batches) == 1:
        projection["client_batch_id"] = batches[0]
    else:
        payload["client_batch_ids"] = batches
    _write_json(source / ref, payload)
    saved = save_checkpoint(source, package, source_run_id="source", configuration=dict(CONFIGURATION))
    mappings = build_plan_mappings(_manifest_of(source, saved["checkpoint_id"]), source,
                                   {"completed_client_batches": completed})
    mapping = next(item for item in mappings if item["source_plan_ref"] == "plan-0001.json")
    assert mapping["status"] == expected
    assert mapping["client_item_ids"] == ["item-1"]
    assert mapping["candidate"] == {"candidate_id": "cand-1", "revision": 2}
    if expected == "completed_do_not_resubmit":
        with pytest.raises(CheckpointError) as error:
            check_resume_submission({"completed_client_batches": completed, "plan_mappings": mappings},
                                    {"client_batch_id": "replacement"}, plan_ref=ref)
        assert error.value.reason_code == "completed_operation_resubmission"
