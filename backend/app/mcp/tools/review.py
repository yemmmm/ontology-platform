"""Review batch MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool
from app.services import governance as governance_service


def register_review(server: FastMCP) -> None:
    @server.tool()
    def list_review_items(ontology_id: str) -> dict[str, Any]:
        """List review batches with counts and exact workbench deep links."""
        return _run_tool(
            lambda session, _driver, _embedding_client: governance_service.list_review_batches(
                session, ontology_id
            )
        )

    @server.tool()
    def get_review_batch(review_batch_id: str) -> dict[str, Any]:
        """Read one stable review batch, its status, counts, and workbench deep link."""
        return _run_tool(
            lambda session, _driver, _embedding_client: governance_service.get_review_batch(
                session, review_batch_id
            )
        )
