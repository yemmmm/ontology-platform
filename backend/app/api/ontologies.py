"""Project + ontology CRUD router.

Stage 3 B2 hard-cut: replaces the legacy ``metadata`` router with the minimal
endpoint surface that the frontend ``OntologyHomePage`` still calls. Class,
property, and relation-type endpoints lived in the old router but have no live
callers post-B1, so they are intentionally not re-added here.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_settings
from app.api.schemas import (
    OntologyCreateResponse,
    OntologyCreate,
    OntologyRead,
    OntologyUpdate,
    OntologyWorkspaceContextRead,
    OntologyWorkspaceRepairRequest,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from app.core.config import Settings
from app.services import ontology_crud as service
from app.services.ontology_workspace import OntologyWorkspaceError, OntologyWorkspaceService

router = APIRouter(tags=["ontologies"])


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(session: Session = Depends(get_db_session)):
    return service.list_projects(session)


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: Session = Depends(get_db_session)):
    return service.create_project(session, payload)


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, session: Session = Depends(get_db_session)):
    return service.get_project(session, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_project(session, project_id, payload)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, session: Session = Depends(get_db_session)):
    service.delete_project(session, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/ontologies", response_model=list[OntologyRead])
def list_ontologies(project_id: str, session: Session = Depends(get_db_session)):
    return service.list_ontologies(session, project_id)


@router.post(
    "/projects/{project_id}/ontologies",
    response_model=OntologyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ontology(
    project_id: str,
    payload: OntologyCreate,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    ontology = service.create_ontology(session, project_id, payload, settings)
    workspace = OntologyWorkspaceService(session, settings).context(ontology.id)
    return {**OntologyRead.model_validate(ontology).model_dump(), "workspace": workspace}


@router.get(
    "/ontologies/{ontology_id}/workspace-context",
    response_model=OntologyWorkspaceContextRead,
)
def get_ontology_workspace_context(
    ontology_id: str,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    try:
        return OntologyWorkspaceService(session, settings).context(ontology_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ontologies/{ontology_id}/workspace/repair")
def repair_ontology_workspace(
    ontology_id: str,
    request: OntologyWorkspaceRepairRequest,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    try:
        return OntologyWorkspaceService(session, settings).repair(
            ontology_id, dry_run=request.dry_run
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OntologyWorkspaceError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/projects/{project_id}/ontology-workspaces/repair")
def repair_project_ontology_workspaces(
    project_id: str,
    request: OntologyWorkspaceRepairRequest,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    service.get_project(session, project_id)
    try:
        return OntologyWorkspaceService(session, settings).repair_project(
            project_id, dry_run=request.dry_run
        )
    except OntologyWorkspaceError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/ontologies/{ontology_id}", response_model=OntologyRead)
def get_ontology(ontology_id: str, session: Session = Depends(get_db_session)):
    return service.get_ontology(session, ontology_id)


@router.patch("/ontologies/{ontology_id}", response_model=OntologyRead)
def update_ontology(
    ontology_id: str,
    payload: OntologyUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_ontology(session, ontology_id, payload)


@router.delete("/ontologies/{ontology_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ontology(ontology_id: str, session: Session = Depends(get_db_session)):
    service.delete_ontology(session, ontology_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
