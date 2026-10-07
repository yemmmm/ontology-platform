"""Generic resource composition reuses authorized family projections."""

import json
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_read_model import SemanticReadModelService
from test_semantic_read_model import FakeScopeResolver, FakeStore, _resolution


def test_resource_list_shared_identity_annotations_multiclass_and_protection():
    graph = "http://op/s/graph/data/a"
    iri = "http://op/s/entity/shared"
    hidden = "http://op/s/entity/hidden"
    store = FakeStore(
        {
            "template: entity-list": [
                {
                    "entity": iri,
                    "semantic_id": "shared",
                    "label": "Shared",
                    "class": c,
                    "graph": graph,
                    "semantic_definition": json.dumps({"semantic_role": "action"}),
                    "action_definition": json.dumps({"input_status": "unknown"}),
                }
                for c in ("urn:Class1", "urn:Class2")
            ]
            + [{"entity": hidden, "semantic_id": "hidden", "label": "HIDDEN", "graph": graph}],
            "template: schema-summary": [{"class": iri, "label": "Shared", "graph": graph}],
        }
    )
    access = SemanticAccessView(requires_filtering=True, _unauthorized_iris=frozenset({hidden}))
    service = SemanticReadModelService(
        store, FakeScopeResolver(_resolution([graph])), access_view=access
    )
    result = service.read_model("gs-1", "resource-list", field_set="full")
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["iri"] == iri
    assert item["class_iris"] == ["urn:Class1", "urn:Class2"]
    assert item["detail_fields"]["semantic_definition"]["semantic_role"] == "action"
    assert item["detail_fields"]["action_definition"]["input_status"] == "unknown"
    assert result["paging"]["visible_count"] == 1
    assert "HIDDEN" not in json.dumps(result)


def test_resource_list_no_class_and_bound_does_not_claim_complete():
    graph = "http://op/s/graph/data/a"
    store = FakeStore(
        {
            "template: entity-list": [
                {
                    "entity": f"urn:entity:{i}",
                    "semantic_id": str(i),
                    "label": str(i),
                    "graph": graph,
                }
                for i in range(3)
            ]
        }
    )
    service = SemanticReadModelService(store, FakeScopeResolver(_resolution([graph])))
    result = service.read_model("gs-1", "resource-list", limit=1)
    assert len(result["items"]) == 1 and result["items"][0]["class_iris"] == []
    assert not result["paging"]["complete"]


def test_operation_resource_list_preserves_exact_binding_and_rejects_secrets():
    from app.core.config import Settings
    from app.services.operation_semantics import canonical_operation_iri
    from test_operation_semantics import _operation

    settings = Settings()
    graph = "http://op/s/graph/ontology/a"
    definition = _operation()
    iri = canonical_operation_iri(settings, definition["operation_id"])

    def row(payload, resource=iri):
        return {
            "operation": resource,
            "label": payload["name"],
            "graph": graph,
            **{
                key: json.dumps(value) if isinstance(value, (list, dict)) else value
                for key, value in payload.items()
                if key not in {"name", "aliases"}
            },
        }

    evil = _operation(tool_bindings=[{"token": "never-return-credential"}])
    store = FakeStore({"template: operation-list": [row(definition), row(evil, "urn:bad")]})
    resolver = FakeScopeResolver(_resolution([graph]))
    resolver.settings = settings
    service = SemanticReadModelService(store, resolver)
    result = service.read_model("gs-1", "resource-list", field_set="full")
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["iri"] == iri
    assert item["detail_fields"]["tool_bindings"][0]["binding_id"] == "generic-http-publish"
    assert item["detail_fields"]["parameters"][0]["name"] == "workflow_id"
    assert "never-return-credential" not in json.dumps(result)
    store.rows_by_template = {"template: operation-detail": [row(definition)]}
    exact = service.read_model("gs-1", "operation-detail", entity_iri=iri)
    assert exact["items"][0]["iri"] == iri


def test_operation_templates_execute_real_rdf_with_custom_namespace():
    from types import SimpleNamespace
    from rdflib import Dataset, URIRef
    from rdflib.util import from_n3
    from app.services.operation_semantics import operation_quads, canonical_operation_iri
    from test_operation_semantics import _operation, _settings

    settings = _settings()
    dataset = Dataset()
    definition = _operation()
    quads = operation_quads(definition, settings, "o")
    for s, p, o, g in quads:
        dataset.graph(URIRef(g)).add((from_n3(s), from_n3(p), from_n3(o)))

    class Store:
        def query_read_model(self, query, **kwargs):
            result = dataset.query(query)
            return SimpleNamespace(
                bindings=[
                    {str(k): {"value": str(v)} for k, v in row.items()} for row in result.bindings
                ]
            )

    graph = quads[0][3]
    resolver = FakeScopeResolver(_resolution([graph]))
    resolver.settings = settings
    service = SemanticReadModelService(Store(), resolver)
    iri = canonical_operation_iri(settings, definition["operation_id"])
    assert service.read_model("gs-1", "resource-list")["items"][0]["iri"] == iri
    assert (
        service.read_model("gs-1", "operation-detail", entity_iri=iri)["items"][0]["detail_fields"][
            "tool_bindings"
        ][0]["binding_id"]
        == "generic-http-publish"
    )
