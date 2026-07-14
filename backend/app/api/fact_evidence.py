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
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.core.config import Settings
from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository
from app.repositories.models import OntologyModel
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
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Create a fact evidence binding in Postgres.

    ``graph_set_id`` is part of the URL for resource identification but is not
    used directly — the fact is identified by ``fact_id`` (computed from
    s/p/o/g). Callers that want the binding scoped to a particular graph_set
    must include the data graph IRI in ``graph_iri``.
    """
    if payload.assertion_kind in ("inferred", "rule_derived"):
        raise HTTPException(
            status_code=409,
            detail="Cannot bind evidence to inferred or rule-derived facts",
        )
    ns = namespace_from_settings(settings)
    try:
        cmd = compile_bind_fact_evidence(
            payload.model_dump(), ns=ns, settings=settings
        )
    except CommandCompilerError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc

    evidence_service = EvidenceReferenceService(session)
    evidence_reference = None
    ontology = None
    if payload.evidence_reference_id or payload.document_filename:
        ontology = session.get(OntologyModel, payload.ontology_id)
        if ontology is None:
            raise HTTPException(status_code=404, detail="Ontology not found")
        try:
            evidence_service.require_ontology_scope(
                ontology.project_id, ontology.id, graph_set_id
            )
            if payload.evidence_reference_id:
                evidence_reference = evidence_service.get(
                    payload.evidence_reference_id, project_id=ontology.project_id
                )
            else:
                evidence_reference, _created = evidence_service.get_or_create(
                    ontology.project_id,
                    payload.document_filename or "",
                    payload.text,
                    actor=payload.actor,
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
            actor=payload.actor,
        )
    session.commit()
    return _binding_to_dict(binding)


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
        return MissingEvidenceFactsResponse(
            graph_set_id=graph_set_id, count=0, fact_ids=[]
        )
    repo = FactEvidenceBindingRepository(session)
    with_bindings = repo.count_facts_with_bindings(fact_ids)
    missing = [fid for fid in fact_ids if fid not in with_bindings]
    return MissingEvidenceFactsResponse(
        graph_set_id=graph_set_id,
        count=len(missing),
        fact_ids=missing,
    )
