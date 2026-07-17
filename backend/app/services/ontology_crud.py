"""Minimal project + ontology CRUD service.

Stage 3 B2 hard-cut: the legacy metadata service (with class/property/relation
CRUD and version-mutability hooks) is gone. This module preserves only the
project and ontology lifecycle operations the frontend ``OntologyHomePage``
still needs.
"""

from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    OntologyCreate,
    OntologyUpdate,
    ProjectCreate,
    ProjectUpdate,
)
from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticRuleDefinitionModel,
    SemanticRuleModel,
)
from app.services.ontology_workspace import OntologyWorkspaceService


def new_id() -> str:
    return str(uuid4())


def not_found(resource: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found")


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def commit_or_409(session: Session, message: str) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise conflict(message) from exc


def list_projects(session: Session) -> list[ProjectModel]:
    return list(session.scalars(select(ProjectModel).order_by(ProjectModel.created_at.desc())))


def get_project(session: Session, project_id: str) -> ProjectModel:
    project = session.get(ProjectModel, project_id)
    if project is None:
        raise not_found("Project")
    return project


def create_project(session: Session, payload: ProjectCreate) -> ProjectModel:
    project = ProjectModel(
        id=new_id(),
        name=payload.name,
        normalized_label=payload.name,
        description=payload.description,
    )
    session.add(project)
    commit_or_409(session, "Project could not be created")
    session.refresh(project)
    return project


def update_project(session: Session, project_id: str, payload: ProjectUpdate) -> ProjectModel:
    project = get_project(session, project_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        project.normalized_label = data["name"]
    for field, value in data.items():
        setattr(project, field, value)
    commit_or_409(session, "Project could not be updated")
    session.refresh(project)
    return project


def delete_project(session: Session, project_id: str) -> None:
    project = get_project(session, project_id)
    _delete_ontology_rules(session, [ontology.id for ontology in project.ontologies])
    session.delete(project)
    commit_or_409(session, "Project could not be deleted")


def list_ontologies(session: Session, project_id: str) -> list[OntologyModel]:
    get_project(session, project_id)
    statement = (
        select(OntologyModel)
        .where(OntologyModel.project_id == project_id)
        .order_by(OntologyModel.created_at.desc())
    )
    return list(session.scalars(statement))


def get_ontology(session: Session, ontology_id: str) -> OntologyModel:
    ontology = session.get(OntologyModel, ontology_id)
    if ontology is None:
        raise not_found("Ontology")
    return ontology


def create_ontology(
    session: Session,
    project_id: str,
    payload: OntologyCreate,
    settings: Settings | None = None,
) -> OntologyModel:
    get_project(session, project_id)
    ontology = OntologyModel(
        id=new_id(),
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        external_mappings=payload.external_mappings,
    )
    session.add(ontology)
    try:
        session.flush()
        OntologyWorkspaceService(session, settings or Settings()).ensure(ontology)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise conflict("Ontology name must be unique within the project") from exc
    except Exception:
        session.rollback()
        raise
    session.refresh(ontology)
    return ontology


def update_ontology(session: Session, ontology_id: str, payload: OntologyUpdate) -> OntologyModel:
    ontology = get_ontology(session, ontology_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ontology, field, value)
    commit_or_409(session, "Ontology could not be updated")
    session.refresh(ontology)
    return ontology


def delete_ontology(session: Session, ontology_id: str) -> None:
    ontology = get_ontology(session, ontology_id)
    _delete_ontology_rules(session, [ontology.id])
    session.delete(ontology)
    commit_or_409(session, "Ontology could not be deleted")


def _delete_ontology_rules(session: Session, ontology_ids: list[str]) -> None:
    """Break the rule/current-definition FK cycle before ontology cascade delete."""
    if not ontology_ids:
        return
    rule_ids = list(
        session.scalars(
            select(SemanticRuleModel.id).where(SemanticRuleModel.ontology_id.in_(ontology_ids))
        )
    )
    if not rule_ids:
        return
    session.execute(
        delete(SemanticRuleDefinitionModel).where(
            SemanticRuleDefinitionModel.semantic_rule_id.in_(rule_ids)
        )
    )
    session.execute(delete(SemanticRuleModel).where(SemanticRuleModel.id.in_(rule_ids)))
    session.flush()
