"""Test fixtures for Phase 4 governance service tests.

Some Phase 4 services (registry, graph set, derived state) issue SQLAlchemy
``select`` queries with multiple filters and ``distinct()``. Mocking them by
hand is brittle, so we use a real in-memory SQLite session that compiles the
Postgres-only JSONB type down to SQLite JSON.
"""

from __future__ import annotations

from typing import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.repositories.postgres import Base


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "JSON"


@pytest.fixture()
def in_memory_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite does not enforce foreign keys by default; enable for CASCADE.
    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
