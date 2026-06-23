"""Graph/entity query MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.runtime import _run_tool
from app.services import graph as graph_service


def register_graph(server: FastMCP) -> None:
    @server.tool()
    def search_entities(
        query: str,
        ontology_id: str | None = None,
        class_id: str | None = None,
        limit: int = 20,
        mode: str = "hybrid",
    ) -> dict[str, Any]:
        """Recall graph entities globally with optional ontology and class filters."""
        return _run_tool(
            lambda session, _driver, embedding_client: graph_service.search_all_entities(
                session,
                _driver,
                query,
                class_id,
                ontology_id,
                limit,
                mode,
                embedding_client,
            ),
        )

    @server.tool()
    def get_entity(
        ontology_id: str,
        entity_id: str,
        include_relations: bool = True,
        relation_limit: int = 50,
    ) -> dict[str, Any]:
        """Fetch one entity and, optionally, its incoming/outgoing relations."""
        return _run_tool(
            lambda session, driver, _embedding_client: graph_service.get_entity_with_relations(
                session,
                driver,
                ontology_id,
                entity_id,
                include_relations,
                relation_limit,
            ),
        )

    @server.tool()
    def find_related_entities(
        ontology_id: str,
        entity_id: str,
        depth: int = 1,
        direction: str = "both",
        relation_type_ids: list[str] | None = None,
        target_class_ids: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Find graph neighbors for an entity with semantic filters."""
        return _run_tool(
            lambda session, driver, _embedding_client: graph_service.find_related_entities(
                session,
                driver,
                ontology_id,
                entity_id,
                depth,
                direction,
                relation_type_ids,
                target_class_ids,
                limit,
            ),
        )

    @server.tool()
    def validate_entity(
        ontology_id: str,
        class_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate entity properties against effective ontology class schema."""
        return _run_tool(
            lambda session, _driver, _embedding_client: graph_service.validate_entity_payload(
                session,
                ontology_id,
                class_id,
                properties,
            ),
        )

    @server.tool()
    def explain_entity(
        ontology_id: str,
        entity_id: str,
        depth: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return one entity with schema, relation context, and a short explanation."""
        return _run_tool(
            lambda session, driver, _embedding_client: graph_service.explain_entity(
                session,
                driver,
                ontology_id,
                entity_id,
                depth,
                limit,
            ),
        )
