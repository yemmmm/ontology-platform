from app.repositories.rdf_store import RdfFormat
from app.services.semantic_projection import SemanticProjectionService


GRAPH = "http://ontology-platform.local/semantic/graph/data/demo"


class FakeStore:
    def get_graph(self, graph_iri, format):
        assert format == RdfFormat.TRIG.value
        return """
        @prefix ex: <http://example.test/> .
        <http://ontology-platform.local/semantic/graph/data/demo> {
          ex:alice ex:knows ex:bob .
        }
        """


def test_projection_counts_nodes_and_relationships_from_rdf() -> None:
    result = SemanticProjectionService(FakeStore()).rebuild([GRAPH], job_id="job")

    assert result.node_count == 2
    assert result.relationship_count == 1
