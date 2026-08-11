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


def test_r23003_accepted_candidate_revision_is_a_positive_integer() -> None:
    with tempfile.TemporaryDirectory(prefix="r23003-revision-") as directory:
        carrier = RunnerAcceptanceCarrier(
            Path(directory) / "r23003",
            task_id="r2-3-003-existing-scope-incremental",
            acceptance_id="acceptance",
        )
        assert carrier.register_accepted_candidate(
            candidate_revision=1,
            candidate_digest="a" * 64,
        ) == {
            "candidate_revision": 1,
            "candidate_digest": "a" * 64,
        }


@pytest.mark.parametrize("candidate_revision", [True, False, 0, -1, "1"])
def test_r23003_rejects_non_positive_integer_candidate_revision(candidate_revision: object) -> None:
    with tempfile.TemporaryDirectory(prefix="r23003-revision-invalid-") as directory:
        carrier = RunnerAcceptanceCarrier(
            Path(directory) / "r23003",
            task_id="r2-3-003-existing-scope-incremental",
            acceptance_id="acceptance",
        )
        with pytest.raises(AcceptanceContractError, match="positive integer"):
            carrier.register_accepted_candidate(
                candidate_revision=candidate_revision,
                candidate_digest="a" * 64,
            )


def _r23003_candidate(revision: int, value: str) -> dict[str, object]:
    return {
        "candidate_kind": "platform-neutral-candidate-v2",
        "candidate_revision": revision,
        "scope": "retained",
        "constraints": ["source-grounded"],
        "items": [
            {
                "item_id": "predicate-field",
                "item_kind": "predicate",
                "semantic": {
                    "predicate": "field",
                    "predicate_kind": "fact",
                    "range": "string",
                },
            },
            {
                "item_id": "entity-a",
                "item_kind": "entity",
                "semantic": {
                    "entity_id": "entity-a",
                    "class": "Entity",
                    "values": {"field": value},
                },
            },
            {
                "item_id": "consumer-q",
                "item_kind": "consumer_query",
                "semantic": {
                    "query_id": "q",
                    "question": "What is the field?",
                    "required_paths": ["field"],
                },
            },
        ],
    }


def test_r23003_revision_replacement_refreshes_candidate_and_retrieval_gate() -> None:
    candidate_v1 = _r23003_candidate(1, "v1")
    candidate_v2 = _r23003_candidate(2, "v2")
    digest_v1 = canonical_digest(candidate_v1)
    digest_v2 = canonical_digest(candidate_v2)
    with tempfile.TemporaryDirectory(prefix="r23003-revision-replacement-") as directory:
        carrier = RunnerAcceptanceCarrier(
            Path(directory) / "r23003",
            task_id="r2-3-003-existing-scope-incremental",
            acceptance_id="acceptance",
        )
        carrier.register_accepted_candidate(
            candidate_revision=1,
            candidate_digest=digest_v1,
            candidate=candidate_v1,
        )
        first_gate = carrier._ordinary_retrieval_gate
        assert first_gate is not None
        carrier._ordinary_retrieval_receipt = {"candidate_revision": 1}

        replacement = carrier.register_accepted_candidate(
            candidate_revision=2,
            candidate_digest=digest_v2,
            candidate=candidate_v2,
        )
        assert replacement == {"candidate_revision": 2, "candidate_digest": digest_v2}
        assert carrier._accepted_candidate_identity == replacement
        assert carrier._accepted_candidate == candidate_v2
        second_gate = carrier._ordinary_retrieval_gate
        assert second_gate is not None and second_gate is not first_gate
        assert second_gate.candidate_revision == 2
        assert second_gate.candidate_digest == digest_v2
        assert carrier.ordinary_retrieval_receipt is None

        assert carrier.register_accepted_candidate(
            candidate_revision=2,
            candidate_digest=digest_v2,
            candidate=candidate_v2,
        ) == replacement
        assert carrier._ordinary_retrieval_gate is second_gate


def test_r23003_revision_replacement_rejects_stale_equal_and_reused_digest() -> None:
    candidate_v1 = _r23003_candidate(1, "v1")
    candidate_v2 = _r23003_candidate(2, "v2")
    candidate_v2_changed = _r23003_candidate(2, "v2-changed")
    candidate_v3 = _r23003_candidate(3, "v3")
    digest_v1 = canonical_digest(candidate_v1)
    digest_v2 = canonical_digest(candidate_v2)
    digest_v2_changed = canonical_digest(candidate_v2_changed)
    with tempfile.TemporaryDirectory(prefix="r23003-revision-fence-") as directory:
        carrier = RunnerAcceptanceCarrier(
            Path(directory) / "r23003",
            task_id="r2-3-003-existing-scope-incremental",
            acceptance_id="acceptance",
        )
        carrier.register_accepted_candidate(
            candidate_revision=1,
            candidate_digest=digest_v1,
            candidate=candidate_v1,
        )
        carrier.register_accepted_candidate(
            candidate_revision=2,
            candidate_digest=digest_v2,
            candidate=candidate_v2,
        )
        with pytest.raises(AcceptanceContractError, match="strictly increase"):
            carrier.register_accepted_candidate(
                candidate_revision=1,
                candidate_digest=digest_v1,
                candidate=candidate_v1,
            )
        with pytest.raises(AcceptanceContractError, match="strictly increase"):
            carrier.register_accepted_candidate(
                candidate_revision=2,
                candidate_digest=digest_v2_changed,
                candidate=candidate_v2_changed,
            )
        with pytest.raises(AcceptanceContractError, match="must change"):
            carrier.register_accepted_candidate(
                candidate_revision=3,
                candidate_digest=digest_v2,
                candidate=candidate_v3,
            )
        assert carrier._accepted_candidate_identity == {
            "candidate_revision": 2,
            "candidate_digest": digest_v2,
        }


def test_r23005_and_default_carriers_keep_safe_string_revision_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="acceptance-revision-scope-") as directory:
        for index, task_id in enumerate(("r2-3-005-formal-acceptance", "task-default")):
            carrier = RunnerAcceptanceCarrier(
                Path(directory) / str(index),
                task_id=task_id,
                acceptance_id="acceptance",
            )
            assert carrier.register_accepted_candidate(
                candidate_revision="revision-1",
                candidate_digest="b" * 64,
            )["candidate_revision"] == "revision-1"
            with pytest.raises(AcceptanceContractError, match="safe stable identifier"):
                carrier.register_accepted_candidate(
                    candidate_revision=1,
                    candidate_digest="b" * 64,
                )
            with pytest.raises(AcceptanceContractError, match="accepted candidate identity was mutated"):
                carrier.register_accepted_candidate(
                    candidate_revision="revision-2",
                    candidate_digest="c" * 64,
                )


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
