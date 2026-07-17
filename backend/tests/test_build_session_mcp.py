"""R-003 MCP registry and shared-service semantics."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.mcp.server import mcp
from app.repositories.models import OntologyModel, ProjectModel


BUILD_SESSION_TOOLS = {
    "get_project_build_context",
    "create_build_session",
    "get_build_session",
    "resume_build_session",
    "save_build_checkpoint",
    "complete_build_session",
    "cancel_build_session",
    "acquire_ontology_lease",
    "renew_ontology_lease",
    "release_ontology_lease",
}


def _tool(name: str):
    tool = mcp._tool_manager.get_tool(name)  # noqa: SLF001 - MCP test seam
    assert tool is not None, name
    return tool


def test_build_session_tools_are_registered_with_agent_facing_identifiers() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert BUILD_SESSION_TOOLS <= tools.keys()
    assert "get_build_context" in tools  # one-release compatibility alias

    forbidden = {"graph_set_id", "graph_iri", "lease_ttl_seconds"}
    for name in BUILD_SESSION_TOOLS:
        schema = tools[name].inputSchema
        properties = set(schema.get("properties", {}))
        assert properties.isdisjoint(forbidden), (name, properties)

    assert "deprecated" in tools["get_build_context"].description.lower()


@pytest.fixture()
def mcp_scope(in_memory_session: Session, monkeypatch, mcp_principal_factory) -> Session:
    in_memory_session.add(
        ProjectModel(
            id="mcp-build-project",
            name="MCP build project",
            normalized_label="mcp build project",
        )
    )
    in_memory_session.flush()
    in_memory_session.add(
        OntologyModel(
            id="mcp-build-ontology",
            project_id="mcp-build-project",
            name="MCP build ontology",
        )
    )
    in_memory_session.commit()
    mcp_principal_factory(in_memory_session)
    factory = sessionmaker(bind=in_memory_session.get_bind(), autoflush=False, autocommit=False)

    def resources():
        return factory, None, object()

    monkeypatch.setattr("app.mcp.runtime.get_resources", resources)
    return in_memory_session


def _data(result: dict[str, Any]) -> dict[str, Any]:
    assert result["ok"] is True, result
    assert isinstance(result["data"], dict)
    return result["data"]


def test_mcp_create_checkpoint_resume_and_get_use_shared_revision_semantics(mcp_scope) -> None:
    created = _data(
        _tool("create_build_session").fn(
            project_id="mcp-build-project",
            client_session_id="mcp-client-session",
            previous_session_id=None,
            initial_checkpoint=None,
        )
    )
    retried = _data(
        _tool("create_build_session").fn(
            project_id="mcp-build-project",
            client_session_id="mcp-client-session",
            previous_session_id=None,
            initial_checkpoint=None,
        )
    )
    session = created.get("session", created)
    retry_session = retried.get("session", retried)
    assert session["id"] == retry_session["id"]
    assert created["created"] is True
    assert retried["created"] is False

    checkpoint = _data(
        _tool("save_build_checkpoint").fn(
            session_id=session["id"],
            client_checkpoint_id="mcp-checkpoint",
            expected_revision=1,
            phase="modeling",
            current_step="Model through MCP",
            next_step="Resume through MCP",
            ontology_id="mcp-build-ontology",
            summary=None,
            blockers=[],
            failure=None,
            related_batch_id=None,
        )
    )
    assert checkpoint["session"]["revision"] == 2
    retry = _data(
        _tool("save_build_checkpoint").fn(
            session_id=session["id"],
            client_checkpoint_id="mcp-checkpoint",
            expected_revision=1,
            phase="modeling",
            current_step="Model through MCP",
            next_step="Resume through MCP",
            ontology_id="mcp-build-ontology",
            summary=None,
            blockers=[],
            failure=None,
            related_batch_id=None,
        )
    )
    assert retry["checkpoint"]["id"] == checkpoint["checkpoint"]["id"]

    resumed = _data(
        _tool("resume_build_session").fn(
            session_id=session["id"],
            client_request_id="mcp-resume",
            expected_revision=2,
        )
    )
    assert resumed["session"]["revision"] == 2
    detail = _data(
        _tool("get_build_session").fn(
            session_id=session["id"], checkpoint_limit=50, checkpoint_cursor=None
        )
    )
    assert detail["latest_checkpoint"]["client_checkpoint_id"] == "mcp-checkpoint"


def test_new_and_compatibility_build_context_tools_return_same_shape(mcp_scope) -> None:
    new = _data(_tool("get_project_build_context").fn(project_id="mcp-build-project"))
    compatibility = _data(_tool("get_build_context").fn(project_id="mcp-build-project"))
    assert compatibility == new
    assert set(new) == {"project", "generated_at", "platform_state", "agent_state"}


def test_mcp_preserves_structured_service_error_code(mcp_scope) -> None:
    missing = _tool("get_build_session").fn(
        session_id="missing-session", checkpoint_limit=50, checkpoint_cursor=None
    )
    assert missing["ok"] is False
    assert missing["error_code"] == "build_session_not_found"
