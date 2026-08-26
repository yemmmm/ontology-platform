"""MCP-surface semantic access tests (R3.0-004 §10.2, A13)."""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.mcp.runtime import set_runtime_principal
from app.mcp.server import mcp
from app.repositories.models import OntologyModel, ProjectModel
from app.security.auth import create_api_key, resolve_api_key
from app.services.evidence_reference import EvidenceReferenceService
from app.services.semantic_protection_set import SemanticProtectionSetService

COST_IRI = "https://example.test/entity/cost-1"


def _tool(name: str):
    tool = mcp._tool_manager.get_tool(name)  # noqa: SLF001 - MCP test seam
    assert tool is not None
    return tool


def _activate(session, name: str, project_id, scopes, grants=None):
    _record, plaintext = create_api_key(
        session,
        name=name,
        project_id=project_id,
        scopes=scopes,
        semantic_grants=grants,
    )
    principal = resolve_api_key(session, plaintext)
    assert principal is not None
    set_runtime_principal(principal)


def _seed(session):
    session.add(ProjectModel(id="p", name="P", normalized_label="p"))
    session.add(OntologyModel(id="o", project_id="p", name="O"))
    session.commit()


def test_exactly_six_protection_set_tools_are_registered():
    tools = {tool.name for tool in mcp._tool_manager.list_tools()}  # noqa: SLF001
    expected = {
        "list_semantic_protection_sets",
        "create_semantic_protection_set",
        "update_semantic_protection_set",
        "delete_semantic_protection_set",
        "add_semantic_protection_set_members",
        "remove_semantic_protection_set_members",
    }
    assert expected <= tools
    assert "get_semantic_protection_set" not in tools


def test_model_principal_manages_protection_sets_over_mcp(
    in_memory_session, monkeypatch, mcp_principal_factory
):
    _seed(in_memory_session)
    mcp_principal_factory(in_memory_session, project_id="p", scopes=["model"])
    factory = sessionmaker(bind=in_memory_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, object()))

    created = _tool("create_semantic_protection_set").fn(
        project_id="p",
        name="cost-visibility",
        allowed_grants=["cost-visibility"],
        members=[{"resource_iri": COST_IRI}],
    )
    assert created["ok"] is True, created
    set_id = created["data"]["id"]

    listed = _tool("list_semantic_protection_sets").fn(project_id="p")
    assert listed["ok"] is True
    assert [item["id"] for item in listed["data"]] == [set_id]

    # empty set deletion is allowed over MCP as over HTTP
    removed_members = _tool("remove_semantic_protection_set_members").fn(
        protection_set_id=set_id, resource_iris=[COST_IRI]
    )
    assert removed_members["ok"] is True
    deleted = _tool("delete_semantic_protection_set").fn(protection_set_id=set_id)
    assert deleted["ok"] is True


def test_read_principal_cannot_manage_protection_sets_over_mcp(
    in_memory_session, monkeypatch, mcp_principal_factory
):
    _seed(in_memory_session)
    mcp_principal_factory(in_memory_session, project_id="p", scopes=["read"])
    factory = sessionmaker(bind=in_memory_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, object()))

    denied = _tool("create_semantic_protection_set").fn(
        project_id="p", name="cost-visibility"
    )
    assert denied["ok"] is False


def test_mcp_evidence_reads_honor_grants_like_http(
    in_memory_session, monkeypatch, mcp_principal_factory
):
    _seed(in_memory_session)
    SemanticProtectionSetService(in_memory_session).create_set(
        project_id="p",
        name="cost-visibility",
        allowed_grants=["cost-visibility"],
        members=[{"resource_iri": COST_IRI, "ontology_id": "o"}],
    )
    service = EvidenceReferenceService(in_memory_session)
    cost_ref, _ = service.get_or_create("p", "cost-doc", "cost excerpt")
    public_ref, _ = service.get_or_create("p", "public-doc", "public excerpt")
    service.associate(
        project_id="p",
        ontology_id="o",
        graph_set_id=None,
        target_type="entity",
        target_id=COST_IRI,
        references=[cost_ref],
        actor="tester",
    )
    in_memory_session.commit()

    factory = sessionmaker(bind=in_memory_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, object()))

    try:
        _activate(in_memory_session, "operator", "p", ["read"])
        operator = _tool("list_evidence_references").fn(project_id="p")
        assert operator["ok"] is True, operator
        assert [item["id"] for item in operator["data"]["items"]] == [public_ref.id]
        hidden = _tool("get_evidence_reference").fn(reference_id=cost_ref.id)
        assert hidden["ok"] is False

        _activate(in_memory_session, "manager", "p", ["read"], grants=["cost-visibility"])
        manager = _tool("list_evidence_references").fn(project_id="p")
        assert manager["ok"] is True
        assert len(manager["data"]["items"]) == 2
        detail = _tool("get_evidence_reference").fn(reference_id=cost_ref.id)
        assert detail["ok"] is True
        assert detail["data"]["association_count"] == 1
    finally:
        set_runtime_principal(None)
