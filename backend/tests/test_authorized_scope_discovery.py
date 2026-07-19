from __future__ import annotations

import hashlib
from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db_session, get_settings
from app.api.semantic import router
from app.core.config import Settings
from app.mcp.server import mcp
from app.repositories.models import OntologyModel, ProjectModel
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency
from app.services.authorized_scope_discovery import (
    AuthorizedScopeDiscoveryService,
    ScopeDiscoveryCursorError,
)
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_query_scope import (
    SemanticQueryScopeNotReady,
    SemanticQueryScopeResolver,
)


def _seed_catalog(session: Session, settings: Settings) -> None:
    projects = [
        ProjectModel(id="p1", name="Alpha Project", normalized_label="Alpha Project"),
        ProjectModel(id="p2", name="Foreign Project", normalized_label="Foreign Project"),
        ProjectModel(id="p3", name="Empty Project", normalized_label="Empty Project"),
    ]
    session.add_all(projects)
    ontologies = [
        OntologyModel(id="o1", project_id="p1", name="Ready One", status="active"),
        OntologyModel(id="o2", project_id="p1", name="Archived One", status="archived"),
        OntologyModel(id="o3", project_id="p1", name="Broken One", status="draft"),
        OntologyModel(id="o4", project_id="p2", name="Foreign Ready", status="active"),
    ]
    session.add_all(ontologies)
    session.flush()
    workspace = OntologyWorkspaceService(session, settings)
    workspace.ensure(ontologies[0])
    workspace.ensure(ontologies[1])
    workspace.ensure(ontologies[3])
    session.commit()


@pytest.fixture()
def catalog(in_memory_session):
    settings = Settings(secret_key="discovery-test-secret")
    _seed_catalog(in_memory_session, settings)
    return in_memory_session, settings


def _service(catalog) -> AuthorizedScopeDiscoveryService:
    session, settings = catalog
    return AuthorizedScopeDiscoveryService(session, settings)


def test_discovery_filters_authorization_before_catalog_matching(catalog):
    result = _service(catalog).discover(authorized_project_id="p1")

    assert [item["id"] for item in result["items"]] == ["p1", "o2", "o3", "o1"]
    assert all(item["id"] not in {"p2", "o4"} for item in result["items"])
    project = result["items"][0]
    assert project["query_status"] == "partial"
    assert {item["reason"] for item in project["excluded_ontologies"]} == {
        "ontology_archived",
        "workspace_not_ready",
    }
    ready = next(item for item in result["items"] if item["id"] == "o1")
    assert ready["queryable"] is True
    assert ready["workspace_version"]
    assert {warning["code"] for warning in ready["derived_warnings"]} == {"derived_result_missing"}
    assert "graph_set" not in str(result)
    assert "graph_iri" not in str(result)


def test_discovery_metadata_matching_and_queryable_filter(catalog):
    service = _service(catalog)

    by_project = service.discover(authorized_project_id="p1", query=" alpha ")
    assert [item["id"] for item in by_project["items"]] == ["p1", "o2", "o3", "o1"]
    assert by_project["items"][0]["matched_on"] == ["name"]
    assert all(item["matched_on"] == ["project"] for item in by_project["items"][1:])

    by_ontology = service.discover(authorized_project_id="p1", query="READY")
    assert [item["id"] for item in by_ontology["items"]] == ["o1"]
    assert by_ontology["items"][0]["matched_on"] == ["name"]

    unavailable = service.discover(authorized_project_id="p1", queryable=False)
    assert [item["id"] for item in unavailable["items"]] == ["p1", "o2", "o3"]
    assert {item["unavailable_reason"] for item in unavailable["items"][1:]} == {
        "ontology_archived",
        "workspace_not_ready",
    }
    assert service.discover(authorized_project_id="p1", query="description only")["items"] == []
    assert service.discover(authorized_project_id="p1", query="p2")["items"] == []


def test_discovery_cursor_is_stable_filter_bound_and_tamper_evident(catalog):
    service = _service(catalog)
    ids = []
    cursor = None
    while True:
        page = service.discover(authorized_project_id="p1", limit=1, cursor=cursor)
        ids.extend(item["id"] for item in page["items"])
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        cursor = page["next_cursor"]
        assert cursor
    assert ids == ["p1", "o2", "o3", "o1"]

    first = service.discover(authorized_project_id="p1", limit=1)
    with pytest.raises(ScopeDiscoveryCursorError):
        service.discover(
            authorized_project_id="p1", limit=1, query="ready", cursor=first["next_cursor"]
        )
    with pytest.raises(ScopeDiscoveryCursorError):
        service.discover(authorized_project_id="p1", limit=1, cursor=first["next_cursor"] + "x")


@pytest.mark.parametrize("other_principal", ["p2", None])
def test_discovery_cursor_is_bound_to_authorized_principal(catalog, other_principal):
    service = _service(catalog)
    first = service.discover(authorized_project_id="p1", limit=1)

    with pytest.raises(ScopeDiscoveryCursorError):
        service.discover(
            authorized_project_id=other_principal,
            limit=1,
            cursor=first["next_cursor"],
        )


def test_default_cursor_integrity_uses_process_private_unpredictable_material(in_memory_session):
    settings = Settings(secret_key="")
    first = AuthorizedScopeDiscoveryService(in_memory_session, settings)
    second = AuthorizedScopeDiscoveryService(in_memory_session, settings)

    assert first._cursor_key() == second._cursor_key()  # noqa: SLF001 - process lifetime contract
    assert len(first._cursor_key()) == 32  # noqa: SLF001 - integrity key contract
    assert (
        first._cursor_key()
        != hashlib.sha256(  # noqa: SLF001 - old public fallback
            b"ontology-platform-discovery-cursor-v1"
        ).digest()
    )


def test_scope_resolver_reuses_archived_and_unavailable_readiness(catalog):
    session, settings = catalog
    resolver = SemanticQueryScopeResolver(session, settings)

    project_scope = resolver.resolve(project_id="p1", scope_mode="project")
    assert [item.ontology_id for item in project_scope.ontologies] == ["o1"]
    assert {item["reason"] for item in project_scope.excluded_ontologies} == {
        "ontology_archived",
        "workspace_not_ready",
    }
    with pytest.raises(SemanticQueryScopeNotReady):
        resolver.resolve(project_id="p1", scope_mode="ontologies", ontology_ids=["o2"])
    with pytest.raises(SemanticQueryScopeNotReady):
        resolver.resolve(project_id="p3", scope_mode="project")


def _api_client(session: Session, settings: Settings, principal: AuthPrincipal) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    app.dependency_overrides[principal_dependency] = lambda: principal
    return client


def test_rest_discovery_uses_principal_filter_and_stable_errors(catalog):
    session, settings = catalog
    principal = AuthPrincipal(
        subject_type="api_key",
        subject_id="key",
        actor="key:test",
        scopes=frozenset({"read"}),
        project_id="p1",
        auth_method="bearer",
    )
    client = _api_client(session, settings, principal)

    response = client.get("/api/semantic/scopes:discover", params={"query": "ready"})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["o1"]
    invalid = client.get("/api/semantic/scopes:discover", params={"queryable": "sometimes"})
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "invalid_discovery_request"
    invalid_limit = client.get("/api/semantic/scopes:discover", params={"limit": 101})
    assert invalid_limit.status_code == 400
    assert invalid_limit.json()["detail"]["code"] == "invalid_discovery_request"


def _tool(name: str):
    tool = mcp._tool_manager.get_tool(name)  # noqa: SLF001 - MCP test seam
    assert tool is not None
    return tool


def test_mcp_discovery_matches_rest_and_filters_project_principal(
    catalog, monkeypatch, mcp_principal_factory
):
    session, settings = catalog
    principal = mcp_principal_factory(session, project_id="p1", scopes=["read"])
    factory = sessionmaker(bind=session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, object()))
    monkeypatch.setattr("app.mcp.tools.semantic.Settings", lambda: settings)

    rest = _api_client(session, settings, principal).get(
        "/api/semantic/scopes:discover", params={"query": "ready", "limit": 1}
    )
    result = _tool("discover_semantic_scopes").fn(query="ready", limit=1)

    assert rest.status_code == 200
    assert result["ok"] is True
    assert result["data"]["items"] == rest.json()["items"]
    assert result["data"]["has_more"] == rest.json()["has_more"]
    assert result["data"]["next_cursor"] == rest.json()["next_cursor"]
    assert "p2" not in str(result)
    assert "o4" not in str(result)


def test_discovery_requires_http_authentication(r008_client):
    client = r008_client["client"]

    unauthenticated = client.get("/api/semantic/scopes:discover")
    assert unauthenticated.status_code == 401
    authorized = client.get(
        "/api/semantic/scopes:discover",
        headers={"Authorization": f"Bearer {r008_client['p1_read_key']}"},
    )
    assert authorized.status_code == 200
    assert {item["id"] for item in authorized.json()["items"]} <= {r008_client["ids"]["p1"]}
