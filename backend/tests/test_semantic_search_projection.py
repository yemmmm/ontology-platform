from app.services.semantic_read_scope import ScopeResolution
from app.services.semantic_search_projection import (
    FakeSearchWriter,
    SemanticSearchProjectionService,
)


class FakeStore:
    def get_graph(self, iri, fmt):
        return """
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix ex: <http://example.test/> .
        <http://op/s/graph/ontology/ov-1> {
          ex:alice rdfs:label "Alice" ;
                   rdfs:comment "A student" .
        }
        """


def _scope(iris, derived_state=None):
    return ScopeResolution(
        ontology_id="gs-1",
        model_revision=1,
        include="asserted",
        model_graph_iris=iris, shape_graph_iris=[],

        governance_graph_iris=[],
        reasoning_result_graph_iri=None,
        derived_state=derived_state or {},
        warnings=[],
    )


def test_search_documents_include_label_assertion_kind_and_signature():
    writer = FakeSearchWriter()
    service = SemanticSearchProjectionService(rdf_store=FakeStore(), writer=writer)
    counts = service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/ontology/ov-1"]),
        partition="gs-1/search/search-v1",
    )
    assert counts["document_count"] == 1
    doc = writer.docs[0]
    assert doc["iri"] == "http://example.test/alice"
    assert doc["assertion_kind"] == "asserted"
    assert doc["model_graph_iri"] == "http://op/s/graph/ontology/ov-1"
    assert doc["model_revision"] == 1
    assert doc["ontology_id"] == "gs-1"
    assert "Alice" in doc["text"]


def test_search_documents_ignore_historical_reasoning_staleness():
    writer = FakeSearchWriter()
    service = SemanticSearchProjectionService(rdf_store=FakeStore(), writer=writer)
    scope = _scope(["http://op/s/graph/ontology/ov-1"])
    scope.derived_state["reasoning"] = {"status": "stale"}
    service.rebuild(
        job_id="job-1",
        scope=scope,
        partition="gs-1/search/search-v1",
    )
    assert writer.docs[0]["is_stale"] is False


def test_search_writer_clear_called_before_write():
    writer = FakeSearchWriter()
    writer.docs.append({"stale": True})
    service = SemanticSearchProjectionService(rdf_store=FakeStore(), writer=writer)
    service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/ontology/ov-1"]),
        partition="gs-1/search/search-v1",
    )
    assert all("stale" not in d for d in writer.docs)
