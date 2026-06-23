from fastapi import APIRouter, Depends, Query, status
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver
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
from app.repositories.models import CompetencyQuestionModel
from app.services import interview as service

router = APIRouter(tags=["project interview"])


@router.get("/projects/{project_id}/build-context")
def get_build_context(project_id: str, session: Session = Depends(get_db_session)):
    return service.get_build_context(session, project_id)


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
    project_id: str, payload: InterviewAnswerCreate, session: Session = Depends(get_db_session)
):
    return service.create_answer(session, project_id, payload)


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
    driver: Driver = Depends(get_neo4j_driver),
):
    service.run_question_validation(session, driver, question_id)
    return session.get(CompetencyQuestionModel, question_id)
