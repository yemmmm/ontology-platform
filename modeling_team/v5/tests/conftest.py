"""Disposable PostgreSQL schema shared by v5 persistence and boundary tests."""

import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest
from psycopg import sql

from ontoweave_modeling.contracts import TaskBinding
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


@pytest.fixture
def task_file(tmp_path):
    materials = tmp_path / "sources"
    materials.mkdir()
    payload = b"A source with a condition and an explicit unknown."
    (materials / "source.md").write_bytes(payload)
    manifest = {
        "source": {
            "path": "source.md",
            "source_ref": "approved-source/v1",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    }
    (materials / "manifest.json").write_text(json.dumps(manifest))
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "roles:\n  modeling: &model\n    model_provider: glm-direct\n"
        "    model: glm-5.3-flash\n    model_reasoning_effort: low\n"
        "  acceptance: *model\n"
    )
    task = {
        "schema_version": "ontoweave-task/v1",
        # Historical flow tests exercise their original frozen single-modeler contract.
        "team_contract": "single-modeler/v1",
        "task_ref": "framework-task",
        "run_id": "framework-run",
        "work_unit_id": "bounded-unit",
        "objective": "Express only the approved source.",
        "materials": str(materials),
        "model_profile": str(profile),
        "instructions": "Preserve conditions and unknowns.",
        "authorization": {"mode": "usage_only", "reference": "test-authorization"},
        "scope": {"mode": "create", "base_url": "http://127.0.0.1:8001"},
        "evaluation": {"freeze_id": "freeze-1", "sha256": "a" * 64, "case_count": 2},
    }
    path = tmp_path / "task.json"
    path.write_text(json.dumps(task))
    return path


@pytest.fixture
def binding(task_file, tmp_path):
    return TaskBinding.prepare(task_file, tmp_path / "run")


@pytest.fixture
def saver(workspace):
    namespace = workspace.schema + "_cp"
    try:
        with workspace.checkpointer(namespace) as saver:
            yield saver
    finally:
        with workspace.connect(autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(namespace))
            )
