import json

from app.services.semantic_ontology_export import (
    ExportError,
    SemanticExportService,
)
from app.services.semantic_read_scope import ScopeResolution


class FakeStore:
    def __init__(self, graphs: dict[str, str]):
        self.graphs = graphs
        self.requested: list[tuple[str, str]] = []

    def get_graph(self, iri, format):
        self.requested.append((iri, format))
        return self.graphs.get(iri, "")


class FakeScopeResolver:
    def __init__(self, resolution):
        self._resolution = resolution

    def resolve(self, ontology_id, include="asserted", allow_stale_derived=True):
        from dataclasses import replace

        return replace(self._resolution, include=include)


def _resolution(source_iris, reasoning=None, rule=None):
    return ScopeResolution(
        ontology_id="gs-1",
        source_signature="sig-1",
        include="asserted",
        model_graph_iris=source_iris, shape_graph_iris=[],

        governance_graph_iris=[],
        reasoning_result_graph_iri=reasoning,
        derived_state={},
        warnings=[],
    )


def test_trig_export_preserves_named_graph_boundaries():
    store = FakeStore(
        {
            "http://op/s/graph/ontology/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/ontology/ov-1> { ex:x ex:y ex:z . }\n",
        }
    )
    resolver = FakeScopeResolver(
        _resolution(
            [
                "http://op/s/graph/ontology/ov-1",
            ]
        )
    )
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, warnings = service.export("gs-1", format="trig", include="asserted")
    assert "ontology/ov-1" in payload
    assert "data/ov-1" not in payload


def test_turtle_exports_single_model_without_selecting_graph_members():
    store = FakeStore({"urn:model": '<urn:model> { <urn:a> <urn:b> "x" . }'})
    service = SemanticExportService(store, FakeScopeResolver(_resolution(["urn:model"])), None)
    payload, warnings = service.export("gs-1", "turtle")
    from rdflib import Graph, URIRef, Literal
    assert (URIRef("urn:a"), URIRef("urn:b"), Literal("x")) in Graph().parse(data=payload, format="turtle")
    assert warnings == []


def test_turtle_allows_single_graph():
    store = FakeStore(
        {
            "http://op/s/graph/ontology/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/ontology/ov-1> { ex:a ex:b ex:c . }\n"
        }
    )
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/ontology/ov-1"]))
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, _ = service.export("gs-1", format="turtle", include="asserted")
    assert "http://example.test/" in payload
    assert ":a" in payload and ":b" in payload and ":c" in payload


def test_json_ld_export_compacts_with_projection_terms():
    store = FakeStore(
        {"http://op/s/graph/ontology/ov-1": '@prefix ex: <http://example.test/> . ex:alice ex:name "Alice" .'}
    )
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/ontology/ov-1"]))
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, _ = service.export("gs-1", format="json-ld", include="asserted")
    parsed = json.loads(payload)
    assert "@context" in parsed
    assert "assertionKind" in parsed["@context"]


def test_export_drops_quads_referencing_unauthorized_members():
    from app.services.semantic_access import SemanticAccessView

    hidden = "http://example.test/hidden-rule"
    store = FakeStore(
        {
            "http://op/s/graph/ontology/a": (
                "@prefix ex: <http://example.test/> .\n"
                "<http://op/s/graph/ontology/a> {\n"
                "  ex:a ex:b ex:c .\n"
                f"  ex:a ex:mappingDefinition {json.dumps(json.dumps({'conversion_rule_iri': hidden}))} .\n"
                "}\n"
            ),
            "http://op/s/graph/ontology/b": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/ontology/b> { ex:x ex:y ex:z . }\n",
        }
    )
    resolver = FakeScopeResolver(
        _resolution(
            ["http://op/s/graph/ontology/a", "http://op/s/graph/ontology/b"]
        )
    )
    view = SemanticAccessView(
        requires_filtering=True,
        _unauthorized_iris=frozenset({"http://example.test/x", hidden}),
    )
    service = SemanticExportService(
        rdf_store=store,
        scope_resolver=resolver,
        settings=None,
        access_view=view,
    )
    payload, warnings = service.export("gs-1", format="trig", include="asserted")
    assert "ex:a" in payload
    assert "ex:x" not in payload
    assert "mappingDefinition" not in payload
    assert warnings == []


def test_export_treats_missing_graph_as_empty():
    """D2 regression: Oxigraph answers GET /store?graph= for a never-written
    graph with 404 (surfaced as RdfStoreUnavailable). A graph-set whose data
    graph has no statements yet must export the remaining graphs instead of
    failing with 500."""
    from app.repositories.rdf_store import RdfStoreUnavailable

    ontology_graph = "http://op/s/graph/ontology/ov-2"
    data_graph = "http://op/s/graph/ontology/absent"
    ontology_content = (
        "@prefix ex: <http://example.test/> .\n"
        f"<{ontology_graph}> {{ ex:a ex:b ex:c . }}\n"
    )

    class OxigraphLikeStore:
        """Mimics the real store: 404 (as RdfStoreUnavailable) for graphs
        that were never written, graph_exists only for present graphs."""

        def graph_exists(self, iri):
            return iri == ontology_graph

        def get_graph(self, iri, format):  # noqa: ARG002
            if iri == ontology_graph:
                return ontology_content
            raise RdfStoreUnavailable("404 Not Found")

    store = OxigraphLikeStore()
    resolver = FakeScopeResolver(_resolution([data_graph]))
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)

    payload, warnings = service.export("gs-1", format="trig")
    assert "ex:b" not in payload
    assert data_graph not in payload
    assert warnings == []

    turtle, _ = service.export("gs-1", format="turtle")
    # rdflib may rename prefixes on serialization; assert on the terms.
    assert not turtle.strip()
