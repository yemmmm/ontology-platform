"""MCP runtime: process-wide resources, JSON envelope, and error mapping."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

from neo4j import Driver
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.mcp.errors import map_exception
from app.repositories.neo4j import create_neo4j_driver, ensure_graph_constraints
from app.repositories.postgres import create_session_factory
from app.services.embedding import EmbeddingClient

T = TypeVar("T")

_settings: Settings | None = None
_session_factory: sessionmaker | None = None
_driver: Driver | None = None
_embedding_client: EmbeddingClient | None = None


def _jsonable(data: Any) -> Any:
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def get_resources() -> tuple[sessionmaker, Driver, EmbeddingClient]:
    """Lazily initialize and return the process-wide MCP resources.

    Test seam: tests can monkeypatch this function to inject fakes without
    mutating module globals.
    """
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


def reset_resources() -> None:
    """Clear cached singletons. Tests use this for isolation."""
    global _settings, _session_factory, _driver, _embedding_client
    _settings = None
    _session_factory = None
    _driver = None
    _embedding_client = None


def _run_tool(fn: Callable[[Session, Driver, EmbeddingClient], T]) -> dict[str, Any]:
    session_factory, driver, embedding_client = get_resources()
    try:
        with session_factory() as session:
            return {"ok": True, "data": _jsonable(fn(session, driver, embedding_client))}
    except Exception as exc:
        code, message = map_exception(exc)
        return {"ok": False, "error": message, "error_code": code}
