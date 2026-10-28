"""Disposable PostgreSQL schema shared by v5 persistence and boundary tests."""

import json
import os
import uuid
from pathlib import Path

import pytest
from psycopg import sql

from ontoweave_modeling.workspace import WorkspaceRepository


@pytest.fixture
def workspace():
    path = Path(
        os.environ.get(
            "ONTOWEAVE_TEST_POSTGRES_CONFIG", "workspaces/v5-codex-p0/postgres-host.json"
        )
    )
    if not path.exists():
        pytest.skip("set ONTOWEAVE_TEST_POSTGRES_CONFIG to an owned PostgreSQL connection file")
    repository = WorkspaceRepository(
        json.loads(path.read_text()), "v5_test_" + uuid.uuid4().hex, "test-task"
    )
    repository.setup()
    try:
        yield repository
    finally:
        with repository.connect(autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(repository.schema))
            )
