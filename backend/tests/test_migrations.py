"""Regression tests for Alembic migration revisions.

Alembic's default ``alembic_version.version_num`` column is ``varchar(32)``.
Revision IDs longer than 32 characters blow up on clean-database upgrades with
``StringDataRightTruncation``. This module loads every migration module under
``backend/migrations/versions`` and asserts the revision IDs fit the column.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"
MAX_REVISION_LEN = 32
BACKEND_DIR = MIGRATIONS_DIR.parents[1]
POSTGRES_MIGRATION_TEST_ENV = "RUN_POSTGRES_MIGRATION_TESTS"


def _load_migration_modules() -> list[tuple[str, object]]:
    modules: list[tuple[str, object]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append((path.name, module))
    return modules


@pytest.fixture(scope="module")
def migration_modules() -> list[tuple[str, object]]:
    return _load_migration_modules()


def test_revision_ids_fit_default_alembic_column(
    migration_modules: list[tuple[str, object]],
) -> None:
    """Each revision ID must be <= 32 characters (alembic_version.version_num)."""
    offenders: list[str] = []
    for filename, module in migration_modules:
        revision = getattr(module, "revision", None)
        assert isinstance(revision, str), f"{filename} missing revision string"
        if len(revision) > MAX_REVISION_LEN:
            offenders.append(f"{filename}: {revision!r} ({len(revision)} chars)")
    assert not offenders, (
        "Revision IDs exceed alembic_version varchar(32):\n  " + "\n  ".join(offenders)
    )


def test_down_revisions_resolve_to_existing_revisions(
    migration_modules: list[tuple[str, object]],
) -> None:
    """Every down_revision must point to a real revision (or be None for the root)."""
    revisions = {
        module.revision
        for _filename, module in migration_modules
        if hasattr(module, "revision")
    }
    errors: list[str] = []
    for filename, module in migration_modules:
        down_revision = getattr(module, "down_revision", None)
        if down_revision is None:
            continue
        if isinstance(down_revision, tuple):
            for rev in down_revision:
                if rev not in revisions:
                    errors.append(f"{filename}: down_revision {rev!r} not found")
        elif down_revision not in revisions:
            errors.append(f"{filename}: down_revision {down_revision!r} not found")
    assert not errors, "Broken down_revision chain:\n  " + "\n  ".join(errors)


@pytest.fixture()
def isolated_postgres_database() -> str:
    """Create and remove a database used only for an Alembic migration test."""
    database_url = make_url(Settings().database_url)
    database_name = f"ontology_migration_{uuid4().hex}"
    admin_url: URL = database_url.set(database="postgres")
    test_url: URL = database_url.set(database=database_name)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}" TEMPLATE template0'))
    try:
        yield test_url.render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


def _run_alembic(database_url: str, revision: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", revision],
        cwd=BACKEND_DIR,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _relation_type_unique_constraints(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return {
            constraint["name"]
            for constraint in inspect(engine).get_unique_constraints("relation_types")
            if constraint["name"] is not None
        }
    finally:
        engine.dispose()


def _database_revision(database_url: str) -> str:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()


def _migration_head() -> str:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


postgres_migration_test = pytest.mark.skipif(
    os.getenv(POSTGRES_MIGRATION_TEST_ENV) != "1",
    reason=f"set {POSTGRES_MIGRATION_TEST_ENV}=1 to run isolated PostgreSQL Alembic checks",
)


@postgres_migration_test
def test_fresh_postgres_database_upgrades_to_head(isolated_postgres_database: str) -> None:
    """A database with no schema can execute the full migration chain."""
    _run_alembic(isolated_postgres_database, "head")
    assert _database_revision(isolated_postgres_database) == _migration_head()


@postgres_migration_test
def test_0002_upgrades_legacy_relation_type_constraint(isolated_postgres_database: str) -> None:
    """0002 still converts databases created before 0001 was corrected."""
    _run_alembic(isolated_postgres_database, "0001_initial_metadata")
    engine = create_engine(isolated_postgres_database)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE relation_types "
                    "DROP CONSTRAINT uq_relation_types_ontology_name_source_target"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE relation_types "
                    "ADD CONSTRAINT uq_relation_types_ontology_name "
                    "UNIQUE (ontology_id, name)"
                )
            )
    finally:
        engine.dispose()

    _run_alembic(isolated_postgres_database, "0002_relation_type_name_scope")

    constraints = _relation_type_unique_constraints(isolated_postgres_database)
    assert "uq_relation_types_ontology_name_source_target" in constraints
    assert "uq_relation_types_ontology_name" not in constraints
