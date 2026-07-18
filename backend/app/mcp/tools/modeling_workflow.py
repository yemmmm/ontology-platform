"""MCP tools for R1.1-002 modeling workflow records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.api.schemas import ModelingExecutionEventCreate, ModelingWorkflowArtifactCreate
from app.core.config import Settings
from app.mcp.runtime import _run_tool, runtime_actor
from app.repositories.rdf_store import RdfStoreRepository
from app.services.modeling_workflow import ModelingWorkflowService
from app.services.ontology_lineage import OntologyLineageService


def _service(session) -> ModelingWorkflowService:
    return ModelingWorkflowService(
        session,
        actor=runtime_actor(),
        lineage_service=OntologyLineageService(
            session, RdfStoreRepository(Settings().oxigraph_url)
        ),
    )


def register_modeling_workflow(server: FastMCP) -> None:
    @server.tool()
    def create_modeling_workflow_artifact(
        session_id: str,
        client_version_id: str,
        artifact_key: str,
        artifact_type: str,
        content_format: str,
        content: Any,
        created_by_role: str,
        workflow_name: str,
        workflow_version: str,
        role_prompt_version: str | None = None,
        ontology_id: str | None = None,
        supersedes_workflow_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        """Create one immutable, idempotent workflow artifact version."""

        def execute(session, _driver, _embedding):
            item, created = _service(session).create_artifact(
                session_id,
                ModelingWorkflowArtifactCreate(
                    client_version_id=client_version_id,
                    artifact_key=artifact_key,
                    artifact_type=artifact_type,
                    content_format=content_format,
                    content=content,
                    created_by_role=created_by_role,
                    workflow_name=workflow_name,
                    workflow_version=workflow_version,
                    role_prompt_version=role_prompt_version,
                    ontology_id=ontology_id,
                    supersedes_workflow_artifact_id=supersedes_workflow_artifact_id,
                ),
            )
            return {"artifact": item, "created": created}

        return _run_tool(execute)

    @server.tool()
    def get_modeling_workflow_artifact(workflow_artifact_id: str) -> dict[str, Any]:
        """Read one immutable workflow artifact version."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).get_artifact(
                workflow_artifact_id
            )
        )

    @server.tool()
    def list_modeling_workflow_artifacts(
        session_id: str,
        artifact_type: str | None = None,
        artifact_key: str | None = None,
        ontology_id: str | None = None,
        current_only: bool = False,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List stable pages of workflow artifact versions for a Build Session."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).list_artifacts(
                session_id,
                artifact_type=artifact_type,
                artifact_key=artifact_key,
                ontology_id=ontology_id,
                current_only=current_only,
                cursor=cursor,
                limit=limit,
            )
        )

    @server.tool()
    def record_modeling_execution_event(
        session_id: str,
        client_event_id: str,
        workflow_name: str,
        workflow_version: str,
        phase: str,
        event_type: str,
        status: str,
        report_source: str,
        actor_role: str,
        summary: str,
        ontology_id: str | None = None,
        role_prompt_version: str | None = None,
        agent_runtime: str | None = None,
        agent_model: str | None = None,
        reasoning_effort: str | None = None,
        input_workflow_artifact_ids: list[str] | None = None,
        output_workflow_artifact_ids: list[str] | None = None,
        question_id: str | None = None,
        question_state: str | None = None,
        question_text: str | None = None,
        answer_text: str | None = None,
        answer_reason: str | None = None,
        expected_question_head_event_id: str | None = None,
        interview_answer_id: str | None = None,
        decisions: list[dict[str, Any]] | None = None,
        rejected_alternatives: list[dict[str, Any]] | None = None,
        unresolved_items: list[str] | None = None,
        blockers: list[str] | None = None,
        next_step: str | None = None,
        related_resources: list[dict[str, Any]] | None = None,
        quality_issues: list[dict[str, Any]] | None = None,
        duration_ms: int | None = None,
        token_usage: dict[str, int | None] | None = None,
        cost_summary: dict[str, float | str | None] | None = None,
        supersedes_execution_event_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Append one idempotent event to a Build Session's execution record."""

        def execute(session, _driver, _embedding):
            item, created = _service(session).record_event(
                session_id,
                ModelingExecutionEventCreate(
                    client_event_id=client_event_id,
                    ontology_id=ontology_id,
                    workflow_name=workflow_name,
                    workflow_version=workflow_version,
                    phase=phase,
                    event_type=event_type,
                    status=status,
                    report_source=report_source,
                    actor_role=actor_role,
                    role_prompt_version=role_prompt_version,
                    agent_runtime=agent_runtime,
                    agent_model=agent_model,
                    reasoning_effort=reasoning_effort,
                    summary=summary,
                    input_workflow_artifact_ids=input_workflow_artifact_ids or [],
                    output_workflow_artifact_ids=output_workflow_artifact_ids or [],
                    question_id=question_id,
                    question_state=question_state,
                    question_text=question_text,
                    answer_text=answer_text,
                    answer_reason=answer_reason,
                    expected_question_head_event_id=expected_question_head_event_id,
                    interview_answer_id=interview_answer_id,
                    decisions=decisions or [],
                    rejected_alternatives=rejected_alternatives or [],
                    unresolved_items=unresolved_items or [],
                    blockers=blockers or [],
                    next_step=next_step,
                    related_resources=related_resources or [],
                    quality_issues=quality_issues or [],
                    duration_ms=duration_ms,
                    token_usage=token_usage or {},
                    cost_summary=cost_summary or {},
                    supersedes_execution_event_id=supersedes_execution_event_id,
                    occurred_at=occurred_at,
                ),
            )
            return {"event": item, "created": created}

        return _run_tool(execute)

    @server.tool()
    def get_modeling_execution_event(execution_event_id: str) -> dict[str, Any]:
        """Read one immutable Modeling Execution Event."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).get_event(execution_event_id)
        )

    @server.tool()
    def list_modeling_execution_events(
        session_id: str,
        phase: str | None = None,
        event_type: str | None = None,
        cursor: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List a stable sequence page from a Build Session's execution timeline."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).list_events(
                session_id,
                phase=phase,
                event_type=event_type,
                cursor=cursor,
                limit=limit,
            )
        )

    @server.tool()
    def export_modeling_workflow_record(
        session_id: str,
        format: str = "json",  # noqa: A002
    ) -> dict[str, Any]:
        """Export the complete execution record as structured JSON or Markdown."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).export(
                session_id, export_format=format
            )
        )


__all__ = ["register_modeling_workflow"]
