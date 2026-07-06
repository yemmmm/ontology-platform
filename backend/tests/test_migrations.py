"""Regression tests for Alembic migration revisions.

Alembic's default ``alembic_version.version_num`` column is ``varchar(32)``.
Revision IDs longer than 32 characters blow up on clean-database upgrades with
``StringDataRightTruncation``. This module loads every migration module under
``backend/migrations/versions`` and asserts the revision IDs fit the column.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"
MAX_REVISION_LEN = 32


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
