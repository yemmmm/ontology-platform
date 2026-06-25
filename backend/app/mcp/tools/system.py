"""Platform health MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool
from app.services.health import check_neo4j, check_postgres


def register_system(server: FastMCP) -> None:
    @server.tool()
    def check_platform_health() -> dict[str, Any]:
        """Verify API, PostgreSQL, and Neo4j are reachable without direct DB credentials."""
        return _run_tool(
            lambda session, driver, _embedding_client: {
                "postgres": check_postgres(session),
                "neo4j": check_neo4j(driver),
            }
        )
