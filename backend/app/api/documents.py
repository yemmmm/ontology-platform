from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.schemas import EvidenceRead, SourceChunkRead, SourceDocumentRead
from app.services import documents as service
from app.services import governance

router = APIRouter(tags=["source-documents"])


@router.post("/projects/{project_id}/source-documents", response_model=SourceDocumentRead, status_code=201)
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    media_type: str | None = Form(default=None),
    session: Session = Depends(get_db_session),
):
    content = await file.read()
    return service.ingest_document(
        session, project_id, file.filename or "document", media_type or file.content_type or "application/octet-stream", content
    )


@router.get("/projects/{project_id}/source-documents", response_model=list[SourceDocumentRead])
def list_documents(project_id: str, session: Session = Depends(get_db_session)):
    return service.list_documents(session, project_id)


@router.get("/source-documents/{document_id}", response_model=SourceDocumentRead)
def get_document(document_id: str, session: Session = Depends(get_db_session)):
    return service.get_document(session, document_id)


@router.post("/source-documents/{document_id}/reparse", response_model=SourceDocumentRead)
def reparse_document(document_id: str, force: bool = False, session: Session = Depends(get_db_session)):
    return service.reparse_document(session, document_id, force)


@router.get("/source-documents/{document_id}/chunks", response_model=list[SourceChunkRead])
def list_chunks(document_id: str, session: Session = Depends(get_db_session)):
    return service.list_chunks(session, document_id)


@router.get("/source-documents/{document_id}/proposals")
def document_proposals(document_id: str, session: Session = Depends(get_db_session)):
    return [governance.proposal_detail(session, proposal_id) for proposal_id in service.list_document_proposals(session, document_id)]


@router.get("/proposals/{proposal_id}/items/{item_key}/sources", response_model=list[EvidenceRead])
def item_sources(proposal_id: str, item_key: str, session: Session = Depends(get_db_session)):
    return service.list_item_sources(session, proposal_id, item_key)
