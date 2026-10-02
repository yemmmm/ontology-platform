"""Canonical mapping carriers in the mounted Protocol contract compile as declared."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.modeling_handlers import ALLOWED_FIELDS, ModelingCommandHandlerRegistry
from app.services.semantic_command_compiler import InvalidCommandPayload


REFERENCES = Path(__file__).resolve().parents[1] / "references"
KINDS = (
    "create_table_mapping",
    "create_join_mapping",
    "create_enum_meaning",
    "create_metric_definition",
)


def contract():
    return json.loads((REFERENCES / "modeling-batch-item-contract.json").read_text())


def prepare(kind, payload):
    registry = ModelingCommandHandlerRegistry(Settings())
    return registry.prepare(
        batch_id="example-batch",
        ontology_id="example-ontology",
        client_item_id="example-command",
        command_kind=kind,
        payload=payload,
    )


@pytest.mark.parametrize("kind", KINDS)
def test_advertised_fields_and_nested_example_match_real_prepare(kind):
    value = contract()
    schema = value["create_payloads"][kind]
    assert set(schema["fields"]) == ALLOWED_FIELDS[kind]
    payload = value["mapping_reference_binding"]["syntax_examples"][kind]
    assert set(schema["required"]) <= set(payload)
    result = prepare(kind, payload)
    assert result.compiled.delta.inserts
    assert result.outputs["resource_iri"]


@pytest.mark.parametrize(
    "kind,mutation,field",
    [
        (
            "create_table_mapping",
            lambda p: p.update(mapped_class_iri="https://example.test/class"),
            "exactly one",
        ),
        (
            "create_table_mapping",
            lambda p: p["column_mappings"][0].update(property_ref={"definition_ref": "x"}),
            "property_ref",
        ),
        (
            "create_join_mapping",
            lambda p: p["join_path"][0].update(source_table_ref={"definition_ref": "x"}),
            "exactly",
        ),
        ("create_enum_meaning", lambda p: p.pop("column"), "together"),
        (
            "create_enum_meaning",
            lambda p: p.update(property_ref={"definition_ref": "x"}),
            "property_ref",
        ),
        ("create_metric_definition", lambda p: p.update(aggregation="sum"), "measure_property_iri"),
        (
            "create_metric_definition",
            lambda p: p["mapping_definition"]["contexts"][0]["property_bindings"][0].update(
                table_mapping_ref={"definition_ref": "x"}
            ),
            "table_mapping_ref",
        ),
    ],
)
def test_neutral_aliases_and_incomplete_pairs_are_repairable_payload_errors(kind, mutation, field):
    payload = deepcopy(contract()["mapping_reference_binding"]["syntax_examples"][kind])
    mutation(payload)
    with pytest.raises(InvalidCommandPayload, match=field):
        prepare(kind, payload)


@pytest.mark.parametrize("kind", KINDS)
def test_schema_source_key_required_without_new_non_null_gate(kind):
    payload = deepcopy(contract()["mapping_reference_binding"]["syntax_examples"][kind])
    payload.pop("schema_source")
    with pytest.raises(InvalidCommandPayload, match="schema_source"):
        prepare(kind, payload)
    payload["schema_source"] = None
    assert prepare(kind, payload).compiled.delta.inserts
