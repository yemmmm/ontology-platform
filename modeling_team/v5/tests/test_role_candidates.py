"""Neutral candidate normalization at the v5 role delivery boundary."""

from __future__ import annotations

from copy import deepcopy

import pytest

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.role_candidates import normalize_model_candidate


def _candidate(*, item_count: int = 1) -> dict:
    return {
        "schema_version": "r3-0-009-unified-graph/v2",
        "scenario_id": "scenario-1",
        "candidate_id": "candidate-1",
        "revision": 1,
        "items": [
            {
                "item_id": f"item-{index}",
                "item_kind": "entity",
                "business_meaning": "placeholder meaning",
                "value": {"label": f"placeholder-{index}"},
                "slice_ids": ["slice-1"],
                "unknowns": [],
            }
            for index in range(item_count)
        ],
        "explicit_unknowns": [],
    }


def test_normalize_adds_only_missing_neutral_fields_for_the_143_item_batch():
    candidate = _candidate(item_count=143)
    original = deepcopy(candidate)

    normalized = normalize_model_candidate(candidate)

    assert normalized is not candidate
    assert candidate == original
    assert all(item["relation_endpoints"] is None for item in normalized["items"])
    assert all(item["shared_scope"] is None for item in normalized["items"])


def test_normalize_preserves_existing_endpoints_shared_scope_and_explicit_nulls():
    candidate = _candidate(item_count=3)
    candidate["items"][1].update(
        relation_endpoints={"from_item_id": "item-0", "to_item_id": "item-2"},
        shared_scope="shared-definition",
    )
    candidate["items"][2].update(relation_endpoints=None, shared_scope=None)
    original = deepcopy(candidate)

    normalized = normalize_model_candidate(candidate)

    assert normalized["items"][1]["relation_endpoints"] == {
        "from_item_id": "item-0",
        "to_item_id": "item-2",
    }
    assert normalized["items"][1]["shared_scope"] == "shared-definition"
    assert normalized["items"][2]["relation_endpoints"] is None
    assert normalized["items"][2]["shared_scope"] is None
    assert candidate == original


def test_normalize_none_candidate_returns_none():
    assert normalize_model_candidate(None) is None


def test_normalize_reports_missing_required_and_extra_fields_with_item_locations():
    candidate = _candidate(item_count=2)
    candidate["items"][0].pop("business_meaning")
    candidate["items"][1]["unapproved_field"] = "bad"

    with pytest.raises(FrameworkError) as caught:
        normalize_model_candidate(candidate)

    assert caught.value.code == "model_candidate_invalid"
    assert caught.value.detail["errors"] == [
        {
            "code": "unified_schema_mismatch",
            "path": "/items/0",
            "item_id": "item-0",
            "message": (
                "candidate item fields drift from the contract at "
                "index 0 (item_id='item-0'): "
                "missing fields ['business_meaning']; unexpected fields []"
            ),
        },
        {
            "code": "unified_schema_mismatch",
            "path": "/items/1",
            "item_id": "item-1",
            "message": (
                "candidate item fields drift from the contract at "
                "index 1 (item_id='item-1'): "
                "missing fields []; unexpected fields ['unapproved_field']"
            ),
        },
    ]
