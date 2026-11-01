"""Exercise the migration and stale-session edits on an owned PostgreSQL schema."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import CompetencyQuestionCreate, CompetencyQuestionUpdate
from app.core.config import Settings
from app.services import interview


def test_postgres_upgrade_keeps_legacy_rows_and_serializes_question_versions():
    engine = create_engine(Settings().database_url)
    schema = "test_custom_cq_" + uuid4().hex
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            conn.execute(
                text(
                    "CREATE TABLE projects (id varchar(36) PRIMARY KEY, name text, normalized_label text, description text, created_at timestamptz default now(), updated_at timestamptz default now())"
                )
            )
            conn.execute(text("CREATE TABLE ontologies (id varchar(36) PRIMARY KEY)"))
            conn.execute(
                text(
                    "CREATE TABLE competency_questions (id varchar(36) PRIMARY KEY, project_id varchar(36) REFERENCES projects(id), ontology_id varchar(36) NOT NULL REFERENCES ontologies(id), question text NOT NULL, importance integer NOT NULL, position integer NOT NULL, status varchar(32) NOT NULL, active boolean NOT NULL, source_answer_ids jsonb NOT NULL, source_brief_fields jsonb NOT NULL, query_definition jsonb NOT NULL, validation_result jsonb NOT NULL, created_at timestamptz default now(), updated_at timestamptz default now())"
                )
            )
            conn.execute(
                text("INSERT INTO projects(id,name,normalized_label) VALUES ('p','P','P')")
            )
            conn.execute(text("INSERT INTO ontologies VALUES ('old-ontology')"))
            conn.execute(
                text(
                    "INSERT INTO competency_questions(id,project_id,ontology_id,question,importance,position,status,active,source_answer_ids,source_brief_fields,query_definition,validation_result) VALUES ('old','p','old-ontology','old count',3,0,'testable',true,'[]','[]','{}','{}')"
                )
            )
            path = Path(__file__).resolve().parents[1] / "migrations/versions/0037_custom_cq.py"
            spec = importlib.util.spec_from_file_location("cq_migration", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
            old = conn.execute(
                text(
                    "SELECT ontology_id,content_revision,cq_definition FROM competency_questions WHERE id='old'"
                )
            ).one()
            assert tuple(old) == ("old-ontology", 1, {})
        with engine.connect() as first, engine.connect() as second:
            for connection in (first, second):
                connection.execute(text(f'SET search_path TO "{schema}"'))
                connection.commit()
            with Session(first) as one, Session(second) as two:
                row = interview.create_question(
                    one, "p", CompetencyQuestionCreate(question="项目问题")
                )
                from app.repositories.models import CompetencyQuestionModel

                stale = two.get(CompetencyQuestionModel, row.id)
                interview.update_question(
                    one, row.id, CompetencyQuestionUpdate(question="已更新", expected_revision=1)
                )
                with pytest.raises(HTTPException) as error:
                    interview.update_question(
                        two,
                        stale.id,
                        CompetencyQuestionUpdate(question="不应覆盖", expected_revision=1),
                    )
                assert error.value.status_code == 409
                two.rollback()
                assert two.get(CompetencyQuestionModel, row.id).question == "已更新"
        with engine.begin() as conn:
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            conn.execute(
                text("UPDATE competency_questions SET external_id='external' WHERE id='old'")
            )
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(
                    text(
                        "UPDATE competency_questions SET external_id='external' WHERE ontology_id IS NULL"
                    )
                )
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
