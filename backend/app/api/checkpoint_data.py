"""Host-only platform data transfer for R3.0-017 checkpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency
from app.services.checkpoint_data import CheckpointDataError, CheckpointDataService

router = APIRouter(prefix="/checkpoint-data", tags=["checkpoint-data"])


class CaptureRequest(BaseModel):
    project_id: str
    ontology_ids: list[str] = Field(min_length=1)


class ForkRequest(BaseModel):
    snapshot: dict[str, Any]
    name: str = Field(min_length=1, max_length=200)
    target_project_id: UUID


def require_host(principal: AuthPrincipal = Depends(principal_dependency)):
    if not principal.is_org_admin:
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})


@router.post("/capture", dependencies=[Depends(require_host)])
def capture_data(
    payload: CaptureRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
):
    try:
        return CheckpointDataService(session, rdf_store).capture(
            payload.project_id, payload.ontology_ids
        )
    except CheckpointDataError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    finally:
        session.rollback()  # read-only capture; release the Ontology locks


@router.post("/fork", dependencies=[Depends(require_host)])
def fork_data(
    payload: ForkRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    try:
        return CheckpointDataService(session, rdf_store).fork(
            payload.snapshot,
            name=payload.name,
            settings=settings,
            target_project_id=str(payload.target_project_id),
        )
    except CheckpointDataError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc
