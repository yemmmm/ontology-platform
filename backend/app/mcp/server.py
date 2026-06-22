import json
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from neo4j import Driver
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.repositories.neo4j import create_neo4j_driver, ensure_graph_constraints
from app.repositories.postgres import create_session_factory
from app.services import graph as graph_service
from app.services.embedding import EmbeddingClient

mcp = FastMCP("ontology-platform")

_settings: Settings | None = None
_session_factory: sessionmaker | None = None
_driver: Driver | None = None
_embedding_client: EmbeddingClient | None = None

T = TypeVar("T")


def _jsonable(data: Any) -> Any:
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def _resources() -> tuple[sessionmaker, Driver, EmbeddingClient]:
    global _settings, _session_factory, _driver, _embedding_client
    if _settings is None:
        _settings = Settings()
    if _session_factory is None:
        _session_factory = create_session_factory(_settings)
    if _driver is None:
        _driver = create_neo4j_driver(_settings)
        ensure_graph_constraints(_driver, _settings.embedding_dimensions)
    if _embedding_client is None:
        _embedding_client = EmbeddingClient(_settings)
    return _session_factory, _driver, _embedding_client


def _run_tool(fn: Callable[[Session, Driver, EmbeddingClient], T]) -> dict[str, Any]:
    session_factory, driver, embedding_client = _resources()
    try:
        with session_factory() as session:
            return {"ok": True, "data": _jsonable(fn(session, driver, embedding_client))}
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return {"ok": False, "error": detail, "status_code": exc.status_code}
    except Exception as exc:  # MCP tools should return structured failures.
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def search_entities(
    query: str,
    ontology_id: str | None = None,
    class_id: str | None = None,
    limit: int = 10,
    mode: str = "hybrid",
) -> dict[str, Any]:
    """Recall graph entities globally with optional ontology and class filters."""
    return _run_tool(
        lambda session, driver, embedding_client: graph_service.search_all_entities(
            session,
            driver,
            query,
            class_id,
            ontology_id,
            limit,
            mode,
            embedding_client,
        ),
    )


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


if __name__ == "__main__":
    mcp.run()
