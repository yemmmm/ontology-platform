"""REST surface for lightweight project evidence references."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.repositories.models import EvidenceAssociationModel
from app.services.evidence_reference import (
    EvidenceReferenceError,
    EvidenceReferenceService,
    association_to_dict,
    reference_to_dict,
)


router = APIRouter(tags=["evidence-references"])


class EvidenceReferenceInput(BaseModel):
    document_name: str = Field(min_length=1, max_length=255)
    excerpt: str = Field(min_length=1)


class EvidenceReferenceCreate(EvidenceReferenceInput):
    actor: str | None = None


class EvidenceReferenceResolveRequest(BaseModel):
    evidence_reference_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReferenceInput] = Field(default_factory=list)
    dry_run: bool = True
    actor: str | None = None


class EvidenceAssociationCreate(BaseModel):
    ontology_id: str
    graph_set_id: str | None = None
    target_type: str = Field(min_length=1, max_length=64)
    target_id: str = Field(min_length=1, max_length=512)
    client_item_id: str | None = None
    edit_audit_id: str | None = None
    evidence_reference_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReferenceInput] = Field(default_factory=list)
    actor: str | None = None


def _raise(exc: EvidenceReferenceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _association_count(session: Session, reference_id: str) -> int:
    return int(
        session.scalar(
            select(func.count(EvidenceAssociationModel.id)).where(
                EvidenceAssociationModel.evidence_reference_id == reference_id
            )
        )
        or 0
    )


@router.post(
    "/projects/{project_id}/evidence-references",
    status_code=status.HTTP_201_CREATED,
)
def create_evidence_reference(
    project_id: str,
    payload: EvidenceReferenceCreate,
    session: Session = Depends(get_db_session),
) -> dict:
    service = EvidenceReferenceService(session)
    try:
        row, created = service.get_or_create(
            project_id, payload.document_name, payload.excerpt, actor=payload.actor
        )
        session.commit()
    except EvidenceReferenceError as exc:
        session.rollback()
        _raise(exc)
    return {**reference_to_dict(row, association_count=_association_count(session, row.id)), "created": created}


@router.get("/projects/{project_id}/evidence-references")
def list_evidence_references(
    project_id: str,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_db_session),
) -> dict:
    service = EvidenceReferenceService(session)
    try:
        rows, total = service.list_references(
            project_id, search=search, limit=limit, offset=offset
        )
    except EvidenceReferenceError as exc:
        _raise(exc)
    counts = dict(
        session.execute(
            select(
                EvidenceAssociationModel.evidence_reference_id,
                func.count(EvidenceAssociationModel.id),
            )
            .where(EvidenceAssociationModel.evidence_reference_id.in_([row.id for row in rows]))
            .group_by(EvidenceAssociationModel.evidence_reference_id)
        ).all()
    ) if rows else {}
    return {
        "items": [reference_to_dict(row, association_count=int(counts.get(row.id, 0))) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/evidence-references/{reference_id}")
def get_evidence_reference(
    reference_id: str,
    session: Session = Depends(get_db_session),
) -> dict:
    service = EvidenceReferenceService(session)
    try:
        row = service.get(reference_id)
    except EvidenceReferenceError as exc:
        _raise(exc)
    return reference_to_dict(row, association_count=_association_count(session, row.id))


@router.get("/evidence-references/{reference_id}/associations")
def list_evidence_associations(
    reference_id: str,
    session: Session = Depends(get_db_session),
) -> dict:
    service = EvidenceReferenceService(session)
    try:
        service.get(reference_id)
        rows = service.list_associations(reference_id=reference_id)
    except EvidenceReferenceError as exc:
        _raise(exc)
    return {"items": [association_to_dict(row) for row in rows], "total": len(rows)}


@router.post("/projects/{project_id}/evidence-references:resolve")
def resolve_evidence_references(
    project_id: str,
    payload: EvidenceReferenceResolveRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    service = EvidenceReferenceService(session)
    try:
        resolved = service.resolve_candidates(
            project_id,
            reference_ids=payload.evidence_reference_ids,
            inline_evidence=[item.model_dump() for item in payload.evidence],
            actor=payload.actor,
            persist=not payload.dry_run,
        )
        if payload.dry_run:
            session.rollback()
        else:
            session.commit()
    except EvidenceReferenceError as exc:
        session.rollback()
        _raise(exc)
    items = []
    for row, candidate, created in resolved:
        if row is not None:
            items.append({**reference_to_dict(row), "created": created, "would_create": False})
        else:
            items.append(
                {
                    "id": None,
                    "document_name": candidate.document_name,
                    "excerpt": candidate.excerpt,
                    "excerpt_hash": candidate.excerpt_hash,
                    "idempotency_key": candidate.idempotency_key,
                    "created": False,
                    "would_create": True,
                }
            )
    return {"dry_run": payload.dry_run, "items": items}


@router.post("/projects/{project_id}/evidence-associations", status_code=201)
def create_evidence_associations(
    project_id: str,
    payload: EvidenceAssociationCreate,
    session: Session = Depends(get_db_session),
) -> dict:
    service = EvidenceReferenceService(session)
    try:
        resolved = service.resolve_candidates(
            project_id,
            reference_ids=payload.evidence_reference_ids,
            inline_evidence=[item.model_dump() for item in payload.evidence],
            actor=payload.actor,
            persist=True,
        )
        references = [row for row, _candidate, _created in resolved if row is not None]
        rows = service.associate(
            project_id=project_id,
            ontology_id=payload.ontology_id,
            graph_set_id=payload.graph_set_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            client_item_id=payload.client_item_id,
            edit_audit_id=payload.edit_audit_id,
            references=references,
            actor=payload.actor,
        )
        session.commit()
    except EvidenceReferenceError as exc:
        session.rollback()
        _raise(exc)
    return {"items": [association_to_dict(row) for row in rows], "total": len(rows)}
