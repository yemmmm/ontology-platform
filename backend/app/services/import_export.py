from typing import Any

from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.schemas import (
    ClassCreate,
    EntityCreate,
    OntologyCreate,
    OntologyImportPayload,
    PropertyDefCreate,
    RelationCreate,
    RelationTypeCreate,
)
from app.repositories.models import OntologyModel, RelationTypeModel
from app.services import graph as graph_service
from app.services import metadata as metadata_service


def ontology_to_dict(ontology: OntologyModel) -> dict[str, Any]:
    return {
        "id": ontology.id,
        "project_id": ontology.project_id,
        "current_version_id": ontology.current_version_id,
        "name": ontology.name,
        "description": ontology.description,
        "status": ontology.status,
        "external_mappings": ontology.external_mappings,
        "created_at": ontology.created_at,
        "updated_at": ontology.updated_at,
    }


def relation_type_to_dict(relation_type: RelationTypeModel) -> dict[str, Any]:
    return {
        "id": relation_type.id,
        "ontology_id": relation_type.ontology_id,
        "name": relation_type.name,
        "description": relation_type.description,
        "aliases": relation_type.aliases,
        "parent_relation_type_id": relation_type.parent_relation_type_id,
        "source_class_id": relation_type.source_class_id,
        "target_class_id": relation_type.target_class_id,
        "inverse_name": relation_type.inverse_name,
        "normalized_type": relation_type.normalized_type,
        "external_mappings": relation_type.external_mappings,
        "created_at": relation_type.created_at,
        "updated_at": relation_type.updated_at,
    }


def export_ontology(session: Session, driver: Driver, ontology_id: str) -> dict[str, Any]:
    ontology = metadata_service.get_ontology_schema(session, ontology_id)
    entities = graph_service.list_entities(session, driver, ontology_id, class_id=None, limit=100)
    relations = graph_service.list_relations(
        session,
        driver,
        ontology_id,
        entity_id=None,
        relation_type_id=None,
        limit=100,
    )
    return {
        "ontology": ontology_to_dict(ontology),
        "classes": [graph_service.class_schema_to_dict(class_) for class_ in ontology.classes],
        "relation_types": [
            relation_type_to_dict(relation_type) for relation_type in ontology.relation_types
        ],
        "entities": entities,
        "relations": relations,
    }


def _map_value(mapping: dict[str, str], value: str | None) -> str | None:
    if value is None:
        return None
    return mapping.get(value, value)


def import_ontology(
    session: Session,
    driver: Driver,
    project_id: str,
    payload: OntologyImportPayload,
) -> dict[str, Any]:
    ontology = metadata_service.create_ontology(
        session,
        project_id,
        OntologyCreate(
            name=payload.ontology.name,
            description=payload.ontology.description,
            external_mappings=payload.ontology.external_mappings,
        ),
    )
    class_id_map: dict[str, str] = {}
    relation_type_id_map: dict[str, str] = {}
    entity_id_map: dict[str, str] = {}

    for item in payload.classes:
        created = metadata_service.create_class(
            session,
            ontology.id,
            ClassCreate(
                name=item["name"],
                description=item.get("description"),
                aliases=item.get("aliases", []),
                parent_class_ids=[class_id_map.get(id_, id_) for id_ in item.get("parent_class_ids", [])],
                external_mappings=item.get("external_mappings", {}),
            ),
        )
        if item.get("id"):
            class_id_map[item["id"]] = created.id
        for prop in item.get("properties", []):
            metadata_service.create_property(
                session,
                created.id,
                PropertyDefCreate(
                    name=prop["name"],
                    type=prop["type"],
                    description=prop.get("description"),
                    required=prop.get("required", False),
                    multi_valued=prop.get("multi_valued", False),
                    enum_values=prop.get("enum_values", []),
                    constraints=prop.get("constraints", {}),
                    external_mappings=prop.get("external_mappings", {}),
                ),
            )

    for item in payload.relation_types:
        created = metadata_service.create_relation_type(
            session,
            ontology.id,
            RelationTypeCreate(
                name=item["name"],
                description=item.get("description"),
                aliases=item.get("aliases", []),
                parent_relation_type_id=_map_value(
                    relation_type_id_map,
                    item.get("parent_relation_type_id"),
                ),
                source_class_id=class_id_map.get(item["source_class_id"], item["source_class_id"]),
                target_class_id=class_id_map.get(item["target_class_id"], item["target_class_id"]),
                inverse_name=item.get("inverse_name"),
                external_mappings=item.get("external_mappings", {}),
            ),
        )
        if item.get("id"):
            relation_type_id_map[item["id"]] = created.id

    for item in payload.entities:
        created = graph_service.create_entity(
            session,
            driver,
            ontology.id,
            EntityCreate(
                class_id=class_id_map.get(item["class_id"], item["class_id"]),
                name=item["name"],
                aliases=item.get("aliases", []),
                properties=item.get("properties", {}),
                ontology_version_id=item.get("ontology_version_id"),
            ),
        )
        if item.get("id"):
            entity_id_map[item["id"]] = created["id"]

    for item in payload.relations:
        graph_service.create_relation(
            session,
            driver,
            ontology.id,
            RelationCreate(
                relation_type_id=relation_type_id_map.get(
                    item["relation_type_id"],
                    item["relation_type_id"],
                ),
                source_entity_id=entity_id_map.get(
                    item["source_entity_id"],
                    item["source_entity_id"],
                ),
                target_entity_id=entity_id_map.get(
                    item["target_entity_id"],
                    item["target_entity_id"],
                ),
                properties=item.get("properties", {}),
                ontology_version_id=item.get("ontology_version_id"),
            ),
        )

    return export_ontology(session, driver, ontology.id)
