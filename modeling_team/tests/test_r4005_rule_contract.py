"""Rule declarations agree across active Modeling, Protocol and Batch contracts."""

import json
from pathlib import Path

from modeling_team.staged_decisions import validate_unified_candidate
from test_r4004_process_contract import (
    test_active_role_inputs_include_process_contract_and_complete_example as _check_mounted_inputs,
)

ROOT = Path(__file__).resolve().parents[2]


def test_rule_contracts_match_and_unified_candidate_fields_stay_closed():
    refs = ROOT / "modeling_team/references"
    authoring, role, unified, batch = [json.loads((refs / name).read_text()) for name in (
        "platform-neutral-candidate-authoring.json", "r4-0-012-modeling-contract.json",
        "r3-0-009-unified-graph-contract.json", "modeling-batch-item-contract.json",
    )]
    assert authoring["business_rule_semantics"] == role["business_rule_semantics"]
    assert role["unified_candidate"]["item_optional_fields"] == unified["candidate"]["item_optional_fields"]
    for section, command in (("create_payloads", "create_entity"),
                             ("update_payloads", "update_entity")):
        assert "rule_definition" in batch[section][command]["fields"]
    item = dict(item_id="rule", item_kind="entity", business_meaning="eligibility",
                value=None, relation_endpoints=[], slice_ids=["slice"], shared_scope=None,
                unknowns=[], rule_definition={"kind": "judgment_constraint"})
    value = dict(schema_version="r3-0-009-unified-graph/v2", scenario_id="scenario",
                 candidate_id="candidate", revision=1, items=[item], explicit_unknowns=[])
    assert validate_unified_candidate(value) == ()
    item["unapproved_field"] = "bad"
    assert validate_unified_candidate(value)[0].reason_code == "unified_schema_mismatch"


def test_active_instructions_expose_rule_contract_without_execution():
    # Reuse the existing mounted-source check; same source carries both contracts.
    _check_mounted_inputs()
    for role in ("modeling", "protocol"):
        instructions = (ROOT / f"modeling_team/agent-packages/{role}/instructions.md").read_text()
        assert "business_rule_semantics" in instructions
        assert "rule_definition" in instructions


def test_current_rule_contract_declares_platform_retirement_and_external_execution():
    for filename in ("platform-neutral-candidate-authoring.json", "r4-0-012-modeling-contract.json"):
        contract = json.loads((ROOT / "modeling_team/references" / filename).read_text())
        section = json.dumps(contract["business_rule_semantics"])
        assert "ordinary entity rule_definition annotations" in section
        assert "never runs or materializes business rules" in section
        assert "Rule Definitions, Rule Runs and rule-result generation are retired" in section
        assert "platform semantic_rule_definition/Rule Run" not in section
