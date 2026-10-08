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
    SemanticGraphRegistryModel,
)
from app.repositories.rdf_store import RdfGraphDelta, RdfStoreRepository
from app.services.checkpoint_archive import lock_projects
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


def delete_project(session: Session, project_id: str, settings=None, rdf_store=None) -> None:
    lock_projects(session, [project_id])
    project = get_project(session, project_id)
    check_mapping_deletion(
        session, [ontology.id for ontology in project.ontologies], settings, rdf_store
    )
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
    changes = payload.model_dump(exclude_unset=True)
    references = changes.get("reference_ontology_ids")
    if "reference_ontology_ids" in changes:
        if references is None or len(set(references)) != len(references) or ontology_id in references:
            raise conflict("reference_ontology_ids must be unique dependencies, excluding self")
        targets = list(session.scalars(select(OntologyModel).where(OntologyModel.id.in_(references))))
        if len(targets) != len(references) or any(target.project_id != ontology.project_id for target in targets):
            raise conflict("Reference Ontologies must belong to this Project")
        lock_projects(session, [ontology.project_id])
        session.scalar(select(OntologyModel).where(OntologyModel.id == ontology_id).with_for_update())
        from app.services.semantic_mapping_state import project_fence_check, mapping_state, _union
        from app.services.semantic_mapping_integrity import validate_mapping_graph
        project_fence_check(session, [ontology.project_id])
        settings = Settings()
        store = RdfStoreRepository(settings.oxigraph_url)
        def findings():
            _, owners, before, _, scopes = mapping_state(session, store, settings, RdfGraphDelta(), ontology_id)
            return validate_mapping_graph(_union(before[iri] for iri in owners[ontology_id]),
                                          reference_graph=_union(before[iri] for iri in scopes[ontology_id]))
        previous = findings()
        ontology.reference_ontology_ids = references
        session.flush()
        new = [finding for finding in findings() if finding not in previous]
        if new:
            session.rollback()
            raise HTTPException(status_code=409, detail={"code": "mapping_reference_scope_in_use",
                                "message": "Revise dependent mappings before removing references", "findings": new})
    for field, value in changes.items():
        setattr(ontology, field, value)
    commit_or_409(session, "Ontology could not be updated")
    session.refresh(ontology)
    return ontology


def delete_ontology(session: Session, ontology_id: str, settings=None, rdf_store=None) -> None:
    ontology = get_ontology(session, ontology_id)
    lock_projects(session, [ontology.project_id])
    session.scalar(select(OntologyModel).where(OntologyModel.id == ontology_id).with_for_update())
    check_mapping_deletion(session, [ontology_id], settings, rdf_store)
    _delete_ontology_rules(session, [ontology.id])
    session.delete(ontology)
    commit_or_409(session, "Ontology could not be deleted")


def check_mapping_deletion(session, ontology_ids, settings=None, rdf_store=None):
    """Prevent lifecycle removal from orphaning a surviving declared mapping."""
    from app.services.semantic_mapping_state import (
        MappingWriteError,
        mapping_write_findings,
        project_fence_check,
    )

    projects = list(
        session.scalars(
            select(OntologyModel.project_id).where(OntologyModel.id.in_(ontology_ids)).distinct()
        )
    )
    try:
        project_fence_check(session, projects)
        graph_iris = list(
            session.scalars(
                select(SemanticGraphRegistryModel.graph_iri).where(
                    SemanticGraphRegistryModel.semantic_owner_type == "ontology",
                    SemanticGraphRegistryModel.semantic_owner_id.in_(ontology_ids),
                    SemanticGraphRegistryModel.category.in_(["ontology", "data"]),
                )
            )
        )
        if not graph_iris:
            return
        settings = settings or Settings()
        rdf_store = rdf_store or RdfStoreRepository(settings.oxigraph_url)
        findings = mapping_write_findings(
            session, rdf_store, settings, RdfGraphDelta(clear_graphs=graph_iris)
        )
        if findings:
            raise MappingWriteError(findings[0]["code"], findings[0]["message"], findings)
    except MappingWriteError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
                "findings": exc.findings,
            },
        ) from exc


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
