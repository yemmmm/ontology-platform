"""R-004 immutable Modeling Batch orchestration shared by REST and MCP."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from rdflib import Graph, URIRef
from rdflib.util import from_n3
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    ModelingBatchSubmit,
)
from app.core.config import Settings
from app.repositories.models import (
    BuildSessionModel,
    CompetencyQuestionModel,
    ModelingAttemptItemResultModel,
    ModelingBatchAttemptModel,
    ModelingBatchModel,
    ModelingItemModel,
    OntologyLeaseModel,
    OntologyModel,
    OntologyWriteFenceModel,
    SemanticEditAuditModel,
    SemanticGraphRevisionModel,
    SemanticProjectionManifestModel,
)
from app.repositories.rdf_store import RdfGraphDelta, RdfStoreRepository
from app.services.build_sessions import BuildSessionError, BuildSessionService
from app.services.modeling_handlers import (
    ModelingCommandHandlerRegistry,
    PreparedModelingCommand,
    union_delta,
)
from app.services.modeling_workspace import OntologyModelRevisionService
from app.services.operation_semantics import (
    OperationValidationError,
    reject_operation_secrets,
)
from app.services.semantic_retrieval import SemanticRetrievalCoordinator
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_canonical_write import (
    CanonicalSemanticWriteError,
    CanonicalSemanticWriteService,
    CanonicalValidationError,
)
from app.services.semantic_command_compiler import (
    CommandCompilerError,
    CompiledCommand,
    InvalidCommandPayload,
)


TERMINAL_ATTEMPT_STATUSES = {
    "validated",
    "validation_failed",
    "applied",
    "partially_applied",
    "failed",
}
TERMINAL_BATCH_STATUSES = {"applied", "partially_applied", "failed"}


class _ExecutionClaimLost(RuntimeError):
    pass


class ModelingBatchError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409, **detail: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class ModelingAuthorizationContext:
    actor: str = "system:unattributed"
    can_read: bool = True
    can_write: bool = True
    surface: str = "internal"


def _id() -> str:
    return str(uuid4())


def _hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_delete_only_impact_receipt(value: Any) -> dict[str, Any]:
    """Validate the opaque, tool-owned before-set persisted with a Phase-B delete.

    ModelingBatchService does not interpret domain semantics here.  It only
    verifies the receipt envelope and its canonical digest before allowing the
    command into an operation plan; the recovery observer later compares the
    exact statement set against the live graph.
    """

    if not isinstance(value, dict):
        raise InvalidCommandPayload("delete-only impact_receipt must be an object")
    required = {
        "schema_version",
        "model_revision",
        "target_semantic_id",
        "project_id",
        "ontology_id",
        "candidate_digest",
        "entity_iri",
        "snapshot_digest",
        "page_digests",
        "statements",
        "complete",
        "receipt_digest",
    }
    if set(value) != required:
        raise InvalidCommandPayload("delete-only impact_receipt has an invalid field set")
    if value.get("schema_version") != "r2-3-003-delete-impact/v1":
        raise InvalidCommandPayload("delete-only impact_receipt schema is unsupported")
    if value.get("complete") is not True:
        raise InvalidCommandPayload("delete-only impact_receipt must be complete")
    for field in (
        "target_semantic_id",
        "project_id",
        "ontology_id",
        "candidate_digest",
        "entity_iri",
        "snapshot_digest",
        "receipt_digest",
    ):
        if not isinstance(value.get(field), str) or not value[field]:
            raise InvalidCommandPayload(f"delete-only impact_receipt {field} is required")
    if type(value.get("model_revision")) is not int or value["model_revision"] < 0:
        raise InvalidCommandPayload("delete-only impact_receipt model_revision is required")
    if not isinstance(value.get("page_digests"), list) or not value["page_digests"]:
        raise InvalidCommandPayload("delete-only impact_receipt page_digests are required")
    if not isinstance(value.get("statements"), list):
        raise InvalidCommandPayload("delete-only impact_receipt statements are required")
    body = dict(value)
    digest = body.pop("receipt_digest")
    if digest != _hash(body):
        raise InvalidCommandPayload("delete-only impact_receipt digest is invalid")
    return json.loads(json.dumps(value, ensure_ascii=False))


def _payload_path(ordinal: int, exc: BaseException) -> list[str | int]:
    """Locate a compiler rejection inside the item payload (R3.0-009 §8).

    Typed conflicts name the offending payload fields; other compiler errors
    stay at payload level. Plain ``KeyError``/``ValueError`` keep the legacy
    ``["payload"]`` path.
    """
    fields = tuple(getattr(exc, "fields", ()) or ())
    if fields:
        return ["items", ordinal, "payload", *fields]
    if isinstance(exc, CommandCompilerError):
        return ["items", ordinal, "payload"]
    return ["payload"]


def _finding(
    code: str,
    severity: str,
    message: str,
    *,
    item_ids: list[str] | None = None,
    scope: str = "item",
    path: list[str | int] | None = None,
    retryable: bool = False,
    **details: Any,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "scope": scope,
        "client_item_ids": item_ids or [],
        "path": path or [],
        "message": message,
        "details": details,
        "blocking": severity == "error",
        "retryable": retryable,
    }


_RELATIONAL_MAPPING_COMMAND_KINDS = frozenset(
    {
        "create_table_mapping",
        "update_table_mapping",
        "delete_table_mapping",
        "create_join_mapping",
        "update_join_mapping",
        "delete_join_mapping",
        "create_enum_meaning",
        "update_enum_meaning",
        "delete_enum_meaning",
        "create_metric_definition",
        "update_metric_definition",
        "delete_metric_definition",
    }
)

_RELATIONAL_METADATA_IRI_KEYS = (
    # Scoped enums also carry their referenced table_mapping_iri. Resolve the
    # written resource first, rather than treating that dependency as output.
    "enum_meaning_iri",
    "metric_iri",
    "join_mapping_iri",
    "table_mapping_iri",
)


def _relational_resource_iri(metadata: dict[str, Any]) -> str | None:
    for key in _RELATIONAL_METADATA_IRI_KEYS:
        value = metadata.get(key)
        if value:
            return str(value)
    return None


class ModelingBatchService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        rdf_store: RdfStoreRepository | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.rdf_store = rdf_store
        self.handlers = ModelingCommandHandlerRegistry(settings)
        self.model_revisions = OntologyModelRevisionService(session, settings)

    def submit(
        self,
        build_session_id: str,
        payload: ModelingBatchSubmit,
        *,
        authorization: ModelingAuthorizationContext | None = None,
        request_bytes: int | None = None,
    ) -> dict[str, Any]:
        auth = authorization or ModelingAuthorizationContext()
        if not auth.can_write:
            raise ModelingBatchError(
                "forbidden", "Project write permission is required", status_code=403
            )
        for item in payload.items:
            if item.command_kind in {
                "create_operation",
                "update_operation",
                "delete_operation",
            }:
                try:
                    reject_operation_secrets(item.payload)
                except OperationValidationError as exc:
                    raise ModelingBatchError(
                        exc.code,
                        str(exc),
                        status_code=422,
                    ) from exc
        self._check_capacity(payload, request_bytes)
        from app.services.checkpoint_archive import lock_projects

        project_id = self.session.scalar(
            select(BuildSessionModel.project_id).where(BuildSessionModel.id == build_session_id)
        )
        if project_id:
            lock_projects(self.session, [project_id])
        build_session = self.session.scalar(
            select(BuildSessionModel)
            .where(BuildSessionModel.id == build_session_id)
            .with_for_update()
        )
        if build_session is None:
            raise ModelingBatchError(
                "build_session_not_found", "Build Session was not found", status_code=404
            )
        if build_session.status != "active":
            raise ModelingBatchError("build_session_not_active", "Build Session is not active")
        ontology = self.session.scalar(
            select(OntologyModel).where(OntologyModel.id == payload.ontology_id).with_for_update()
        )
        if ontology is None or ontology.project_id != build_session.project_id:
            raise ModelingBatchError(
                "ontology_not_found", "Ontology was not found", status_code=404
            )
        if payload.mode == "dry_run" and payload.lease_token is not None:
            raise ModelingBatchError(
                "invalid_lease_token", "dry_run must omit lease_token", status_code=422
            )
        if payload.mode != "dry_run" and payload.lease_token is None:
            raise ModelingBatchError("ontology_lease_conflict", "apply requires lease_token")

        content = self._content(payload)
        content_hash = _hash(content)
        request_hash = _hash(
            {
                "content_hash": content_hash,
                "mode": payload.mode,
                "expected_model_revision": payload.expected_model_revision,
            }
        )
        existing_attempt = self.session.scalar(
            select(ModelingBatchAttemptModel)
            .where(
                ModelingBatchAttemptModel.build_session_id == build_session_id,
                ModelingBatchAttemptModel.idempotency_key == payload.idempotency_key,
            )
            .with_for_update()
        )
        if existing_attempt is not None:
            if existing_attempt.request_hash != request_hash:
                raise ModelingBatchError(
                    "idempotency_conflict", "Idempotency key was used with different semantics"
                )
            if existing_attempt.status in {"applying", "recovering"}:
                return self._resume_attempt(existing_attempt, auth)
            return self._attempt_response(existing_attempt, False, False)

        if self.session.get(OntologyWriteFenceModel, payload.ontology_id) is not None:
            raise ModelingBatchError(
                "ontology_write_fenced", "Ontology has an in-flight Modeling Batch write"
            )
        workspace = OntologyWorkspaceService(self.session, self.settings).context(
            payload.ontology_id
        )
        if workspace.get("state") != "ready" or not workspace.get("ontology_id"):
            raise ModelingBatchError(
                "workspace_revision_conflict", "Ontology workspace is incomplete"
            )
        current_version = self.model_revisions.version_for(payload.ontology_id)
        if current_version != payload.expected_model_revision:
            raise ModelingBatchError(
                "workspace_revision_conflict",
                "Ontology workspace changed after the caller last read it",
                current_model_revision=current_version,
            )

        batch, created_batch = self._get_or_create_batch(
            build_session, ontology, payload.client_batch_id, content_hash, content
        )
        if batch.status == "failed" and payload.mode != "dry_run":
            raise ModelingBatchError("batch_failed", "Modeling Batch cannot be applied again")
        if batch.status in {"applied", "partially_applied"} and payload.mode != "dry_run":
            terminal = next(
                attempt
                for attempt in reversed(batch.attempts)
                if attempt.status in {"applied", "partially_applied"}
            )
            return self._attempt_response(terminal, False, False)
        authorization_result: dict[str, Any] | None = None
        if payload.mode != "dry_run":
            try:
                authorization_result = BuildSessionService(
                    self.session, self.settings
                ).authorize_apply(
                    session_id=build_session_id,
                    ontology_id=payload.ontology_id,
                    lease_token=payload.lease_token or "",
                    expected_model_revision=payload.expected_model_revision,
                )
            except BuildSessionError as exc:
                raise ModelingBatchError(
                    exc.code, exc.message, status_code=exc.status_code, **exc.detail
                ) from exc

        attempt = ModelingBatchAttemptModel(
            id=_id(),
            batch_id=batch.id,
            build_session_id=build_session_id,
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
            mode=payload.mode,
            status="validating",
            expected_model_revision=payload.expected_model_revision,
            model_revision_before=current_version,
            ontology_id=payload.ontology_id,
            lease_revision=(authorization_result or {}).get("lease_revision"),
            target_snapshot=self._target_snapshot(payload.ontology_id),
            findings=[],
            groups=[],
            recovery_detail={"history": []},
        )
        self.session.add(attempt)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(ModelingBatchAttemptModel).where(
                    ModelingBatchAttemptModel.build_session_id == build_session_id,
                    ModelingBatchAttemptModel.idempotency_key == payload.idempotency_key,
                )
            )
            if existing is None:
                raise
            if existing.request_hash != request_hash:
                raise ModelingBatchError("idempotency_conflict", "Concurrent request conflict")
            return self._attempt_response(existing, False, False)
        try:
            prepared, findings, groups, dependency_map = self._compile(batch)
            selected, statuses = self._select_items(
                batch, payload.mode, findings, groups, dependency_map
            )
            candidate_delta = union_delta(
                [prepared[item_id] for item_id in selected if item_id in prepared]
            )
            while True:
                validation_findings = self._validate_candidate_delta(
                    batch, candidate_delta, prepared, selected
                )
                findings = self._dedupe_findings([*findings, *validation_findings])
                if not any(finding["blocking"] for finding in validation_findings):
                    break
                attributable = any(finding["client_item_ids"] for finding in validation_findings)
                if payload.mode != "apply_partial" or not attributable:
                    if payload.mode != "dry_run":
                        for item_id in selected:
                            statuses[item_id] = "not_applied"
                        selected.clear()
                    break
                previous = set(selected)
                selected, statuses = self._select_items(
                    batch, payload.mode, findings, groups, dependency_map
                )
                if selected == previous:
                    selected.clear()
                    break
                candidate_delta = union_delta(
                    [prepared[item_id] for item_id in selected if item_id in prepared]
                )
            delta = (
                candidate_delta
                if payload.mode == "dry_run"
                else union_delta([prepared[item_id] for item_id in selected])
            )
            normalized_delta = self._delta_dict(delta)
            plan = {
                "selected_client_item_ids": sorted(selected),
                "delta": normalized_delta,
                "before_graph_hashes": self._before_graph_hashes(delta),
                "expected_graph_hashes": self._expected_graph_hashes(delta),
                "commands": {
                    item_id: {
                        "command_kind": prepared[item_id].command_kind,
                        "payload": prepared[item_id].payload,
                        "outputs": prepared[item_id].outputs,
                        "storage": prepared[item_id].storage,
                    }
                    for item_id in sorted(selected)
                },
                "audit_id": str(uuid5(NAMESPACE_URL, f"modeling-attempt:{attempt.id}:audit")),
                "actor": auth.actor,
            }
            delete_receipts = []
            for item_id in sorted(selected):
                command = prepared[item_id]
                if command.command_kind != "delete_entity":
                    continue
                receipt = command.payload.get("impact_receipt")
                if receipt is None:
                    continue
                delete_receipts.append(
                    {
                        "client_item_id": item_id,
                        "entity_iri": command.payload.get("entity_iri"),
                        "impact_receipt": receipt,
                    }
                )
            if delete_receipts:
                plan["delete_only_recovery"] = {
                    "schema_version": "r2-3-003-delete-impact/v1",
                    "receipts": delete_receipts,
                }
            findings = self._fingerprint_findings(attempt.id, findings)
            attempt.findings = findings
            attempt.groups = groups
            attempt.normalized_delta = normalized_delta
            attempt.delta_hash = _hash(normalized_delta)
            attempt.operation_plan = plan
            attempt.operation_plan_hash = _hash(plan)
            attempt.audit_id = plan["audit_id"]
            self._save_item_results(attempt, batch, statuses, groups, findings)
            has_error = any(finding["blocking"] for finding in findings)
            if (
                payload.mode == "dry_run"
                or (payload.mode == "apply_atomic" and has_error)
                or not selected
            ):
                attempt.status = "validation_failed" if has_error else "validated"
                attempt.completed_at = self._now()
                self.session.commit()
                return self._attempt_response(attempt, created_batch, True)
            self._establish_fence(attempt, batch, authorization_result or {})
            self.session.commit()
            return self._execute(
                attempt,
                auth,
                claim_id=attempt.execution_claim_id,
                created_batch=created_batch,
                created_attempt=True,
            )
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(ModelingBatchAttemptModel).where(
                    ModelingBatchAttemptModel.build_session_id == build_session_id,
                    ModelingBatchAttemptModel.idempotency_key == payload.idempotency_key,
                )
            )
            if existing is None:
                raise
            if existing.request_hash != request_hash:
                raise ModelingBatchError("idempotency_conflict", "Concurrent request conflict")
            return self._attempt_response(existing, False, False)

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        batch = self.session.get(ModelingBatchModel, batch_id)
        if batch is None:
            raise ModelingBatchError(
                "modeling_batch_not_found", "Modeling Batch was not found", status_code=404
            )
        return self._batch_detail(batch)

    def list_session_batches(
        self,
        build_session_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        statuses: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.session.get(BuildSessionModel, build_session_id) is None:
            raise ModelingBatchError(
                "build_session_not_found", "Build Session was not found", status_code=404
            )
        return self._list_batches(
            [ModelingBatchModel.build_session_id == build_session_id], cursor, limit, statuses
        )

    def list_ontology_batches(
        self,
        ontology_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        statuses: list[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> dict[str, Any]:
        ontology = self.session.get(OntologyModel, ontology_id)
        if ontology is None:
            raise ModelingBatchError(
                "ontology_not_found", "Ontology was not found", status_code=404
            )
        filters = [ModelingBatchModel.ontology_id == ontology_id]
        if created_from:
            filters.append(ModelingBatchModel.created_at >= created_from)
        if created_to:
            filters.append(ModelingBatchModel.created_at <= created_to)
        return self._list_batches(filters, cursor, limit, statuses)

    def get_modeling_context(self, ontology_id: str) -> dict[str, Any]:
        ontology = self.session.get(OntologyModel, ontology_id)
        if ontology is None:
            raise ModelingBatchError(
                "ontology_not_found", "Ontology was not found", status_code=404
            )
        workspace = OntologyWorkspaceService(self.session, self.settings).context(ontology_id)
        version = (
            self.model_revisions.version_for(ontology_id)
            if workspace["state"] == "ready"
            else None
        )
        fence = self.session.get(OntologyWriteFenceModel, ontology_id)
        lease = self.session.get(OntologyLeaseModel, ontology_id)
        now = self._now()
        active_lease = bool(
            lease and lease.released_at is None and self._aware(lease.expires_at) > now
        )
        stale_pointers = 0
        stale_projections = int(
            self.session.scalar(
                select(func.count(SemanticProjectionManifestModel.id)).where(
                    SemanticProjectionManifestModel.ontology_id
                    == workspace.get("ontology_id"),
                    SemanticProjectionManifestModel.status == "stale",
                )
            )
            or 0
        )
        stale = stale_pointers + stale_projections
        recent = self._list_batches(
            [ModelingBatchModel.ontology_id == ontology_id],
            None,
            10,
            None,
        )
        entries = {
            name: {
                "rest": f"/api/ontologies/{ontology_id}/semantic-read-models/{name}",
                "mcp": {
                    "tool": "get_ontology_read_model",
                    "ontology_id": ontology_id,
                    "model_name": name,
                },
            }
            for name in ("classes", "entities", "facts")
        }
        rdf_counts, counts_warning = self._rdf_resource_counts(workspace)
        return {
            "semantic_base_iri": self.settings.semantic_base_iri,
            "project": {"id": ontology.project_id},
            "ontology": {"id": ontology.id, "name": ontology.name, "status": ontology.status},
            "workspace": {
                "state": workspace["state"],
                "model_revision": version,
                "editable": workspace["state"] == "ready"
                and workspace["editable"],
                "issues": workspace["issues"],
            },
            "resource_counts": {
                **rdf_counts,
            },
            "resource_counts_warning": counts_warning,
            "derived_state": {
                "stale_count": stale,
                "stale_pointer_count": stale_pointers,
                "stale_projection_count": stale_projections,
                "warning": "derived_state_stale" if stale else None,
            },
            "lease": {"active": active_lease, "fenced": fence is not None},
            "recovering": {
                "active": fence is not None,
                "attempt_id": fence.attempt_id if fence else None,
            },
            "recent_batches": recent["batches"],
            "recent_batches_next_cursor": recent["next_cursor"],
            "batch_history": f"/api/ontologies/{ontology_id}/modeling-batches",
            "query_entries": entries,
        }

    def _rdf_resource_counts(
        self, workspace: dict[str, Any]
    ) -> tuple[dict[str, int | None], str | None]:
        keys = (
            "classes",
            "properties",
            "relation_types",
            "entities",
            "relations",
            "facts",
            "mappings",
        )
        empty = {key: None for key in keys}
        if workspace.get("state") != "ready":
            return empty, "semantic_workspace_incomplete"
        if self.rdf_store is None or not hasattr(self.rdf_store, "query_sparql"):
            return empty, "semantic_count_query_unavailable"
        ontology_graph = data_graph = workspace["model_graph_iri"]
        if not ontology_graph or not data_graph:
            return empty, "semantic_workspace_incomplete"
        op = self.settings.semantic_base_iri.rstrip("/") + "/vocab/"
        branches = {
            "classes": f"GRAPH <{ontology_graph}> {{ ?s a <http://www.w3.org/2002/07/owl#Class> }}",
            "properties": f"GRAPH <{ontology_graph}> {{ ?s a <http://www.w3.org/2002/07/owl#DatatypeProperty> }}",
            "relation_types": f"GRAPH <{ontology_graph}> {{ ?s a <http://www.w3.org/2002/07/owl#ObjectProperty> }}",
            "entities": f"GRAPH <{data_graph}> {{ ?s a <http://www.w3.org/2002/07/owl#NamedIndividual> }}",
            "relations": f"GRAPH <{data_graph}> {{ ?s ?p ?o FILTER(isIRI(?o) && ?p != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>) }}",
            "facts": f"GRAPH <{data_graph}> {{ ?s ?p ?o }}",
            "mappings": f"GRAPH <{ontology_graph}> {{ ?s a <{op}SemanticMapping> }}",
        }
        query = (
            "SELECT ?kind ?count WHERE { "
            + " UNION ".join(
                '{ SELECT ("'
                + key
                + '" AS ?kind) (COUNT(DISTINCT ?s) AS ?count) WHERE { '
                + pattern
                + " } }"
                for key, pattern in branches.items()
            )
            + " }"
        )
        try:
            result = self.rdf_store.query_sparql(query, timeout_seconds=10, limit=100)
            bindings = (result.result or {}).get("results", {}).get("bindings", [])
            counts = {key: 0 for key in keys}
            for row in bindings:
                key = (row.get("kind") or {}).get("value")
                if key in counts:
                    counts[key] = int((row.get("count") or {}).get("value", 0))
            return counts, None
        except Exception:
            return empty, "semantic_count_query_failed"

    # ------------------------------------------------------------------
    # compilation and deterministic validation
    # ------------------------------------------------------------------

    def _compile(self, batch: ModelingBatchModel):
        findings: list[dict[str, Any]] = []
        prepared: dict[str, PreparedModelingCommand] = {}
        dependency_map = {item.client_item_id: set(item.depends_on or []) for item in batch.items}
        outputs: dict[str, dict[str, str]] = {}
        for item in batch.items:
            try:
                self.handlers.validate_payload_shape(item.command_kind, item.payload)
                outputs[item.client_item_id] = self.handlers.outputs_for(
                    batch_id=batch.id,
                    ontology_id=batch.ontology_id,
                    client_item_id=item.client_item_id,
                    command_kind=item.command_kind,
                    payload=item.payload,
                )
            except CommandCompilerError as exc:
                # R3.0-009 §8: compiler rejections surface as typed findings
                # carrying the machine-readable code, never as HTTP 500.
                code = getattr(exc, "code", None) or (
                    "forbidden_target_override"
                    if "Forbidden target" in str(exc)
                    else "unsupported_command_kind"
                    if "Unsupported Modeling" in str(exc)
                    else "unsupported_batch_variant"
                    if "unsupported_batch_variant" in str(exc)
                    else "invalid_command_payload"
                )
                findings.append(
                    _finding(
                        code,
                        "error",
                        str(exc),
                        item_ids=[item.client_item_id],
                        path=_payload_path(item.ordinal, exc),
                    )
                )
        known_ids = {item.client_item_id for item in batch.items}
        for item in batch.items:
            if item.client_item_id not in outputs:
                continue
            for dependency in list(dependency_map[item.client_item_id]):
                if dependency not in known_ids:
                    findings.append(
                        _finding(
                            "invalid_dependency",
                            "error",
                            f"Unknown dependency: {dependency}",
                            item_ids=[item.client_item_id],
                            path=["depends_on"],
                        )
                    )
            try:
                resolved, implicit = self._resolve_refs(item.payload, outputs, known_ids)
            except InvalidCommandPayload as exc:
                findings.append(
                    _finding(
                        "unresolved_item_ref",
                        "error",
                        str(exc),
                        item_ids=[item.client_item_id],
                        path=["payload"],
                    )
                )
                continue
            dependency_map[item.client_item_id].update(implicit)
            try:
                command = self.handlers.prepare(
                    batch_id=batch.id,
                    ontology_id=batch.ontology_id,
                    client_item_id=item.client_item_id,
                    command_kind=item.command_kind,
                    payload=resolved,
                )
                if item.command_kind == "delete_entity" and "impact_receipt" in command.payload:
                    receipt = _validate_delete_only_impact_receipt(
                        command.payload["impact_receipt"]
                    )
                    if command.payload.get("impact_receipt_digest") != receipt["receipt_digest"]:
                        raise InvalidCommandPayload(
                            "delete-only impact_receipt_digest does not match receipt"
                        )
                prepared[item.client_item_id] = command
                item.resource_outputs = command.outputs
            except (CommandCompilerError, KeyError, TypeError, ValueError) as exc:
                code = getattr(exc, "code", None) or (
                    str(exc).split(":", 1)[0]
                    if str(exc).startswith(
                        (
                            "invalid_operation_payload:",
                            "operation_secret_forbidden:",
                            "unsupported_operation_schema_version:",
                        )
                    )
                    else "invalid_command_payload"
                )
                findings.append(
                    _finding(
                        code,
                        "error",
                        str(exc),
                        item_ids=[item.client_item_id],
                        path=_payload_path(item.ordinal, exc),
                    )
                )
                continue
            self._validate_competency_questions(batch, item, findings)
            if not item.rationale:
                findings.append(
                    _finding(
                        "missing_rationale",
                        "info",
                        "Modeling Item has no rationale",
                        item_ids=[item.client_item_id],
                    )
                )

        groups = self._groups(dependency_map)
        all_effects = []
        for item_id, command in prepared.items():
            all_effects.extend(self.handlers.effects(item_id, command))
        for index, left in enumerate(all_effects):
            for right in all_effects[index + 1 :]:
                if left.item_id == right.item_id:
                    continue
                if (
                    left.resource_key == right.resource_key
                    and left.slot_key == right.slot_key
                    and left.operation == right.operation
                    and left.value_hash == right.value_hash
                ):
                    findings.append(
                        _finding(
                            "duplicate_effect",
                            "warning",
                            "Items contain the same normalized write effect",
                            item_ids=sorted({left.item_id, right.item_id}),
                        )
                    )
                elif self._effects_overlap(left, right) and (
                    left.cardinality == "single"
                    or right.cardinality == "single"
                    or left.operation == "delete"
                    or right.operation == "delete"
                ):
                    if self._multi_valued_statement_replacement(left, right):
                        # R4.0-007 F5/A6: switching a reference deletes the old
                        # statement and adds the new one in one atomic Batch.
                        continue
                    findings.append(
                        _finding(
                            "conflicting_item_effects",
                            "error",
                            "Items contain incompatible writes to the same semantic target",
                            item_ids=sorted({left.item_id, right.item_id}),
                        )
                    )
        # A single model also contains incoming definition/mapping references.
        # Reject new references to a resource removed by another item; do not erase
        # those definitions as an implicit entity-delete cascade.
        for delete_id, delete_command in prepared.items():
            if delete_command.compiled is None:
                continue
            removed = {subject for subject, predicate, obj, graph in delete_command.compiled.delta.deletes
                       if predicate == "?p" and obj == "?o" and not subject.startswith("?")}
            for insert_id, insert_command in prepared.items():
                if delete_id != insert_id and insert_command.compiled is not None and any(obj in removed for _, _, obj, _ in insert_command.compiled.delta.inserts):
                    findings.append(_finding("conflicting_item_effects", "error",
                        "An item references a resource deleted by another item",
                        item_ids=sorted({delete_id, insert_id})))
        return prepared, self._dedupe_findings(findings), groups, dependency_map

    @staticmethod
    def _multi_valued_statement_replacement(left, right) -> bool:
        """True for one concrete delete+insert pair replacing a statement.

        R4.0-007 F5/A6 switches a reference by removing the old relation
        statement and adding the new one in the same atomic Batch. On a
        multi-valued slot that pair has one defined outcome, so it is a declared
        replacement rather than two writers racing one target. The exemption
        stays narrow: same resource and slot, concrete statements only (no
        wildcard match or cascade delete), different objects, multi-valued on
        both sides. Deleting and re-adding the *same* statement stays a
        conflict because the merged delta would both remove and insert it.
        """
        if {left.operation, right.operation} != {"delete", "insert"}:
            return False
        if left.cardinality != "multi" or right.cardinality != "multi":
            return False
        if left.resource_key != right.resource_key or left.slot_key != right.slot_key:
            return False
        if left.value_hash == right.value_hash:
            return False
        return not (
            left.match_pattern
            or right.match_pattern
            or left.cascade_footprint
            or right.cascade_footprint
        )


    @staticmethod
    def _depends_transitively(
        later: str, earlier: str, dependency_map: dict[str, set[str]]
    ) -> bool:
        stack = [*dependency_map.get(later, ())]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == earlier:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(dependency_map.get(current, ()))
        return False

    def _validate_candidate_delta(
        self,
        batch: ModelingBatchModel,
        delta,
        prepared: dict[str, PreparedModelingCommand],
        selected: set[str],
    ) -> list[dict[str, Any]]:
        if delta.is_empty:
            return []
        if self.rdf_store is None:
            return [
                _finding(
                    "candidate_validation_failed",
                    "error",
                    "RDF store is unavailable for deterministic candidate validation",
                    scope="batch",
                )
            ]
        operation_commands = {
            item_id: prepared[item_id]
            for item_id in selected
            if item_id in prepared and prepared[item_id].command_kind.endswith("_operation")
        }
        current_by_graph: dict[str, Graph] = {}
        for item_id, command in operation_commands.items():
            graph_iri = command.compiled.target_graph_iris[0]
            if graph_iri not in current_by_graph:
                current = Graph()
                graph_exists = not hasattr(self.rdf_store, "graph_exists") or (
                    self.rdf_store.graph_exists(graph_iri)
                )
                content = self.rdf_store.get_graph(graph_iri, "turtle") if graph_exists else ""
                if content and content.strip():
                    current.parse(data=content, format="turtle")
                current_by_graph[graph_iri] = current
            operation_iri = command.compiled.metadata.get("operation_iri")
            exists = operation_iri is not None and any(
                current_by_graph[graph_iri].triples((URIRef(operation_iri), None, None))
            )
            if command.command_kind == "create_operation" and exists:
                return [
                    _finding(
                        "resource_already_exists",
                        "error",
                        "Operation already exists; use update_operation",
                        item_ids=[item_id],
                    )
                ]
            if command.command_kind != "create_operation" and not exists:
                return [
                    _finding(
                        "operation_not_found",
                        "error",
                        "Operation was not found in the target Ontology",
                        item_ids=[item_id],
                    )
                ]
        relational_findings = self._validate_relational_mapping_commands(batch, prepared, selected)
        if relational_findings:
            return relational_findings
        compiled = CompiledCommand(
            command_kind="modeling_batch",
            delta=delta,
            object_kind="modeling_batch",
            source_ids=[],
            target_graph_iris=delta.affected_graph_iris(),
            metadata={"ontology_id": batch.ontology_id},
        )
        try:
            CanonicalSemanticWriteService(
                self.session, self.rdf_store, self.settings
            ).validate_compiled_command(
                compiled,

            )
        except CanonicalSemanticWriteError as exc:
            code = getattr(exc, "code", "candidate_validation_failed")
            item_ids = []
            if str(code).startswith("operation_") or code in {
                "invalid_operation_payload",
                "unsupported_operation_schema_version",
            }:
                item_ids = sorted(
                    item_id
                    for item_id in selected
                    if prepared.get(item_id)
                    and prepared[item_id].command_kind.endswith("_operation")
                )
            return [
                _finding(
                    code,
                    "error",
                    str(exc),
                    item_ids=item_ids,
                    scope="item" if item_ids else "batch",
                    path=self._error_path(batch, exc, item_ids),
                )
            ]
        return []

    @staticmethod
    def _error_path(batch, exc: BaseException, item_ids: list[str]) -> list[str | int]:
        """Qualify a canonical-write error path with the offending item (D5)."""
        relative = list(getattr(exc, "path", ()) or ())
        if not item_ids or not relative:
            return relative
        first = next((item for item in batch.items if item.client_item_id == item_ids[0]), None)
        if first is None:
            return relative
        fields = relative[1:] if relative[0] == "payload" else relative
        return ["items", first.ordinal, "payload", *fields]

    def _validate_relational_mapping_commands(
        self,
        batch: ModelingBatchModel,
        prepared: dict[str, PreparedModelingCommand],
        selected: set[str],
    ) -> list[dict[str, Any]]:
        """Check the final delta, including explicit cross-graph reverse dependencies."""
        commands = [
            prepared[item_id]
            for item_id in sorted(selected)
            if item_id in prepared and prepared[item_id].compiled is not None
        ]
        if not commands:
            return []
        if self.rdf_store is None:
            return [
                _finding(
                    "candidate_validation_failed",
                    "error",
                    "RDF store is unavailable for mapping validation",
                    scope="batch",
                )
            ]
        from app.services.semantic_mapping_state import mapping_state, mapping_write_findings

        delta = union_delta(commands)
        _projects, _owners, before, _after, _scopes = mapping_state(
            self.session, self.rdf_store, self.settings, delta, batch.ontology_id
        )
        original = Graph()
        for graph in before.values():
            for triple in graph:
                original.add(triple)
        findings = []
        created = set()
        subjects = {}
        for item_id in sorted(selected):
            command = prepared.get(item_id)
            if command is None or command.compiled is None:
                continue
            if command.command_kind not in _RELATIONAL_MAPPING_COMMAND_KINDS:
                continue
            iri = _relational_resource_iri(command.compiled.metadata)
            if not iri:
                continue
            subjects[iri] = item_id
            exists = any(original.triples((URIRef(iri), None, None)))
            if command.command_kind.startswith("create_"):
                if exists or iri in created:
                    findings.append(
                        _finding(
                            "resource_already_exists",
                            "error",
                            "Relational mapping resource already exists; use the update command",
                            item_ids=[item_id],
                            path=["payload"],
                        )
                    )
                created.add(iri)
            elif not exists and iri not in created:
                findings.append(
                    _finding(
                        "resource_not_found",
                        "error",
                        "Relational mapping resource was not found in the target Ontology",
                        item_ids=[item_id],
                        path=["payload"],
                    )
                )
        for finding in mapping_write_findings(
            self.session, self.rdf_store, self.settings, delta, batch.ontology_id
        ):
            item_id = subjects.get(str(finding.get("subject", "")))
            findings.append(
                _finding(
                    finding["code"],
                    finding.get("severity", "error"),
                    finding["message"],
                    item_ids=[item_id] if item_id else sorted(selected),
                    path=["payload", *finding.get("path", [])],
                    resource_iri=finding.get("subject"),
                )
            )
        return findings


    @staticmethod
    def _effects_overlap(left, right) -> bool:
        if left.resource_key == right.resource_key and (
            left.slot_key == right.slot_key or left.slot_key == "*" or right.slot_key == "*"
        ):
            return True
        left_prefixes = set(left.cascade_footprint)
        right_prefixes = set(right.cascade_footprint)
        for footprint in left_prefixes:
            prefix = footprint.removesuffix("*")
            if right.resource_key.startswith(prefix.rstrip(":")):
                return True
        for footprint in right_prefixes:
            prefix = footprint.removesuffix("*")
            if left.resource_key.startswith(prefix.rstrip(":")):
                return True
        # Entity cascade deletes also match relations where the entity is the
        # object, which is not encoded in the other effect's resource key.
        return bool(
            (
                left.match_pattern
                and left.match_pattern.startswith("?s ")
                and left.object_key == right.object_key
            )
            or (
                right.match_pattern
                and right.match_pattern.startswith("?s ")
                and right.object_key == left.object_key
            )
        )

    def _resolve_refs(
        self, value: Any, outputs: dict[str, dict[str, str]], known_ids: set[str]
    ) -> tuple[Any, set[str]]:
        dependencies: set[str] = set()
        if isinstance(value, dict):
            if set(value) == {"resource_id"}:
                return value["resource_id"], dependencies
            if set(value) == {"item_ref"} and isinstance(value["item_ref"], dict):
                ref = value["item_ref"]
                item_id = ref.get("client_item_id")
                output = ref.get("output")
                if item_id not in known_ids or output not in {"resource_id", "resource_iri"}:
                    raise InvalidCommandPayload("Unknown Item reference or output")
                if output not in outputs.get(str(item_id), {}):
                    raise InvalidCommandPayload("Referenced Item does not expose requested output")
                dependencies.add(str(item_id))
                return outputs[str(item_id)][str(output)], dependencies
            result = {}
            for key, nested in value.items():
                resolved, found = self._resolve_refs(nested, outputs, known_ids)
                result[key] = resolved
                dependencies.update(found)
            return result, dependencies
        if isinstance(value, list):
            result = []
            for nested in value:
                resolved, found = self._resolve_refs(nested, outputs, known_ids)
                result.append(resolved)
                dependencies.update(found)
            return result, dependencies
        return value, dependencies

    def _validate_competency_questions(
        self,
        batch: ModelingBatchModel,
        item: ModelingItemModel,
        findings: list[dict[str, Any]],
    ) -> None:
        for question_id in item.competency_question_ids:
            question = self.session.get(CompetencyQuestionModel, question_id)
            if question is None or question.project_id != batch.project_id:
                findings.append(
                    _finding(
                        "competency_question_not_found",
                        "error",
                        "Competency Question was not found in this Project",
                        item_ids=[item.client_item_id],
                        question_id=question_id,
                    )
                )
            elif question.ontology_id and question.ontology_id != batch.ontology_id:
                findings.append(
                    _finding(
                        "competency_question_scope_mismatch",
                        "error",
                        "Competency Question does not apply to this Ontology",
                        item_ids=[item.client_item_id],
                        question_id=question_id,
                    )
                )

    @staticmethod
    def _groups(dependencies: dict[str, set[str]]) -> list[dict[str, Any]]:
        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        low: dict[str, int] = {}
        components: list[list[str]] = []

        def visit(node: str) -> None:
            nonlocal index
            indices[node] = low[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)
            for target in sorted(dependencies.get(node, set())):
                if target not in dependencies:
                    continue
                if target not in indices:
                    visit(target)
                    low[node] = min(low[node], low[target])
                elif target in on_stack:
                    low[node] = min(low[node], indices[target])
            if low[node] == indices[node]:
                component = []
                while True:
                    target = stack.pop()
                    on_stack.remove(target)
                    component.append(target)
                    if target == node:
                        break
                components.append(sorted(component))

        for node in sorted(dependencies):
            if node not in indices:
                visit(node)
        item_to_group = {}
        for members in components:
            group_id = str(uuid5(NAMESPACE_URL, "modeling-group:" + ":".join(members)))
            for member in members:
                item_to_group[member] = group_id
        return [
            {
                "atomic_group_id": item_to_group[members[0]],
                "client_item_ids": members,
                "cyclic": len(members) > 1 or members[0] in dependencies.get(members[0], set()),
                "depends_on_group_ids": sorted(
                    {
                        item_to_group[target]
                        for member in members
                        for target in dependencies.get(member, set())
                        if target in item_to_group
                        and item_to_group[target] != item_to_group[members[0]]
                    }
                ),
            }
            for members in sorted(components, key=lambda value: value[0])
        ]

    def _select_items(self, batch, mode, findings, groups, dependency_map):
        direct_failed = {
            item_id
            for finding in findings
            if finding["blocking"]
            for item_id in finding["client_item_ids"]
        }
        group_by_item = {item_id: group for group in groups for item_id in group["client_item_ids"]}
        failed_groups = {
            group_by_item[item_id]["atomic_group_id"]
            for item_id in direct_failed
            if item_id in group_by_item
        }
        changed = True
        while changed:
            changed = False
            for group in groups:
                if group["atomic_group_id"] not in failed_groups and any(
                    dep in failed_groups for dep in group["depends_on_group_ids"]
                ):
                    failed_groups.add(group["atomic_group_id"])
                    changed = True
        statuses: dict[str, str] = {}
        has_error = bool(direct_failed)
        for item in batch.items:
            group_failed = (
                group_by_item.get(item.client_item_id, {}).get("atomic_group_id") in failed_groups
            )
            if item.client_item_id in direct_failed:
                statuses[item.client_item_id] = "failed"
            elif group_failed:
                statuses[item.client_item_id] = "blocked"
                findings.append(
                    _finding(
                        "dependency_failed",
                        "error",
                        "A dependency or Atomic Dependency Group failed",
                        item_ids=[item.client_item_id],
                    )
                )
            elif mode == "apply_atomic" and has_error:
                statuses[item.client_item_id] = "not_applied"
            else:
                statuses[item.client_item_id] = "validated" if mode == "dry_run" else "applied"
        selected = {
            item_id
            for item_id, status in statuses.items()
            if status in ({"validated"} if mode == "dry_run" else {"applied"})
        }
        if mode == "apply_atomic" and has_error:
            selected.clear()
        return selected, statuses

    # ------------------------------------------------------------------
    # write, recovery, and immutable records
    # ------------------------------------------------------------------

    def _establish_fence(self, attempt, batch, authorization):
        attempt.status = "applying"
        batch.status = "applying"
        attempt.execution_claim_id = _id()
        now = self._now()
        attempt.execution_claim_heartbeat_at = now
        attempt.execution_claim_expires_at = now + timedelta(
            seconds=self.settings.modeling_batch_execution_claim_ttl_seconds
        )
        self.session.add(
            OntologyWriteFenceModel(
                ontology_id=batch.ontology_id,
                attempt_id=attempt.id,
                build_session_id=batch.build_session_id,
                lease_revision=int(
                    authorization.get("lease_revision") or attempt.lease_revision or 0
                ),
            )
        )

    def _execute(
        self,
        attempt,
        auth,
        *,
        claim_id: str | None,
        rdf_already_applied: bool = False,
        created_batch=False,
        created_attempt=False,
    ):
        from app.services.checkpoint_archive import lock_projects

        batch = attempt.batch
        plan = attempt.operation_plan
        project_id = None
        try:
            project_id = self.session.scalar(
                select(OntologyModel.project_id).where(OntologyModel.id == batch.ontology_id)
            )
            lock_projects(self.session, [project_id] if project_id else [])
            self.session.scalar(
                select(OntologyModel).where(OntologyModel.id == batch.ontology_id).with_for_update()
            )
            commands = self._commands_from_plan(batch.ontology_id, plan)
            rdf_commands = [
                command for command in commands.values() if command.compiled is not None
            ]
            if rdf_commands:
                if self.rdf_store is None:
                    raise RuntimeError("RDF store is unavailable")
                delta = union_delta(rdf_commands)
                compiled = CompiledCommand(
                    command_kind="modeling_batch",
                    delta=delta,
                    object_kind="modeling_batch",
                    source_ids=sorted(plan["selected_client_item_ids"]),
                    target_graph_iris=delta.affected_graph_iris(),
                    metadata={"ontology_id": batch.ontology_id},
                )
                item_by_client = {item.client_item_id: item for item in batch.items}
                modeling_item_effects: dict[tuple[str, str, str, str], list[str]] = {}
                for client_item_id, command in commands.items():
                    if command.compiled is None:
                        continue
                    item = item_by_client[client_item_id]
                    for quad in command.compiled.delta.inserts:
                        modeling_item_effects.setdefault(quad, []).append(item.id)
                existing_audit = self.session.get(SemanticEditAuditModel, attempt.audit_id)
                if not (rdf_already_applied and existing_audit is not None):
                    try:
                        result = CanonicalSemanticWriteService(
                            self.session, self.rdf_store, self.settings
                        ).apply_compiled_command(
                            compiled,
                            ontology_id=attempt.ontology_id,
                            actor=auth.actor,
                            reason=f"Modeling Batch {batch.id}",
                            commit=False,
                            audit_id=attempt.audit_id,
                            fence_attempt_id=attempt.id,
                            write_rdf=not rdf_already_applied,
                            modeling_item_effects=modeling_item_effects,
                        )
                    except (CanonicalValidationError, CanonicalSemanticWriteError) as exc:
                        if rdf_already_applied:
                            # A recovery failure cannot erase evidence of an existing write.
                            raise
                        # Deterministic pre-write rejection (D13): the canonical
                        # pipeline validates before it writes, so nothing reached
                        # the store and reconciliation is trivial. It must fail
                        # the attempt instead of entering recovery, where an
                        # unfixed payload would only re-fail and a missing
                        # optional graph could escalate to a write fence.
                        self.session.rollback()
                        lock_projects(self.session, [project_id] if project_id else [])
                        self.session.scalar(
                            select(OntologyModel)
                            .where(OntologyModel.id == batch.ontology_id)
                            .with_for_update()
                        )
                        current = self.session.scalar(
                            select(ModelingBatchAttemptModel)
                            .where(ModelingBatchAttemptModel.id == attempt.id)
                            .with_for_update()
                        )
                        if current is None:
                            raise
                        self._fail_attempt_without_side_effects(
                            current,
                            code=getattr(exc, "code", "candidate_validation_failed"),
                            message=str(exc)[:1000],
                            violations=getattr(exc, "validation_result", {}).get("violations")
                            or [],
                        )
                        self.session.commit()
                        return self._attempt_response(current, created_batch, created_attempt)
                    attempt.audit_id = result["audit_id"]
            self.session.flush()
            locked = self.session.scalar(
                select(ModelingBatchAttemptModel)
                .where(ModelingBatchAttemptModel.id == attempt.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if locked is None or locked.execution_claim_id != claim_id:
                raise _ExecutionClaimLost("Execution claim was superseded")
            self._finalize_success(locked)
            self.session.commit()
            attempt = locked
            try:
                retrieval_indexes = SemanticRetrievalCoordinator(
                    self.session, self.rdf_store, self.settings
                ).rebuild_affected(ontology_ids=[batch.ontology_id])
            except Exception:
                retrieval_indexes = [
                    {
                        "ontology_id": batch.ontology_id,
                        "write_applied": True,
                        "status": "failed",
                        "warning": "retrieval_index_failed",
                    }
                ]
            attempt.recovery_detail = {
                **(attempt.recovery_detail or {}),
                "retrieval_indexes": retrieval_indexes,
            }
            self.session.commit()
        except _ExecutionClaimLost:
            self.session.rollback()
            current = self.session.get(ModelingBatchAttemptModel, attempt.id)
            if current is None:
                raise
            return self._attempt_response(current, created_batch, created_attempt)
        except Exception as exc:
            self.session.rollback()
            lock_projects(self.session, [project_id] if project_id else [])
            self.session.scalar(
                select(OntologyModel).where(OntologyModel.id == batch.ontology_id).with_for_update()
            )
            current = self.session.scalar(
                select(ModelingBatchAttemptModel)
                .where(ModelingBatchAttemptModel.id == attempt.id)
                .with_for_update()
            )
            if current is None:
                raise
            if current.status in TERMINAL_ATTEMPT_STATUSES:
                return self._attempt_response(current, created_batch, created_attempt)
            if current.execution_claim_id != claim_id:
                return self._attempt_response(current, created_batch, created_attempt)
            current.status = "recovering"
            current.batch.status = "recovering"
            current.recovery_state = "pending"
            detail = dict(current.recovery_detail or {})
            history = list(detail.get("history", []))
            history.append(
                {
                    "at": self._now().isoformat(),
                    "code": "uncertain_execution",
                    "message": str(exc)[:1000],
                }
            )
            current.recovery_detail = {"history": history, "safe_to_retry": True}
            current.execution_claim_id = None
            current.execution_claim_expires_at = None
            self.session.commit()
            return self._attempt_response(current, created_batch, created_attempt)
        return self._attempt_response(attempt, created_batch, created_attempt)

    def _resume_attempt(self, attempt, auth):
        from app.services.checkpoint_archive import lock_projects

        ontology_id = attempt.batch.ontology_id
        project_id = self.session.scalar(
            select(OntologyModel.project_id).where(OntologyModel.id == ontology_id)
        )
        lock_projects(self.session, [project_id] if project_id else [])
        self.session.scalar(
            select(OntologyModel).where(OntologyModel.id == ontology_id).with_for_update()
        )
        from app.services.semantic_mapping_state import (
            MappingWriteError,
            mapping_write_relevant,
            project_fence_check,
        )

        try:
            if self.rdf_store is not None and mapping_write_relevant(
                self.session,
                self.rdf_store,
                self.settings,
                RdfGraphDelta(**attempt.normalized_delta),
                ontology_id,
            ):
                project_fence_check(self.session, [project_id] if project_id else [], attempt.id)
        except MappingWriteError as exc:
            raise ModelingBatchError(exc.code, str(exc)) from exc
        attempt = self.session.scalar(
            select(ModelingBatchAttemptModel)
            .where(ModelingBatchAttemptModel.id == attempt.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if attempt is None:
            raise ModelingBatchError(
                "modeling_attempt_not_found", "Modeling Attempt was not found", status_code=404
            )
        now = self._now()
        history = list((attempt.recovery_detail or {}).get("history", []))
        observation = self._observe_recovery_state(attempt)
        if len(history) >= self.settings.modeling_batch_recovery_max_steps:
            reconcilable = observation["state"] == "not_applied"
            if reconcilable:
                attempt.status = "failed"
                attempt.batch.status = "failed"
                attempt.completed_at = now
                attempt.batch.terminal_at = now
                attempt.recovery_state = "failed_without_side_effects"
                fence = self.session.get(OntologyWriteFenceModel, attempt.batch.ontology_id)
                if fence and fence.attempt_id == attempt.id:
                    self.session.delete(fence)
            else:
                attempt.recovery_state = "recovery_requires_intervention"
            attempt.recovery_detail = {
                **(attempt.recovery_detail or {}),
                # A reconcilable exit releases the write fence, so submitting a
                # corrected batch is safe; only the drifted case stays fenced.
                "safe_to_retry": reconcilable,
                "message": "Automatic recovery step limit reached",
                "observation": observation,
                **({"reason_code": observation["reason"]} if observation.get("reason") else {}),
            }
            self.session.commit()
            return self._attempt_response(attempt, False, False)
        if not self._recovery_revision_guard(attempt):
            attempt.status = "recovering"
            attempt.batch.status = "recovering"
            attempt.recovery_state = "recovery_requires_intervention"
            attempt.recovery_detail = {
                **(attempt.recovery_detail or {}),
                "safe_to_retry": False,
                "message": "Observed graph revision is not attributable to the persisted plan",
            }
            self.session.commit()
            return self._attempt_response(attempt, False, False)
        if observation["state"] in {"unexpected", "partial_or_drifted"}:
            attempt.status = "recovering"
            attempt.batch.status = "recovering"
            attempt.recovery_state = "recovery_requires_intervention"
            attempt.recovery_detail = {
                **(attempt.recovery_detail or {}),
                "safe_to_retry": False,
                "message": (
                    "Delete-only RDF state is partial or drifted"
                    if observation["state"] == "partial_or_drifted"
                    else "RDF state contains effects outside the persisted operation plan"
                ),
                "observation": observation,
            }
            self.session.commit()
            return self._attempt_response(attempt, False, False)
        expiry = (
            self._aware(attempt.execution_claim_expires_at)
            if attempt.execution_claim_expires_at
            else None
        )
        if expiry and expiry > now and attempt.execution_claim_id:
            response = self._attempt_response(attempt, False, False)
            response["recovery"]["retry_after"] = expiry
            return response
        attempt.status = "recovering"
        attempt.batch.status = "recovering"
        attempt.recovery_state = "running"
        attempt.execution_claim_id = _id()
        attempt.execution_claim_heartbeat_at = now
        attempt.execution_claim_expires_at = now + timedelta(
            seconds=self.settings.modeling_batch_execution_claim_ttl_seconds
        )
        attempt.recovery_detail = {
            **(attempt.recovery_detail or {}),
            "observation": observation,
        }
        claim_id = attempt.execution_claim_id
        self.session.commit()
        return self._execute(
            attempt,
            auth,
            claim_id=claim_id,
            rdf_already_applied=observation["state"] == "applied",
        )

    def _observe_delete_only_recovery(self, attempt) -> dict[str, Any] | None:
        """Observe a receipt-bound Phase-B delete without inferring semantics.

        A generic graph-hash observation cannot distinguish a fully unapplied
        delete from one that removed only part of an entity's incident edge
        set.  When the persisted operation plan carries a complete impact
        receipt, compare the exact before statement set with the current
        subject/object incident set.  Any mixed, malformed, or newly observed
        edge is explicitly ``partial_or_drifted`` and therefore never retried.
        """

        metadata = (attempt.operation_plan or {}).get("delete_only_recovery")
        if not isinstance(metadata, dict):
            return None
        entries = metadata.get("receipts")
        if metadata.get("schema_version") != "r2-3-003-delete-impact/v1" or not isinstance(
            entries, list
        ):
            return {"state": "partial_or_drifted", "reason": "delete_only_receipt_metadata_invalid"}
        if self.rdf_store is None or not hasattr(self.rdf_store, "get_graph"):
            return {"state": "partial_or_drifted", "reason": "rdf_observation_unavailable"}

        def canonical_statement(subject, predicate, obj, graph_iri) -> dict[str, Any]:
            if isinstance(subject, URIRef):
                subject_value = str(subject)
            else:
                subject_value = str(subject)
            if isinstance(obj, URIRef):
                object_value = str(obj)
                object_kind = "uri"
            elif hasattr(obj, "datatype"):
                object_value = str(obj)
                object_kind = "literal"
            else:
                object_value = str(obj)
                object_kind = "bnode"
            return {
                "subject": subject_value,
                "predicate": str(predicate),
                "object": object_value,
                "object_kind": object_kind,
                "graph": graph_iri,
            }

        states: list[str] = []
        details: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                return {
                    "state": "partial_or_drifted",
                    "reason": "delete_only_receipt_entry_invalid",
                }
            receipt = entry.get("impact_receipt")
            target_iri = entry.get("entity_iri")
            if (
                not isinstance(receipt, dict)
                or not isinstance(target_iri, str)
                or not target_iri
                or receipt.get("complete") is not True
            ):
                return {
                    "state": "partial_or_drifted",
                    "reason": "delete_only_receipt_entry_invalid",
                }
            before = receipt.get("statements")
            if not isinstance(before, list):
                return {"state": "partial_or_drifted", "reason": "delete_only_before_set_invalid"}
            graph_iris = {
                item.get("graph")
                for item in before
                if isinstance(item, dict) and isinstance(item.get("graph"), str)
            }
            if not graph_iris:
                graph_iris = {
                    graph.get("graph_iri")
                    for graph in (attempt.target_snapshot or {}).get("graphs", [])
                    if isinstance(graph, dict) and isinstance(graph.get("graph_iri"), str)
                }
            graphs: dict[str, Graph] = {}
            try:
                graphs = self._load_observed_graphs(sorted(graph_iris))
            except Exception as exc:
                return {
                    "state": "partial_or_drifted",
                    "reason": "delete_only_observation_failed",
                    "error": str(exc),
                }
            after: list[dict[str, Any]] = []
            for graph_iri, graph in graphs.items():
                for subject, predicate, obj in graph:
                    if str(subject) == target_iri or str(obj) == target_iri:
                        after.append(canonical_statement(subject, predicate, obj, graph_iri))
            before_hashes = {_hash(item) for item in before if isinstance(item, dict)}
            after_hashes = {_hash(item) for item in after}
            planned_deletes = (attempt.operation_plan or {}).get("delta", {}).get("deletes")
            expected_after = set()
            if isinstance(planned_deletes, list):
                for item in before:
                    def removes(quad):
                        terms = (item["subject"], item["predicate"], item["object"])
                        return quad[3] == item["graph"] and all(
                            term.startswith("?") or str(from_n3(term)) == actual
                            for term, actual in zip(quad[:3], terms)
                        )
                    if not any(removes(quad) for quad in planned_deletes):
                        expected_after.add(_hash(item))
            if after_hashes == expected_after and after_hashes != before_hashes:
                state = "applied"
            elif after_hashes == before_hashes:
                state = "not_applied"
            else:
                state = "partial_or_drifted"
            states.append(state)
            details.append(
                {
                    "client_item_id": entry.get("client_item_id"),
                    "state": state,
                    "before_statement_count": len(before_hashes),
                    "after_statement_count": len(after_hashes),
                }
            )
        if not states:
            return {"state": "partial_or_drifted", "reason": "delete_only_receipts_empty"}
        if any(state == "partial_or_drifted" for state in states):
            state = "partial_or_drifted"
        elif all(state == "applied" for state in states):
            state = "applied"
        elif all(state == "not_applied" for state in states):
            state = "not_applied"
        else:
            state = "partial_or_drifted"
        return {"state": state, "delete_only": True, "entries": details}

    def _load_observed_graphs(self, graph_iris: list[str]) -> dict[str, Graph]:
        """Read the named graphs a recovery observation must compare.

        A graph the store does not have is an empty graph, not an observation
        failure (AGENTS.md T0 / D13): lazy materialization leaves workspace
        graphs such as ``…/shapes/{ont}/custom`` un-created, and reading that
        as a store error escalated a reconcilable failure into a permanent
        ``ontology_write_fenced``. Real store failures still propagate.
        """
        graphs: dict[str, Graph] = {}
        exists = getattr(self.rdf_store, "graph_exists", None)
        for graph_iri in graph_iris:
            graph = Graph()
            if exists is None or exists(graph_iri):
                content = self.rdf_store.get_graph(graph_iri, "turtle")
                if content:
                    graph.parse(data=content, format="turtle")
            graphs[graph_iri] = graph
        return graphs

    def _observe_recovery_state(self, attempt) -> dict[str, Any]:
        delete_only = self._observe_delete_only_recovery(attempt)
        if delete_only is not None:
            return delete_only
        delta = (attempt.operation_plan or {}).get("delta", {})
        inserts = [tuple(quad) for quad in delta.get("inserts", [])]
        deletes = [tuple(quad) for quad in delta.get("deletes", [])]
        if (
            not inserts
            and not deletes
            and not delta.get("clear_graphs")
            and not delta.get("drop_graphs")
        ):
            return {"state": "applied", "reason": "no_rdf_effects"}
        if self.rdf_store is None or not hasattr(self.rdf_store, "get_graph"):
            return {"state": "unexpected", "reason": "rdf_observation_unavailable"}
        graphs: dict[str, Graph] = {}
        try:
            graphs = self._load_observed_graphs(sorted({quad[3] for quad in [*inserts, *deletes]}))
        except Exception as exc:
            return {"state": "unexpected", "reason": "rdf_observation_failed", "error": str(exc)}

        current_hashes = {
            graph_iri: self._hash_rdf_graph(graph) for graph_iri, graph in graphs.items()
        }
        before_hashes = {
            graph["graph_iri"]: graph.get("content_hash_before")
            for graph in attempt.target_snapshot.get("graphs", [])
            if graph.get("graph_iri") in current_hashes
        }
        # Graphs the plan itself targets (for example the lazily created custom
        # shapes sub-graph) are not workspace members, so the plan carries their
        # pre-write state; persisted snapshot entries stay authoritative (D13).
        before_hashes = {
            **(attempt.operation_plan or {}).get("before_graph_hashes", {}),
            **before_hashes,
        }
        expected_hashes = (attempt.operation_plan or {}).get("expected_graph_hashes", {})
        if expected_hashes and all(
            current_hashes.get(graph_iri) == expected_hash
            for graph_iri, expected_hash in expected_hashes.items()
        ):
            return {"state": "applied", "graph_hashes": current_hashes}
        if before_hashes and all(
            current_hashes.get(graph_iri) == before_hash
            for graph_iri, before_hash in before_hashes.items()
        ):
            return {"state": "not_applied", "graph_hashes": current_hashes}
        if expected_hashes:
            return {
                "state": "unexpected",
                "reason": "graph_hash_outside_persisted_plan",
                "graph_hashes": current_hashes,
            }

        insert_terms = {
            (self._rdf_term(s), self._rdf_term(p), self._rdf_term(o), graph_iri)
            for s, p, o, graph_iri in inserts
        }
        present_inserts = {
            quad for quad in insert_terms if quad[:3] in graphs.get(quad[3], Graph())
        }
        unexpected_matches = 0
        for subject, predicate, obj, graph_iri in deletes:
            pattern = tuple(
                None if value.startswith("?") else self._rdf_term(value)
                for value in (subject, predicate, obj)
            )
            for triple in graphs.get(graph_iri, Graph()).triples(pattern):
                if (*triple, graph_iri) not in insert_terms:
                    unexpected_matches += 1
        all_inserts = len(present_inserts) == len(insert_terms)
        if all_inserts and unexpected_matches == 0:
            return {
                "state": "applied",
                "present_inserts": len(present_inserts),
                "unexpected_delete_matches": 0,
            }
        if not present_inserts:
            return {
                "state": "not_applied",
                "present_inserts": 0,
                "unexpected_delete_matches": unexpected_matches,
            }
        return {
            "state": "unexpected"
            if expected_hashes or unexpected_matches
            else "partially_observed",
            "present_inserts": len(present_inserts),
            "expected_inserts": len(insert_terms),
            "unexpected_delete_matches": unexpected_matches,
        }

    @staticmethod
    def _rdf_term(value: str):
        return from_n3(value)

    def _affected_graph_states(self, delta) -> dict[str, Graph]:
        """Read every graph the delta touches; a missing graph is empty (D13)."""
        graphs: dict[str, Graph] = {}
        for graph_iri in delta.affected_graph_iris():
            graph = Graph()
            graph_exists = not hasattr(self.rdf_store, "graph_exists") or (
                self.rdf_store.graph_exists(graph_iri)
            )
            content = self.rdf_store.get_graph(graph_iri, "turtle") if graph_exists else ""
            if content:
                graph.parse(data=content, format="turtle")
            graphs[graph_iri] = graph
        return graphs

    def _before_graph_hashes(self, delta) -> dict[str, str]:
        """Hash of each affected graph before the plan's writes (D13).

        Workspace graphs such as ``…/shapes/{ont}/custom`` may not exist yet,
        so their before state is the empty graph. Recovery compares against it
        to prove "nothing was applied" instead of reporting a hash outside the
        persisted plan.
        """
        if delta.is_empty or self.rdf_store is None or not hasattr(self.rdf_store, "get_graph"):
            return {}
        graphs = self._affected_graph_states(delta)
        for subject, predicate, obj, graph_iri in delta.deletes:
            pattern = tuple(
                None if value.startswith("?") else self._rdf_term(value)
                for value in (subject, predicate, obj)
            )
            graphs[graph_iri].remove(pattern)
        return {graph_iri: self._hash_rdf_graph(graph) for graph_iri, graph in graphs.items()}

    def _expected_graph_hashes(self, delta) -> dict[str, str]:
        if delta.is_empty or self.rdf_store is None or not hasattr(self.rdf_store, "get_graph"):
            return {}
        graphs = self._affected_graph_states(delta)
        for graph_iri in (*delta.clear_graphs, *delta.drop_graphs):
            graphs[graph_iri] = Graph()
        for subject, predicate, obj, graph_iri in delta.deletes:
            pattern = tuple(
                None if value.startswith("?") else self._rdf_term(value)
                for value in (subject, predicate, obj)
            )
            graphs[graph_iri].remove(pattern)
        for subject, predicate, obj, graph_iri in delta.inserts:
            graphs[graph_iri].add(
                (self._rdf_term(subject), self._rdf_term(predicate), self._rdf_term(obj))
            )
        return {graph_iri: self._hash_rdf_graph(graph) for graph_iri, graph in graphs.items()}

    @staticmethod
    def _hash_rdf_graph(graph: Graph) -> str:
        rows = sorted(
            f"{subject.n3()} {predicate.n3()} {obj.n3()} ." for subject, predicate, obj in graph
        )
        return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()

    def _recovery_revision_guard(self, attempt) -> bool:
        # Old hash-bound attempts stay historical; recovery cannot assume they
        # were prepared against the new revision contract.
        before = attempt.model_revision_before
        if before is None:
            return False
        current = self.model_revisions.version_for(attempt.batch.ontology_id)
        if current == before:
            return True
        if current != before + 1:
            return False
        ontology = self.session.get(OntologyModel, attempt.batch.ontology_id)
        audit_revision = self.session.scalar(
            select(SemanticGraphRevisionModel).where(
                SemanticGraphRevisionModel.graph_iri == ontology.model_graph_iri
            )
        )
        return audit_revision is not None and audit_revision.last_edit_audit_id == attempt.audit_id

    def _commands_from_plan(self, ontology_id, plan):
        commands = {}
        for item_id, entry in plan.get("commands", {}).items():
            commands[item_id] = self.handlers.prepare(
                batch_id="persisted-plan",
                ontology_id=ontology_id,
                client_item_id=item_id,
                command_kind=entry["command_kind"],
                payload=entry["payload"],
            )
        return commands


    def _fail_attempt_without_side_effects(
        self, attempt, *, code: str, message: str, violations: list[dict[str, Any]]
    ) -> None:
        """Terminate an attempt whose RDF write was rejected before it started.

        The caller has rolled back, so the attempt is back at its persisted
        state while the ontology still carries this attempt's write fence. The
        fence must be released here: a deterministic rejection is reconcilable
        (nothing was written) and must never turn into
        ``recovery_requires_intervention`` / ``ontology_write_fenced`` (D13).
        """
        now = self._now()
        attempt.status = "failed"
        attempt.batch.status = "failed"
        attempt.completed_at = now
        attempt.batch.terminal_at = now
        attempt.recovery_state = "failed_without_side_effects"
        attempt.recovery_detail = {
            **(attempt.recovery_detail or {}),
            "safe_to_retry": True,
            "reason_code": code,
            "message": message,
            "violations": violations,
        }
        selected = attempt.operation_plan.get("selected_client_item_ids", [])
        new_findings = []
        for violation in violations or [{"code": code, "message": message}]:
            subject = violation.get("subject")
            item_ids = [
                key
                for key, command in attempt.operation_plan.get("commands", {}).items()
                if subject and command.get("outputs", {}).get("resource_iri") == subject
            ]
            new_findings.append(
                _finding(
                    violation.get("code", code),
                    "error",
                    violation.get("message", message),
                    item_ids=item_ids or selected,
                    path=["payload", *violation.get("path", [])],
                    retryable=code == "mapping_reference_write_fenced",
                )
            )
        attempt.findings = self._fingerprint_findings(
            attempt.id, [*(attempt.findings or []), *new_findings]
        )
        for result in attempt.item_results:
            if result.client_item_id in selected:
                result.status = "not_applied"
                result.finding_codes = list(dict.fromkeys([*(result.finding_codes or []), code]))
        fence = self.session.get(OntologyWriteFenceModel, attempt.batch.ontology_id)
        if fence and fence.attempt_id == attempt.id:
            self.session.delete(fence)
        attempt.execution_claim_id = None
        attempt.execution_claim_expires_at = None

    def _finalize_success(self, attempt):
        now = self._now()
        has_failure = any(result.status in {"failed", "blocked"} for result in attempt.item_results)
        attempt.status = "partially_applied" if has_failure else "applied"
        attempt.batch.status = attempt.status
        attempt.completed_at = now
        attempt.batch.terminal_at = now
        attempt.recovery_state = (
            "converged" if attempt.recovery_state != "not_required" else "not_required"
        )
        attempt.model_revision_after = self.model_revisions.version_for(
            attempt.batch.ontology_id
        )
        after = self._target_snapshot(attempt.batch.ontology_id)
        before_graphs = {
            graph["role"]: graph for graph in attempt.target_snapshot.get("graphs", [])
        }
        attempt.target_snapshot = {
            **attempt.target_snapshot,
            "model_revision_after": after.get("model_revision_before"),
            "graphs": [
                {
                    **before_graphs.get(graph["role"], {}),
                    "role": graph["role"],
                    "graph_iri": graph["graph_iri"],
                    "revision_after": graph["revision_before"],
                }
                for graph in after.get("graphs", [])
            ],
        }
        build_session = self.session.get(BuildSessionModel, attempt.build_session_id)
        if build_session:
            build_session.last_activity_at = now
        fence = self.session.get(OntologyWriteFenceModel, attempt.batch.ontology_id)
        if fence and fence.attempt_id == attempt.id:
            self.session.delete(fence)
        attempt.execution_claim_id = None
        attempt.execution_claim_expires_at = None

    # ------------------------------------------------------------------
    # persistence/read helpers
    # ------------------------------------------------------------------

    def _get_or_create_batch(self, build_session, ontology, client_batch_id, content_hash, content):
        batch = self.session.scalar(
            select(ModelingBatchModel).where(
                ModelingBatchModel.build_session_id == build_session.id,
                ModelingBatchModel.client_batch_id == client_batch_id,
            )
        )
        if batch:
            if batch.content_hash != content_hash:
                raise ModelingBatchError(
                    "batch_content_conflict",
                    "client_batch_id identifies different immutable content",
                )
            return batch, False
        batch = ModelingBatchModel(
            id=_id(),
            project_id=ontology.project_id,
            ontology_id=ontology.id,
            build_session_id=build_session.id,
            client_batch_id=client_batch_id,
            content_hash=content_hash,
            status="open",
        )
        self.session.add(batch)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(ModelingBatchModel).where(
                    ModelingBatchModel.build_session_id == build_session.id,
                    ModelingBatchModel.client_batch_id == client_batch_id,
                )
            )
            if existing is None:
                raise
            if existing.content_hash != content_hash:
                raise ModelingBatchError(
                    "batch_content_conflict",
                    "client_batch_id identifies different immutable content",
                )
            return existing, False
        for ordinal, item in enumerate(content["items"]):
            batch.items.append(
                ModelingItemModel(
                    id=str(
                        uuid5(NAMESPACE_URL, f"modeling-item:{batch.id}:{item['client_item_id']}")
                    ),
                    client_item_id=item["client_item_id"],
                    ordinal=ordinal,
                    command_kind=item["command_kind"],
                    payload=item["payload"],
                    depends_on=item["depends_on"],
                    rationale=item["rationale"],
                    competency_question_ids=item["competency_question_ids"],
                )
            )
        self.session.flush()
        return batch, True

    def _save_item_results(self, attempt, batch, statuses, groups, findings):
        group_by_item = {
            item_id: group["atomic_group_id"]
            for group in groups
            for item_id in group["client_item_ids"]
        }
        codes = {item.client_item_id: [] for item in batch.items}
        for finding in findings:
            for item_id in finding["client_item_ids"]:
                codes.setdefault(item_id, []).append(finding["code"])
        for item in batch.items:
            self.session.add(
                ModelingAttemptItemResultModel(
                    id=str(uuid5(NAMESPACE_URL, f"modeling-result:{attempt.id}:{item.id}")),
                    attempt_id=attempt.id,
                    modeling_item_id=item.id,
                    client_item_id=item.client_item_id,
                    status=statuses[item.client_item_id],
                    atomic_group_id=group_by_item.get(item.client_item_id),
                    resource_outputs=item.resource_outputs,
                    finding_codes=sorted(set(codes.get(item.client_item_id, []))),
                )
            )
        self.session.flush()

    def _attempt_response(self, attempt, created_batch, created_attempt):
        batch = attempt.batch
        response = {
            "batch_id": batch.id,
            "client_batch_id": batch.client_batch_id,
            "batch_status": batch.status,
            "attempt_id": attempt.id,
            "idempotency_key": attempt.idempotency_key,
            "mode": attempt.mode,
            "attempt_status": attempt.status,
            "created_batch": created_batch,
            "created_attempt": created_attempt,
            "workspace": {
                "expected_version": attempt.expected_model_revision,
                "before_version": attempt.model_revision_before,
                "after_version": attempt.model_revision_after,
            },
            "target": attempt.target_snapshot,
            "items": [self._result_dict(result) for result in attempt.item_results],
            "groups": attempt.groups or [],
            "findings": attempt.findings or [],
            "normalized_delta": attempt.normalized_delta or {},
            "delta_hash": attempt.delta_hash,
            "recovery": {
                "state": attempt.recovery_state,
                "safe_to_retry": bool(
                    (attempt.recovery_detail or {}).get(
                        "safe_to_retry", attempt.status in {"applying", "recovering"}
                    )
                ),
                "detail": attempt.recovery_detail or {},
            },
            "retrieval_indexes": list(
                (attempt.recovery_detail or {}).get("retrieval_indexes") or []
            ),
            "created_at": attempt.created_at,
            "completed_at": attempt.completed_at,
        }
        return response

    def _batch_detail(self, batch):
        return {
            "batch_id": batch.id,
            "client_batch_id": batch.client_batch_id,
            "project_id": batch.project_id,
            "ontology_id": batch.ontology_id,
            "build_session_id": batch.build_session_id,
            "content_hash": batch.content_hash,
            "batch_status": batch.status,
            "items": [
                {
                    "item_id": item.id,
                    "client_item_id": item.client_item_id,
                    "ordinal": item.ordinal,
                    "command_kind": item.command_kind,
                    "payload": item.payload,
                    "depends_on": item.depends_on,
                    "resource_outputs": item.resource_outputs,
                    "rationale": item.rationale,
                    "competency_question_ids": item.competency_question_ids,
                }
                for item in batch.items
            ],
            "attempts": [
                self._attempt_response(attempt, False, False) for attempt in batch.attempts
            ],
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
            "terminal_at": batch.terminal_at,
        }

    def _list_batches(self, filters, cursor, limit, statuses):
        limit = max(1, min(limit, 100))
        statement = select(ModelingBatchModel).where(*filters)
        if statuses:
            statement = statement.where(ModelingBatchModel.status.in_(statuses))
        if cursor:
            try:
                created, row_id = json.loads(base64.urlsafe_b64decode(cursor + "===").decode())
                cursor_time = datetime.fromisoformat(created)
            except Exception as exc:
                raise ModelingBatchError(
                    "invalid_cursor", "Invalid pagination cursor", status_code=400
                ) from exc
            statement = statement.where(
                (ModelingBatchModel.created_at < cursor_time)
                | (
                    (ModelingBatchModel.created_at == cursor_time)
                    & (ModelingBatchModel.id < row_id)
                )
            )
        rows = list(
            self.session.scalars(
                statement.order_by(
                    ModelingBatchModel.created_at.desc(), ModelingBatchModel.id.desc()
                ).limit(limit + 1)
            )
        )
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page:
            raw = json.dumps([page[-1].created_at.isoformat(), page[-1].id]).encode()
            next_cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        return {"batches": [self._batch_summary(row) for row in page], "next_cursor": next_cursor}

    @staticmethod
    def _batch_summary(batch):
        latest = batch.attempts[-1] if batch.attempts else None
        return {
            "batch_id": batch.id,
            "client_batch_id": batch.client_batch_id,
            "ontology_id": batch.ontology_id,
            "build_session_id": batch.build_session_id,
            "batch_status": batch.status,
            "item_count": len(batch.items),
            "latest_attempt": (
                {
                    "attempt_id": latest.id,
                    "mode": latest.mode,
                    "attempt_status": latest.status,
                    "finding_count": len(latest.findings or []),
                    "recovery_state": latest.recovery_state,
                }
                if latest
                else None
            ),
            "created_at": batch.created_at,
            "terminal_at": batch.terminal_at,
        }

    @staticmethod
    def _result_dict(result):
        return {
            "item_id": result.modeling_item_id,
            "client_item_id": result.client_item_id,
            "status": result.status,
            "resource_outputs": result.resource_outputs,
            "atomic_group_id": result.atomic_group_id,
            "finding_codes": result.finding_codes,
        }

    def _observed_graph_hash(self, graph_iri: str) -> str:
        """Hash a workspace graph for the recovery snapshot (D13).

        Workspace graphs are materialized lazily, so a graph the store does not
        have is the empty state (AGENTS.md T0): recording the empty-graph hash
        lets ``_observe_recovery_state`` recognize a still-unapplied attempt
        whose target graph never came into existence instead of reporting a
        hash outside the persisted plan. Store outages and unreadable content
        raise and the caller keeps the workspace's own hash.
        """
        graph = Graph()
        exists = getattr(self.rdf_store, "graph_exists", None)
        if exists is None or exists(graph_iri):
            content = self.rdf_store.get_graph(graph_iri, "turtle")
            if content:
                graph.parse(data=content, format="turtle")
        return self._hash_rdf_graph(graph)

    def _target_snapshot(self, ontology_id):
        workspace = OntologyWorkspaceService(self.session, self.settings).context(ontology_id)
        iri = workspace["model_graph_iri"]
        content_hash = workspace["content_hash"]
        if self.rdf_store is not None and hasattr(self.rdf_store, "get_graph"):
            content_hash = self._observed_graph_hash(iri)
        return {"ontology_id": ontology_id,
                "model_revision_before": workspace["model_revision"],
                "model_revision_after": None,
                "graphs": [{"role": "model", "graph_iri": iri,
                            "revision_before": workspace["model_revision"], "revision_after": None,
                            "content_hash_before": content_hash, "content_hash_after": None}]}


    def _data_graphs(self, ontology_id):
        """Workspace graphs holding asserted instances (R3.0-009 §6.1)."""
        workspace = OntologyWorkspaceService(self.session, self.settings).context(ontology_id)
        return [workspace["model_graph_iri"]]


    @staticmethod
    def _delta_dict(delta):
        return {
            "inserts": [list(quad) for quad in delta.inserts],
            "deletes": [list(quad) for quad in delta.deletes],
            "clear_graphs": list(delta.clear_graphs),
            "drop_graphs": list(delta.drop_graphs),
        }

    @staticmethod
    def _content(payload):
        items = []
        for item in sorted(payload.items, key=lambda value: value.client_item_id):
            data = item.model_dump(mode="json")
            data["depends_on"] = sorted(set(data["depends_on"]))
            data["competency_question_ids"] = sorted(set(data["competency_question_ids"]))
            items.append(data)
        ids = [item["client_item_id"] for item in items]
        if len(ids) != len(set(ids)):
            raise ModelingBatchError(
                "invalid_command_payload", "client_item_id must be unique", status_code=422
            )
        return {"ontology_id": payload.ontology_id, "items": items}

    def _check_capacity(self, payload, request_bytes):
        actual_bytes = (
            request_bytes
            if request_bytes is not None
            else len(
                json.dumps(payload.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
            )
        )
        if actual_bytes > self.settings.modeling_batch_max_request_bytes:
            raise ModelingBatchError(
                "request_too_large",
                "Modeling Batch request is too large",
                status_code=413,
                actual=actual_bytes,
                limit=self.settings.modeling_batch_max_request_bytes,
            )
        if len(payload.items) > self.settings.modeling_batch_max_items:
            raise ModelingBatchError(
                "batch_limit_exceeded",
                "Modeling Batch has too many Items",
                status_code=413,
                actual=len(payload.items),
                limit=self.settings.modeling_batch_max_items,
            )

    @staticmethod
    def _dedupe_findings(findings):
        unique = {}
        for finding in findings:
            key = _hash({k: v for k, v in finding.items() if k != "message"})
            unique.setdefault(key, finding)
        return list(unique.values())

    @staticmethod
    def _fingerprint_findings(attempt_id: str, findings: list[dict[str, Any]]):
        """Assign stable, item-disambiguating identities to persisted Attempt findings."""
        fingerprinted = []
        for ordinal, finding in enumerate(findings):
            identity = {
                "attempt_id": attempt_id,
                "ordinal": ordinal,
                "code": finding["code"],
                "scope": finding["scope"],
                "client_item_ids": sorted(finding.get("client_item_ids") or []),
                "path": finding.get("path") or [],
                "details": finding.get("details") or {},
            }
            fingerprinted.append({**finding, "finding_fingerprint": _hash(identity)})
        return fingerprinted

    def _now(self):
        value = self.session.scalar(select(func.now()))
        return self._aware(value if isinstance(value, datetime) else datetime.now(timezone.utc))

    @staticmethod
    def _aware(value):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
