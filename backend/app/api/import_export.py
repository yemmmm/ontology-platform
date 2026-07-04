from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_embedding_client, get_neo4j_driver, get_settings
from app.api.schemas import (
    OntologyExportRead,
    OntologyImportPayload,
    SemanticCompactProjectionRead,
    SemanticNamespaceRead,
    SemanticProjectionParseRequest,
)
from app.core.config import Settings
from app.services import import_export as service
from app.services import semantic_export
from app.services.embedding import EmbeddingClient

router = APIRouter(tags=["import-export"])


@router.get("/ontologies/{ontology_id}/export", response_model=OntologyExportRead)
def export_ontology(
    ontology_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
):
    return service.export_ontology(session, driver, ontology_id)


@router.get("/semantic/namespaces", response_model=SemanticNamespaceRead)
def semantic_namespaces(settings: Settings = Depends(get_settings)) -> SemanticNamespaceRead:
    return SemanticNamespaceRead(
        context=semantic_export.jsonld_context(settings),
        iri_patterns=semantic_export.semantic_iri_manifest(settings),
    )


@router.get("/ontologies/{ontology_id}/semantic-export")
def export_ontology_semantic(
    ontology_id: str,
    format: Annotated[str, Query(pattern="^(trig|turtle|json-ld)$")] = "trig",
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        content = semantic_export.export_ontology_semantic(
            session,
            driver,
            settings,
            ontology_id,
            format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=content, media_type=_semantic_media_type(format))


@router.get("/ontologies/{ontology_id}/semantic-shapes")
def export_ontology_semantic_shapes(
    ontology_id: str,
    format: Annotated[str, Query(pattern="^(trig|turtle|json-ld)$")] = "turtle",
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        content = semantic_export.export_ontology_shapes(
            session,
            driver,
            settings,
            ontology_id,
            format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=content, media_type=_semantic_media_type(format))


@router.post("/semantic/projections:parse", response_model=SemanticCompactProjectionRead)
def parse_semantic_projection(
    request: SemanticProjectionParseRequest,
) -> SemanticCompactProjectionRead:
    result = semantic_export.compact_projection_from_semantic_export(
        request.content,
        request.format,
    )
    return SemanticCompactProjectionRead(**result)


@router.post(
    "/projects/{project_id}/ontologies/import",
    response_model=OntologyExportRead,
    status_code=status.HTTP_201_CREATED,
)
def import_ontology(
    project_id: str,
    payload: OntologyImportPayload,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
):
    return service.import_ontology(session, driver, project_id, payload, embedding_client)


def _semantic_media_type(format: str) -> str:
    return {
        "trig": "application/trig",
        "turtle": "text/turtle",
        "json-ld": "application/ld+json",
    }[format]
