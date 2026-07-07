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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_settings
from app.core.config import Settings
from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository
from app.services.semantic_command_compiler import (
    CommandCompilerError,
    compile_bind_fact_evidence,
    compile_unbind_fact_evidence,
)
from app.services.semantic_export import namespace_from_settings

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
    chunk_id: str | None = None
    evidence_artifact_id: str | None = None
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
    ns = namespace_from_settings(settings)
    try:
        cmd = compile_bind_fact_evidence(
            payload.model_dump(), ns=ns, settings=settings
        )
    except CommandCompilerError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc

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
        document_filename=cmd.metadata.get("document_filename"),
        sequence=cmd.metadata.get("sequence"),
        char_start=cmd.metadata.get("char_start"),
        char_end=cmd.metadata.get("char_end"),
        actor=cmd.metadata.get("actor"),
        reason=cmd.metadata.get("reason"),
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
