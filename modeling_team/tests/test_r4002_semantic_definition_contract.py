"""Neutral authoring references and unified approval inputs for R4.0-002."""

import json
from pathlib import Path

from modeling_team.protocol_mechanics import _translate_definition_relation
from modeling_team.staged_decisions import validate_unified_candidate

ROOT = Path(__file__).resolve().parents[2]


def test_role_visible_contract_agrees_with_protocol_authoring_contract():
    contracts = [
        json.loads((ROOT / "modeling_team/references" / name).read_text())
        for name in (
            "platform-neutral-candidate-authoring.json",
            "r4-0-012-modeling-contract.json",
        )
    ]
    assert (
        contracts[0]["multiview_semantic_definition"]
        == contracts[1]["multiview_semantic_definition"]
    )
    assert contracts[1]["unified_candidate"]["item_optional_fields"] == ["semantic_definition"]


def test_unified_candidate_preserves_optional_declaration_without_opening_field_set():
    item = dict(
        item_id="object",
        item_kind="entity",
        business_meaning="shared",
        value=None,
        relation_endpoints=[],
        slice_ids=["slice"],
        shared_scope=None,
        unknowns=[],
    )
    value = dict(
        schema_version="r3-0-009-unified-graph/v2",
        scenario_id="scenario",
        candidate_id="candidate",
        revision=1,
        items=[item],
        explicit_unknowns=[],
    )
    assert validate_unified_candidate(value) == ()
    item["semantic_definition"] = {"semantic_role": "object", "business_meaning": "shared"}
    assert validate_unified_candidate(value) == ()
    item["unapproved_field"] = "bad"
    assert validate_unified_candidate(value)[0].reason_code == "unified_schema_mismatch"


def test_definition_reference_keeps_receipt_bound_existing_endpoint():
    _, payload = _translate_definition_relation(
        {
            "subject": {"existing_entity_ref": {"semantic_id": "old", "expected_class": "Thing"}},
            "predicate": "usesDefinition",
            "object": {"definition_ref": "shared"},
        },
        set(),
        {"usesDefinition": {"predicate_kind": "relation"}},
        {"shared": "http://example.org/platform-created/class/shared"},
        {"old": "http://example.org/platform-created/entity/old"},
    )
    assert payload["source_entity_iri"] == "http://example.org/platform-created/entity/old"
    assert payload["target_entity_iri"] == "http://example.org/platform-created/class/shared"
