import hashlib

from app.services.semantic_read_scope import ScopeResolution
from app.services.semantic_vector_projection import (
    FakeVectorWriter,
    SemanticVectorProjectionService,
)


class FakeStore:
    def get_graph(self, iri, fmt):
        return """
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix ex: <http://example.test/> .
        ex:alice rdfs:label "Alice" ;
                 rdfs:comment "A student" .
        """


def _scope(iris):
    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature="sig-1",
        include="asserted",
        source_graph_iris=iris,
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=None,
        rule_result_graph_iri=None,
        derived_state={},
        warnings=[],
    )


def test_vector_documents_have_deterministic_ids_and_config_hash():
    writer = FakeVectorWriter()
    service = SemanticVectorProjectionService(
        rdf_store=FakeStore(),
        writer=writer,
        embedding_config={"model": "fake-embed", "version": "v1"},
    )
    counts = service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/vector/vector-v1",
    )
    assert counts["document_count"] == 1
    doc = writer.docs[0]
    expected_id = hashlib.sha256(
        f"gs-1|http://example.test/alice|resource|vector-v1".encode()
    ).hexdigest()
    assert doc["id"] == expected_id
    assert doc["embedding_config_hash"]
    assert doc["source_signature"] == "sig-1"
    assert doc["assertion_kind"] == "asserted"


def test_different_projection_version_changes_document_id():
    writer = FakeVectorWriter()
    service = SemanticVectorProjectionService(
        rdf_store=FakeStore(),
        writer=writer,
        embedding_config={"model": "fake-embed", "version": "v1"},
    )
    service.rebuild(
        job_id="job-1",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/vector/vector-v1",
    )
    first_id = writer.docs[0]["id"]
    writer.docs.clear()
    service2 = SemanticVectorProjectionService(
        rdf_store=FakeStore(),
        writer=writer,
        embedding_config={"model": "fake-embed", "version": "v2"},
    )
    service2.rebuild(
        job_id="job-2",
        scope=_scope(["http://op/s/graph/data/ov-1"]),
        partition="gs-1/vector/vector-v2",
    )
    assert writer.docs[0]["id"] != first_id
