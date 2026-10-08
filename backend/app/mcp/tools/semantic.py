"""Direct semantic read/write MCP tools."""

from __future__ import annotations

from typing import Any, Literal


from mcp.server.fastmcp import FastMCP

from app.core.config import Settings
from app.mcp.runtime import (
    _run_tool,
    get_context_cursor_codec,
    runtime_actor,
    runtime_principal,
)
from app.repositories.rdf_store import RdfStoreRepository
from app.services.authorized_scope_discovery import AuthorizedScopeDiscoveryService
from app.services.semantic import SemanticService
from app.services.semantic_context_query import (
    SemanticContextQueryError,
    SemanticContextQueryService,
)
from app.services.semantic_graph_registry import SemanticGraphRegistryService
from app.services.semantic_derived_state import SemanticDerivedStateService
from app.services.semantic_ontology_export import SemanticExportService
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
from app.services.semantic_query_scope import SemanticQueryScopeResolver
from app.services.scoped_sparql_query import ScopedSparqlQueryService
from app.services.semantic_search_projection import (
    FakeSearchWriter,
    SemanticSearchProjectionService,
)
from app.services.semantic_retrieval import (
    SemanticRetrievalProjectionService,
    SemanticResourceRetrievalService,
)
from app.services.embedding import EmbeddingClient
from app.services.semantic_access import (
    SemanticAccessResolver,
    project_id_for_ontology,
)


def _rdf_store() -> RdfStoreRepository:
    return RdfStoreRepository(Settings().oxigraph_url)


def _semantic_service(session) -> SemanticService:
    settings = Settings()
    return SemanticService(
        session=session,
        rdf_store=RdfStoreRepository(settings.oxigraph_url),
        settings=settings,
    )


def _scope_resolver(session) -> SemanticQueryScopeResolver:
    return SemanticQueryScopeResolver(session, Settings())


def _context_query_service(session, project_id: str | None = None) -> SemanticContextQueryService:
    return SemanticContextQueryService(
        session,
        _rdf_store(),
        _scope_resolver(session),
        cursor_codec=get_context_cursor_codec(),
        access_view=SemanticAccessResolver(session).resolve(
            runtime_principal(), project_id
        ),
    )


def _normalize_mcp_queries(*, query: str | None, queries: list[str] | None) -> list[str]:
    """Apply the R1.2-004 ``query`` xor ``queries`` rule at the MCP boundary.

    The shared service still re-validates; this helper keeps the MCP error code
    aligned with the REST adapter for symmetric client feedback.
    """
    if query is not None and queries is not None:
        raise SemanticContextQueryError("Provide exactly one of 'queries' or 'query'")
    if queries is not None:
        return list(queries)
    if query is not None:
        return [query]
    raise SemanticContextQueryError("Provide exactly one of 'queries' or 'query'")


def _scoped_sparql_service(session, project_id: str | None = None) -> ScopedSparqlQueryService:
    settings = Settings()
    return ScopedSparqlQueryService(
        _scope_resolver(session),
        _rdf_store(),
        settings,
        access_view=SemanticAccessResolver(session).resolve(
            runtime_principal(), project_id
        ),
    )




def _derived_state_service(session) -> SemanticDerivedStateService:
    settings = Settings()
    return SemanticDerivedStateService(session, settings)


def _registry_service(session) -> SemanticGraphRegistryService:
    settings = Settings()
    return SemanticGraphRegistryService(session, settings)


def register_semantic(server: FastMCP) -> None:
    @server.tool()
    def discover_semantic_scopes(
        query: str | None = None,
        queryable: bool | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Discover authorized Project/Ontology query scopes and readiness."""
        return _run_tool(
            lambda session, _driver, _embedding_client: AuthorizedScopeDiscoveryService(
                session, Settings()
            ).discover(
                authorized_project_id=runtime_principal().project_id,
                query=query,
                queryable=queryable,
                cursor=cursor,
                limit=limit,
            )
        )

    @server.tool()
    def semantic_sparql_query(
        project_id: str,
        scope_mode: str,
        query: str,
        ontology_ids: list[str] | None = None,
        timeout_seconds: float | None = None,
        result_limit: int | None = None,
    ) -> dict[str, Any]:
        """Run scoped read-only SPARQL against current Ontology semantic state."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _scoped_sparql_service(
                session, project_id
            ).query(
                project_id=project_id,
                scope_mode=scope_mode,
                ontology_ids=ontology_ids or [],
                query=query,
                timeout_seconds=timeout_seconds,
                result_limit=result_limit,
            )
        )

    @server.tool()
    def query_semantic_context(
        project_id: str,
        scope_mode: str,
        query: str | None = None,
        queries: list[str] | None = None,
        ontology_ids: list[str] | None = None,
        resource_types: list[str] | None = None,
        assertion_types: list[str] | None = None,
        semantic_roles: list[str] | None = None,
        search_mode: str = "hybrid",
        depth: int = 1,
        limit: int = 20,
        context_limit: int = 100,
        context_detail: Literal["full", "compact"] = "compact",
        match_cursor: str | None = None,
        context_cursor: str | None = None,
    ) -> dict[str, Any]:
        """Recall structured semantic context from one Project's current Ontologies."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _context_query_service(
                session, project_id
            ).query_multi(
                project_id=project_id,
                scope_mode=scope_mode,
                ontology_ids=ontology_ids or [],
                queries=_normalize_mcp_queries(query=query, queries=queries),
                resource_types=resource_types,
                assertion_types=assertion_types,
                semantic_roles=semantic_roles,
                search_mode=search_mode,
                depth=depth,
                limit=limit,
                context_limit=context_limit,
                context_detail=context_detail,
                principal=runtime_principal(),
                match_cursor=match_cursor,
                context_cursor=context_cursor,
            )
        )

    @server.tool()
    def submit_semantic_edit(
        format: str,
        content: str,
        ontology_id: str,
        actor: str | None = None,
        reason: str | None = None,
        warning_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit a governed RDF/SPARQL Update semantic edit with audit metadata."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _semantic_service(session).apply_edit(
                format=format,
                content=content,
                target_graph_iri=SemanticReadScopeResolver(session).resolve(ontology_id).model_graph_iris[0],
                actor=runtime_actor(),
                reason=reason,
                warning_state=warning_state or {},
            )
        )

    @server.tool()
    def list_semantic_edit_audits(limit: int = 50) -> dict[str, Any]:
        """List recent governed semantic edit audit records."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _semantic_service(session).list_edit_audits(
                limit
            )
        )



    @server.tool()
    def get_semantic_governance_status() -> dict[str, Any]:
        """Return a governance status summary: graph counts, editability, derived staleness."""
        return _run_tool(
            lambda session, _driver, _embedding_client: {
                "graphs": _registry_service(session).status_summary(),
                "derived": {},
            }
        )


    @server.tool()
    def get_semantic_read_model(
        ontology_id: str,
        model_name: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
        limit: int | None = None,
        entity_iri: str | None = None,
    ) -> dict[str, Any]:
        """Read a compact graph-derived business JSON read model for an Ontology."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _read_model(
                session,
                ontology_id,
                model_name,
                include,
                allow_stale_derived,
                limit,
                entity_iri,
            )
        )

    @server.tool()
    def export_semantic_ontology(
        ontology_id: str,
        format: str = "trig",
        include: str = "asserted",
        allow_stale_derived: bool = False,
    ) -> dict[str, Any]:
        """Export an Ontology model as Turtle, TriG, or JSON-LD."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _export_ontology(
                session,
                ontology_id,
                format,
                include,
                allow_stale_derived,
            )
        )

    @server.tool()
    def inspect_semantic_projection_status(
        ontology_id: str | None = None,
    ) -> dict[str, Any]:
        """Inspect projection freshness by Ontology and projection kind."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _projection_status(session, ontology_id)
        )

    @server.tool()
    def start_semantic_projection_job(
        ontology_id: str,
        projection_kind: str,
        projection_version: str,
        include: str = "asserted",
        mode: str = "rebuild",
        allow_stale_derived: bool = False,
    ) -> dict[str, Any]:
        """Request a projection rebuild job and (for non-dry-run modes) execute it."""
        return _run_tool(
            lambda session, driver, _embedding_client: _start_projection_job(
                session,
                driver,
                ontology_id,
                projection_kind,
                projection_version,
                include,
                mode,
                allow_stale_derived,
            )
        )

    # ------------------------------------------------------------------
    # Phase 7 — canonical RDF dataset migration tools
    # ------------------------------------------------------------------

    @server.tool()
    def preflight_semantic_migration(
        scope_type: str,
        scope_id: str | None = None,
        target_ontology_id: str | None = None,
    ) -> dict[str, Any]:
        """Run Phase 7 migration preflight for a scope."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _migration_service(session).preflight(
                scope_type, scope_id, target_ontology_id=target_ontology_id
            )
        )

    @server.tool()
    def create_semantic_migration_run(
        scope_type: str,
        mode: str,
        scope_id: str | None = None,
        target_ontology_id: str | None = None,
        batch_size: int | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Create a Phase 7 migration run in dry_run/shadow/dual_write_backfill/cutover/rollback mode."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _migration_service(session).create_run(
                scope_type=scope_type,
                scope_id=scope_id,
                mode=mode,
                target_ontology_id=target_ontology_id,
                batch_size=batch_size,
                created_by=runtime_actor(),
            )
        )

    @server.tool()
    def run_next_semantic_migration_batch(run_id: str) -> dict[str, Any]:
        """Execute the next pending batch of a Phase 7 migration run."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _migration_service(session).run_next_batch(
                run_id
            )
        )

    @server.tool()
    def run_semantic_migration_parity_check(
        run_id: str, check_name: str | None = None
    ) -> dict[str, Any]:
        """Run parity checks for a Phase 7 migration run."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _migration_service(
                session
            ).run_parity_check(run_id, check_name=check_name)
        )

    @server.tool()
    def cutover_semantic_migration_run(run_id: str) -> dict[str, Any]:
        """Execute the guarded RDF-primary cutover for a Phase 7 migration run."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _migration_service(session).cutover(run_id)
        )

    @server.tool()
    def rollback_semantic_migration_run(run_id: str) -> dict[str, Any]:
        """Roll back a Phase 7 cutover and restore legacy-primary mode."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _migration_service(session).rollback(run_id)
        )

    @server.tool()
    def compile_and_apply_canonical_command(
        command_kind: str,
        ontology_id: str,
        payload: dict[str, Any],
        actor: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Compile and apply a structured product command through the Phase 7 canonical writer."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _canonical_write_service(
                session
            ).apply_command(
                command_kind,
                payload,
                ontology_id=ontology_id,
                actor=runtime_actor(),
                reason=reason,
            )
        )






def _resolve_data_graphs(session, ontology_id: str) -> list[str]:
    return SemanticReadScopeResolver(session).resolve(ontology_id).model_graph_iris




def _read_model_service(
    session, project_id: str | None = None
) -> SemanticReadModelService:
    settings = Settings()
    return SemanticReadModelService(
        rdf_store=_rdf_store(),
        scope_resolver=SemanticReadScopeResolver(session),
        access_view=SemanticAccessResolver(session).resolve(
            runtime_principal(), project_id
        ),
        session=session,
        retrieval_service=SemanticResourceRetrievalService(session, settings),
    )


def _export_service(session, project_id: str | None = None) -> SemanticExportService:
    settings = Settings()
    return SemanticExportService(
        rdf_store=_rdf_store(),
        scope_resolver=SemanticReadScopeResolver(session),
        settings=settings,
        access_view=SemanticAccessResolver(session).resolve(
            runtime_principal(), project_id
        ),
    )


def _projection_job_service(session, driver) -> SemanticProjectionJobService:
    settings = Settings()
    writers = {
        "search": SemanticSearchProjectionService(_rdf_store(), FakeSearchWriter()),
        "vector": SemanticRetrievalProjectionService(
            session, _rdf_store(), EmbeddingClient(settings), settings
        ),
    }
    return SemanticProjectionJobService(
        session=session,
        writers=writers,
        scope_resolver_builder=SemanticReadScopeResolver,
    )


def _migration_service(session):
    settings = Settings()
    from app.services.semantic_migration import SemanticMigrationService

    return SemanticMigrationService(session, _rdf_store(), settings)


def _canonical_write_service(session):
    settings = Settings()
    from app.services.semantic_canonical_write import CanonicalSemanticWriteService

    return CanonicalSemanticWriteService(session, _rdf_store(), settings)


def _read_model(
    session,
    ontology_id: str,
    model_name: str,
    include: str,
    allow_stale_derived: bool,
    limit: int | None,
    entity_iri: str | None = None,
) -> dict[str, Any]:
    service = _read_model_service(session, project_id_for_ontology(session, ontology_id))
    try:
        return service.read_model(
            ontology_id=ontology_id,
            model_name=model_name,
            include=include,
            allow_stale_derived=allow_stale_derived,
            limit=limit,
            entity_iri=entity_iri,
        )
    except (ReadModelError, ReadScopeError) as exc:
        return {"error": str(exc), "status_code": getattr(exc, "status_code", 400)}


def _export_ontology(
    session,
    ontology_id: str,
    format: str,
    include: str,
    allow_stale_derived: bool,
) -> dict[str, Any]:
    service = _export_service(session, project_id_for_ontology(session, ontology_id))
    try:
        payload, warnings = service.export(
            ontology_id=ontology_id,
            format=format,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
    except (Exception,) as exc:  # noqa: BLE001
        return {"error": str(exc), "status_code": getattr(exc, "status_code", 400)}
    return {"format": format, "payload": payload, "warnings": warnings}


def _projection_status(session, ontology_id: str | None) -> dict[str, Any]:
    service = _projection_job_service(session, None)
    return service.status(ontology_id=ontology_id)


def _start_projection_job(
    session,
    driver,
    ontology_id: str,
    projection_kind: str,
    projection_version: str,
    include: str,
    mode: str,
    allow_stale_derived: bool,
) -> dict[str, Any]:
    service = _projection_job_service(session, driver)
    try:
        job = service.create_job(
            ontology_id=ontology_id,
            projection_kind=projection_kind,
            projection_version=projection_version,
            include=include,
            mode=mode,
            allow_stale_derived=allow_stale_derived,
        )
        if mode != "dry_run":
            service.run_job(job.id)
        refreshed = service.get_job(job.id)
    except ProjectionJobError as exc:
        return {"error": str(exc), "status_code": getattr(exc, "status_code", 400)}
    return {
        "id": refreshed.id,
        "status": refreshed.status,
        "projection_kind": refreshed.projection_kind,
        "node_count": refreshed.node_count,
        "relationship_count": refreshed.relationship_count,
        "document_count": refreshed.document_count,
    }
