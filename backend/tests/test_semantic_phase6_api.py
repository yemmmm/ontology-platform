"""Phase 6 graph-derived API integration tests."""

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.semantic import router
from app.core.config import Settings
from app.repositories.models import (
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)


def _seed_graph_set(session: Session, graph_iris: list[str]) -> None:
    gs = SemanticGraphSetModel(
        id="gs-1",
        name="demo",
        scope_type="ontology_version",
        scope_id="ov-1",
        status="active",
        source_signature="sig-1",
    )
    session.add(gs)
    for idx, iri in enumerate(graph_iris):
        gs.members.append(
            SemanticGraphSetMemberModel(
                id=f"m-{idx}",
                graph_iri=iri,
                role="asserted_data" if idx == 0 else "shape",
                required=True,
                sort_order=idx,
            )
        )
    session.commit()


class FakeStore:
    """Test double for RdfStoreRepository.

    Returns canned TriG payloads for known graph IRIs and canned rows for
    read-model templates. The rows are plain dicts (not SPARQL JSON binding
    form) — the read-model service tolerates both.
    """

    def __init__(
        self,
        graphs: dict[str, str] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._graphs = graphs or {}
        self._rows = rows or []
        self.last_query: str | None = None
        self.last_graph_iris: list[str] | None = None

    def get_graph(self, iri, fmt):
        return self._graphs.get(iri, "")

    def query_read_model(self, query, graph_iris, timeout_seconds, limit):
        self.last_query = query
        self.last_graph_iris = list(graph_iris)

        class _Result:
            bindings = self._rows

        return _Result()

    def query_sparql(self, query, timeout_seconds, limit):
        # Existing service paths still call this; return empty results.
        return {"results": {"bindings": []}}


def _client(
    store: FakeStore,
    session: Session,
    settings: Settings | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    settings = settings or Settings()

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_read_model_endpoint_returns_envelope(in_memory_session):
    _seed_graph_set(in_memory_session, ["http://op/s/graph/data/ov-1"])
    store = FakeStore(
        rows=[
            {
                "class": "http://op/s/class/x",
                "label": "X",
                "graph": "http://op/s/graph/data/ov-1",
            }
        ]
    )
    client = _client(store, in_memory_session)
    response = client.get(
        "/api/semantic/graph-sets/gs-1/read-models/ontology-schema-summary",
        params={"include": "asserted"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["graph_set_id"] == "gs-1"
    assert body["items"][0]["assertion_kind"] == "asserted"
    assert body["items"][0]["source_graph_iri"] == "http://op/s/graph/data/ov-1"


def test_read_model_unknown_returns_400(in_memory_session):
    _seed_graph_set(in_memory_session, ["http://op/s/graph/data/ov-1"])
    client = _client(FakeStore(), in_memory_session)
    response = client.get(
        "/api/semantic/graph-sets/gs-1/read-models/no-such-model",
    )
    assert response.status_code == 400


def test_export_endpoint_returns_trig(in_memory_session):
    _seed_graph_set(in_memory_session, ["http://op/s/graph/data/ov-1"])
    store = FakeStore(
        graphs={
            "http://op/s/graph/data/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/data/ov-1> { ex:a ex:b ex:c . }\n"
        }
    )
    client = _client(store, in_memory_session)
    response = client.get(
        "/api/semantic/graph-sets/gs-1/export",
        params={"format": "trig"},
    )
    assert response.status_code == 200
    assert "application/trig" in response.headers["content-type"]


def test_export_turtle_rejects_multi_graph(in_memory_session):
    # Seed two graphs both as asserted_data so the export sees both.
    gs = SemanticGraphSetModel(
        id="gs-1",
        name="demo",
        scope_type="ontology_version",
        scope_id="ov-1",
        status="active",
        source_signature="sig-1",
    )
    in_memory_session.add(gs)
    for idx, iri in enumerate(
        [
            "http://op/s/graph/data/ov-1",
            "http://op/s/graph/ontology/ov-1",
        ]
    ):
        gs.members.append(
            SemanticGraphSetMemberModel(
                id=f"m-{idx}",
                graph_iri=iri,
                role="asserted_data",
                required=True,
                sort_order=idx,
            )
        )
    in_memory_session.commit()
    store = FakeStore(
        graphs={
            "http://op/s/graph/data/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/data/ov-1> { ex:a ex:b ex:c . }\n",
            "http://op/s/graph/ontology/ov-1": "@prefix ex: <http://example.test/> .\n<http://op/s/graph/ontology/ov-1> { ex:x ex:y ex:z . }\n",
        }
    )
    client = _client(store, in_memory_session)
    response = client.get(
        "/api/semantic/graph-sets/gs-1/export",
        params={"format": "turtle"},
    )
    assert response.status_code == 400


def test_projection_job_lifecycle(in_memory_session):
    _seed_graph_set(in_memory_session, ["http://op/s/graph/data/ov-1"])
    client = _client(FakeStore(), in_memory_session)

    create = client.post(
        "/api/semantic/graph-sets/gs-1/projection-jobs",
        json={
            "graph_set_id": "gs-1",
            "projection_kind": "search",
            "projection_version": "search-v1",
            "include": "asserted",
            "mode": "rebuild",
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    run = client.post(f"/api/semantic/projection-jobs/{job_id}:run")
    assert run.status_code == 200
    assert run.json()["status"] == "succeeded"

    status = client.get(
        "/api/semantic/projections/status", params={"graph_set_id": "gs-1"}
    )
    assert status.status_code == 200
    assert any(m["projection_kind"] == "search" for m in status.json()["manifests"])


def test_projection_reconcile_endpoint(in_memory_session):
    _seed_graph_set(in_memory_session, ["http://op/s/graph/data/ov-1"])
    client = _client(FakeStore(), in_memory_session)
    response = client.post("/api/semantic/projections:reconcile")
    assert response.status_code == 200
    assert "reconciled" in response.json()


def test_list_projection_jobs_filters_by_kind(in_memory_session):
    _seed_graph_set(in_memory_session, ["http://op/s/graph/data/ov-1"])
    client = _client(FakeStore(), in_memory_session)
    for kind, version in [("search", "search-v1"), ("vector", "vector-v1")]:
        create = client.post(
            "/api/semantic/graph-sets/gs-1/projection-jobs",
            json={
                "graph_set_id": "gs-1",
                "projection_kind": kind,
                "projection_version": version,
                "mode": "dry_run",
            },
        )
        assert create.status_code == 201
    response = client.get(
        "/api/semantic/projection-jobs", params={"projection_kind": "search"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["projection_kind"] == "search"
