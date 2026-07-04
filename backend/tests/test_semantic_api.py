from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.semantic import router
from app.core.config import Settings
from app.repositories.rdf_store import SparqlResult, UpdateResult


GRAPH = "http://ontology-platform.local/semantic/graph/data/demo"


class FakeSession:
    def add(self, obj) -> None:
        pass

    def commit(self) -> None:
        pass

    def scalar(self, statement):
        return None


class FakeStore:
    def __init__(self) -> None:
        self.updates = []

    def query_sparql(self, query, timeout_seconds, limit):
        return SparqlResult(result={"head": {"vars": ["s"]}, "results": {"bindings": []}})

    def update_sparql(self, update):
        self.updates.append(update)
        return UpdateResult()

    def export_dataset(self, format, graph_iris=None):
        return "@prefix ex: <http://example.test/> ."


def _client(store: FakeStore) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def session_override() -> Generator[FakeSession, None, None]:
        yield FakeSession()

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings()
    return TestClient(app)


def test_semantic_sparql_endpoint_rejects_write_query() -> None:
    client = _client(FakeStore())

    response = client.post("/api/semantic/sparql:query", json={"query": "DELETE DATA {}"})

    assert response.status_code == 400
    assert "Write SPARQL" in response.json()["detail"]


def test_semantic_edit_endpoint_applies_turtle_insert() -> None:
    store = FakeStore()
    client = _client(store)

    response = client.post(
        "/api/semantic/edits",
        json={
            "format": "turtle",
            "content": "@prefix ex: <http://example.test/> . ex:alice ex:name \"Alice\" .",
            "target_graph_iri": GRAPH,
            "validate": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["applied"] is True
    assert store.updates
