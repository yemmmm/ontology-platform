"""R3.0-009 unified semantic graph contract tests.

Covers the versioned 009 artifact schemas (design §9.1), the approval
projection/digest rules (§9.2), the schema-dispatched intent/receipt
reconciliation, the unified read/receipt bind entry, and the Task parameter
dependency.  Every expected reason code is written independently here; 008B
defaults must stay byte-identical, which is why the 008B shapes are asserted
alongside the 009 ones.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modeling_team.contracts import (
    TeamConfigurationError,
    load_multi_slice_team_configuration,
    task_declares_multi_slice_workflow,
)
from modeling_team.protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_unified_entity_binding_receipt,
    validate_unified_entity_binding_receipt,
    validate_unified_entity_projection,
)
from modeling_team.staged_decisions import (
    APPROVALS_SCHEMA,
    DECISION_TARGET_KINDS,
    INTENT_FIELDS,
    RECEIPT_FIELDS,
    STAGE3_SLOT_SCHEMA,
    SUBMISSION_INTENT_SCHEMA,
    UNIFIED_APPROVALS_FIELDS,
    UNIFIED_CANDIDATE_ITEM_FIELDS,
    UNIFIED_INTENT_FIELDS,
    UNIFIED_MATERIALIZATION_PLAN_FIELDS,
    UNIFIED_RECEIPT_FIELDS,
    UNIFIED_STAGE3_SLOT_FIELDS,
    build_approval_projection,
    build_batch_projection,
    build_decision_binding,
    build_identity_binding,
    build_submission_intent,
    build_submission_receipt,
    candidate_item_digest,
    canonical_json_digest,
    load_materialization_plan_ref,
    normalize_class_iris,
    projection_digest,
    staged_decision_artifact_paths,
    staged_decision_directories,
    staged_intent_receipt_issues,
    unified_approval_issue,
    unified_candidate_issue,
    unified_graph_mode,
    unified_plan_issue,
    validate_materialization_plan,
    validate_unified_approvals,
    validate_unified_candidate,
    validate_unified_stage3_slot,
    write_submission_intent,
    write_submission_receipt,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _codes(issues) -> list[str]:
    return [issue.reason_code for issue in issues]


# --- fixtures ---------------------------------------------------------------


@pytest.fixture()
def candidate():
    return {
        "schema_version": "r3-0-009-unified-graph/v2",
        "scenario_id": "scenario-1",
        "candidate_id": "cand-1",
        "revision": 2,
        "items": [
            {
                "item_id": "item-entity",
                "item_kind": "entity",
                "business_meaning": "placeholder meaning",
                "value": {"label": "placeholder"},
                "relation_endpoints": None,
                "slice_ids": ["slice-1"],
                "shared_scope": None,
                "unknowns": [],
            },
            {
                "item_id": "item-relation",
                "item_kind": "relation",
                "business_meaning": "placeholder relation",
                "value": {"predicate": "relatedTo"},
                "relation_endpoints": {"from_item_id": "item-entity", "to_item_id": "item-entity"},
                "slice_ids": ["slice-1"],
                "shared_scope": "shared",
                "unknowns": [],
            },
        ],
        "explicit_unknowns": [],
    }


@pytest.fixture()
def projection(candidate):
    return build_approval_projection(
        task_id="r3-0-009-unified-graph-real",
        scenario_id=candidate["scenario_id"],
        session_id="session-1",
        client_batch_id="client-batch-1",
        ontology_id="ont-1",
        candidate_id=candidate["candidate_id"],
        candidate_revision=candidate["revision"],
        candidate_digest=canonical_json_digest(candidate["items"]),
        items=[
            {
                "client_item_id": "client-1",
                "command_kind": "create_entity",
                "payload": {"label": "placeholder", "class_iris": []},
            }
        ],
        decision_bindings=[
            build_decision_binding(
                command_index=0,
                client_item_id="client-1",
                candidate_item_ids=["item-entity"],
                candidate_revision=candidate["revision"],
                candidate_content_digests={"item-entity": candidate_item_digest(candidate["items"][0])},
                decision_ids=["decision-1"],
            )
        ],
        identity_bindings=[
            build_identity_binding(
                candidate_item_id="item-entity",
                resource_iri="http://example.test/entity/1",
                evidence_ref="read-evidence-1",
            )
        ],
    )


@pytest.fixture()
def plan(projection):
    return {
        "schema_version": "r3-0-009-materialization-plan/v2",
        "plan_id": "plan-1",
        "revision": 1,
        "projection": projection,
        "projection_digest": projection_digest(projection),
    }


@pytest.fixture()
def approvals(candidate):
    return {
        "schema_version": "r3-0-009-approvals/v2",
        "scenario_id": "scenario-1",
        "maintained_by": "coordinator",
        "entries": [],
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


# --- task parameter and directory preparation -------------------------------


def test_task_declares_unified_parameter_and_loads_with_multi_slice_profile():
    task_path = REPO_ROOT / "modeling_team/tasks/r3-0-009-unified-graph-real.yaml"
    profile_path = REPO_ROOT / "modeling_team/profiles/r3-0-002-modeling-team.yaml"
    assert task_declares_multi_slice_workflow(task_path) is True
    config = load_multi_slice_team_configuration(profile_path, task_path, root=REPO_ROOT)
    assert config.task.task_id == "r3-0-009-unified-graph-real"
    assert config.task.parameters == {
        "multi_slice_workflow": True,
        "staged_modeling_decisions": True,
        "unified_semantic_graph": True,
    }
    contract = json.loads(
        (REPO_ROOT / "modeling_team/references/r3-0-009-unified-graph-contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["schema_version"] == "r3-0-009-unified-graph-contract/v2"


def test_unified_parameter_requires_the_two_underlying_capabilities(tmp_path):
    import yaml

    task_path = REPO_ROOT / "modeling_team/tasks/r3-0-009-unified-graph-real.yaml"
    data = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    profile_path = REPO_ROOT / "modeling_team/profiles/r3-0-002-modeling-team.yaml"
    for parameters in (
        {"unified_semantic_graph": True},
        {"unified_semantic_graph": True, "multi_slice_workflow": True},
        {"unified_semantic_graph": True, "staged_modeling_decisions": True},
    ):
        data["parameters"] = parameters
        path = tmp_path / "task.yaml"
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        with pytest.raises(TeamConfigurationError) as excinfo:
            load_multi_slice_team_configuration(profile_path, path, root=REPO_ROOT)
        assert "requires" in str(excinfo.value)


def test_unified_mode_adds_only_the_two_neutral_graph_directories(tmp_path):
    legacy_dirs = staged_decision_directories(tmp_path)
    unified_dirs = staged_decision_directories(tmp_path, unified=True)
    assert staged_decision_directories(tmp_path, unified=False) == legacy_dirs
    added = [path for path in unified_dirs if path not in legacy_dirs]
    assert [path.relative_to(tmp_path).as_posix() for path in added] == [
        "stage3-neutral-graph/candidates",
        "stage3-neutral-graph/materialization-plans",
    ]
    legacy_paths = staged_decision_artifact_paths(tmp_path)
    unified_paths = staged_decision_artifact_paths(tmp_path, unified=True)
    assert set(unified_paths) - set(legacy_paths) == {"candidates_dir", "materialization_plans_dir"}
    assert set(legacy_paths).issubset(unified_paths)
    assert unified_graph_mode({"unified_semantic_graph": True}) is True
    assert unified_graph_mode({"unified_semantic_graph": False}) is False
    assert unified_graph_mode(None) is False


# --- closed schemas (design §9.1) -------------------------------------------


def test_s_closed_field_sets_match_design():
    assert UNIFIED_STAGE3_SLOT_FIELDS == {
        "schema_version",
        "scenario_id",
        "produced_by",
        "approved_by",
        "candidate_artifacts",
        "candidate_contract",
        "slot_note",
    }
    assert UNIFIED_CANDIDATE_ITEM_FIELDS == {
        "item_id",
        "item_kind",
        "business_meaning",
        "value",
        "relation_endpoints",
        "slice_ids",
        "shared_scope",
        "unknowns",
    }
    assert UNIFIED_INTENT_FIELDS - INTENT_FIELDS == {
        "plan_ref",
        "projection",
        "projection_digest",
        "decision_bindings",
    }
    assert UNIFIED_RECEIPT_FIELDS - RECEIPT_FIELDS == {
        "plan_ref",
        "projection_digest",
        "decision_bindings",
    }
    assert UNIFIED_MATERIALIZATION_PLAN_FIELDS == {
        "schema_version",
        "plan_id",
        "revision",
        "projection",
        "projection_digest",
    }
    assert "projection" not in UNIFIED_RECEIPT_FIELDS
    assert UNIFIED_APPROVALS_FIELDS - {"decisions", "translation_approvals"} == {
        "schema_version",
        "scenario_id",
        "maintained_by",
        "entries",
    }
    assert APPROVALS_SCHEMA == "r3-0-008b-approvals/v1"
    assert STAGE3_SLOT_SCHEMA == "r3-0-008b-stage3-slot/v1"


def test_s_valid_unified_artifacts_pass(candidate, projection, plan, approvals):
    slot = {
        "schema_version": "r3-0-009-stage3-slot/v1",
        "scenario_id": "scenario-1",
        "produced_by": "modeling",
        "approved_by": "coordinator",
        "candidate_artifacts": ["stage3-neutral-graph/candidates/cand-1-r2.json"],
        "candidate_contract": "r3-0-009-unified-graph/v2",
        "slot_note": "neutral slot",
    }
    assert validate_unified_stage3_slot(slot) == ()
    assert validate_unified_candidate(candidate) == ()
    assert validate_unified_approvals(approvals) == ()
    assert validate_materialization_plan(plan) == ()


def test_s_member_relation_is_an_approved_decision_target_kind(candidate, approvals):
    """D4: a member relation decision must pass the closed target-kind set and
    stay in sync with the published 009 contract JSON."""
    assert DECISION_TARGET_KINDS == (
        "commonality_node",
        "member_relation",
        "commonality_relation",
    )
    contract = json.loads(
        (REPO_ROOT / "modeling_team/references/r3-0-009-unified-graph-contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["approvals"]["decision_target_kinds"] == list(DECISION_TARGET_KINDS)

    member_decision = dict(approvals["decisions"][0])
    member_decision["decision_id"] = "decision-member"
    member_decision["target_kind"] = "member_relation"
    member_decision["target_id"] = "item-relation"
    member_decision["content_digest"] = candidate_item_digest(candidate["items"][1])
    member_approvals = dict(approvals)
    member_approvals["decisions"] = [*approvals["decisions"], member_decision]

    assert validate_unified_approvals(member_approvals) == ()


def test_b_unified_artifact_schema_drift_is_typed(candidate, projection, plan, approvals):
    slot = {
        "schema_version": "r3-0-009-stage3-slot/v1",
        "scenario_id": "scenario-1",
        "produced_by": "modeling",
        "approved_by": "coordinator",
        "candidate_artifacts": ["candidates/cand-1-r2.json"],
        "deferred_contract": "r3-0-008b-stage3-deferred/v1",
        "slot_note": None,
    }
    assert _codes(validate_unified_stage3_slot(slot)) == ["unified_schema_mismatch"]
    assert _codes(validate_unified_stage3_slot({**slot, "schema_version": STAGE3_SLOT_SCHEMA})) == [
        "unified_schema_mismatch"
    ]

    drifted_candidate = {**candidate, "extra": 1}
    assert _codes(validate_unified_candidate(drifted_candidate)) == ["unified_schema_mismatch"]
    assert _codes(validate_unified_candidate({**candidate, "items": []})) == [
        "missing_candidate_reference"
    ]
    assert _codes(
        validate_unified_candidate({**candidate, "items": [{**candidate["items"][0], "item_kind": "ontology"}]})
    ) == ["unified_schema_mismatch"]
    assert _codes(
        validate_unified_candidate(
            {**candidate, "items": [candidate["items"][0], dict(candidate["items"][0])]}
        )
    ) == ["missing_candidate_reference"]

    assert _codes(validate_unified_approvals({**approvals, "extra": 1})) == ["unified_schema_mismatch"]
    relation_decision = {
        **approvals["decisions"][0],
        "decision_id": "decision-2",
        "target_kind": "commonality_relation",
        "scope": None,
    }
    assert _codes(validate_unified_approvals({**approvals, "decisions": [relation_decision]})) == [
        "relation_scope_ambiguous"
    ]
    scoped_relation = {**relation_decision, "scope": {"slice_ids": ["slice-1"]}}
    assert validate_unified_approvals({**approvals, "decisions": [scoped_relation]}) == ()
    node_with_scope = {**approvals["decisions"][0], "scope": {"slice_ids": ["slice-1"]}}
    assert _codes(validate_unified_approvals({**approvals, "decisions": [node_with_scope]})) == [
        "relation_scope_ambiguous"
    ]
    obsolete_evidence = {**approvals["decisions"][0], "evidence_refs": []}
    assert _codes(validate_unified_approvals({**approvals, "decisions": [obsolete_evidence]})) == [
        "unified_schema_mismatch"
    ]
    no_digest = {**approvals["decisions"][0], "content_digest": ""}
    assert _codes(validate_unified_approvals({**approvals, "decisions": [no_digest]})) == [
        "approval_content_mismatch"
    ]
    wrong_translation = {
        **approvals["translation_approvals"][0],
        "decision": "deferred",
        "projection_digest": "",
    }
    # R3.0-014 (M28): rejected or format-drifted translation entries are
    # history, not file-wide gate failures — only the list shape is checked
    # here; the apply-time exact-key match lives in unified_translation_issue.
    assert validate_unified_approvals(
        {**approvals, "translation_approvals": [wrong_translation]}
    ) == ()
    assert _codes(
        validate_unified_approvals({**approvals, "translation_approvals": "nope"})
    ) == ["unified_schema_mismatch"]

    assert _codes(validate_materialization_plan({**plan, "projection_digest": "sha256:0"})) == [
        "approval_content_mismatch"
    ]
    assert _codes(validate_materialization_plan({**plan, "revision": 0})) == ["approval_stale"]
    assert _codes(validate_materialization_plan({**plan, "extra": 1})) == ["unified_schema_mismatch"]


# --- digest conventions (design §9.2) ---------------------------------------


def test_digest_rules_are_canonical_and_order_insensitive_for_class_iris():
    assert canonical_json_digest({"b": 1, "a": 2}) == canonical_json_digest({"a": 2, "b": 1})
    assert canonical_json_digest({}).startswith("sha256:")
    assert normalize_class_iris([]) == []
    assert normalize_class_iris(None) == []
    assert normalize_class_iris(["http://example.test/c/B", "http://example.test/c/A"]) == [
        "http://example.test/c/A",
        "http://example.test/c/B",
    ]
    assert normalize_class_iris(
        ["http://example.test/c/A", "http://example.test/c/A", "http://example.test/c/B"]
    ) == ["http://example.test/c/A", "http://example.test/c/B"]
    # legacy scalar ids are expanded by the backend; the helper only closes sets
    assert normalize_class_iris(["legacy-id", ""]) == ["legacy-id"]


def test_projection_omits_execution_parameters_and_defaults_items(projection):
    assert set(projection) == {
        "task_id",
        "contract_version",
        "scenario_id",
        "session_id",
        "client_batch_id",
        "ontology_id",
        "candidate_id",
        "candidate_revision",
        "candidate_digest",
        "items",
        "decision_bindings",
        "identity_bindings",
    }
    assert projection["items"][0] == {
        "client_item_id": "client-1",
        "command_kind": "create_entity",
        "payload": {"label": "placeholder", "class_iris": []},
        "depends_on": [],
        "rationale": None,
        "competency_question_ids": [],
    }
    with pytest.raises(Exception) as excinfo:
        build_approval_projection(
            task_id="t",
            scenario_id="s",
            session_id="sess",
            client_batch_id="cb",
            ontology_id="o",
            candidate_id="c",
            candidate_revision=1,
            candidate_digest="sha256:0",
            items=[{"client_item_id": "x", "command_kind": "create_entity", "payload": {}, "extra": 1}],
            decision_bindings=[],
            identity_bindings=[],
        )
    assert "unexpected fields" in str(excinfo.value)


def test_identity_binding_requires_exactly_one_locator():
    with pytest.raises(Exception):
        build_identity_binding(candidate_item_id="item-1")
    with pytest.raises(Exception):
        build_identity_binding(
            candidate_item_id="item-1",
            resource_iri="http://example.test/e",
            receipt_ref="receipt-1",
            evidence_ref="ev",
        )
    existing = build_identity_binding(
        candidate_item_id="item-1",
        resource_iri="http://example.test/e",
        evidence_ref="ev",
    )
    assert existing == {
        "candidate_item_id": "item-1",
        "resource_iri": "http://example.test/e",
        "receipt_ref": None,
        "evidence_ref": "ev",
    }
    future = build_identity_binding(candidate_item_id="item-1", receipt_ref="receipt-1")
    assert future["resource_iri"] is None and future["evidence_ref"] is None


# --- §9.2 comparison at receipt time ----------------------------------------


def test_matching_batch_projection_is_accepted(candidate, projection, plan):
    batch = {
        "session_id": projection["session_id"],
        "client_batch_id": projection["client_batch_id"],
        "ontology_id": projection["ontology_id"],
        "mode": "apply_atomic",
        "idempotency_key": "key-1",
        "expected_model_revision": 1,
        "items": projection["items"],
    }
    assert unified_plan_issue(plan=plan, batch=batch, task_id=projection["task_id"]) is None
    rebuilt = build_batch_projection(
        task_id=projection["task_id"],
        batch=batch,
        scenario_id=projection["scenario_id"],
        candidate_id=projection["candidate_id"],
        candidate_revision=projection["candidate_revision"],
        candidate_digest=projection["candidate_digest"],
        decision_bindings=projection["decision_bindings"],
        identity_bindings=projection["identity_bindings"],
    )
    assert rebuilt == projection


def test_payload_drift_is_rejected_even_with_a_correct_self_reported_digest(plan, projection):
    batch = {
        "session_id": projection["session_id"],
        "client_batch_id": projection["client_batch_id"],
        "ontology_id": projection["ontology_id"],
        "items": [{**projection["items"][0], "payload": {"label": "changed", "class_iris": []}}],
    }
    issue = unified_plan_issue(plan=plan, batch=batch, task_id=projection["task_id"])
    assert _codes([issue]) == ["approval_content_mismatch"]


def test_candidate_revision_and_approval_closures(tmp_path, candidate, projection, plan, approvals):
    run_root = tmp_path
    candidates_dir = run_root / "stage3-neutral-graph" / "candidates"
    candidates_dir.mkdir(parents=True)
    (candidates_dir / "cand-1-r2.json").write_text(
        json.dumps(candidate, ensure_ascii=False), encoding="utf-8"
    )
    assert unified_candidate_issue(run_root, projection) is None

    stale_projection = {**projection, "candidate_revision": 3}
    assert _codes([unified_candidate_issue(run_root, stale_projection)]) == ["approval_stale"]

    other_candidate = {**candidate, "items": [candidate["items"][1], candidate["items"][0]]}
    (candidates_dir / "cand-1-r2.json").write_text(
        json.dumps(other_candidate, ensure_ascii=False), encoding="utf-8"
    )
    assert _codes([unified_candidate_issue(run_root, projection)]) == ["approval_content_mismatch"]
    (candidates_dir / "cand-1-r2.json").write_text(
        json.dumps(candidate, ensure_ascii=False), encoding="utf-8"
    )

    altered_digest = {
        **projection,
        "decision_bindings": [
            {
                **projection["decision_bindings"][0],
                "candidate_content_digests": {"item-entity": "sha256:" + "1" * 64},
            }
        ],
    }
    assert _codes([unified_candidate_issue(run_root, altered_digest)]) == ["approval_content_mismatch"]

    missing_item_projection = {
        **projection,
        "decision_bindings": [
            {
                **projection["decision_bindings"][0],
                "candidate_content_digests": {"item-missing": candidate_item_digest(candidate["items"][0])},
            }
        ],
    }
    assert _codes([unified_candidate_issue(run_root, missing_item_projection)]) == [
        "approval_content_mismatch"
    ]

    approvals["decisions"][0]["content_digest"] = candidate_item_digest(candidate["items"][0])
    assert unified_approval_issue(approvals, projection) is None
    rejected = {**approvals, "decisions": [{**approvals["decisions"][0], "decision": "rejected"}]}
    assert _codes([unified_approval_issue(rejected, projection)]) == ["approval_missing"]
    other_candidate_decision = {
        **approvals["decisions"][0],
        "candidate_id": "cand-9",
    }
    assert _codes(
        [unified_approval_issue({**approvals, "decisions": [other_candidate_decision]}, projection)]
    ) == ["approval_missing"]
    stale_revision = {**approvals["decisions"][0], "content_revision": 1}
    assert _codes(
        [unified_approval_issue({**approvals, "decisions": [stale_revision]}, projection)]
    ) == ["approval_stale"]
    wrong_content = {**approvals["decisions"][0], "content_digest": "sha256:" + "2" * 64}
    assert _codes(
        [unified_approval_issue({**approvals, "decisions": [wrong_content]}, projection)]
    ) == ["approval_content_mismatch"]
    unknown_decision = {
        **approvals,
        "decisions": [{**approvals["decisions"][0], "decision_id": "decision-9"}],
    }
    assert _codes([unified_approval_issue(unknown_decision, projection)]) == ["approval_missing"]
    assert _codes([unified_approval_issue({}, projection)]) == ["unified_schema_mismatch"]


def test_plan_ref_must_live_in_the_published_directory(tmp_path, plan):
    plans_dir = tmp_path / "stage3-neutral-graph" / "materialization-plans"
    plans_dir.mkdir(parents=True)
    ref = "stage3-neutral-graph/materialization-plans/plan-1-r1.json"
    (plans_dir / "plan-1-r1.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    loaded, issue = load_materialization_plan_ref(tmp_path, ref)
    assert issue is None and loaded["plan_id"] == "plan-1"

    assert _codes([load_materialization_plan_ref(tmp_path, "../plan-1-r1.json")[1]]) == [
        "missing_candidate_reference"
    ]
    assert _codes([load_materialization_plan_ref(tmp_path, "value-semantics/plan.json")[1]]) == [
        "missing_candidate_reference"
    ]
    assert _codes([load_materialization_plan_ref(tmp_path, None)[1]]) == ["missing_candidate_reference"]
    (plans_dir / "plan-1-r1.json").unlink()
    assert _codes([load_materialization_plan_ref(tmp_path, ref)[1]]) == ["missing_candidate_reference"]
    (plans_dir / "plan-1-r1.json").write_text("{not json", encoding="utf-8")
    assert _codes([load_materialization_plan_ref(tmp_path, ref)[1]]) == ["missing_candidate_reference"]


# --- intent/receipt dispatch and reconciliation ------------------------------


def _write_run(run_root, intent, receipt, *, plan_ref="stage3-neutral-graph/materialization-plans/plan-1-r1.json", digest="sha256:" + "0" * 64):
    write_submission_intent(run_root, intent)
    write_submission_receipt(run_root, receipt)
    return intent, receipt


def test_legacy_intent_and_receipt_stay_on_the_old_contract(tmp_path):
    intent = build_submission_intent(
        1,
        idempotency_key="key-1",
        client_batch_id="cb",
        session_id="s",
        mode="dry_run",
        commands=[],
        value_traces=[],
        l3_nodes=[],
    )
    assert intent["schema_version"] == SUBMISSION_INTENT_SCHEMA
    assert set(intent) == set(INTENT_FIELDS)
    receipt = build_submission_receipt(1, intent, batch_id="b-1", response_digest="sha256:r")
    assert receipt["schema_version"] == "r3-0-008b-submission-receipt/v1"
    assert set(receipt) == set(RECEIPT_FIELDS)
    _write_run(tmp_path, intent, receipt)
    assert staged_intent_receipt_issues(tmp_path) == ()


def test_unified_intent_and_receipt_round_trip(tmp_path, projection):
    intent = build_submission_intent(
        1,
        idempotency_key="key-1",
        client_batch_id="cb",
        session_id="s",
        mode="apply_atomic",
        commands=[],
        value_traces=[],
        l3_nodes=[],
        plan_ref="stage3-neutral-graph/materialization-plans/plan-1-r1.json",
        projection=projection,
        decision_bindings=projection["decision_bindings"],
    )
    assert intent["schema_version"] == "r3-0-009-submission-intent/v1"
    assert intent["projection_digest"] == projection_digest(projection)
    receipt = build_submission_receipt(1, intent, batch_id="b-1", response_digest="sha256:r")
    assert receipt["schema_version"] == "r3-0-009-submission-receipt/v1"
    assert receipt["projection_digest"] == intent["projection_digest"]
    assert receipt["plan_ref"] == intent["plan_ref"]
    assert receipt["decision_bindings"] == intent["decision_bindings"]
    assert "projection" not in receipt
    _write_run(tmp_path, intent, receipt)
    assert staged_intent_receipt_issues(tmp_path) == ()


def test_intent_and_receipt_bindings_are_kill_switch_triggers(tmp_path, projection):
    intent = build_submission_intent(
        1,
        idempotency_key="key-1",
        client_batch_id="cb",
        session_id="s",
        mode="apply_atomic",
        commands=[],
        value_traces=[],
        l3_nodes=[],
        plan_ref="stage3-neutral-graph/materialization-plans/plan-1-r1.json",
        projection=projection,
        decision_bindings=projection["decision_bindings"],
    )
    receipt = build_submission_receipt(1, intent, batch_id="b-1", response_digest="sha256:r")

    no_bindings_intent = {**intent, "decision_bindings": []}
    _write_run(tmp_path, no_bindings_intent, receipt)
    assert _codes(staged_intent_receipt_issues(tmp_path)) == ["missing_candidate_reference"]

    for path in (tmp_path / "value-semantics" / "submission-intents").iterdir():
        path.unlink()
    for path in (tmp_path / "value-semantics" / "submission-receipts").iterdir():
        path.unlink()

    drifted_intent = {**intent, "projection_digest": "sha256:" + "3" * 64}
    _write_run(tmp_path, drifted_intent, receipt)
    # the intent digest mismatch and the receipt/intent drift both report
    assert set(_codes(staged_intent_receipt_issues(tmp_path))) == {"approval_content_mismatch"}
    for path in (tmp_path / "value-semantics" / "submission-intents").iterdir():
        path.unlink()
    for path in (tmp_path / "value-semantics" / "submission-receipts").iterdir():
        path.unlink()

    drifted_receipt = {**receipt, "projection_digest": "sha256:" + "4" * 64}
    _write_run(tmp_path, intent, drifted_receipt)
    assert _codes(staged_intent_receipt_issues(tmp_path)) == ["approval_content_mismatch"]
    for path in (tmp_path / "value-semantics" / "submission-intents").iterdir():
        path.unlink()
    for path in (tmp_path / "value-semantics" / "submission-receipts").iterdir():
        path.unlink()

    legacy_receipt_for_unified_intent = {
        **receipt,
        "schema_version": "r3-0-008b-submission-receipt/v1",
    }
    for field in ("plan_ref", "projection_digest", "decision_bindings"):
        legacy_receipt_for_unified_intent.pop(field, None)
    _write_run(tmp_path, intent, legacy_receipt_for_unified_intent)
    assert _codes(staged_intent_receipt_issues(tmp_path)) == ["unified_schema_mismatch"]
    for path in (tmp_path / "value-semantics" / "submission-intents").iterdir():
        path.unlink()
    for path in (tmp_path / "value-semantics" / "submission-receipts").iterdir():
        path.unlink()

    unknown_schema = {**intent, "schema_version": "r3-0-009-submission-intent/v2"}
    _write_run(tmp_path, unknown_schema, receipt)
    # the unknown intent schema and its 009 receipt binding both report
    assert set(_codes(staged_intent_receipt_issues(tmp_path))) == {
        "approval_content_mismatch",
        "unified_schema_mismatch",
    }


def test_partial_009_intent_arguments_are_rejected():
    with pytest.raises(Exception):
        build_submission_intent(
            1,
            idempotency_key="k",
            client_batch_id="cb",
            session_id="s",
            mode="apply_atomic",
            commands=[],
            value_traces=[],
            l3_nodes=[],
            plan_ref="stage3-neutral-graph/materialization-plans/plan-1-r1.json",
        )
    with pytest.raises(Exception):
        build_submission_intent(
            1,
            idempotency_key="k",
            client_batch_id="cb",
            session_id="s",
            mode="apply_atomic",
            commands=[],
            value_traces=[],
            l3_nodes=[],
            projection={"task_id": "t"},
        )


# --- 009 read/receipt bind entry --------------------------------------------


def _candidate_for(refs):
    return {
        "candidate_kind": "platform-neutral-candidate-v3",
        "candidate_id": "cand-1",
        "candidate_revision": 1,
        "scope": {"ontology_id": "ont-1"},
        "constraints": ["no-business-rows"],
        "items": [
            {
                "item_id": f"item-{index}",
                "item_kind": "existing_entity_ref",
                "semantic": {"semantic_id": semantic_id, "expected_class": expected_class},
            }
            for index, (semantic_id, expected_class) in enumerate(refs, start=1)
        ],
    }


def _row(semantic_id, iri, class_semantic_id, class_iri, *, project="proj-1", ontology="ont-1", version=1):
    return {
        "semantic_id": semantic_id,
        "entity_iri": iri,
        "class_semantic_id": class_semantic_id,
        "class_iri": class_iri,
        "project_id": project,
        "ontology_id": ontology,
        "model_revision": version,
        "read_evidence": {"receipt": f"receipt-{semantic_id}"},
    }


def test_zero_class_ref_binds_only_a_genuinely_unclassified_row():
    candidate = _candidate_for([("ent-zero", None)])
    receipt = build_unified_entity_binding_receipt(
        candidate,
        [_row("ent-zero", "http://example.test/e/0", None, None)],
        project_id="proj-1",
        ontology_id="ont-1",
        model_revision=1,
    )
    assert receipt["schema_version"] == "r3-0-009-existing-entity-binding/v1"
    assert receipt["bindings"][0]["class_state"] == "unclassified"
    assert receipt["bindings"][0]["expected_class"] is None
    assert validate_unified_entity_binding_receipt(
        candidate, receipt, project_id="proj-1", ontology_id="ont-1", model_revision=1
    ) == receipt


def test_classified_and_incomplete_rows_are_bound_by_state():
    candidate = _candidate_for([("ent-full", "EntFull")])
    receipt = build_unified_entity_binding_receipt(
        candidate,
        [_row("ent-full", "http://example.test/e/2", "EntFull", "http://example.test/class/EntFull")],
        project_id="proj-1",
        ontology_id="ont-1",
        model_revision=1,
    )
    assert receipt["bindings"][0]["class_state"] == "classified"
    assert validate_unified_entity_binding_receipt(candidate, receipt) == receipt


def test_incomplete_class_identity_is_reported_and_never_proves_a_class():
    incomplete_row = _row("ent-inc", "http://example.test/e/1", None, "http://example.test/class/K")
    with pytest.raises(ProtocolRetrievalFallbackError):
        build_unified_entity_binding_receipt(
            _candidate_for([("ent-inc", None)]),
            [incomplete_row],
            project_id="proj-1",
            ontology_id="ont-1",
            model_revision=1,
        )
    with pytest.raises(ProtocolRetrievalFallbackError):
        build_unified_entity_binding_receipt(
            _candidate_for([("ent-inc", "K")]),
            [incomplete_row],
            project_id="proj-1",
            ontology_id="ont-1",
            model_revision=1,
        )


def test_zero_class_ref_rejects_a_row_that_still_carries_class_identity():
    candidate = _candidate_for([("ent-zero", None)])
    with pytest.raises(ProtocolRetrievalFallbackError) as excinfo:
        build_unified_entity_binding_receipt(
            candidate,
            [_row("ent-zero", "http://example.test/e/0", "K", "http://example.test/class/K")],
            project_id="proj-1",
            ontology_id="ont-1",
            model_revision=1,
        )
    assert "Class identity" in str(excinfo.value)


def test_projection_validator_states_and_drift():
    base = _row("ent-zero", "http://example.test/e/0", None, None)
    assert validate_unified_entity_projection(
        base, project_id="proj-1", ontology_id="ont-1", model_revision=1
    )["class_iri"] is None
    with pytest.raises(ValueError):
        validate_unified_entity_projection(
            {**base, "class_semantic_id": "K"},
            project_id="proj-1",
            ontology_id="ont-1",
            model_revision=1,
        )
    with pytest.raises(ValueError):
        validate_unified_entity_projection(
            {**base, "model_revision": 2},
            project_id="proj-1",
            ontology_id="ont-1",
            model_revision=1,
        )
    with pytest.raises(ValueError):
        validate_unified_entity_projection(
            {key: value for key, value in base.items() if key != "class_iri"},
            project_id="proj-1",
            ontology_id="ont-1",
            model_revision=1,
        )


def test_binding_receipt_rejects_digest_and_state_drift():
    candidate = _candidate_for([("ent-zero", None), ("ent-full", "EntFull")])
    rows = [
        _row("ent-zero", "http://example.test/e/0", None, None),
        _row("ent-full", "http://example.test/e/2", "EntFull", "http://example.test/class/EntFull"),
    ]
    receipt = build_unified_entity_binding_receipt(
        candidate, rows, project_id="proj-1", ontology_id="ont-1", model_revision=1
    )
    body = dict(receipt)
    body.pop("receipt_digest")
    tampered = {**body, "receipt_digest": "0" * 64}
    with pytest.raises(ProtocolRetrievalFallbackError):
        validate_unified_entity_binding_receipt(candidate, tampered)
    state_drift = {
        **body,
        "bindings": [
            {**binding, "class_state": "classified"}
            if binding["semantic_id"] == "ent-zero"
            else binding
            for binding in receipt["bindings"]
        ],
        "receipt_digest": receipt["receipt_digest"],
    }
    with pytest.raises(ProtocolRetrievalFallbackError):
        validate_unified_entity_binding_receipt(candidate, state_drift)
    dropped = {**body, "bindings": [receipt["bindings"][0]], "receipt_digest": receipt["receipt_digest"]}
    with pytest.raises(ProtocolRetrievalFallbackError):
        validate_unified_entity_binding_receipt(candidate, dropped)


def test_unified_candidate_rejects_legacy_trace_field_and_schema(candidate):
    obsolete = {**candidate, "items": [{**candidate["items"][0], "evidence_refs": []}]}
    assert _codes(validate_unified_candidate(obsolete)) == ["unified_schema_mismatch"]
    assert _codes(validate_unified_candidate({**candidate, "schema_version": "r3-0-009-unified-graph/v1"})) == ["unified_schema_mismatch"]
