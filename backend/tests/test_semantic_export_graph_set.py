import json

from app.services.semantic_graph_set_export import (
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

    def resolve(self, graph_set_id, include="asserted", allow_stale_derived=True):
        from dataclasses import replace

        return replace(self._resolution, include=include)


def _resolution(source_iris, reasoning=None, rule=None):
    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature="sig-1",
        include="asserted",
        source_graph_iris=source_iris,
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=reasoning,
        rule_result_graph_iri=rule,
        derived_state={},
        warnings=[],
    )


def test_trig_export_preserves_named_graph_boundaries():
    store = FakeStore(
        {
            "http://op/s/graph/ontology/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/ontology/ov-1> { ex:a ex:b ex:c . }\n",
            "http://op/s/graph/data/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/data/ov-1> { ex:x ex:y ex:z . }\n",
        }
    )
    resolver = FakeScopeResolver(
        _resolution(
            [
                "http://op/s/graph/ontology/ov-1",
                "http://op/s/graph/data/ov-1",
            ]
        )
    )
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, warnings = service.export("gs-1", format="trig", include="asserted")
    assert "ontology/ov-1" in payload
    assert "data/ov-1" in payload


def test_turtle_rejects_multi_graph_without_merged_profile():
    store = FakeStore(
        {
            "http://op/s/graph/ontology/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/ontology/ov-1> { ex:a ex:b ex:c . }\n",
            "http://op/s/graph/data/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/data/ov-1> { ex:x ex:y ex:z . }\n",
        }
    )
    resolver = FakeScopeResolver(
        _resolution(
            [
                "http://op/s/graph/ontology/ov-1",
                "http://op/s/graph/data/ov-1",
            ]
        )
    )
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    try:
        service.export("gs-1", format="turtle", include="asserted")
        raise AssertionError("expected ExportError")
    except ExportError as exc:
        assert "merged" in str(exc).lower() or "single" in str(exc).lower()


def test_turtle_allows_single_graph():
    store = FakeStore(
        {
            "http://op/s/graph/data/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/data/ov-1> { ex:a ex:b ex:c . }\n"
        }
    )
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/data/ov-1"]))
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, _ = service.export("gs-1", format="turtle", include="asserted")
    assert "http://example.test/" in payload
    assert ":a" in payload and ":b" in payload and ":c" in payload


def test_json_ld_export_compacts_with_projection_terms():
    store = FakeStore(
        {"http://op/s/graph/data/ov-1": '@prefix ex: <http://example.test/> . ex:alice ex:name "Alice" .'}
    )
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/data/ov-1"]))
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, _ = service.export("gs-1", format="json-ld", include="asserted")
    parsed = json.loads(payload)
    assert "@context" in parsed
    assert "assertionKind" in parsed["@context"]


def test_warns_on_stale_reasoning_when_requested():
    store = FakeStore({"http://op/s/graph/rr/run-1": "@prefix ex: <http://example.test/> . ex:x ex:y ex:z ."})
    scope = _resolution(
        ["http://op/s/graph/data/ov-1"],
        reasoning="http://op/s/graph/rr/run-1",
    )
    scope.derived_state["reasoning"] = {
        "status": "stale",
        "run_id": "run-1",
        "result_graph_iri": "http://op/s/graph/rr/run-1",
    }
    scope.warnings = [
        {"code": "stale_reasoning_result", "message": "stale"}
    ]
    resolver = FakeScopeResolver(scope)
    service = SemanticExportService(rdf_store=store, scope_resolver=resolver, settings=None)
    payload, warnings = service.export(
        "gs-1",
        format="trig",
        include="asserted-plus-reasoning",
        allow_stale_derived=True,
    )
    assert any(w["code"] == "stale_reasoning_result" for w in warnings)


def test_export_filters_restricted_graphs_via_visibility_policy():
    from app.services.semantic_visibility import SemanticVisibilityPolicy

    store = FakeStore(
        {
            "http://op/s/graph/data/a": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/data/a> { ex:a ex:b ex:c . }\n",
            "http://op/s/graph/data/b": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/data/b> { ex:x ex:y ex:z . }\n",
        }
    )
    resolver = FakeScopeResolver(
        _resolution(
            ["http://op/s/graph/data/a", "http://op/s/graph/data/b"]
        )
    )
    policy = SemanticVisibilityPolicy(
        graph_labels={"http://op/s/graph/data/b": "restricted"}
    )
    service = SemanticExportService(
        rdf_store=store,
        scope_resolver=resolver,
        settings=None,
        visibility_policy=policy,
    )
    payload, warnings = service.export(
        "gs-1",
        format="trig",
        include="asserted",
        visibility_context={"labels": ["internal"]},
    )
    assert "data/a" in payload
    assert "data/b" not in payload
    assert any(w["code"] == "visibility_graph_omitted" for w in warnings)
