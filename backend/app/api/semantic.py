from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver, get_rdf_store, get_settings
from app.api.schemas import (
    SemanticDatasetLoadRequest,
    SemanticDatasetLoadResponse,
    SemanticEditRequest,
    SemanticEditResponse,
    SemanticGraphEditabilityRequest,
    SemanticGraphEditabilityResponse,
    SemanticProjectionRequest,
    SemanticProjectionResponse,
    SemanticReasoningRunRequest,
    SemanticReasoningRunResponse,
    SemanticSparqlQueryRequest,
    SemanticSparqlQueryResponse,
    SemanticValidationRunRequest,
    SemanticValidationRunResponse,
)
from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreError, RdfStoreRepository
from app.services.owl_reasoner import CommandOwlReasonerRunner
from app.services.semantic import SemanticService, SemanticServiceError
from app.services.semantic_projection import SemanticProjectionService

router = APIRouter(prefix="/semantic", tags=["semantic"])


def _service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
    driver: Driver | None = None,
) -> SemanticService:
    return SemanticService(
        session=session,
        rdf_store=rdf_store,
        settings=settings,
        reasoner=CommandOwlReasonerRunner(settings.semantic_reasoner_command),
        projection=SemanticProjectionService(rdf_store, driver),
    )


@router.post("/datasets:load", response_model=SemanticDatasetLoadResponse)
def load_dataset(
    request: SemanticDatasetLoadRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticDatasetLoadResponse:
    try:
        result = _service(session, rdf_store, settings).load_dataset(
            request.content,
            request.format,
            request.base_iri,
        )
        return SemanticDatasetLoadResponse(**result.__dict__)
    except (SemanticServiceError, RdfStoreError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc


@router.post("/sparql:query", response_model=SemanticSparqlQueryResponse)
def query_sparql(
    request: SemanticSparqlQueryRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticSparqlQueryResponse:
    try:
        result = _service(session, rdf_store, settings).query_sparql(
            request.query,
            request.timeout_seconds,
            request.result_limit,
        )
        return SemanticSparqlQueryResponse(**result.__dict__)
    except (SemanticServiceError, RdfStoreError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc


@router.post("/validation-runs", response_model=SemanticValidationRunResponse)
def create_validation_run(
    request: SemanticValidationRunRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticValidationRunResponse:
    result = _service(session, rdf_store, settings).run_validation(
        request.data_graph_iris,
        request.shape_graph_iris,
        request.inference,
    )
    return SemanticValidationRunResponse(**result)


@router.post("/reasoning-runs", response_model=SemanticReasoningRunResponse)
def create_reasoning_run(
    request: SemanticReasoningRunRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticReasoningRunResponse:
    result = _service(session, rdf_store, settings).run_reasoning(
        request.source_graph_iris,
        request.tasks,
        request.persist_result_graph,
    )
    return SemanticReasoningRunResponse(**result)


@router.post("/edits", response_model=SemanticEditResponse)
def create_semantic_edit(
    request: SemanticEditRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticEditResponse:
    try:
        result = _service(session, rdf_store, settings).apply_edit(
            request.format,
            request.content,
            request.target_graph_iri,
            request.validate_edit,
            request.shape_graph_iris,
        )
        return SemanticEditResponse(**result)
    except (SemanticServiceError, RdfStoreError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc


@router.patch("/graphs/{graph_iri:path}/editability", response_model=SemanticGraphEditabilityResponse)
def update_graph_editability(
    graph_iri: str,
    request: SemanticGraphEditabilityRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphEditabilityResponse:
    try:
        result = _service(session, rdf_store, settings).set_graph_editability(
            graph_iri,
            request.editable,
            request.actor,
            request.reason,
        )
        return SemanticGraphEditabilityResponse(**result)
    except SemanticServiceError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc


@router.get("/export")
def export_dataset(
    format: Annotated[str, Query(pattern="^(trig|json-ld|turtle)$")] = "trig",
    graph_iri: Annotated[list[str] | None, Query()] = None,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        content = _service(session, rdf_store, settings).export_dataset(format, graph_iri)
    except RdfStoreError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    media_type = {
        "trig": "application/trig",
        "json-ld": "application/ld+json",
        "turtle": "text/turtle",
    }[format]
    return Response(content=content, media_type=media_type)


@router.post("/projection-jobs", response_model=SemanticProjectionResponse)
def create_projection_job(
    request: SemanticProjectionRequest,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionResponse:
    result = _service(session, rdf_store, settings, driver).rebuild_projection(
        request.source_graph_iris,
        request.reasoning_result_graph_iri,
    )
    return SemanticProjectionResponse(**result)
