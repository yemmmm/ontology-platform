from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.schemas import (
    ConnectorQueryRequest,
    ConnectorQueryResult,
    ConnectorTemplateCreate,
    ConnectorTemplateRead,
    ConnectorTemplateUpdate,
    DataResourceCreate,
    DataResourceRead,
    DataResourceUpdate,
    DataSourceCreate,
    DataSourceRead,
    DataSourceUpdate,
    ExternalFieldCreate,
    ExternalFieldRead,
    ExternalFieldUpdate,
    IdentifierResolutionRequest,
    IdentifierResolutionStats,
    SemanticMappingCreate,
    SemanticMappingRead,
    SemanticMappingUpdate,
)
from app.services import catalog as service

router = APIRouter(tags=["catalog"])


@router.post("/projects/{project_id}/data-sources", response_model=DataSourceRead, status_code=201)
def create_data_source(
    project_id: str,
    payload: DataSourceCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_data_source(session, project_id, payload)


@router.get("/projects/{project_id}/data-sources", response_model=list[DataSourceRead])
def list_data_sources(project_id: str, session: Session = Depends(get_db_session)):
    return service.list_data_sources(session, project_id)


@router.patch("/projects/{project_id}/data-sources/{data_source_id}", response_model=DataSourceRead)
def update_data_source(
    project_id: str,
    data_source_id: str,
    payload: DataSourceUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_data_source(session, project_id, data_source_id, payload)


@router.post(
    "/projects/{project_id}/data-resources",
    response_model=DataResourceRead,
    status_code=201,
)
def create_data_resource(
    project_id: str,
    payload: DataResourceCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_data_resource(session, project_id, payload)


@router.get("/projects/{project_id}/data-resources", response_model=list[DataResourceRead])
def list_data_resources(project_id: str, session: Session = Depends(get_db_session)):
    return service.list_data_resources(session, project_id)


@router.patch(
    "/projects/{project_id}/data-resources/{resource_id}",
    response_model=DataResourceRead,
)
def update_data_resource(
    project_id: str,
    resource_id: str,
    payload: DataResourceUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_data_resource(session, project_id, resource_id, payload)


@router.post(
    "/projects/{project_id}/external-fields",
    response_model=ExternalFieldRead,
    status_code=201,
)
def create_external_field(
    project_id: str,
    payload: ExternalFieldCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_external_field(session, project_id, payload)


@router.get("/projects/{project_id}/external-fields", response_model=list[ExternalFieldRead])
def list_external_fields(project_id: str, session: Session = Depends(get_db_session)):
    return service.list_external_fields(session, project_id)


@router.patch(
    "/projects/{project_id}/external-fields/{field_id}",
    response_model=ExternalFieldRead,
)
def update_external_field(
    project_id: str,
    field_id: str,
    payload: ExternalFieldUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_external_field(session, project_id, field_id, payload)


@router.post(
    "/projects/{project_id}/semantic-mappings",
    response_model=SemanticMappingRead,
    status_code=201,
)
def create_semantic_mapping(
    project_id: str,
    payload: SemanticMappingCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_semantic_mapping(session, project_id, payload)


@router.get("/projects/{project_id}/semantic-mappings", response_model=list[SemanticMappingRead])
def list_semantic_mappings(
    project_id: str,
    ontology_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    session: Session = Depends(get_db_session),
):
    return service.list_semantic_mappings(
        session,
        project_id,
        ontology_id=ontology_id,
        target_type=target_type,
        target_id=target_id,
    )


@router.patch(
    "/projects/{project_id}/semantic-mappings/{mapping_id}",
    response_model=SemanticMappingRead,
)
def update_semantic_mapping(
    project_id: str,
    mapping_id: str,
    payload: SemanticMappingUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_semantic_mapping(session, project_id, mapping_id, payload)


@router.post(
    "/projects/{project_id}/connector-templates",
    response_model=ConnectorTemplateRead,
    status_code=201,
)
def create_connector_template(
    project_id: str,
    payload: ConnectorTemplateCreate,
    session: Session = Depends(get_db_session),
):
    return service.create_connector_template(session, project_id, payload)


@router.get(
    "/projects/{project_id}/connector-templates",
    response_model=list[ConnectorTemplateRead],
)
def list_connector_templates(project_id: str, session: Session = Depends(get_db_session)):
    return service.list_connector_templates(session, project_id)


@router.patch(
    "/projects/{project_id}/connector-templates/{template_id}",
    response_model=ConnectorTemplateRead,
)
def update_connector_template(
    project_id: str,
    template_id: str,
    payload: ConnectorTemplateUpdate,
    session: Session = Depends(get_db_session),
):
    return service.update_connector_template(session, project_id, template_id, payload)


@router.post(
    "/projects/{project_id}/connector-templates/{template_id}/query",
    response_model=ConnectorQueryResult,
)
def run_connector_query(
    project_id: str,
    template_id: str,
    payload: ConnectorQueryRequest,
    session: Session = Depends(get_db_session),
):
    return service.run_connector_query(session, project_id, template_id, payload)


@router.post(
    "/projects/{project_id}/identity-resolution/analyze",
    response_model=IdentifierResolutionStats,
)
def analyze_identifier_resolution(
    project_id: str,
    payload: IdentifierResolutionRequest,
    session: Session = Depends(get_db_session),
):
    service.list_data_sources(session, project_id)
    return service.analyze_identifier_resolution(payload)
