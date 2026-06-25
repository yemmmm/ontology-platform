from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.schemas import EvidenceRead, EvidenceChunkRead, EvidenceArtifactRead
from app.services import documents as service
from app.services import governance

router = APIRouter(tags=["evidence-artifacts"])


@router.post("/projects/{project_id}/evidence-artifacts", response_model=EvidenceArtifactRead, status_code=201)
async def upload_artifact(
    project_id: str,
    file: UploadFile = File(...),
    media_type: str | None = Form(default=None),
    session: Session = Depends(get_db_session),
):
    content = await file.read()
    return service.ingest_artifact(
        session, project_id, file.filename or "document", media_type or file.content_type or "application/octet-stream", content
    )


@router.post("/projects/{project_id}/source-documents", response_model=EvidenceArtifactRead, status_code=201)
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    media_type: str | None = Form(default=None),
    session: Session = Depends(get_db_session),
):
    return await upload_artifact(project_id, file, media_type, session)


@router.get("/projects/{project_id}/evidence-artifacts", response_model=list[EvidenceArtifactRead])
def list_artifacts(project_id: str, session: Session = Depends(get_db_session)):
    return service.list_artifacts(session, project_id)


@router.get("/projects/{project_id}/source-documents", response_model=list[EvidenceArtifactRead])
def list_documents(project_id: str, session: Session = Depends(get_db_session)):
    return service.list_artifacts(session, project_id)


@router.get("/evidence-artifacts/{artifact_id}", response_model=EvidenceArtifactRead)
def get_artifact(artifact_id: str, session: Session = Depends(get_db_session)):
    return service.get_artifact(session, artifact_id)


@router.get("/source-documents/{document_id}", response_model=EvidenceArtifactRead)
def get_document(document_id: str, session: Session = Depends(get_db_session)):
    return service.get_artifact(session, document_id)


@router.post("/evidence-artifacts/{artifact_id}/reparse", response_model=EvidenceArtifactRead)
def reparse_artifact(artifact_id: str, force: bool = False, session: Session = Depends(get_db_session)):
    return service.reparse_artifact(session, artifact_id, force)


@router.post("/source-documents/{document_id}/reparse", response_model=EvidenceArtifactRead)
def reparse_document(document_id: str, force: bool = False, session: Session = Depends(get_db_session)):
    return service.reparse_artifact(session, document_id, force)


@router.get("/evidence-artifacts/{artifact_id}/chunks", response_model=list[EvidenceChunkRead])
def list_chunks(artifact_id: str, session: Session = Depends(get_db_session)):
    return service.list_chunks(session, artifact_id)


@router.get("/source-documents/{document_id}/chunks", response_model=list[EvidenceChunkRead])
def list_document_chunks(document_id: str, session: Session = Depends(get_db_session)):
    return service.list_chunks(session, document_id)


@router.get("/evidence-artifacts/{artifact_id}/proposals")
def artifact_proposals(artifact_id: str, session: Session = Depends(get_db_session)):
    return [
        governance.proposal_detail(session, proposal_id)
        for proposal_id in service.list_artifact_proposals(session, artifact_id)
    ]


@router.get("/source-documents/{document_id}/proposals")
def document_proposals(document_id: str, session: Session = Depends(get_db_session)):
    return [
        governance.proposal_detail(session, proposal_id)
        for proposal_id in service.list_artifact_proposals(session, document_id)
    ]


@router.get("/proposals/{proposal_id}/items/{item_key}/sources", response_model=list[EvidenceRead])
def item_sources(proposal_id: str, item_key: str, session: Session = Depends(get_db_session)):
    return service.list_item_sources(session, proposal_id, item_key)
