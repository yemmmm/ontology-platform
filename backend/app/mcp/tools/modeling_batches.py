"""MCP surface for R-004; every tool delegates to the REST application service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.api.modeling_batches import get_ontology_read_model as read_model_adapter
from app.api.schemas import ModelingBatchSubmit, ModelingItemInput
from app.core.config import Settings
from app.mcp.runtime import _run_tool, runtime_actor
from app.repositories.rdf_store import RdfStoreRepository
from app.services.modeling_batches import ModelingAuthorizationContext, ModelingBatchService
from app.services.modeling_handlers import ModelingCommandHandlerRegistry


# The MCP schema must reflect the commands the Modeling Batch Handler accepts,
# rather than the wider semantic compiler vocabulary.
MODELING_BATCH_COMMAND_KINDS = tuple(ModelingCommandHandlerRegistry(Settings()).command_kinds)
ModelingBatchCommandKind = Literal[*MODELING_BATCH_COMMAND_KINDS]

MODELING_BATCH_PAYLOAD_GUIDANCE = (
    "Use the Modeling Batch Handler contract. Required create payload fields: "
    "create_class: name; create_property: class_id, name, plus datatype or object_class_id; "
    "create_relation_type: name, source_class_id, target_class_id; "
    "create_shape: target_class_id, constraints; "
    "create_entity: class_iri_or_legacy_id, label; its optional properties must be a JSON object "
    "mapping property IRI keys to values, and lists are invalid; update_entity uses the same "
    "properties form. "
    "create_relation: source_entity_iri, relation_type_iri, target_entity_iri. "
    "Only published command_kind values are permitted; add_* aliases are forbidden."
)


class McpModelingItemInput(ModelingItemInput):
    """MCP-facing Modeling Item with the handler's finite command inventory."""

    command_kind: ModelingBatchCommandKind
    payload: dict[str, Any] = Field(description=MODELING_BATCH_PAYLOAD_GUIDANCE)


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
        items: list[McpModelingItemInput],
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
                authorization=ModelingAuthorizationContext(actor=runtime_actor(), surface="mcp"),
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
