from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ConnectorQueryRequest,
    ConnectorTemplateCreate,
    ConnectorTemplateUpdate,
    DataResourceCreate,
    DataResourceUpdate,
    DataSourceCreate,
    DataSourceUpdate,
    ExternalFieldCreate,
    ExternalFieldUpdate,
    IdentifierResolutionRequest,
    SemanticMappingCreate,
    SemanticMappingUpdate,
)
from app.repositories.models import (
    ClassModel,
    ConnectorQueryAuditModel,
    ConnectorTemplateModel,
    DataResourceModel,
    DataSourceModel,
    ExternalFieldModel,
    OntologyModel,
    PropertyDefModel,
    RelationTypeModel,
    SemanticMappingModel,
)
from app.services.metadata import bad_request, commit_or_409, get_project, new_id, not_found


def create_data_source(
    session: Session, project_id: str, payload: DataSourceCreate
) -> DataSourceModel:
    get_project(session, project_id)
    source = DataSourceModel(id=new_id(), project_id=project_id, **payload.model_dump())
    session.add(source)
    commit_or_409(session, "Data source name must be unique within the project")
    session.refresh(source)
    return source


def list_data_sources(session: Session, project_id: str) -> list[DataSourceModel]:
    get_project(session, project_id)
    statement = (
        select(DataSourceModel)
        .where(DataSourceModel.project_id == project_id)
        .order_by(DataSourceModel.created_at.desc())
    )
    return list(session.scalars(statement))


def get_data_source(session: Session, data_source_id: str) -> DataSourceModel:
    source = session.get(DataSourceModel, data_source_id)
    if source is None:
        raise not_found("Data source")
    return source


def update_data_source(
    session: Session, project_id: str, data_source_id: str, payload: DataSourceUpdate
) -> DataSourceModel:
    source = get_data_source(session, data_source_id)
    if source.project_id != project_id:
        raise bad_request("Data source must belong to the project")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    commit_or_409(session, "Data source could not be updated")
    session.refresh(source)
    return source


def create_data_resource(
    session: Session, project_id: str, payload: DataResourceCreate
) -> DataResourceModel:
    source = get_data_source(session, payload.data_source_id)
    if source.project_id != project_id:
        raise bad_request("Data source must belong to the project")
    resource = DataResourceModel(id=new_id(), project_id=project_id, **payload.model_dump())
    session.add(resource)
    commit_or_409(session, "Data resource name must be unique within the data source")
    session.refresh(resource)
    return resource


def list_data_resources(session: Session, project_id: str) -> list[DataResourceModel]:
    get_project(session, project_id)
    statement = (
        select(DataResourceModel)
        .where(DataResourceModel.project_id == project_id)
        .order_by(DataResourceModel.created_at.desc())
    )
    return list(session.scalars(statement))


def get_data_resource(session: Session, resource_id: str) -> DataResourceModel:
    resource = session.get(DataResourceModel, resource_id)
    if resource is None:
        raise not_found("Data resource")
    return resource


def update_data_resource(
    session: Session, project_id: str, resource_id: str, payload: DataResourceUpdate
) -> DataResourceModel:
    resource = get_data_resource(session, resource_id)
    if resource.project_id != project_id:
        raise bad_request("Data resource must belong to the project")
    data = payload.model_dump(exclude_unset=True)
    if "data_source_id" in data:
        source = get_data_source(session, data["data_source_id"])
        if source.project_id != project_id:
            raise bad_request("Data source must belong to the project")
    for field, value in data.items():
        setattr(resource, field, value)
    if "name" in data:
        _sync_mapping_resource_name(session, resource.id, data["name"])
    commit_or_409(session, "Data resource could not be updated")
    session.refresh(resource)
    return resource


def create_external_field(
    session: Session, project_id: str, payload: ExternalFieldCreate
) -> ExternalFieldModel:
    resource = get_data_resource(session, payload.data_resource_id)
    if resource.project_id != project_id:
        raise bad_request("Data resource must belong to the project")
    values = payload.model_dump()
    field = ExternalFieldModel(
        id=new_id(),
        project_id=project_id,
        data_source_id=resource.data_source_id,
        **values,
    )
    session.add(field)
    commit_or_409(session, "External field name must be unique within the data resource")
    session.refresh(field)
    return field


def list_external_fields(session: Session, project_id: str) -> list[ExternalFieldModel]:
    get_project(session, project_id)
    statement = (
        select(ExternalFieldModel)
        .where(ExternalFieldModel.project_id == project_id)
        .order_by(ExternalFieldModel.created_at.desc())
    )
    return list(session.scalars(statement))


def get_external_field(session: Session, field_id: str) -> ExternalFieldModel:
    field = session.get(ExternalFieldModel, field_id)
    if field is None:
        raise not_found("External field")
    return field


def update_external_field(
    session: Session, project_id: str, field_id: str, payload: ExternalFieldUpdate
) -> ExternalFieldModel:
    field = get_external_field(session, field_id)
    if field.project_id != project_id:
        raise bad_request("External field must belong to the project")
    data = payload.model_dump(exclude_unset=True)
    if "data_resource_id" in data:
        resource = get_data_resource(session, data["data_resource_id"])
        if resource.project_id != project_id:
            raise bad_request("Data resource must belong to the project")
        field.data_source_id = resource.data_source_id
        _sync_mapping_field_resource(session, field.id, resource)
    for name, value in data.items():
        setattr(field, name, value)
    if "name" in data:
        _sync_mapping_field_name(session, field.id, data["name"])
    commit_or_409(session, "External field could not be updated")
    session.refresh(field)
    return field


def _sync_mapping_resource_name(session: Session, resource_id: str, name: str) -> None:
    rows = session.scalars(
        select(SemanticMappingModel).where(SemanticMappingModel.resource_id == resource_id)
    )
    for mapping in rows:
        mapping.external_resource_name = name


def _sync_mapping_field_name(session: Session, field_id: str, name: str) -> None:
    rows = session.scalars(
        select(SemanticMappingModel).where(SemanticMappingModel.field_id == field_id)
    )
    for mapping in rows:
        mapping.external_field_name = name


def _sync_mapping_field_resource(
    session: Session, field_id: str, resource: DataResourceModel
) -> None:
    rows = session.scalars(
        select(SemanticMappingModel).where(SemanticMappingModel.field_id == field_id)
    )
    for mapping in rows:
        mapping.data_source_id = resource.data_source_id
        mapping.resource_id = resource.id
        mapping.external_resource_name = resource.name


def _ensure_mapping_target(
    session: Session,
    ontology: OntologyModel,
    target_type: str,
    target_id: str,
) -> None:
    if target_type == "class":
        target = session.get(ClassModel, target_id)
        if target is None or target.ontology_id != ontology.id:
            raise bad_request("Mapping target class must belong to the ontology")
    elif target_type == "property":
        target = session.get(PropertyDefModel, target_id)
        if target is None or target.class_.ontology_id != ontology.id:
            raise bad_request("Mapping target property must belong to the ontology")
    elif target_type == "relation_type":
        target = session.get(RelationTypeModel, target_id)
        if target is None or target.ontology_id != ontology.id:
            raise bad_request("Mapping target relation type must belong to the ontology")
    elif target_type == "entity":
        if not target_id.strip():
            raise bad_request("Mapping target entity id must not be empty")
    else:
        raise bad_request("Unsupported mapping target type")


def create_semantic_mapping(
    session: Session, project_id: str, payload: SemanticMappingCreate
) -> SemanticMappingModel:
    ontology = session.get(OntologyModel, payload.ontology_id)
    if ontology is None:
        raise not_found("Ontology")
    if ontology.project_id != project_id:
        raise bad_request("Ontology must belong to the project")
    field = get_external_field(session, payload.field_id)
    if field.project_id != project_id:
        raise bad_request("External field must belong to the project")
    resource = get_data_resource(session, field.data_resource_id)
    _ensure_mapping_target(session, ontology, payload.target_type, payload.target_id)
    mapping = SemanticMappingModel(
        id=new_id(),
        project_id=project_id,
        data_source_id=field.data_source_id,
        resource_id=field.data_resource_id,
        external_resource_name=resource.name,
        external_field_name=field.name,
        **payload.model_dump(),
    )
    session.add(mapping)
    commit_or_409(session, "Semantic mapping already exists for this target and field")
    session.refresh(mapping)
    return mapping


def update_semantic_mapping(
    session: Session, project_id: str, mapping_id: str, payload: SemanticMappingUpdate
) -> SemanticMappingModel:
    mapping = session.get(SemanticMappingModel, mapping_id)
    if mapping is None:
        raise not_found("Semantic mapping")
    if mapping.project_id != project_id:
        raise bad_request("Semantic mapping must belong to the project")
    ontology = session.get(OntologyModel, mapping.ontology_id)
    if ontology is None:
        raise not_found("Ontology")
    data = payload.model_dump(exclude_unset=True)
    target_type = data.get("target_type", mapping.target_type)
    target_id = data.get("target_id", mapping.target_id)
    if "target_type" in data or "target_id" in data:
        _ensure_mapping_target(session, ontology, target_type, target_id)
    if "field_id" in data:
        field = get_external_field(session, data["field_id"])
        if field.project_id != project_id:
            raise bad_request("External field must belong to the project")
        resource = get_data_resource(session, field.data_resource_id)
        mapping.data_source_id = field.data_source_id
        mapping.resource_id = field.data_resource_id
        mapping.external_resource_name = resource.name
        mapping.external_field_name = field.name
    for field_name, value in data.items():
        setattr(mapping, field_name, value)
    commit_or_409(session, "Semantic mapping could not be updated")
    session.refresh(mapping)
    return mapping


def list_semantic_mappings(
    session: Session,
    project_id: str,
    ontology_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> list[SemanticMappingModel]:
    get_project(session, project_id)
    statement = select(SemanticMappingModel).where(SemanticMappingModel.project_id == project_id)
    if ontology_id is not None:
        statement = statement.where(SemanticMappingModel.ontology_id == ontology_id)
    if target_type is not None:
        statement = statement.where(SemanticMappingModel.target_type == target_type)
    if target_id is not None:
        statement = statement.where(SemanticMappingModel.target_id == target_id)
    return list(session.scalars(statement.order_by(SemanticMappingModel.created_at.desc())))


def create_connector_template(
    session: Session, project_id: str, payload: ConnectorTemplateCreate
) -> ConnectorTemplateModel:
    source = get_data_source(session, payload.data_source_id)
    if source.project_id != project_id:
        raise bad_request("Data source must belong to the project")
    if payload.allowed_field_ids:
        fields = list(
            session.scalars(
                select(ExternalFieldModel).where(
                    ExternalFieldModel.project_id == project_id,
                    ExternalFieldModel.id.in_(payload.allowed_field_ids),
                )
            )
        )
        found_ids = {field.id for field in fields}
        missing = sorted(set(payload.allowed_field_ids) - found_ids)
        if missing:
            raise bad_request(f"External fields do not belong to project: {', '.join(missing)}")
        wrong_source = [field.id for field in fields if field.data_source_id != payload.data_source_id]
        if wrong_source:
            raise bad_request("Connector template fields must belong to the same data source")
    template = ConnectorTemplateModel(id=new_id(), project_id=project_id, **payload.model_dump())
    session.add(template)
    commit_or_409(session, "Connector template name must be unique within the data source")
    session.refresh(template)
    return template


def update_connector_template(
    session: Session, project_id: str, template_id: str, payload: ConnectorTemplateUpdate
) -> ConnectorTemplateModel:
    template = session.get(ConnectorTemplateModel, template_id)
    if template is None:
        raise not_found("Connector template")
    if template.project_id != project_id:
        raise bad_request("Connector template must belong to the project")
    data = payload.model_dump(exclude_unset=True)
    data_source_id = data.get("data_source_id", template.data_source_id)
    if "data_source_id" in data:
        source = get_data_source(session, data_source_id)
        if source.project_id != project_id:
            raise bad_request("Data source must belong to the project")
    if "allowed_field_ids" in data:
        _validate_template_fields(session, project_id, data_source_id, data["allowed_field_ids"])
    for field_name, value in data.items():
        setattr(template, field_name, value)
    commit_or_409(session, "Connector template could not be updated")
    session.refresh(template)
    return template


def list_connector_templates(session: Session, project_id: str) -> list[ConnectorTemplateModel]:
    get_project(session, project_id)
    statement = (
        select(ConnectorTemplateModel)
        .where(ConnectorTemplateModel.project_id == project_id)
        .order_by(ConnectorTemplateModel.created_at.desc())
    )
    return list(session.scalars(statement))


def _validate_template_fields(
    session: Session, project_id: str, data_source_id: str, field_ids: list[str]
) -> None:
    if not field_ids:
        return
    fields = list(
        session.scalars(
            select(ExternalFieldModel).where(
                ExternalFieldModel.project_id == project_id,
                ExternalFieldModel.id.in_(field_ids),
            )
        )
    )
    found_ids = {field.id for field in fields}
    missing = sorted(set(field_ids) - found_ids)
    if missing:
        raise bad_request(f"External fields do not belong to project: {', '.join(missing)}")
    wrong_source = [field.id for field in fields if field.data_source_id != data_source_id]
    if wrong_source:
        raise bad_request("Connector template fields must belong to the same data source")


def run_connector_query(
    session: Session, project_id: str, template_id: str, payload: ConnectorQueryRequest
) -> dict[str, Any]:
    template = session.get(ConnectorTemplateModel, template_id)
    if template is None:
        raise not_found("Connector template")
    if template.project_id != project_id:
        raise bad_request("Connector template must belong to the project")
    source = get_data_source(session, template.data_source_id)
    fields = list(
        session.scalars(
            select(ExternalFieldModel).where(ExternalFieldModel.id.in_(template.allowed_field_ids))
        )
    )
    authorized, denial_reason = _authorize_query(template, fields, payload.approved)
    queried_at = datetime.now(timezone.utc)
    rows = (
        _apply_field_policies(
            _materialize_result_rows(template.result_schema, payload.parameters),
            fields,
            payload.approved,
        )
        if authorized
        else []
    )
    result = {
        "template_id": template.id,
        "authorized": authorized,
        "denial_reason": denial_reason,
        "source": {
            "data_source_id": source.id,
            "data_source": source.name,
            "source_type": source.source_type,
        },
        "queried_at": queried_at,
        "audit": {
            "actor_id": payload.actor_id,
            "field_ids": template.allowed_field_ids,
            "policy": template.access_policy,
        },
        "rows": rows,
    }
    audit = ConnectorQueryAuditModel(
        id=new_id(),
        project_id=project_id,
        template_id=template.id,
        actor_id=payload.actor_id,
        authorized=authorized,
        denial_reason=denial_reason,
        parameters=payload.parameters,
        result={"rows": rows, "source": result["source"]},
    )
    session.add(audit)
    commit_or_409(session, "Connector query audit could not be recorded")
    result["audit"]["audit_id"] = audit.id
    return result


def _authorize_query(
    template: ConnectorTemplateModel, fields: list[ExternalFieldModel], approved: bool
) -> tuple[bool, str | None]:
    if template.access_policy == "deny":
        return False, "Connector template policy denies this query"
    restricted = [
        field
        for field in fields
        if field.access_policy in {"deny", "approval_required"} or field.sensitivity == "restricted"
    ]
    denied = [field.name for field in fields if field.access_policy == "deny"]
    if denied:
        return False, f"Field policy denies access: {', '.join(sorted(denied))}"
    if template.access_policy == "approval_required" and not approved:
        return False, "Connector template requires approval"
    if restricted and not approved:
        names = ", ".join(sorted(field.name for field in restricted))
        return False, f"Approval required for restricted fields: {names}"
    return True, None


def _materialize_result_rows(
    result_schema: dict[str, Any], parameters: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = result_schema.get("rows", [])
    if not isinstance(rows, list):
        return []
    materialized = [dict(row) for row in rows if isinstance(row, dict)]
    if not parameters:
        return materialized
    return [
        row
        for row in materialized
        if all(key not in row or row[key] == value for key, value in parameters.items())
    ]


def _apply_field_policies(
    rows: list[dict[str, Any]], fields: list[ExternalFieldModel], approved: bool
) -> list[dict[str, Any]]:
    field_by_name = {field.name: field for field in fields}
    masked_rows: list[dict[str, Any]] = []
    for row in rows:
        masked = dict(row)
        for name, value in row.items():
            field = field_by_name.get(name)
            if field is None or approved:
                continue
            if field.access_policy == "mask":
                masked[name] = field.masking_rule or "***"
            elif field.sensitivity in {"confidential", "restricted"}:
                masked[name] = "***" if value is not None else None
        masked_rows.append(masked)
    return masked_rows


def analyze_identifier_resolution(payload: IdentifierResolutionRequest) -> dict[str, Any]:
    left = set(payload.left_values)
    right = set(payload.right_values)
    overlap = left & right
    left_count = len(left)
    right_count = len(right)
    return {
        "left_count": left_count,
        "right_count": right_count,
        "overlap_count": len(overlap),
        "left_coverage": len(overlap) / left_count if left_count else 0.0,
        "right_coverage": len(overlap) / right_count if right_count else 0.0,
        "one_to_one": left_count == right_count == len(overlap),
        "unmapped_left": sorted(left - right),
        "unmapped_right": sorted(right - left),
    }
