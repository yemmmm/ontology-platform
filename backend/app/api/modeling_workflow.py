"""REST adapter for R1.1-002 modeling workflow records."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store
from app.api.schemas import ModelingExecutionEventCreate, ModelingWorkflowArtifactCreate
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency
from app.services.modeling_workflow import ModelingWorkflowError, ModelingWorkflowService
from app.services.ontology_lineage import OntologyLineageService

router = APIRouter(tags=["modeling workflow"])


def _service(
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    principal: AuthPrincipal = Depends(principal_dependency),
) -> ModelingWorkflowService:
    return ModelingWorkflowService(
        session,
        actor=principal.actor,
        lineage_service=OntologyLineageService(session, rdf_store),
    )


def _call(operation):
    try:
        return operation()
    except ModelingWorkflowError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=jsonable_encoder({"code": exc.code, "message": exc.message, **exc.detail}),
        ) from exc


@router.post(
    "/build-sessions/{session_id}/modeling-workflow-artifacts",
    status_code=status.HTTP_201_CREATED,
)
def create_modeling_workflow_artifact(
    session_id: str,
    payload: ModelingWorkflowArtifactCreate,
    response: Response,
    service: ModelingWorkflowService = Depends(_service),
):
    item, created = _call(lambda: service.create_artifact(session_id, payload))
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return item


@router.get("/build-sessions/{session_id}/modeling-workflow-artifacts")
def list_modeling_workflow_artifacts(
    session_id: str,
    artifact_type: str | None = Query(default=None),
    artifact_key: str | None = Query(default=None),
    ontology_id: str | None = Query(default=None),
    current_only: bool = Query(default=False),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    service: ModelingWorkflowService = Depends(_service),
):
    return _call(
        lambda: service.list_artifacts(
            session_id,
            artifact_type=artifact_type,
            artifact_key=artifact_key,
            ontology_id=ontology_id,
            current_only=current_only,
            cursor=cursor,
            limit=limit,
        )
    )


@router.get("/modeling-workflow-artifacts/{workflow_artifact_id}")
def get_modeling_workflow_artifact(
    workflow_artifact_id: str,
    service: ModelingWorkflowService = Depends(_service),
):
    return _call(lambda: service.get_artifact(workflow_artifact_id))


@router.post(
    "/build-sessions/{session_id}/modeling-execution-events",
    status_code=status.HTTP_201_CREATED,
)
def record_modeling_execution_event(
    session_id: str,
    payload: ModelingExecutionEventCreate,
    response: Response,
    service: ModelingWorkflowService = Depends(_service),
):
    item, created = _call(lambda: service.record_event(session_id, payload))
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return item


@router.get("/build-sessions/{session_id}/modeling-execution-events")
def list_modeling_execution_events(
    session_id: str,
    phase: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    cursor: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    service: ModelingWorkflowService = Depends(_service),
):
    return _call(
        lambda: service.list_events(
            session_id,
            phase=phase,
            event_type=event_type,
            cursor=cursor,
            limit=limit,
        )
    )


@router.get("/modeling-execution-events/{execution_event_id}")
def get_modeling_execution_event(
    execution_event_id: str,
    service: ModelingWorkflowService = Depends(_service),
):
    return _call(lambda: service.get_event(execution_event_id))


@router.get("/build-sessions/{session_id}/modeling-workflow:export")
def export_modeling_workflow_record(
    session_id: str,
    format: Literal["json", "markdown"] = Query(default="json"),  # noqa: A002
    service: ModelingWorkflowService = Depends(_service),
):
    exported = _call(lambda: service.export(session_id, export_format=format))
    if format == "markdown":
        return PlainTextResponse(exported, media_type="text/markdown; charset=utf-8")
    return exported


__all__ = ["router"]
