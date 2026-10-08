from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.schemas import (
    CompetencyQuestionCreate,
    CompetencyQuestionRead,
    CompetencyQuestionStatusUpdate,
    CompetencyQuestionUpdate,
    InterviewAnswerCreate,
    InterviewAnswerRead,
    ProjectBriefRead,
    ProjectBriefUpdate,
)
from app.core.config import Settings
from app.repositories.models import CompetencyQuestionModel
from app.repositories.rdf_store import RdfStoreRepository
from app.services import interview as service
from app.services.interview import brief_summary_for_overview, question_summary_for_overview
from app.services.semantic_build_overview import BuildOverviewService
from app.services.semantic_read_model import SemanticReadModelService
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency

router = APIRouter(tags=["project interview"])


@router.get("/projects/{project_id}/brief", response_model=ProjectBriefRead)
def get_project_brief(project_id: str, session: Session = Depends(get_db_session)):
    return service.get_project_brief(session, project_id)


@router.patch("/projects/{project_id}/brief", response_model=ProjectBriefRead)
def update_project_brief(
    project_id: str, payload: ProjectBriefUpdate, session: Session = Depends(get_db_session)
):
    return service.update_project_brief(session, project_id, payload)


@router.post(
    "/projects/{project_id}/interview-answers",
    response_model=InterviewAnswerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_interview_answer(
    project_id: str,
    payload: InterviewAnswerCreate,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
):
    return service.create_answer(
        session, project_id, payload.model_copy(update={"actor_id": principal.actor})
    )


@router.get(
    "/projects/{project_id}/competency-questions", response_model=list[CompetencyQuestionRead]
)
def list_competency_questions(
    project_id: str,
    include_inactive: bool = Query(False),
    session: Session = Depends(get_db_session),
):
    return service.list_questions(session, project_id, include_inactive)


@router.post(
    "/projects/{project_id}/competency-questions",
    response_model=CompetencyQuestionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_competency_question(
    project_id: str, payload: CompetencyQuestionCreate, session: Session = Depends(get_db_session)
):
    return service.create_question(session, project_id, payload)


@router.patch("/competency-questions/{question_id}", response_model=CompetencyQuestionRead)
def update_competency_question(
    question_id: str, payload: CompetencyQuestionUpdate, session: Session = Depends(get_db_session)
):
    return service.update_question(session, question_id, payload)


@router.post("/competency-questions/{question_id}/status", response_model=CompetencyQuestionRead)
def set_competency_question_status(
    question_id: str,
    payload: CompetencyQuestionStatusUpdate,
    session: Session = Depends(get_db_session),
):
    return service.set_question_status(session, question_id, payload)


@router.post("/competency-questions/{question_id}/validate", response_model=CompetencyQuestionRead)
def validate_competency_question(
    question_id: str,
    session: Session = Depends(get_db_session),
    rdf_store=Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    service.run_question_validation(session, rdf_store, question_id, settings)
    return session.get(CompetencyQuestionModel, question_id)




def _build_overview_service(session, rdf_store, settings):
    from app.services.semantic_read_scope import SemanticReadScopeResolver

    scope_resolver = SemanticReadScopeResolver(session)

    read_model_service = SemanticReadModelService(
        rdf_store=rdf_store,
        scope_resolver=scope_resolver,
        timeout_seconds=settings.semantic_query_timeout_seconds,
        default_limit=1,
    )

    def _read(ontology_id, model_name):
        return read_model_service.read_model(
            ontology_id=ontology_id,
            model_name=model_name,
            field_set="summary",
        )

    return BuildOverviewService(
        read_model=_read,
        brief_summary=brief_summary_for_overview,
        question_summary=question_summary_for_overview,
    )


@router.get("/ontologies/{ontology_id}/build-overview")
def get_build_overview(
    ontology_id: str,
    project_id: Annotated[str, Query()] = "",
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    from app.repositories.models import OntologyModel
    ontology = session.get(OntologyModel, ontology_id)
    if ontology is None or (project_id and ontology.project_id != project_id):
        raise HTTPException(status_code=404, detail="Ontology not found")
    project_id = ontology.project_id
    service = _build_overview_service(session, rdf_store, settings)
    response = service.build(
        session=session,
        project_id=project_id,
        ontology_id=ontology_id,

    )
    return asdict(response)
