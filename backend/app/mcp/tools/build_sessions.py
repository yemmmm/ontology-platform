"""MCP tools for R-003 Project build sessions and Ontology leases."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.api.schemas import (
    BuildCheckpointCreate,
    BuildSessionCancel,
    BuildSessionComplete,
    BuildSessionCreate,
    BuildSessionResume,
    InitialBuildCheckpoint,
    OntologyLeaseAcquire,
    OntologyLeaseRelease,
    OntologyLeaseRenew,
)
from app.core.config import Settings
from app.mcp.runtime import _run_tool
from app.services.build_sessions import BuildSessionService


def _service(session) -> BuildSessionService:
    return BuildSessionService(session, Settings())


def register_build_sessions(server: FastMCP) -> None:
    @server.tool()
    def get_project_build_context(
        project_id: str,
        recent_session_limit: int = 10,
        recent_session_cursor: int = 0,
    ) -> dict[str, Any]:
        """Read Project-wide platform facts and recoverable Agent session state."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(
                session
            ).get_project_build_context(
                project_id,
                recent_session_limit=recent_session_limit,
                recent_session_cursor=recent_session_cursor,
            )
        )

    @server.tool()
    def create_build_session(
        project_id: str,
        client_session_id: str,
        previous_session_id: str | None = None,
        initial_checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Idempotently create a Project-scoped external Agent Build Session."""

        def execute(session, _driver, _embedding):
            detail, created = _service(session).create_session(
                project_id,
                BuildSessionCreate(
                    client_session_id=client_session_id,
                    previous_session_id=previous_session_id,
                    initial_checkpoint=(
                        InitialBuildCheckpoint.model_validate(initial_checkpoint)
                        if initial_checkpoint is not None
                        else None
                    ),
                ),
            )
            return {"session": detail, "created": created}

        return _run_tool(execute)

    @server.tool()
    def get_build_session(
        session_id: str,
        checkpoint_limit: int = 50,
        checkpoint_cursor: int | None = None,
    ) -> dict[str, Any]:
        """Read one Build Session's checkpoints, leases, and recovery context."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).get_session_detail(
                session_id,
                checkpoint_limit=checkpoint_limit,
                checkpoint_cursor=checkpoint_cursor,
            )
        )

    @server.tool()
    def resume_build_session(
        session_id: str, client_request_id: str, expected_revision: int
    ) -> dict[str, Any]:
        """Resume an active Build Session without changing its revision."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).resume_session(
                session_id,
                BuildSessionResume(
                    client_request_id=client_request_id,
                    expected_revision=expected_revision,
                ),
            )
        )

    @server.tool()
    def save_build_checkpoint(
        session_id: str,
        client_checkpoint_id: str,
        expected_revision: int,
        phase: str,
        current_step: str,
        next_step: str | None = None,
        ontology_id: str | None = None,
        summary: str | None = None,
        blockers: list[str] | None = None,
        failure: dict[str, str] | None = None,
        related_batch_id: str | None = None,
    ) -> dict[str, Any]:
        """Idempotently append an Agent-reported Build Checkpoint."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).save_checkpoint(
                session_id,
                BuildCheckpointCreate(
                    client_checkpoint_id=client_checkpoint_id,
                    expected_revision=expected_revision,
                    phase=phase,
                    current_step=current_step,
                    next_step=next_step,
                    ontology_id=ontology_id,
                    summary=summary,
                    blockers=blockers or [],
                    failure=failure,
                    related_batch_id=related_batch_id,
                ),
            )
        )

    @server.tool()
    def complete_build_session(
        session_id: str,
        client_request_id: str,
        expected_revision: int,
        summary: str,
        unresolved_items: list[str] | None = None,
    ) -> dict[str, Any]:
        """Idempotently complete a Build Session and release all its leases."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).complete_session(
                session_id,
                BuildSessionComplete(
                    client_request_id=client_request_id,
                    expected_revision=expected_revision,
                    summary=summary,
                    unresolved_items=unresolved_items or [],
                ),
            )
        )

    @server.tool()
    def cancel_build_session(
        session_id: str,
        client_request_id: str,
        expected_revision: int,
        reason: str,
    ) -> dict[str, Any]:
        """Idempotently cancel a Build Session and release all its leases."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).cancel_session(
                session_id,
                BuildSessionCancel(
                    client_request_id=client_request_id,
                    expected_revision=expected_revision,
                    reason=reason,
                ),
            )
        )

    @server.tool()
    def acquire_ontology_lease(
        session_id: str,
        ontology_id: str,
        client_request_id: str,
        expected_session_revision: int,
        rotate_token: bool = False,
    ) -> dict[str, Any]:
        """Acquire or rotate this Build Session's exclusive Ontology write lease."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(
                session
            ).acquire_ontology_lease(
                session_id,
                ontology_id,
                OntologyLeaseAcquire(
                    client_request_id=client_request_id,
                    expected_session_revision=expected_session_revision,
                    rotate_token=rotate_token,
                ),
            )
        )

    @server.tool()
    def renew_ontology_lease(
        session_id: str,
        ontology_id: str,
        client_request_id: str,
        lease_token: str,
        expected_lease_revision: int,
    ) -> dict[str, Any]:
        """Renew a valid Ontology lease using its opaque token."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(
                session
            ).renew_ontology_lease(
                session_id,
                ontology_id,
                OntologyLeaseRenew(
                    client_request_id=client_request_id,
                    lease_token=lease_token,
                    expected_lease_revision=expected_lease_revision,
                ),
            )
        )

    @server.tool()
    def release_ontology_lease(
        session_id: str,
        ontology_id: str,
        client_request_id: str,
        lease_token: str,
        expected_lease_revision: int,
    ) -> dict[str, Any]:
        """Idempotently release this Build Session's Ontology write lease."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(
                session
            ).release_ontology_lease(
                session_id,
                ontology_id,
                OntologyLeaseRelease(
                    client_request_id=client_request_id,
                    lease_token=lease_token,
                    expected_lease_revision=expected_lease_revision,
                ),
            )
        )


__all__ = ["register_build_sessions"]
