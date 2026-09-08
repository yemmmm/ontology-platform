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
from rdflib.namespace import OWL, RDF
from rdflib.util import from_n3
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    ModelingBatchSubmit,
    ModelingOperationPlanEvidenceRead,
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
    SemanticDerivedResultPointerModel,
    SemanticEditAuditModel,
    SemanticGraphSetModel,
    SemanticGraphRevisionModel,
    SemanticProjectionManifestModel,
    SemanticRuleDefinitionModel,
    SemanticRuleModel,
)
from app.repositories.rdf_store import RdfStoreRepository
from app.services.build_sessions import BuildSessionError, BuildSessionService
from app.services.evidence_reference import (
    EvidenceReferenceError,
    EvidenceReferenceService,
    normalize_evidence,
)
from app.services.modeling_handlers import (
    ModelingCommandHandlerRegistry,
    PreparedModelingCommand,
    union_delta,
)
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.operation_semantics import (
    OperationValidationError,
    reject_operation_secrets,
)
from app.services.semantic_retrieval import SemanticRetrievalCoordinator
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_canonical_write import (
    CanonicalSemanticWriteError,
    CanonicalSemanticWriteService,
    CanonicalShaclViolation,
)
from app.services.semantic_command_compiler import (
    CommandCompilerError,
    CompiledCommand,
    InvalidCommandPayload,
)
from app.services.semantic_derived_state import SemanticDerivedStateService
from app.services.semantic_export import namespace_from_settings
from app.services.semantic_rule_definition import (
    ALLOWED_INPUT_ROLES,
    ALLOWED_LANGUAGES,
    ALLOWED_OUTPUT_KINDS,
    RuleDefinitionError,
    validate_construct_template,
    validate_platform_dsl,
    validate_workflow_state_machine,
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
        "target_semantic_id",
        "project_id",
        "ontology_id",
        "workspace_version",
        "candidate_digest",
        "entity_iri",
        "snapshot_digest",
        "page_digests",
        "statements",
        "complete",
        "receipt_digest",
    }
    if set(value) != required:
        raise InvalidCommandPayload(
            "delete-only impact_receipt has an invalid field set"
        )
    if value.get("schema_version") != "r2-3-003-delete-impact/v1":
        raise InvalidCommandPayload("delete-only impact_receipt schema is unsupported")
    if value.get("complete") is not True:
        raise InvalidCommandPayload("delete-only impact_receipt must be complete")
    for field in (
        "target_semantic_id",
        "project_id",
        "ontology_id",
        "workspace_version",
        "candidate_digest",
        "entity_iri",
        "snapshot_digest",
        "receipt_digest",
    ):
        if not isinstance(value.get(field), str) or not value[field]:
            raise InvalidCommandPayload(f"delete-only impact_receipt {field} is required")
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
    "table_mapping_iri",
    "join_mapping_iri",
    "enum_meaning_iri",
    "metric_iri",
)


def _relational_resource_iri(metadata: dict[str, Any]) -> str | None:
    for key in _RELATIONAL_METADATA_IRI_KEYS:
        value = metadata.get(key)
        if value:
            return str(value)
    return None


def _parse_json_columns(value: Any) -> set[str]:
    """Column names from a ``op:columnMappings`` JSON literal."""
    if value is None:
        return set()
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return set()
    if not isinstance(parsed, list):
        return set()
    return {
        str(entry.get("column"))
        for entry in parsed
        if isinstance(entry, dict) and entry.get("column")
    }


def _parse_json_steps(value: Any) -> list[dict[str, Any]]:
    """Ordered steps from an ``op:joinPath`` JSON literal."""
    if value is None:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


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
        self.workspace_versions = ModelingWorkspaceVersionService(session, settings)

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
                "expected_workspace_version": payload.expected_workspace_version,
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
        if workspace.get("state") != "ready" or not workspace.get("default_graph_set_id"):
            raise ModelingBatchError(
                "workspace_revision_conflict", "Ontology workspace is incomplete"
            )
        current_version = self.workspace_versions.version_for(payload.ontology_id)
        if current_version != payload.expected_workspace_version:
            raise ModelingBatchError(
                "workspace_revision_conflict",
                "Ontology workspace changed after the caller last read it",
                current_workspace_version=current_version,
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
                    expected_workspace_version=payload.expected_workspace_version,
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
            expected_workspace_version=payload.expected_workspace_version,
            workspace_version_before=current_version,
            graph_set_id=(authorization_result or {}).get("graph_set_id")
            or OntologyWorkspaceService(self.session, self.settings).context(payload.ontology_id)[
                "default_graph_set_id"
            ],
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
                "evidence": self._evidence_plan(attempt, batch, selected),
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
            self.workspace_versions.version_for(ontology_id)
            if workspace["state"] == "ready"
            else None
        )
        fence = self.session.get(OntologyWriteFenceModel, ontology_id)
        lease = self.session.get(OntologyLeaseModel, ontology_id)
        now = self._now()
        active_lease = bool(
            lease and lease.released_at is None and self._aware(lease.expires_at) > now
        )
        rules = int(
            self.session.scalar(
                select(func.count(SemanticRuleModel.id)).where(
                    SemanticRuleModel.ontology_id == ontology_id,
                    SemanticRuleModel.status == "active",
                )
            )
            or 0
        )
        stale_pointers = int(
            self.session.scalar(
                select(func.count(SemanticDerivedResultPointerModel.id)).where(
                    SemanticDerivedResultPointerModel.graph_set_id
                    == workspace.get("default_graph_set_id"),
                    SemanticDerivedResultPointerModel.status == "stale",
                )
            )
            or 0
        )
        stale_projections = int(
            self.session.scalar(
                select(func.count(SemanticProjectionManifestModel.id)).where(
                    SemanticProjectionManifestModel.graph_set_id
                    == workspace.get("default_graph_set_id"),
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
            for name in ("classes", "entities", "facts", "history", "delta", "rules")
        }
        rdf_counts, counts_warning = self._rdf_resource_counts(workspace)
        return {
            "project": {"id": ontology.project_id},
            "ontology": {"id": ontology.id, "name": ontology.name, "status": ontology.status},
            "workspace": {
                "state": workspace["state"],
                "workspace_version": version,
                "editable": workspace["state"] == "ready"
                and any(m["editable"] for m in workspace["members"]),
                "issues": workspace["issues"],
            },
            "resource_counts": {
                **rdf_counts,
                "rule_definitions": rules,
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
            "shapes",
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
        roles = {member["role"]: member["graph_iri"] for member in workspace.get("members", [])}
        ontology_graph = roles.get("asserted_ontology")
        data_graph = roles.get("asserted_data")
        shapes_graph = roles.get("shapes")
        if not ontology_graph or not data_graph or not shapes_graph:
            return empty, "semantic_workspace_incomplete"
        op = self.settings.semantic_base_iri.rstrip("/") + "/vocab/"
        branches = {
            "classes": f"GRAPH <{ontology_graph}> {{ ?s a <http://www.w3.org/2002/07/owl#Class> }}",
            "properties": f"GRAPH <{ontology_graph}> {{ ?s a <http://www.w3.org/2002/07/owl#DatatypeProperty> }}",
            "relation_types": f"GRAPH <{ontology_graph}> {{ ?s a <http://www.w3.org/2002/07/owl#ObjectProperty> }}",
            "shapes": f"GRAPH ?g {{ ?s a <http://www.w3.org/ns/shacl#NodeShape> }} FILTER(STRSTARTS(STR(?g), STR(<{shapes_graph}>)))",
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
                    receipt = _validate_delete_only_impact_receipt(command.payload["impact_receipt"])
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
            self._validate_rule_command(batch, item.client_item_id, command, findings)
            self._validate_evidence_and_questions(batch, item, findings)
            if not item.evidence_reference_ids and not item.evidence:
                findings.append(
                    _finding(
                        "missing_evidence",
                        "warning",
                        "Modeling Item has no Evidence",
                        item_ids=[item.client_item_id],
                    )
                )
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
                    if self._ordered_shape_refinement(left, right, prepared, dependency_map):
                        # D15: defining and refining one Shape inside a batch is
                        # a declared sequence, not two writers racing one target.
                        continue
                    findings.append(
                        _finding(
                            "conflicting_item_effects",
                            "error",
                            "Items contain incompatible writes to the same semantic target",
                            item_ids=sorted({left.item_id, right.item_id}),
                        )
                    )
        return prepared, self._dedupe_findings(findings), groups, dependency_map

    def _ordered_shape_refinement(
        self, left, right, prepared: dict[str, PreparedModelingCommand], dependency_map
    ) -> bool:
        """True for a dependency-ordered ``create_shape`` → ``update_shape`` pair.

        Both items address the same Shape IRI and the create is a (transitive)
        dependency of the update, so the update's cascade delete plus its own
        constraints describe the final state (R3.0-009 / D15). Without the
        declared ordering the pair stays a conflict: an ``update_shape`` that
        precedes its own ``create_shape`` is still rejected.
        """
        left_command = prepared.get(left.item_id)
        right_command = prepared.get(right.item_id)
        if left_command is None or right_command is None:
            return False
        kinds = {left_command.command_kind, right_command.command_kind}
        if kinds != {"create_shape", "update_shape"}:
            return False
        create = (
            left_command
            if left_command.command_kind == "create_shape"
            else right_command
        )
        update = right_command if create is left_command else left_command
        if create.compiled is None or update.compiled is None:
            return False
        create_shape_iri = str(create.compiled.metadata.get("shape_iri") or "")
        update_shape_iri = str(update.compiled.metadata.get("shape_iri") or "")
        if not create_shape_iri or create_shape_iri != update_shape_iri:
            return False
        return self._depends_transitively(left.item_id, right.item_id, dependency_map) or (
            self._depends_transitively(right.item_id, left.item_id, dependency_map)
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
        relational_findings = self._validate_relational_mapping_commands(
            batch, prepared, selected
        )
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
                validate_shacl=True,
                shape_graph_iris=self._shape_graphs(batch.ontology_id),
                # Shape commands leave the data graph untouched, so the SHACL
                # candidate is the workspace data scope (R3.0-009 §6.1).
                candidate_graph_iris=self._data_graphs(batch.ontology_id),
                # A merged candidate carries no per-item kind, so the batch
                # reports the shapes its items create/update (D11): a sibling
                # create makes the update legal, an unknown id fails loudly.
                created_shape_iris=self._selected_shape_iris(
                    batch, prepared, selected, "create_shape"
                ),
                updated_shape_iris=self._selected_shape_iris(
                    batch, prepared, selected, "update_shape"
                ),
            )
        except CanonicalShaclViolation as exc:
            report_text = str(exc.validation_result.get("report_text") or "")
            item_ids = []
            for item_id in sorted(selected):
                command = prepared.get(item_id)
                if command is None:
                    continue
                terms = set(command.outputs.values())
                if command.compiled is not None:
                    for subject, _predicate, obj, _graph_iri in (
                        *command.compiled.delta.inserts,
                        *command.compiled.delta.deletes,
                    ):
                        terms.update({subject.strip("<>"), obj.strip("<>")})
                if any(term and term in report_text for term in terms):
                    item_ids.append(item_id)
            return [
                _finding(
                    "shacl_violation",
                    "error",
                    str(exc),
                    item_ids=item_ids,
                    scope="item" if item_ids else "batch",
                    report_summary=exc.validation_result.get("summary"),
                    violations=exc.validation_result.get("violations") or [],
                )
            ]
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
            elif code == "shape_not_found":
                item_ids = [
                    item_id
                    for item_id in sorted(selected)
                    if prepared.get(item_id)
                    and prepared[item_id].command_kind in {"update_shape", "delete_shape"}
                    and str(prepared[item_id].compiled.metadata.get("shape_iri") or "")
                    in str(exc)
                ]
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
        first = next(
            (item for item in batch.items if item.client_item_id == item_ids[0]), None
        )
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
        """Deterministic G2/G3/G5/G6 gates for relational mapping commands.

        Existence and cross-resource checks run on the merged view (current
        ontology graph + same-batch compiled inserts); TableMapping
        update/delete also checks that existing JoinMappings do not become
        dangling (G3 reverse). No LLM calls.
        """
        relational_items = [
            (item.client_item_id, prepared[item.client_item_id])
            for item in sorted(batch.items, key=lambda entry: entry.ordinal)
            if item.client_item_id in selected
            and item.client_item_id in prepared
            and prepared[item.client_item_id].command_kind in _RELATIONAL_MAPPING_COMMAND_KINDS
        ]
        # R3.0-008A G7-d trigger: delete_entity is the command-surface carrier
        # of L3 first-class nodes (written to the data graph), so a batch that
        # deletes an entity must also run the semanticValue dangling scan even
        # when it carries no relational mapping command at all.
        delete_entity_items = [
            (item.client_item_id, prepared[item.client_item_id])
            for item in sorted(batch.items, key=lambda entry: entry.ordinal)
            if item.client_item_id in selected
            and item.client_item_id in prepared
            and prepared[item.client_item_id].command_kind == "delete_entity"
        ]
        if not relational_items and not delete_entity_items:
            return []
        if self.rdf_store is None:
            return [
                _finding(
                    "candidate_validation_failed",
                    "error",
                    "RDF store is unavailable for deterministic relational mapping validation",
                    scope="batch",
                )
            ]
        ns = namespace_from_settings(self.settings)
        op = str(ns.vocab)
        graph_iri = str(ns.graph("ontology", batch.ontology_id))
        store_graph = Graph()
        graph_exists = not hasattr(self.rdf_store, "graph_exists") or (
            self.rdf_store.graph_exists(graph_iri)
        )
        content = self.rdf_store.get_graph(graph_iri, "turtle") if graph_exists else ""
        if content and content.strip():
            store_graph.parse(data=content, format="turtle")
        merged = Graph()
        for triple in store_graph:
            merged.add(triple)
        # Project the same-batch commands onto the merged view: deletes first
        # (so TableMapping update/delete can leave existing JoinMappings
        # dangling in this view), then inserts.
        for item_id in sorted(selected):
            command = prepared.get(item_id)
            if command is None or command.compiled is None:
                continue
            for subject, predicate, obj, target_graph in command.compiled.delta.deletes:
                if target_graph != graph_iri:
                    continue
                if predicate == "?p":
                    # Whole-subject wildcard delete (delete_* relational commands).
                    for triple in list(merged.triples((URIRef(subject[1:-1]), None, None))):
                        merged.remove(triple)
                elif obj == "?o":
                    for triple in list(
                        merged.triples((URIRef(subject[1:-1]), URIRef(predicate[1:-1]), None))
                    ):
                        merged.remove(triple)
                else:
                    merged.remove(
                        (
                            from_n3(subject),
                            from_n3(predicate),
                            from_n3(obj),
                        )
                    )
        nt_lines = []
        for item_id in sorted(selected):
            command = prepared.get(item_id)
            if command is None or command.compiled is None:
                continue
            for subject, predicate, obj, target_graph in command.compiled.delta.inserts:
                if target_graph == graph_iri:
                    nt_lines.append(f"{subject} {predicate} {obj} .")
        if nt_lines:
            merged.parse(data="\n".join(nt_lines), format="nt")

        findings: list[dict[str, Any]] = []

        # ---- G6: create collisions / update-delete target existence ----
        batch_created: set[str] = set()
        for item_id, command in relational_items:
            subject_iri = _relational_resource_iri(command.compiled.metadata)
            if subject_iri is None:
                continue
            exists = any(store_graph.triples((URIRef(subject_iri), None, None)))
            is_create = command.command_kind.startswith("create_")
            if is_create:
                if exists or subject_iri in batch_created:
                    findings.append(
                        _finding(
                            "resource_already_exists",
                            "error",
                            "Relational mapping resource already exists; use the update command",
                            item_ids=[item_id],
                            path=["payload"],
                        )
                    )
                    continue
                batch_created.add(subject_iri)
            elif not exists and subject_iri not in batch_created:
                findings.append(
                    _finding(
                        "resource_not_found",
                        "error",
                        "Relational mapping resource was not found in the target Ontology",
                        item_ids=[item_id],
                        path=["payload"],
                    )
                )

        # ---- G2: referenced IRIs exist in the merged view ----
        class_types = {OWL.Class, URIRef("http://www.w3.org/2000/01/rdf-schema#Class")}
        relation_types = {OWL.ObjectProperty}
        property_types = {
            OWL.ObjectProperty,
            OWL.DatatypeProperty,
            URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"),
        }

        def reference_missing(iri: str | None, expected_types: set) -> bool:
            if not iri:
                return False
            subject = URIRef(iri)
            for type_iri in expected_types:
                if (subject, RDF.type, type_iri) in merged:
                    return False
            return True

        def add_reference_finding(item_id: str, field: str, iri: str, role: str) -> None:
            findings.append(
                _finding(
                    "invalid_resource_reference",
                    "error",
                    f"{field} does not reference an existing {role} in the target Ontology: {iri}",
                    item_ids=[item_id],
                    path=["payload", field],
                )
            )

        for item_id, command in relational_items:
            payload = command.payload
            kind = command.command_kind
            if kind == "create_table_mapping" and reference_missing(
                payload.get("mapped_class_iri"), class_types
            ):
                add_reference_finding(item_id, "mapped_class_iri", payload["mapped_class_iri"], "class")
            elif kind == "create_join_mapping" and reference_missing(
                payload.get("relation_type_iri"), relation_types
            ):
                add_reference_finding(
                    item_id, "relation_type_iri", payload["relation_type_iri"], "relation type"
                )
            elif kind == "create_enum_meaning" and reference_missing(
                payload.get("property_iri"), property_types
            ):
                add_reference_finding(item_id, "property_iri", payload["property_iri"], "property")
            elif kind in {"create_metric_definition", "update_metric_definition"}:
                grain = payload.get("grain")
                if isinstance(grain, list):
                    for index, grain_iri in enumerate(grain):
                        if reference_missing(grain_iri, property_types):
                            add_reference_finding(
                                item_id, f"grain[{index}]", str(grain_iri), "property"
                            )
                for field in ("time_field", "measure_property_iri"):
                    if payload.get(field) and reference_missing(payload[field], property_types):
                        add_reference_finding(item_id, field, payload[field], "property")
                filters = payload.get("filters")
                if isinstance(filters, list):
                    for index, entry in enumerate(filters):
                        if isinstance(entry, dict) and reference_missing(
                            entry.get("field"), property_types
                        ):
                            add_reference_finding(
                                item_id, f"filters[{index}].field", str(entry.get("field")), "property"
                            )

        # ---- G5: (mappedProperty, enumValue) uniqueness per Ontology ----
        enum_pairs = {}
        for subject, _, _ in merged.triples((None, RDF.type, URIRef(f"{op}EnumValueMeaning"))):
            property_value = merged.value(subject, URIRef(f"{op}mappedProperty"))
            enum_value = merged.value(subject, URIRef(f"{op}enumValue"))
            if property_value is not None and enum_value is not None:
                enum_pairs[str(subject)] = (str(property_value), str(enum_value))
        if any(
            command.command_kind in {"create_enum_meaning", "update_enum_meaning"}
            for _item_id, command in relational_items
        ):
            pair_counts: dict[tuple[str, str], int] = {}
            for pair in enum_pairs.values():
                pair_counts[pair] = pair_counts.get(pair, 0) + 1
            for item_id, command in relational_items:
                if command.command_kind not in {"create_enum_meaning", "update_enum_meaning"}:
                    continue
                subject_iri = _relational_resource_iri(command.compiled.metadata)
                pair = enum_pairs.get(subject_iri or "")
                if pair is not None and pair_counts.get(pair, 0) > 1:
                    findings.append(
                        _finding(
                            "resource_already_exists",
                            "error",
                            "Enum value meaning duplicates an existing (property, enum value) "
                            f"pair in the target Ontology: {pair[1]}",
                            item_ids=[item_id],
                            path=["payload", "enum_value"],
                        )
                    )

        # ---- G3: join path closure, forward and reverse ----
        table_records: dict[str, dict[str, Any]] = {}
        for subject, _, _ in merged.triples((None, RDF.type, URIRef(f"{op}TableMapping"))):
            table_name = merged.value(subject, URIRef(f"{op}tableName"))
            columns_value = merged.value(subject, URIRef(f"{op}columnMappings"))
            columns = _parse_json_columns(columns_value)
            table_records[str(subject)] = {
                "table_name": str(table_name) if table_name is not None else None,
                "columns": columns,
            }
        store_table_records: dict[str, dict[str, Any]] = {}
        for subject, _, _ in store_graph.triples((None, RDF.type, URIRef(f"{op}TableMapping"))):
            table_name = store_graph.value(subject, URIRef(f"{op}tableName"))
            columns_value = store_graph.value(subject, URIRef(f"{op}columnMappings"))
            store_table_records[str(subject)] = {
                "table_name": str(table_name) if table_name is not None else None,
                "columns": _parse_json_columns(columns_value),
            }
        join_records: dict[str, dict[str, Any]] = {}
        for subject, _, _ in merged.triples((None, RDF.type, URIRef(f"{op}JoinMapping"))):
            join_path_value = merged.value(subject, URIRef(f"{op}joinPath"))
            join_records[str(subject)] = {
                "join_path": _parse_json_steps(join_path_value),
            }
        tables_by_name = {
            record["table_name"]: record
            for record in table_records.values()
            if record["table_name"]
        }
        batch_join_subjects = {
            _relational_resource_iri(command.compiled.metadata): item_id
            for item_id, command in relational_items
            if command.command_kind in {"create_join_mapping", "update_join_mapping"}
            and _relational_resource_iri(command.compiled.metadata) is not None
        }
        batch_table_change_items = [
            (item_id, command)
            for item_id, command in relational_items
            if command.command_kind in {"update_table_mapping", "delete_table_mapping"}
        ]
        for join_subject, record in sorted(join_records.items()):
            unresolved: list[tuple[str | None, str | None]] = []
            steps = record["join_path"]
            for index, step in enumerate(steps):
                if (
                    index + 1 < len(steps)
                    and step.get("to_table") != steps[index + 1].get("from_table")
                ):
                    unresolved.append((None, None))
                for table_key, columns_key in (("from_table", "from_columns"), ("to_table", "to_columns")):
                    table = step.get(table_key)
                    table_record = tables_by_name.get(table)
                    if table_record is None:
                        unresolved.append((table, None))
                        continue
                    for column in step.get(columns_key, []):
                        if column not in table_record["columns"]:
                            unresolved.append((table, column))
            if not unresolved:
                continue
            details = "; ".join(
                f"table {table or '?'}{' column ' + column if column else ''} is not mapped"
                for table, column in unresolved
            )
            batch_join_item = batch_join_subjects.get(join_subject)
            if batch_join_item is not None:
                findings.append(
                    _finding(
                        "join_path_not_mapped",
                        "error",
                        f"Join path is not closed by TableMappings in the target Ontology: {details}",
                        item_ids=[batch_join_item],
                        path=["payload", "join_path"],
                    )
                )
                continue
            attributed = [
                item_id
                for item_id, command in batch_table_change_items
                if any(
                    table is not None
                    and store_table_records.get(
                        _relational_resource_iri(command.compiled.metadata) or "", {}
                    ).get("table_name")
                    == table
                    for table, _column in unresolved
                )
            ]
            findings.append(
                _finding(
                    "join_path_not_mapped",
                    "error",
                    "Updating or deleting a TableMapping would leave an existing JoinMapping "
                    f"dangling: {details}",
                    item_ids=sorted(set(attributed)),
                    scope="item" if attributed else "batch",
                    path=["payload"],
                )
            )

        # ---- G7: semanticValue structural gate (R3.0-008A design §3.3) ----
        # Runs on its own dual-graph merged view (ontology graph + data graph
        # of the batch target Ontology, plus same-batch projections filtered
        # to both graphs). G2/G3/G5/G6 above keep the ontology-graph-only view
        # and are untouched: EnumValueMeaning subjects live in the ontology
        # graph while their L3 targets live in the data graph, so a dual view
        # is the mechanical precondition for target existence to be visible.
        enum_command_items = [
            (item_id, command)
            for item_id, command in relational_items
            if command.command_kind in {"create_enum_meaning", "update_enum_meaning"}
        ]
        if enum_command_items or delete_entity_items:
            data_graph_iri = str(ns.graph("data", batch.ontology_id))
            g7_graphs = {graph_iri, data_graph_iri}
            g7_view = Graph()
            for source_graph in (graph_iri, data_graph_iri):
                source_exists = not hasattr(self.rdf_store, "graph_exists") or (
                    self.rdf_store.graph_exists(source_graph)
                )
                source_content = (
                    self.rdf_store.get_graph(source_graph, "turtle") if source_exists else ""
                )
                if source_content and source_content.strip():
                    g7_view.parse(data=source_content, format="turtle")
            # Project the same-batch commands onto the dual view (deletes
            # first, then inserts — same ordering contract as the merged view
            # above). Note the object-position wildcard of delete_entity is a
            # no-op under this projection by design: dangling protection is
            # defined by the target appearing as a subject (design review
            # note), which the whole-subject wildcard delete already removes.
            for item_id in sorted(selected):
                command = prepared.get(item_id)
                if command is None or command.compiled is None:
                    continue
                for subject, predicate, obj, target_graph in command.compiled.delta.deletes:
                    if target_graph not in g7_graphs:
                        continue
                    if predicate == "?p":
                        for triple in list(g7_view.triples((URIRef(subject[1:-1]), None, None))):
                            g7_view.remove(triple)
                    elif obj == "?o":
                        for triple in list(
                            g7_view.triples(
                                (URIRef(subject[1:-1]), URIRef(predicate[1:-1]), None)
                            )
                        ):
                            g7_view.remove(triple)
                    else:
                        g7_view.remove(
                            (
                                from_n3(subject),
                                from_n3(predicate),
                                from_n3(obj),
                            )
                        )
            g7_insert_lines = []
            for item_id in sorted(selected):
                command = prepared.get(item_id)
                if command is None or command.compiled is None:
                    continue
                for subject, predicate, obj, target_graph in command.compiled.delta.inserts:
                    if target_graph in g7_graphs:
                        g7_insert_lines.append(f"{subject} {predicate} {obj} .")
            if g7_insert_lines:
                g7_view.parse(data="\n".join(g7_insert_lines), format="nt")

            semantic_predicate = URIRef(f"{op}semanticValue")
            mapping_type_iris = {
                URIRef(f"{op}{type_name}")
                for type_name in (
                    "EnumValueMeaning",
                    "TableMapping",
                    "JoinMapping",
                    "MetricDefinition",
                )
            }

            # G7-a (target exists) / G7-b (non-mapping resource type).
            for item_id, command in enum_command_items:
                semantic_value = (
                    command.compiled.metadata.get("semantic_value_iri")
                    or command.payload.get("semantic_value")
                )
                if not semantic_value:
                    continue
                target = URIRef(str(semantic_value))
                if not any(g7_view.triples((target, None, None))):
                    findings.append(
                        _finding(
                            "invalid_resource_reference",
                            "error",
                            "semantic_value does not reference an existing first-class semantic "
                            f"node in the target Ontology: {semantic_value}",
                            item_ids=[item_id],
                            path=["payload", "semantic_value"],
                        )
                    )
                    continue
                if any((target, RDF.type, type_iri) in g7_view for type_iri in mapping_type_iris):
                    findings.append(
                        _finding(
                            "invalid_resource_reference",
                            "error",
                            "semantic_value must reference a non-mapping first-class semantic "
                            f"node: {semantic_value}",
                            item_ids=[item_id],
                            path=["payload", "semantic_value"],
                        )
                    )

            # G7-c (at most one semanticValue per EnumValueMeaning, catching
            # direct-write residue) and, when the batch deletes entities, the
            # G7-d dangling scan over every EnumValueMeaning in the dual view.
            enum_subject_items = {
                _relational_resource_iri(command.compiled.metadata): item_id
                for item_id, command in enum_command_items
                if _relational_resource_iri(command.compiled.metadata) is not None
            }
            dangling_targets: list[str] = []
            for subject, _, _ in g7_view.triples((None, RDF.type, URIRef(f"{op}EnumValueMeaning"))):
                values = list(g7_view.objects(subject, semantic_predicate))
                if len(values) > 1:
                    owner_item = enum_subject_items.get(str(subject))
                    findings.append(
                        _finding(
                            "invalid_resource_reference",
                            "error",
                            "EnumValueMeaning must carry at most one semanticValue: "
                            f"{subject}",
                            item_ids=[owner_item] if owner_item else [],
                            scope="item" if owner_item else "batch",
                            path=["payload", "semantic_value"],
                        )
                    )
                    continue
                if not values:
                    continue
                target = URIRef(str(values[0]))
                if not any(g7_view.triples((target, None, None))):
                    dangling_targets.append(str(values[0]))
            if dangling_targets and delete_entity_items:
                deleted_subject_items = {
                    str(command.compiled.metadata.get("entity_iri") or ""): item_id
                    for item_id, command in delete_entity_items
                }
                for target in dangling_targets:
                    attributed = [
                        item_id
                        for deleted_iri, item_id in deleted_subject_items.items()
                        if deleted_iri == target
                    ]
                    findings.append(
                        _finding(
                            "semantic_value_dangling",
                            "error",
                            "Deleting this entity would leave an EnumValueMeaning "
                            f"semanticValue dangling: {target}",
                            item_ids=sorted(set(attributed)),
                            scope="item" if attributed else "batch",
                            path=["payload"],
                        )
                    )
        return findings

    def _validate_rule_command(
        self,
        batch: ModelingBatchModel,
        client_item_id: str,
        command: PreparedModelingCommand,
        findings: list[dict[str, Any]],
    ) -> None:
        if command.storage != "postgres":
            return
        payload = command.payload
        rule_id = payload.get("rule_id")
        rule_iri = payload.get("rule_iri") or command.outputs.get("resource_iri")
        rule = self.session.get(SemanticRuleModel, rule_id) if rule_id else None
        if rule is None and rule_iri:
            rule = self.session.scalar(
                select(SemanticRuleModel).where(
                    SemanticRuleModel.ontology_id == batch.ontology_id,
                    SemanticRuleModel.rule_iri == rule_iri,
                )
            )
        if command.command_kind == "create_rule_definition" and rule is not None:
            findings.append(
                _finding(
                    "resource_already_exists",
                    "error",
                    "Rule already exists; use update_rule_definition to create a new version",
                    item_ids=[client_item_id],
                    path=["payload", "rule_id"],
                )
            )
            return
        if command.command_kind != "create_rule_definition" and (
            rule is None or rule.ontology_id != batch.ontology_id
        ):
            findings.append(
                _finding(
                    "invalid_resource_reference",
                    "error",
                    "Rule was not found in the target Ontology",
                    item_ids=[client_item_id],
                    path=["payload", "rule_id"],
                )
            )
            return
        if command.command_kind == "delete_rule_definition":
            return
        current = (
            self.session.get(SemanticRuleDefinitionModel, rule.current_definition_id)
            if rule and rule.current_definition_id
            else None
        )
        definition = {
            "language": payload.get("language", current.language if current else None),
            "body": payload.get("body", current.body if current else None),
            "input_roles": payload.get("input_roles", current.input_roles if current else []),
            "output_kind": payload.get(
                "output_kind", current.output_kind if current else "assertion"
            ),
        }
        try:
            if definition["language"] not in ALLOWED_LANGUAGES:
                raise RuleDefinitionError("Unsupported Rule language")
            if definition["output_kind"] not in ALLOWED_OUTPUT_KINDS:
                raise RuleDefinitionError("Unsupported Rule output kind")
            if not definition["input_roles"] or (
                set(definition["input_roles"]) - ALLOWED_INPUT_ROLES
            ):
                raise RuleDefinitionError("Invalid Rule input roles")
            if definition["language"] == "sparql_construct":
                validate_construct_template(definition["body"])
            elif definition["language"] == "platform_dsl":
                validate_platform_dsl(definition["body"])
            else:
                validate_workflow_state_machine(definition["body"])
        except RuleDefinitionError as exc:
            findings.append(
                _finding(
                    "invalid_command_payload",
                    "error",
                    str(exc),
                    item_ids=[client_item_id],
                    path=["payload", "body"],
                )
            )

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

    def _validate_evidence_and_questions(
        self,
        batch: ModelingBatchModel,
        item: ModelingItemModel,
        findings: list[dict[str, Any]],
    ) -> None:
        evidence_service = EvidenceReferenceService(self.session)
        try:
            evidence_service.resolve_candidates(
                batch.project_id,
                reference_ids=item.evidence_reference_ids,
                inline_evidence=item.evidence,
                persist=False,
            )
        except EvidenceReferenceError as exc:
            findings.append(
                _finding(
                    "evidence_not_found",
                    "error",
                    str(exc),
                    item_ids=[item.client_item_id],
                    path=["evidence"],
                )
            )
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
        batch = attempt.batch
        plan = attempt.operation_plan
        try:
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
                            graph_set_id=attempt.graph_set_id,
                            actor=auth.actor,
                            reason=f"Modeling Batch {batch.id}",
                            validate=True,
                            shape_graph_iris=self._shape_graphs(batch.ontology_id),
                            candidate_graph_iris=self._data_graphs(batch.ontology_id),
                            created_shape_iris=self._batch_created_shape_iris(commands),
                            commit=False,
                            audit_id=attempt.audit_id,
                            fence_attempt_id=attempt.id,
                            write_rdf=not rdf_already_applied,
                            modeling_item_effects=modeling_item_effects,
                        )
                    except (CanonicalShaclViolation, CanonicalSemanticWriteError) as exc:
                        # Deterministic pre-write rejection (D13): the canonical
                        # pipeline validates before it writes, so nothing reached
                        # the store and reconciliation is trivial. It must fail
                        # the attempt instead of entering recovery, where an
                        # unfixed payload would only re-fail and a missing
                        # optional graph could escalate to a write fence.
                        self.session.rollback()
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
            else:
                self._ensure_rule_only_audit(attempt, auth.actor)
            for item_id, command in commands.items():
                if command.storage == "postgres":
                    self._apply_rule(
                        batch,
                        item_id,
                        command,
                        auth.actor,
                        attempt.audit_id,
                    )
            self._persist_evidence(attempt, auth.actor)
            self._mark_rule_derived_stale(attempt.graph_set_id)
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
                **(
                    {"reason_code": observation["reason"]}
                    if observation.get("reason")
                    else {}
                ),
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
        if metadata.get("schema_version") != "r2-3-003-delete-impact/v1" or not isinstance(entries, list):
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
                return {"state": "partial_or_drifted", "reason": "delete_only_receipt_entry_invalid"}
            receipt = entry.get("impact_receipt")
            target_iri = entry.get("entity_iri")
            if (
                not isinstance(receipt, dict)
                or not isinstance(target_iri, str)
                or not target_iri
                or receipt.get("complete") is not True
            ):
                return {"state": "partial_or_drifted", "reason": "delete_only_receipt_entry_invalid"}
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
            target_present = bool(after_hashes)
            if target_present and after_hashes == before_hashes:
                state = "not_applied"
            elif not target_present and not after_hashes:
                state = "applied"
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
            graphs = self._load_observed_graphs(
                sorted({quad[3] for quad in [*inserts, *deletes]})
            )
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
        for graph in attempt.target_snapshot.get("graphs", []):
            revision = self.session.scalar(
                select(SemanticGraphRevisionModel).where(
                    SemanticGraphRevisionModel.graph_iri == graph.get("graph_iri")
                )
            )
            before = graph.get("revision_before")
            if revision is None or before is None:
                continue
            if revision.revision == before:
                continue
            if revision.revision == before + 1 and revision.last_edit_audit_id == attempt.audit_id:
                continue
            return False
        return True

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

    def _apply_rule(self, batch, item_id, command, actor, audit_id):
        payload = command.payload
        rule_id = payload.get("rule_id")
        rule_iri = payload.get("rule_iri") or command.outputs.get("resource_iri")
        rule = self.session.get(SemanticRuleModel, rule_id) if rule_id else None
        if rule is None and rule_iri:
            rule = self.session.scalar(
                select(SemanticRuleModel).where(
                    SemanticRuleModel.ontology_id == batch.ontology_id,
                    SemanticRuleModel.rule_iri == rule_iri,
                )
            )
        if command.command_kind == "create_rule_definition":
            if rule is None:
                rule = SemanticRuleModel(
                    id=rule_id or command.outputs["resource_id"],
                    ontology_id=batch.ontology_id,
                    rule_iri=rule_iri,
                    status="active",
                )
                self.session.add(rule)
                self.session.flush()
            elif rule.ontology_id != batch.ontology_id:
                raise RuntimeError("Rule belongs to another Ontology")
        elif rule is None or rule.ontology_id != batch.ontology_id:
            raise RuntimeError("Rule was not found in target Ontology")
        if command.command_kind == "delete_rule_definition":
            rule.status = "inactive"
            if rule.current_definition_id:
                current = self.session.get(SemanticRuleDefinitionModel, rule.current_definition_id)
                if current:
                    current.status = "inactive"
            return
        required = {"name", "language", "body", "input_roles"}
        if command.command_kind == "create_rule_definition" and not required.issubset(payload):
            raise RuntimeError(f"Rule payload missing: {sorted(required - set(payload))}")
        current = (
            self.session.get(SemanticRuleDefinitionModel, rule.current_definition_id)
            if rule.current_definition_id
            else None
        )
        definition_data = {
            "name": payload.get("name", current.name if current else None),
            "language": payload.get("language", current.language if current else None),
            "body": payload.get("body", current.body if current else None),
            "input_roles": payload.get("input_roles", current.input_roles if current else []),
            "output_kind": payload.get(
                "output_kind", current.output_kind if current else "assertion"
            ),
            "uses_inferred_facts": payload.get(
                "uses_inferred_facts", current.uses_inferred_facts if current else False
            ),
            "requires_review": payload.get(
                "requires_review", current.requires_review if current else False
            ),
            "priority": payload.get("priority", current.priority if current else 0),
            "safety_profile": payload.get(
                "safety_profile", current.safety_profile if current else {}
            ),
            "metadata": payload.get("metadata", current.rule_metadata if current else {}),
        }
        if (
            definition_data["language"] not in ALLOWED_LANGUAGES
            or definition_data["output_kind"] not in ALLOWED_OUTPUT_KINDS
        ):
            raise RuntimeError("Invalid Rule language or output kind")
        if (
            not definition_data["input_roles"]
            or set(definition_data["input_roles"]) - ALLOWED_INPUT_ROLES
        ):
            raise RuntimeError("Invalid Rule input roles")
        definition_hash = _hash(definition_data)
        version = "sha256:" + definition_hash[:16]
        existing = self.session.scalar(
            select(SemanticRuleDefinitionModel).where(
                SemanticRuleDefinitionModel.semantic_rule_id == rule.id,
                SemanticRuleDefinitionModel.version == version,
            )
        )
        if existing is None:
            existing = SemanticRuleDefinitionModel(
                id=str(uuid5(NAMESPACE_URL, f"modeling-rule:{rule.id}:{version}")),
                semantic_rule_id=rule.id,
                rule_iri=rule.rule_iri,
                version=version,
                status="active",
                created_by=actor,
                definition_hash=definition_hash,
                rule_metadata=definition_data.pop("metadata"),
                **definition_data,
            )
            self.session.add(existing)
            self.session.flush()
        if current and current.id != existing.id:
            current.status = "superseded"
        modeling_item = next(item for item in batch.items if item.client_item_id == item_id)
        existing.rule_metadata = {
            **(existing.rule_metadata or {}),
            "modeling_item_id": modeling_item.id,
            "edit_audit_id": audit_id,
            "modeling_batch_id": batch.id,
        }
        existing.status = "active"
        rule.status = "active"
        rule.current_definition_id = existing.id

    def _persist_evidence(self, attempt, actor):
        service = EvidenceReferenceService(self.session)
        item_by_client = {item.client_item_id: item for item in attempt.batch.items}
        result_by_client = {result.client_item_id: result for result in attempt.item_results}
        for client_item_id in attempt.operation_plan.get("selected_client_item_ids", []):
            item = item_by_client[client_item_id]
            result = result_by_client[client_item_id]
            entries = attempt.operation_plan.get("evidence", {}).get(client_item_id, [])
            references = []
            association_ids = {}
            for entry in entries:
                if entry.get("document_name") is not None:
                    reference, _created = service.get_or_create(
                        attempt.batch.project_id,
                        entry["document_name"],
                        entry["excerpt"],
                        actor=actor,
                        reference_id=entry["reference_id"],
                    )
                else:
                    reference = service.get(
                        entry["reference_id"], project_id=attempt.batch.project_id
                    )
                references.append(reference)
                association_ids[reference.id] = entry["association_id"]
            associations = service.associate(
                project_id=attempt.batch.project_id,
                ontology_id=attempt.batch.ontology_id,
                graph_set_id=attempt.graph_set_id,
                target_type="modeling_item",
                target_id=item.id,
                references=references,
                client_item_id=client_item_id,
                edit_audit_id=attempt.audit_id,
                actor=actor,
                association_ids=association_ids,
            )
            result.evidence_reference_ids = [row.id for row in references]
            result.evidence_association_ids = [row.id for row in associations]

    def _evidence_plan(self, attempt, batch, selected):
        service = EvidenceReferenceService(self.session)
        planned: dict[str, list[dict[str, Any]]] = {}
        for item in batch.items:
            if item.client_item_id not in selected:
                continue
            entries: list[dict[str, Any]] = []
            seen: set[str] = set()
            for reference_id in item.evidence_reference_ids:
                reference = service.get(reference_id, project_id=batch.project_id)
                if reference.id in seen:
                    continue
                seen.add(reference.id)
                entries.append(
                    {
                        "reference_id": reference.id,
                        "association_id": str(
                            uuid5(
                                NAMESPACE_URL,
                                f"modeling-evidence-association:{attempt.id}:{item.id}:"
                                f"{reference.id}",
                            )
                        ),
                    }
                )
            for evidence in item.evidence:
                normalized = normalize_evidence(
                    evidence.get("document_name", ""), evidence.get("excerpt", "")
                )
                existing = service.find_existing(batch.project_id, normalized)
                reference_id = (
                    existing.id
                    if existing
                    else str(
                        uuid5(
                            NAMESPACE_URL,
                            f"modeling-evidence:{batch.project_id}:"
                            f"{normalized.document_name}:{normalized.excerpt_hash}",
                        )
                    )
                )
                if reference_id in seen:
                    continue
                seen.add(reference_id)
                entries.append(
                    {
                        "reference_id": reference_id,
                        "association_id": str(
                            uuid5(
                                NAMESPACE_URL,
                                f"modeling-evidence-association:{attempt.id}:{item.id}:"
                                f"{reference_id}",
                            )
                        ),
                        "document_name": normalized.document_name,
                        "excerpt": normalized.excerpt,
                        "excerpt_hash": normalized.excerpt_hash,
                    }
                )
            planned[item.client_item_id] = entries
        return planned

    def _ensure_rule_only_audit(self, attempt, actor):
        if self.session.get(SemanticEditAuditModel, attempt.audit_id) is None:
            self.session.add(
                SemanticEditAuditModel(
                    id=attempt.audit_id,
                    actor=actor,
                    reason=f"Modeling Batch {attempt.batch_id}",
                    input_format="modeling-batch",
                    target_graph_iri=None,
                    affected_graph_iris=[],
                    validation_result={"conforms": True},
                    graph_delta=attempt.normalized_delta,
                    evidence_status="item_scoped",
                    warning_state={
                        "findings": attempt.findings,
                        "graph_set_id": attempt.graph_set_id,
                    },
                    applied=True,
                )
            )
            self.session.flush()

    def _mark_rule_derived_stale(self, graph_set_id):
        if not graph_set_id:
            return
        SemanticDerivedStateService(self.session, self.settings).mark_graph_set_stale(
            graph_set_id,
            reason="workspace_rule_changed",
            commit=False,
        )

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
        if attempt.graph_set_id:
            from app.services.semantic_graph_set import SemanticGraphSetService

            graph_set = self.session.get(SemanticGraphSetModel, attempt.graph_set_id)
            if graph_set is not None:
                graph_set.source_signature = SemanticGraphSetService(
                    self.session, self.settings
                ).source_signature_for(attempt.graph_set_id)
        attempt.workspace_version_after = self.workspace_versions.version_for(
            attempt.batch.ontology_id
        )
        after = self._target_snapshot(attempt.batch.ontology_id)
        before_graphs = {
            graph["role"]: graph for graph in attempt.target_snapshot.get("graphs", [])
        }
        attempt.target_snapshot = {
            **attempt.target_snapshot,
            "source_signature_after": after.get("source_signature_before"),
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
                    evidence_reference_ids=item["evidence_reference_ids"],
                    evidence=item["evidence"],
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
                "expected_version": attempt.expected_workspace_version,
                "before_version": attempt.workspace_version_before,
                "after_version": attempt.workspace_version_after,
            },
            "target": attempt.target_snapshot,
            "items": [self._result_dict(result) for result in attempt.item_results],
            "groups": attempt.groups or [],
            "findings": attempt.findings or [],
            "normalized_delta": attempt.normalized_delta or {},
            "delta_hash": attempt.delta_hash,
            "evidence_candidates": self._evidence_candidates(batch),
            "recovery": {
                "state": attempt.recovery_state,
                "safe_to_retry": bool(
                    (attempt.recovery_detail or {}).get(
                        "safe_to_retry", attempt.status in {"applying", "recovering"}
                    )
                ),
                "detail": attempt.recovery_detail or {},
            },
            "retrieval_indexes": list((attempt.recovery_detail or {}).get("retrieval_indexes") or []),
            "created_at": attempt.created_at,
            "completed_at": attempt.completed_at,
        }
        # The operation plan is an internal persisted structure.  Expose only
        # its source-minimal Evidence projection on dry-run receipts so the
        # Protocol can compare its candidate-local map without receiving
        # locators, owner identities, or any raw source beyond submitted
        # inline excerpts.  Apply/recovery receipts retain their existing
        # shape and semantics.
        if attempt.mode == "dry_run":
            response["operation_plan"] = {
                "evidence": self._safe_operation_plan_evidence(attempt)
            }
        return response

    def _safe_operation_plan_evidence(self, attempt) -> list[dict[str, str]]:
        """Project persisted Evidence plan rows into a safe dry-run shape.

        ``_evidence_plan`` remains the single source of deduplication and
        deterministic reference allocation.  This method only reads those
        planned rows and resolves metadata for existing references; it never
        creates or mutates Evidence rows.
        """

        planned = (attempt.operation_plan or {}).get("evidence") or {}
        if not planned:
            return []
        service = EvidenceReferenceService(self.session)
        rows: list[dict[str, str]] = []
        for client_item_id in sorted(planned):
            for entry in planned.get(client_item_id) or []:
                reference_id = str(entry.get("reference_id") or "")
                document_name = entry.get("document_name")
                excerpt_hash = entry.get("excerpt_hash")
                if document_name is None or excerpt_hash is None:
                    # Existing references are represented in the internal
                    # plan by their stable reference ID.  Resolve only the
                    # safe metadata needed for map comparison; do not copy
                    # the stored excerpt into the receipt.
                    reference = service.get(
                        reference_id,
                        project_id=attempt.batch.project_id,
                    )
                    document_name = reference.normalized_document_name
                    excerpt_hash = reference.excerpt_hash
                projection = ModelingOperationPlanEvidenceRead(
                    client_item_id=client_item_id,
                    document_name=str(document_name),
                    normalized_excerpt_sha256=str(excerpt_hash),
                    dedupe_identity=reference_id,
                )
                rows.append(projection.model_dump(mode="json"))
        return rows

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
                    "evidence_reference_ids": item.evidence_reference_ids,
                    "evidence": item.evidence,
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
            "evidence_reference_ids": result.evidence_reference_ids,
            "evidence_association_ids": result.evidence_association_ids,
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
        content_hashes: dict[str, str | None] = {}
        if self.rdf_store is not None and hasattr(self.rdf_store, "get_graph"):
            for member in workspace.get("members", []):
                try:
                    content_hashes[member["graph_iri"]] = self._observed_graph_hash(
                        member["graph_iri"]
                    )
                except Exception:
                    content_hashes[member["graph_iri"]] = member.get("content_hash")
        return {
            "graph_set_id": workspace.get("default_graph_set_id"),
            "source_signature_before": workspace.get("source_signature"),
            "source_signature_after": None,
            "graphs": [
                {
                    "role": member["role"],
                    "graph_iri": member["graph_iri"],
                    "revision_before": member["revision"],
                    "revision_after": None,
                    "content_hash_before": content_hashes.get(
                        member["graph_iri"], member.get("content_hash")
                    ),
                }
                for member in workspace.get("members", [])
            ],
        }

    def _shape_graphs(self, ontology_id):
        """Shape graphs that govern candidate validation (R3.0-009 §6.1).

        Both the workspace shapes role graph and the custom sub-graph written
        by Modeling ``create_shape``/``update_shape`` commands constrain the
        data graph, so both are passed to SHACL validation.
        """
        workspace = OntologyWorkspaceService(self.session, self.settings).context(ontology_id)
        prefix = self.settings.semantic_graph_iri_prefix.rstrip("/")
        graphs: list[str] = []
        for member in workspace["members"]:
            if member["role"] != "shapes":
                continue
            graphs.append(member["graph_iri"])
            custom = f"{prefix}/shapes/{ontology_id}/custom"
            if member["graph_iri"] == f"{prefix}/shapes/{ontology_id}" and custom not in graphs:
                graphs.append(custom)
        return graphs

    @staticmethod
    def _batch_created_shape_iris(commands) -> list[str]:
        """Shape IRIs this batch's own ``create_shape`` items define (D15).

        The apply phase validates the merged delta in one shot, so an
        ``update_shape`` addressing a shape a sibling item creates must be
        treated exactly like the pre-check: the definition exists in the same
        write and must not fail the ``shape_not_found`` existence guard.
        """
        iris: list[str] = []
        for command in commands.values():
            compiled = command.compiled
            if compiled is None or compiled.command_kind != "create_shape":
                continue
            shape_iri = compiled.metadata.get("shape_iri")
            if shape_iri:
                iris.append(str(shape_iri))
        return iris

    def _data_graphs(self, ontology_id):
        """Workspace graphs holding asserted instances (R3.0-009 §6.1)."""
        workspace = OntologyWorkspaceService(self.session, self.settings).context(ontology_id)
        return [
            member["graph_iri"]
            for member in workspace["members"]
            if member["role"] == "asserted_data"
        ]

    def _selected_shape_iris(self, batch, prepared, selected, command_kind):
        """Shape IRIs the candidate's ``create_shape``/``update_shape`` items touch.

        The merged candidate command has no per-item command kind, so the
        existence guard for ``update_shape`` (D11) is driven from here.
        """
        iris: list[str] = []
        for item in sorted(batch.items, key=lambda entry: entry.ordinal):
            if item.client_item_id not in selected or item.client_item_id not in prepared:
                continue
            command = prepared[item.client_item_id]
            if command.command_kind != command_kind or command.compiled is None:
                continue
            shape_iri = command.compiled.metadata.get("shape_iri")
            if shape_iri:
                iris.append(str(shape_iri))
        return iris

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
            data["evidence_reference_ids"] = sorted(set(data["evidence_reference_ids"]))
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
        evidence = [item for model_item in payload.items for item in model_item.evidence]
        if len(evidence) > self.settings.modeling_batch_max_inline_evidence:
            raise ModelingBatchError(
                "inline_evidence_limit_exceeded",
                "Too many inline Evidence excerpts",
                status_code=413,
                actual=len(evidence),
                limit=self.settings.modeling_batch_max_inline_evidence,
            )
        for item in evidence:
            if len(item.excerpt) > self.settings.modeling_batch_max_evidence_excerpt_chars:
                raise ModelingBatchError(
                    "evidence_excerpt_too_large",
                    "Evidence excerpt is too large",
                    status_code=413,
                    actual=len(item.excerpt),
                    limit=self.settings.modeling_batch_max_evidence_excerpt_chars,
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

    @staticmethod
    def _evidence_candidates(batch):
        return [
            {
                "client_item_id": item.client_item_id,
                "existing_reference_ids": item.evidence_reference_ids,
                "inline": [
                    {
                        "document_name": evidence["document_name"],
                        "excerpt_hash": hashlib.sha256(evidence["excerpt"].encode()).hexdigest(),
                    }
                    for evidence in item.evidence
                ],
            }
            for item in batch.items
        ]

    def _now(self):
        value = self.session.scalar(select(func.now()))
        return self._aware(value if isinstance(value, datetime) else datetime.now(timezone.utc))

    @staticmethod
    def _aware(value):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
