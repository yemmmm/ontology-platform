"""MCP parity and secret enforcement for R1.1-002 workflow records."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.mcp.server import mcp
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticStatementOccurrenceModel,
)
from app.services.semantic_lineage_identity import occurrence_id_for, statement_id_for_quad

MCP_LINEAGE_SUBJECT = "https://workflow.test/resource/mcp-known"
MCP_LINEAGE_PREDICATE = "https://workflow.test/property/status"
MCP_LINEAGE_OBJECT = '"known"'
MCP_LINEAGE_GRAPH = "https://workflow.test/graph/mcp"
MCP_LINEAGE_STATEMENT_ID = statement_id_for_quad(
    MCP_LINEAGE_SUBJECT,
    MCP_LINEAGE_PREDICATE,
    MCP_LINEAGE_OBJECT,
    MCP_LINEAGE_GRAPH,
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
    in_memory_session.add(
        SemanticStatementOccurrenceModel(
            id=occurrence_id_for(MCP_LINEAGE_STATEMENT_ID, 1),
            ontology_id="mcp-workflow-ontology",
            graph_set_id=None,
            statement_id=MCP_LINEAGE_STATEMENT_ID,
            subject_iri=MCP_LINEAGE_SUBJECT,
            predicate_iri=MCP_LINEAGE_PREDICATE,
            object_ntriples=MCP_LINEAGE_OBJECT,
            graph_iri=MCP_LINEAGE_GRAPH,
            graph_revision=1,
            assertion_kind="asserted",
            status="active",
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


def test_mcp_lineage_reference_uses_stable_service_error(mcp_workflow):
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
    known = _tool("record_modeling_execution_event").fn(
        **common,
        client_event_id="mcp-known-lineage",
        related_resources=[
            {
                "resource_type": "lineage",
                "ontology_id": "mcp-workflow-ontology",
                "target_type": "statement",
                "target_id": MCP_LINEAGE_STATEMENT_ID,
            }
        ],
    )
    assert known["ok"] is True, known

    mismatched = _tool("record_modeling_execution_event").fn(
        **common,
        client_event_id="mcp-mismatched-lineage",
        related_resources=[
            {
                "resource_type": "lineage",
                "ontology_id": "mcp-workflow-ontology",
                "target_type": "resource",
                "target_id": MCP_LINEAGE_STATEMENT_ID,
            }
        ],
    )
    assert mismatched["ok"] is False
    assert mismatched["error_code"] == "workflow_reference_conflict"
