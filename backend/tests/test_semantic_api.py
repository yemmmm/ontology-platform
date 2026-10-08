from single_model_support import seed_model
from sqlalchemy import func, select
import pytest
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
    OntologyModel,
    ProjectModel,
    SemanticEditAuditModel,
    SemanticGraphRegistryModel,
    SemanticProjectionManifestModel,
    SemanticReasoningRunModel,
    SemanticRuleRunModel,
    SemanticValidationRunModel,
)
from app.repositories.rdf_store import SparqlResult, UpdateResult


GRAPH = "http://ontology-platform.local/semantic/graph/ontology/demo"
RESULT_GRAPH = "http://ontology-platform.local/semantic/graph/reasoning-result/run-1"
TEST_PROJECT_ID = "semantic-api-project"
TEST_ONTOLOGY_ID = "semantic-api-ontology"


class FakeStore:
    def __init__(
        self,
        *,
        construct_result: str | None = None,
        select_result: dict[str, Any] | None = None,
    ) -> None:
        self.updates = []
        self.clears: list[str] = []
        self.queries: list[str] = []
        self._graphs: set[str] = set()
        self._stored: dict[str, str] = {}
        self._construct_result = construct_result
        self._select_result = select_result or {
            "head": {"vars": ["s"]},
            "results": {"bindings": []},
        }

    def query_sparql(self, query, timeout_seconds, limit):
        self.queries.append(query)
        if "CONSTRUCT" in query.upper() and self._construct_result is not None:
            return SparqlResult(result=self._construct_result)
        return SparqlResult(result=self._select_result)

    def update_sparql(self, update):
        self.updates.append(update)
        return UpdateResult()

    def export_dataset(self, format, graph_iris=None):
        return "@prefix ex: <http://example.test/> ."

    def graph_exists(self, graph_iri):
        return graph_iri in self._graphs

    def get_graph(self, graph_iri, format):
        return self._stored.get(graph_iri, "")

    def set_graph(self, graph_iri, content):
        self._stored[graph_iri] = content
        self._graphs.add(graph_iri)

    def clear_graph(self, graph_iri):
        self.clears.append(graph_iri)
        self._graphs.discard(graph_iri)
        return UpdateResult()

    def graph_content_hash(self, graph_iri):
        return None


def _client(
    store: FakeStore,
    session: Session | None = None,
    settings: Settings | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    settings = settings or Settings()
    if session is not None and session.get(ProjectModel, TEST_PROJECT_ID) is None:
        session.add(
            ProjectModel(
                id=TEST_PROJECT_ID,
                name="Semantic API project",
                normalized_label="semantic api project",
            )
        )
        session.add(
            OntologyModel(
                id=TEST_ONTOLOGY_ID,
                project_id=TEST_PROJECT_ID,
                name="Semantic API ontology",
                model_graph_iri=GRAPH,
            )
        )
        session.commit()

    def session_override() -> Generator[Session, None, None]:
        yield session  # type: ignore[misc]

    if session is not None:
        app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_semantic_sparql_endpoint_rejects_write_query(in_memory_session) -> None:
    client = _client(FakeStore(), in_memory_session)

    response = client.post(
        "/api/semantic/sparql:query",
        json={
            "project_id": "project",
            "scope_mode": "project",
            "ontology_ids": [],
            "query": "DELETE DATA {}",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_query"


def test_semantic_edit_endpoint_applies_turtle_insert(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)

    response = client.post(
        "/api/semantic/edits",
        json={
            "format": "turtle",
            "content": '@prefix ex: <http://example.test/> . ex:alice ex:name "Alice" .',
            "ontology_id": TEST_ONTOLOGY_ID,

        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] is True
    assert body["graph_revisions"][GRAPH] == 1
    assert store.updates


def test_semantic_edit_endpoint_rejects_reasoning_result_graph(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)

    response = client.post(
        "/api/semantic/edits",
        json={
            "format": "turtle",
            "content": '@prefix ex: <http://example.test/> . ex:alice ex:name "Alice" .',
            "ontology_id": TEST_ONTOLOGY_ID,
            "target_graph_iri": RESULT_GRAPH,

        },
    )

    assert response.status_code == 422
    assert store.updates == []


def test_semantic_edit_endpoint_returns_400_for_malformed_rdf(in_memory_session) -> None:
    """Regression: malformed RDF must produce a structured 400, not an HTTP 500."""
    store = FakeStore()
    client = _client(store, in_memory_session)

    response = client.post(
        "/api/semantic/edits",
        json={
            "format": "turtle",
            "content": "GARBAGE not valid turtle",
            "ontology_id": TEST_ONTOLOGY_ID,

        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "parse" in detail["message"].lower() or "syntax" in detail["message"].lower()
    assert "line" in detail
    assert "column" in detail
    assert store.updates == []


def test_semantic_dataset_load_endpoint_returns_400_for_malformed_rdf(
    in_memory_session,
) -> None:
    """Regression: malformed RDF at /datasets:load must produce a structured 400."""
    store = FakeStore()
    client = _client(store, in_memory_session)

    response = client.post(
        "/api/semantic/datasets:load",
        json={
            "format": "turtle",
            "content": "GARBAGE not valid turtle",
            "base_iri": "http://example.test/",
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "parse" in detail["message"].lower() or "syntax" in detail["message"].lower()
    assert "line" in detail
    assert "column" in detail


def test_semantic_edit_audits_endpoint_lists_records(in_memory_session) -> None:
    in_memory_session.add(
        SemanticEditAuditModel(
            id="audit-1",
            actor="agent:test",
            reason="phase3 coverage",
            input_format="turtle",
            target_graph_iri=GRAPH,
            affected_graph_iris=[GRAPH],
            validation_result=None,
            graph_delta={"operation": "insert"},
            evidence_status="missing_evidence",
            warning_state={"missing_evidence": True},
            applied=True,
            created_at=datetime(2026, 7, 4, tzinfo=UTC),
        )
    )
    in_memory_session.commit()
    client = _client(FakeStore(), in_memory_session)

    response = client.get("/api/semantic/edits/audits")

    assert response.status_code == 200, response.text
    assert response.json()[0]["id"] == "audit-1"
    assert response.json()[0]["actor"] == "agent:test"
    assert response.json()[0]["graph_delta"] == {"operation": "insert"}








def test_gc_endpoint_dry_run_does_not_call_clear(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)

    response = client.post(
        "/api/semantic/derived-results:gc",
        json={"target_kind": "reasoning_result", "dry_run": True, "retention_days": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert store.updates == []


def test_gc_endpoint_executes_clear_for_eligible_superseded(in_memory_session) -> None:
    from datetime import UTC, datetime, timedelta

    from app.repositories.models import SemanticDerivedResultPointerModel

    superseded_at = datetime.now(UTC) - timedelta(days=2)
    in_memory_session.add(
        SemanticDerivedResultPointerModel(
            id="ptr-1",
            ontology_id="gs-1",
            result_kind="reasoning",
            run_id="run-1",
            result_graph_iri=RESULT_GRAPH,
            source_signature="historical-signature",
            status="superseded",
            became_current_at=datetime(2026, 1, 1, tzinfo=UTC),
            pointer_metadata={"superseded_at": superseded_at.isoformat()},
        )
    )
    in_memory_session.commit()
    store = FakeStore()
    client = _client(store, in_memory_session)

    response = client.post(
        "/api/semantic/derived-results:gc",
        json={"target_kind": "reasoning_result", "dry_run": False, "retention_days": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["deleted_count"] == 1
    assert RESULT_GRAPH in body["deleted_graph_iris"]
    assert store.clears == [RESULT_GRAPH]


# ---------------------------------------------------------------------------
# Phase 5 endpoints: rule definitions, rule runs, graph-set validation
# ---------------------------------------------------------------------------


PREFIX = "http://ontology-platform.local/semantic/graph/"


def _create_graph_set(client, members=None) -> str:
    members = members or [{"graph_iri": f"{PREFIX}ontology/demo", "role": "asserted_data"}]
    response = client.post(
        "/api/semantic/graph-sets",
        json={
            "name": "gs",
            "scope_type": "ontology",
            "scope_id": TEST_ONTOLOGY_ID,
            "members": members,
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_stage5_projection_status_exposes_stale_projection_count(
    in_memory_session,
) -> None:
    client = _client(FakeStore(), in_memory_session)
    in_memory_session.add(
        seed_model(in_memory_session, "gs-stage5", name="stage5")
    )
    in_memory_session.add(
        SemanticProjectionManifestModel(
            id="manifest-stage5",
            ontology_id="gs-stage5",
            projection_kind="search",
            active_job_id="job-old",
            model_revision=1,
            projection_version="search-v1",
            target_partition="gs-stage5/search/search-v1",
            status="current",
        )
    )
    in_memory_session.commit()

    response = client.get("/api/semantic/projections/status")

    assert response.status_code == 200
    body = response.json()
    assert body["stale"] == ["manifest-stage5"]
    assert body["stale_projection_count"] == 1




# ---------------------------------------------------------------------------
# Stage 1 intake refactor smoke tests
# ---------------------------------------------------------------------------




def test_build_overview_route_registered() -> None:
    """Verify the build-overview route is registered on the interview router."""
    from app.api.interview import router

    routes = [r for r in router.routes if hasattr(r, "path") and "build-overview" in r.path]
    assert len(routes) == 1
    assert "GET" in routes[0].methods


def test_competency_question_validate_route_registered() -> None:
    """Verify the validate route is still registered on the interview router."""
    from app.api.interview import router

    routes = [r for r in router.routes if hasattr(r, "path") and "validate" in r.path]
    assert len(routes) >= 1


def test_project_build_context_replaces_legacy_route_without_deprecation(
    in_memory_session,
) -> None:
    """The R-003 recovery view replaces the deprecated interview aggregate."""
    from app.api.build_sessions import router as build_sessions_router
    from app.repositories.models import ProjectModel

    in_memory_session.add(ProjectModel(id="smoke-proj", name="smoke", normalized_label="smoke"))
    in_memory_session.commit()

    app = FastAPI()
    app.include_router(build_sessions_router, prefix="/api")

    store = FakeStore()
    settings = Settings()

    def session_override() -> Generator[Session, None, None]:
        yield in_memory_session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)

    resp = client.get("/api/projects/smoke-proj/build-context")
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") is None
    assert "Sunset" not in resp.headers
    assert set(resp.json()) == {
        "project",
        "generated_at",
        "platform_state",
        "agent_state",
    }


@pytest.mark.parametrize("path,payload", [
    ("/rule-definitions", {"rule_iri": "urn:retired:dsl", "name": "Old DSL", "language": "platform_dsl", "input_roles": ["asserted_data"], "body": {"when": [{"s": "?s", "p": "urn:p", "o": "x"}], "then": [{"s": "?s", "p": "urn:result", "o": True}]}}),
    ("/rule-definitions", {"rule_iri": "urn:retired:construct", "language": "sparql_construct", "body": {"template": "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"}}),
    ("/ontologies/gs-stage5/construct-runs", {"template": "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"}),
    ("/ontologies/gs-stage5/rule-runs", {}),
    ("/ontologies/gs-stage5/rule-runs", {"rule_definition_ids": ["legacy"]}),
])
def test_retired_rule_requests_do_not_write_even_with_original_payloads(in_memory_session, path, payload):
    store = FakeStore()
    client = _client(store, in_memory_session)
    response = client.post("/api/semantic" + path, json=payload)
    assert response.status_code == 404, response.text
    assert store.updates == []
    assert in_memory_session.scalar(select(func.count()).select_from(SemanticRuleRunModel)) == 0

@pytest.mark.parametrize("method,path", [("POST", "/graphs"), ("GET", "/graphs"), ("POST", "/graph-sets"), ("PUT", "/graph-sets/old/members")])
def test_storage_container_management_routes_retired(in_memory_session, method, path):
    client = _client(FakeStore(), in_memory_session)
    assert client.request(method, "/api/semantic" + path, json={}).status_code == 404
