from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from modeling_team.acceptance import AcceptanceContractError, RunnerAcceptanceCarrier, validate_ticket
from modeling_team.tests.test_r23005_c_settlement import _run_round
from modeling_team.tests.test_r23005_contracts import _ticket
from modeling_team.r23003_contract import (
    R2_3_003_TARGET_IDS,
    build_delete_impact_receipt,
    canonical_digest,
    classify_delete_only_recovery,
    deletion_policy,
    get_entity_statement_context,
    validate_candidate_delete_declaration,
    validate_canonical_entity_projection,
    validate_deletion_policy,
    validate_r23003_candidate_declarations,
)
from modeling_team.protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_existing_entity_binding_receipt,
)


SCOPE = {
    "project_id": "project-r23003",
    "ontology_id": "ontology-r23003",
    "workspace_version": "workspace-v1",
}


def test_deletion_policy_and_candidate_are_exactly_frozen() -> None:
    policy = deletion_policy()
    assert tuple(item["semantic_id"] for item in policy["targets"]) == R2_3_003_TARGET_IDS
    assert validate_deletion_policy(policy) == policy
    assert validate_candidate_delete_declaration(
        {
            "semantic_id": R2_3_003_TARGET_IDS[0],
            "expected_class": "ExplicitUnknown",
            "delete_mode": "full_live_impact",
        }
    )["delete_mode"] == "full_live_impact"
    with pytest.raises(ValueError):
        validate_candidate_delete_declaration(
            {
                "semantic_id": R2_3_003_TARGET_IDS[0],
                "expected_class": "ExplicitUnknown",
                "delete_mode": "full_live_impact",
                "entity_iri": "http://spoofed.invalid/entity",
            }
        )
    with pytest.raises(ValueError):
        validate_deletion_policy({**policy, "targets": list(reversed(policy["targets"]))})


def test_candidate_deletion_gate_requires_exact_two_ordered_unique_targets() -> None:
    def candidate(declarations):
        return {"items": [{"item_kind": "delete_existing_entity", "semantic": item} for item in declarations]}

    frozen = [
        {
            "semantic_id": R2_3_003_TARGET_IDS[0],
            "expected_class": "ExplicitUnknown",
            "delete_mode": "full_live_impact",
        },
        {
            "semantic_id": R2_3_003_TARGET_IDS[1],
            "expected_class": "ExplicitUnknown",
            "delete_mode": "full_live_impact",
        },
    ]
    assert len(validate_r23003_candidate_declarations(candidate(frozen))) == 2
    for declarations in ([], [frozen[0]], [frozen[0], frozen[0]], [frozen[0], frozen[1], frozen[1]]):
        with pytest.raises(ValueError):
            validate_r23003_candidate_declarations(candidate(declarations))


def test_deletion_aware_ticket_requires_runner_owned_question_progress() -> None:
    ticket = _ticket("r23003-progress")
    ticket["unknown_policy"] = deletion_policy()
    with pytest.raises(AcceptanceContractError, match="complete Runner question progress"):
        validate_ticket(ticket)


def test_single_question_pass_reaches_settlement_without_next_cq_boundary() -> None:
    with tempfile.TemporaryDirectory(prefix="r23003-n1-") as directory:
        carrier = RunnerAcceptanceCarrier(
            Path(directory) / "carrier",
            task_id="task-r23005",
            acceptance_id="acceptance",
        )
        _run_round(carrier, _ticket("r23003-n1"), "r23003-n1")
        assert carrier.settlement_ready()
        assert carrier.settle()["status"] == "settled"


def test_canonical_projection_requires_explicit_scope_and_identity() -> None:
    projection = {
        "semantic_id": "unknown-cross-release-output-meaning",
        "entity_iri": "http://ontology-platform.local/entity/unknown-cross-release-output-meaning",
        "class_semantic_id": "ExplicitUnknown",
        "class_iri": "http://ontology-platform.local/class/ExplicitUnknown",
        **SCOPE,
    }
    assert validate_canonical_entity_projection(projection, **SCOPE) == projection
    with pytest.raises(ValueError):
        validate_canonical_entity_projection(
            {key: value for key, value in projection.items() if key != "class_semantic_id"},
            **SCOPE,
        )
    with pytest.raises(ValueError):
        validate_canonical_entity_projection(
            {**projection, "entity_iri": "not-an-iri"},
            **SCOPE,
        )


def test_synthetic_only_entity_shape_fails_closed() -> None:
    candidate = {
        "candidate_kind": "platform-neutral-candidate-v2",
        "candidate_revision": 1,
        "scope": "retained",
        "constraints": ["source-grounded"],
        "items": [
            {
                "item_id": "existing",
                "item_kind": "existing_entity_ref",
                "semantic": {
                    "semantic_id": "unknown-cross-release-output-meaning",
                    "expected_class": "ExplicitUnknown",
                },
            },
            {
                "item_id": "delete-a",
                "item_kind": "delete_existing_entity",
                "semantic": {
                    "semantic_id": "unknown-cross-release-output-meaning",
                    "expected_class": "ExplicitUnknown",
                    "delete_mode": "full_live_impact",
                },
            },
            {
                "item_id": "delete-b",
                "item_kind": "delete_existing_entity",
                "semantic": {
                    "semantic_id": "unknown-b-no-score-behavior",
                    "expected_class": "ExplicitUnknown",
                    "delete_mode": "full_live_impact",
                },
            },
        ],
    }
    with pytest.raises(ProtocolRetrievalFallbackError, match="canonical entity projection"):
        build_existing_entity_binding_receipt(
            candidate,
            {
                "entities": [
                    {
                        "semantic_id": "unknown-cross-release-output-meaning",
                        "class": "ExplicitUnknown",
                        "entity_iri": "https://example.test/entity/unknown",
                        "read_evidence": {"source": "synthetic"},
                    }
                ]
            },
            **SCOPE,
        )
def test_entity_statement_context_paginates_opaque_snapshot_and_rejects_drift() -> None:
    statements = [
        {"subject": "http://ontology-platform.local/entity/target", "predicate": "p", "object": str(i)}
        for i in range(1001)
    ]
    first = get_entity_statement_context(
        statements,
        entity_iri="http://ontology-platform.local/entity/target",
        page_size=1000,
        **SCOPE,
    )
    assert len(first["statements"]) == 1000
    assert first["complete"] is False
    second = get_entity_statement_context(
        statements,
        entity_iri="http://ontology-platform.local/entity/target",
        cursor=first["next_cursor"],
        page_size=1000,
        **SCOPE,
    )
    assert len(second["statements"]) == 1
    assert second["complete"] is True
    with pytest.raises(ValueError, match="snapshot"):
        get_entity_statement_context(
            statements + [{"subject": "new", "predicate": "p", "object": "drift"}],
            entity_iri="http://ontology-platform.local/entity/target",
            cursor=first["next_cursor"],
            page_size=1000,
            **SCOPE,
        )


def test_delete_impact_chain_and_recovery_are_fail_closed() -> None:
    statements = [
        {"subject": "http://ontology-platform.local/entity/target", "predicate": "p", "object": "x"},
    ]
    pages = [
        {
            **SCOPE,
            "entity_iri": "http://ontology-platform.local/entity/target",
            "cursor": None,
            "statements": [],
            "page_digest": canonical_digest([]),
            "snapshot_digest": canonical_digest(statements),
            "complete": False,
            "next_cursor": "esc1.next",
        },
        {
            **SCOPE,
            "entity_iri": "http://ontology-platform.local/entity/target",
            "cursor": "esc1.next",
            "statements": statements,
            "page_digest": canonical_digest(statements),
            "snapshot_digest": canonical_digest(statements),
            "complete": True,
            "next_cursor": None,
        },
    ]
    receipt = build_delete_impact_receipt(
        pages,
        target_semantic_id=R2_3_003_TARGET_IDS[0],
        candidate_digest="candidate-1",
        **SCOPE,
    )
    assert receipt["entity_iri"] == "http://ontology-platform.local/entity/target"
    with pytest.raises(ValueError, match="page digest"):
        build_delete_impact_receipt(
            [{**pages[0], "page_digest": "wrong"}, pages[1]],
            target_semantic_id=R2_3_003_TARGET_IDS[0],
            candidate_digest="candidate-1",
            **SCOPE,
        )
    with pytest.raises(ValueError, match="snapshot"):
        build_delete_impact_receipt(
            [{**pages[0], "snapshot_digest": "different"}, pages[1]],
            target_semantic_id=R2_3_003_TARGET_IDS[0],
            candidate_digest="candidate-1",
            **SCOPE,
        )
    before = {
        **SCOPE,
        "statements": statements,
        "target_semantic_ids": [R2_3_003_TARGET_IDS[0]],
        "complete": True,
    }
    assert classify_delete_only_recovery(receipt, before) == "not_applied"
    assert classify_delete_only_recovery(
        receipt,
        {**SCOPE, "statements": [], "target_semantic_ids": [], "complete": True},
    ) == "applied"
    assert classify_delete_only_recovery(
        receipt,
        {**SCOPE, "statements": [{"subject": "new"}], "target_semantic_ids": [], "complete": True},
    ) == "partial_or_drifted"
    with pytest.raises(ValueError):
        build_delete_impact_receipt(
            [{**pages[0], "complete": True}, pages[1]],
            target_semantic_id=R2_3_003_TARGET_IDS[0],
            candidate_digest="candidate-1",
            **SCOPE,
        )
