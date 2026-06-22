from fastapi import APIRouter, Depends, Query, Response, status
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_embedding_client, get_neo4j_driver
from app.api.schemas import (
    EntityCreate,
    EntityExplainRead,
    EntityRead,
    EntitySearchResult,
    EntityUpdate,
    EntityWithRelationsRead,
    RelatedEntityRead,
    RelationCreate,
    RelationRead,
    ValidationResult,
)
from app.services import graph as service
from app.services.embedding import EmbeddingClient

router = APIRouter(tags=["graph"])


@router.get("/entities/search", response_model=EntitySearchResult)
def search_all_entities(
    query: str,
    mode: str = Query(default="hybrid", pattern="^(text|vector|hybrid)$"),
    ontology_id: str | None = None,
    class_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
):
    return service.search_all_entities(
        session,
        driver,
        query,
        class_id,
        ontology_id,
        limit,
        mode,
        embedding_client,
    )


@router.get("/ontologies/{ontology_id}/entities", response_model=list[EntityRead])
def list_entities(
    ontology_id: str,
    class_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.list_entities(session, driver, ontology_id, class_id, limit)


@router.get("/ontologies/{ontology_id}/entities/search", response_model=EntitySearchResult)
def search_entities(
    ontology_id: str,
    query: str = "",
    mode: str = Query(default="text", pattern="^(text|vector|hybrid)$"),
    class_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
):
    return service.search_entities(
        session, driver, ontology_id, query, class_id, limit, mode, embedding_client
    )


@router.post(
    "/ontologies/{ontology_id}/entities",
    response_model=EntityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_entity(
    ontology_id: str,
    payload: EntityCreate,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
):
    return service.create_entity(session, driver, ontology_id, payload, embedding_client)


@router.get("/ontologies/{ontology_id}/entities/{entity_id}", response_model=EntityWithRelationsRead)
def get_entity(
    ontology_id: str,
    entity_id: str,
    include_relations: bool = True,
    relation_limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.get_entity_with_relations(
        session,
        driver,
        ontology_id,
        entity_id,
        include_relations,
        relation_limit,
    )


@router.post("/ontologies/{ontology_id}/entities/validate", response_model=ValidationResult)
def validate_entity(
    ontology_id: str,
    payload: EntityCreate,
    session: Session = Depends(get_db_session),
):
    return service.validate_entity_payload(session, ontology_id, payload.class_id, payload.properties)


@router.get(
    "/ontologies/{ontology_id}/entities/{entity_id}/related",
    response_model=list[RelatedEntityRead],
)
def find_related_entities(
    ontology_id: str,
    entity_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    direction: str = Query(default="both", pattern="^(incoming|outgoing|both)$"),
    relation_type_ids: list[str] | None = Query(default=None),
    target_class_ids: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.find_related_entities(
        session,
        driver,
        ontology_id,
        entity_id,
        depth,
        direction,
        relation_type_ids,
        target_class_ids,
        limit,
    )


@router.get(
    "/ontologies/{ontology_id}/entities/{entity_id}/explain",
    response_model=EntityExplainRead,
)
def explain_entity(
    ontology_id: str,
    entity_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.explain_entity(session, driver, ontology_id, entity_id, depth, limit)


@router.patch("/ontologies/{ontology_id}/entities/{entity_id}", response_model=EntityRead)
def update_entity(
    ontology_id: str,
    entity_id: str,
    payload: EntityUpdate,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
):
    return service.update_entity(
        session, driver, ontology_id, entity_id, payload, embedding_client
    )


@router.delete("/ontologies/{ontology_id}/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity(
    ontology_id: str,
    entity_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    service.delete_entity(session, driver, ontology_id, entity_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/ontologies/{ontology_id}/relations", response_model=list[RelationRead])
def list_relations(
    ontology_id: str,
    entity_id: str | None = None,
    relation_type_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.list_relations(session, driver, ontology_id, entity_id, relation_type_id, limit)


@router.post(
    "/ontologies/{ontology_id}/relations",
    response_model=RelationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_relation(
    ontology_id: str,
    payload: RelationCreate,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.create_relation(session, driver, ontology_id, payload)


@router.delete(
    "/ontologies/{ontology_id}/relations/{relation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_relation(
    ontology_id: str,
    relation_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    service.delete_relation(session, driver, ontology_id, relation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
