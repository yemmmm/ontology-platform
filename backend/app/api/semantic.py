from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver, get_rdf_store, get_settings
from app.api.schemas import (
    SemanticDatasetLoadRequest,
    SemanticDatasetLoadResponse,
    SemanticDerivedResultReconcileResponse,
    SemanticEditAuditRead,
    SemanticEditRequest,
    SemanticEditResponse,
    SemanticGraphEditabilityRequest,
    SemanticGraphEditabilityResponse,
    SemanticGraphGcRequest,
    SemanticGraphGcResponse,
    SemanticGraphRegistryCreate,
    SemanticGraphRegistryListResponse,
    SemanticGraphRegistryRead,
    SemanticGraphSetCreate,
    SemanticGraphSetListResponse,
    SemanticGraphSetMembershipUpdate,
    SemanticGraphSetRead,
    SemanticGraphSetReasoningRunRequest,
    SemanticGovernanceStatusResponse,
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
from app.services.semantic_graph_gc import GraphGcError, SemanticGraphGcService
from app.services.semantic_graph_registry import (
    GraphRegistryError,
    SemanticGraphRegistryService,
)
from app.services.semantic_graph_set import GraphSetError, SemanticGraphSetService
from app.services.semantic_derived_state import SemanticDerivedStateService
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


def _registry_service(session: Session, settings: Settings) -> SemanticGraphRegistryService:
    return SemanticGraphRegistryService(session, settings)


def _graph_set_service(session: Session, settings: Settings) -> SemanticGraphSetService:
    return SemanticGraphSetService(session, settings)


def _gc_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
    retention_days: int | None = None,
) -> SemanticGraphGcService:
    return SemanticGraphGcService(
        session=session,
        rdf_store=rdf_store,
        settings=settings,
        retention_days=retention_days if retention_days is not None else 7,
    )


def _derived_state_service(session: Session, settings: Settings) -> SemanticDerivedStateService:
    return SemanticDerivedStateService(session, settings)


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
        graph_set_id=request.graph_set_id,
        engine_version=request.engine_version,
        shape_version=request.shape_version,
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
            request.actor,
            request.reason,
            request.evidence_status,
            request.warning_state,
        )
        return SemanticEditResponse(**result)
    except (SemanticServiceError, RdfStoreError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc


@router.get("/edits/audits", response_model=list[SemanticEditAuditRead])
def list_semantic_edit_audits(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> list[SemanticEditAuditRead]:
    result = _service(session, rdf_store, settings).list_edit_audits(limit)
    return [SemanticEditAuditRead(**item) for item in result]


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


@router.get("/graphs", response_model=SemanticGraphRegistryListResponse)
def list_graph_registry(
    category: Annotated[str | None, Query()] = None,
    owner_type: Annotated[str | None, Query()] = None,
    owner_id: Annotated[str | None, Query()] = None,
    include_revisions: Annotated[bool, Query()] = True,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphRegistryListResponse:
    registry = _registry_service(session, settings)
    records = registry.list_graphs(category=category, owner_type=owner_type, owner_id=owner_id)
    graphs: list[SemanticGraphRegistryRead] = []
    for record in records:
        graphs.append(_registry_read(registry, record, include_revisions))
    summary = registry.status_summary()
    return SemanticGraphRegistryListResponse(graphs=graphs, summary=summary)


@router.post("/graphs", response_model=SemanticGraphRegistryRead)
def register_graph(
    request: SemanticGraphRegistryCreate,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphRegistryRead:
    registry = _registry_service(session, settings)
    try:
        record = registry.register_graph(
            graph_iri=request.graph_iri,
            category=request.category,
            owner_type=request.owner_type,
            owner_id=request.owner_id,
            created_by=request.created_by,
            mutable_by_direct_edit=request.mutable_by_direct_edit,
            metadata=request.metadata,
        )
    except GraphRegistryError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return _registry_read(registry, record, include_revisions=True)


@router.get("/graphs/{graph_iri:path}", response_model=SemanticGraphRegistryRead)
def get_graph_registry(
    graph_iri: str,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphRegistryRead:
    registry = _registry_service(session, settings)
    status = registry.graph_status(graph_iri)
    return SemanticGraphRegistryRead(**status)


@router.get("/graph-sets", response_model=SemanticGraphSetListResponse)
def list_graph_sets(
    scope_type: Annotated[str | None, Query()] = None,
    scope_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphSetListResponse:
    service = _graph_set_service(session, settings)
    sets = service.list_graph_sets(scope_type=scope_type, scope_id=scope_id, status=status)
    return SemanticGraphSetListResponse(
        graph_sets=[SemanticGraphSetRead(**service.describe(graph_set.id)) for graph_set in sets]
    )


@router.post("/graph-sets", response_model=SemanticGraphSetRead)
def create_graph_set(
    request: SemanticGraphSetCreate,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphSetRead:
    service = _graph_set_service(session, settings)
    try:
        graph_set = service.create_graph_set(
            name=request.name,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            members=[member.model_dump() for member in request.members],
            created_by=request.created_by,
            metadata=request.metadata,
            supersedes=request.supersedes,
        )
    except GraphSetError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return SemanticGraphSetRead(**service.describe(graph_set.id))


@router.get("/graph-sets/{graph_set_id}", response_model=SemanticGraphSetRead)
def get_graph_set(
    graph_set_id: str,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphSetRead:
    service = _graph_set_service(session, settings)
    try:
        description = service.describe(graph_set_id)
    except GraphSetError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
    return SemanticGraphSetRead(**description)


@router.put("/graph-sets/{graph_set_id}/members", response_model=SemanticGraphSetRead)
def update_graph_set_members(
    graph_set_id: str,
    request: SemanticGraphSetMembershipUpdate,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphSetRead:
    service = _graph_set_service(session, settings)
    try:
        graph_set = service.update_membership(
            graph_set_id,
            [member.model_dump() for member in request.members],
        )
    except GraphSetError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return SemanticGraphSetRead(**service.describe(graph_set.id))


@router.post(
    "/graph-sets/{graph_set_id}/reasoning-runs",
    response_model=SemanticReasoningRunResponse,
)
def create_graph_set_reasoning_run(
    graph_set_id: str,
    request: SemanticGraphSetReasoningRunRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticReasoningRunResponse:
    graph_set_service = _graph_set_service(session, settings)
    try:
        description = graph_set_service.describe(graph_set_id)
    except GraphSetError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
    source_graph_iris = [
        member["graph_iri"]
        for member in description["members"]
        if member["role"]
        in {"asserted_ontology", "asserted_data"}
    ]
    result = _service(session, rdf_store, settings).run_reasoning(
        source_graph_iris,
        request.tasks,
        request.persist_result_graph,
        graph_set_id=graph_set_id,
        engine_version=request.engine_version,
        shape_version=request.shape_version,
    )
    return SemanticReasoningRunResponse(**result)


@router.post(
    "/derived-results:reconcile",
    response_model=SemanticDerivedResultReconcileResponse,
)
def reconcile_derived_results(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticDerivedResultReconcileResponse:
    service = _derived_state_service(session, settings)
    summary = service.reconcile()
    return SemanticDerivedResultReconcileResponse(**summary)


@router.post("/derived-results:gc", response_model=SemanticGraphGcResponse)
def run_derived_results_gc(
    request: SemanticGraphGcRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphGcResponse:
    gc_service = _gc_service(session, rdf_store, settings, retention_days=request.retention_days)
    try:
        result = gc_service.execute(
            target_kind=request.target_kind,
            dry_run=request.dry_run,
        )
    except GraphGcError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return SemanticGraphGcResponse(**result)


@router.get("/status", response_model=SemanticGovernanceStatusResponse)
def get_governance_status(
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticGovernanceStatusResponse:
    service = _service(session, rdf_store, settings)
    summary = service.governance_status()
    return SemanticGovernanceStatusResponse(**summary)


def _registry_read(
    registry: SemanticGraphRegistryService,
    record,
    include_revisions: bool,
) -> SemanticGraphRegistryRead:
    if include_revisions:
        status = registry.graph_status(record.graph_iri)
        return SemanticGraphRegistryRead(
            graph_iri=record.graph_iri,
            category=record.category,
            registered=True,
            owner_type=record.semantic_owner_type,
            owner_id=record.semantic_owner_id,
            mutable_by_direct_edit=record.mutable_by_direct_edit,
            editable=status.get("editable"),
            editability_reason=status.get("editability_reason"),
            revision=status.get("revision"),
            content_hash=status.get("content_hash"),
            derived_pointers=status.get("derived_pointers") or [],
            metadata=record.registry_metadata or {},
        )
    return SemanticGraphRegistryRead(
        graph_iri=record.graph_iri,
        category=record.category,
        registered=True,
        owner_type=record.semantic_owner_type,
        owner_id=record.semantic_owner_id,
        mutable_by_direct_edit=record.mutable_by_direct_edit,
        metadata=record.registry_metadata or {},
    )
