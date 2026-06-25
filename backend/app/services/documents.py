from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.models import (
    EvidenceModel,
    ProjectModel,
    ProposalModel,
    EvidenceChunkModel,
    EvidenceArtifactModel,
)

PARSER_VERSION = "v1"
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {
    "application/pdf": "pdf",
    "text/markdown": "text",
    "text/plain": "text",
}
ALLOWED_SUFFIXES = {".pdf": "pdf", ".md": "text", ".markdown": "text", ".txt": "text"}


def _id() -> str:
    return str(uuid4())


def _kind(filename: str, media_type: str) -> str:
    normalized = media_type.split(";", 1)[0].strip().lower()
    if normalized in ALLOWED_MEDIA_TYPES:
        return ALLOWED_MEDIA_TYPES[normalized]
    lowered = filename.lower()
    for suffix, kind in ALLOWED_SUFFIXES.items():
        if lowered.endswith(suffix):
            return kind
    raise HTTPException(status_code=415, detail="Only PDF, Markdown and plain text are supported")


def _pages(content: bytes, kind: str) -> list[tuple[int | None, str]]:
    if kind == "pdf":
        try:
            return [(index, page.extract_text() or "") for index, page in enumerate(PdfReader(BytesIO(content)).pages, 1)]
        except Exception as exc:
            raise ValueError(f"PDF parsing failed: {exc}") from exc
    try:
        return [(None, content.decode("utf-8-sig"))]
    except UnicodeDecodeError as exc:
        raise ValueError("Text documents must use UTF-8 encoding") from exc


def chunk_pages(pages: list[tuple[int | None, str]]) -> list[dict[str, Any]]:
    """Create stable, source-relative chunks; document text remains inert extraction data."""
    chunks: list[dict[str, Any]] = []
    document_offset = 0
    sequence = 0
    for page_number, text in pages:
        start = 0
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            value = text[start:end]
            if value.strip():
                chunks.append(
                    {
                        "sequence": sequence,
                        "page_number": page_number,
                        "char_start": document_offset + start,
                        "char_end": document_offset + end,
                        "text": value,
                        "content_hash": sha256(value.encode()).hexdigest(),
                    }
                )
                sequence += 1
            if end == len(text):
                break
            start = end - CHUNK_OVERLAP
        document_offset += len(text)
    return chunks


def _artifact_result(session: Session, artifact: EvidenceArtifactModel, reused: bool = False) -> dict[str, Any]:
    chunk_count = session.scalar(
        select(func.count()).select_from(EvidenceChunkModel).where(EvidenceChunkModel.document_id == artifact.id)
    )
    return {
        **{column.name: getattr(artifact, column.name) for column in artifact.__table__.columns if column.name != "content"},
        "artifact_id": artifact.id,
        "reused": reused,
        "chunk_count": int(chunk_count or 0),
    }


def ingest_artifact(
    session: Session, project_id: str, filename: str, media_type: str, content: bytes
) -> dict[str, Any]:
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded document is empty")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Evidence artifacts are limited to 25 MiB")
    if session.get(ProjectModel, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    kind = _kind(filename, media_type)
    digest = sha256(content).hexdigest()
    existing = session.scalar(
        select(EvidenceArtifactModel).where(
            EvidenceArtifactModel.project_id == project_id,
            EvidenceArtifactModel.content_hash == digest,
        )
    )
    if existing is not None:
        return _artifact_result(session, existing, reused=True)
    artifact = EvidenceArtifactModel(
        id=_id(), project_id=project_id, filename=filename, media_type=media_type,
        size_bytes=len(content), content_hash=digest, content=content,
        parse_status="parsing", parser_version=PARSER_VERSION, parse_count=0, parse_revision=1,
    )
    session.add(artifact)
    try:
        session.flush()
        parsed = chunk_pages(_pages(content, kind))
        for item in parsed:
            session.add(
                EvidenceChunkModel(
                    id=_id(), document_id=artifact.id, parse_revision=artifact.parse_revision, **item
                )
            )
        artifact.parse_status = "parsed"
        artifact.parse_count = 1
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(EvidenceArtifactModel).where(
                EvidenceArtifactModel.project_id == project_id,
                EvidenceArtifactModel.content_hash == digest,
            )
        )
        if existing is None:
            raise
        return _artifact_result(session, existing, reused=True)
    except Exception as exc:
        session.rollback()
        artifact = EvidenceArtifactModel(
            id=_id(), project_id=project_id, filename=filename, media_type=media_type,
            size_bytes=len(content), content_hash=digest, content=content,
            parse_status="failed", parse_error=str(exc), parser_version=PARSER_VERSION,
            parse_count=1, parse_revision=1,
        )
        session.add(artifact)
        session.commit()
    session.refresh(artifact)
    return _artifact_result(session, artifact)


def reparse_artifact(session: Session, artifact_id: str, force: bool = False) -> dict[str, Any]:
    artifact = session.get(EvidenceArtifactModel, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Evidence artifact not found")
    if not force and artifact.parse_status == "parsed" and artifact.parser_version == PARSER_VERSION:
        return _artifact_result(session, artifact, reused=True)
    kind = _kind(artifact.filename, artifact.media_type)
    try:
        parsed = chunk_pages(_pages(artifact.content, kind))
        artifact.parse_revision += 1
        for item in parsed:
            session.add(
                EvidenceChunkModel(
                    id=_id(), document_id=artifact.id,
                    parse_revision=artifact.parse_revision, **item,
                )
            )
        artifact.parse_status = "parsed"
        artifact.parse_error = None
        artifact.parser_version = PARSER_VERSION
        artifact.parse_count += 1
        session.commit()
    except Exception as exc:
        session.rollback()
        artifact.parse_status = "failed"
        artifact.parse_error = str(exc)
        artifact.parse_count += 1
        session.commit()
    session.refresh(artifact)
    return _artifact_result(session, artifact)


def list_artifacts(session: Session, project_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(EvidenceArtifactModel).where(EvidenceArtifactModel.project_id == project_id).order_by(EvidenceArtifactModel.created_at.desc())
    )
    return [_artifact_result(session, row) for row in rows]


def get_artifact(session: Session, artifact_id: str) -> dict[str, Any]:
    artifact = session.get(EvidenceArtifactModel, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Evidence artifact not found")
    return _artifact_result(session, artifact)


def list_chunks(session: Session, artifact_id: str) -> list[EvidenceChunkModel]:
    if session.get(EvidenceArtifactModel, artifact_id) is None:
        raise HTTPException(status_code=404, detail="Evidence artifact not found")
    artifact = session.get(EvidenceArtifactModel, artifact_id)
    return list(
        session.scalars(
            select(EvidenceChunkModel)
            .where(
                EvidenceChunkModel.document_id == artifact_id,
                EvidenceChunkModel.parse_revision == artifact.parse_revision,
            )
            .order_by(EvidenceChunkModel.sequence)
        )
    )


def list_artifact_proposals(session: Session, artifact_id: str) -> list[str]:
    return list(session.scalars(select(EvidenceModel.proposal_id).where(EvidenceModel.document_id == artifact_id).distinct()))


def ingest_document(session: Session, project_id: str, filename: str, media_type: str, content: bytes) -> dict[str, Any]:
    return ingest_artifact(session, project_id, filename, media_type, content)


def reparse_document(session: Session, document_id: str, force: bool = False) -> dict[str, Any]:
    return reparse_artifact(session, document_id, force)


def list_documents(session: Session, project_id: str) -> list[dict[str, Any]]:
    return list_artifacts(session, project_id)


def get_document(session: Session, document_id: str) -> dict[str, Any]:
    return get_artifact(session, document_id)


def list_document_proposals(session: Session, document_id: str) -> list[str]:
    return list_artifact_proposals(session, document_id)


def list_item_sources(session: Session, proposal_id: str, item_key: str) -> list[EvidenceModel]:
    proposal = session.get(ProposalModel, proposal_id)
    if proposal is None or not any(item.get("key") == item_key for item in proposal.payload.get("items", [])):
        raise HTTPException(status_code=404, detail="Proposal item not found")
    item = next(item for item in proposal.payload["items"] if item.get("key") == item_key)
    evidence_ids = item.get("evidence_ids", [])
    return list(session.scalars(select(EvidenceModel).where(EvidenceModel.id.in_(evidence_ids)))) if evidence_ids else []
