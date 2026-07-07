from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver, get_rdf_store, get_settings
from app.api.schemas import (
    ReasoningRunListResponse,
    RuleRunListResponse,
    SemanticCanonicalModeRead,
    SemanticCanonicalProductWriteRequest,
    SemanticCanonicalProductWriteResponse,
    SemanticDatasetLoadRequest,
    SemanticDatasetLoadResponse,
    SemanticDerivedResultReconcileResponse,
    SemanticEditAuditRead,
    SemanticEditRequest,
    SemanticEditResponse,
    SemanticExportRequest,
    SemanticGraphEditabilityRequest,
    SemanticGraphEditabilityResponse,
    SemanticGraphGcRequest,
    SemanticGraphGcResponse,
    SemanticGraphRegistryCreate,
    SemanticGraphRegistryListResponse,
    SemanticGraphRegistryRead,
    SemanticGraphSetConstructRunRequest,
    SemanticGraphSetCreate,
    SemanticGraphSetListResponse,
    SemanticGraphSetMembershipUpdate,
    SemanticGraphSetRead,
    SemanticGraphSetReasoningRunRequest,
    SemanticGraphSetRuleRunRequest,
    SemanticGraphSetValidationRunRequest,
    SemanticGovernanceStatusResponse,
    SemanticMigrationBatchRunResponse,
    SemanticMigrationCreateRequest,
    SemanticMigrationCutoverResponse,
    SemanticMigrationParityCheckResponse,
    SemanticMigrationPreflightRequest,
    SemanticMigrationPreflightResponse,
    SemanticMigrationRollbackResponse,
    SemanticMigrationRunListResponse,
    SemanticMigrationRunRead,
    SemanticMissingEvidenceSummary,
    SemanticProjectionJobCreate,
    SemanticProjectionJobListResponse,
    SemanticProjectionJobRead,
    SemanticProjectionReconcileResponse,
    SemanticProjectionRequest,
    SemanticProjectionResponse,
    SemanticProjectionStatusResponse,
    SemanticReadModelEnvelope,
    SemanticReasoningRunRead,
    SemanticReasoningRunRequest,
    SemanticReasoningRunResponse,
    SemanticResourceRead,
    SemanticRuleDefinitionCreate,
    SemanticRuleDefinitionListResponse,
    SemanticRuleDefinitionRead,
    SemanticRuleDefinitionUpdate,
    SemanticRuleRunRead,
    SemanticSparqlQueryRequest,
    SemanticSparqlQueryResponse,
    SemanticValidationRunRead,
    SemanticValidationRunRequest,
    SemanticValidationRunResponse,
    ValidationRunListResponse,
)
from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreError, RdfStoreRepository
from app.services.owl_reasoner import CommandOwlReasonerRunner
from app.services.semantic import SemanticService, SemanticServiceError
from app.services.semantic_graph_set_export import (
    ExportError,
    SemanticExportService,
)
from app.services.semantic_graph_gc import GraphGcError, SemanticGraphGcService
from app.services.semantic_graph_registry import (
    GraphRegistryError,
    SemanticGraphRegistryService,
)
from app.services.semantic_graph_set import GraphSetError, SemanticGraphSetService
from app.services.semantic_derived_state import SemanticDerivedStateService
from app.services.semantic_missing_evidence import SemanticMissingEvidenceService
from app.services.semantic_neo4j_projection import Neo4jSemanticProjectionService
from app.services.semantic_projection import SemanticProjectionService
from app.services.semantic_projection_job import (
    ProjectionJobError,
    SemanticProjectionJobService,
)
from app.services.semantic_read_model import (
    ReadModelError,
    SemanticReadModelService,
)
from app.services.semantic_read_scope import (
    ReadScopeError,
    SemanticReadScopeResolver,
)
from app.services.semantic_search_projection import (
    FakeSearchWriter,
    SemanticSearchProjectionService,
)
from app.services.semantic_vector_projection import (
    FakeVectorWriter,
    SemanticVectorProjectionService,
)
from app.services.semantic_visibility import SemanticVisibilityPolicy
from app.services.semantic_reasoning import SemanticReasoningService
from app.services.semantic_rule_definition import (
    RuleDefinitionError,
    RuleDefinitionNotFound,
    SemanticRuleDefinitionService,
)
from app.services.semantic_rule_execution import (
    RuleExecutionError,
    SemanticRuleExecutionService,
)
from app.services.semantic_validation import SemanticValidationService
from app.services.semantic_canonical_write import (
    CanonicalSemanticWriteError,
    CanonicalSemanticWriteService,
)
from app.services.semantic_command_compiler import (
    CommandCompilerError,
    compile_command,
)
from app.services.semantic_migration import (
    MigrationError,
    SemanticMigrationService,
)

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


def _validation_service(
    session: Session, rdf_store: RdfStoreRepository, settings: Settings
) -> SemanticValidationService:
    return SemanticValidationService(session, rdf_store, settings)


def _reasoning_service(
    session: Session, rdf_store: RdfStoreRepository, settings: Settings
) -> SemanticReasoningService:
    return SemanticReasoningService(
        session=session,
        rdf_store=rdf_store,
        settings=settings,
        reasoner=CommandOwlReasonerRunner(settings.semantic_reasoner_command),
    )


def _rule_definition_service(
    session: Session, settings: Settings
) -> SemanticRuleDefinitionService:
    return SemanticRuleDefinitionService(session, settings)


def _rule_execution_service(
    session: Session, rdf_store: RdfStoreRepository, settings: Settings
) -> SemanticRuleExecutionService:
    return SemanticRuleExecutionService(session, rdf_store, settings)


def _missing_evidence_service(rdf_store: RdfStoreRepository) -> SemanticMissingEvidenceService:
    return SemanticMissingEvidenceService(rdf_store)


def _scope_resolver(session: Session) -> SemanticReadScopeResolver:
    return SemanticReadScopeResolver(session)


def _visibility_policy(settings: Settings) -> SemanticVisibilityPolicy:
    return SemanticVisibilityPolicy(
        graph_labels=getattr(settings, "semantic_graph_visibility_labels", {}) or {}
    )


def _read_model_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
) -> SemanticReadModelService:
    from app.services.semantic_shape_endpoint_service import (
        SemanticShapeEndpointService,
    )

    return SemanticReadModelService(
        rdf_store=rdf_store,
        scope_resolver=_scope_resolver(session),
        visibility_policy=_visibility_policy(settings),
        shape_endpoint=SemanticShapeEndpointService(session, rdf_store, settings),
        session=session,
    )


def _export_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
) -> SemanticExportService:
    return SemanticExportService(
        rdf_store=rdf_store,
        scope_resolver=_scope_resolver(session),
        settings=settings,
        visibility_policy=_visibility_policy(settings),
    )


def _projection_job_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    driver: Driver | None,
    settings: Settings,
) -> SemanticProjectionJobService:
    writers: dict[str, object] = {
        "neo4j": Neo4jSemanticProjectionService(rdf_store, driver),
        "search": SemanticSearchProjectionService(rdf_store, FakeSearchWriter()),
        "vector": SemanticVectorProjectionService(rdf_store, FakeVectorWriter()),
    }
    return SemanticProjectionJobService(
        session=session,
        writers=writers,
        scope_resolver_builder=_scope_resolver,
    )


def _projection_job_read(job) -> SemanticProjectionJobRead:
    return SemanticProjectionJobRead(
        id=job.id,
        graph_set_id=job.graph_set_id,
        projection_kind=job.projection_kind,
        projection_version=job.projection_version,
        projection_scope=job.projection_scope,
        source_signature=job.source_signature,
        input_graph_revisions=job.input_graph_revisions or {},
        input_derived_pointers=job.input_derived_pointers or {},
        target_store=job.target_store,
        target_partition=job.target_partition,
        status=job.status,
        node_count=job.node_count,
        relationship_count=job.relationship_count,
        document_count=job.document_count,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        metadata=job.job_metadata or {},
    )


def _run_list_summary(items: list[dict], total: int) -> dict[str, int]:
    stale_count = sum(1 for item in items if (item.get("staleness") or {}).get("stale"))
    superseded_count = sum(
        1
        for item in items
        if item.get("status") == "superseded"
        or (item.get("derived_pointer") or {}).get("status") == "superseded"
    )
    return {
        "total": total,
        "stale_count": stale_count,
        "superseded_count": superseded_count,
    }


def _semantic_http_exception(exc: Exception) -> HTTPException:
    detail: object = str(exc)
    if hasattr(exc, "parse_message"):
        detail = {
            "message": f"RDF parse error: {getattr(exc, 'parse_message')}",
            "line": getattr(exc, "parse_line", None),
            "column": getattr(exc, "parse_column", None),
        }
    return HTTPException(status_code=getattr(exc, "status_code", 400), detail=detail)


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
        raise _semantic_http_exception(exc) from exc


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
        raise _semantic_http_exception(exc) from exc


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
        raise _semantic_http_exception(exc) from exc


@router.get("/validation-runs", response_model=ValidationRunListResponse)
def list_validation_runs(
    graph_set_id: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> ValidationRunListResponse:
    items, total = _validation_service(session, rdf_store, settings).list_validation_runs(
        limit=limit,
        offset=offset,
        graph_set_id=graph_set_id,
        kind=kind,
    )
    return ValidationRunListResponse(items=items, summary=_run_list_summary(items, total))


@router.get("/reasoning-runs", response_model=ReasoningRunListResponse)
def list_reasoning_runs(
    graph_set_id: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> ReasoningRunListResponse:
    items, total = _reasoning_service(session, rdf_store, settings).list_reasoning_runs(
        limit=limit,
        offset=offset,
        graph_set_id=graph_set_id,
        kind=kind,
    )
    return ReasoningRunListResponse(items=items, summary=_run_list_summary(items, total))


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
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphRegistryListResponse:
    registry = _registry_service(session, settings)
    records = registry.list_graphs(category=category, owner_type=owner_type, owner_id=owner_id)
    graphs: list[SemanticGraphRegistryRead] = []
    for record in records:
        graphs.append(_registry_read(registry, record, include_revisions, rdf_store))
    summary = registry.status_summary()
    return SemanticGraphRegistryListResponse(graphs=graphs, summary=summary)


@router.post("/graphs", response_model=SemanticGraphRegistryRead)
def register_graph(
    request: SemanticGraphRegistryCreate,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
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
    return _registry_read(registry, record, include_revisions=True, rdf_store=rdf_store)


@router.get("/graphs/{graph_iri:path}", response_model=SemanticGraphRegistryRead)
def get_graph_registry(
    graph_iri: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphRegistryRead:
    registry = _registry_service(session, settings)
    status = registry.graph_status(graph_iri)
    status["statement_count"] = _statement_count(rdf_store, graph_iri)
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
    result = _reasoning_service(session, rdf_store, settings).run_reasoning(
        source_graph_iris,
        request.tasks,
        request.persist_result_graph,
        graph_set_id=graph_set_id,
        engine_version=request.engine_version,
        shape_version=request.shape_version,
    )
    return SemanticReasoningRunResponse(**result)


@router.post(
    "/graph-sets/{graph_set_id}/validation-runs",
    response_model=SemanticValidationRunResponse,
)
def create_graph_set_validation_run(
    graph_set_id: str,
    request: SemanticGraphSetValidationRunRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticValidationRunResponse:
    graph_set_service = _graph_set_service(session, settings)
    try:
        description = graph_set_service.describe(graph_set_id)
    except GraphSetError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
    data_graph_iris = [
        member["graph_iri"]
        for member in description["members"]
        if member["role"] in {"asserted_data"}
    ]
    shape_graph_iris = list(request.shape_graph_iris) or [
        member["graph_iri"]
        for member in description["members"]
        if member["role"] == "shape"
    ]
    try:
        result = _validation_service(session, rdf_store, settings).run_validation(
            data_graph_iris=data_graph_iris,
            shape_graph_iris=shape_graph_iris,
            inference=request.inference,
            graph_set_id=graph_set_id,
            validation_scope=request.validation_scope,
            persist_report_graph=request.persist_report_graph,
            shape_version=request.shape_version,
            engine_version=request.engine_version,
            reasoning_result_graph_iri=request.reasoning_result_graph_iri,
            actor=request.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SemanticValidationRunResponse(
        run_id=result["run_id"],
        status=result["status"],
        conforms=result["conforms"],
        report_text=result["report_text"],
        summary=result["summary"],
        error=result["error"],
    )


@router.get("/validation-runs/{run_id}", response_model=SemanticValidationRunRead)
def get_validation_run(
    run_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticValidationRunRead:
    try:
        result = _validation_service(session, rdf_store, settings).get_validation_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SemanticValidationRunRead(**result)


@router.get("/reasoning-runs/{run_id}", response_model=SemanticReasoningRunRead)
def get_reasoning_run(
    run_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticReasoningRunRead:
    try:
        result = _reasoning_service(session, rdf_store, settings).get_reasoning_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SemanticReasoningRunRead(**result)


@router.get("/rule-definitions", response_model=SemanticRuleDefinitionListResponse)
def list_rule_definitions(
    status: Annotated[str | None, Query()] = None,
    language: Annotated[str | None, Query()] = None,
    rule_iri: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticRuleDefinitionListResponse:
    service = _rule_definition_service(session, settings)
    rules = service.list_rules(
        status=status, language=language, rule_iri=rule_iri, limit=limit
    )
    return SemanticRuleDefinitionListResponse(
        rules=[_rule_definition_read(rule) for rule in rules]
    )


@router.post("/rule-definitions", response_model=SemanticRuleDefinitionRead)
def create_rule_definition(
    request: SemanticRuleDefinitionCreate,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticRuleDefinitionRead:
    service = _rule_definition_service(session, settings)
    try:
        rule = service.create_rule(
            rule_iri=request.rule_iri,
            name=request.name,
            language=request.language,
            body=request.body,
            input_roles=request.input_roles,
            output_kind=request.output_kind,
            uses_inferred_facts=request.uses_inferred_facts,
            requires_review=request.requires_review,
            priority=request.priority,
            safety_profile=request.safety_profile,
            status=request.status,
            created_by=request.created_by,
            metadata=request.metadata,
        )
    except RuleDefinitionError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return _rule_definition_read(rule)


@router.get("/rule-definitions/{rule_id}", response_model=SemanticRuleDefinitionRead)
def get_rule_definition(
    rule_id: str,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticRuleDefinitionRead:
    service = _rule_definition_service(session, settings)
    try:
        rule = service.get_rule(rule_id)
    except RuleDefinitionNotFound as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
    return _rule_definition_read(rule)


@router.patch("/rule-definitions/{rule_id}", response_model=SemanticRuleDefinitionRead)
def update_rule_definition(
    rule_id: str,
    request: SemanticRuleDefinitionUpdate,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticRuleDefinitionRead:
    service = _rule_definition_service(session, settings)
    try:
        if request.status is not None:
            rule = service.update_status(rule_id, request.status)
        else:
            rule = service.get_rule(rule_id)
        if request.name is not None or request.priority is not None or request.metadata is not None:
            if request.name is not None:
                rule.name = request.name
            if request.priority is not None:
                rule.priority = request.priority
            if request.metadata is not None:
                rule.rule_metadata = {**(rule.rule_metadata or {}), **request.metadata}
            session.commit()
            session.refresh(rule)
    except RuleDefinitionNotFound as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
    except RuleDefinitionError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return _rule_definition_read(rule)


@router.post(
    "/graph-sets/{graph_set_id}/construct-runs",
    response_model=SemanticRuleRunRead,
)
def create_graph_set_construct_run(
    graph_set_id: str,
    request: SemanticGraphSetConstructRunRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticRuleRunRead:
    service = _rule_execution_service(session, rdf_store, settings)
    try:
        result = service.execute_construct_template(
            graph_set_id=graph_set_id,
            template=request.template,
            rule_definition_id=request.rule_definition_id,
            rule_version=request.rule_version,
            promote_pointer=request.promote_pointer,
            actor=request.actor,
            engine_version=request.engine_version,
        )
    except RuleExecutionError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return SemanticRuleRunRead(**_rule_run_response(result))


@router.post(
    "/graph-sets/{graph_set_id}/rule-runs",
    response_model=SemanticRuleRunRead,
)
def create_graph_set_rule_run(
    graph_set_id: str,
    request: SemanticGraphSetRuleRunRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticRuleRunRead:
    service = _rule_execution_service(session, rdf_store, settings)
    try:
        if request.rule_definition_ids or (
            not request.rule_definition_id and not request.rule_iri
        ):
            result = service.execute_rule_group(
                graph_set_id=graph_set_id,
                rule_definition_ids=request.rule_definition_ids,
                promote_pointer=request.promote_pointer,
                actor=request.actor,
                engine_version=request.engine_version,
            )
        else:
            result = service.execute_rule(
                graph_set_id=graph_set_id,
                rule_definition_id=request.rule_definition_id,
                rule_iri=request.rule_iri,
                promote_pointer=request.promote_pointer,
                actor=request.actor,
                engine_version=request.engine_version,
            )
    except RuleExecutionError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return SemanticRuleRunRead(**_rule_run_response(result))


@router.get("/rule-runs", response_model=RuleRunListResponse)
def list_rule_runs(
    graph_set_id: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> RuleRunListResponse:
    items, total = _rule_execution_service(session, rdf_store, settings).list_rule_runs(
        limit=limit,
        offset=offset,
        graph_set_id=graph_set_id,
        kind=kind,
    )
    return RuleRunListResponse(items=items, summary=_run_list_summary(items, total))


@router.get("/rule-runs/{run_id}", response_model=SemanticRuleRunRead)
def get_rule_run(
    run_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticRuleRunRead:
    service = _rule_execution_service(session, rdf_store, settings)
    try:
        result = service.get_rule_run(run_id)
    except RuleExecutionError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
    return SemanticRuleRunRead(**_rule_run_response(result))


@router.get(
    "/graph-sets/{graph_set_id}/missing-evidence",
    response_model=SemanticMissingEvidenceSummary,
)
def get_graph_set_missing_evidence(
    graph_set_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMissingEvidenceSummary:
    graph_set_service = _graph_set_service(session, settings)
    try:
        description = graph_set_service.describe(graph_set_id)
    except GraphSetError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
    service = _missing_evidence_service(rdf_store)
    graph_iris = [
        member["graph_iri"]
        for member in description["members"]
        if member["role"] in {"asserted_ontology", "asserted_data"}
    ]
    dependencies = service.collect_from_graphs(graph_iris)
    summary = service.summarize_dependencies(dependencies)
    from app.services.semantic_missing_evidence import derived_warning_message

    warning = derived_warning_message(dependencies)
    return SemanticMissingEvidenceSummary(
        graph_set_id=graph_set_id,
        dependencies=dependencies,
        summary=summary,
        warning=warning,
    )


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


# ----------------------------------------------------------------------------
# Phase 7 — canonical RDF dataset migration runs, batches, and parity reports
# ----------------------------------------------------------------------------


def _migration_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
) -> SemanticMigrationService:
    return SemanticMigrationService(session, rdf_store, settings)


def _canonical_write_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
) -> CanonicalSemanticWriteService:
    return CanonicalSemanticWriteService(session, rdf_store, settings)


@router.post("/migrations:preflight", response_model=SemanticMigrationPreflightResponse)
def preflight_migration(
    request: SemanticMigrationPreflightRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMigrationPreflightResponse:
    service = _migration_service(session, rdf_store, settings)
    summary = service.preflight(
        scope_type=request.scope_type,
        scope_id=request.scope_id,
        target_graph_set_id=request.target_graph_set_id,
    )
    return SemanticMigrationPreflightResponse(**summary)


@router.post("/migrations", response_model=SemanticMigrationRunRead, status_code=201)
def create_migration_run(
    request: SemanticMigrationCreateRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMigrationRunRead:
    service = _migration_service(session, rdf_store, settings)
    try:
        run = service.create_run(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            mode=request.mode,
            target_graph_set_id=request.target_graph_set_id,
            batch_size=request.batch_size,
            created_by=request.created_by,
            metadata=request.metadata,
        )
    except MigrationError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    return SemanticMigrationRunRead(**run)


@router.get("/migrations", response_model=SemanticMigrationRunListResponse)
def list_migration_runs(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMigrationRunListResponse:
    service = _migration_service(session, rdf_store, settings)
    return SemanticMigrationRunListResponse(**service.list_runs(limit=limit))


@router.get("/migrations/{run_id}", response_model=SemanticMigrationRunRead)
def get_migration_run(
    run_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMigrationRunRead:
    service = _migration_service(session, rdf_store, settings)
    try:
        run = service.get_run(run_id)
    except MigrationError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 404), detail=str(exc)
        ) from exc
    return SemanticMigrationRunRead(**run)


@router.post(
    "/migrations/{run_id}:run-next-batch",
    response_model=SemanticMigrationBatchRunResponse,
)
def run_next_migration_batch(
    run_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMigrationBatchRunResponse:
    service = _migration_service(session, rdf_store, settings)
    try:
        result = service.run_next_batch(run_id)
    except MigrationError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    payload = {**result}
    batch = payload.pop("batch", None)
    return SemanticMigrationBatchRunResponse(
        **payload,
        batch=batch,
    )


@router.post(
    "/migrations/{run_id}:rerun-failed-batches",
    response_model=SemanticMigrationRunRead,
)
def rerun_failed_migration_batches(
    run_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMigrationRunRead:
    service = _migration_service(session, rdf_store, settings)
    try:
        service.rerun_failed_batches(run_id)
        run = service.get_run(run_id)
    except MigrationError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    return SemanticMigrationRunRead(**run)


@router.post(
    "/migrations/{run_id}:parity-check",
    response_model=SemanticMigrationParityCheckResponse,
)
def run_migration_parity_check(
    run_id: str,
    check_name: Annotated[str | None, Query()] = None,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMigrationParityCheckResponse:
    service = _migration_service(session, rdf_store, settings)
    try:
        result = service.run_parity_check(run_id, check_name=check_name)
    except MigrationError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    return SemanticMigrationParityCheckResponse(**result)


@router.post(
    "/migrations/{run_id}:cutover",
    response_model=SemanticMigrationCutoverResponse,
)
def cutover_migration_run(
    run_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMigrationCutoverResponse:
    service = _migration_service(session, rdf_store, settings)
    try:
        result = service.cutover(run_id)
    except MigrationError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from exc
    return SemanticMigrationCutoverResponse(**result)


@router.post(
    "/migrations/{run_id}:rollback",
    response_model=SemanticMigrationRollbackResponse,
)
def rollback_migration_run(
    run_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticMigrationRollbackResponse:
    service = _migration_service(session, rdf_store, settings)
    try:
        result = service.rollback(run_id)
    except MigrationError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from exc
    return SemanticMigrationRollbackResponse(**result)


@router.post(
    "/canonical-writes:compile-and-apply",
    response_model=SemanticCanonicalProductWriteResponse,
)
def compile_and_apply_product_command(
    request: SemanticCanonicalProductWriteRequest,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticCanonicalProductWriteResponse:
    service = _canonical_write_service(session, rdf_store, settings)
    try:
        result = service.apply_command(
            request.command_kind,
            request.payload,
            graph_set_id=request.graph_set_id,
            actor=request.actor,
            reason=request.reason,
            validate=request.validate_edit,
            shape_graph_iris=request.shape_graph_iris,
        )
    except CanonicalSemanticWriteError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    except CommandCompilerError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    return SemanticCanonicalProductWriteResponse(**result)


@router.get("/canonical-mode", response_model=SemanticCanonicalModeRead)
def get_canonical_mode(
    settings: Settings = Depends(get_settings),
) -> SemanticCanonicalModeRead:
    return SemanticCanonicalModeRead(
        canonical_store=settings.semantic_canonical_store,
        product_write_mode=settings.semantic_product_write_mode,
        read_mode=settings.semantic_read_mode,
        legacy_write_blocked=settings.semantic_legacy_write_blocked,
        scope_type=None,
        scope_id=None,
        notes=[
            "Modes are resolved per scope by the migration orchestrator. "
            "These settings reflect the current global defaults.",
        ],
    )


# ----------------------------------------------------------------------------
# Phase 6 — graph-derived read models, exports, projection jobs/manifests
# ----------------------------------------------------------------------------


@router.get(
    "/graph-sets/{graph_set_id}/read-models/{model_name}",
    response_model=SemanticReadModelEnvelope,
)
def read_model(
    graph_set_id: str,
    model_name: str,
    include: Annotated[str, Query()] = "asserted",
    allow_stale_derived: Annotated[bool, Query()] = True,
    field_set: Annotated[str, Query()] = "summary",
    limit: Annotated[int | None, Query(ge=1, le=2000)] = None,
    entity: Annotated[str | None, Query()] = None,
    class_iri: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    target: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticReadModelEnvelope:
    service = _read_model_service(session, rdf_store, settings)
    try:
        envelope = service.read_model(
            graph_set_id=graph_set_id,
            model_name=model_name,
            include=include,
            allow_stale_derived=allow_stale_derived,
            limit=limit,
            field_set=field_set,
            entity_iri=entity,
            class_iri=class_iri,
            kind=kind,
            target=target,
            q=q,
        )
    except (ReadModelError, ReadScopeError) as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    return SemanticReadModelEnvelope(**envelope)


# ----------------------------------------------------------------------------
# Stage 2 — per-class SHACL form guidance (merged from generated + custom)
# ----------------------------------------------------------------------------


@router.get("/graph-sets/{graph_set_id}/shapes/classes/{class_iri:path}")
def read_class_shape_guidance(
    graph_set_id: str,
    class_iri: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.services.semantic_shape_endpoint_service import (
        GraphSetNotFound,
        OntologyGraphMissing,
        SemanticShapeEndpointService,
        ShapeEndpointError,
    )

    service = SemanticShapeEndpointService(session, rdf_store, settings)
    try:
        return service.read_merged_guidance(
            graph_set_id=graph_set_id,
            class_iri=class_iri,
        )
    except GraphSetNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OntologyGraphMissing as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ShapeEndpointError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc


@router.get("/resources/{resource_iri:path}", response_model=SemanticResourceRead)
def read_resource(
    resource_iri: str,
    graph_set_id: Annotated[str, Query()],
    include: Annotated[str, Query()] = "asserted",
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticResourceRead:
    service = _read_model_service(session, rdf_store, settings)
    envelope = service.read_model(
        graph_set_id=graph_set_id,
        model_name="entity-detail",
        include=include,
    )
    for item in envelope["items"]:
        if item["iri"] == resource_iri:
            return SemanticResourceRead(
                iri=resource_iri,
                label=item.get("label"),
                graph_set_id=graph_set_id,
                source_signature=envelope["source_signature"],
                assertion_kind=item["assertion_kind"],
                evidence_status=item["evidence_status"],
                source_graph_iri=item["source_graph_iri"],
                properties={},
                derived_state=envelope["derived_state"],
                warnings=envelope["warnings"],
            )
    raise HTTPException(status_code=404, detail=f"Resource not found: {resource_iri}")


@router.get("/statements", response_model=SemanticReadModelEnvelope)
def list_statements(
    graph_set_id: Annotated[str, Query()],
    include: Annotated[str, Query()] = "asserted",
    allow_stale_derived: Annotated[bool, Query()] = True,
    limit: Annotated[int | None, Query(ge=1, le=5000)] = None,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticReadModelEnvelope:
    service = _read_model_service(session, rdf_store, settings)
    envelope = service.read_model(
        graph_set_id=graph_set_id,
        model_name="statement-list",
        include=include,
        allow_stale_derived=allow_stale_derived,
        limit=limit,
    )
    return SemanticReadModelEnvelope(**envelope)


@router.get("/graph-sets/{graph_set_id}/export")
def export_graph_set(
    graph_set_id: str,
    format: Annotated[str, Query()] = "trig",
    include: Annotated[str, Query()] = "asserted",
    include_evidence: Annotated[bool, Query()] = False,
    include_shapes: Annotated[bool, Query()] = False,
    include_policy: Annotated[bool, Query()] = False,
    include_metadata: Annotated[bool, Query()] = False,
    allow_stale_derived: Annotated[bool, Query()] = False,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    service = _export_service(session, rdf_store, settings)
    try:
        payload, _warnings = service.export(
            graph_set_id=graph_set_id,
            format=format,
            include=include,
            include_evidence=include_evidence,
            include_shapes=include_shapes,
            include_policy=include_policy,
            include_metadata=include_metadata,
            allow_stale_derived=allow_stale_derived,
        )
    except (ExportError, ReadScopeError) as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    media_type = {
        "trig": "application/trig",
        "json-ld": "application/ld+json",
        "turtle": "text/turtle",
    }[format]
    return Response(content=payload, media_type=media_type)


@router.post(
    "/graph-sets/{graph_set_id}/projection-jobs",
    response_model=SemanticProjectionJobRead,
    status_code=201,
)
def create_projection_job_for_set(
    graph_set_id: str,
    request: SemanticProjectionJobCreate,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobRead:
    if request.graph_set_id != graph_set_id:
        raise HTTPException(
            status_code=400, detail="graph_set_id in body must match path"
        )
    service = _projection_job_service(session, rdf_store, driver, settings)
    try:
        job = service.create_job(
            graph_set_id=request.graph_set_id,
            projection_kind=request.projection_kind,
            projection_version=request.projection_version,
            include=request.include,
            mode=request.mode,
            target_partition=request.target_partition,
            allow_stale_derived=request.allow_stale_derived,
            metadata=request.metadata,
        )
    except ProjectionJobError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    return _projection_job_read(job)


@router.get("/projection-jobs", response_model=SemanticProjectionJobListResponse)
def list_projection_jobs(
    graph_set_id: Annotated[str | None, Query()] = None,
    projection_kind: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobListResponse:
    service = _projection_job_service(session, rdf_store, driver, settings)
    jobs = service.list_jobs(
        graph_set_id=graph_set_id,
        projection_kind=projection_kind,
        status=status,
    )
    items = [_projection_job_read(j) for j in jobs]
    return SemanticProjectionJobListResponse(items=items, total=len(items))


@router.get("/projection-jobs/{job_id}", response_model=SemanticProjectionJobRead)
def get_projection_job(
    job_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobRead:
    service = _projection_job_service(session, rdf_store, driver, settings)
    try:
        job = service.get_job(job_id)
    except ProjectionJobError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 404), detail=str(exc)
        ) from exc
    return _projection_job_read(job)


@router.post("/projection-jobs/{job_id}:run", response_model=SemanticProjectionJobRead)
def run_projection_job(
    job_id: str,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobRead:
    service = _projection_job_service(session, rdf_store, driver, settings)
    try:
        job = service.run_job(job_id)
    except ProjectionJobError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400), detail=str(exc)
        ) from exc
    return _projection_job_read(job)


@router.post(
    "/projections:reconcile", response_model=SemanticProjectionReconcileResponse
)
def reconcile_projections(
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionReconcileResponse:
    service = _projection_job_service(session, rdf_store, driver, settings)
    report = service.reconcile()
    return SemanticProjectionReconcileResponse(**report)


@router.get("/projections/status", response_model=SemanticProjectionStatusResponse)
def projection_status(
    graph_set_id: Annotated[str | None, Query()] = None,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionStatusResponse:
    service = _projection_job_service(session, rdf_store, driver, settings)
    status = service.status(graph_set_id=graph_set_id)
    return SemanticProjectionStatusResponse(**status)


def _registry_read(
    registry: SemanticGraphRegistryService,
    record,
    include_revisions: bool,
    rdf_store: RdfStoreRepository,
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
            statement_count=_statement_count(rdf_store, record.graph_iri),
            latest_audit_at=status.get("latest_audit_at"),
        )
    return SemanticGraphRegistryRead(
        graph_iri=record.graph_iri,
        category=record.category,
        registered=True,
        owner_type=record.semantic_owner_type,
        owner_id=record.semantic_owner_id,
        mutable_by_direct_edit=record.mutable_by_direct_edit,
        metadata=record.registry_metadata or {},
        statement_count=_statement_count(rdf_store, record.graph_iri),
        latest_audit_at=registry.latest_audit_at(record.graph_iri),
    )


def _statement_count(rdf_store: RdfStoreRepository, graph_iri: str) -> int | None:
    try:
        result = rdf_store.query_sparql(
            f"SELECT (COUNT(*) AS ?c) WHERE {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}",
            timeout_seconds=10,
            limit=1,
        )
    except Exception:
        return None
    payload = result.result
    if not isinstance(payload, dict):
        return None
    bindings = payload.get("results", {}).get("bindings", [])
    if not bindings:
        return 0
    value = bindings[0].get("c", {}).get("value")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rule_definition_read(rule) -> SemanticRuleDefinitionRead:
    return SemanticRuleDefinitionRead(
        id=rule.id,
        rule_iri=rule.rule_iri,
        name=rule.name,
        language=rule.language,
        version=rule.version,
        status=rule.status,
        body=rule.body,
        input_roles=list(rule.input_roles or []),
        output_kind=rule.output_kind,
        uses_inferred_facts=bool(rule.uses_inferred_facts),
        requires_review=bool(rule.requires_review),
        priority=int(rule.priority or 0),
        safety_profile=dict(rule.safety_profile or {}),
        created_by=rule.created_by,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        metadata=dict(rule.rule_metadata or {}),
    )


def _rule_run_response(result: dict) -> dict:
    """Normalise a rule-run service result for the SemanticRuleRunRead schema."""
    response = dict(result)
    response.setdefault("statements", [])
    response.setdefault("bindings", [])
    response.setdefault("warnings", [])
    response.setdefault("missing_evidence_dependencies", {})
    response.setdefault("explanations", [])
    response.setdefault("audit_status", "system_accepted")
    response.setdefault("truncated", False)
    response.setdefault("generated_statement_count", 0)
    response.setdefault("engine_name", "rule")
    response["run_id"] = response.get("run_id", "")
    response["status"] = response.get("status", "pending")
    response["graph_set_id"] = response.get("graph_set_id", "")
    return response
