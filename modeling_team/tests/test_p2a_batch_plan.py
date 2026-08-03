from __future__ import annotations

import copy
from pathlib import Path

import pytest

from modeling_team.p2a_batch_plan import (
    ASSERTION_CLIENT_ITEM_IDS,
    P2ABatchPlanError,
    build_p2a_batch_plan,
    verify_p2a_dry_run_evidence_projection,
)
from modeling_team.matrix_artifact import load_matrix
from modeling_team.p2a_protocol_driver import _generated_candidate
from modeling_team.proof_v2 import build_candidate_item_evidence_map


def candidate() -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    return _generated_candidate(load_matrix(root))[0]


def candidate_receipt(value: dict[str, object]) -> dict[str, object]:
    return {
        "status": "accepted",
        "candidate_revision": value["candidate_revision"],
        "semantic_digest": value["semantic_digest"],
        "candidate_digest": value["candidate_digest"],
    }


def evidence_map(value: dict[str, object], run_id: str = "p2a-run-1") -> dict[str, object]:
    return build_candidate_item_evidence_map(
        value,
        ASSERTION_CLIENT_ITEM_IDS,
        run_id=run_id,
    )


def dry_run_detail(value: dict[str, object], dedupe_suffix: str = "") -> dict[str, object]:
    dedupe_by_identity = {
        identity: f"evidence-{index}{dedupe_suffix}"
        for index, identity in enumerate(
            sorted({row["inline_evidence_identity"] for row in value["rows"]}),
            1,
        )
    }
    groups = {
        (row["client_item_id"], row["inline_evidence_identity"]): row
        for row in value["rows"]
    }
    plan_rows = [
        {
            "client_item_id": row["client_item_id"],
            "document_name": row["document_name"],
            "normalized_excerpt_sha256": row["excerpt_sha256"],
            "dedupe_identity": dedupe_by_identity[row["inline_evidence_identity"]],
        }
        for row in groups.values()
    ]
    return {
        "batch_id": "batch-1",
        "items": [
            {"client_item_id": client_item_id}
            for client_item_id in ASSERTION_CLIENT_ITEM_IDS.values()
        ],
        "attempts": [
            {
                "attempt_id": "attempt-1",
                "mode": "dry_run",
                "attempt_status": "validated",
                "findings": [],
                "operation_plan": {"evidence": plan_rows},
            }
        ],
    }


def dry_run_receipt(detail: dict[str, object]) -> dict[str, object]:
    attempt = copy.deepcopy(detail["attempts"][0])
    return {
        "batch_id": detail["batch_id"],
        "items": copy.deepcopy(detail["items"]),
        **attempt,
    }


def test_frozen_candidate_compiles_to_exact_one_entity_and_three_relations():
    value = candidate()
    plan = build_p2a_batch_plan(
        value,
        evidence_map(value),
        candidate_receipt(value),
        expected_run_id="p2a-run-1",
    )

    assert [item["client_item_id"] for item in plan["items"]] == list(
        ASSERTION_CLIENT_ITEM_IDS.values()
    )
    assert [item["command_kind"] for item in plan["items"]] == [
        "create_entity",
        "create_relation",
        "create_relation",
        "create_relation",
    ]
    assert plan["items"][0]["payload"]["properties"] == {
        "urn:p2a:publicationStatus": "published"
    }
    assert "datatype" not in plan["items"][0]["payload"]
    assert all(item["evidence"] for item in plan["items"])
    assert plan["items"][1]["payload"]["source_entity_iri"] == {
        "item_ref": {
            "client_item_id": "p2a-01-literal-a008",
            "output": "resource_iri",
        }
    }


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda value: value["items"].reverse(), "candidate is invalid"),
        (
            lambda value: value["items"].pop(),
            "candidate is invalid",
        ),
        (
            lambda value: value.update(candidate_digest="0" * 64),
            "candidate is invalid",
        ),
    ],
)
def test_candidate_drift_fails_closed(mutate, expected):
    value = candidate()
    retained_map = evidence_map(value)
    receipt = candidate_receipt(value)
    mutate(value)

    with pytest.raises(P2ABatchPlanError, match=expected):
        build_p2a_batch_plan(value, retained_map, receipt, expected_run_id="p2a-run-1")


def test_receipt_map_and_run_drift_fail_closed():
    value = candidate()
    retained_map = evidence_map(value)
    receipt = candidate_receipt(value)
    receipt["delivery_id"] = "different"
    with pytest.raises(P2ABatchPlanError, match="receipt"):
        build_p2a_batch_plan(value, retained_map, receipt, expected_run_id="p2a-run-1")

    with pytest.raises(P2ABatchPlanError, match="Evidence map"):
        build_p2a_batch_plan(
            value,
            retained_map,
            candidate_receipt(value),
            expected_run_id="cross-run",
        )


def test_projection_requires_receipt_plus_two_canonical_reads_and_global_bijection():
    value = candidate()
    retained_map = evidence_map(value)
    detail = dry_run_detail(retained_map)
    result = verify_p2a_dry_run_evidence_projection(
        value,
        retained_map,
        dry_run_receipt(detail),
        copy.deepcopy(detail),
        copy.deepcopy(detail),
        expected_run_id="p2a-run-1",
    )

    assert len(result["plan_rows"]) == 4
    assert all(set(row) == {
        "client_item_id",
        "inline_evidence_identity",
        "dedupe_identity",
    } for row in result["plan_rows"])
    assert len(result["dedupe_by_inline_identity"]) == len(
        {row["inline_evidence_identity"] for row in retained_map["rows"]}
    )
    assert result["postapply_bound"] is False

    unstable = dry_run_detail(retained_map, "-changed")
    with pytest.raises(P2ABatchPlanError, match="canonically stable|bijection"):
        verify_p2a_dry_run_evidence_projection(
            value,
            retained_map,
            detail,
            detail,
            unstable,
            expected_run_id="p2a-run-1",
        )

    collided = copy.deepcopy(detail)
    rows = collided["attempts"][0]["operation_plan"]["evidence"]
    distinct_index = next(
        index
        for index, row in enumerate(rows[1:], 1)
        if (
            row["document_name"],
            row["normalized_excerpt_sha256"],
        )
        != (
            rows[0]["document_name"],
            rows[0]["normalized_excerpt_sha256"],
        )
    )
    rows[distinct_index]["dedupe_identity"] = rows[0]["dedupe_identity"]
    with pytest.raises(P2ABatchPlanError, match="multiple inline identities"):
        verify_p2a_dry_run_evidence_projection(
            value,
            retained_map,
            collided,
            collided,
            collided,
            expected_run_id="p2a-run-1",
        )


def test_projection_validates_postapply_same_id_back_references():
    value = candidate()
    retained_map = evidence_map(value)
    detail = dry_run_detail(retained_map)
    preapply = verify_p2a_dry_run_evidence_projection(
        value,
        retained_map,
        dry_run_receipt(detail),
        detail,
        detail,
        expected_run_id="p2a-run-1",
    )
    bindings = [
        {
            "client_item_id": row["client_item_id"],
            "inline_evidence_identity": row["inline_evidence_identity"],
            "evidence_reference_id": row["dedupe_identity"],
        }
        for row in preapply["plan_rows"]
    ]
    result = verify_p2a_dry_run_evidence_projection(
        value,
        retained_map,
        dry_run_receipt(detail),
        detail,
        detail,
        expected_run_id="p2a-run-1",
        postapply_evidence_bindings=bindings,
    )
    assert result["postapply_bound"] is True

    bindings[0]["evidence_reference_id"] = "different-reference"
    with pytest.raises(P2ABatchPlanError, match="back-reference"):
        verify_p2a_dry_run_evidence_projection(
            value,
            retained_map,
            dry_run_receipt(detail),
            detail,
            detail,
            expected_run_id="p2a-run-1",
            postapply_evidence_bindings=bindings,
        )
