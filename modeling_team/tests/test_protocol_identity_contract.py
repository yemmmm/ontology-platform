"""Mounted Protocol identity guidance agrees with the current constructors."""

import json
import inspect
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.modeling_handlers import ALLOWED_FIELDS, ModelingCommandHandlerRegistry
from modeling_team.staged_decisions import build_identity_binding, unified_identity_issue


REFERENCES = Path(__file__).resolve().parents[1] / "references"


@pytest.mark.parametrize("identity_field", ["property_id", "property_iri"])
@pytest.mark.parametrize("description", [None, "", "Approved revised description"])
def test_documented_property_update_preserves_identity_and_only_changes_comment(
    identity_field, description
):
    from app.services.semantic_export import namespace_from_settings

    contract = json.loads((REFERENCES / "modeling-batch-item-contract.json").read_text())
    schema = contract["update_payloads"]["update_property"]
    assert set(schema["fields"]) == ALLOWED_FIELDS["update_property"]
    binding_rule = schema["rules"][1]
    for required in (
        "existing identity binding carries a resource_iri",
        "property_iri with that exact value, not a short property_id",
        "property_id remains valid",
        "ID-based and the ID matches",
    ):
        assert required in binding_rule
    settings = Settings()
    property_iri = str(namespace_from_settings(settings).resource("property", "existing-example"))
    payload = {
        identity_field: "existing-example" if identity_field == "property_id" else property_iri,
        "description": description,
    }
    prepared = ModelingCommandHandlerRegistry(settings).prepare(
        batch_id="batch-example", ontology_id="ontology-example",
        client_item_id="update-example", command_kind="update_property", payload=payload,
    )
    compiled = prepared.compiled
    assert prepared.outputs == {}  # update does not allocate a new resource
    assert compiled.metadata["property_iri"] == property_iri
    delta = compiled.delta
    assert all(subject == f"<{property_iri}>" for subject, _, _, _ in [*delta.inserts, *delta.deletes])
    assert {predicate for _, predicate, _, _ in [*delta.inserts, *delta.deletes]} == (
        set() if description is None else {"<http://www.w3.org/2000/01/rdf-schema#comment>"}
    )
    assert len(delta.deletes) == (0 if description is None else 1)
    assert len(delta.inserts) == (1 if description else 0)


def test_documented_property_reads_match_registered_governed_tool_fields():
    from app.api.modeling_batches import READ_MODEL_NAMES
    from app.mcp.tools.semantic import register_semantic
    from app.services.scoped_sparql_query import validate_read_only_query
    from app.services.semantic_sparql_templates import get_template

    tools = {}

    class ToolCatalog:
        def tool(self):
            def register(function):
                tools[function.__name__] = function
                return function
            return register

    register_semantic(ToolCatalog())
    contract = json.loads((REFERENCES / "modeling-batch-item-contract.json").read_text())
    reads = contract["property_read_contract"]
    for route in (reads["listing"], reads["exact_definition"]):
        parameters = inspect.signature(tools[route["tool"]]).parameters
        assert set(route["fields"]) == set(parameters)
        assert set(route["required"]) == {
            name for name, parameter in parameters.items() if parameter.default is inspect.Parameter.empty
        }
    listing = reads["listing"]
    assert listing["model_name"] == "property-list"
    assert listing["include"] == "asserted"
    assert "property-list" not in READ_MODEL_NAMES
    assert get_template(listing["model_name"]).required_roles == ("asserted_ontology",)
    assert validate_read_only_query(reads["exact_definition"]["query_example"]) == "select"
    assert "only when advertised" in reads["availability"]
    assert "original scoped HTTP read envelope" in reads["availability"]

    from app.api.semantic import router
    routes = {(route.path, method) for route in router.routes for method in route.methods}
    for route in (reads["listing"], reads["exact_definition"]):
        http = route["http"]
        path = http["path"].removeprefix("/api")
        if route is listing:
            path = path.removesuffix("property-list") + "{model_name}"
        assert (path, http["method"]) in routes
    listing_endpoint = next(
        route.endpoint for route in router.routes
        if route.path == "/semantic/graph-sets/{graph_set_id}/read-models/{model_name}"
    )
    parameters = inspect.signature(listing_endpoint).parameters
    assert set(listing["http"]["query_example"]) <= set(parameters)
    assert listing["http"]["identity_filter_parameter"] == "entity"
    assert "entity" in parameters


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
