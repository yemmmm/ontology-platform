"""Direct semantic read/write MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.core.config import Settings
from app.mcp.runtime import _run_tool
from app.repositories.rdf_store import RdfStoreRepository
from app.services.owl_reasoner import CommandOwlReasonerRunner
from app.services.semantic import SemanticService
from app.services.semantic_graph_registry import SemanticGraphRegistryService
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_derived_state import SemanticDerivedStateService
from app.services.semantic_reasoning import SemanticReasoningService
from app.services.semantic_rule_definition import SemanticRuleDefinitionService
from app.services.semantic_rule_execution import SemanticRuleExecutionService
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
from app.services.semantic_search_projection import (
    FakeSearchWriter,
    SemanticSearchProjectionService,
)
from app.services.semantic_vector_projection import (
    FakeVectorWriter,
    SemanticVectorProjectionService,
)
from app.services.semantic_visibility import SemanticVisibilityPolicy


def _rdf_store() -> RdfStoreRepository:
    return RdfStoreRepository(Settings().oxigraph_url)


def _semantic_service(session) -> SemanticService:
    settings = Settings()
    return SemanticService(
        session=session,
        rdf_store=RdfStoreRepository(settings.oxigraph_url),
        settings=settings,
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


def _rule_definition_service(session) -> SemanticRuleDefinitionService:
    return SemanticRuleDefinitionService(session, Settings())


def _rule_execution_service(session) -> SemanticRuleExecutionService:
    settings = Settings()
    return SemanticRuleExecutionService(session, _rdf_store(), settings)


def register_semantic(server: FastMCP) -> None:
    @server.tool()
    def semantic_sparql_query(
        query: str,
        timeout_seconds: float | None = None,
        result_limit: int | None = None,
    ) -> dict[str, Any]:
        """Run read-only SPARQL against the governed semantic RDF dataset."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _semantic_service(session)
            .query_sparql(query, timeout_seconds, result_limit)
            .__dict__
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
                actor=actor,
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
        """List derived-result pointers for reasoning/rule results."""
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
            lambda session, _driver, _embedding_client: _validation_service(
                session
            ).run_validation(
                data_graph_iris=_resolve_data_graphs(session, graph_set_id),
                shape_graph_iris=shape_graph_iris
                or _resolve_role_graphs(session, graph_set_id, "shape"),
                graph_set_id=graph_set_id,
                validation_scope=validation_scope,
                reasoning_result_graph_iri=reasoning_result_graph_iri,
                shape_version=shape_version,
                persist_report_graph=persist_report_graph,
                actor=actor,
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
    def submit_semantic_rule_definition(
        rule_iri: str,
        name: str,
        language: str,
        body: dict[str, Any],
        input_roles: list[str] | None = None,
        output_kind: str = "assertion",
        uses_inferred_facts: bool = False,
        requires_review: bool = False,
        priority: int = 0,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Create or reuse an immediately executable platform rule definition."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _rule_definition_service(
                session
            )
            .create_rule(
                rule_iri=rule_iri,
                name=name,
                language=language,
                body=body,
                input_roles=input_roles or [],
                output_kind=output_kind,
                uses_inferred_facts=uses_inferred_facts,
                requires_review=requires_review,
                priority=priority,
                created_by=created_by,
            )
            .__dict__
        )

    @server.tool()
    def run_semantic_rule(
        graph_set_id: str,
        rule_definition_id: str | None = None,
        rule_iri: str | None = None,
        rule_definition_ids: list[str] | None = None,
        promote_pointer: bool = True,
        engine_version: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Run a single rule, a named group, or all rules for a graph set."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _rule_execution_service(
                session
            )._dispatch(
                graph_set_id=graph_set_id,
                rule_definition_id=rule_definition_id,
                rule_iri=rule_iri,
                rule_definition_ids=rule_definition_ids,
                promote_pointer=promote_pointer,
                actor=actor,
                engine_version=engine_version,
            )
        )

    @server.tool()
    def get_semantic_read_model(
        graph_set_id: str,
        model_name: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
        limit: int | None = None,
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
            lambda session, _driver, _embedding_client: _projection_status(
                session, graph_set_id
            )
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

    @server.tool()
    def inspect_semantic_statement_provenance(
        graph_set_id: str,
        statement_iri: str,
        include: str = "asserted",
    ) -> dict[str, Any]:
        """Inspect provenance, evidence, assertion kind, and staleness for a statement."""
        return _run_tool(
            lambda session, _driver, _embedding_client: _statement_provenance(
                session, graph_set_id, statement_iri, include
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
                created_by=created_by,
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
                actor=actor,
                reason=reason,
                shape_graph_iris=shape_graph_iris or [],
            )
        )



def _resolve_data_graphs(
    session, graph_set_id: str, roles: tuple[str, ...] = ("asserted_data",)
) -> list[str]:
    settings = Settings()
    service = SemanticGraphSetService(session, settings)
    description = service.describe(graph_set_id)
    return [
        member["graph_iri"] for member in description["members"] if member["role"] in roles
    ]


def _resolve_role_graphs(session, graph_set_id: str, role: str) -> list[str]:
    settings = Settings()
    service = SemanticGraphSetService(session, settings)
    description = service.describe(graph_set_id)
    return [
        member["graph_iri"] for member in description["members"] if member["role"] == role
    ]


def _read_model_service(session) -> SemanticReadModelService:
    settings = Settings()
    return SemanticReadModelService(
        rdf_store=_rdf_store(),
        scope_resolver=SemanticReadScopeResolver(session),
        visibility_policy=SemanticVisibilityPolicy(
            graph_labels=getattr(settings, "semantic_graph_visibility_labels", {}) or {}
        ),
    )


def _export_service(session) -> SemanticExportService:
    settings = Settings()
    return SemanticExportService(
        rdf_store=_rdf_store(),
        scope_resolver=SemanticReadScopeResolver(session),
        settings=settings,
        visibility_policy=SemanticVisibilityPolicy(
            graph_labels=getattr(settings, "semantic_graph_visibility_labels", {}) or {}
        ),
    )


def _projection_job_service(session, driver) -> SemanticProjectionJobService:
    writers = {
        "search": SemanticSearchProjectionService(_rdf_store(), FakeSearchWriter()),
        "vector": SemanticVectorProjectionService(_rdf_store(), FakeVectorWriter()),
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
) -> dict[str, Any]:
    service = _read_model_service(session)
    try:
        return service.read_model(
            graph_set_id=graph_set_id,
            model_name=model_name,
            include=include,
            allow_stale_derived=allow_stale_derived,
            limit=limit,
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
    service = _export_service(session)
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


def _statement_provenance(
    session,
    graph_set_id: str,
    statement_iri: str,
    include: str,
) -> dict[str, Any]:
    service = _read_model_service(session)
    envelope = service.read_model(
        graph_set_id=graph_set_id,
        model_name="statement-list",
        include=include,
    )
    for item in envelope["items"]:
        if item["iri"] == statement_iri:
            return item
    return {
        "error": "statement not found",
        "graph_set_id": graph_set_id,
        "iri": statement_iri,
    }
