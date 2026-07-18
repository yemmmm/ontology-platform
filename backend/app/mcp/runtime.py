"""MCP runtime: process-wide resources, JSON envelope, and error mapping."""

from __future__ import annotations

import json
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.mcp.errors import map_exception
from app.repositories.postgres import create_session_factory
from app.services.embedding import EmbeddingClient
from app.repositories.models import ApiKeyModel
from app.security.auth import AuthPrincipal, audit_security_event, resolve_api_key, validate_scopes
from app.security.http import _collect_resource_ids, _project_for_resource
from app.security.secrets import scan_domain_payload

T = TypeVar("T")

_settings: Settings | None = None
_session_factory: sessionmaker | None = None
_embedding_client: EmbeddingClient | None = None
_principal: AuthPrincipal | None = None


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
    "get_modeling_batch": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "list_session_modeling_batches": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "list_ontology_modeling_batches": _policy(
        "read", McpOwnership.PROJECT_RESOURCE, mutates_state=False
    ),
    "get_modeling_context": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "get_ontology_read_model": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "list_evidence_references": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "get_evidence_reference": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
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
    "get_ontology_lineage": _policy("read", McpOwnership.PROJECT_RESOURCE, mutates_state=False),
    "inspect_semantic_statement_provenance": _policy(
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
    "create_evidence_reference": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
    "associate_evidence_reference": _policy(
        "model", McpOwnership.PROJECT_RESOURCE, mutates_state=True
    ),
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
    global _settings, _session_factory, _embedding_client, _principal
    _settings = None
    _session_factory = None
    _embedding_client = None
    _principal = None


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
    record = session.get(ApiKeyModel, _principal.subject_id)
    if record is None or record.revoked_at is not None:
        raise PermissionError("MCP credential is no longer valid")
    try:
        current_scopes = validate_scopes(record.scopes, record.project_id)
    except ValueError as exc:
        raise PermissionError("MCP credential is no longer valid") from exc
    principal = AuthPrincipal(
        subject_type="api_key",
        subject_id=record.id,
        actor=f"key:{record.name}",
        scopes=current_scopes,
        project_id=record.project_id,
        auth_method="mcp",
    )
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
    return principal


def _run_tool(fn: Callable[[Session, Any, EmbeddingClient], T]) -> dict[str, Any]:
    session_factory, _driver, embedding_client = get_resources()
    tool_name = inspect.currentframe().f_back.f_code.co_name
    try:
        with session_factory() as session:
            _authorize_tool(session, tool_name, fn)
            scan_domain_payload(_closure_values(fn))
            return {"ok": True, "data": _jsonable(fn(session, _driver, embedding_client))}
    except Exception as exc:
        code, message = map_exception(exc)
        return {"ok": False, "error": message, "error_code": code}
