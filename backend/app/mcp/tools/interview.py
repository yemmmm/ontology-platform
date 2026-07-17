"""Interview / Project Brief / Competency Question MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.api.schemas import (
    CompetencyQuestionCreate,
    CompetencyQuestionRead,
    InterviewAnswerCreate,
    InterviewAnswerRead,
    ProjectBriefUpdate,
)
from app.core.config import Settings
from app.mcp.runtime import _run_tool, runtime_actor
from app.services import interview as interview_service
from app.services.build_sessions import BuildSessionService
from app.services.ontology_workspace import OntologyWorkspaceService


def register_interview(server: FastMCP) -> None:
    @server.tool()
    def get_build_context(project_id: str) -> dict[str, Any]:
        """Deprecated alias for get_project_build_context; use the new tool."""
        return _run_tool(
            lambda session, _driver, _embedding_client: BuildSessionService(
                session, Settings()
            ).get_project_build_context(project_id)
        )

    @server.tool()
    def get_ontology_workspace_context(ontology_id: str) -> dict[str, Any]:
        """Read the default Graph Set, graph roles, revisions, and editability."""
        return _run_tool(
            lambda session, _driver, _embedding_client: OntologyWorkspaceService(
                session, Settings()
            ).context(ontology_id)
        )

    @server.tool()
    def repair_ontology_workspace(ontology_id: str, dry_run: bool = False) -> dict[str, Any]:
        """Idempotently inspect or repair an Ontology's default semantic workspace."""
        return _run_tool(
            lambda session, _driver, _embedding_client: OntologyWorkspaceService(
                session, Settings()
            ).repair(ontology_id, dry_run=dry_run)
        )

    @server.tool()
    def get_project_brief(project_id: str) -> dict[str, Any]:
        """Read Project Brief completeness and up to three high-value clarification items."""
        return _run_tool(
            lambda session, _driver, _embedding_client: interview_service.get_project_brief(
                session, project_id
            )
        )

    @server.tool()
    def save_interview_answer(
        project_id: str,
        answer: str,
        source_type: str = "conversation",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Save a user answer so Project Brief fields and questions can cite it."""
        return _run_tool(
            lambda session, _driver, _embedding_client: InterviewAnswerRead.model_validate(
                interview_service.create_answer(
                    session,
                    project_id,
                    InterviewAnswerCreate(
                        answer=answer, source_type=source_type, actor_id=runtime_actor()
                    ),
                )
            ).model_dump()
        )

    @server.tool()
    def update_project_brief(project_id: str, update: dict[str, Any]) -> dict[str, Any]:
        """Update and confirm interview fields with saved-answer source links."""
        return _run_tool(
            lambda session, _driver, _embedding_client: interview_service.update_project_brief(
                session, project_id, ProjectBriefUpdate.model_validate(update)
            )
        )

    @server.tool()
    def list_competency_questions(
        project_id: str, include_inactive: bool = False
    ) -> dict[str, Any]:
        """List ordered competency questions and their validation states."""
        return _run_tool(
            lambda session, _driver, _embedding_client: [
                CompetencyQuestionRead.model_validate(item).model_dump()
                for item in interview_service.list_questions(session, project_id, include_inactive)
            ]
        )

    @server.tool()
    def propose_competency_questions(
        project_id: str, questions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Create ordered draft competency questions; this does not approve them."""
        return _run_tool(
            lambda session, _driver, _embedding_client: [
                CompetencyQuestionRead.model_validate(
                    interview_service.create_question(
                        session,
                        project_id,
                        CompetencyQuestionCreate.model_validate(question),
                    )
                ).model_dump()
                for question in questions
            ]
        )

    @server.tool()
    def validate_competency_question(question_id: str) -> dict[str, Any]:
        """Run the bound query definition and record pass/fail result."""
        return _run_tool(
            lambda session, driver, _embedding_client: interview_service.run_question_validation(
                session, driver, question_id
            )
        )
