"""MCP surface for R-004; every tool delegates to the REST application service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.api.modeling_batches import get_ontology_read_model as read_model_adapter
from app.api.schemas import ModelingBatchSubmit
from app.core.config import Settings
from app.mcp.runtime import _run_tool
from app.repositories.rdf_store import RdfStoreRepository
from app.services.modeling_batches import ModelingAuthorizationContext, ModelingBatchService


def _service(session) -> ModelingBatchService:
    settings = Settings()
    return ModelingBatchService(session, settings, RdfStoreRepository(settings.oxigraph_url))


def register_modeling_batches(server: FastMCP) -> None:
    @server.tool()
    def submit_modeling_batch(
        session_id: str,
        client_batch_id: str,
        ontology_id: str,
        idempotency_key: str,
        expected_workspace_version: str,
        items: list[dict[str, Any]],
        mode: str = "apply_atomic",
        lease_token: str | None = None,
    ) -> dict[str, Any]:
        """Dry-run or idempotently apply one immutable Ontology Modeling Batch."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).submit(
                session_id,
                ModelingBatchSubmit(
                    client_batch_id=client_batch_id,
                    ontology_id=ontology_id,
                    idempotency_key=idempotency_key,
                    expected_workspace_version=expected_workspace_version,
                    mode=mode,
                    lease_token=lease_token,
                    items=items,
                ),
                authorization=ModelingAuthorizationContext(surface="mcp"),
            )
        )

    @server.tool()
    def get_modeling_batch(batch_id: str) -> dict[str, Any]:
        """Read immutable Items, Attempts, Findings, and recovery history."""
        return _run_tool(lambda session, _driver, _embedding: _service(session).get_batch(batch_id))

    @server.tool()
    def list_session_modeling_batches(
        session_id: str,
        cursor: str | None = None,
        limit: int = 50,
        status: list[str] | None = None,
    ) -> dict[str, Any]:
        """List Modeling Batches created in one Build Session."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).list_session_batches(
                session_id, cursor=cursor, limit=limit, statuses=status
            )
        )

    @server.tool()
    def list_ontology_modeling_batches(
        ontology_id: str,
        cursor: str | None = None,
        limit: int = 50,
        status: list[str] | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> dict[str, Any]:
        """List Modeling Batches across Sessions for an Ontology."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).list_ontology_batches(
                ontology_id,
                cursor=cursor,
                limit=limit,
                statuses=status,
                created_from=datetime.fromisoformat(created_from) if created_from else None,
                created_to=datetime.fromisoformat(created_to) if created_to else None,
            )
        )

    @server.tool()
    def get_modeling_context(ontology_id: str) -> dict[str, Any]:
        """Read the authoritative current state from which further modeling starts."""
        return _run_tool(
            lambda session, _driver, _embedding: _service(session).get_modeling_context(ontology_id)
        )

    @server.tool()
    def get_ontology_read_model(
        ontology_id: str,
        model_name: str,
        include: str = "asserted",
        allow_stale_derived: bool = True,
        field_set: str = "summary",
        limit: int | None = None,
        entity_iri: str | None = None,
        class_iri: str | None = None,
        kind: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        """Resolve the default workspace and read a fixed Ontology semantic model."""

        def execute(session, _driver, _embedding):
            settings = Settings()
            return read_model_adapter(
                ontology_id=ontology_id,
                model_name=model_name,
                include=include,
                allow_stale_derived=allow_stale_derived,
                field_set=field_set,
                limit=limit,
                entity_iri=entity_iri,
                class_iri=class_iri,
                kind=kind,
                q=q,
                session=session,
                rdf_store=RdfStoreRepository(settings.oxigraph_url),
                settings=settings,
            )

        return _run_tool(execute)
