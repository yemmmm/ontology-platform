"""Publication readiness MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool
from app.services import publication as publication_service


def register_publication(server: FastMCP) -> None:
    @server.tool()
    def get_publication_readiness(version_id: str) -> dict[str, Any]:
        """Evaluate structured publication gates and return blocking items."""
        return _run_tool(
            lambda session, driver, _embedding_client: publication_service.evaluate_readiness(
                session, driver, version_id
            )
        )
