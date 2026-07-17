"""REST endpoints for fact-level evidence bindings.

Replaces the legacy prov:wasDerivedFrom + chunk literal pattern. All evidence
data lives in Postgres; RDF triple store is not touched.

These endpoints compile a structured command (re-using the same compiler used
by the canonical-write pipeline) and apply it directly to
``FactEvidenceBindingRepository``. They bypass the RDF delta application in
``CanonicalSemanticWriteService`` because the new compilers emit empty deltas
and write to Postgres instead.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.core.config import Settings
from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository
from app.repositories.models import (
    OntologyModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)
from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic_command_compiler import (
    CommandCompilerError,
    compile_bind_fact_evidence,
)
from app.services.evidence_reference import EvidenceReferenceError, EvidenceReferenceService
from app.services.semantic_export import namespace_from_settings
from app.services.semantic_read_model import SemanticReadModelService
from app.services.semantic_read_scope import SemanticReadScopeResolver
from app.services.semantic_shape_endpoint_service import (
    SemanticShapeEndpointService,
)
from app.services.semantic_visibility import SemanticVisibilityPolicy
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency

router = APIRouter(tags=["semantic"])


class BindFactEvidenceRequest(BaseModel):
    ontology_id: str
    subject_iri: str
    predicate_iri: str
    object_value: str
    object_is_iri: bool = False
    object_datatype: str | None = None
    object_lang: str | None = None
    graph_iri: str | None = None
    fact_id: str | None = None
    assertion_kind: str | None = None
    chunk_id: str | None = None
    evidence_artifact_id: str | None = None
    evidence_reference_id: str | None = None
    document_filename: str | None = None
    sequence: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    text: str
    actor: str | None = None
    reason: str | None = None


def _binding_to_dict(binding) -> dict:
    return {
        "id": binding.id,
        "fact_id": binding.fact_id,
        "subject_iri": binding.subject_iri,
        "predicate_iri": binding.predicate_iri,
        "object_value": binding.object_value,
        "graph_iri": binding.graph_iri,
        "chunk_id": binding.chunk_id,
        "evidence_artifact_id": binding.evidence_artifact_id,
        "evidence_reference_id": binding.evidence_reference_id,
        "document_filename": binding.document_filename,
        "sequence": binding.sequence,
        "char_start": binding.char_start,
        "char_end": binding.char_end,
        "text": binding.text,
        "actor": binding.actor,
        "reason": binding.reason,
        "created_at": binding.created_at.isoformat() if binding.created_at else None,
    }


@router.post("/semantic/graph-sets/{graph_set_id}/fact-evidence")
def create_fact_evidence(
    graph_set_id: str,
    payload: BindFactEvidenceRequest,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Create evidence for an asserted fact in an Ontology-owned data graph."""
    if payload.assertion_kind not in (None, "asserted", "missing_evidence"):
        raise HTTPException(
            status_code=409,
            detail="Cannot bind evidence to a derived fact",
        )
    ontology, asserted_graph_iri = _require_asserted_fact_target(
        session=session,
        ontology_id=payload.ontology_id,
        graph_set_id=graph_set_id,
        graph_iri=payload.graph_iri,
    )
    compile_payload = payload.model_dump()
    compile_payload["actor"] = principal.actor
    compile_payload["graph_iri"] = asserted_graph_iri
    compile_payload["assertion_kind"] = "asserted"
    ns = namespace_from_settings(settings)
    try:
        cmd = compile_bind_fact_evidence(compile_payload, ns=ns, settings=settings)
    except CommandCompilerError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc

    evidence_service = EvidenceReferenceService(session)
    evidence_reference = None
    if payload.evidence_reference_id or payload.document_filename:
        try:
            evidence_service.require_ontology_scope(ontology.project_id, ontology.id, graph_set_id)
            if payload.evidence_reference_id:
                evidence_reference = evidence_service.get(
                    payload.evidence_reference_id, project_id=ontology.project_id
                )
            else:
                evidence_reference, _created = evidence_service.get_or_create(
                    ontology.project_id,
                    payload.document_filename or "",
                    payload.text,
                    actor=principal.actor,
                )
        except EvidenceReferenceError as exc:
            session.rollback()
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    repo = FactEvidenceBindingRepository(session)
    binding = repo.create(
        fact_id=cmd.metadata["fact_id"],
        subject_iri=cmd.metadata["subject_iri"],
        predicate_iri=cmd.metadata["predicate_iri"],
        object_value=cmd.metadata["object_value"],
        graph_iri=cmd.metadata["graph_iri"],
        text=cmd.metadata["text"],
        chunk_id=cmd.metadata.get("chunk_id"),
        evidence_artifact_id=cmd.metadata.get("evidence_artifact_id"),
        evidence_reference_id=evidence_reference.id if evidence_reference else None,
        document_filename=cmd.metadata.get("document_filename"),
        sequence=cmd.metadata.get("sequence"),
        char_start=cmd.metadata.get("char_start"),
        char_end=cmd.metadata.get("char_end"),
        actor=cmd.metadata.get("actor"),
        reason=cmd.metadata.get("reason"),
    )
    if evidence_reference is not None and ontology is not None:
        evidence_service.associate(
            project_id=ontology.project_id,
            ontology_id=ontology.id,
            graph_set_id=graph_set_id,
            target_type="fact",
            target_id=cmd.metadata["fact_id"],
            references=[evidence_reference],
            actor=principal.actor,
        )
    session.commit()
    return _binding_to_dict(binding)


def _require_asserted_fact_target(
    *,
    session: Session,
    ontology_id: str,
    graph_set_id: str,
    graph_iri: str | None,
) -> tuple[OntologyModel, str]:
    ontology = session.get(OntologyModel, ontology_id)
    if ontology is None:
        raise HTTPException(status_code=404, detail="Ontology not found")
    graph_set = session.get(SemanticGraphSetModel, graph_set_id)
    if (
        graph_set is None
        or graph_set.scope_type != "ontology"
        or graph_set.scope_id != ontology.id
        or graph_set.status != "active"
    ):
        raise HTTPException(
            status_code=409,
            detail="Graph Set does not belong to the target Ontology",
        )
    asserted_graphs = list(
        session.scalars(
            select(SemanticGraphSetMemberModel.graph_iri).where(
                SemanticGraphSetMemberModel.graph_set_id == graph_set.id,
                SemanticGraphSetMemberModel.role == "asserted_data",
            )
        )
    )
    if not asserted_graphs:
        raise HTTPException(
            status_code=409,
            detail="Graph Set has no asserted_data member",
        )
    selected_graph = graph_iri or asserted_graphs[0]
    if selected_graph not in asserted_graphs:
        raise HTTPException(
            status_code=409,
            detail="Fact evidence target must be an asserted_data member of the Graph Set",
        )
    return ontology, selected_graph


@router.delete(
    "/semantic/graph-sets/{graph_set_id}/fact-evidence/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_fact_evidence(
    graph_set_id: str,
    binding_id: str,
    session: Session = Depends(get_db_session),
) -> None:
    """Delete a fact evidence binding by id."""
    repo = FactEvidenceBindingRepository(session)
    if not repo.delete(binding_id):
        raise HTTPException(status_code=404, detail="binding not found")
    session.commit()
    return None


def _build_read_model_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
) -> SemanticReadModelService:
    """Construct a SemanticReadModelService wired to the same dependencies
    used by the read-model endpoint in ``app.api.semantic``."""
    visibility = SemanticVisibilityPolicy(
        graph_labels=getattr(settings, "semantic_graph_visibility_labels", {}) or {}
    )
    return SemanticReadModelService(
        rdf_store=rdf_store,
        scope_resolver=SemanticReadScopeResolver(session),
        visibility_policy=visibility,
        shape_endpoint=SemanticShapeEndpointService(session, rdf_store, settings),
        session=session,
    )


class MissingEvidenceFactsResponse(BaseModel):
    graph_set_id: str
    count: int
    fact_ids: list[str]


@router.get(
    "/semantic/graph-sets/{graph_set_id}/missing-evidence-facts",
    response_model=MissingEvidenceFactsResponse,
)
def list_missing_evidence_facts(
    graph_set_id: str,
    limit: int = 5000,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> MissingEvidenceFactsResponse:
    """Return fact_ids in this graph_set that have zero evidence bindings.

    Enumerates all asserted ``(s, p, o, g)`` tuples from the asserted_data
    member graph(s), computes the canonical ``fact_id`` for each, then
    subtracts the subset that appears in ``fact_evidence_bindings``.
    """
    service = _build_read_model_service(session, rdf_store, settings)
    scope = service.scope_resolver.resolve(
        graph_set_id=graph_set_id,
        include="asserted",
        allow_stale_derived=True,
    )
    fact_ids = service._list_asserted_fact_ids(scope, limit=limit)
    if not fact_ids:
        return MissingEvidenceFactsResponse(graph_set_id=graph_set_id, count=0, fact_ids=[])
    repo = FactEvidenceBindingRepository(session)
    with_bindings = repo.count_facts_with_bindings(fact_ids)
    missing = [fid for fid in fact_ids if fid not in with_bindings]
    return MissingEvidenceFactsResponse(
        graph_set_id=graph_set_id,
        count=len(missing),
        fact_ids=missing,
    )
