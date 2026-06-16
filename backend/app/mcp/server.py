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

mcp = FastMCP("ontology-platform")

_settings: Settings | None = None
_session_factory: sessionmaker | None = None
_driver: Driver | None = None

T = TypeVar("T")


def _jsonable(data: Any) -> Any:
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def _resources() -> tuple[Settings, sessionmaker, Driver]:
    global _settings, _session_factory, _driver
    if _settings is None:
        _settings = Settings()
    if _session_factory is None:
        _session_factory = create_session_factory(_settings)
    if _driver is None:
        _driver = create_neo4j_driver(_settings)
        ensure_graph_constraints(_driver)
    return _settings, _session_factory, _driver


def _authorize(settings: Settings, api_key: str | None) -> dict[str, Any] | None:
    if api_key != settings.mcp_api_key:
        return {"ok": False, "error": "Invalid MCP API key"}
    return None


def _run_tool(api_key: str | None, fn: Callable[[Session, Driver], T]) -> dict[str, Any]:
    settings, session_factory, driver = _resources()
    auth_error = _authorize(settings, api_key)
    if auth_error is not None:
        return auth_error
    try:
        with session_factory() as session:
            return {"ok": True, "data": _jsonable(fn(session, driver))}
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return {"ok": False, "error": detail, "status_code": exc.status_code}
    except Exception as exc:  # MCP tools should return structured failures.
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def search_entities(
    ontology_id: str,
    query: str,
    class_id: str | None = None,
    limit: int = 10,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Search ontology graph entities by text and optional class filter."""
    return _run_tool(
        api_key,
        lambda session, driver: graph_service.search_entities(
            session,
            driver,
            ontology_id,
            query,
            class_id,
            limit,
        ),
    )


@mcp.tool()
def get_entity(
    ontology_id: str,
    entity_id: str,
    include_relations: bool = True,
    relation_limit: int = 50,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Fetch one entity and, optionally, its incoming/outgoing relations."""
    return _run_tool(
        api_key,
        lambda session, driver: graph_service.get_entity_with_relations(
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
    api_key: str | None = None,
) -> dict[str, Any]:
    """Find graph neighbors for an entity with semantic filters."""
    return _run_tool(
        api_key,
        lambda session, driver: graph_service.find_related_entities(
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
    api_key: str | None = None,
) -> dict[str, Any]:
    """Validate entity properties against effective ontology class schema."""
    return _run_tool(
        api_key,
        lambda session, _driver: graph_service.validate_entity_payload(
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
    api_key: str | None = None,
) -> dict[str, Any]:
    """Return one entity with schema, relation context, and a short explanation."""
    return _run_tool(
        api_key,
        lambda session, driver: graph_service.explain_entity(
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
