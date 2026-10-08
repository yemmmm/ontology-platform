"""MCP surface for R-004; every tool delegates to the REST application service."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.api.modeling_batches import get_ontology_read_model as read_model_adapter
from app.api.schemas import ModelingBatchSubmit, ModelingItemInput
from app.core.config import Settings
from app.mcp.runtime import _run_tool, runtime_actor, runtime_principal
from app.repositories.models import OntologyModel
from app.repositories.rdf_store import RdfStoreRepository
from app.services.modeling_batches import ModelingAuthorizationContext, ModelingBatchService
from app.services.modeling_handlers import ModelingCommandHandlerRegistry
from app.services.modeling_workspace import OntologyModelRevisionService
from app.services.ontology_workspace import OntologyWorkspaceService


# The MCP schema must reflect the commands the Modeling Batch Handler accepts,
# rather than the wider semantic compiler vocabulary.
MODELING_BATCH_COMMAND_KINDS = tuple(ModelingCommandHandlerRegistry(Settings()).command_kinds)
ModelingBatchCommandKind = Literal[*MODELING_BATCH_COMMAND_KINDS]

MODELING_BATCH_PAYLOAD_GUIDANCE = (
    "Use the Modeling Batch Handler contract. Required create payload fields: "
    "create_class: name; create_property: class_id, name, plus datatype or object_class_id; "
    "create_relation_type: name, source_class_id, target_class_id; "
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


def _canonical_json_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _statement_cursor_encode(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "esc1." + base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _statement_cursor_decode(value: str) -> dict[str, Any]:
    if not isinstance(value, str) or not value.startswith("esc1."):
        raise ValueError("entity statement cursor is invalid")
    try:
        raw = value[5:]
        raw += "=" * (-len(raw) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("entity statement cursor is invalid") from exc
    if not isinstance(decoded, dict):
        raise ValueError("entity statement cursor is invalid")
    return decoded


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
        expected_model_revision: int,
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
                    expected_model_revision=expected_model_revision,
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
    def get_entity_statement_context(
        ontology_id: str,
        entity_iri: str,
        model_revision: int | None = None,
        page_size: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Read the complete incident statement set for one exact live entity IRI.

        This is intentionally a generic read projection.  Omitting
        ``model_revision`` binds the authoritative current version, which the
        response and every opaque cursor carry; an explicit version must still
        equal the current version.  The opaque cursor binds Project/Ontology,
        exact entity IRI, model revision, and a snapshot digest; callers
        must consume every page through ``complete=true`` before using the
        response as delete-impact evidence.
        """

        def execute(session, _driver, _embedding):
            from urllib.parse import urlparse

            if isinstance(page_size, bool) or not isinstance(page_size, int) or not 0 < page_size <= 1000:
                raise ValueError("entity statement page_size must be between 1 and 1000")
            if model_revision is not None and (type(model_revision) is not int or model_revision < 0):
                raise ValueError("entity statement model_revision must be a nonnegative integer")
            parsed = urlparse(entity_iri) if isinstance(entity_iri, str) else None
            if parsed is None or not parsed.scheme or not parsed.netloc:
                raise ValueError("entity statement entity_iri is invalid")
            ontology = session.get(OntologyModel, ontology_id)
            if ontology is None:
                raise ValueError("ontology_not_found")
            from app.services.semantic_read_scope import SemanticReadScopeResolver

            resolver = SemanticReadScopeResolver(session)
            scope = resolver.resolve(ontology_id)
            current_version = scope.model_revision
            # Read-only first pages bind the authoritative current version when
            # the caller omits it; explicit delete-impact callers keep the
            # strict drift check below.
            bound_version = model_revision if model_revision is not None else current_version
            if bound_version != current_version:
                raise ValueError("entity statement workspace version drifted")
            data_graphs = scope.model_graph_iris
            if not data_graphs:
                raise ValueError("asserted data graph is unavailable")
            escaped_entity = entity_iri.replace("\\", "\\\\").replace(">", "\\>")
            graph_values = " ".join(f"<{graph}>" for graph in data_graphs)
            query = (
                "SELECT DISTINCT ?subject ?predicate ?object ?graph WHERE { "
                f"VALUES ?graph {{ {graph_values} }} "
                "GRAPH ?graph { ?subject ?predicate ?object . "
                f"FILTER(?subject = <{escaped_entity}> || (isIRI(?object) && ?object = <{escaped_entity}>)) "
                "} } LIMIT 100000"
            )
            result = RdfStoreRepository(Settings().oxigraph_url).query_read_model(
                query=query,
                graph_iris=data_graphs,
                timeout_seconds=10,
                limit=100000,
            )
            result_obj = getattr(result, "result", result)
            if hasattr(result, "bindings"):
                rows = list(result.bindings)
            elif isinstance(result_obj, dict):
                rows = list(result_obj.get("results", {}).get("bindings", []))
            else:
                rows = []

            def cell(row: dict[str, Any], key: str) -> tuple[str, str | None]:
                value = row.get(key)
                if isinstance(value, dict):
                    return str(value.get("value", "")), value.get("type")
                return (str(value) if value is not None else ""), None

            statements: list[dict[str, Any]] = []
            for row in rows:
                subject, subject_kind = cell(row, "subject")
                predicate, predicate_kind = cell(row, "predicate")
                obj, object_kind = cell(row, "object")
                graph, graph_kind = cell(row, "graph")
                if not subject or not predicate or not obj or not graph:
                    continue
                statements.append(
                    {
                        "subject": subject,
                        "predicate": predicate,
                        "object": obj,
                        "object_kind": object_kind or "literal",
                        "graph": graph,
                    }
                )
            # R3.0-004: hide statements whose s/p/o names an unauthorized
            # protected member before digest, cursor, and page computation.
            from app.services.semantic_access import SemanticAccessResolver

            access_view = SemanticAccessResolver(session).resolve(
                runtime_principal(), ontology.project_id
            )
            statements = [
                item
                for item in statements
                if access_view.is_statement_visible(
                    item["subject"], item["predicate"], [item["object"]]
                )
            ]
            encoded = [json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in statements]
            if len(set(encoded)) != len(encoded):
                raise ValueError("entity statement projection contains duplicate statements")
            ordered = [json.loads(item) for item in sorted(encoded)]
            if resolver.resolve(ontology_id).model_revision != bound_version:
                raise ValueError("entity statement model revision changed during reading")
            snapshot_digest = _canonical_json_digest(ordered)
            offset = 0
            if cursor is not None:
                token = _statement_cursor_decode(cursor)
                expected = {
                    "project_id": ontology.project_id,
                    "ontology_id": ontology_id,
                    "entity_iri": entity_iri,
                    "model_revision": bound_version,
                    "snapshot_digest": snapshot_digest,
                }
                if any(token.get(key) != value for key, value in expected.items()):
                    raise ValueError("entity statement cursor scope or snapshot drifted")
                offset = token.get("offset")
                if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                    raise ValueError("entity statement cursor offset is invalid")
            if offset > len(ordered):
                raise ValueError("entity statement cursor is beyond snapshot")
            page = ordered[offset : offset + page_size]
            next_offset = offset + len(page)
            complete = next_offset >= len(ordered)
            next_cursor = None
            if not complete:
                next_cursor = _statement_cursor_encode(
                    {
                        "project_id": ontology.project_id,
                        "ontology_id": ontology_id,
                        "entity_iri": entity_iri,
                        "model_revision": bound_version,
                        "snapshot_digest": snapshot_digest,
                        "offset": next_offset,
                    }
                )
            return {
                "project_id": ontology.project_id,
                "ontology_id": ontology_id,
                "entity_iri": entity_iri,
                "model_revision": bound_version,
                "cursor": cursor,
                "statements": page,
                "page_digest": _canonical_json_digest(page),
                "snapshot_digest": snapshot_digest,
                "next_cursor": next_cursor,
                "complete": complete,
            }

        return _run_tool(execute)

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
                principal=runtime_principal(),
                session=session,
                rdf_store=RdfStoreRepository(settings.oxigraph_url),
                settings=settings,
            )

        return _run_tool(execute)
