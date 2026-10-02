"""Mounted Protocol identity guidance agrees with the current constructors."""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.modeling_handlers import ModelingCommandHandlerRegistry
from modeling_team.staged_decisions import build_identity_binding, unified_identity_issue


REFERENCES = Path(__file__).resolve().parents[1] / "references"


def test_identity_binding_examples_use_string_locator_and_exact_constructor_shape():
    contract = json.loads((REFERENCES / "r3-0-009-unified-graph-contract.json").read_text())
    section = contract["materialization_plan"]
    examples = section["identity_binding_examples"]
    for name in ("future_create", "existing_resource"):
        example = examples[name]
        assert set(example) == set(section["identity_binding_fields"])
        assert build_identity_binding(**example) == example
    assert isinstance(examples["future_create"]["receipt_ref"], str)
    assert examples["future_create"]["resource_iri"] is None
    assert examples["future_create"]["evidence_ref"] is None


def test_future_locator_is_a_string_and_candidate_id_need_not_equal_payload_id():
    contract = json.loads((REFERENCES / "r3-0-009-unified-graph-contract.json").read_text())
    identity = dict(contract["materialization_plan"]["identity_binding_examples"]["future_create"])
    projection = {
        "identity_bindings": [identity],
        "items": [{"command_kind": "create_entity", "payload": {"entity_id": "different-id"}}],
        "decision_bindings": [{"command_index": 0, "candidate_item_ids": ["neutral-item"]}],
    }
    published = {"neutral-item": {"item_kind": "entity"}}
    assert unified_identity_issue(projection, published) is None
    identity["receipt_ref"] = {"plan": "example", "item": "create-example"}
    assert (
        unified_identity_issue(projection, published).reason_code == "missing_candidate_reference"
    )
    identity["receipt_ref"] = "plan-example/batch-example/create-item-example"
    identity["resource_id"] = "different-id"
    assert (
        unified_identity_issue(projection, published).reason_code == "missing_candidate_reference"
    )


@pytest.mark.parametrize(
    "kind,id_field,payload",
    [
        ("create_class", "class_id", {"name": "Example class"}),
        ("create_property", "property_id", {"name": "Example property", "datatype": "string"}),
        ("create_relation_type", "relation_type_id", {"name": "Example relation"}),
        ("create_shape", "shape_id", {}),
        ("create_entity", "entity_id", {"label": "Example entity"}),
    ],
)
def test_documented_create_id_preservation_and_default_output(kind, id_field, payload):
    contract = json.loads((REFERENCES / "modeling-batch-item-contract.json").read_text())
    fields = contract["create_payloads"][kind]["fields"]
    assert "resource_id" not in fields
    assert "preserved" in fields[id_field]["server_behavior"]
    registry = ModelingCommandHandlerRegistry(Settings())
    args = dict(
        batch_id="batch-example",
        ontology_id="ontology-example",
        client_item_id="command-example",
        command_kind=kind,
    )
    supplied = registry.outputs_for(**args, payload={**payload, id_field: "explicit-resource-id"})
    assert supplied["resource_id"] == "explicit-resource-id"
    generated = registry.outputs_for(**args, payload=payload)
    assert generated == registry.outputs_for(**args, payload=payload)
    assert generated["resource_id"] != "explicit-resource-id"
