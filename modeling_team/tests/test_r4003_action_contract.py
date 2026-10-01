"""Role-visible, neutral and unified authoring contracts agree for Actions."""

import json
from pathlib import Path

from modeling_team.staged_decisions import validate_unified_candidate

ROOT = Path(__file__).resolve().parents[2]


def test_role_and_protocol_contracts_match_and_unified_fields_remain_closed():
    authoring, role, unified, batch = [
        json.loads((ROOT / "modeling_team/references" / name).read_text())
        for name in (
            "platform-neutral-candidate-authoring.json", "r4-0-012-modeling-contract.json",
            "r3-0-009-unified-graph-contract.json", "modeling-batch-item-contract.json",
        )
    ]
    assert authoring["reusable_action_semantics"] == role["reusable_action_semantics"]
    assert role["unified_candidate"]["item_optional_fields"] == unified["candidate"]["item_optional_fields"]
    for field in ("action_definition", "parameter_definition"):
        assert field in batch["create_payloads"]["create_entity"]["fields"]
    item = dict(item_id="action", item_kind="entity", business_meaning="reusable",
                value=None, relation_endpoints=[], slice_ids=["slice"], shared_scope=None,
                unknowns=[], action_definition={"output_status": "none"})
    value = dict(schema_version="r3-0-009-unified-graph/v2", scenario_id="scenario",
                 candidate_id="candidate", revision=1, items=[item], explicit_unknowns=[])
    assert validate_unified_candidate(value) == ()
    item["parameter_definition"] = {"direction": "input", "cardinality": "collection"}
    assert validate_unified_candidate(value) == ()
    item["unapproved_field"] = "bad"
    assert validate_unified_candidate(value)[0].reason_code == "unified_schema_mismatch"
