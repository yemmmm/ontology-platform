from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.schemas import (
    ClassCreate,
    ClassRead,
    ClassUpdate,
    OntologyCreate,
    OntologyRead,
    OntologySchemaRead,
    OntologyUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    PropertyDefCreate,
    PropertyDefRead,
    PropertyDefUpdate,
    RelationTypeCreate,
    RelationTypeRead,
    RelationTypeUpdate,
)
from app.services import metadata as service

router = APIRouter(tags=["metadata"])


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
    response_model=OntologyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ontology(
    project_id: str,
    payload: OntologyCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_ontology(session, project_id, payload)


@router.get("/ontologies/{ontology_id}", response_model=OntologyRead)
def get_ontology(ontology_id: str, session: Session = Depends(get_db_session)):
    return service.get_ontology(session, ontology_id)


@router.get("/ontologies/{ontology_id}/schema", response_model=OntologySchemaRead)
def get_ontology_schema(ontology_id: str, session: Session = Depends(get_db_session)):
    return service.get_ontology_schema(session, ontology_id)


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


@router.get("/ontologies/{ontology_id}/classes", response_model=list[ClassRead])
def list_classes(ontology_id: str, session: Session = Depends(get_db_session)):
    return service.list_classes(session, ontology_id)


@router.post(
    "/ontologies/{ontology_id}/classes",
    response_model=ClassRead,
    status_code=status.HTTP_201_CREATED,
)
def create_class(
    ontology_id: str,
    payload: ClassCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_class(session, ontology_id, payload)


@router.get("/classes/{class_id}", response_model=ClassRead)
def get_class(class_id: str, session: Session = Depends(get_db_session)):
    return service.get_class(session, class_id)


@router.patch("/classes/{class_id}", response_model=ClassRead)
def update_class(
    class_id: str,
    payload: ClassUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_class(session, class_id, payload)


@router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(class_id: str, session: Session = Depends(get_db_session)):
    service.delete_class(session, class_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/classes/{class_id}/properties", response_model=list[PropertyDefRead])
def list_properties(class_id: str, session: Session = Depends(get_db_session)):
    return service.list_properties(session, class_id)


@router.post(
    "/classes/{class_id}/properties",
    response_model=PropertyDefRead,
    status_code=status.HTTP_201_CREATED,
)
def create_property(
    class_id: str,
    payload: PropertyDefCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_property(session, class_id, payload)


@router.get("/properties/{property_id}", response_model=PropertyDefRead)
def get_property(property_id: str, session: Session = Depends(get_db_session)):
    return service.get_property(session, property_id)


@router.patch("/properties/{property_id}", response_model=PropertyDefRead)
def update_property(
    property_id: str,
    payload: PropertyDefUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_property(session, property_id, payload)


@router.delete("/properties/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(property_id: str, session: Session = Depends(get_db_session)):
    service.delete_property(session, property_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/ontologies/{ontology_id}/relation-types", response_model=list[RelationTypeRead])
def list_relation_types(ontology_id: str, session: Session = Depends(get_db_session)):
    return service.list_relation_types(session, ontology_id)


@router.post(
    "/ontologies/{ontology_id}/relation-types",
    response_model=RelationTypeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_relation_type(
    ontology_id: str,
    payload: RelationTypeCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_relation_type(session, ontology_id, payload)


@router.get("/relation-types/{relation_type_id}", response_model=RelationTypeRead)
def get_relation_type(relation_type_id: str, session: Session = Depends(get_db_session)):
    return service.get_relation_type(session, relation_type_id)


@router.patch("/relation-types/{relation_type_id}", response_model=RelationTypeRead)
def update_relation_type(
    relation_type_id: str,
    payload: RelationTypeUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_relation_type(session, relation_type_id, payload)


@router.delete("/relation-types/{relation_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relation_type(relation_type_id: str, session: Session = Depends(get_db_session)):
    service.delete_relation_type(session, relation_type_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
