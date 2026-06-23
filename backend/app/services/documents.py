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
    SourceChunkModel,
    SourceDocumentModel,
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


def _document_result(session: Session, document: SourceDocumentModel, reused: bool = False) -> dict[str, Any]:
    chunk_count = session.scalar(
        select(func.count()).select_from(SourceChunkModel).where(SourceChunkModel.document_id == document.id)
    )
    return {
        **{column.name: getattr(document, column.name) for column in document.__table__.columns if column.name != "content"},
        "reused": reused,
        "chunk_count": int(chunk_count or 0),
    }


def ingest_document(
    session: Session, project_id: str, filename: str, media_type: str, content: bytes
) -> dict[str, Any]:
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded document is empty")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Source documents are limited to 25 MiB")
    if session.get(ProjectModel, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    kind = _kind(filename, media_type)
    digest = sha256(content).hexdigest()
    existing = session.scalar(
        select(SourceDocumentModel).where(
            SourceDocumentModel.project_id == project_id,
            SourceDocumentModel.content_hash == digest,
        )
    )
    if existing is not None:
        return _document_result(session, existing, reused=True)
    document = SourceDocumentModel(
        id=_id(), project_id=project_id, filename=filename, media_type=media_type,
        size_bytes=len(content), content_hash=digest, content=content,
        parse_status="parsing", parser_version=PARSER_VERSION, parse_count=0, parse_revision=1,
    )
    session.add(document)
    try:
        session.flush()
        parsed = chunk_pages(_pages(content, kind))
        for item in parsed:
            session.add(
                SourceChunkModel(
                    id=_id(), document_id=document.id, parse_revision=document.parse_revision, **item
                )
            )
        document.parse_status = "parsed"
        document.parse_count = 1
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(SourceDocumentModel).where(
                SourceDocumentModel.project_id == project_id,
                SourceDocumentModel.content_hash == digest,
            )
        )
        if existing is None:
            raise
        return _document_result(session, existing, reused=True)
    except Exception as exc:
        session.rollback()
        document = SourceDocumentModel(
            id=_id(), project_id=project_id, filename=filename, media_type=media_type,
            size_bytes=len(content), content_hash=digest, content=content,
            parse_status="failed", parse_error=str(exc), parser_version=PARSER_VERSION,
            parse_count=1, parse_revision=1,
        )
        session.add(document)
        session.commit()
    session.refresh(document)
    return _document_result(session, document)


def reparse_document(session: Session, document_id: str, force: bool = False) -> dict[str, Any]:
    document = session.get(SourceDocumentModel, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    if not force and document.parse_status == "parsed" and document.parser_version == PARSER_VERSION:
        return _document_result(session, document, reused=True)
    kind = _kind(document.filename, document.media_type)
    try:
        parsed = chunk_pages(_pages(document.content, kind))
        document.parse_revision += 1
        for item in parsed:
            session.add(
                SourceChunkModel(
                    id=_id(), document_id=document.id,
                    parse_revision=document.parse_revision, **item,
                )
            )
        document.parse_status = "parsed"
        document.parse_error = None
        document.parser_version = PARSER_VERSION
        document.parse_count += 1
        session.commit()
    except Exception as exc:
        session.rollback()
        document.parse_status = "failed"
        document.parse_error = str(exc)
        document.parse_count += 1
        session.commit()
    session.refresh(document)
    return _document_result(session, document)


def list_documents(session: Session, project_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(SourceDocumentModel).where(SourceDocumentModel.project_id == project_id).order_by(SourceDocumentModel.created_at.desc())
    )
    return [_document_result(session, row) for row in rows]


def get_document(session: Session, document_id: str) -> dict[str, Any]:
    document = session.get(SourceDocumentModel, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return _document_result(session, document)


def list_chunks(session: Session, document_id: str) -> list[SourceChunkModel]:
    if session.get(SourceDocumentModel, document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    document = session.get(SourceDocumentModel, document_id)
    return list(
        session.scalars(
            select(SourceChunkModel)
            .where(
                SourceChunkModel.document_id == document_id,
                SourceChunkModel.parse_revision == document.parse_revision,
            )
            .order_by(SourceChunkModel.sequence)
        )
    )


def list_document_proposals(session: Session, document_id: str) -> list[str]:
    return list(session.scalars(select(EvidenceModel.proposal_id).where(EvidenceModel.document_id == document_id).distinct()))


def list_item_sources(session: Session, proposal_id: str, item_key: str) -> list[EvidenceModel]:
    proposal = session.get(ProposalModel, proposal_id)
    if proposal is None or not any(item.get("key") == item_key for item in proposal.payload.get("items", [])):
        raise HTTPException(status_code=404, detail="Proposal item not found")
    item = next(item for item in proposal.payload["items"] if item.get("key") == item_key)
    evidence_ids = item.get("evidence_ids", [])
    return list(session.scalars(select(EvidenceModel).where(EvidenceModel.id.in_(evidence_ids)))) if evidence_ids else []
