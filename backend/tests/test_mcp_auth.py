import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import sessionmaker

import app.mcp.runtime as mcp_runtime
from app.mcp.runtime import (
    MCP_TOOL_POLICIES,
    McpOwnership,
    _authorize_tool,
    _run_tool,
    authenticate_runtime,
    set_runtime_principal,
)
from app.repositories.models import (
    ApiKeyModel,
    OntologyModel,
    ProjectModel,
    SemanticGraphRegistryModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)
from app.mcp.server import mcp


def test_every_registered_tool_has_an_explicit_policy():
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == set(MCP_TOOL_POLICIES)


def test_policy_inventory_fails_closed_for_resource_less_and_mutating_tools():
    tools = asyncio.run(mcp.list_tools())
    global_safe = set()
    for tool in tools:
        policy = MCP_TOOL_POLICIES[tool.name]
        properties = set((tool.inputSchema or {}).get("properties", {}))
        has_owner_input = bool(
            properties
            & {
                "project_id",
                "ontology_id",
                "session_id",
                "batch_id",
                "workflow_artifact_id",
                "execution_event_id",
                "reference_id",
                "question_id",
                "graph_set_id",
                "target_graph_set_id",
                "rule_definition_id",
                "run_id",
                "job_id",
                "ontology_ids",
                "scope_id",
            }
        ) or any(name.endswith("graph_iri") or name.endswith("graph_iris") for name in properties)
        if policy.ownership is McpOwnership.PROJECT_RESOURCE:
            assert has_owner_input, f"{tool.name} cannot resolve a Project resource"
        if not has_owner_input:
            assert policy.ownership in {McpOwnership.ORG_ONLY, McpOwnership.GLOBAL_SAFE}
        if policy.mutates_state:
            assert policy.required_scope in {"model", "admin"}
            assert policy.ownership is not McpOwnership.GLOBAL_SAFE
        if policy.ownership is McpOwnership.GLOBAL_SAFE:
            global_safe.add(tool.name)

    assert global_safe == {"check_platform_health"}
    assert MCP_TOOL_POLICIES["check_semantic_staleness"].required_scope == "admin"
    assert MCP_TOOL_POLICIES["check_semantic_staleness"].ownership is McpOwnership.ORG_ONLY
    assert MCP_TOOL_POLICIES["check_semantic_staleness"].mutates_state is True


def test_mcp_startup_requires_environment_key(monkeypatch):
    monkeypatch.delenv("ONTOLOGY_MCP_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ONTOLOGY_MCP_API_KEY is required"):
        authenticate_runtime()


def test_mcp_rechecks_revocation_on_each_tool_call(in_memory_session, mcp_principal_factory):
    principal = mcp_principal_factory(in_memory_session)

    def callback(_session, _driver, _embedding_client):
        return None

    assert (
        _authorize_tool(in_memory_session, "check_platform_health", callback).subject_id
        == principal.subject_id
    )

    record = in_memory_session.get(ApiKeyModel, principal.subject_id)
    record.revoked_at = datetime.now(UTC)
    in_memory_session.commit()

    with pytest.raises(PermissionError, match="no longer valid"):
        _authorize_tool(in_memory_session, "check_platform_health", callback)


def test_project_mcp_denies_ad_hoc_graph_set_and_allows_owned_graph_set(
    in_memory_session, mcp_principal_factory
):
    project = ProjectModel(id="p1", name="P1", normalized_label="P1")
    ontology = OntologyModel(
        id="o1",
        project_id=project.id,
        name="Owned",
        status="active",
    )
    graph = SemanticGraphRegistryModel(
        id="registry-1",
        graph_iri="urn:r008:p1:data",
        category="asserted_data",
        semantic_owner_type="ontology",
        semantic_owner_id=ontology.id,
    )
    owned = SemanticGraphSetModel(
        id="owned-set",
        name="Owned",
        scope_type="ontology",
        scope_id=ontology.id,
        status="active",
        source_signature="owned",
    )
    owned.members.append(
        SemanticGraphSetMemberModel(
            id="owned-member",
            graph_iri=graph.graph_iri,
            role="asserted_data",
            required=True,
            sort_order=0,
        )
    )
    ad_hoc = SemanticGraphSetModel(
        id="ad-hoc-set",
        name="Ad hoc",
        scope_type="ontology_version",
        scope_id="not-a-platform-ontology",
        status="active",
        source_signature="ad-hoc",
    )
    in_memory_session.add_all([project, ontology, graph, owned, ad_hoc])
    in_memory_session.commit()
    mcp_principal_factory(in_memory_session, project_id=project.id, scopes=["model"])

    graph_set_id = ad_hoc.id

    def read_ad_hoc(_session, _driver, _embedding_client):
        return graph_set_id

    with pytest.raises(PermissionError, match="owner cannot be resolved"):
        _authorize_tool(in_memory_session, "describe_semantic_graph_set", read_ad_hoc)

    graph_set_id = owned.id

    def read_owned(_session, _driver, _embedding_client):
        return graph_set_id

    assert (
        _authorize_tool(in_memory_session, "describe_semantic_graph_set", read_owned).project_id
        == project.id
    )


def test_resource_less_global_mutation_denies_all_project_principals_and_allows_org_admin(
    in_memory_session, mcp_principal_factory, monkeypatch
):
    project = ProjectModel(id="policy-p1", name="Policy P1", normalized_label="Policy P1")
    in_memory_session.add(project)
    in_memory_session.commit()
    project_principals = [
        mcp_principal_factory(in_memory_session, project_id=project.id, scopes=[scope])
        for scope in ("read", "model", "admin")
    ]
    org_admin = mcp_principal_factory(in_memory_session, scopes=["admin"])
    factory = sessionmaker(bind=in_memory_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(mcp_runtime, "get_resources", lambda: (factory, None, None))
    effects: list[str] = []

    def check_semantic_staleness():
        return _run_tool(
            lambda _session, _driver, _embedding_client: (
                effects.append("reconciled") or {"changed": True}
            )
        )

    for principal in project_principals:
        set_runtime_principal(principal)
        result = check_semantic_staleness()
        assert result["ok"] is False
        assert effects == []

    set_runtime_principal(org_admin)
    assert check_semantic_staleness() == {"ok": True, "data": {"changed": True}}
    assert effects == ["reconciled"]

    def check_platform_health():
        return _run_tool(
            lambda _session, _driver, _embedding_client: {"postgres": {"status": "ok"}}
        )

    set_runtime_principal(project_principals[0])
    assert check_platform_health()["ok"] is True
    assert effects == ["reconciled"]
