"""R1.1-002 workflow artifact/event service invariants on SQLite."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    BuildSessionCreate,
    ModelingExecutionEventCreate,
    ModelingWorkflowArtifactCreate,
)
from app.core.config import Settings
from app.repositories.models import (
    BuildSessionModel,
    ModelingExecutionEventModel,
    ModelingBatchAttemptModel,
    ModelingBatchModel,
    ModelingWorkflowArtifactModel,
    OntologyModel,
    ProjectModel,
    SemanticStatementOccurrenceModel,
)
from app.services.build_sessions import BuildSessionService
from app.services.modeling_batches import ModelingBatchService
from app.services.modeling_workflow import (
    ARTIFACT_CONTENT_LIMIT,
    EVENT_PAYLOAD_LIMIT,
    EXPORT_LIMIT,
    ModelingWorkflowError,
    ModelingWorkflowService,
    _canonical_json,
)
from app.services.semantic_lineage_identity import occurrence_id_for, statement_id_for_quad


@pytest.fixture()
def workflow(in_memory_session: Session):
    project_id = f"workflow-project-{uuid4().hex}"
    ontology_id = str(uuid4())
    in_memory_session.add(ProjectModel(id=project_id, name="Workflow", normalized_label="workflow"))
    in_memory_session.flush()
    in_memory_session.add(
        OntologyModel(id=ontology_id, project_id=project_id, name="Workflow ontology")
    )
    in_memory_session.commit()
    detail, created = BuildSessionService(in_memory_session, Settings()).create_session(
        project_id, BuildSessionCreate(client_session_id=f"session-{uuid4().hex}")
    )
    assert created
    return (
        ModelingWorkflowService(in_memory_session, actor="key:test-model"),
        in_memory_session,
        detail["id"],
        ontology_id,
    )


def _artifact(**changes):
    values = {
        "client_version_id": "pack-v1",
        "artifact_key": "business-knowledge-pack",
        "artifact_type": "business_knowledge_pack",
        "content_format": "json",
        "content": {"scope": "workflow", "goals": ["answer questions"]},
        "created_by_role": "business_organizer",
        "workflow_name": "ontology-builder",
        "workflow_version": "r1.1-v1",
        "role_prompt_version": "organizer-v1",
    }
    values.update(changes)
    return ModelingWorkflowArtifactCreate(**values)


def _event(client_event_id: str, event_type: str = "phase_completed", **changes):
    values = {
        "client_event_id": client_event_id,
        "workflow_name": "ontology-builder",
        "workflow_version": "r1.1-v1",
        "phase": "global_scan",
        "event_type": event_type,
        "status": "completed",
        "report_source": "agent_reported",
        "actor_role": "main_agent",
        "summary": f"Recorded {event_type}",
    }
    values.update(changes)
    return ModelingExecutionEventCreate(**values)


def _assert_error(error, code, status=409):
    assert error.value.code == code
    assert error.value.status_code == status


def _lineage_occurrence(session: Session, ontology_id: str, *, suffix: str) -> str:
    subject = f"https://workflow.test/resource/{suffix}"
    predicate = "https://workflow.test/property/status"
    obj = '"known"'
    graph_iri = f"https://workflow.test/graph/{suffix}"
    statement_id = statement_id_for_quad(subject, predicate, obj, graph_iri)
    session.add(
        SemanticStatementOccurrenceModel(
            id=occurrence_id_for(statement_id, 1),
            ontology_id=ontology_id,
            graph_set_id=None,
            statement_id=statement_id,
            subject_iri=subject,
            predicate_iri=predicate,
            object_ntriples=obj,
            graph_iri=graph_iri,
            graph_revision=1,
            assertion_kind="asserted",
            status="active",
        )
    )
    session.commit()
    return statement_id


def _event_with_canonical_size(client_event_id: str, size: int):
    base = _event(client_event_id, decisions=[{"padding": ""}])
    base_size = len(_canonical_json(base.model_dump(mode="json")))
    assert base_size <= size
    payload = _event(client_event_id, decisions=[{"padding": "x" * (size - base_size)}])
    assert len(_canonical_json(payload.model_dump(mode="json"))) == size
    return payload


def test_artifact_versions_are_canonical_linear_idempotent_and_pageable(workflow):
    service, session, session_id, ontology_id = workflow
    first, created = service.create_artifact(session_id, _artifact(ontology_id=ontology_id))
    retry, retry_created = service.create_artifact(
        session_id,
        _artifact(
            content={"goals": ["answer questions"], "scope": "workflow"}, ontology_id=ontology_id
        ),
    )
    assert created is True and retry_created is False
    assert retry["workflow_artifact_id"] == first["workflow_artifact_id"]
    assert retry["content_hash"] == first["content_hash"]

    second, second_created = service.create_artifact(
        session_id,
        _artifact(
            client_version_id="pack-v2",
            content={"scope": "workflow", "goals": ["answer questions"], "confirmed": True},
            ontology_id=ontology_id,
            supersedes_workflow_artifact_id=first["workflow_artifact_id"],
        ),
    )
    assert second_created is True and second["version"] == 2
    assert service.get_artifact(first["workflow_artifact_id"])["version"] == 1
    current = service.list_artifacts(session_id, current_only=True)
    assert [item["version"] for item in current["items"]] == [2]
    page1 = service.list_artifacts(session_id, limit=1)
    page2 = service.list_artifacts(session_id, cursor=page1["next_cursor"], limit=1)
    assert page1["items"][0]["workflow_artifact_id"] != page2["items"][0]["workflow_artifact_id"]
    assert session.scalar(select(func.count(ModelingWorkflowArtifactModel.id))) == 2


def test_artifact_stale_version_idempotency_size_and_secret_fail_closed(workflow):
    service, session, session_id, _ontology_id = workflow
    first, _ = service.create_artifact(session_id, _artifact())
    with pytest.raises(ModelingWorkflowError) as idempotency:
        service.create_artifact(session_id, _artifact(content={"different": True}))
    _assert_error(idempotency, "idempotency_conflict")
    with pytest.raises(ModelingWorkflowError) as missing_head:
        service.create_artifact(session_id, _artifact(client_version_id="pack-v2"))
    _assert_error(missing_head, "workflow_artifact_version_conflict")
    with pytest.raises(ModelingWorkflowError) as too_large:
        service.create_artifact(
            session_id,
            _artifact(
                client_version_id="pack-large",
                content_format="markdown",
                content="x" * (1024 * 1024 + 1),
                supersedes_workflow_artifact_id=first["workflow_artifact_id"],
            ),
        )
    _assert_error(too_large, "workflow_artifact_too_large", 413)
    fake_secret = "sk_model_" + "A" * 32
    with pytest.raises(ModelingWorkflowError) as secret:
        service.create_artifact(
            session_id,
            _artifact(
                client_version_id="pack-secret",
                content={"notes": fake_secret},
                supersedes_workflow_artifact_id=first["workflow_artifact_id"],
            ),
        )
    _assert_error(secret, "secret_in_payload", 422)
    assert fake_secret not in str(secret.value)
    assert session.scalar(select(func.count(ModelingWorkflowArtifactModel.id))) == 1


def test_exact_artifact_event_and_export_size_boundaries(workflow):
    service, _session, session_id, _ontology_id = workflow
    artifact, created = service.create_artifact(
        session_id,
        _artifact(
            client_version_id="exact-artifact-v1",
            artifact_key="exact-artifact",
            artifact_type="review_report",
            content_format="markdown",
            content="x" * ARTIFACT_CONTENT_LIMIT,
        ),
    )
    assert created is True
    assert artifact["content_size_bytes"] == ARTIFACT_CONTENT_LIMIT
    with pytest.raises(ModelingWorkflowError) as artifact_too_large:
        service.create_artifact(
            session_id,
            _artifact(
                client_version_id="oversized-artifact-v1",
                artifact_key="oversized-artifact",
                artifact_type="review_report",
                content_format="markdown",
                content="x" * (ARTIFACT_CONTENT_LIMIT + 1),
            ),
        )
    _assert_error(artifact_too_large, "workflow_artifact_too_large", 413)

    event, event_created = service.record_event(
        session_id, _event_with_canonical_size("exact-event", EVENT_PAYLOAD_LIMIT)
    )
    assert event_created is True and event["sequence"] == 1
    with pytest.raises(ModelingWorkflowError) as event_too_large:
        service.record_event(
            session_id,
            _event_with_canonical_size("oversized-event", EVENT_PAYLOAD_LIMIT + 1),
        )
    _assert_error(event_too_large, "invalid_modeling_workflow_payload", 413)

    service._assert_export_size(b"x" * EXPORT_LIMIT)
    with pytest.raises(ModelingWorkflowError) as export_too_large:
        service._assert_export_size(b"x" * (EXPORT_LIMIT + 1))
    _assert_error(export_too_large, "modeling_workflow_export_too_large", 413)


def test_question_current_head_cas_reopen_and_correction_preserve_history(workflow):
    service, session, session_id, _ontology_id = workflow
    opened, _ = service.record_event(
        session_id,
        _event(
            "q-open",
            "question_asked",
            phase="business_confirmation",
            status="recorded",
            question_id="q-scope",
            question_state="open",
            question_text="Should API logs be in scope?",
        ),
    )
    answered, _ = service.record_event(
        session_id,
        _event(
            "q-answer",
            "answer_recorded",
            phase="business_confirmation",
            status="recorded",
            report_source="user_reported",
            actor_role="user",
            question_id="q-scope",
            question_state="answered",
            answer_text="Yes, include execution logs.",
            expected_question_head_event_id=opened["execution_event_id"],
        ),
    )
    with pytest.raises(ModelingWorkflowError) as stale:
        service.record_event(
            session_id,
            _event(
                "q-stale",
                "answer_recorded",
                phase="business_confirmation",
                question_id="q-scope",
                question_state="skipped",
                answer_reason="stale branch",
                expected_question_head_event_id=opened["execution_event_id"],
            ),
        )
    _assert_error(stale, "question_state_conflict")

    corrected, _ = service.record_event(
        session_id,
        _event(
            "q-correct",
            "answer_recorded",
            phase="business_confirmation",
            report_source="user_reported",
            actor_role="user",
            question_id="q-scope",
            question_state="uncertain",
            answer_reason="Only API execution logs are confirmed.",
            expected_question_head_event_id=answered["execution_event_id"],
            supersedes_execution_event_id=answered["execution_event_id"],
        ),
    )
    reopened, _ = service.record_event(
        session_id,
        _event(
            "q-reopen",
            "question_asked",
            phase="business_confirmation",
            status="recorded",
            question_id="q-scope",
            question_state="reopened",
            question_text="Do UI logs also matter?",
            expected_question_head_event_id=corrected["execution_event_id"],
        ),
    )
    summary = service.summary(session_id)
    assert summary["question_states"] == [
        {
            "question_id": "q-scope",
            "head_event_id": reopened["execution_event_id"],
            "state": "reopened",
            "sequence": 4,
        }
    ]
    assert session.scalar(select(func.count(ModelingExecutionEventModel.id))) == 4
    assert session.get(BuildSessionModel, session_id).revision == 1


def test_event_artifact_refs_idempotency_export_and_terminal_guard(workflow):
    service, session, session_id, _ontology_id = workflow
    artifact, _ = service.create_artifact(session_id, _artifact())
    event, created = service.record_event(
        session_id,
        _event(
            "artifact-created",
            "artifact_created",
            output_workflow_artifact_ids=[artifact["workflow_artifact_id"]],
            next_step="Confirm business scope",
        ),
    )
    retry, retry_created = service.record_event(
        session_id,
        _event(
            "artifact-created",
            "artifact_created",
            output_workflow_artifact_ids=[artifact["workflow_artifact_id"]],
            next_step="Confirm business scope",
        ),
    )
    assert created is True and retry_created is False
    assert retry["execution_event_id"] == event["execution_event_id"]
    exported = service.export(session_id, export_format="json")
    assert exported["current_artifact_index"]["business-knowledge-pack"]["version"] == 1
    assert exported["events"][0]["next_step"] == "Confirm business scope"
    markdown = service.export(session_id, export_format="markdown")
    assert "artifact_created" in markdown and "platform_observed" not in markdown

    row = session.get(BuildSessionModel, session_id)
    row.status = "completed"
    session.commit()
    with pytest.raises(ModelingWorkflowError) as terminal:
        service.record_event(session_id, _event("after-terminal"))
    _assert_error(terminal, "session_terminal")


def test_foreign_artifact_reference_and_platform_source_are_rejected(workflow):
    service, session, session_id, _ontology_id = workflow
    other_project = ProjectModel(id=f"other-{uuid4().hex}", name="Other", normalized_label="other")
    session.add(other_project)
    session.commit()
    other, _ = BuildSessionService(session, Settings()).create_session(
        other_project.id, BuildSessionCreate(client_session_id=f"other-{uuid4().hex}")
    )
    foreign, _ = service.create_artifact(other["id"], _artifact())
    with pytest.raises(ModelingWorkflowError) as conflict:
        service.record_event(
            session_id,
            _event(
                "foreign-ref",
                "artifact_created",
                output_workflow_artifact_ids=[foreign["workflow_artifact_id"]],
            ),
        )
    _assert_error(conflict, "workflow_reference_conflict")
    with pytest.raises(ValueError):
        _event("platform-source", report_source="platform_observed")


def test_attempt_finding_fingerprints_are_stable_and_disambiguate_same_code_path():
    findings = [
        {
            "code": "invalid_dependency",
            "severity": "error",
            "scope": "item",
            "client_item_ids": ["item-a"],
            "path": ["depends_on"],
            "message": "missing dependency",
            "details": {"dependency": "missing"},
            "blocking": True,
            "retryable": False,
        },
        {
            "code": "invalid_dependency",
            "severity": "error",
            "scope": "item",
            "client_item_ids": ["item-b"],
            "path": ["depends_on"],
            "message": "missing dependency",
            "details": {"dependency": "missing"},
            "blocking": True,
            "retryable": False,
        },
    ]
    first = ModelingBatchService._fingerprint_findings("attempt-1", findings)
    retry = ModelingBatchService._fingerprint_findings("attempt-1", findings)
    assert first == retry
    assert first[0]["finding_fingerprint"] != first[1]["finding_fingerprint"]
    assert all(len(item["finding_fingerprint"]) == 64 for item in first)


def test_event_finding_reference_requires_exact_attempt_fingerprint(workflow):
    service, session, session_id, ontology_id = workflow
    project_id = session.get(BuildSessionModel, session_id).project_id
    batch = ModelingBatchModel(
        id=str(uuid4()),
        project_id=project_id,
        ontology_id=ontology_id,
        build_session_id=session_id,
        client_batch_id="finding-batch",
        content_hash="a" * 64,
        status="open",
    )
    attempt = ModelingBatchAttemptModel(
        id=str(uuid4()),
        batch=batch,
        build_session_id=session_id,
        idempotency_key="finding-attempt",
        request_hash="b" * 64,
        mode="dry_run",
        status="validation_failed",
        expected_workspace_version="workspace-v1",
        findings=[{"code": "invalid_dependency", "finding_fingerprint": "c" * 64}],
    )
    session.add_all([batch, attempt])
    session.commit()
    accepted, _ = service.record_event(
        session_id,
        _event(
            "finding-reference",
            "review_completed",
            phase="review",
            related_resources=[
                {
                    "resource_type": "finding",
                    "attempt_id": attempt.id,
                    "finding_fingerprint": "c" * 64,
                }
            ],
        ),
    )
    assert accepted["related_resources"][0]["finding_fingerprint"] == "c" * 64
    with pytest.raises(ModelingWorkflowError) as unknown:
        service.record_event(
            session_id,
            _event(
                "unknown-finding",
                "rework_requested",
                phase="review",
                related_resources=[
                    {
                        "resource_type": "finding",
                        "attempt_id": attempt.id,
                        "finding_fingerprint": "d" * 64,
                    }
                ],
            ),
        )
    _assert_error(unknown, "workflow_reference_conflict")


def test_lineage_reference_uses_existing_read_model_and_fails_closed(workflow):
    service, session, session_id, ontology_id = workflow
    known_statement_id = _lineage_occurrence(session, ontology_id, suffix="known")

    accepted, _ = service.record_event(
        session_id,
        _event(
            "known-lineage",
            "verification_completed",
            phase="verification",
            related_resources=[
                {
                    "resource_type": "lineage",
                    "ontology_id": ontology_id,
                    "target_type": "statement",
                    "target_id": known_statement_id,
                }
            ],
        ),
    )
    assert accepted["related_resources"][0]["target_id"] == known_statement_id

    invalid_references = [
        {
            "client_event_id": "missing-lineage",
            "ontology_id": ontology_id,
            "target_type": "statement",
            "target_id": "0" * 64,
        },
        {
            "client_event_id": "type-mismatched-lineage",
            "ontology_id": ontology_id,
            "target_type": "resource",
            "target_id": known_statement_id,
        },
    ]
    for invalid in invalid_references:
        with pytest.raises(ModelingWorkflowError) as conflict:
            service.record_event(
                session_id,
                _event(
                    invalid["client_event_id"],
                    "verification_completed",
                    phase="verification",
                    related_resources=[
                        {
                            "resource_type": "lineage",
                            "ontology_id": invalid["ontology_id"],
                            "target_type": invalid["target_type"],
                            "target_id": invalid["target_id"],
                        }
                    ],
                ),
            )
        _assert_error(conflict, "workflow_reference_conflict")

    foreign_project = ProjectModel(
        id=f"foreign-lineage-{uuid4().hex}",
        name="Foreign lineage",
        normalized_label=f"foreign-lineage-{uuid4().hex}",
    )
    foreign_ontology = OntologyModel(
        id=str(uuid4()), project_id=foreign_project.id, name="Foreign lineage"
    )
    session.add_all([foreign_project, foreign_ontology])
    session.commit()
    foreign_statement_id = _lineage_occurrence(session, foreign_ontology.id, suffix="foreign")
    with pytest.raises(ModelingWorkflowError) as foreign:
        service.record_event(
            session_id,
            _event(
                "foreign-lineage",
                "verification_completed",
                phase="verification",
                related_resources=[
                    {
                        "resource_type": "lineage",
                        "ontology_id": foreign_ontology.id,
                        "target_type": "statement",
                        "target_id": foreign_statement_id,
                    }
                ],
            ),
        )
    _assert_error(foreign, "workflow_reference_conflict")
