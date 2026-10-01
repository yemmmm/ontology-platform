"""MCP parity and secret enforcement for R1.1-002 workflow records."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.mcp.server import mcp
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
)


def _tool(name: str):
    tool = mcp._tool_manager.get_tool(name)  # noqa: SLF001
    assert tool is not None
    return tool


def _data(result: dict[str, Any]):
    assert result["ok"] is True, result
    return result["data"]


@pytest.fixture()
def mcp_workflow(in_memory_session: Session, monkeypatch, mcp_principal_factory):
    in_memory_session.add(
        ProjectModel(
            id="mcp-workflow-project", name="MCP workflow", normalized_label="mcp workflow"
        )
    )
    in_memory_session.flush()
    in_memory_session.add(
        OntologyModel(
            id="mcp-workflow-ontology",
            project_id="mcp-workflow-project",
            name="MCP workflow ontology",
        )
    )
    in_memory_session.commit()
    mcp_principal_factory(in_memory_session)
    factory = sessionmaker(bind=in_memory_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (factory, None, object()))
    created = _data(
        _tool("create_build_session").fn(
            project_id="mcp-workflow-project",
            client_session_id="mcp-workflow-session",
            previous_session_id=None,
            initial_checkpoint=None,
        )
    )
    return created["session"]["id"]


def test_mcp_artifact_event_read_list_and_export_use_shared_service(mcp_workflow):
    session_id = mcp_workflow
    created = _data(
        _tool("create_modeling_workflow_artifact").fn(
            session_id=session_id,
            client_version_id="pack-v1",
            artifact_key="business-knowledge-pack",
            artifact_type="business_knowledge_pack",
            content_format="json",
            content={"scope": "workflow"},
            created_by_role="business_organizer",
            workflow_name="ontology-builder",
            workflow_version="r1.1-v1",
            role_prompt_version="organizer-v1",
            ontology_id="mcp-workflow-ontology",
            supersedes_workflow_artifact_id=None,
        )
    )
    artifact = created["artifact"]
    assert created["created"] is True
    fetched = _data(
        _tool("get_modeling_workflow_artifact").fn(
            workflow_artifact_id=artifact["workflow_artifact_id"]
        )
    )
    assert fetched["content_hash"] == artifact["content_hash"]
    listed = _data(
        _tool("list_modeling_workflow_artifacts").fn(
            session_id=session_id,
            artifact_type=None,
            artifact_key=None,
            ontology_id=None,
            current_only=True,
            cursor=None,
            limit=50,
        )
    )
    assert len(listed["items"]) == 1

    event = _data(
        _tool("record_modeling_execution_event").fn(
            session_id=session_id,
            client_event_id="artifact-created",
            workflow_name="ontology-builder",
            workflow_version="r1.1-v1",
            phase="global_scan",
            event_type="artifact_created",
            status="completed",
            report_source="agent_reported",
            actor_role="main_agent",
            summary="Persisted Pack",
            output_workflow_artifact_ids=[artifact["workflow_artifact_id"]],
        )
    )["event"]
    fetched_event = _data(
        _tool("get_modeling_execution_event").fn(execution_event_id=event["execution_event_id"])
    )
    assert fetched_event["sequence"] == 1
    timeline = _data(
        _tool("list_modeling_execution_events").fn(
            session_id=session_id, phase=None, event_type=None, cursor=None, limit=50
        )
    )
    assert timeline["items"][0]["event_type"] == "artifact_created"
    exported = _data(
        _tool("export_modeling_workflow_record").fn(session_id=session_id, format="json")
    )
    assert exported["current_artifact_index"]["business-knowledge-pack"]["version"] == 1


def test_mcp_wrapper_rejects_secret_before_persistence(mcp_workflow):
    fake_secret = "sk_model_" + "Q" * 32
    response = _tool("create_modeling_workflow_artifact").fn(
        session_id=mcp_workflow,
        client_version_id="secret-v1",
        artifact_key="secret-test",
        artifact_type="review_report",
        content_format="json",
        content={"credential": fake_secret},
        created_by_role="reviewer",
        workflow_name="ontology-builder",
        workflow_version="r1.1-v1",
    )
    assert response["ok"] is False
    assert response["error_code"] == "secret_in_payload"
    assert fake_secret not in response["error"]
    listed = _data(
        _tool("list_modeling_workflow_artifacts").fn(
            session_id=mcp_workflow,
            artifact_type=None,
            artifact_key="secret-test",
            ontology_id=None,
            current_only=False,
            cursor=None,
            limit=50,
        )
    )
    assert listed["items"] == []


def test_mcp_lineage_reference_is_rejected_by_workflow_contract(mcp_workflow):
    common = {
        "session_id": mcp_workflow,
        "workflow_name": "ontology-builder",
        "workflow_version": "r1.1-v1",
        "phase": "verification",
        "event_type": "verification_completed",
        "status": "completed",
        "report_source": "agent_reported",
        "actor_role": "main_agent",
        "summary": "Checked lineage reference",
    }
    rejected = _tool("record_modeling_execution_event").fn(
        **common,
        client_event_id="mcp-lineage",
        related_resources=[
            {
                "resource_type": "lineage",
                "ontology_id": "mcp-workflow-ontology",
                "target_type": "statement",
                "target_id": "0" * 64,
            }
        ],
    )
    assert rejected["ok"] is False
    assert rejected["error_code"] == "validation_error"
