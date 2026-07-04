from app.core.config import Settings
from app.repositories.rdf_store import UpdateResult
from app.services.owl_reasoner import OwlReasonerResult, OwlReasonerRunner
from app.services.semantic import SemanticService


GRAPH = "http://ontology-platform.local/semantic/graph/ontology/demo"


class FakeSession:
    def add(self, obj) -> None:
        self.obj = obj

    def commit(self) -> None:
        pass

    def scalar(self, statement):
        return None


class FakeStore:
    def __init__(self) -> None:
        self.updates = []

    def get_graph(self, graph_iri, format):
        return "@prefix ex: <http://example.test/> . ex:Student a ex:Person ."

    def update_sparql(self, update):
        self.updates.append(update)
        return UpdateResult()


class FakeReasoner(OwlReasonerRunner):
    def run(self, source_documents, tasks, timeout_seconds):
        return OwlReasonerResult(
            consistent=True,
            classification={"classes": ["http://example.test/Student"]},
            entailments=[{"subject": "ex:Student", "predicate": "rdfs:subClassOf", "object": "ex:Person"}],
            inferred_rdf="@prefix ex: <http://example.test/> . ex:alice a ex:Person .",
        )


def test_reasoning_can_persist_result_graph_without_source_mutation() -> None:
    store = FakeStore()
    service = SemanticService(FakeSession(), store, Settings(), reasoner=FakeReasoner())

    result = service.run_reasoning([GRAPH], ["consistency"], persist_result_graph=True)

    assert result["status"] == "succeeded"
    assert result["consistent"] is True
    assert "reasoning-result" in result["result_graph_iri"]
    assert len(store.updates) == 1
    assert GRAPH not in store.updates[0]
