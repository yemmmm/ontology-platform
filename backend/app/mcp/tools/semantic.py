"""Direct semantic read/write MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.core.config import Settings
from app.mcp.runtime import _run_tool
from app.repositories.rdf_store import RdfStoreRepository
from app.services.semantic import SemanticService
from app.services.semantic_graph_registry import SemanticGraphRegistryService
from app.services.semantic_graph_set import SemanticGraphSetService
from app.services.semantic_derived_state import SemanticDerivedStateService


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
        evidence_status: str | None = None,
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
                evidence_status=evidence_status,
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
