"""MCP runtime: process-wide resources, JSON envelope, and error mapping."""

from __future__ import annotations

import json
import hashlib
import inspect
import os
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.mcp.errors import map_exception
from app.repositories.postgres import create_session_factory
from app.services.embedding import EmbeddingClient
from app.services.semantic_context_cursor import ContextCursorCodec
from app.repositories.models import ApiKeyModel
from app.security.auth import (
    AuthPrincipal,
    audit_security_event,
    principal_from_key,
    AuthorizationDependencyError,
    resolve_api_key,
)
from app.security.http import _collect_resource_ids, _project_for_resource
from app.security.secrets import scan_domain_payload

T = TypeVar("T")

_settings: Settings | None = None
_session_factory: sessionmaker | None = None
_embedding_client: EmbeddingClient | None = None
_principal: AuthPrincipal | None = None
_context_cursor_codec: ContextCursorCodec | None = None
_context_cursor_codec_lock = threading.Lock()
_protocol_revalidation_lock = threading.Lock()
_protocol_revalidations: dict[tuple[str, str], dict[str, Any]] = {}


class McpOwnership(StrEnum):
    PROJECT_RESOURCE = "project_resource"
    ORG_ONLY = "org_only"
    GLOBAL_SAFE = "global_safe"


@dataclass(frozen=True)
class McpToolPolicy:
    required_scope: Literal["read", "model", "admin"]
    ownership: McpOwnership
    mutates_state: bool


def _policy(
    required_scope: Literal["read", "model", "admin"],
    ownership: McpOwnership,
    *,
    mutates_state: bool,
) -> McpToolPolicy:
    return McpToolPolicy(required_scope, ownership, mutates_state)


MCP_TOOL_POLICIES: dict[str, McpToolPolicy] = {
    "check_platform_health": _policy("read", McpOwnership.GLOBAL_SAFE, mutates_state=False),
    "discover_semantic_scopes": _policy("read", McpOwnership.GLOBAL_SAFE, mutates_state=False),
    "get_modeling_batch": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "list_session_modeling_batches": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "list_ontology_modeling_batches": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "get_modeling_context": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "get_ontology_read_model": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "get_entity_statement_context": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "get_build_context": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "get_ontology_workspace_context": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "get_project_brief": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "list_competency_questions": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "semantic_sparql_query": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "query_semantic_context": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "list_semantic_edit_audits": _policy("read", McpOwnership.ORG_ONLY, mutates_state=False),
    "describe_semantic_graph_set": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "list_semantic_derived_pointers": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "check_semantic_staleness": _policy("admin", McpOwnership.ORG_ONLY, mutates_state=True),
    "get_semantic_governance_status": _policy("read", McpOwnership.ORG_ONLY, mutates_state=False),
    "get_semantic_read_model": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "export_semantic_graph_set": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "inspect_semantic_projection_status": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "list_semantic_validation_runs": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "get_semantic_validation_run": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "list_semantic_reasoning_runs": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "get_semantic_reasoning_run": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "get_project_build_context": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "get_build_session": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "get_modeling_workflow_artifact": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "list_modeling_workflow_artifacts": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "get_modeling_execution_event": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "list_modeling_execution_events": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "export_modeling_workflow_record": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "submit_modeling_batch": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "save_interview_answer": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "update_project_brief": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "propose_competency_questions": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "validate_competency_question": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "submit_semantic_edit": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "run_semantic_validation": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "run_semantic_reasoning": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "submit_semantic_rule_definition": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "run_semantic_rule": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "get_semantic_rule_definition": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "start_semantic_projection_job": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "compile_and_apply_canonical_command": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "create_build_session": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "create_modeling_workflow_artifact": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "record_modeling_execution_event": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "resume_build_session": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "save_build_checkpoint": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "complete_build_session": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "cancel_build_session": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "acquire_ontology_lease": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "renew_ontology_lease": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "release_ontology_lease": _policy("model", McpOwnership.PROJECT_RESOURCE, mutates_state=True),
    "repair_ontology_workspace": _policy(
        "admin", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "preflight_semantic_migration": _policy("admin", McpOwnership.ORG_ONLY, mutates_state=False),
    "create_semantic_migration_run": _policy("admin", McpOwnership.ORG_ONLY, mutates_state=True),
    "run_next_semantic_migration_batch": _policy(
        "admin", McpOwnership.ORG_ONLY, mutates_state=True
    ),
    "run_semantic_migration_parity_check": _policy(
        "admin", McpOwnership.ORG_ONLY, mutates_state=True
    ),
    "cutover_semantic_migration_run": _policy("admin", McpOwnership.ORG_ONLY, mutates_state=True),
    "rollback_semantic_migration_run": _policy("admin", McpOwnership.ORG_ONLY, mutates_state=True),
    "list_semantic_protection_sets": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "create_semantic_protection_set": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "update_semantic_protection_set": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "delete_semantic_protection_set": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "add_semantic_protection_set_members": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "remove_semantic_protection_set_members": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
}


def _jsonable(data: Any) -> Any:
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def get_resources() -> tuple[sessionmaker, None, EmbeddingClient]:
    """Lazily initialize and return the process-wide MCP resources.

    Test seam: tests can monkeypatch this function to inject fakes without
    mutating module globals.
    """
    global _settings, _session_factory, _embedding_client
    if _settings is None:
        _settings = Settings()
    if _session_factory is None:
        _session_factory = create_session_factory(_settings)
    if _embedding_client is None:
        _embedding_client = EmbeddingClient(_settings)
    return _session_factory, None, _embedding_client


def reset_resources() -> None:
    """Clear cached singletons. Tests use this for isolation."""
    global _settings, _session_factory, _embedding_client, _principal, _context_cursor_codec
    _settings = None
    _session_factory = None
    _embedding_client = None
    _principal = None
    with _context_cursor_codec_lock:
        _context_cursor_codec = None
    with _protocol_revalidation_lock:
        _protocol_revalidations.clear()


def get_context_cursor_codec() -> ContextCursorCodec:
    """Return the process-wide MCP Context Query cursor signer.

    MCP tool calls create a fresh service object for each request. The cursor
    codec must nevertheless outlive those service objects so an ephemeral
    process-local signing key can verify a continuation on the next call. A
    configured signing secret remains the source of stable verification across
    process restarts; this accessor only owns the per-process instance.
    """
    global _context_cursor_codec
    codec = _context_cursor_codec
    if codec is not None:
        return codec
    with _context_cursor_codec_lock:
        codec = _context_cursor_codec
        if codec is None:
            settings = _settings or Settings()
            codec = ContextCursorCodec.from_settings(settings)
            _context_cursor_codec = codec
        return codec


def authenticate_runtime() -> AuthPrincipal:
    global _principal
    settings = Settings()
    plaintext = settings.ontology_mcp_api_key
    if not plaintext:
        raise RuntimeError("ONTOLOGY_MCP_API_KEY is required")
    session_factory = create_session_factory(settings)
    with session_factory() as session:
        principal = resolve_api_key(session, plaintext)
    if principal is None:
        raise RuntimeError("MCP authentication failed")
    _principal = principal
    return principal


def set_runtime_principal(principal: AuthPrincipal | None) -> None:
    """Test seam that still requires a concrete, server-created principal."""
    global _principal
    _principal = principal


def runtime_actor() -> str:
    if _principal is None:
        raise RuntimeError("MCP authentication has not completed")
    return _principal.actor


def runtime_principal() -> AuthPrincipal:
    if _principal is None:
        raise RuntimeError("MCP authentication has not completed")
    return _principal


def _closure_values(fn: Callable) -> dict[str, Any]:
    values = _closure_payload(fn)
    flattened: dict[str, Any] = {}

    def visit(value: Any, name: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, str(key))
        elif hasattr(value, "model_dump"):
            visit(value.model_dump(), name)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, f"{name[:-1]}" if name.endswith("_ids") else name)
        elif name:
            flattened[name] = value

    for name, value in values.items():
        visit(value, name)
    return flattened


def _closure_payload(fn: Callable) -> dict[str, Any]:
    return dict(inspect.getclosurevars(fn).nonlocals)


def _authorize_tool(session: Session, tool_name: str, fn: Callable) -> AuthPrincipal:
    if _principal is None:
        raise PermissionError("MCP authentication has not completed")
    from sqlalchemy.exc import SQLAlchemyError

    try:
        record = session.get(ApiKeyModel, _principal.subject_id)
        principal = principal_from_key(session, record, auth_method="mcp")
    except SQLAlchemyError as exc:
        raise AuthorizationDependencyError() from exc
    if principal is None:
        raise PermissionError("MCP credential is no longer valid")
    # R1.2-004: refresh the process-wide principal so tool callbacks can read
    # the verified identity through ``runtime_principal()`` instead of trusting
    # a client-supplied field. This never accepts a caller-controlled identity.
    _set_runtime_principal(principal)
    policy = MCP_TOOL_POLICIES.get(tool_name)
    if policy is None or policy.required_scope not in principal.effective_scopes:
        raise PermissionError("MCP operation is not authorized")
    values = _closure_values(fn)
    supplied_actor = values.get("actor") or values.get("created_by") or values.get("actor_id")
    if supplied_actor and supplied_actor != principal.actor:
        audit_security_event(
            _session_factory or create_session_factory(Settings()),
            "actor_spoof_attempt",
            "overridden",
            principal,
        )
    if principal.project_id is not None:
        if policy.ownership is McpOwnership.ORG_ONLY:
            raise PermissionError("MCP operation requires organization admin scope")
        resolved = []
        resources: list[tuple[str, str]] = []
        _collect_resource_ids(_closure_payload(fn), resources)
        for kind, value in resources:
            project_id = _project_for_resource(session, kind, value)
            if project_id is None:
                raise PermissionError("MCP resource owner cannot be resolved")
            resolved.append(project_id)
        if any(project_id != principal.project_id for project_id in resolved):
            raise PermissionError("MCP resource is outside the authorized Project")
        if policy.ownership is McpOwnership.PROJECT_RESOURCE and not resolved:
            raise PermissionError("MCP operation requires a Project-owned resource")
    if policy.mutates_state:
        from app.services.checkpoint_archive import project_is_checkpoint_archived

        resources = []
        _collect_resource_ids(_closure_payload(fn), resources)
        project_ids = {_project_for_resource(session, kind, value) for kind, value in resources}
        if any(
            project_is_checkpoint_archived(session, project_id)
            for project_id in project_ids if project_id
        ):
            raise PermissionError("checkpoint_source_archived: source Project is read-only")
    return principal


def _set_runtime_principal(principal: AuthPrincipal) -> None:
    """Internal setter used by ``_authorize_tool`` to publish the refreshed principal."""
    global _principal
    _principal = principal


def _read_candidate_platform_gate() -> tuple[str | None, dict[str, Any] | None]:
    """Read the Runner-owned candidate gate without following links."""

    gate_path = os.environ.get("FORMAL_CANDIDATE_GATE_PATH")
    if gate_path is None:
        return None, None
    if not gate_path:
        return gate_path, None
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(gate_path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 64 * 1024:
            return gate_path, None
        payload = os.read(descriptor, 64 * 1024 + 1)
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            return gate_path, None
        if value.get("schema_version") != "r2-3-005-candidate-platform-gate/v1":
            return gate_path, None
        return gate_path, value
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return gate_path, None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _context_binding(state: dict[str, Any]) -> dict[str, str] | None:
    """Return the exact R2.3-003 Modeling context bound to a candidate gate."""

    value = state.get("modeling_context")
    if value is None:
        return None
    required = {
        "project_id",
        "ontology_id",
        "workspace_version",
        "context_receipt_digest",
        "response_digest",
        "call_receipt_digest",
    }
    if not isinstance(value, dict) or set(value) != required:
        return {}
    if any(not isinstance(value.get(field), str) or not value[field] for field in required):
        return {}
    return {field: str(value[field]) for field in required}


def _gate_denial(
    error: str,
    error_code: str,
    *,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "error": error, "error_code": error_code}
    if detail is not None:
        result["data"] = detail
    return result


def _candidate_platform_gate_error(
    tool_name: str | None = None,
    fn: Callable[..., Any] | None = None,
) -> dict[str, Any] | None:
    """Return the formal gate denial, including the R2.3-003 stateful fence.

    A legacy/default or R2.3-005 gate has no ``modeling_context`` member and
    therefore retains the original all-tools-open behavior.  The 003 gate keeps
    read-only tools available after the candidate receipt but requires a
    process-local exact-O revalidation record before any mutating Protocol tool.
    """

    gate_path, state = _read_candidate_platform_gate()
    if gate_path is None:
        return None
    if state is None or state.get("state") != "open":
        return _gate_denial(
            "candidate receipt required before platform call",
            "candidate_receipt_required",
        )
    context = _context_binding(state)
    if context == {}:
        policy = MCP_TOOL_POLICIES.get(tool_name) if tool_name is not None else None
        if policy is None or not policy.mutates_state:
            # Keep exact-O/context reads available so a malformed binding can
            # still be diagnosed; no stateful callback can pass this branch.
            return None
        return _gate_denial(
            "candidate Modeling context binding is invalid",
            "modeling_context_binding_invalid",
            detail={
                "candidate_digest": state.get("candidate_digest"),
                "mutation_state": "zero-mutation",
            },
        )
    if context is None or tool_name is None:
        return None
    policy = MCP_TOOL_POLICIES.get(tool_name)
    if policy is None or not policy.mutates_state:
        return None
    candidate_digest = state.get("candidate_digest")
    key = (gate_path, str(candidate_digest))
    with _protocol_revalidation_lock:
        record = _protocol_revalidations.get(key)
    if record is None:
        return _gate_denial(
            "exact-O Modeling context revalidation is required before stateful platform calls",
            "modeling_context_revalidation_required",
            detail={
                "run_id": state.get("run_id"),
                "candidate_digest": candidate_digest,
                "project_id": context["project_id"],
                "ontology_id": context["ontology_id"],
                "expected_workspace_version": context["workspace_version"],
                "mutation_state": "zero-mutation",
                "conflict_code": "modeling_context_revalidation_required",
            },
        )
    return None


def _context_value(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if value.get("ok") is False:
        return None
    if "data" in value:
        value = value.get("data")
    elif isinstance(value.get("result"), dict):
        value = value.get("result")
    return value if isinstance(value, dict) else None


def _context_is_valid(value: Any, context: dict[str, str]) -> bool:
    value = _context_value(value)
    if value is None:
        return False
    project = value.get("project")
    ontology = value.get("ontology")
    workspace = value.get("workspace")
    derived = value.get("derived_state")
    return bool(
        isinstance(project, dict)
        and project.get("id") == context["project_id"]
        and isinstance(ontology, dict)
        and ontology.get("id") == context["ontology_id"]
        and isinstance(workspace, dict)
        and workspace.get("state") == "ready"
        and workspace.get("workspace_version") == context["workspace_version"]
        and workspace.get("issues") == []
        and isinstance(derived, dict)
        and isinstance(derived.get("stale_count"), int)
        and not isinstance(derived.get("stale_count"), bool)
        and derived.get("stale_count") >= 0
        and not (
            isinstance(value.get("recovering"), dict)
            and value["recovering"].get("active") is True
        )
    )


def _context_digest(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _current_revalidation_context(
    gate_path: str,
    state: dict[str, Any],
    context: dict[str, str],
) -> dict[str, str]:
    """Return the candidate context advanced by successful Protocol writes."""

    key = (gate_path, str(state.get("candidate_digest")))
    with _protocol_revalidation_lock:
        record = _protocol_revalidations.get(key)
    workspace_version = record.get("workspace_version") if record is not None else None
    if not isinstance(workspace_version, str) or not workspace_version:
        return context
    return {**context, "workspace_version": workspace_version}


def _protocol_revalidation_error(
    state: dict[str, Any],
    context: dict[str, str],
    *,
    reason: str,
    observed: Any = None,
) -> dict[str, Any]:
    observed_value = _context_value(observed)
    workspace = observed_value.get("workspace") if observed_value else None
    observed_version = workspace.get("workspace_version") if isinstance(workspace, dict) else None
    return _gate_denial(
        "Protocol Modeling context revalidation failed; stateful call remains closed",
        "modeling_context_revalidation_failed",
        detail={
            "run_id": state.get("run_id"),
            "candidate_digest": state.get("candidate_digest"),
            "project_id": context["project_id"],
            "ontology_id": context["ontology_id"],
            "expected_workspace_version": context["workspace_version"],
            "observed_workspace_version": observed_version,
            "reason_code": reason,
            "mutation_state": "zero-mutation",
            "conflict_code": "modeling_context_revalidation_failed",
        },
    )


def _record_protocol_revalidation(
    gate_path: str,
    state: dict[str, Any],
    value: Any,
) -> dict[str, Any] | None:
    context = _context_binding(state)
    if context in (None, {}):
        return None
    context = _current_revalidation_context(gate_path, state, context)
    if not _context_is_valid(value, context):
        key = (gate_path, str(state.get("candidate_digest")))
        with _protocol_revalidation_lock:
            _protocol_revalidations.pop(key, None)
        return _protocol_revalidation_error(state, context, reason="context_shape_or_scope", observed=value)
    normalized = _context_value(value)
    assert normalized is not None
    response_digest = _context_digest(normalized)
    call_digest = _context_digest(
        {"tool": "get_modeling_context", "ontology_id": context["ontology_id"]}
    )
    payload = {
        "candidate_digest": state.get("candidate_digest"),
        "project_id": context["project_id"],
        "ontology_id": context["ontology_id"],
        "workspace_version": context["workspace_version"],
        "context_receipt_digest": context["context_receipt_digest"],
        "response_digest": response_digest,
        "call_receipt_digest": call_digest,
    }
    record = {**payload, "revalidation_receipt_digest": _context_digest(payload)}
    key = (gate_path, str(state.get("candidate_digest")))
    with _protocol_revalidation_lock:
        existing = _protocol_revalidations.get(key)
        if existing is None:
            _protocol_revalidations[key] = record
    return None


def _advance_protocol_revalidation_after_apply(
    gate_path: str,
    state: dict[str, Any],
    value: Any,
) -> None:
    """Advance the stateful fence after this Protocol process applies a batch."""

    normalized = _jsonable(value)
    if not isinstance(normalized, dict) or normalized.get("mode") != "apply_atomic":
        return
    if normalized.get("attempt_status") != "applied":
        return
    workspace = normalized.get("workspace")
    if not isinstance(workspace, dict):
        return
    before_version = workspace.get("before_version")
    expected_version = workspace.get("expected_version")
    after_version = workspace.get("after_version")
    if not all(isinstance(item, str) and item for item in (before_version, after_version)):
        return
    key = (gate_path, str(state.get("candidate_digest")))
    with _protocol_revalidation_lock:
        record = _protocol_revalidations.get(key)
        if record is None or record.get("workspace_version") != before_version:
            return
        if expected_version not in (None, before_version):
            return
        payload = {
            **{key: item for key, item in record.items() if key != "revalidation_receipt_digest"},
            "workspace_version": after_version,
        }
        _protocol_revalidations[key] = {
            **payload,
            "revalidation_receipt_digest": _context_digest(payload),
        }


def _read_live_modeling_context(session: Session, ontology_id: str) -> dict[str, Any]:
    """Read current context for the stateful fence without invoking a write tool."""

    from app.repositories.rdf_store import RdfStoreRepository
    from app.services.modeling_batches import ModelingBatchService

    settings = Settings()
    return ModelingBatchService(
        session,
        settings,
        RdfStoreRepository(settings.oxigraph_url),
    ).get_modeling_context(ontology_id)


def _check_live_protocol_context(
    gate_path: str,
    state: dict[str, Any],
    session: Session,
) -> dict[str, Any] | None:
    context = _context_binding(state)
    if context in (None, {}):
        return None
    context = _current_revalidation_context(gate_path, state, context)
    try:
        current = _read_live_modeling_context(session, context["ontology_id"])
    except Exception:
        key = (gate_path, str(state.get("candidate_digest")))
        with _protocol_revalidation_lock:
            _protocol_revalidations.pop(key, None)
        return _protocol_revalidation_error(state, context, reason="live_context_read_failed")
    if not _context_is_valid(current, context):
        key = (gate_path, str(state.get("candidate_digest")))
        with _protocol_revalidation_lock:
            _protocol_revalidations.pop(key, None)
        return _protocol_revalidation_error(state, context, reason="workspace_or_context_drift", observed=current)
    return None


def _run_tool(fn: Callable[[Session, Any, EmbeddingClient], T]) -> dict[str, Any]:
    tool_name = inspect.currentframe().f_back.f_code.co_name
    gate_error = _candidate_platform_gate_error(tool_name, fn)
    if gate_error is not None:
        return gate_error
    session_factory, _driver, embedding_client = get_resources()
    gate_path, gate_state = _read_candidate_platform_gate()
    try:
        with session_factory() as session:
            _authorize_tool(session, tool_name, fn)
            if gate_path is not None and gate_state is not None:
                context = _context_binding(gate_state)
                policy = MCP_TOOL_POLICIES.get(tool_name)
                if context and policy is not None and policy.mutates_state:
                    live_error = _check_live_protocol_context(gate_path, gate_state, session)
                    if live_error is not None:
                        return live_error
            scan_domain_payload(_closure_values(fn))
            value = fn(session, _driver, embedding_client)
            if gate_path is not None and gate_state is not None and tool_name == "get_modeling_context":
                revalidation_error = _record_protocol_revalidation(gate_path, gate_state, value)
                if revalidation_error is not None:
                    return revalidation_error
            if (
                gate_path is not None
                and gate_state is not None
                and tool_name == "submit_modeling_batch"
            ):
                _advance_protocol_revalidation_after_apply(gate_path, gate_state, value)
            return {"ok": True, "data": _jsonable(value)}
    except Exception as exc:
        code, message = map_exception(exc)
        return {"ok": False, "error": message, "error_code": code}
