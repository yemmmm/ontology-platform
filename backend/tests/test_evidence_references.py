"""R-002 lightweight evidence reference REST and service coverage."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.evidence_references import router
from app.repositories.models import (
    EvidenceAssociationModel,
    EvidenceReferenceModel,
    OntologyModel,
    ProjectModel,
    SemanticGraphSetModel,
    SemanticEditAuditModel,
)
from app.api.schemas import SemanticCanonicalProductWriteRequest
from app.api.semantic import compile_and_apply_product_command
from app.core.config import Settings


PROJECT_ID = "project-evidence"
OTHER_PROJECT_ID = "project-other"
ONTOLOGY_ID = "ontology-evidence"
GRAPH_SET_ID = "graph-set-evidence"


def _seed_scope(session: Session) -> None:
    session.add_all(
        [
            ProjectModel(
                id=PROJECT_ID,
                name="Evidence project",
                normalized_label="evidence project",
            ),
            ProjectModel(
                id=OTHER_PROJECT_ID,
                name="Other project",
                normalized_label="other project",
            ),
            OntologyModel(
                id=ONTOLOGY_ID,
                project_id=PROJECT_ID,
                name="Evidence ontology",
            ),
            SemanticGraphSetModel(
                id=GRAPH_SET_ID,
                name="Default",
                scope_type="ontology",
                scope_id=ONTOLOGY_ID,
                status="active",
                is_default=True,
                source_signature="test",
            ),
        ]
    )
    session.commit()


def _client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def override_session():
        yield session

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app)


def test_create_normalizes_and_idempotently_reuses_reference(in_memory_session: Session) -> None:
    _seed_scope(in_memory_session)
    client = _client(in_memory_session)
    payload = {
        "document_name": "  API Guide.md  ",
        "excerpt": " first line\r\nsecond line ",
        "actor": "agent:test",
    }

    first = client.post(f"/api/projects/{PROJECT_ID}/evidence-references", json=payload)
    second = client.post(f"/api/projects/{PROJECT_ID}/evidence-references", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["document_name"] == "API Guide.md"
    assert first.json()["excerpt"] == "first line\nsecond line"
    count = in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id)))
    assert count == 1


def test_same_excerpt_under_different_document_names_is_not_merged(
    in_memory_session: Session,
) -> None:
    _seed_scope(in_memory_session)
    client = _client(in_memory_session)
    for document_name in ("Guide A", "Guide B"):
        response = client.post(
            f"/api/projects/{PROJECT_ID}/evidence-references",
            json={"document_name": document_name, "excerpt": "same excerpt"},
        )
        assert response.status_code == 201
        assert response.json()["created"] is True
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 2


def test_blank_normalized_values_are_rejected(in_memory_session: Session) -> None:
    _seed_scope(in_memory_session)
    client = _client(in_memory_session)
    response = client.post(
        f"/api/projects/{PROJECT_ID}/evidence-references",
        json={"document_name": "  ", "excerpt": "\r\n"},
    )
    assert response.status_code == 422
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 0


def test_resolve_dry_run_reports_candidate_without_persisting(in_memory_session: Session) -> None:
    _seed_scope(in_memory_session)
    client = _client(in_memory_session)
    response = client.post(
        f"/api/projects/{PROJECT_ID}/evidence-references:resolve",
        json={
            "dry_run": True,
            "evidence": [{"document_name": "Guide", "excerpt": "quoted text"}],
        },
    )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["would_create"] is True
    assert item["id"] is None
    assert len(item["excerpt_hash"]) == 64
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 0


def test_list_searches_document_name_and_excerpt(in_memory_session: Session) -> None:
    _seed_scope(in_memory_session)
    client = _client(in_memory_session)
    for name, excerpt in (("API Guide", "publish workflow"), ("Admin", "audit logs")):
        client.post(
            f"/api/projects/{PROJECT_ID}/evidence-references",
            json={"document_name": name, "excerpt": excerpt},
        )
    response = client.get(
        f"/api/projects/{PROJECT_ID}/evidence-references", params={"search": "publish"}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["document_name"] == "API Guide"


def test_association_reuses_reference_and_is_idempotent(in_memory_session: Session) -> None:
    _seed_scope(in_memory_session)
    client = _client(in_memory_session)
    payload = {
        "ontology_id": ONTOLOGY_ID,
        "graph_set_id": GRAPH_SET_ID,
        "target_type": "create_class",
        "target_id": "https://example.test/Workflow",
        "client_item_id": "item-1",
        "evidence": [{"document_name": "API Guide", "excerpt": "A workflow can be published."}],
    }
    first = client.post(f"/api/projects/{PROJECT_ID}/evidence-associations", json=payload)
    second = client.post(f"/api/projects/{PROJECT_ID}/evidence-associations", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["items"][0]["id"] == second.json()["items"][0]["id"]
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 1
    assert in_memory_session.scalar(select(func.count(EvidenceAssociationModel.id))) == 1
    target_query = client.get(
        f"/api/projects/{PROJECT_ID}/evidence-associations",
        params={
            "ontology_id": ONTOLOGY_ID,
            "target_type": "create_class",
            "target_id": "https://example.test/Workflow",
        },
    )
    assert target_query.status_code == 200
    assert target_query.json()["total"] == 1
    assert target_query.json()["items"][0]["evidence_reference"]["document_name"] == "API Guide"


def test_cross_project_reference_is_hidden_and_atomic(in_memory_session: Session) -> None:
    _seed_scope(in_memory_session)
    client = _client(in_memory_session)
    foreign = client.post(
        f"/api/projects/{OTHER_PROJECT_ID}/evidence-references",
        json={"document_name": "Foreign", "excerpt": "secret"},
    ).json()
    response = client.post(
        f"/api/projects/{PROJECT_ID}/evidence-associations",
        json={
            "ontology_id": ONTOLOGY_ID,
            "target_type": "create_entity",
            "target_id": "https://example.test/entity/1",
            "evidence_reference_ids": [foreign["id"]],
            "evidence": [{"document_name": "Local", "excerpt": "must roll back"}],
        },
    )
    assert response.status_code == 404
    assert in_memory_session.scalar(
        select(func.count(EvidenceReferenceModel.id)).where(
            EvidenceReferenceModel.project_id == PROJECT_ID
        )
    ) == 0
    assert in_memory_session.scalar(select(func.count(EvidenceAssociationModel.id))) == 0


def test_association_batch_dry_run_atomic_failure_and_partial_apply(
    in_memory_session: Session,
) -> None:
    _seed_scope(in_memory_session)
    client = _client(in_memory_session)
    valid_item = {
        "client_item_id": "valid-item",
        "ontology_id": ONTOLOGY_ID,
        "graph_set_id": GRAPH_SET_ID,
        "target_type": "create_entity",
        "target_id": "https://example.test/entity/1",
        "evidence": [{"document_name": "Guide", "excerpt": "An entity exists."}],
    }
    invalid_item = {
        "client_item_id": "invalid-item",
        "ontology_id": ONTOLOGY_ID,
        "graph_set_id": GRAPH_SET_ID,
        "target_type": "create_entity",
        "target_id": "https://example.test/entity/2",
        "evidence": [{"document_name": "  ", "excerpt": "invalid source"}],
    }

    dry_run = client.post(
        f"/api/projects/{PROJECT_ID}/evidence-associations:batch",
        json={"dry_run": True, "items": [valid_item]},
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["items"][0]["evidence"][0]["would_create"] is True
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 0

    atomic = client.post(
        f"/api/projects/{PROJECT_ID}/evidence-associations:batch",
        json={"items": [valid_item, invalid_item]},
    )
    assert atomic.status_code == 422
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 0
    assert in_memory_session.scalar(select(func.count(EvidenceAssociationModel.id))) == 0

    partial = client.post(
        f"/api/projects/{PROJECT_ID}/evidence-associations:batch",
        json={"allow_partial": True, "items": [valid_item, invalid_item]},
    )
    assert partial.status_code == 200
    assert [item["status"] for item in partial.json()["items"]] == ["applied", "failed"]
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 1
    assert in_memory_session.scalar(select(func.count(EvidenceAssociationModel.id))) == 1


def test_canonical_write_atomically_persists_inline_evidence(
    in_memory_session: Session, monkeypatch
) -> None:
    _seed_scope(in_memory_session)

    class FakeCanonicalWriter:
        def apply_command(self, command_kind, payload, **kwargs):
            assert command_kind == "create_class"
            assert kwargs["commit"] is False
            in_memory_session.add(
                SemanticEditAuditModel(
                    id="audit-evidence",
                    actor="agent:test",
                    reason="create_class",
                    input_format="canonical-write",
                    target_graph_iri="http://example.test/ontology",
                    affected_graph_iris=["http://example.test/ontology"],
                    graph_delta={},
                    warning_state={},
                    applied=True,
                )
            )
            in_memory_session.flush()
            return {
                "audit_id": "audit-evidence",
                "applied": True,
                "command_kind": command_kind,
                "affected_graph_iris": ["http://example.test/ontology"],
                "delta": {},
                "warnings": [],
                "validation": None,
                "graph_revisions": {},
                "stale_derived_pointers": [],
            }

    monkeypatch.setattr(
        "app.api.semantic._canonical_write_service",
        lambda _session, _rdf_store, _settings: FakeCanonicalWriter(),
    )
    response = compile_and_apply_product_command(
        SemanticCanonicalProductWriteRequest(
            command_kind="create_class",
            graph_set_id=GRAPH_SET_ID,
            payload={"class_iri": "https://example.test/Workflow", "label": "Workflow"},
            actor="agent:test",
            client_item_id="item-class-1",
            evidence=[
                {
                    "document_name": "API Guide",
                    "excerpt": "A workflow can be published.",
                }
            ],
        ),
        session=in_memory_session,
        rdf_store=object(),
        settings=Settings(),
    )
    assert response.applied is True
    assert len(response.evidence_associations) == 1
    association = response.evidence_associations[0]
    assert association["target_id"] == "https://example.test/Workflow"
    assert association["edit_audit_id"] == "audit-evidence"
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 1
    assert in_memory_session.scalar(select(func.count(EvidenceAssociationModel.id))) == 1
