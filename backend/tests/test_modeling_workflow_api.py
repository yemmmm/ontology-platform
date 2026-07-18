"""REST/R-008 contract for R1.1-002 workflow records."""

from uuid import uuid4

from app.api.schemas import BuildSessionCreate
from app.core.config import Settings
from app.repositories.models import OntologyModel, SemanticStatementOccurrenceModel
from app.services.build_sessions import BuildSessionService
from app.services.semantic_lineage_identity import occurrence_id_for, statement_id_for_quad


def _bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def _seed_session(r008_client, project_key: str):
    project_id = r008_client["ids"][project_key]
    ontology_id = str(uuid4())
    with r008_client["factory"]() as session:
        session.add(OntologyModel(id=ontology_id, project_id=project_id, name="Workflow API"))
        session.commit()
        detail, _ = BuildSessionService(session, Settings()).create_session(
            project_id,
            BuildSessionCreate(client_session_id=f"workflow-api-{uuid4()}"),
        )
    return detail["id"], ontology_id


def _artifact(ontology_id: str):
    return {
        "client_version_id": "pack-v1",
        "artifact_key": "business-knowledge-pack",
        "artifact_type": "business_knowledge_pack",
        "content_format": "json",
        "content": {"scope": "Dify Workflow"},
        "created_by_role": "business_organizer",
        "workflow_name": "ontology-builder",
        "workflow_version": "r1.1-v1",
        "ontology_id": ontology_id,
    }


def _seed_lineage(r008_client, ontology_id: str) -> str:
    subject = "https://workflow.test/resource/api-known"
    predicate = "https://workflow.test/property/status"
    obj = '"known"'
    graph_iri = "https://workflow.test/graph/api"
    statement_id = statement_id_for_quad(subject, predicate, obj, graph_iri)
    with r008_client["factory"]() as session:
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


def test_rest_idempotency_permissions_export_and_opaque_foreign_isolation(r008_client):
    client = r008_client["client"]
    session_id, ontology_id = _seed_session(r008_client, "p1")
    foreign_session_id, _ = _seed_session(r008_client, "p2")
    path = f"/api/build-sessions/{session_id}/modeling-workflow-artifacts"

    denied = client.post(
        path,
        headers=_bearer(r008_client["p1_read_key"]),
        json=_artifact(ontology_id),
    )
    assert denied.status_code == 403
    created = client.post(
        path,
        headers=_bearer(r008_client["p1_model_key"]),
        json=_artifact(ontology_id),
    )
    assert created.status_code == 201, created.text
    retry = client.post(
        path,
        headers=_bearer(r008_client["p1_model_key"]),
        json=_artifact(ontology_id),
    )
    assert retry.status_code == 200
    assert retry.json()["workflow_artifact_id"] == created.json()["workflow_artifact_id"]

    listed = client.get(path, headers=_bearer(r008_client["p1_read_key"]))
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1
    fetched = client.get(
        f"/api/modeling-workflow-artifacts/{created.json()['workflow_artifact_id']}",
        headers=_bearer(r008_client["p1_read_key"]),
    )
    assert fetched.status_code == 200

    event = client.post(
        f"/api/build-sessions/{session_id}/modeling-execution-events",
        headers=_bearer(r008_client["p1_model_key"]),
        json={
            "client_event_id": "artifact-created",
            "workflow_name": "ontology-builder",
            "workflow_version": "r1.1-v1",
            "phase": "global_scan",
            "event_type": "artifact_created",
            "status": "completed",
            "report_source": "agent_reported",
            "actor_role": "main_agent",
            "summary": "Persisted confirmed business pack",
            "output_workflow_artifact_ids": [created.json()["workflow_artifact_id"]],
        },
    )
    assert event.status_code == 201, event.text
    exported = client.get(
        f"/api/build-sessions/{session_id}/modeling-workflow:export",
        headers=_bearer(r008_client["p1_read_key"]),
    )
    assert exported.status_code == 200
    assert exported.json()["events"][0]["actor"].startswith("key:")
    markdown = client.get(
        f"/api/build-sessions/{session_id}/modeling-workflow:export",
        params={"format": "markdown"},
        headers=_bearer(r008_client["p1_read_key"]),
    )
    assert markdown.status_code == 200 and "artifact_created" in markdown.text

    foreign = client.get(
        f"/api/build-sessions/{foreign_session_id}/modeling-execution-events",
        headers=_bearer(r008_client["p1_read_key"]),
    )
    assert foreign.status_code == 404


def test_rest_secret_rejection_does_not_persist_or_echo(r008_client):
    client = r008_client["client"]
    session_id, ontology_id = _seed_session(r008_client, "p1")
    fake_secret = "sk_model_" + "Z" * 32
    payload = _artifact(ontology_id)
    payload["content"] = {"credential": fake_secret}
    response = client.post(
        f"/api/build-sessions/{session_id}/modeling-workflow-artifacts",
        headers=_bearer(r008_client["p1_model_key"]),
        json=payload,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "secret_in_payload"
    assert fake_secret not in response.text
    listed = client.get(
        f"/api/build-sessions/{session_id}/modeling-workflow-artifacts",
        headers=_bearer(r008_client["p1_read_key"]),
    )
    assert listed.json()["items"] == []


def test_rest_lineage_reference_is_resolved_and_type_mismatch_is_stable(r008_client):
    client = r008_client["client"]
    session_id, ontology_id = _seed_session(r008_client, "p1")
    statement_id = _seed_lineage(r008_client, ontology_id)
    path = f"/api/build-sessions/{session_id}/modeling-execution-events"
    base = {
        "workflow_name": "ontology-builder",
        "workflow_version": "r1.1-v1",
        "phase": "verification",
        "event_type": "verification_completed",
        "status": "completed",
        "report_source": "agent_reported",
        "actor_role": "main_agent",
        "summary": "Checked lineage reference",
    }
    known = client.post(
        path,
        headers=_bearer(r008_client["p1_model_key"]),
        json={
            **base,
            "client_event_id": "api-known-lineage",
            "related_resources": [
                {
                    "resource_type": "lineage",
                    "ontology_id": ontology_id,
                    "target_type": "statement",
                    "target_id": statement_id,
                }
            ],
        },
    )
    assert known.status_code == 201, known.text

    mismatched = client.post(
        path,
        headers=_bearer(r008_client["p1_model_key"]),
        json={
            **base,
            "client_event_id": "api-mismatched-lineage",
            "related_resources": [
                {
                    "resource_type": "lineage",
                    "ontology_id": ontology_id,
                    "target_type": "resource",
                    "target_id": statement_id,
                }
            ],
        },
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["detail"]["code"] == "workflow_reference_conflict"
