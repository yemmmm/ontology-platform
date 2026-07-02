"""Fact audit MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.api.schemas import FactClaimRead
from app.mcp.runtime import _run_tool
from app.services import facts as facts_service


def _serialize(claims: Any) -> list[dict[str, Any]]:
    return [
        FactClaimRead.model_validate(c).model_dump(mode="json", exclude_none=True)
        for c in claims
    ]


def register_facts(server: FastMCP) -> None:
    @server.tool()
    def generate_fact_claims(version_id: str) -> dict[str, Any]:
        """Deterministically regenerate structured Fact Claims from the draft graph."""
        return _run_tool(
            lambda session, driver, _embedding_client: _serialize(
                facts_service.generate_fact_claims(session, driver, version_id)
            )
        )

    @server.tool()
    def list_fact_claims(
        version_id: str, layer: str | None = None, claim_type: str | None = None
    ) -> dict[str, Any]:
        """List structured Fact Claims stratified by audit layer."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                facts_service.list_fact_claims(session, version_id, layer, claim_type)
            )
        )

    @server.tool()
    def sample_fact_claims(
        version_id: str, config: dict[str, int] | None = None
    ) -> dict[str, Any]:
        """Return a stratified fact sample for human audit."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _serialize(
                facts_service.sample_fact_claims(session, version_id, config)
            )
        )

    @server.tool()
    def execute_rule_definitions(version_id: str) -> dict[str, Any]:
        """Run active deterministic rules and create derived Assertions for review."""
        return _run_tool(
            lambda session, driver, _embedding_client: _serialize(
                facts_service.execute_rule_definitions(session, driver, version_id)
            )
        )

    @server.tool()
    def recall_background_knowledge(
        version_id: str,
        query: str | None = None,
        query_embedding: list[float] | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Recall unanchored background knowledge separately from governed facts."""
        return _run_tool(
            lambda session, _driver, _embedding_client: facts_service.recall_background_knowledge(
                session,
                version_id,
                query=query,
                query_embedding=query_embedding,
                limit=limit,
            )
        )
