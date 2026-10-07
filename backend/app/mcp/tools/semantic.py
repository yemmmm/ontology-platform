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
from app.services.owl_reasoner import CommandOwlReasonerRunner
from app.services.authorized_scope_discovery import AuthorizedScopeDiscoveryService
from app.services.semantic import SemanticService
from app.services.semantic_context_query import (
    SemanticContextQueryError,
    SemanticContextQueryService,
)
from app.services.semantic_graph_registry import SemanticGraphRegistryService
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_derived_state import SemanticDerivedStateService
from app.services.semantic_reasoning import SemanticReasoningService
from app.services.semantic_validation import SemanticValidationService
from app.services.semantic_graph_set_export import SemanticExportService
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
    project_id_for_graph_set,
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


def _graph_set_service(session) -> SemanticGraphSetService:
    settings = Settings()
    return SemanticGraphSetService(session, settings)


def _derived_state_service(session) -> SemanticDerivedStateService:
    settings = Settings()
    return SemanticDerivedStateService(session, settings)


def _registry_service(session) -> SemanticGraphRegistryService:
    settings = Settings()
    return SemanticGraphRegistryService(session, settings)


def _validation_service(session) -> SemanticValidationService:
    settings = Settings()
    return SemanticValidationService(session, _rdf_store(), settings)


def _reasoning_service(session) -> SemanticReasoningService:
    settings = Settings()
    return SemanticReasoningService(
        session=session,
        rdf_store=_rdf_store(),
        settings=settings,
        reasoner=CommandOwlReasonerRunner(settings.semantic_reasoner_command),
    )


def _list_scoped_run_records(
    result: tuple[list[dict[str, Any]], int], *, graph_set_id: str
) -> dict[str, Any]:
    """Normalize a read-service list result and enforce the requested scope."""
    if not isinstance(graph_set_id, str) or not graph_set_id:
        raise ValueError("graph_set_id is required for semantic run reads")
    items, total = result
    if any(item.get("graph_set_id") != graph_set_id for item in items):
        raise PermissionError("semantic run is outside the requested graph set")
    return {"graph_set_id": graph_set_id, "items": items, "total": int(total)}


def _get_scoped_run_record(
    item: dict[str, Any], *, graph_set_id: str, run_kind: str
) -> dict[str, Any]:
    """Bind a read-by-id result to the graph set supplied by the caller."""
    if not isinstance(graph_set_id, str) or not graph_set_id:
        raise ValueError("graph_set_id is required for semantic run reads")
    if item.get("graph_set_id") != graph_set_id:
        raise PermissionError(f"{run_kind} run is outside the requested graph set")
    return item


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
        target_graph_iri: str | None = None,
        validate: bool = True,
        shape_graph_iris: list[str] | None = None,
        actor: str | None = None,
        reason: str | None = None,
        warning_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit a governed RDF/SPARQL Update semantic edit with audit metadata."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _semantic_service(session).apply_edit(
                format=format,
                content=content,
                target_graph_iri=target_graph_iri,
                validate=validate,
                shape_graph_iris=shape_graph_iris or [],
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
    def describe_semantic_graph_set(graph_set_id: str) -> dict[str, Any]:
        """Return graph-set membership, source signature, and current derived pointers."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _graph_set_service(session).describe(
                graph_set_id
            )
        )

    @server.tool()
    def list_semantic_derived_pointers(
        graph_set_id: str | None = None,
        result_kind: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List derived-result pointers for reasoning results."""
        return _run_tool(
            lambda session, _driver, _embedding_client: {
                "pointers": [
                    {
                        "id": row.id,
                        "graph_set_id": row.graph_set_id,
                        "result_kind": row.result_kind,
                        "run_id": row.run_id,
                        "result_graph_iri": row.result_graph_iri,
                        "status": row.status,
                        "engine_name": row.engine_name,
                        "engine_version": row.engine_version,
                        "became_current_at": row.became_current_at,
                    }
                    for row in _derived_state_service(session).list_pointers(
                        graph_set_id=graph_set_id,
                        result_kind=result_kind,
                        status=status,
                    )
                ]
            }
        )

    @server.tool()
    def check_semantic_staleness() -> dict[str, Any]:
        """Reconcile derived-result staleness and return current/stale counts."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _derived_state_service(session).reconcile()
        )

    @server.tool()
    def get_semantic_governance_status() -> dict[str, Any]:
        """Return a governance status summary: graph counts, editability, derived staleness."""
        return _run_tool(
            lambda session, _driver, _embedding_client: {
                "graphs": _registry_service(session).status_summary(),
                "derived": _derived_state_service(session).status_summary(),
            }
        )

    @server.tool()
    def run_semantic_validation(
        graph_set_id: str,
        shape_graph_iris: list[str] | None = None,
        validation_scope: str = "asserted_only",
        reasoning_result_graph_iri: str | None = None,
        shape_version: str | None = None,
        persist_report_graph: bool = True,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Run SHACL validation over a graph set, persisting the report graph and run metadata."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _validation_service(session).run_validation(
                data_graph_iris=_resolve_data_graphs(session, graph_set_id),
                shape_graph_iris=shape_graph_iris
                or _resolve_role_graphs(session, graph_set_id, "shape"),
                graph_set_id=graph_set_id,
                validation_scope=validation_scope,
                reasoning_result_graph_iri=reasoning_result_graph_iri,
                shape_version=shape_version,
                persist_report_graph=persist_report_graph,
                actor=runtime_actor(),
            )
        )

    @server.tool()
    def run_semantic_reasoning(
        graph_set_id: str,
        tasks: list[str] | None = None,
        persist_result_graph: bool = True,
        engine_version: str | None = None,
        shape_version: str | None = None,
    ) -> dict[str, Any]:
        """Run OWL reasoning over a graph set and persist the result graph."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _reasoning_service(session).run_reasoning(
                source_graph_iris=_resolve_data_graphs(
                    session, graph_set_id, roles=("asserted_ontology", "asserted_data")
                ),
                tasks=tasks or ["consistency"],
                persist_result_graph=persist_result_graph,
                graph_set_id=graph_set_id,
                engine_version=engine_version,
                shape_version=shape_version,
            )
        )

    @server.tool()
    def list_semantic_validation_runs(
        graph_set_id: str,
        limit: int = 50,
        offset: int = 0,
        kind: str | None = None,
    ) -> dict[str, Any]:
        """List existing validation runs for one authorized graph set.

        This is deliberately read-only: it never starts validation or reruns a
        report.  The graph-set argument is required so the MCP authorization
        layer can bind the child request to its ticket-owned Project scope.
        """
        return _run_tool(
            lambda session, _driver, _embedding_client: _list_scoped_run_records(
                _validation_service(session).list_validation_runs(
                    limit=limit,
                    offset=offset,
                    graph_set_id=graph_set_id,
                    kind=kind,
                ),
                graph_set_id=graph_set_id,
            )
        )

    @server.tool()
    def get_semantic_validation_run(
        validation_run_id: str, graph_set_id: str
    ) -> dict[str, Any]:
        """Read one existing validation run, bound to an authorized graph set."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _get_scoped_run_record(
                _validation_service(session).get_validation_run(validation_run_id),
                graph_set_id=graph_set_id,
                run_kind="validation",
            )
        )

    @server.tool()
    def list_semantic_reasoning_runs(
        graph_set_id: str,
        limit: int = 50,
        offset: int = 0,
        kind: str | None = None,
    ) -> dict[str, Any]:
        """List existing reasoning runs for one authorized graph set without rerunning them."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _list_scoped_run_records(
                _reasoning_service(session).list_reasoning_runs(
                    limit=limit,
                    offset=offset,
                    graph_set_id=graph_set_id,
                    kind=kind,
                ),
                graph_set_id=graph_set_id,
            )
        )

    @server.tool()
    def get_semantic_reasoning_run(
        reasoning_run_id: str, graph_set_id: str
    ) -> dict[str, Any]:
        """Read one existing reasoning run, bound to an authorized graph set."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _get_scoped_run_record(
                _reasoning_service(session).get_reasoning_run(reasoning_run_id),
                graph_set_id=graph_set_id,
                run_kind="reasoning",
            )
        )


    @server.tool()
    def get_semantic_read_model(
        graph_set_id: str,
        model_name: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
        limit: int | None = None,
        entity_iri: str | None = None,
    ) -> dict[str, Any]:
        """Read a compact graph-derived business JSON read model for a graph set."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _read_model(
                session,
                graph_set_id,
                model_name,
                include,
                allow_stale_derived,
                limit,
                entity_iri,
            )
        )

    @server.tool()
    def export_semantic_graph_set(
        graph_set_id: str,
        format: str = "trig",
        include: str = "asserted",
        allow_stale_derived: bool = False,
    ) -> dict[str, Any]:
        """Export a graph set as Turtle, TriG, or JSON-LD."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _export_graph_set(
                session,
                graph_set_id,
                format,
                include,
                allow_stale_derived,
            )
        )

    @server.tool()
    def inspect_semantic_projection_status(
        graph_set_id: str | None = None,
    ) -> dict[str, Any]:
        """Inspect projection freshness by graph set and projection kind."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _projection_status(session, graph_set_id)
        )

    @server.tool()
    def start_semantic_projection_job(
        graph_set_id: str,
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
                graph_set_id,
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
        target_graph_set_id: str | None = None,
    ) -> dict[str, Any]:
        """Run Phase 7 migration preflight for a scope."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _migration_service(session).preflight(
                scope_type, scope_id, target_graph_set_id=target_graph_set_id
            )
        )

    @server.tool()
    def create_semantic_migration_run(
        scope_type: str,
        mode: str,
        scope_id: str | None = None,
        target_graph_set_id: str | None = None,
        batch_size: int | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Create a Phase 7 migration run in dry_run/shadow/dual_write_backfill/cutover/rollback mode."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _migration_service(session).create_run(
                scope_type=scope_type,
                scope_id=scope_id,
                mode=mode,
                target_graph_set_id=target_graph_set_id,
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
        graph_set_id: str,
        payload: dict[str, Any],
        actor: str | None = None,
        reason: str | None = None,
        shape_graph_iris: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compile and apply a structured product command through the Phase 7 canonical writer."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _canonical_write_service(
                session
            ).apply_command(
                command_kind,
                payload,
                graph_set_id=graph_set_id,
                actor=runtime_actor(),
                reason=reason,
                shape_graph_iris=shape_graph_iris or [],
            )
        )


def _selected_set_members(
    session, graph_set_id: str, roles: tuple[str, ...]
) -> list[dict[str, Any]]:
    settings = Settings()
    service = SemanticGraphSetService(session, settings)
    description = service.describe(graph_set_id)
    return [member for member in description["members"] if member["role"] in roles]


def _reject_unmaterialized_members(
    members: list[dict[str, Any]], graph_set_id: str, roles: tuple[str, ...]
) -> None:
    """R3.0-016 #29: name never-materialized members before the store does.

    ``update_membership`` registers a member at revision 0 until its first
    write materializes the graph.  Handing such an IRI to the RDF store made
    the external ``graph does not exists`` reply the only diagnostic — no
    backend source explained it.  Fail here, in backend vocabulary, instead.
    """

    missing = [str(member["graph_iri"]) for member in members if not member.get("revision")]
    if missing:
        raise ValueError(
            f"graph set {graph_set_id} has {'/'.join(roles)} member(s) with no "
            f"materialized revision: {', '.join(missing)}; materialize the graph "
            "or drop it from the set before validation/reasoning"
        )


def _resolve_data_graphs(
    session, graph_set_id: str, roles: tuple[str, ...] = ("asserted_data",)
) -> list[str]:
    members = _selected_set_members(session, graph_set_id, roles)
    _reject_unmaterialized_members(members, graph_set_id, roles)
    return [member["graph_iri"] for member in members]


def _resolve_role_graphs(session, graph_set_id: str, role: str) -> list[str]:
    members = _selected_set_members(session, graph_set_id, (role,))
    _reject_unmaterialized_members(members, graph_set_id, (role,))
    return [member["graph_iri"] for member in members]


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
    graph_set_id: str,
    model_name: str,
    include: str,
    allow_stale_derived: bool,
    limit: int | None,
    entity_iri: str | None = None,
) -> dict[str, Any]:
    service = _read_model_service(session, project_id_for_graph_set(session, graph_set_id))
    try:
        return service.read_model(
            graph_set_id=graph_set_id,
            model_name=model_name,
            include=include,
            allow_stale_derived=allow_stale_derived,
            limit=limit,
            entity_iri=entity_iri,
        )
    except (ReadModelError, ReadScopeError) as exc:
        return {"error": str(exc), "status_code": getattr(exc, "status_code", 400)}


def _export_graph_set(
    session,
    graph_set_id: str,
    format: str,
    include: str,
    allow_stale_derived: bool,
) -> dict[str, Any]:
    service = _export_service(session, project_id_for_graph_set(session, graph_set_id))
    try:
        payload, warnings = service.export(
            graph_set_id=graph_set_id,
            format=format,
            include=include,
            allow_stale_derived=allow_stale_derived,
        )
    except (Exception,) as exc:  # noqa: BLE001
        return {"error": str(exc), "status_code": getattr(exc, "status_code", 400)}
    return {"format": format, "payload": payload, "warnings": warnings}


def _projection_status(session, graph_set_id: str | None) -> dict[str, Any]:
    service = _projection_job_service(session, None)
    return service.status(graph_set_id=graph_set_id)


def _start_projection_job(
    session,
    driver,
    graph_set_id: str,
    projection_kind: str,
    projection_version: str,
    include: str,
    mode: str,
    allow_stale_derived: bool,
) -> dict[str, Any]:
    service = _projection_job_service(session, driver)
    try:
        job = service.create_job(
            graph_set_id=graph_set_id,
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
