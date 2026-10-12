"""Independent feedback submission and admin-only internal processing."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool, runtime_principal
from app.services.semantic_feedback import SemanticFeedbackService


def register_semantic_feedback(server: FastMCP):
    @server.tool()
    def submit_semantic_feedback(
        feedback_id: str,
        query_request: dict[str, Any],
        reasons: list[str],
        description: str,
        result_snapshot: dict[str, Any] | None = None,
        snapshot_complete: bool = False,
    ) -> dict[str, Any]:
        """Save a client observation (read scope); reuse the ID and body for unknown receipts.

        This only saves feedback. It does not diagnose, start modeling or modify the model.
        """
        payload = dict(
            feedback_id=feedback_id,
            query_request=query_request,
            reasons=reasons,
            description=description,
            result_snapshot=result_snapshot,
            snapshot_complete=snapshot_complete,
        )
        return _run_tool(
            lambda session, *_: SemanticFeedbackService(session, runtime_principal()).submit(
                payload
            )
        )

    @server.tool()
    def list_semantic_feedback(
        project_id: str, pending_only: bool = True, limit: int = 50, cursor: str | None = None
    ) -> dict[str, Any]:
        """Internal admin: list private feedback in one authorized Project, with bounded pages."""
        return _run_tool(
            lambda session, *_: SemanticFeedbackService(session, runtime_principal()).list(
                project_id, pending_only=pending_only, limit=limit, cursor=cursor
            )
        )

    @server.tool()
    def get_semantic_feedback(feedback_id: str) -> dict[str, Any]:
        """Internal admin: read one private submission and its append-only resolution history."""
        return _run_tool(
            lambda session, *_: SemanticFeedbackService(session, runtime_principal()).get(
                feedback_id
            )
        )

    @server.tool()
    def record_semantic_feedback_resolution(
        feedback_id: str, resolution: dict[str, Any]
    ) -> dict[str, Any]:
        """Internal admin: append a scoped diagnosis and verification reference; no model write.

        A resolved conclusion requires current model revisions, actual readback references
        and an independent validation reference. References are reports, not semantic verdicts.
        """
        return _run_tool(
            lambda session, *_: SemanticFeedbackService(
                session, runtime_principal()
            ).record_resolution(feedback_id, resolution)
        )
