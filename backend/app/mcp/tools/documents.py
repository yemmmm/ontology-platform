"""Source document MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool
from app.services import documents as document_service


def register_documents(server: FastMCP) -> None:
    @server.tool()
    def list_source_documents(project_id: str) -> dict[str, Any]:
        """List uploaded sources and their deterministic parsing status."""
        return _run_tool(
            lambda session, _driver, _embedding_client: document_service.list_documents(
                session, project_id
            )
        )

    @server.tool()
    def get_source_document_status(document_id: str) -> dict[str, Any]:
        """Read parsing status, content identity, and chunk count for one source."""
        return _run_tool(
            lambda session, _driver, _embedding_client: document_service.get_document(
                session, document_id
            )
        )
