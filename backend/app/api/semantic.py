from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_context_cursor_codec,
    get_db_session,
    get_rdf_store,
    get_settings,
)
from app.api.schemas import (
    SemanticCanonicalModeRead,
    SemanticCanonicalProductWriteRequest,
    SemanticCanonicalProductWriteResponse,
    SemanticContextQueryRequest,
    SemanticContextQueryResponse,
    SemanticDatasetLoadRequest,
    SemanticDatasetLoadResponse,
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
    SemanticProjectionJobCreate,
    SemanticProjectionJobListResponse,
    SemanticProjectionJobRead,
    SemanticProjectionReconcileResponse,
    SemanticProjectionStatusResponse,
    SemanticReadModelEnvelope,
    SemanticResourceRead,
    SemanticScopeDiscoveryResponse,
    SemanticSparqlQueryRequest,
    SemanticSparqlQueryResponse,
)
from app.core.config import Settings
from app.repositories.rdf_store import RdfStoreError, RdfStoreRepository
from app.repositories.models import (
    OntologyModel,
    SemanticGraphRegistryModel,
    SemanticGraphSetModel,
)
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency
from app.services.semantic import SemanticService, SemanticServiceError
from app.services.semantic_context_query import (
    SemanticContextQueryError,
    SemanticContextQueryService,
)
from app.services.semantic_context_cursor import ContextCursorCodec
from app.services.authorized_scope_discovery import (
    AuthorizedScopeDiscoveryService,
    ScopeDiscoveryError,
)
from app.services.semantic_query_scope import (
    SemanticQueryScopeError,
    SemanticQueryScopeResolver,
)
from app.services.scoped_sparql_query import ScopedSparqlQueryError, ScopedSparqlQueryService
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
from app.services.semantic_retrieval import (
    SemanticResourceRetrievalService,
    SemanticRetrievalCoordinator,
    SemanticRetrievalProjectionService,
)
from app.services.embedding import EmbeddingClient
from app.services.semantic_access import (
    SemanticAccessDependencyError,
    SemanticAccessResolver,
    SemanticAccessView,
    project_id_for_graph_iri,
    project_id_for_graph_set,
)
from app.services.semantic_canonical_write import (
    CanonicalSemanticWriteError,
    CanonicalSemanticWriteService,
)
from app.services.semantic_command_compiler import (
    CommandCompilerError,
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
) -> SemanticService:
    return SemanticService(
        session=session,
        rdf_store=rdf_store,
        settings=settings,
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


def _scope_resolver(session: Session) -> SemanticReadScopeResolver:
    return SemanticReadScopeResolver(session)


def _access_view(
    session: Session,
    principal: AuthPrincipal | None,
    project_id: str | None,
) -> SemanticAccessView:
    """R3.0-004 shared authorization view; DB failures fail closed as 503."""
    try:
        return SemanticAccessResolver(session).resolve(principal, project_id)
    except SemanticAccessDependencyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "dependency_error", "message": str(exc)},
        ) from exc


def _read_model_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
    access_view: SemanticAccessView | None = None,
) -> SemanticReadModelService:

    return SemanticReadModelService(
        rdf_store=rdf_store,
        scope_resolver=_scope_resolver(session),
        access_view=access_view,
        session=session,
        retrieval_service=SemanticResourceRetrievalService(session, settings),
    )


def _export_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
    access_view: SemanticAccessView | None = None,
) -> SemanticExportService:
    return SemanticExportService(
        rdf_store=rdf_store,
        scope_resolver=_scope_resolver(session),
        settings=settings,
        access_view=access_view,
    )


def _projection_job_service(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
) -> SemanticProjectionJobService:
    writers: dict[str, object] = {
        "search": SemanticSearchProjectionService(rdf_store, FakeSearchWriter()),
        "vector": SemanticRetrievalProjectionService(
            session, rdf_store, EmbeddingClient(settings), settings
        ),
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


def _semantic_query_http_exception(exc: RuntimeError) -> HTTPException:
    return HTTPException(
        status_code=getattr(exc, "status_code", 400),
        detail={
            "code": getattr(exc, "code", "invalid_query"),
            "message": str(exc),
        },
    )


@router.get("/scopes:discover", response_model=SemanticScopeDiscoveryResponse)
def discover_semantic_scopes(
    query: Annotated[str | None, Query()] = None,
    queryable: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query()] = 50,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SemanticScopeDiscoveryResponse:
    try:
        result = AuthorizedScopeDiscoveryService(session, settings).discover(
            authorized_project_id=principal.project_id,
            query=query,
            queryable=queryable,
            cursor=cursor,
            limit=limit,
        )
        return SemanticScopeDiscoveryResponse(**result)
    except ScopeDiscoveryError as exc:
        raise _semantic_query_http_exception(exc) from exc


@router.post("/context:query", response_model=SemanticContextQueryResponse)
def query_semantic_context(
    request: SemanticContextQueryRequest,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
    cursor_codec: ContextCursorCodec = Depends(get_context_cursor_codec),
) -> SemanticContextQueryResponse:
    try:
        resolver = SemanticQueryScopeResolver(session, settings)
        access_view = _access_view(session, principal, request.project_id)
        result = SemanticContextQueryService(
            session,
            rdf_store,
            resolver,
            cursor_codec=cursor_codec,
            access_view=access_view,
        ).query_multi(
            project_id=request.project_id,
            scope_mode=request.scope_mode,
            ontology_ids=request.ontology_ids,
            queries=request.queries if request.queries is not None else [request.query],
            resource_types=request.resource_types,
            assertion_types=request.assertion_types,
            semantic_roles=request.semantic_roles,
            search_mode=request.search_mode,
            depth=request.depth,
            limit=request.limit,
            context_limit=request.context_limit,
            context_detail=request.context_detail,
            principal=principal,
            match_cursor=request.match_cursor,
            context_cursor=request.context_cursor,
        )
        return SemanticContextQueryResponse(**result)
    except (SemanticContextQueryError, SemanticQueryScopeError, RdfStoreError) as exc:
        raise _semantic_query_http_exception(exc) from exc


@router.post("/sparql:query", response_model=SemanticSparqlQueryResponse)
def query_sparql(
    request: SemanticSparqlQueryRequest,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticSparqlQueryResponse:
    try:
        access_view = _access_view(session, principal, request.project_id)
        result = ScopedSparqlQueryService(
            SemanticQueryScopeResolver(session, settings),
            rdf_store,
            settings,
            access_view=access_view,
        ).query(
            project_id=request.project_id,
            scope_mode=request.scope_mode,
            ontology_ids=request.ontology_ids,
            query=request.query,
            timeout_seconds=request.timeout_seconds,
            result_limit=request.result_limit,
        )
        return SemanticSparqlQueryResponse(**result)
    except (ScopedSparqlQueryError, SemanticQueryScopeError, RdfStoreError) as exc:
        raise _semantic_query_http_exception(exc) from exc


@router.post("/edits", response_model=SemanticEditResponse)
def create_semantic_edit(
    request: SemanticEditRequest,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticEditResponse:
    try:
        result = _service(session, rdf_store, settings).apply_edit(
            request.format,
            request.content,
            request.target_graph_iri,
            principal.actor,
            request.reason,
            request.warning_state,
        )
        return SemanticEditResponse(**result)
    except (SemanticServiceError, RdfStoreError) as exc:
        raise _semantic_http_exception(exc) from exc


@router.get("/edits/audits", response_model=list[SemanticEditAuditRead])
def list_semantic_edit_audits(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> list[SemanticEditAuditRead]:
    result = _service(session, rdf_store, settings).list_edit_audits(limit)
    return [SemanticEditAuditRead(**item) for item in result]


@router.patch(
    "/graphs/{graph_iri:path}/editability", response_model=SemanticGraphEditabilityResponse
)
def update_graph_editability(
    graph_iri: str,
    request: SemanticGraphEditabilityRequest,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphEditabilityResponse:
    try:
        result = _service(session, rdf_store, settings).set_graph_editability(
            graph_iri,
            request.editable,
            principal.actor,
            request.reason,
        )
        return SemanticGraphEditabilityResponse(**result)
    except SemanticServiceError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc


@router.get("/export")
def export_dataset(
    request: Request,
    format: Annotated[str, Query(pattern="^(trig|json-ld|turtle)$")] = "trig",
    graph_iri: Annotated[list[str] | None, Query()] = None,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    if "include_evidence" in request.query_params:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsupported_parameter",
                "message": "include_evidence is no longer supported",
            },
        )
    try:
        access_view = _access_view(session, principal, principal.project_id)
        requested = list(graph_iri) if graph_iri else None
        effective: list[str] | None = requested
        if principal.project_id is not None and not principal.is_org_admin:
            # R3.0-004 row 6: a project key only exports its own Project's
            # ontology graphs; unauthorized graph_iris are silently omitted.
            project_graphs = set(
                session.scalars(select(SemanticGraphRegistryModel.graph_iri))
            )
            project_graphs = {
                iri
                for iri in project_graphs
                if project_id_for_graph_iri(session, iri) == principal.project_id
            }
            effective = (
                sorted(project_graphs) if requested is None
                else [iri for iri in requested if iri in project_graphs]
            )
        if access_view.requires_filtering and effective:
            content = _filtered_export(rdf_store, access_view, format, effective)
        else:
            content = _service(session, rdf_store, settings).export_dataset(
                format, effective
            )
    except RdfStoreError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    media_type = {
        "trig": "application/trig",
        "json-ld": "application/ld+json",
        "turtle": "text/turtle",
    }[format]
    return Response(content=content, media_type=media_type)


def _filtered_export(
    rdf_store: RdfStoreRepository,
    access_view: SemanticAccessView,
    format: str,
    graph_iris: list[str],
) -> str:
    """Serialize the authorized quads only (R3.0-004 quad-level filtering)."""
    from rdflib import Dataset, Graph

    from app.repositories.rdf_store import RdfFormat

    dataset = Dataset()
    for iri in graph_iris:
        raw = rdf_store.get_graph(iri, RdfFormat.TRIG.value)
        if raw:
            dataset.parse(data=raw, format=RdfFormat.TRIG.value)
    access_view.filter_quads(dataset)
    if format == "trig":
        return dataset.serialize(format="trig")
    if format == "json-ld":
        return dataset.serialize(format="json-ld", indent=2)
    merged = Graph()
    for graph in dataset.graphs():
        if str(graph.identifier) == "urn:x-rdflib:default":
            continue
        for triple in graph:
            merged.add(triple)
    return merged.serialize(format="turtle")


@router.get("/graphs", response_model=SemanticGraphRegistryListResponse)
def list_graph_registry(
    category: Annotated[str | None, Query()] = None,
    owner_type: Annotated[str | None, Query()] = None,
    owner_id: Annotated[str | None, Query()] = None,
    include_revisions: Annotated[bool, Query()] = True,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
    principal: AuthPrincipal = Depends(principal_dependency),
) -> SemanticGraphRegistryListResponse:
    registry = _registry_service(session, settings)
    records = registry.list_graphs(category=category, owner_type=owner_type, owner_id=owner_id)
    if principal.project_id is not None:
        ontology_ids = set(
            session.scalars(
                select(OntologyModel.id).where(OntologyModel.project_id == principal.project_id)
            )
        )
        records = [
            record
            for record in records
            if record.semantic_owner_type == "ontology" and record.semantic_owner_id in ontology_ids
        ]
    graphs: list[SemanticGraphRegistryRead] = []
    for record in records:
        graphs.append(_registry_read(registry, record, include_revisions, rdf_store))
    summary = registry.status_summary(records if principal.project_id is not None else None)
    return SemanticGraphRegistryListResponse(graphs=graphs, summary=summary)


@router.post("/graphs", response_model=SemanticGraphRegistryRead)
def register_graph(
    request: SemanticGraphRegistryCreate,
    principal: AuthPrincipal = Depends(principal_dependency),
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
            created_by=principal.actor,
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
    principal: AuthPrincipal = Depends(principal_dependency),
) -> SemanticGraphSetListResponse:
    service = _graph_set_service(session, settings)
    sets = service.list_graph_sets(scope_type=scope_type, scope_id=scope_id, status=status)
    if principal.project_id is not None:
        ontology_ids = set(
            session.scalars(
                select(OntologyModel.id).where(OntologyModel.project_id == principal.project_id)
            )
        )
        sets = [
            graph_set
            for graph_set in sets
            if graph_set.scope_type == "ontology" and graph_set.scope_id in ontology_ids
        ]
    return SemanticGraphSetListResponse(
        graph_sets=[SemanticGraphSetRead(**service.describe(graph_set.id)) for graph_set in sets]
    )


@router.post("/graph-sets", response_model=SemanticGraphSetRead)
def create_graph_set(
    request: SemanticGraphSetCreate,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphSetRead:
    service = SemanticGraphSetService(session, settings, rdf_store)
    try:
        graph_set = service.create_graph_set(
            name=request.name,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            members=[member.model_dump() for member in request.members],
            created_by=principal.actor,
            metadata=request.metadata,
            supersedes=request.supersedes,
        )
    except GraphSetError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=getattr(exc, "detail", str(exc))) from exc
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
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticGraphSetRead:
    service = SemanticGraphSetService(session, settings, rdf_store)
    try:
        graph_set = service.update_membership(
            graph_set_id,
            [member.model_dump() for member in request.members],
        )
    except GraphSetError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=getattr(exc, "detail", str(exc))) from exc
    return SemanticGraphSetRead(**service.describe(graph_set.id))


@router.post("/ontologies/{ontology_id}/retrieval:rebuild")
def rebuild_ontology_retrieval(
    ontology_id: str,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Retry one Ontology's disposable retrieval projection for an org admin."""
    ontology = session.get(OntologyModel, ontology_id)
    if ontology is None or (
        principal.project_id is not None and ontology.project_id != principal.project_id
    ):
        raise HTTPException(status_code=404, detail="Ontology not found")
    if not principal.is_org_admin:
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})
    return _rebuild_retrieval_for_ontology_id(session, rdf_store, settings, ontology_id)


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
    principal: AuthPrincipal = Depends(principal_dependency),
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
            created_by=principal.actor,
            metadata=request.metadata,
        )
    except MigrationError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
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
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
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
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
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
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
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
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
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
        raise HTTPException(status_code=getattr(exc, "status_code", 409), detail=str(exc)) from exc
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
        raise HTTPException(status_code=getattr(exc, "status_code", 409), detail=str(exc)) from exc
    return SemanticMigrationRollbackResponse(**result)


@router.post(
    "/canonical-writes:compile-and-apply",
    response_model=SemanticCanonicalProductWriteResponse,
)
def compile_and_apply_product_command(
    request: SemanticCanonicalProductWriteRequest,
    principal: AuthPrincipal = Depends(principal_dependency),
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
            actor=principal.actor,
            reason=request.reason,
            commit=True,
        )
    except CanonicalSemanticWriteError as exc:
        session.rollback()
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    except CommandCompilerError as exc:
        session.rollback()
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
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
    search_mode: Annotated[str, Query(pattern="^(hybrid|lexical)$")] = "hybrid",
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticReadModelEnvelope:
    access_view = _access_view(
        session, principal, project_id_for_graph_set(session, graph_set_id)
    )
    service = _read_model_service(session, rdf_store, settings, access_view=access_view)
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
            search_mode=search_mode,
        )
    except (ReadModelError, ReadScopeError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return SemanticReadModelEnvelope(**envelope)


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------


@router.get("/resources/{resource_iri:path}", response_model=SemanticResourceRead)
def read_resource(
    resource_iri: str,
    graph_set_id: Annotated[str, Query()],
    include: Annotated[str, Query()] = "asserted",
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticResourceRead:
    access_view = _access_view(
        session, principal, project_id_for_graph_set(session, graph_set_id)
    )
    service = _read_model_service(session, rdf_store, settings, access_view=access_view)
    # Mapping/metric resources use the same exact-IRI read contract as the
    # original generic resources.  Keep these specialized templates behind
    # the resource endpoint so REST callers do not need to know which
    # projection family owns a resource before requesting it.
    for model_name in (
        "operation-detail",
        "table-mapping-detail",
        "join-mapping-detail",
        "enum-meaning-detail",
        "metric-detail",
        "entity-detail",
        "class-detail",
        "property-list",
        "relation-type-list",
    ):
        envelope = service.read_model(
            graph_set_id=graph_set_id,
            model_name=model_name,
            include=include,
            entity_iri=resource_iri,
        )
        for item in envelope["items"]:
            if item["iri"] == resource_iri:
                return SemanticResourceRead(
                    iri=resource_iri,
                    label=item.get("label"),
                    graph_set_id=graph_set_id,
                    source_signature=envelope["source_signature"],
                    assertion_kind=item["assertion_kind"],
                    source_graph_iri=item["source_graph_iri"],
                    properties=item.get("detail_fields", {}),
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
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticReadModelEnvelope:
    access_view = _access_view(
        session, principal, project_id_for_graph_set(session, graph_set_id)
    )
    service = _read_model_service(session, rdf_store, settings, access_view=access_view)
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
    request: Request,
    format: Annotated[str, Query()] = "trig",
    include: Annotated[str, Query()] = "asserted",
    include_policy: Annotated[bool, Query()] = False,
    include_metadata: Annotated[bool, Query()] = False,
    allow_stale_derived: Annotated[bool, Query()] = False,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    if "include_evidence" in request.query_params:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unsupported_parameter",
                "message": "include_evidence is no longer supported",
            },
        )
    access_view = _access_view(
        session, principal, project_id_for_graph_set(session, graph_set_id)
    )
    service = _export_service(session, rdf_store, settings, access_view=access_view)
    try:
        payload, _warnings = service.export(
            graph_set_id=graph_set_id,
            format=format,
            include=include,
            include_policy=include_policy,
            include_metadata=include_metadata,
            allow_stale_derived=allow_stale_derived,
        )
    except (ExportError, ReadScopeError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
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
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobRead:
    if request.graph_set_id != graph_set_id:
        raise HTTPException(status_code=400, detail="graph_set_id in body must match path")
    service = _projection_job_service(session, rdf_store, settings)
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
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return _projection_job_read(job)


@router.get("/projection-jobs", response_model=SemanticProjectionJobListResponse)
def list_projection_jobs(
    graph_set_id: Annotated[str | None, Query()] = None,
    projection_kind: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobListResponse:
    service = _projection_job_service(session, rdf_store, settings)
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
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobRead:
    service = _projection_job_service(session, rdf_store, settings)
    try:
        job = service.get_job(job_id)
    except ProjectionJobError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 404), detail=str(exc)) from exc
    return _projection_job_read(job)


@router.post("/projection-jobs/{job_id}:run", response_model=SemanticProjectionJobRead)
def run_projection_job(
    job_id: str,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionJobRead:
    service = _projection_job_service(session, rdf_store, settings)
    try:
        job = service.run_job(job_id)
    except ProjectionJobError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return _projection_job_read(job)


@router.post("/projections:reconcile", response_model=SemanticProjectionReconcileResponse)
def reconcile_projections(
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionReconcileResponse:
    service = _projection_job_service(session, rdf_store, settings)
    report = service.reconcile()
    return SemanticProjectionReconcileResponse(**report)


@router.get("/projections/status", response_model=SemanticProjectionStatusResponse)
def projection_status(
    graph_set_id: Annotated[str | None, Query()] = None,
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> SemanticProjectionStatusResponse:
    service = _projection_job_service(session, rdf_store, settings)
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


def _graph_set_ontology_id(session: Session, graph_set_id: str) -> str:
    graph_set = session.get(SemanticGraphSetModel, graph_set_id)
    if graph_set is None or graph_set.scope_type != "ontology" or not graph_set.scope_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden_scope", "message": "Ontology-scoped Graph Set required"},
        )
    return graph_set.scope_id


def _rebuild_retrieval_for_ontology_id(
    session: Session,
    rdf_store: RdfStoreRepository,
    settings: Settings,
    ontology_id: str | None,
) -> dict[str, Any]:
    if not ontology_id:
        return {"write_applied": True, "status": "stale", "warning": "retrieval_index_unscoped"}
    return SemanticRetrievalCoordinator(session, rdf_store, settings).rebuild_ontology(ontology_id)


def _retrieval_headers(retrieval_index: dict[str, Any]) -> dict[str, str]:
    headers = {
        "X-Semantic-Write-Applied": "true",
        "X-Retrieval-Index-Status": str(retrieval_index.get("status", "stale")),
    }
    if retrieval_index.get("job_id"):
        headers["X-Retrieval-Index-Job-Id"] = str(retrieval_index["job_id"])
    return headers


def _set_retrieval_headers(response: Response | None, retrieval_index: dict[str, Any]) -> None:
    if response is not None:
        response.headers.update(_retrieval_headers(retrieval_index))
