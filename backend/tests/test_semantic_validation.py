from pathlib import Path

from app.core.config import Settings
from app.services.semantic import SemanticService


DATA_GRAPH = "http://ontology-platform.local/semantic/graph/data/demo"
SHAPE_GRAPH = "http://ontology-platform.local/semantic/graph/shapes/demo"


class FakeSession:
    def add(self, obj) -> None:
        self.obj = obj

    def commit(self) -> None:
        pass

    def scalar(self, statement):
        return None


class FakeStore:
    def get_graph(self, graph_iri, format):
        if graph_iri == DATA_GRAPH:
            return "@prefix ex: <http://example.test/> . ex:alice a ex:Person ."
        return Path("tests/fixtures/semantic/tiny-shapes.ttl").read_text(encoding="utf-8")


def test_shacl_validation_reports_non_conformance() -> None:
    service = SemanticService(FakeSession(), FakeStore(), Settings())

    result = service.run_validation([DATA_GRAPH], [SHAPE_GRAPH])

    assert result["status"] == "succeeded"
    assert result["conforms"] is False
    assert result["summary"]["violations"] == 1
