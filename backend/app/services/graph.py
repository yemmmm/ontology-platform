from datetime import date, datetime
from typing import Any, Literal

from fastapi import HTTPException, status
from neo4j import Driver
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import EntityCreate, EntityUpdate, RelationCreate
from app.repositories import graph as graph_repo
from app.repositories.models import ClassModel, OntologyModel, PropertyDefModel, RelationTypeModel
from app.services.metadata import (
    bad_request,
    ensure_class_ids_belong_to_ontology,
    get_ontology,
    new_id,
    not_found,
)
from app.services.embedding import (
    EmbeddingClient,
    EmbeddingServiceError,
    create_entity_embedding,
    embedding_properties,
)

SearchMode = Literal["text", "vector", "hybrid"]


def graph_conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def embedding_unavailable(exc: EmbeddingServiceError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


def clamp_limit(limit: int, maximum: int = 100) -> int:
    return max(1, min(limit, maximum))


def clamp_depth(depth: int) -> int:
    return max(1, min(depth, 3))


def get_class_with_properties(session: Session, class_id: str) -> ClassModel:
    statement = (
        select(ClassModel)
        .where(ClassModel.id == class_id)
        .options(selectinload(ClassModel.properties))
    )
    class_ = session.scalars(statement).first()
    if class_ is None:
        raise not_found("Class")
    return class_


def list_classes_for_ontology(session: Session, ontology_id: str) -> dict[str, ClassModel]:
    classes = session.scalars(select(ClassModel).where(ClassModel.ontology_id == ontology_id))
    return {class_.id: class_ for class_ in classes}


def collect_effective_properties(
    class_: ClassModel,
    classes_by_id: dict[str, ClassModel],
    seen: set[str] | None = None,
) -> dict[str, PropertyDefModel]:
    seen = seen or set()
    if class_.id in seen:
        raise bad_request("Class inheritance cycle detected")
    seen.add(class_.id)

    properties: dict[str, PropertyDefModel] = {}
    for parent_id in class_.parent_class_ids:
        parent = classes_by_id.get(parent_id)
        if parent is None:
            raise bad_request(f"Parent class not found: {parent_id}")
        properties.update(collect_effective_properties(parent, classes_by_id, seen.copy()))

    for property_def in class_.properties:
        properties[property_def.name] = property_def
    return properties


def is_descendant_or_same(
    actual_class_id: str,
    expected_class_id: str,
    classes_by_id: dict[str, ClassModel],
    seen: set[str] | None = None,
) -> bool:
    if actual_class_id == expected_class_id:
        return True
    seen = seen or set()
    if actual_class_id in seen:
        return False
    seen.add(actual_class_id)
    actual = classes_by_id.get(actual_class_id)
    if actual is None:
        return False
    return any(
        is_descendant_or_same(parent_id, expected_class_id, classes_by_id, seen)
        for parent_id in actual.parent_class_ids
    )


def validate_property_value(property_def: PropertyDefModel, value: Any) -> None:
    if property_def.multi_valued:
        if not isinstance(value, list):
            raise bad_request(f"Property '{property_def.name}' must be a list")
        for item in value:
            validate_single_property_value(property_def, item)
        return
    validate_single_property_value(property_def, value)


def validate_single_property_value(property_def: PropertyDefModel, value: Any) -> None:
    match property_def.type:
        case "string":
            if not isinstance(value, str):
                raise bad_request(f"Property '{property_def.name}' must be a string")
        case "number":
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise bad_request(f"Property '{property_def.name}' must be a number")
        case "boolean":
            if not isinstance(value, bool):
                raise bad_request(f"Property '{property_def.name}' must be a boolean")
        case "date":
            if not isinstance(value, str):
                raise bad_request(f"Property '{property_def.name}' must be an ISO date string")
            try:
                datetime.fromisoformat(value)
            except ValueError:
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise bad_request(f"Property '{property_def.name}' must be an ISO date") from exc
        case "enum":
            if not isinstance(value, str):
                raise bad_request(f"Property '{property_def.name}' must be an enum string")
            if property_def.enum_values and value not in property_def.enum_values:
                raise bad_request(
                    f"Property '{property_def.name}' must be one of: "
                    f"{', '.join(property_def.enum_values)}"
                )
        case "reference":
            if not isinstance(value, str):
                raise bad_request(f"Property '{property_def.name}' must be an entity id string")
        case "json":
            return
        case _:
            raise bad_request(f"Unsupported property type: {property_def.type}")


def validate_entity_properties(
    class_: ClassModel,
    classes_by_id: dict[str, ClassModel],
    properties: dict[str, Any],
) -> None:
    effective_properties = collect_effective_properties(class_, classes_by_id)
    missing_required = [
        name
        for name, property_def in effective_properties.items()
        if property_def.required and name not in properties
    ]
    if missing_required:
        raise bad_request(f"Missing required properties: {', '.join(sorted(missing_required))}")

    unknown = sorted(set(properties) - set(effective_properties))
    if unknown:
        raise bad_request(f"Unknown properties for class '{class_.name}': {', '.join(unknown)}")

    for name, value in properties.items():
        validate_property_value(effective_properties[name], value)


def ensure_ontology_and_class(
    session: Session,
    ontology_id: str,
    class_id: str,
) -> tuple[OntologyModel, ClassModel, dict[str, ClassModel]]:
    ontology = get_ontology(session, ontology_id)
    class_ = get_class_with_properties(session, class_id)
    if class_.ontology_id != ontology_id:
        raise bad_request("Class must belong to the ontology")
    classes_by_id = list_classes_for_ontology(session, ontology_id)
    return ontology, class_, classes_by_id


def create_entity(
    session: Session,
    driver: Driver,
    ontology_id: str,
    payload: EntityCreate,
    embedding_client: EmbeddingClient,
) -> dict[str, Any]:
    ontology, class_, classes_by_id = ensure_ontology_and_class(session, ontology_id, payload.class_id)
    validate_entity_properties(class_, classes_by_id, payload.properties)
    values = {
        "id": new_id(),
        "project_id": ontology.project_id,
        "ontology_id": ontology.id,
        "ontology_version_id": payload.ontology_version_id or ontology.current_version_id,
        "class_id": class_.id,
        "class_label": class_.normalized_label,
        "name": payload.name,
        "aliases": payload.aliases,
        "properties": payload.properties,
    }
    try:
        values.update(embedding_properties(create_entity_embedding(embedding_client, values)))
    except EmbeddingServiceError as exc:
        raise embedding_unavailable(exc) from exc
    return graph_repo.create_entity_node(driver, class_.normalized_label, values)


def list_entities(
    session: Session,
    driver: Driver,
    ontology_id: str,
    class_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    ontology = get_ontology(session, ontology_id)
    if class_id is not None:
        class_ = get_class_with_properties(session, class_id)
        if class_.ontology_id != ontology_id:
            raise bad_request("Class must belong to the ontology")
    return graph_repo.list_entity_nodes(
        driver,
        ontology.project_id,
        ontology.id,
        class_id,
        clamp_limit(limit),
    )


def search_entities(
    session: Session,
    driver: Driver,
    ontology_id: str,
    query: str,
    class_id: str | None = None,
    limit: int = 20,
    mode: SearchMode = "text",
    embedding_client: EmbeddingClient | None = None,
) -> dict[str, Any]:
    ontology = get_ontology(session, ontology_id)
    return _search_entities(
        session,
        driver,
        query,
        class_id,
        limit,
        mode,
        embedding_client,
        ontology.project_id,
        ontology.id,
    )


def search_all_entities(
    session: Session,
    driver: Driver,
    query: str,
    class_id: str | None = None,
    ontology_id: str | None = None,
    limit: int = 20,
    mode: SearchMode = "hybrid",
    embedding_client: EmbeddingClient | None = None,
) -> dict[str, Any]:
    project_id = None
    if ontology_id is not None:
        ontology = get_ontology(session, ontology_id)
        project_id = ontology.project_id
    return _search_entities(
        session,
        driver,
        query,
        class_id,
        limit,
        mode,
        embedding_client,
        project_id,
        ontology_id,
    )


def _search_entities(
    session: Session,
    driver: Driver,
    query: str,
    class_id: str | None,
    limit: int,
    mode: SearchMode,
    embedding_client: EmbeddingClient | None,
    project_id: str | None,
    ontology_id: str | None,
) -> dict[str, Any]:
    if class_id is not None:
        class_ = get_class_with_properties(session, class_id)
        if ontology_id is not None and class_.ontology_id != ontology_id:
            raise bad_request("Class must belong to the ontology")
        if ontology_id is None:
            ontology_id = class_.ontology_id
            ontology = get_ontology(session, ontology_id)
            project_id = ontology.project_id
    bounded_limit = clamp_limit(limit)
    if mode == "text":
        results = graph_repo.search_entity_nodes(
            driver, project_id, ontology_id, query, class_id, bounded_limit
        )
    elif mode in {"vector", "hybrid"}:
        if not query.strip():
            raise bad_request("Query must not be empty for vector search")
        if embedding_client is None:
            raise embedding_unavailable(EmbeddingServiceError("Embedding client is unavailable"))
        try:
            vector = embedding_client.embed([query[:2000]])[0]
        except EmbeddingServiceError as exc:
            raise embedding_unavailable(exc) from exc
        candidate_limit = min(max(bounded_limit + 10, bounded_limit * 2), 200)
        vector_results = graph_repo.search_entity_vectors(
            driver,
            vector,
            project_id,
            ontology_id,
            class_id,
            candidate_limit,
            bounded_limit,
        )
        if mode == "vector":
            results = vector_results
        else:
            text_results = graph_repo.search_entity_nodes(
                driver, project_id, ontology_id, query, class_id, bounded_limit
            )
            results = _reciprocal_rank_fusion(text_results, vector_results, bounded_limit)
    else:
        raise bad_request(f"Unsupported search mode: {mode}")
    return {"results": results, "count": len(results)}


def _reciprocal_rank_fusion(
    text_results: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    limit: int,
    rank_constant: int = 60,
) -> list[dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}
    sources: dict[str, set[str]] = {}
    scores: dict[str, float] = {}
    for source, results in (("text", text_results), ("vector", vector_results)):
        for rank, entity in enumerate(results, start=1):
            entity_id = entity["id"]
            fused[entity_id] = entity
            sources.setdefault(entity_id, set()).add(source)
            scores[entity_id] = scores.get(entity_id, 0.0) + 1.0 / (rank_constant + rank)
    ranked_ids = sorted(scores, key=lambda entity_id: (-scores[entity_id], entity_id))[:limit]
    return [
        {
            **fused[entity_id],
            "score": scores[entity_id],
            "match_source": "hybrid" if len(sources[entity_id]) == 2 else next(iter(sources[entity_id])),
        }
        for entity_id in ranked_ids
    ]


def get_entity(
    session: Session,
    driver: Driver,
    ontology_id: str,
    entity_id: str,
) -> dict[str, Any]:
    ontology = get_ontology(session, ontology_id)
    entity = graph_repo.get_entity_node(driver, entity_id, ontology.project_id, ontology.id)
    if entity is None:
        raise not_found("Entity")
    return entity


def get_entity_with_relations(
    session: Session,
    driver: Driver,
    ontology_id: str,
    entity_id: str,
    include_relations: bool = True,
    relation_limit: int = 50,
) -> dict[str, Any]:
    entity = get_entity(session, driver, ontology_id, entity_id)
    if not include_relations:
        return {**entity, "outgoing": [], "incoming": []}
    outgoing = find_entity_relations(
        session,
        driver,
        ontology_id,
        entity_id,
        direction="outgoing",
        limit=relation_limit,
    )
    incoming = find_entity_relations(
        session,
        driver,
        ontology_id,
        entity_id,
        direction="incoming",
        limit=relation_limit,
    )
    return {**entity, "outgoing": outgoing, "incoming": incoming}


def update_entity(
    session: Session,
    driver: Driver,
    ontology_id: str,
    entity_id: str,
    payload: EntityUpdate,
    embedding_client: EmbeddingClient,
) -> dict[str, Any]:
    ontology = get_ontology(session, ontology_id)
    entity = graph_repo.get_entity_node(driver, entity_id, ontology.project_id, ontology.id)
    if entity is None:
        raise not_found("Entity")
    data = payload.model_dump(exclude_unset=True)
    if "properties" in data:
        class_ = get_class_with_properties(session, entity["class_id"])
        classes_by_id = list_classes_for_ontology(session, ontology_id)
        validate_entity_properties(class_, classes_by_id, data["properties"])
    if {"name", "aliases", "properties"}.intersection(data):
        embedding_entity = {
            **entity,
            **{key: value for key, value in data.items() if key in {"name", "aliases", "properties"}},
        }
        try:
            data.update(
                embedding_properties(create_entity_embedding(embedding_client, embedding_entity))
            )
        except EmbeddingServiceError as exc:
            raise embedding_unavailable(exc) from exc
    updated = graph_repo.update_entity_node(driver, entity_id, ontology.project_id, ontology.id, data)
    if updated is None:
        raise not_found("Entity")
    return updated


def delete_entity(
    session: Session,
    driver: Driver,
    ontology_id: str,
    entity_id: str,
) -> None:
    ontology = get_ontology(session, ontology_id)
    deleted = graph_repo.delete_entity_node(driver, entity_id, ontology.project_id, ontology.id)
    if not deleted:
        existing = graph_repo.get_entity_node(driver, entity_id, ontology.project_id, ontology.id)
        if existing is None:
            raise not_found("Entity")
        raise graph_conflict("Entity could not be deleted because it still has relations")


def get_relation_type_for_ontology(
    session: Session,
    ontology_id: str,
    relation_type_id: str,
) -> RelationTypeModel:
    relation_type = session.get(RelationTypeModel, relation_type_id)
    if relation_type is None:
        raise not_found("Relation type")
    if relation_type.ontology_id != ontology_id:
        raise bad_request("Relation type must belong to the ontology")
    return relation_type


def create_relation(
    session: Session,
    driver: Driver,
    ontology_id: str,
    payload: RelationCreate,
) -> dict[str, Any]:
    ontology = get_ontology(session, ontology_id)
    relation_type = get_relation_type_for_ontology(session, ontology_id, payload.relation_type_id)
    source = graph_repo.get_entity_node(
        driver,
        payload.source_entity_id,
        ontology.project_id,
        ontology.id,
    )
    target = graph_repo.get_entity_node(
        driver,
        payload.target_entity_id,
        ontology.project_id,
        ontology.id,
    )
    if source is None:
        raise not_found("Source entity")
    if target is None:
        raise not_found("Target entity")

    classes_by_id = list_classes_for_ontology(session, ontology_id)
    if not is_descendant_or_same(source["class_id"], relation_type.source_class_id, classes_by_id):
        raise bad_request("Source entity class is not compatible with relation type source class")
    if not is_descendant_or_same(target["class_id"], relation_type.target_class_id, classes_by_id):
        raise bad_request("Target entity class is not compatible with relation type target class")

    values = {
        "id": new_id(),
        "project_id": ontology.project_id,
        "ontology_id": ontology.id,
        "ontology_version_id": payload.ontology_version_id or ontology.current_version_id,
        "relation_type_id": relation_type.id,
        "relation_type": relation_type.normalized_type,
        "source_entity_id": payload.source_entity_id,
        "target_entity_id": payload.target_entity_id,
        "properties": payload.properties,
    }
    return graph_repo.create_relation_edge(driver, relation_type.normalized_type, values)


def delete_relation(
    session: Session,
    driver: Driver,
    ontology_id: str,
    relation_id: str,
) -> None:
    ontology = get_ontology(session, ontology_id)
    deleted = graph_repo.delete_relation_edge(
        driver,
        relation_id,
        ontology.project_id,
        ontology.id,
    )
    if not deleted:
        raise not_found("Relation")


def list_relations(
    session: Session,
    driver: Driver,
    ontology_id: str,
    entity_id: str | None,
    relation_type_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    ontology = get_ontology(session, ontology_id)
    if relation_type_id is not None:
        get_relation_type_for_ontology(session, ontology_id, relation_type_id)
    return graph_repo.list_relation_edges(
        driver,
        ontology.project_id,
        ontology.id,
        entity_id,
        relation_type_id,
        clamp_limit(limit),
    )


def find_entity_relations(
    session: Session,
    driver: Driver,
    ontology_id: str,
    entity_id: str,
    direction: str = "both",
    relation_type_ids: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if direction not in {"incoming", "outgoing", "both"}:
        raise bad_request("direction must be one of: incoming, outgoing, both")
    ontology = get_ontology(session, ontology_id)
    entity = graph_repo.get_entity_node(driver, entity_id, ontology.project_id, ontology.id)
    if entity is None:
        raise not_found("Entity")
    if relation_type_ids:
        for relation_type_id in relation_type_ids:
            get_relation_type_for_ontology(session, ontology_id, relation_type_id)
    return graph_repo.list_entity_relation_edges(
        driver,
        ontology.project_id,
        ontology.id,
        entity_id,
        direction,
        relation_type_ids or None,
        clamp_limit(limit),
    )


def find_related_entities(
    session: Session,
    driver: Driver,
    ontology_id: str,
    entity_id: str,
    depth: int = 1,
    direction: str = "both",
    relation_type_ids: list[str] | None = None,
    target_class_ids: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if direction not in {"incoming", "outgoing", "both"}:
        raise bad_request("direction must be one of: incoming, outgoing, both")
    ontology = get_ontology(session, ontology_id)
    entity = graph_repo.get_entity_node(driver, entity_id, ontology.project_id, ontology.id)
    if entity is None:
        raise not_found("Entity")
    if relation_type_ids:
        for relation_type_id in relation_type_ids:
            get_relation_type_for_ontology(session, ontology_id, relation_type_id)
    if target_class_ids:
        ensure_class_ids_belong_to_ontology(session, ontology_id, target_class_ids)
    return graph_repo.find_related_entity_nodes(
        driver,
        ontology.project_id,
        ontology.id,
        entity_id,
        clamp_depth(depth),
        direction,
        relation_type_ids or None,
        target_class_ids or None,
        clamp_limit(limit),
    )


def validate_entity_payload(
    session: Session,
    ontology_id: str,
    class_id: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    try:
        _ontology, class_, classes_by_id = ensure_ontology_and_class(session, ontology_id, class_id)
        validate_entity_properties(class_, classes_by_id, properties)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return {"valid": False, "errors": [detail]}
    return {"valid": True, "errors": []}


def class_schema_to_dict(class_: ClassModel) -> dict[str, Any]:
    return {
        "id": class_.id,
        "ontology_id": class_.ontology_id,
        "name": class_.name,
        "normalized_label": class_.normalized_label,
        "description": class_.description,
        "aliases": class_.aliases,
        "parent_class_ids": class_.parent_class_ids,
        "external_mappings": class_.external_mappings,
        "created_at": class_.created_at,
        "updated_at": class_.updated_at,
        "properties": [
            {
                "id": prop.id,
                "class_id": prop.class_id,
                "name": prop.name,
                "type": prop.type,
                "description": prop.description,
                "required": prop.required,
                "multi_valued": prop.multi_valued,
                "enum_values": prop.enum_values,
                "constraints": prop.constraints,
                "external_mappings": prop.external_mappings,
                "created_at": prop.created_at,
                "updated_at": prop.updated_at,
            }
            for prop in class_.properties
        ],
    }


def explain_entity(
    session: Session,
    driver: Driver,
    ontology_id: str,
    entity_id: str,
    depth: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    entity = get_entity(session, driver, ontology_id, entity_id)
    class_ = get_class_with_properties(session, entity["class_id"])
    direct_relations = find_entity_relations(
        session,
        driver,
        ontology_id,
        entity_id,
        direction="both",
        limit=limit,
    )
    related_entities = find_related_entities(
        session,
        driver,
        ontology_id,
        entity_id,
        depth=depth,
        direction="both",
        limit=limit,
    )
    explain_text = (
        f"{entity['name']} is a {class_.name} entity with "
        f"{len(direct_relations)} direct relation(s) and "
        f"{len(related_entities)} related entity result(s) within depth {clamp_depth(depth)}."
    )
    return {
        "entity": entity,
        "class_schema": class_schema_to_dict(class_),
        "direct_relations": direct_relations,
        "related_entities": related_entities,
        "explain_text": explain_text,
    }
