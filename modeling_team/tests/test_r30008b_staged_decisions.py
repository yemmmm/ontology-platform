"""R3.0-008B staged-decision artifact contract tests (test plan S1/S2/S5-S8/S10, B1/B2/B8/B11/B12).

Every expected reason code, receipt field, and digest expectation in this file is
written independently by the test author; nothing is imported from the
implementation's reason-code tables.  Fixtures use the ``example.test`` /
placeholder-* namespace only.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from modeling_team.staged_decisions import (
    StagedDecisionArtifactError,
    adjudicate_unknown_intent,
    build_submission_intent,
    build_submission_receipt,
    canonical_command_digest,
    check_stage3_candidate_artifacts,
    cross_validate_approvals,
    load_analysis_conclusions,
    load_approvals,
    load_joint_acceptance_checklist,
    load_materialization_unlock,
    mark_intent_status,
    reconcile_platform_batches,
    staged_decision_artifact_paths,
    staged_stage3_issue,
    validate_analysis_conclusions,
    validate_approvals,
    validate_joint_acceptance_checklist,
    validate_materialization_ledger,
    validate_materialization_unlock,
    validate_stage3_slot,
    validate_staged_submission,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

CHECKLIST_ITEMS = [
    "business_semantics_recall",
    "commonality_recall",
    "cross_slice_cross_ontology_recall",
    "value_semantics_recall",
    "sql_mapping_chain",
    "r30008a_representative_question_recheck",
    "rdf_no_business_rows",
]


def _codes(issues) -> list[str]:
    return [issue.reason_code for issue in issues]


def _conclusion_entry(**overrides) -> dict:
    entry = {
        "conclusion_id": "ac-0001",
        "mapped_property": "https://example.test/prop/placeholder-status",
        "candidate_value": "placeholder-alpha",
        "business_meaning_hypothesis": "placeholder hypothesis",
        "proposed_level": "L2",
        "blocking_unknowns": None,
        "status": "analyzed",
        "confirmed_enum_value": None,
        "confirmed_level": None,
        "confirmed_by": None,
        "conflict_note": None,
        "revision": 1,
    }
    entry.update(overrides)
    return entry


def _conclusions(entries, **overrides) -> dict:
    artifact = {
        "schema_version": "r3-0-008b-analysis-conclusions/v2",
        "scenario_id": "placeholder-scenario",
        "maintained_by": "modeling",
        "entries": entries,
    }
    artifact.update(overrides)
    return artifact


def _confirmed_entry(**overrides) -> dict:
    entry = _conclusion_entry(
        status="confirmed",
        confirmed_enum_value="placeholder-alpha",
        confirmed_level="L2",
        confirmed_by="coordinator",
        revision=2,
    )
    entry.update(overrides)
    return entry


def _materialize_unlock() -> dict:
    return {
        "schema_version": "r3-0-008b-materialization-unlock/v1",
        "scenario_id": "placeholder-scenario",
        "unlocked_by": "coordinator",
        "mode": "materialize",
        "mapping_sources": [
            {"source_type": "database_schema", "reference": "placeholder.table"}
        ],
        "confirmed_codes": [
            {
                "conclusion_id": "ac-0001",
                "mapped_property": "https://example.test/prop/placeholder-status",
                "confirmed_enum_value": "placeholder-alpha",
                "confirmed_level": "L2",
            }
        ],
        "skip_reason": None,
    }


# --- S1: conclusions contract -------------------------------------------------


def test_s1_valid_conclusions_with_archive_chain_passes():
    conclusions = _conclusions([_confirmed_entry()])
    archive = {"ac-0001": [_conclusion_entry(status="analyzed", revision=1)]}
    assert validate_analysis_conclusions(conclusions, archive=archive) == ()


def test_s1_empty_entries_is_legal():
    assert validate_analysis_conclusions(_conclusions([])) == ()


def test_s7_revision_chain_and_legal_transitions():
    # ac-0001 revision 2 replaces revision 1 (analyzed -> confirmed).
    conclusions = _conclusions([_confirmed_entry()])
    archive = {"ac-0001": [_conclusion_entry(status="analyzed", revision=1)]}
    assert validate_analysis_conclusions(conclusions, archive=archive) == ()
    # conflict -> analyzed with revision+1 and confirmed_* cleared is legal.
    resolved = _conclusions(
        [
            _conclusion_entry(
                revision=3,
            )
        ]
    )
    archive = {
        "ac-0001": [
            _conclusion_entry(status="analyzed", revision=1),
            _conclusion_entry(
                status="conflict", conflict_note="placeholder contradiction", revision=2
            ),
        ]
    }
    assert validate_analysis_conclusions(resolved, archive=archive) == ()


def test_b1_status_field_violations_are_typed():
    analyzed_with_value = _conclusions([_conclusion_entry(confirmed_enum_value="x")])
    assert _codes(validate_analysis_conclusions(analyzed_with_value)) == [
        "conclusions_invalid_status_fields"
    ]
    confirmed_without_by = _conclusions(
        [_conclusion_entry(status="confirmed", confirmed_enum_value="x")]
    )
    assert _codes(validate_analysis_conclusions(confirmed_without_by)) == [
        "conclusions_invalid_status_fields"
    ]
    conflict_without_note = _conclusions([_conclusion_entry(status="conflict")])
    assert _codes(validate_analysis_conclusions(conflict_without_note)) == [
        "conclusions_invalid_status_fields"
    ]


def test_b1_illegal_transitions_and_revision_regressions():
    # analyzed -> materialized (revision 2 after archived analyzed revision 1).
    conclusions = _conclusions(
        [
            _conclusion_entry(
                status="materialized",
                confirmed_enum_value="x",
                confirmed_by="coordinator",
                revision=2,
            )
        ]
    )
    archive = {"ac-0001": [_conclusion_entry(status="analyzed", revision=1)]}
    codes = _codes(
        validate_analysis_conclusions(
            conclusions, archive=archive, ledger_entries=[{"conclusion_id": "ac-0001"}]
        )
    )
    assert "conclusions_illegal_transition" in codes
    # materialized -> analyzed.
    conclusions = _conclusions([_conclusion_entry(revision=3)])
    archive = {
        "ac-0001": [
            _conclusion_entry(status="analyzed", revision=1),
            _conclusion_entry(
                status="materialized",
                confirmed_enum_value="x",
                confirmed_by="coordinator",
                revision=2,
            ),
        ]
    }
    assert "conclusions_illegal_transition" in _codes(
        validate_analysis_conclusions(conclusions, archive=archive)
    )
    # revision regression: current revision 1 while an archive exists.
    conclusions = _conclusions([_confirmed_entry(revision=1)])
    archive = {"ac-0001": [_conclusion_entry(status="analyzed", revision=5)]}
    assert "conclusions_revision_regression" in _codes(
        validate_analysis_conclusions(conclusions, archive=archive)
    )
    # revision skip: current revision 5 after archived highest 1.
    conclusions = _conclusions([_confirmed_entry(revision=5)])
    archive = {"ac-0001": [_conclusion_entry(status="analyzed", revision=1)]}
    assert "conclusions_revision_regression" in _codes(
        validate_analysis_conclusions(conclusions, archive=archive)
    )


def test_b1_materialized_requires_ledger_entry():
    conclusions = _conclusions(
        [
            _conclusion_entry(
                status="materialized",
                confirmed_enum_value="x",
                confirmed_by="coordinator",
                revision=2,
            )
        ]
    )
    archive = {
        "ac-0001": [
            _conclusion_entry(
                status="confirmed", confirmed_enum_value="x", confirmed_by="coordinator", revision=1
            )
        ]
    }
    assert "conclusions_materialized_without_ledger" in _codes(
        validate_analysis_conclusions(conclusions, archive=archive)
    )


def test_b1_unparsable_and_symlink_rejected(tmp_path):
    path = tmp_path / "analysis-conclusions.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(Exception, match="conclusions_unparsable"):
        load_analysis_conclusions(path)
    linked = tmp_path / "linked.json"
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    linked.symlink_to(target)
    with pytest.raises(Exception, match="conclusions_unparsable"):
        load_analysis_conclusions(linked)


# --- S2 / B2: materialization unlock ------------------------------------------


def test_s2_materialize_and_skip_unlock_shapes_pass():
    conclusions = _conclusions([_confirmed_entry()])
    assert validate_materialization_unlock(_materialize_unlock(), conclusions=conclusions) == ()
    skip = {
        "schema_version": "r3-0-008b-materialization-unlock/v1",
        "scenario_id": "placeholder-scenario",
        "unlocked_by": "coordinator",
        "mode": "skip",
        "mapping_sources": None,
        "confirmed_codes": None,
        "skip_reason": "no_schema_no_interface",
    }
    # Skip mode is only consistent while no conclusion is confirmed yet.
    assert validate_materialization_unlock(skip, conclusions=_conclusions([_conclusion_entry()])) == ()
    assert validate_materialization_unlock(skip, conclusions=None) == ()


def test_b2_unlock_violations_are_typed():
    conclusions = _conclusions([_confirmed_entry()])
    drifted = _materialize_unlock()
    drifted["confirmed_codes"][0]["confirmed_enum_value"] = "placeholder-other"
    assert _codes(validate_materialization_unlock(drifted, conclusions=conclusions)) == [
        "unlock_code_mismatch"
    ]
    dangling = _materialize_unlock()
    dangling["confirmed_codes"][0]["conclusion_id"] = "ac-9999"
    assert _codes(validate_materialization_unlock(dangling, conclusions=conclusions)) == [
        "unlock_dangling_conclusion"
    ]
    inconsistent = _materialize_unlock()
    inconsistent["mode"] = "skip"
    assert "unlock_skip_inconsistent" in _codes(
        validate_materialization_unlock(inconsistent, conclusions=conclusions)
    )
    wrong_reason = _materialize_unlock()
    wrong_reason["mode"] = "skip"
    wrong_reason["confirmed_codes"] = None
    wrong_reason["mapping_sources"] = None
    wrong_reason["skip_reason"] = "placeholder-wrong"
    assert set(_codes(validate_materialization_unlock(wrong_reason, conclusions=conclusions))) == {
        "unlock_skip_inconsistent"
    }


# --- S5: materialization trace chain closure ----------------------------------


def _receipt(*, ordinal=1, mode="apply_atomic") -> dict:
    intent = build_submission_intent(
        ordinal,
        idempotency_key="placeholder-key-1",
        client_batch_id="placeholder-batch-1",
        session_id="placeholder-session",
        mode=mode,
        commands=[
            {
                "command_kind": "create_enum_meaning",
                "payload": {
                    "enum_meaning_id": "placeholder-enum-1",
                    "property_iri": "https://example.test/prop/placeholder-status",
                    "enum_value": "placeholder-alpha",
                    "semantic_value": "https://example.test/value/placeholder-alpha",
                },
            }
        ],
        value_traces=[
            {
                "command_index": 0,
                "conclusion_id": "ac-0001",
                "mapped_property": "https://example.test/prop/placeholder-status",
                "enum_target": "placeholder-enum-1",
            }
        ],
        l3_nodes=[],
    )
    return build_submission_receipt(
        ordinal,
        intent,
        batch_id="placeholder-batch-1",
        response_digest="sha256:" + "0" * 64,
    )


def test_s5_receipt_ledger_and_reconciliation_close():
    receipt = _receipt()
    ledger = {
        "schema_version": "r3-0-008b-materialization-ledger/v1",
        "scenario_id": "placeholder-scenario",
        "maintained_by": "protocol",
        "entries": [
            {
                "conclusion_id": "ac-0001",
                "receipt_ordinal": 1,
                "batch_id": "placeholder-batch-1",
                "command_digest": receipt["commands"][0],
                "semantic_value_iri": "https://example.test/value/placeholder-alpha",
            }
        ],
    }
    assert validate_materialization_ledger(ledger, receipts=[receipt]) == ()
    intents = [
        {
            "ordinal": 1,
            "idempotency_key": "placeholder-key-1",
            "status": "receipted",
        }
    ]
    listing = [{"batch_id": "placeholder-batch-1", "idempotency_key": "placeholder-key-1"}]
    assert reconcile_platform_batches(listing, intents, [receipt]) == ()


def test_b7_ledger_drift_and_reconciliation_violations():
    receipt = _receipt()
    ledger = {
        "schema_version": "r3-0-008b-materialization-ledger/v1",
        "scenario_id": "placeholder-scenario",
        "maintained_by": "protocol",
        "entries": [
            {
                "conclusion_id": "ac-0001",
                "receipt_ordinal": 1,
                "batch_id": "placeholder-other-batch",
                "command_digest": receipt["commands"][0],
                "semantic_value_iri": None,
            }
        ],
    }
    assert _codes(validate_materialization_ledger(ledger, receipts=[receipt])) == [
        "staged_ledger_stale"
    ]
    intents = [
        {"ordinal": 1, "idempotency_key": "placeholder-key-1", "status": "receipted"}
    ]
    bypass = reconcile_platform_batches(
        [{"batch_id": "b2", "idempotency_key": "rogue-key"}], intents, [receipt]
    )
    assert set(_codes(bypass)) == {"staged_unreconciled_batch"}
    fake = reconcile_platform_batches([], intents, [receipt])
    assert _codes(fake) == ["staged_unreconciled_batch"]
    # An unreachable listing reconciles nothing (adjudication owns that path).
    assert reconcile_platform_batches(None, intents, [receipt]) == ()


# --- S6 / B8: joint acceptance checklist ---------------------------------------


def _checklist(**overrides) -> dict:
    artifact = {
        "schema_version": "r3-0-008b-joint-acceptance-checklist/v1",
        "scenario_id": "placeholder-scenario",
        "produced_by": "coordinator",
        "items": [
            {
                "item_id": item_id,
                "verdict": "pending",
                "evidence_ref": f"evidence/{item_id}.md",
                "checked_by": "coordinator",
            }
            for item_id in CHECKLIST_ITEMS
        ],
    }
    artifact.update(overrides)
    return artifact


def test_s6_valid_checklist_passes_with_exact_fixed_items():
    assert validate_joint_acceptance_checklist(_checklist()) == ()


def test_b8_checklist_violations_are_typed():
    missing_item = _checklist()
    missing_item["items"] = missing_item["items"][:-1]
    assert _codes(validate_joint_acceptance_checklist(missing_item)) == [
        "acceptance_checklist_schema_mismatch"
    ]
    duplicated = _checklist()
    duplicated["items"][-1] = dict(duplicated["items"][0])
    assert _codes(validate_joint_acceptance_checklist(duplicated)) == [
        "acceptance_checklist_schema_mismatch"
    ]
    drifted = _checklist()
    drifted["items"][0]["verdict"] = "placeholder-verdict"
    assert _codes(validate_joint_acceptance_checklist(drifted)) == [
        "acceptance_checklist_schema_mismatch"
    ]


def test_b8_checklist_unparsable(tmp_path):
    path = tmp_path / "joint-acceptance-checklist.json"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(Exception, match="acceptance_checklist_unparsable"):
        load_joint_acceptance_checklist(path)


# --- S10 / B11: approvals cross-validation --------------------------------------


def _approvals(entries) -> dict:
    return {
        "schema_version": "r3-0-008b-approvals/v1",
        "scenario_id": "placeholder-scenario",
        "maintained_by": "coordinator",
        "entries": entries,
    }


def _approval_entry(**overrides) -> dict:
    entry = {
        "kind": "conclusion_confirmation",
        "target_id": "ac-0001",
        "revision": 2,
        "confirmed_enum_value": "placeholder-alpha",
        "approved_by": "coordinator",
        "note": None,
    }
    entry.update(overrides)
    return entry


def _stage3_slot(**overrides) -> dict:
    slot = {
        "schema_version": "r3-0-008b-stage3-slot/v1",
        "scenario_id": "placeholder-scenario",
        "produced_by": "modeling",
        "approved_by": "coordinator",
        "candidate_artifacts": ["stage3-neutral-graph/placeholder-candidate.json"],
        "deferred_contract": "R3.0-009",
        "slot_note": None,
    }
    slot.update(overrides)
    return slot


def test_s10_approvals_cross_validation_passes_and_invalidates_on_revision():
    conclusions = _conclusions([_confirmed_entry()])
    approvals = _approvals(
        [
            _approval_entry(),
            _approval_entry(kind="stage3_slot", target_id="placeholder-scenario", confirmed_enum_value=None),
        ]
    )
    assert validate_approvals(approvals) == ()
    assert cross_validate_approvals(approvals, conclusions, _stage3_slot()) == ()
    assert validate_stage3_slot(_stage3_slot()) == ()
    # A revision bump to analyzed invalidates nothing (only confirmed entries
    # need anchoring), but re-confirming at revision 3 needs a new approval.
    revised = _conclusions([_conclusion_entry(revision=3)])
    assert _codes(cross_validate_approvals(approvals, revised, None)) == []


def test_b11_approval_violations_are_typed():
    conclusions = _conclusions([_confirmed_entry()])
    empty_approvals = _approvals([])
    assert _codes(
        cross_validate_approvals(empty_approvals, conclusions, None)
    ) == ["conclusions_approval_missing"]
    assert _codes(
        cross_validate_approvals(empty_approvals, _conclusions([]), _stage3_slot())
    ) == ["stage3_approval_record_missing"]
    drifted = _approvals([_approval_entry(revision=1)])
    assert validate_approvals(drifted) == ()
    assert _codes(cross_validate_approvals(drifted, conclusions, None)) == [
        "conclusions_approval_missing"
    ]
    bad_shape = _approvals([_approval_entry(kind="placeholder-kind")])
    assert _codes(validate_approvals(bad_shape)) == ["approvals_schema_mismatch"]


def test_b11_approvals_unparsable(tmp_path):
    path = tmp_path / "approvals.json"
    path.write_text("[", encoding="utf-8")
    with pytest.raises(Exception, match="approvals_unparsable"):
        load_approvals(path)


# --- B12: envelope mirrors the real backend signature ---------------------------


def test_b12_capability_envelope_mirrors_real_submit_modeling_batch():
    from app.mcp.tools.modeling_batches import register_modeling_batches

    class _RecorderServer:
        def __init__(self) -> None:
            self.tools: dict[str, object] = {}

        def tool(self):
            def decorator(function):
                self.tools[function.__name__] = function
                return function

            return decorator

    server = _RecorderServer()
    register_modeling_batches(server)
    function = server.tools.get("submit_modeling_batch")
    assert function is not None, "backend must register submit_modeling_batch"
    signature = inspect.signature(function)
    # Independently hard-coded expectation (test author, not implementation).
    real_parameters = {
        "session_id",
        "client_batch_id",
        "ontology_id",
        "idempotency_key",
        "expected_model_revision",
        "items",
        "mode",
        "lease_token",
    }
    assert set(signature.parameters) == real_parameters
    defaults = {
        name: parameter.default
        for name, parameter in signature.parameters.items()
        if parameter.default is not inspect.Parameter.empty
    }
    assert defaults == {"mode": "apply_atomic", "lease_token": None}

    from modeling_team.staged_decisions import (
        BATCH_ENVELOPE_OPTIONAL_FIELDS,
        BATCH_ENVELOPE_REQUIRED_FIELDS,
    )

    assert set(BATCH_ENVELOPE_REQUIRED_FIELDS) | set(BATCH_ENVELOPE_OPTIONAL_FIELDS) == real_parameters
    assert "build_session_id" not in real_parameters
    assert "commands" not in real_parameters


# --- F3: determinism ------------------------------------------------------------


def test_f3_command_digests_are_deterministic_and_key_order_insensitive():
    command_one = {
        "command_kind": "create_enum_meaning",
        "payload": {"enum_value": "placeholder-alpha", "enum_meaning_id": "placeholder-enum-1"},
    }
    command_two = {
        "payload": {"enum_meaning_id": "placeholder-enum-1", "enum_value": "placeholder-alpha"},
        "command_kind": "create_enum_meaning",
    }
    assert canonical_command_digest(command_one) == canonical_command_digest(command_two)
    assert canonical_command_digest(command_one).startswith("sha256:")
    assert canonical_command_digest(
        {"command_kind": "update_enum_meaning", "payload": {}}
    ) != canonical_command_digest(command_one)


# --- B6: unknown adjudication (pure branches) -----------------------------------


def test_b6_unknown_intent_adjudication_branches():
    intent = {
        "ordinal": 1,
        "idempotency_key": "placeholder-key-1",
        "client_batch_id": "placeholder-batch-1",
        "status": "unknown",
    }
    claim_hit = [{"client_batch_id": "placeholder-batch-1", "idempotency_key": "other"}]
    branch, batch = adjudicate_unknown_intent(intent, claim_hit)
    assert branch == "claim" and batch == claim_hit[0]
    key_hit = [{"batch_id": "other", "idempotency_key": "placeholder-key-1"}]
    branch, batch = adjudicate_unknown_intent(intent, key_hit)
    assert branch == "claim" and batch == key_hit[0]
    branch, batch = adjudicate_unknown_intent(intent, [])
    assert (branch, batch) == ("retry", None)
    branch, batch = adjudicate_unknown_intent(intent, None)
    assert (branch, batch) == ("suspend", None)
    assert mark_intent_status(intent, "receipted")["status"] == "receipted"


# --- S4 / S8 / B3-B5: staged submission validation (pure layer) ------------------


def _envelope(items, *, mode="apply_atomic", lease_token="placeholder-lease") -> dict:
    return {
        "session_id": "placeholder-session",
        "client_batch_id": "placeholder-batch-1",
        "ontology_id": "https://example.test/ontology/placeholder",
        "idempotency_key": "placeholder-key-1",
        "expected_model_revision": 1,
        "items": items,
        "mode": mode,
        **({"lease_token": lease_token} if mode == "apply_atomic" else {}),
    }


def _enum_command(**payload_overrides) -> dict:
    payload = {
        "enum_meaning_id": "placeholder-enum-1",
        "property_iri": "https://example.test/prop/placeholder-status",
        "enum_value": "placeholder-alpha",
        "semantic_value": "https://example.test/value/placeholder-alpha",
    }
    payload.update(payload_overrides)
    return {"command_kind": "create_enum_meaning", "payload": payload}


def _trace(**overrides) -> dict:
    trace = {
        "command_index": 0,
        "conclusion_id": "ac-0001",
        "mapped_property": "https://example.test/prop/placeholder-status",
    }
    trace.update(overrides)
    return trace


def test_s4_valid_submission_passes_all_mechanical_checks():
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope([_enum_command()]),
        "value_traces": [_trace()],
        "l3_nodes": [
            {
                "command_index": 1,
                "entity_id": "placeholder-entity",
                "semantic_value_iri": "https://example.test/value/placeholder-alpha",
            }
        ],
    }
    payload["batch"]["items"].append(
        {
            "command_kind": "create_entity",
            "payload": {
                "entity_id": "placeholder-entity",
                "label": "placeholder-entity",
            },
        }
    )
    # The traced conclusion is confirmed at L3 so the L3 node is approved.
    conclusions = _conclusions(
        [_confirmed_entry(confirmed_level="L3", proposed_level="L3")]
    )
    unlock = _materialize_unlock()
    unlock["confirmed_codes"][0]["confirmed_level"] = "L3"
    issues = validate_staged_submission(
        payload,
        gate_open=True,
        conclusions=conclusions,
        unlock=unlock,
        receipts=[],
    )
    assert issues == ()


def test_b3_stage5_time_gate_is_fail_closed():
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope([_enum_command()]),
        "value_traces": [_trace()],
        "l3_nodes": [],
    }
    conclusions = _conclusions([_confirmed_entry()])
    # No unlock file at all.
    assert _codes(
        validate_staged_submission(payload, gate_open=True, conclusions=conclusions, unlock=None)
    ) == ["staged_value_materialization_locked"]
    # Skip-mode unlock keeps the stage-5 lock.
    skip = _materialize_unlock()
    skip["mode"] = "skip"
    skip["confirmed_codes"] = None
    skip["mapping_sources"] = None
    skip["skip_reason"] = "no_schema_no_interface"
    assert _codes(
        validate_staged_submission(
            payload, gate_open=True, conclusions=conclusions, unlock=skip
        )
    ) == ["staged_value_materialization_locked"]
    # Conclusions artifact missing while enum commands are present.
    assert _codes(
        validate_staged_submission(
            payload, gate_open=True, conclusions=None, unlock=_materialize_unlock()
        )
    ) == ["staged_conclusions_unavailable"]
    # Closed gate rejects everything first.
    assert _codes(
        validate_staged_submission(payload, gate_open=False, conclusions=conclusions, unlock=None)
    ) == ["staged_gate_closed"]


def test_s8_skip_mode_still_forwards_non_enum_payloads():
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope(
            [{"command_kind": "create_entity", "payload": {"entity_id": "placeholder-entity"}}]
        ),
        "value_traces": [],
        "l3_nodes": [],
    }
    assert (
        validate_staged_submission(
            payload, gate_open=True, conclusions=None, unlock=None
        )
        == ()
    )


def test_b4_materialization_matching_violations():
    conclusions = _conclusions([_confirmed_entry()])

    def check(**overrides):
        payload = {
            "protocol_id": "protocol",
            "batch": _envelope([_enum_command(**overrides.pop("payload", {}))]),
            "value_traces": overrides.pop("traces", [_trace()]),
            "l3_nodes": [],
        }
        payload.update(overrides.pop("extra", {}))
        return _codes(
            validate_staged_submission(
                payload,
                gate_open=True,
                conclusions=overrides.pop("conclusions", conclusions),
                unlock=_materialize_unlock(),
            )
        )

    assert check(traces=[]) == ["staged_missing_trace"]
    assert check(conclusions=_conclusions([_conclusion_entry()])) == [
        "staged_conclusion_not_confirmed"
    ]
    conflict = _conclusions(
        [_conclusion_entry(status="conflict", conflict_note="placeholder contradiction")]
    )
    assert check(conclusions=conflict) == ["staged_conclusion_conflict"]
    materialized = _conclusions(
        [
            _conclusion_entry(
                status="materialized",
                confirmed_enum_value="placeholder-alpha",
                confirmed_by="coordinator",
            )
        ]
    )
    assert check(conclusions=materialized) == ["staged_conclusion_already_materialized"]
    assert check(payload={"enum_value": "placeholder-other"}) == ["staged_trace_mismatch"]
    assert check(
        payload={"property_iri": "https://example.test/prop/placeholder-other"}
    ) == ["staged_trace_mismatch"]
    assert check(traces=[_trace(conclusion_id="ac-9999")]) == ["staged_trace_mismatch"]
    # update without enum_value and without a receipted target.
    update = {
        "command_kind": "update_enum_meaning",
        "payload": {"enum_meaning_id": "placeholder-enum-1"},
    }
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope([update]),
        "value_traces": [_trace()],
        "l3_nodes": [],
    }
    assert _codes(
        validate_staged_submission(
            payload, gate_open=True, conclusions=conclusions, unlock=_materialize_unlock()
        )
    ) == ["staged_unknown_enum_target"]


def test_b4_update_without_enum_value_closes_against_receipted_target():
    receipt = _receipt()
    conclusions = _conclusions([_confirmed_entry()])
    update = {
        "command_kind": "update_enum_meaning",
        "payload": {"enum_meaning_id": "placeholder-enum-1", "label": "placeholder label"},
    }
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope([update]),
        "value_traces": [_trace()],
        "l3_nodes": [],
    }
    assert (
        validate_staged_submission(
            payload, gate_open=True, conclusions=conclusions, unlock=_materialize_unlock(), receipts=[receipt]
        )
        == ()
    )


def test_b5_l3_node_violations():
    conclusions = _conclusions([_confirmed_entry()])

    def payload_with(node, command, traces):
        return {
            "protocol_id": "protocol",
            "batch": _envelope([command]),
            "value_traces": traces,
            "l3_nodes": [node],
        }

    entity_command = {
        "command_kind": "create_entity",
        "payload": {"entity_id": "placeholder-entity"},
    }
    node = {
        "command_index": 0,
        "entity_id": "placeholder-entity",
        "semantic_value_iri": "https://example.test/value/placeholder-alpha",
    }
    # The L3 node's conclusion is only L2-confirmed: unapproved.
    issues = validate_staged_submission(
        payload_with(node, entity_command, [_trace(command_index=0)]),
        gate_open=True,
        conclusions=conclusions,
        unlock=_materialize_unlock(),
    )
    assert _codes(issues) == ["staged_l3_unapproved"]
    # An L3-confirmed conclusion with a matching enum command backs the node.
    l3_conclusions = _conclusions(
        [_confirmed_entry(confirmed_level="L3", proposed_level="L3")]
    )
    batch = _envelope([_enum_command(), entity_command])
    batch["items"][1]["payload"]["entity_id"] = "placeholder-entity"
    payload = {
        "protocol_id": "protocol",
        "batch": batch,
        "value_traces": [_trace()],
        "l3_nodes": [
            {
                "command_index": 1,
                "entity_id": "placeholder-entity",
                "semantic_value_iri": "https://example.test/value/placeholder-alpha",
            }
        ],
    }
    issues = validate_staged_submission(
        payload, gate_open=True, conclusions=l3_conclusions, unlock=_materialize_unlock()
    )
    assert _codes(issues) == []


def test_b5_dangling_semantic_value():
    command = _enum_command(semantic_value="https://example.test/value/placeholder-other")
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope([command]),
        "value_traces": [_trace()],
        "l3_nodes": [],
    }
    conclusions = _conclusions([_confirmed_entry()])
    issues = validate_staged_submission(
        payload, gate_open=True, conclusions=conclusions, unlock=_materialize_unlock()
    )
    assert "staged_dangling_semantic_value" in _codes(issues)


def test_b6_envelope_schema_violations():
    conclusions = _conclusions([_confirmed_entry()])

    def check(batch):
        payload = {
            "protocol_id": "protocol",
            "batch": batch,
            "value_traces": [_trace()],
            "l3_nodes": [],
        }
        return _codes(
            validate_staged_submission(
                payload, gate_open=True, conclusions=conclusions, unlock=_materialize_unlock()
            )
        )

    missing_key = _envelope([_enum_command()])
    del missing_key["idempotency_key"]
    assert check(missing_key) == ["staged_submit_schema_mismatch"]
    missing_version = _envelope([_enum_command()])
    del missing_version["expected_model_revision"]
    assert check(missing_version) == ["staged_submit_schema_mismatch"]
    no_items = _envelope([])
    assert check(no_items) == ["staged_submit_schema_mismatch"]
    no_lease = _envelope([_enum_command()])
    del no_lease["lease_token"]
    assert check(no_lease) == ["staged_submit_schema_mismatch"]
    legacy = _envelope([_enum_command()])
    legacy["build_session_id"] = "placeholder-session"
    legacy["commands"] = legacy.pop("items")
    assert check(legacy) == ["staged_submit_schema_mismatch"]
    non_object = {"protocol_id": "protocol", "batch": "not-an-object", "value_traces": [], "l3_nodes": []}
    assert _codes(
        validate_staged_submission(non_object, gate_open=True, conclusions=None, unlock=None)
    ) == ["staged_submit_schema_mismatch"]
    unparsable = "not-an-object"
    assert _codes(
        validate_staged_submission(unparsable, gate_open=True, conclusions=None, unlock=None)
    ) == ["staged_submit_unparsable"]


def test_d1_stage3_slot_failure_reason_codes_are_typed(tmp_path):
    run_root = tmp_path / "run"
    paths = staged_decision_artifact_paths(run_root)

    # A present-but-unparsable slot surfaces the typed unparsable code.
    paths["stage3_slot"].parent.mkdir(parents=True, exist_ok=True)
    paths["stage3_slot"].write_text("{broken json", encoding="utf-8")
    issue = staged_stage3_issue(run_root, None)
    assert issue is not None and issue.reason_code == "stage3_unparsable"

    # An unapproved slot (empty approved_by) is rejected typed.
    assert [entry.reason_code for entry in validate_stage3_slot(_stage3_slot(approved_by=""))] == [
        "stage3_missing_approval"
    ]

    # A declared candidate artifact that does not exist (or escapes the run
    # workspace) is rejected typed.
    run_root2 = tmp_path / "run2"
    missing = staged_stage3_issue(
        run_root2, None
    )  # absent slot file is the missing-artifact code, not a crash
    assert missing is not None and missing.reason_code == "stage3_missing_artifact"
    escaping = validate_stage3_slot(_stage3_slot(candidate_artifacts=["../outside.json"]))
    assert [entry.reason_code for entry in escaping] == [
        "stage3_candidate_artifact_unavailable"
    ]
    reachable = check_stage3_candidate_artifacts(
        run_root2, _stage3_slot(candidate_artifacts=["stage3-neutral-graph/absent.json"])
    )
    assert reachable is not None and reachable.reason_code == "stage3_candidate_artifact_unavailable"


def test_d1_conclusions_schema_mismatch_is_typed():
    drifted = _conclusions([_conclusion_entry()])
    drifted["extra_field"] = "placeholder"
    codes = _codes(validate_analysis_conclusions(drifted))
    assert codes == ["conclusions_schema_mismatch"]
    wrong_version = _conclusions([_conclusion_entry()])
    wrong_version["schema_version"] = "r3-0-008b-analysis-conclusions/v0"
    assert _codes(validate_analysis_conclusions(wrong_version)) == ["conclusions_schema_mismatch"]
    bad_entry = _conclusions([_conclusion_entry(proposed_level="L9")])
    assert "conclusions_schema_mismatch" in _codes(validate_analysis_conclusions(bad_entry))


def test_conclusions_reject_legacy_trace_fields_and_version():
    entry = _conclusion_entry(evidence_refs=[])
    assert _codes(validate_analysis_conclusions(_conclusions([entry]))) == [
        "conclusions_schema_mismatch"
    ]
    obsolete = _conclusions([_conclusion_entry()])
    obsolete["schema_version"] = "r3-0-008b-analysis-conclusions/v1"
    assert _codes(validate_analysis_conclusions(obsolete)) == ["conclusions_schema_mismatch"]


def test_d1_unlock_failure_reason_codes_are_typed(tmp_path):
    run_root = tmp_path / "run"
    paths = staged_decision_artifact_paths(run_root)

    # A present-but-unparsable unlock raises the typed unparsable code.
    paths["unlock"].parent.mkdir(parents=True, exist_ok=True)
    paths["unlock"].write_text("{broken json", encoding="utf-8")
    with pytest.raises(StagedDecisionArtifactError, match="unlock_unparsable"):
        load_materialization_unlock(paths["unlock"])

    # Structural unlock violations surface the typed schema-mismatch code.
    drifted = _materialize_unlock()
    drifted["unexpected"] = True
    assert _codes(validate_materialization_unlock(drifted)) == ["unlock_schema_mismatch"]
    wrong_version = _materialize_unlock()
    wrong_version["schema_version"] = "r3-0-008b-materialization-unlock/v0"
    assert _codes(validate_materialization_unlock(wrong_version)) == ["unlock_schema_mismatch"]
    bad_mode = _materialize_unlock()
    bad_mode["mode"] = "partial"
    assert _codes(validate_materialization_unlock(bad_mode)) == ["unlock_schema_mismatch"]


def test_reference_contract_json_is_valid_and_self_consistent():
    contract = json.loads(
        (
            REPO_ROOT
            / "modeling_team"
            / "references"
            / "r3-0-008b-staged-decisions-contract.json"
        ).read_text(encoding="utf-8")
    )
    assert contract["schema_version"] == "r3-0-008b-staged-decisions-contract/v2"
    assert (
        contract["joint_acceptance_checklist"]["fixed_item_ids"] == CHECKLIST_ITEMS
    )
    capability = contract["staged_submission_capability"]
    assert capability["operation"] == "protocol_staged_submit_modeling_batch"
    assert "staged_value_materialization_locked" in capability["failure_reason_codes"]
    assert "staged_unknown_enum_target" in capability["failure_reason_codes"]
    assert contract["kill_switch"]["reason_code"] == "staged_unreconciled_batch"
    assert len(contract["kill_switch"]["triggers"]) == 4


# --- auth008-start1 forensics: enum code sets carried as string lists ---------


def test_b1_multi_code_enum_lists_are_legal():
    codes = ["placeholder-alpha", "placeholder-beta"]
    conclusions = _conclusions(
        [
            _confirmed_entry(
                candidate_value=list(codes),
                confirmed_enum_value=list(codes),
            )
        ]
    )
    archive = {"ac-0001": [_conclusion_entry(status="analyzed", revision=1)]}
    assert validate_analysis_conclusions(conclusions, archive=archive) == ()
    approvals = _approvals([_approval_entry(confirmed_enum_value=list(codes))])
    assert validate_approvals(approvals) == ()
    assert cross_validate_approvals(approvals, conclusions, None) == ()
    # The unlock mirrors the same list form and still matches the conclusion.
    unlock = _materialize_unlock()
    unlock["confirmed_codes"][0]["confirmed_enum_value"] = list(codes)
    assert validate_materialization_unlock(unlock, conclusions=conclusions) == ()


def test_b1_invalid_enum_list_shapes_are_typed():
    assert _codes(validate_analysis_conclusions(_conclusions([_conclusion_entry(candidate_value=[])]))) == [
        "conclusions_schema_mismatch"
    ]
    assert _codes(
        validate_analysis_conclusions(_conclusions([_conclusion_entry(candidate_value=["placeholder-alpha", ""])]))
    ) == ["conclusions_schema_mismatch"]
    assert _codes(
        validate_analysis_conclusions(_conclusions([_conclusion_entry(candidate_value=[1])]))
    ) == ["conclusions_schema_mismatch"]
    assert _codes(
        validate_analysis_conclusions(_conclusions([_confirmed_entry(confirmed_enum_value=[], revision=1)]))
    ) == ["conclusions_invalid_status_fields"]
    # A plain non-empty string stays the canonical single-code form.
    assert validate_analysis_conclusions(_conclusions([_confirmed_entry(revision=1)])) == ()
    assert _codes(validate_approvals(_approvals([_approval_entry(confirmed_enum_value=[])]))) == [
        "approvals_schema_mismatch"
    ]


def test_b4_each_confirmed_code_materializes_via_its_own_enum_command():
    codes = ["placeholder-alpha", "placeholder-beta"]
    conclusions = _conclusions(
        [
            _confirmed_entry(
                candidate_value=list(codes),
                confirmed_enum_value=list(codes),
            )
        ]
    )
    unlock = _materialize_unlock()
    unlock["confirmed_codes"][0]["confirmed_enum_value"] = list(codes)

    def check(enum_value):
        command = _enum_command(
            enum_meaning_id=f"placeholder-enum-{enum_value}",
            enum_value=enum_value,
            semantic_value=None,
        )
        payload = {
            "protocol_id": "protocol",
            "batch": _envelope([command]),
            "value_traces": [_trace()],
            "l3_nodes": [],
        }
        return validate_staged_submission(
            payload, gate_open=True, conclusions=conclusions, unlock=unlock
        )

    # One create_enum_meaning per confirmed code: membership, not whole-set equality.
    for code in codes:
        assert check(code) == ()
    assert _codes(check("placeholder-gamma")) == ["staged_trace_mismatch"]


def test_b4_update_enum_value_accepts_any_confirmed_code():
    codes = ["placeholder-alpha", "placeholder-beta"]
    conclusions = _conclusions([_confirmed_entry(confirmed_enum_value=list(codes))])
    receipt = _receipt()
    update = {
        "command_kind": "update_enum_meaning",
        "payload": {
            "enum_meaning_id": "placeholder-enum-1",
            "enum_value": "placeholder-beta",
        },
    }
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope([update]),
        "value_traces": [_trace()],
        "l3_nodes": [],
    }
    assert (
        validate_staged_submission(
            payload,
            gate_open=True,
            conclusions=conclusions,
            unlock=_materialize_unlock(),
            receipts=[receipt],
        )
        == ()
    )
    outside = dict(update)
    outside["payload"] = dict(update["payload"], enum_value="placeholder-gamma")
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope([outside]),
        "value_traces": [_trace()],
        "l3_nodes": [],
    }
    assert _codes(
        validate_staged_submission(
            payload, gate_open=True, conclusions=conclusions, unlock=_materialize_unlock()
        )
    ) == ["staged_trace_mismatch"]


def test_issue_details_carry_expected_shapes():
    # candidate_value failure names the field and the accepted shapes.
    issues = validate_analysis_conclusions(_conclusions([_conclusion_entry(candidate_value=[])]))
    assert "candidate_value" in issues[0].detail
    assert "non-empty" in issues[0].detail
    # A confirmed entry without a usable code set names confirmed_enum_value.
    issues = validate_analysis_conclusions(
        _conclusions([_confirmed_entry(confirmed_enum_value=[], revision=1)])
    )
    assert any("confirmed_enum_value" in issue.detail for issue in issues)
    # Trace mismatch names the rejected payload code and the accepted codes.
    codes = ["placeholder-alpha", "placeholder-beta"]
    conclusions = _conclusions([_confirmed_entry(confirmed_enum_value=list(codes))])
    payload = {
        "protocol_id": "protocol",
        "batch": _envelope([_enum_command(enum_value="placeholder-gamma", semantic_value=None)]),
        "value_traces": [_trace()],
        "l3_nodes": [],
    }
    issues = validate_staged_submission(
        payload, gate_open=True, conclusions=conclusions, unlock=_materialize_unlock()
    )
    assert issues[0].reason_code == "staged_trace_mismatch"
    assert "placeholder-gamma" in issues[0].detail
    assert "placeholder-alpha" in issues[0].detail and "placeholder-beta" in issues[0].detail
