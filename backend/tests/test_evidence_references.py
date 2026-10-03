"""R4.0-012 canonical writes remain decoupled from inline evidence."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
from app.security.auth import AuthPrincipal


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


def test_canonical_write_does_not_expose_inline_evidence(
    in_memory_session: Session, monkeypatch
) -> None:
    _seed_scope(in_memory_session)

    class FakeCanonicalWriter:
        def apply_command(self, command_kind, payload, **kwargs):
            assert command_kind == "create_class"
            assert kwargs["commit"] is True
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
        ),
        principal=AuthPrincipal(
            subject_type="api_key",
            subject_id="direct-test",
            actor="key:direct-test",
            scopes=frozenset({"admin"}),
            project_id=None,
            auth_method="bearer",
        ),
        session=in_memory_session,
        rdf_store=object(),
        settings=Settings(),
    )
    assert response.applied is True
    assert not hasattr(response, "evidence_associations")
    assert in_memory_session.scalar(select(func.count(EvidenceReferenceModel.id))) == 0
    assert in_memory_session.scalar(select(func.count(EvidenceAssociationModel.id))) == 0
