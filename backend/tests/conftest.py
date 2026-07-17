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
from app.main import create_app
from app.repositories.models import ProjectModel, UserModel
from app.security.auth import create_api_key, hash_password
from app.security.auth import AuthPrincipal
from app.security.auth import resolve_api_key
from app.security.http import AuthenticationMiddleware, principal_dependency
from app.mcp.runtime import set_runtime_principal
from fastapi.testclient import TestClient
from uuid import uuid4


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "JSON"


@pytest.fixture(autouse=True)
def legacy_router_principal(monkeypatch):
    """Keep pre-R-008 isolated-router tests focused on their original behavior.

    Main-app and R-008 tests still traverse the real authentication middleware.
    """
    original = TestClient.__init__

    def initialize(client, app, *args, **kwargs):
        has_auth = any(
            middleware.cls is AuthenticationMiddleware
            for middleware in getattr(app, "user_middleware", [])
        )
        if not has_auth:
            app.dependency_overrides[principal_dependency] = lambda: AuthPrincipal(
                subject_type="api_key",
                subject_id="legacy-test-admin",
                actor="key:legacy-test-admin",
                scopes=frozenset({"admin"}),
                project_id=None,
                auth_method="bearer",
            )
        return original(client, app, *args, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", initialize)


@pytest.fixture()
def mcp_principal_factory():
    def activate(
        session: Session,
        project_id: str | None = None,
        scopes: list[str] | None = None,
    ) -> AuthPrincipal:
        _record, plaintext = create_api_key(
            session,
            name=f"mcp-test-{uuid4()}",
            project_id=project_id,
            scopes=scopes or ["admin"],
        )
        principal = resolve_api_key(session, plaintext)
        assert principal is not None
        set_runtime_principal(principal)
        return principal

    yield activate
    set_runtime_principal(None)


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


@pytest.fixture()
def r008_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as session:
        p1 = ProjectModel(id=str(uuid4()), name="P1", normalized_label="P1")
        p2 = ProjectModel(id=str(uuid4()), name="P2", normalized_label="P2")
        session.add_all([p1, p2])
        session.commit()
        org_record, org_key = create_api_key(session, name="org", project_id=None, scopes=["admin"])
        p1_read_record, p1_read_key = create_api_key(
            session, name="p1-read", project_id=p1.id, scopes=["read"]
        )
        p1_model_record, p1_model_key = create_api_key(
            session, name="p1-model", project_id=p1.id, scopes=["model"]
        )
        p1_admin_record, p1_admin_key = create_api_key(
            session, name="p1-admin", project_id=p1.id, scopes=["admin"]
        )
        p2_read_record, _p2_read_key = create_api_key(
            session, name="p2-read", project_id=p2.id, scopes=["read"]
        )
        session.add(
            UserModel(
                id=str(uuid4()),
                username="admin",
                password_hash=hash_password("correct horse battery staple"),
                session_version=1,
            )
        )
        session.commit()
        ids = {
            "p1": p1.id,
            "p2": p2.id,
            "org_key_id": org_record.id,
            "p1_read_key_id": p1_read_record.id,
            "p1_model_key_id": p1_model_record.id,
            "p1_admin_key_id": p1_admin_record.id,
            "p2_read_key_id": p2_read_record.id,
        }
    app = create_app()
    app.state.session_factory = factory
    app.state.session_secret = "test-secret-that-is-stable"
    with TestClient(app) as client:
        yield {
            "client": client,
            "factory": factory,
            "ids": ids,
            "org_key": org_key,
            "p1_read_key": p1_read_key,
            "p1_model_key": p1_model_key,
            "p1_admin_key": p1_admin_key,
        }
    engine.dispose()
