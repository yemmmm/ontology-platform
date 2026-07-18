"""Opt-in real PostgreSQL concurrency coverage for R1.1-002 workflow records."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.schemas import (
    BuildSessionCreate,
    ModelingExecutionEventCreate,
    ModelingWorkflowArtifactCreate,
)
from app.core.config import Settings
from app.repositories.models import ProjectModel
from app.services.build_sessions import BuildSessionService
from app.services.modeling_workflow import ModelingWorkflowError, ModelingWorkflowService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_CONCURRENCY_TESTS") != "1",
    reason="set RUN_POSTGRES_CONCURRENCY_TESTS=1 to use migrated PostgreSQL",
)


def _event(client_event_id: str, event_type: str = "phase_completed", **changes):
    values = {
        "client_event_id": client_event_id,
        "workflow_name": "ontology-builder",
        "workflow_version": "postgres-v1",
        "phase": "global_scan",
        "event_type": event_type,
        "status": "completed",
        "report_source": "agent_reported",
        "actor_role": "main_agent",
        "summary": event_type,
    }
    values.update(changes)
    return ModelingExecutionEventCreate(**values)


@pytest.fixture()
def postgres_workflow():
    settings = Settings()
    engine = create_engine(settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    project_id = str(uuid4())
    with factory() as session:
        session.add(ProjectModel(id=project_id, name="R1.1 race", normalized_label=project_id))
        session.commit()
        detail, _ = BuildSessionService(session, settings).create_session(
            project_id, BuildSessionCreate(client_session_id=f"race-{uuid4()}")
        )
        session_id = detail["id"]
    try:
        yield factory, session_id
    finally:
        with factory() as session:
            project = session.get(ProjectModel, project_id)
            if project is not None:
                session.delete(project)
                session.commit()
        engine.dispose()


def test_concurrent_artifact_idempotency_and_event_sequences(postgres_workflow):
    factory, session_id = postgres_workflow
    artifact = ModelingWorkflowArtifactCreate(
        client_version_id="concurrent-pack-v1",
        artifact_key="business-knowledge-pack",
        artifact_type="business_knowledge_pack",
        content_format="json",
        content={"scope": "concurrency"},
        created_by_role="business_organizer",
        workflow_name="ontology-builder",
        workflow_version="postgres-v1",
    )

    def create_artifact(_index):
        with factory() as session:
            item, created = ModelingWorkflowService(session, actor="key:race").create_artifact(
                session_id, artifact
            )
            return item["workflow_artifact_id"], created

    with ThreadPoolExecutor(max_workers=2) as pool:
        artifacts = list(pool.map(create_artifact, (0, 1)))
    assert len({item[0] for item in artifacts}) == 1
    assert sorted(item[1] for item in artifacts) == [False, True]

    def record_event(index):
        with factory() as session:
            item, _ = ModelingWorkflowService(session, actor=f"key:event-{index}").record_event(
                session_id, _event(f"concurrent-event-{index}")
            )
            return item["sequence"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        sequences = list(pool.map(record_event, (1, 2)))
    assert sorted(sequences) == [1, 2]


def test_concurrent_question_answer_has_one_linear_winner(postgres_workflow):
    factory, session_id = postgres_workflow
    with factory() as session:
        opened, _ = ModelingWorkflowService(session, actor="key:main").record_event(
            session_id,
            _event(
                "question-open",
                "question_asked",
                phase="business_confirmation",
                status="recorded",
                question_id="question-concurrent",
                question_state="open",
                question_text="Which scope is authoritative?",
            ),
        )

    def answer(index):
        with factory() as session:
            try:
                item, _ = ModelingWorkflowService(
                    session, actor=f"key:answer-{index}"
                ).record_event(
                    session_id,
                    _event(
                        f"question-answer-{index}",
                        "answer_recorded",
                        phase="business_confirmation",
                        status="recorded",
                        report_source="user_reported",
                        actor_role="user",
                        question_id="question-concurrent",
                        question_state="answered",
                        answer_text=f"Answer {index}",
                        expected_question_head_event_id=opened["execution_event_id"],
                    ),
                )
                return "ok", item["execution_event_id"]
            except ModelingWorkflowError as exc:
                return "error", exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(answer, (1, 2)))
    assert sorted(item[0] for item in results) == ["error", "ok"]
    assert next(item[1] for item in results if item[0] == "error") == "question_state_conflict"
