"""Administrator read-only Team artifact bridge (R4.1-010)."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_settings
from app.core.config import Settings
from app.repositories.models import OntologyModel
from app.api.subject_access import require_project
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency
from app.services.modeling_workbench import ModelingWorkbenchService, WorkbenchNotFound
from app.services.ontology_workspace import OntologyWorkspaceService

router = APIRouter(tags=["modeling workbench"])


def get_workbench_service(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ModelingWorkbenchService:
    observations = {}

    def read_workspace(project_id: str, ontology_id: str) -> dict:
        ontology = session.get(OntologyModel, ontology_id)
        if ontology is None or ontology.project_id != project_id:
            raise LookupError("Bound resource not found")
        if ontology_id not in observations:
            observations[ontology_id] = OntologyWorkspaceService(session, settings).context(
                ontology_id
            )
        return observations[ontology_id]

    return ModelingWorkbenchService(workspace_reader=read_workspace)


@router.get("/projects/{project_id}/workbench")
def workbench(
    project_id: str,
    response: Response,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    service: ModelingWorkbenchService = Depends(get_workbench_service),
) -> dict:
    require_project(principal, session, project_id)
    response.headers["Cache-Control"] = "no-store"
    return service.list_runs(project_id)


@router.get("/projects/{project_id}/workbench/runs/{team_run_id}")
def workbench_run(
    project_id: str,
    team_run_id: str,
    response: Response,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    service: ModelingWorkbenchService = Depends(get_workbench_service),
) -> dict:
    require_project(principal, session, project_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        # Team IDs are file identities, distinct from legacy database run_id
        # resources. The projection service resolves their project binding.
        return service.detail(project_id, team_run_id)
    except WorkbenchNotFound as exc:
        raise HTTPException(404, detail={"code": "not_found"}) from exc


@router.get("/projects/{project_id}/workbench/runs/{team_run_id}/competency-questions")
def workbench_competency_questions(
    project_id: str,
    team_run_id: str,
    response: Response,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    service: ModelingWorkbenchService = Depends(get_workbench_service),
) -> dict:
    require_project(principal, session, project_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.competency_questions(project_id, team_run_id)
    except WorkbenchNotFound as exc:
        raise HTTPException(404, detail={"code": "not_found"}) from exc
