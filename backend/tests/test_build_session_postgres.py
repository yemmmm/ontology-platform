"""Opt-in PostgreSQL race coverage for the R-003 Ontology lease slot.

Run with ``RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest
tests/test_build_session_postgres.py`` after applying migrations.  The normal
suite remains SQLite-only, where ``SELECT ... FOR UPDATE`` cannot prove the
two-connection insert race.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.schemas import BuildSessionCreate, OntologyLeaseAcquire
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.services.build_sessions import BuildSessionError, BuildSessionService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_CONCURRENCY_TESTS") != "1",
    reason="set RUN_POSTGRES_CONCURRENCY_TESTS=1 to use the migrated PostgreSQL database",
)


def test_concurrent_first_acquire_has_one_winner_and_one_stable_conflict(
    monkeypatch,
) -> None:
    settings = Settings()
    engine = create_engine(settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex
    project_id = f"p-{suffix}"
    ontology_id = f"o-{suffix}"

    with factory() as session:
        session.add(
            ProjectModel(
                id=project_id,
                name=f"R-003 race {suffix}",
                normalized_label=f"r-003 race {suffix}",
            )
        )
        session.flush()
        session.add(
            OntologyModel(
                id=ontology_id,
                project_id=project_id,
                name=f"Race ontology {suffix}",
            )
        )
        session.commit()

    session_ids: list[str] = []
    for index in (1, 2):
        with factory() as session:
            detail, created = BuildSessionService(session, settings).create_session(
                project_id,
                BuildSessionCreate(client_session_id=f"race-{suffix}-{index}"),
            )
            assert created is True
            session_ids.append(detail["id"])

    # Force both transactions to observe the initially empty lease slot before
    # either inserts.  This deterministically exercises the PK-conflict retry,
    # rather than relying on thread scheduling to happen to create the race.
    empty_slot_barrier = Barrier(2)
    original_lease = BuildSessionService._lease  # noqa: SLF001 - concurrency seam

    def synchronized_empty_slot(self, candidate_ontology_id, *, lock=False):
        lease = original_lease(self, candidate_ontology_id, lock=lock)
        if candidate_ontology_id == ontology_id and lock and lease is None:
            empty_slot_barrier.wait(timeout=10)
        return lease

    monkeypatch.setattr(BuildSessionService, "_lease", synchronized_empty_slot)

    def acquire(index: int) -> tuple[str, str]:
        with factory() as session:
            try:
                result = BuildSessionService(session, settings).acquire_ontology_lease(
                    session_ids[index],
                    ontology_id,
                    OntologyLeaseAcquire(
                        client_request_id=f"acquire-{suffix}-{index}",
                        expected_session_revision=1,
                    ),
                )
                return "acquired", result["build_session_id"]
            except BuildSessionError as exc:
                return "error", exc.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(acquire, (0, 1)))
        assert sorted(item[0] for item in results) == ["acquired", "error"]
        assert next(item[1] for item in results if item[0] == "error") == (
            "ontology_lease_conflict"
        )
        winner = next(item[1] for item in results if item[0] == "acquired")
        assert winner in session_ids
    finally:
        with factory() as session:
            project = session.get(ProjectModel, project_id)
            if project is not None:
                session.delete(project)
                session.commit()
        engine.dispose()
