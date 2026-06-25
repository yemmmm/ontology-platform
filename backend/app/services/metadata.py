from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import (
    ClassCreate,
    ClassUpdate,
    OntologyCreate,
    OntologyUpdate,
    ProjectCreate,
    ProjectUpdate,
    PropertyDefCreate,
    PropertyDefUpdate,
    RelationTypeCreate,
    RelationTypeUpdate,
)
from app.domain.naming import normalize_neo4j_label, normalize_neo4j_relationship_type
from app.repositories.models import (
    ClassModel,
    OntologyModel,
    ProjectModel,
    PropertyDefModel,
    RelationTypeModel,
)
from app.repositories.postgres import assert_version_mutable


def new_id() -> str:
    return str(uuid4())


def not_found(resource: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found")


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


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
        normalized_label=normalize_neo4j_label(payload.name),
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
        project.normalized_label = normalize_neo4j_label(data["name"])
    for field, value in data.items():
        setattr(project, field, value)
    commit_or_409(session, "Project could not be updated")
    session.refresh(project)
    return project


def delete_project(session: Session, project_id: str) -> None:
    project = get_project(session, project_id)
    for ontology in project.ontologies:
        if isinstance(ontology.current_version_id, str) and ontology.current_version_id:
            ensure_ontology_mutable(session, ontology.id)
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


def ensure_ontology_mutable(session: Session, ontology_id: str) -> None:
    """Protect all legacy metadata write routes once an ontology is version-managed."""
    ontology = get_ontology(session, ontology_id)
    if isinstance(ontology.current_version_id, str) and ontology.current_version_id:
        assert_version_mutable(session, ontology.current_version_id)


def get_ontology_schema(session: Session, ontology_id: str) -> OntologyModel:
    statement = (
        select(OntologyModel)
        .where(OntologyModel.id == ontology_id)
        .options(
            selectinload(OntologyModel.classes).selectinload(ClassModel.properties),
            selectinload(OntologyModel.relation_types),
        )
    )
    ontology = session.scalars(statement).first()
    if ontology is None:
        raise not_found("Ontology")
    return ontology


def create_ontology(session: Session, project_id: str, payload: OntologyCreate) -> OntologyModel:
    get_project(session, project_id)
    ontology = OntologyModel(
        id=new_id(),
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        external_mappings=payload.external_mappings,
    )
    session.add(ontology)
    commit_or_409(session, "Ontology name must be unique within the project")
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
    ensure_ontology_mutable(session, ontology_id)
    session.delete(ontology)
    commit_or_409(session, "Ontology could not be deleted")


def list_classes(session: Session, ontology_id: str) -> list[ClassModel]:
    get_ontology(session, ontology_id)
    statement = (
        select(ClassModel)
        .where(ClassModel.ontology_id == ontology_id)
        .order_by(ClassModel.created_at.desc())
    )
    return list(session.scalars(statement))


def get_class(session: Session, class_id: str) -> ClassModel:
    class_ = session.get(ClassModel, class_id)
    if class_ is None:
        raise not_found("Class")
    return class_


def ensure_class_ids_belong_to_ontology(
    session: Session,
    ontology_id: str,
    class_ids: list[str],
) -> None:
    if not class_ids:
        return
    found_ids = set(
        session.scalars(
            select(ClassModel.id).where(
                ClassModel.ontology_id == ontology_id,
                ClassModel.id.in_(class_ids),
            )
        )
    )
    missing = sorted(set(class_ids) - found_ids)
    if missing:
        raise bad_request(f"Classes do not belong to ontology: {', '.join(missing)}")


def create_class(session: Session, ontology_id: str, payload: ClassCreate) -> ClassModel:
    ensure_ontology_mutable(session, ontology_id)
    ensure_class_ids_belong_to_ontology(session, ontology_id, payload.parent_class_ids)
    class_ = ClassModel(
        id=new_id(),
        ontology_id=ontology_id,
        name=payload.name,
        normalized_label=normalize_neo4j_label(payload.name),
        description=payload.description,
        aliases=payload.aliases,
        parent_class_ids=payload.parent_class_ids,
        external_mappings=payload.external_mappings,
    )
    session.add(class_)
    commit_or_409(session, "Class name must be unique within the ontology")
    session.refresh(class_)
    return class_


def update_class(session: Session, class_id: str, payload: ClassUpdate) -> ClassModel:
    class_ = get_class(session, class_id)
    ensure_ontology_mutable(session, class_.ontology_id)
    data = payload.model_dump(exclude_unset=True)
    if "parent_class_ids" in data:
        parent_ids = data["parent_class_ids"]
        if class_id in parent_ids:
            raise bad_request("Class cannot inherit from itself")
        ensure_class_ids_belong_to_ontology(session, class_.ontology_id, parent_ids)
    if "name" in data:
        class_.normalized_label = normalize_neo4j_label(data["name"])
    for field, value in data.items():
        setattr(class_, field, value)
    commit_or_409(session, "Class could not be updated")
    session.refresh(class_)
    return class_


def delete_class(session: Session, class_id: str) -> None:
    class_ = get_class(session, class_id)
    ensure_ontology_mutable(session, class_.ontology_id)
    session.delete(class_)
    commit_or_409(session, "Class could not be deleted because it is still referenced")


def list_properties(session: Session, class_id: str) -> list[PropertyDefModel]:
    get_class(session, class_id)
    statement = (
        select(PropertyDefModel)
        .where(PropertyDefModel.class_id == class_id)
        .order_by(PropertyDefModel.created_at.desc())
    )
    return list(session.scalars(statement))


def get_property(session: Session, property_id: str) -> PropertyDefModel:
    property_ = session.get(PropertyDefModel, property_id)
    if property_ is None:
        raise not_found("Property definition")
    return property_


def create_property(
    session: Session,
    class_id: str,
    payload: PropertyDefCreate,
) -> PropertyDefModel:
    class_ = get_class(session, class_id)
    ensure_ontology_mutable(session, class_.ontology_id)
    property_ = PropertyDefModel(
        id=new_id(),
        class_id=class_id,
        name=payload.name,
        type=payload.type.value,
        description=payload.description,
        required=payload.required,
        multi_valued=payload.multi_valued,
        enum_values=payload.enum_values,
        constraints=payload.constraints,
        external_mappings=payload.external_mappings,
    )
    session.add(property_)
    commit_or_409(session, "Property name must be unique within the class")
    session.refresh(property_)
    return property_


def update_property(
    session: Session,
    property_id: str,
    payload: PropertyDefUpdate,
) -> PropertyDefModel:
    property_ = get_property(session, property_id)
    ensure_ontology_mutable(session, property_.class_.ontology_id)
    data = payload.model_dump(exclude_unset=True)
    if "type" in data:
        data["type"] = data["type"].value if hasattr(data["type"], "value") else data["type"]
    for field, value in data.items():
        setattr(property_, field, value)
    commit_or_409(session, "Property definition could not be updated")
    session.refresh(property_)
    return property_


def delete_property(session: Session, property_id: str) -> None:
    property_ = get_property(session, property_id)
    ensure_ontology_mutable(session, property_.class_.ontology_id)
    session.delete(property_)
    commit_or_409(session, "Property definition could not be deleted")


def list_relation_types(session: Session, ontology_id: str) -> list[RelationTypeModel]:
    get_ontology(session, ontology_id)
    statement = (
        select(RelationTypeModel)
        .where(RelationTypeModel.ontology_id == ontology_id)
        .order_by(RelationTypeModel.created_at.desc())
    )
    return list(session.scalars(statement))


def get_relation_type(session: Session, relation_type_id: str) -> RelationTypeModel:
    relation_type = session.get(RelationTypeModel, relation_type_id)
    if relation_type is None:
        raise not_found("Relation type")
    return relation_type


def ensure_relation_parent_belongs_to_ontology(
    session: Session,
    ontology_id: str,
    parent_relation_type_id: str | None,
) -> None:
    if parent_relation_type_id is None:
        return
    parent = get_relation_type(session, parent_relation_type_id)
    if parent.ontology_id != ontology_id:
        raise bad_request("Parent relation type must belong to the same ontology")


def create_relation_type(
    session: Session,
    ontology_id: str,
    payload: RelationTypeCreate,
) -> RelationTypeModel:
    ensure_ontology_mutable(session, ontology_id)
    ensure_class_ids_belong_to_ontology(
        session,
        ontology_id,
        [payload.source_class_id, payload.target_class_id],
    )
    ensure_relation_parent_belongs_to_ontology(
        session,
        ontology_id,
        payload.parent_relation_type_id,
    )
    relation_type = RelationTypeModel(
        id=new_id(),
        ontology_id=ontology_id,
        name=payload.name,
        description=payload.description,
        aliases=payload.aliases,
        parent_relation_type_id=payload.parent_relation_type_id,
        source_class_id=payload.source_class_id,
        target_class_id=payload.target_class_id,
        inverse_name=payload.inverse_name,
        normalized_type=normalize_neo4j_relationship_type(payload.name),
        scope_policy=payload.scope_policy,
        symmetric=payload.symmetric,
        transitive=payload.transitive,
        status=payload.status,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        external_mappings=payload.external_mappings,
    )
    session.add(relation_type)
    commit_or_409(
        session,
        "Relation type name must be unique for the same source and target classes",
    )
    session.refresh(relation_type)
    return relation_type


def update_relation_type(
    session: Session,
    relation_type_id: str,
    payload: RelationTypeUpdate,
) -> RelationTypeModel:
    relation_type = get_relation_type(session, relation_type_id)
    ensure_ontology_mutable(session, relation_type.ontology_id)
    data = payload.model_dump(exclude_unset=True)
    class_ids = [
        value
        for key, value in data.items()
        if key in {"source_class_id", "target_class_id"} and value is not None
    ]
    ensure_class_ids_belong_to_ontology(session, relation_type.ontology_id, class_ids)
    if data.get("parent_relation_type_id") == relation_type_id:
        raise bad_request("Relation type cannot inherit from itself")
    ensure_relation_parent_belongs_to_ontology(
        session,
        relation_type.ontology_id,
        data.get("parent_relation_type_id"),
    )
    if "name" in data:
        relation_type.normalized_type = normalize_neo4j_relationship_type(data["name"])
    for field, value in data.items():
        setattr(relation_type, field, value)
    commit_or_409(session, "Relation type could not be updated")
    session.refresh(relation_type)
    return relation_type


def delete_relation_type(session: Session, relation_type_id: str) -> None:
    relation_type = get_relation_type(session, relation_type_id)
    ensure_ontology_mutable(session, relation_type.ontology_id)
    session.delete(relation_type)
    commit_or_409(session, "Relation type could not be deleted because it is still referenced")
