"""REST adapter for R-003 external Agent build sessions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_settings
from app.api.schemas import (
    BuildCheckpointCreate,
    BuildSessionCancel,
    BuildSessionComplete,
    BuildSessionCreate,
    BuildSessionResume,
    OntologyLeaseAcquire,
    OntologyLeaseRelease,
    OntologyLeaseRenew,
)
from app.core.config import Settings
from app.services.build_sessions import BuildSessionError, BuildSessionService
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency

router = APIRouter(tags=["build sessions"])


def _service(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(principal_dependency),
) -> BuildSessionService:
    return BuildSessionService(session, settings, actor=principal.actor)


def _call(operation):
    try:
        return operation()
    except BuildSessionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=jsonable_encoder({"code": exc.code, "message": exc.message, **exc.detail}),
        ) from exc


@router.get("/projects/{project_id}/build-context")
def get_project_build_context(
    project_id: str,
    recent_session_limit: int = Query(default=10, ge=1, le=100),
    recent_session_cursor: int = Query(default=0, ge=0),
    service: BuildSessionService = Depends(_service),
):
    return _call(
        lambda: service.get_project_build_context(
            project_id,
            recent_session_limit=recent_session_limit,
            recent_session_cursor=recent_session_cursor,
        )
    )


@router.post(
    "/projects/{project_id}/build-sessions",
    status_code=status.HTTP_201_CREATED,
)
def create_build_session(
    project_id: str,
    payload: BuildSessionCreate,
    response: Response,
    service: BuildSessionService = Depends(_service),
):
    detail, created = _call(lambda: service.create_session(project_id, payload))
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return detail


@router.get("/build-sessions/{session_id}")
def get_build_session(
    session_id: str,
    checkpoint_limit: int = Query(default=50, ge=1, le=100),
    checkpoint_cursor: int | None = Query(default=None, ge=1),
    service: BuildSessionService = Depends(_service),
):
    return _call(
        lambda: service.get_session_detail(
            session_id,
            checkpoint_limit=checkpoint_limit,
            checkpoint_cursor=checkpoint_cursor,
        )
    )


@router.post("/build-sessions/{session_id}:resume")
def resume_build_session(
    session_id: str,
    payload: BuildSessionResume,
    service: BuildSessionService = Depends(_service),
):
    return _call(lambda: service.resume_session(session_id, payload))


@router.post("/build-sessions/{session_id}/checkpoints")
def save_build_checkpoint(
    session_id: str,
    payload: BuildCheckpointCreate,
    service: BuildSessionService = Depends(_service),
):
    return _call(lambda: service.save_checkpoint(session_id, payload))


@router.post("/build-sessions/{session_id}:complete")
def complete_build_session(
    session_id: str,
    payload: BuildSessionComplete,
    service: BuildSessionService = Depends(_service),
):
    return _call(lambda: service.complete_session(session_id, payload))


@router.post("/build-sessions/{session_id}:cancel")
def cancel_build_session(
    session_id: str,
    payload: BuildSessionCancel,
    service: BuildSessionService = Depends(_service),
):
    return _call(lambda: service.cancel_session(session_id, payload))


@router.post("/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire")
def acquire_ontology_lease(
    session_id: str,
    ontology_id: str,
    payload: OntologyLeaseAcquire,
    service: BuildSessionService = Depends(_service),
):
    return _call(lambda: service.acquire_ontology_lease(session_id, ontology_id, payload))


@router.post("/build-sessions/{session_id}/ontology-leases/{ontology_id}:renew")
def renew_ontology_lease(
    session_id: str,
    ontology_id: str,
    payload: OntologyLeaseRenew,
    service: BuildSessionService = Depends(_service),
):
    return _call(lambda: service.renew_ontology_lease(session_id, ontology_id, payload))


@router.post("/build-sessions/{session_id}/ontology-leases/{ontology_id}:release")
def release_ontology_lease(
    session_id: str,
    ontology_id: str,
    payload: OntologyLeaseRelease,
    service: BuildSessionService = Depends(_service),
):
    return _call(lambda: service.release_ontology_lease(session_id, ontology_id, payload))
