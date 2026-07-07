"""Stage 4 §5.1 evidence-artifact REST surface.

Minimal read-only CRUD over the existing ``evidence_artifacts`` and
``evidence_chunks`` Postgres tables. This is the Keep side of the
``split`` evidence strategy: file/chunk metadata lives in Postgres and is
exposed here; the RDF ``prov:wasDerivedFrom`` binding that ties a fact to a
chunk is read through the ``fact-audit-queue`` read model (Stage 4 §4.4).

Routes:

* ``GET /api/projects/{project_id}/evidence-artifacts`` — paged artifact list
  (default 50).
* ``GET /api/evidence-artifacts/{artifact_id}`` — single artifact metadata,
  ``content`` binary deliberately omitted.
* ``GET /api/evidence-artifacts/{artifact_id}/chunks`` — chunks ordered by
  ``sequence``.
* ``GET /api/chunks/{chunk_id}`` — single chunk with a 500-char text preview.

No write paths; no RDF store involvement.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.repositories.models import EvidenceArtifactModel, EvidenceChunkModel

router = APIRouter(tags=["evidence"])

#: Cap on the text preview returned by ``GET /api/chunks/{id}`` (spec §5.1).
CHUNK_TEXT_PREVIEW_LIMIT = 500

#: Default page size for the artifacts listing (spec §5.1).
DEFAULT_ARTIFACT_PAGE_SIZE = 50


def _artifact_to_metadata(row: EvidenceArtifactModel) -> dict[str, Any]:
    """Project an ``EvidenceArtifactModel`` row into the JSON metadata shape.

    The ``content`` binary column is deliberately excluded — the route
    exists for browsing file/chunk metadata, not for streaming bytes."""
    return {
        "id": row.id,
        "project_id": row.project_id,
        "filename": row.filename,
        "media_type": row.media_type,
        "size_bytes": row.size_bytes,
        "content_hash": row.content_hash,
        "parse_status": row.parse_status,
        "parse_error": row.parse_error,
        "parser_version": row.parser_version,
        "parse_count": row.parse_count,
        "parse_revision": row.parse_revision,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _chunk_to_dict(row: EvidenceChunkModel, *, include_preview: bool) -> dict[str, Any]:
    """Project an ``EvidenceChunkModel`` row into the JSON chunk shape.

    ``include_preview`` controls whether the 500-char ``text_preview`` is
    attached alongside the full ``text`` field. The single-chunk route
    includes both so the drawer can render highlights without a second
    round-trip; the chunks listing omits the preview to keep the payload
    small."""
    out: dict[str, Any] = {
        "id": row.id,
        "document_id": row.document_id,
        "sequence": row.sequence,
        "parse_revision": row.parse_revision,
        "page_number": row.page_number,
        "char_start": row.char_start,
        "char_end": row.char_end,
        "content_hash": row.content_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_preview:
        text = row.text or ""
        out["text"] = text
        out["text_preview"] = text[:CHUNK_TEXT_PREVIEW_LIMIT]
    else:
        out["text"] = row.text
    return out


@router.get("/projects/{project_id}/evidence-artifacts")
def list_project_evidence_artifacts(
    project_id: str,
    session: Session = Depends(get_db_session),
    limit: int = Query(DEFAULT_ARTIFACT_PAGE_SIZE, ge=0, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List evidence artifacts for ``project_id`` (paged)."""
    base = (
        select(EvidenceArtifactModel)
        .where(EvidenceArtifactModel.project_id == project_id)
        .order_by(EvidenceArtifactModel.created_at.desc())
    )
    rows = list(
        session.scalars(base.offset(offset).limit(limit))
    )
    count = session.scalar(
        select(func.count(EvidenceArtifactModel.id)).where(
            EvidenceArtifactModel.project_id == project_id
        )
    )
    return {
        "project_id": project_id,
        "items": [_artifact_to_metadata(r) for r in rows],
        "total": int(count or 0),
        "limit": limit,
        "offset": offset,
    }


@router.get("/evidence-artifacts/{artifact_id}")
def get_evidence_artifact(
    artifact_id: str, session: Session = Depends(get_db_session)
) -> dict[str, Any]:
    row = session.scalar(
        select(EvidenceArtifactModel).where(EvidenceArtifactModel.id == artifact_id)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"evidence artifact {artifact_id!r} not found",
        )
    return _artifact_to_metadata(row)


@router.get("/evidence-artifacts/{artifact_id}/chunks")
def list_evidence_artifact_chunks(
    artifact_id: str, session: Session = Depends(get_db_session)
) -> dict[str, Any]:
    # Verify the parent artifact exists; 404 otherwise.
    parent = session.scalar(
        select(EvidenceArtifactModel).where(EvidenceArtifactModel.id == artifact_id)
    )
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"evidence artifact {artifact_id!r} not found",
        )
    rows = list(
        session.scalars(
            select(EvidenceChunkModel)
            .where(EvidenceChunkModel.document_id == artifact_id)
            .order_by(EvidenceChunkModel.sequence.asc())
        )
    )
    total = session.scalar(
        select(func.count(EvidenceChunkModel.id)).where(
            EvidenceChunkModel.document_id == artifact_id
        )
    )
    return {
        "artifact_id": artifact_id,
        "items": [_chunk_to_dict(r, include_preview=False) for r in rows],
        "total": int(total or 0),
    }


@router.get("/chunks/{chunk_id}")
def get_evidence_chunk(
    chunk_id: str, session: Session = Depends(get_db_session)
) -> dict[str, Any]:
    row = session.scalar(
        select(EvidenceChunkModel).where(EvidenceChunkModel.id == chunk_id)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"evidence chunk {chunk_id!r} not found",
        )
    return _chunk_to_dict(row, include_preview=True)
