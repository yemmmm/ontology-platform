from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Receive, Scope, Send

from app.repositories.models import (
    BuildSessionModel,
    CompetencyQuestionModel,
    EvidenceArtifactModel,
    EvidenceAssociationModel,
    EvidenceChunkModel,
    EvidenceReferenceModel,
    ModelingBatchModel,
    BuildCheckpointModel,
    OntologyModel,
    ProjectModel,
    SemanticGraphSetModel,
    SemanticGraphRegistryModel,
    SemanticRuleDefinitionModel,
    SemanticRuleModel,
    SemanticRuleRunModel,
    SemanticProjectionJobModel,
    SemanticEditAuditModel,
)
from app.security.auth import AuthPrincipal, audit_security_event, resolve_api_key, resolve_session
from app.security.secrets import reject_domain_secrets

PUBLIC_PATHS = {
    ("GET", "/api/health"),
    ("GET", "/api/health/postgres"),
    ("GET", "/api/health/dependencies"),
    ("POST", "/api/auth/login"),
}
SESSION_COOKIE = "ontology_session"
CSRF_COOKIE = "ontology_csrf"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

OWNER_RESOURCE_KEYS = frozenset(
    {
        "project_id",
        "ontology_id",
        "session_id",
        "build_session_id",
        "checkpoint_id",
        "batch_id",
        "artifact_id",
        "chunk_id",
        "reference_id",
        "evidence_reference_id",
        "association_id",
        "evidence_association_id",
        "question_id",
        "graph_set_id",
        "target_graph_set_id",
        "graph_iri",
        "target_graph_iri",
        "rule_id",
        "rule_definition_id",
        "run_id",
        "rule_run_id",
        "job_id",
        "projection_job_id",
        "audit_id",
        "edit_audit_id",
    }
)

HTTP_ROUTE_POLICIES: dict[tuple[str, str], str] = {}

_ADMIN_PATHS = (
    "/api/api-keys",
    "/api/semantic/migrations",
    "/api/semantic/derived-results:gc",
    "/api/semantic/canonical-mode",
)


def required_scope(method: str, path: str) -> str:
    if any(path.startswith(prefix) for prefix in _ADMIN_PATHS):
        return "admin"
    if method == "GET":
        return "read"
    if path == "/api/projects" or (
        re.fullmatch(r"/api/projects/[^/]+", path) and method in {"PATCH", "DELETE"}
    ):
        return "admin"
    if "/ontologies" in path and method in {"POST", "PATCH", "DELETE"}:
        return "admin"
    if path.endswith("/workspace/repair") or path.endswith("/ontology-workspaces/repair"):
        return "admin"
    if path in {"/api/semantic/context:query", "/api/semantic/sparql:query"}:
        return "read"
    return "model"


def install_http_route_policies(app) -> None:
    HTTP_ROUTE_POLICIES.clear()

    def walk(routes, prefix: str = "") -> None:
        for route in routes:
            original_router = getattr(route, "original_router", None)
            if original_router is not None:
                context = getattr(route, "include_context", None)
                walk(original_router.routes, prefix + getattr(context, "prefix", ""))
                continue
            path = prefix + getattr(route, "path_format", getattr(route, "path", ""))
            methods = getattr(route, "methods", set()) or set()
            for method in methods - {"HEAD", "OPTIONS"}:
                if (method, path) not in PUBLIC_PATHS:
                    HTTP_ROUTE_POLICIES[(method, path)] = required_scope(method, path)

    walk(app.routes)


def _auth_error() -> JSONResponse:
    return JSONResponse(
        {"detail": {"code": "invalid_authentication"}},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


class AuthenticationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        method = request.method
        path = request.url.path
        if (method, path) in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        app = request.app
        session_factory = app.state.session_factory
        authorization = request.headers.get("authorization", "")
        bearer_value = ""
        if authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() == "bearer" and value and " " not in value:
                bearer_value = value
        session_value = request.cookies.get(SESSION_COOKIE, "")
        bearer_principal = None
        session_principal = None
        with session_factory() as db:
            if bearer_value:
                bearer_principal = resolve_api_key(db, bearer_value)
            if session_value:
                session_principal = resolve_session(db, session_value, app.state.session_secret)
        principal = bearer_principal or session_principal
        if bearer_value and bearer_principal is None:
            audit_security_event(
                session_factory,
                "authentication_failure",
                "denied",
                details={"reason": "invalid_bearer"},
            )
            await _auth_error()(scope, receive, send)
            return
        if session_value and session_principal is None and not bearer_principal:
            audit_security_event(
                session_factory,
                "authentication_failure",
                "denied",
                details={"reason": "invalid_session"},
            )
            await _auth_error()(scope, receive, send)
            return
        if (
            bearer_principal
            and session_principal
            and (
                bearer_principal.subject_type,
                bearer_principal.subject_id,
            )
            != (session_principal.subject_type, session_principal.subject_id)
        ):
            audit_security_event(
                session_factory,
                "authentication_conflict",
                "denied",
                details={"presented_auth_methods": "bearer,session"},
            )
            await _auth_error()(scope, receive, send)
            return
        if principal is None:
            audit_security_event(
                session_factory,
                "authentication_failure",
                "denied",
                details={"reason": "missing_credentials"},
            )
            await _auth_error()(scope, receive, send)
            return
        if principal.auth_method == "session" and method in UNSAFE_METHODS:
            origin = request.headers.get("origin", "").rstrip("/")
            csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
            csrf_header = request.headers.get("x-csrf-token", "")
            if (
                not origin
                or origin not in app.state.settings.ontology_ui_origins
                or not csrf_cookie
                or not csrf_header
                or csrf_cookie != csrf_header
            ):
                audit_security_event(
                    session_factory,
                    "csrf_failure",
                    "denied",
                    principal,
                    details={"reason": "csrf_or_origin_mismatch"},
                )
                response = JSONResponse({"detail": {"code": "forbidden_scope"}}, status_code=403)
                await response(scope, receive, send)
                return
        scope.setdefault("state", {})["principal"] = principal
        await self.app(scope, receive, send)


def current_principal(request: Request) -> AuthPrincipal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_authentication"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def _project_for_resource(session: Session, kind: str, value: str) -> str | None:
    if kind == "target_graph_set_id":
        kind = "graph_set_id"
    if kind == "project_id":
        return value if session.get(ProjectModel, value) is not None else None
    if kind == "ontology_id":
        row = session.get(OntologyModel, value)
        return row.project_id if row else None
    if kind in {"session_id", "build_session_id"}:
        row = session.get(BuildSessionModel, value)
        return row.project_id if row else None
    if kind == "checkpoint_id":
        row = session.get(BuildCheckpointModel, value)
        build_session = session.get(BuildSessionModel, row.build_session_id) if row else None
        return build_session.project_id if build_session else None
    if kind == "batch_id":
        row = session.get(ModelingBatchModel, value)
        return row.project_id if row else None
    if kind == "artifact_id":
        row = session.get(EvidenceArtifactModel, value)
        return row.project_id if row else None
    if kind == "chunk_id":
        row = session.get(EvidenceChunkModel, value)
        artifact = session.get(EvidenceArtifactModel, row.document_id) if row else None
        return artifact.project_id if artifact else None
    if kind in {"reference_id", "evidence_reference_id"}:
        row = session.get(EvidenceReferenceModel, value)
        return row.project_id if row else None
    if kind in {"association_id", "evidence_association_id"}:
        row = session.get(EvidenceAssociationModel, value)
        return row.project_id if row else None
    if kind == "question_id":
        row = session.get(CompetencyQuestionModel, value)
        return row.project_id if row else None
    if kind == "graph_set_id":
        row = session.get(SemanticGraphSetModel, value)
        if row and row.scope_type == "ontology" and row.scope_id:
            ontology = session.get(OntologyModel, row.scope_id)
            if ontology is None:
                return None
            for member in row.members:
                if (
                    _project_for_resource(session, "graph_iri", member.graph_iri)
                    != ontology.project_id
                ):
                    return None
            return ontology.project_id
        return None
    if kind in {"graph_iri", "target_graph_iri"}:
        row = session.scalar(
            select(SemanticGraphRegistryModel).where(SemanticGraphRegistryModel.graph_iri == value)
        )
        if row and row.semantic_owner_type == "ontology" and row.semantic_owner_id:
            ontology = session.get(OntologyModel, row.semantic_owner_id)
            return ontology.project_id if ontology else None
        return None
    if kind in {"rule_id", "rule_definition_id"}:
        definition = session.get(SemanticRuleDefinitionModel, value)
        rule = (
            session.get(SemanticRuleModel, definition.semantic_rule_id)
            if definition and definition.semantic_rule_id
            else None
        )
        ontology = session.get(OntologyModel, rule.ontology_id) if rule else None
        return ontology.project_id if ontology else None
    if kind in {"run_id", "rule_run_id", "job_id", "projection_job_id"}:
        rule_run = session.get(SemanticRuleRunModel, value)
        if rule_run:
            return _project_for_resource(session, "graph_set_id", rule_run.graph_set_id)
        projection = session.get(SemanticProjectionJobModel, value)
        if projection and projection.graph_set_id:
            return _project_for_resource(session, "graph_set_id", projection.graph_set_id)
        return None
    if kind in {"audit_id", "edit_audit_id"}:
        audit = session.get(SemanticEditAuditModel, value)
        if audit:
            return _project_for_resource(session, "graph_iri", audit.target_graph_iri)
        return None
    return None


def _collect_resource_ids(value: Any, output: list[tuple[str, str]]) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, dict):
        if "owner_type" in value:
            owner_type = value.get("owner_type")
            owner_id = value.get("owner_id")
            if owner_type == "ontology" and isinstance(owner_id, str) and owner_id:
                output.append(("ontology_id", owner_id))
            elif owner_id is not None:
                output.append(("unowned_owner", str(owner_id or owner_type)))
        if "scope_type" in value:
            scope_type = value.get("scope_type")
            scope_id = value.get("scope_id")
            if scope_type == "ontology" and isinstance(scope_id, str) and scope_id:
                output.append(("ontology_id", scope_id))
            elif scope_type == "project" and isinstance(scope_id, str) and scope_id:
                output.append(("project_id", scope_id))
            elif scope_id is not None:
                output.append(("unowned_scope", str(scope_id or scope_type)))
        for key, child in value.items():
            if (
                (key in OWNER_RESOURCE_KEYS or key.endswith("graph_iri"))
                and isinstance(child, str)
                and child
            ):
                output.append(("graph_iri" if key.endswith("graph_iri") else key, child))
            elif key == "ontology_ids" and isinstance(child, list):
                output.extend(("ontology_id", item) for item in child if isinstance(item, str))
            elif key.endswith("graph_iris") and isinstance(child, list):
                output.extend(("graph_iri", item) for item in child if isinstance(item, str))
            elif key == "supersedes" and isinstance(child, str) and child:
                output.append(("graph_set_id", child))
            _collect_resource_ids(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_resource_ids(child, output)


async def authorize_api_request(request: Request) -> None:
    if (request.method, request.url.path) in PUBLIC_PATHS:
        return
    principal = current_principal(request)
    scope = required_scope(request.method, request.url.path)
    if scope not in principal.effective_scopes:
        audit_security_event(
            request.app.state.session_factory,
            "authorization_failure",
            "denied",
            principal,
            details={"required_scope": scope, "reason": "scope"},
        )
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})

    if request.method in UNSAFE_METHODS and request.url.path not in {
        "/api/auth/logout",
        "/api/api-keys",
    }:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                payload = await request.json()
            except Exception:
                payload = None
            if payload is not None:
                reject_domain_secrets(payload)
                actor = payload.get("actor") if isinstance(payload, dict) else None
                if actor is None and isinstance(payload, dict):
                    actor = payload.get("created_by") or payload.get("reported_by")
                if actor and actor != principal.actor:
                    request.state.actor_spoof_attempt = True
                    audit_security_event(
                        request.app.state.session_factory,
                        "actor_spoof_attempt",
                        "overridden",
                        principal,
                    )

    if principal.project_id is None:
        return
    if request.url.path == "/api/projects" and request.method == "POST":
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})
    if re.fullmatch(r"/api/projects/[^/]+", request.url.path) and request.method in {
        "PATCH",
        "DELETE",
    }:
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})

    ids: list[tuple[str, str]] = [
        (key, value) for key, value in request.path_params.items() if key in OWNER_RESOURCE_KEYS
    ]
    query_payload: dict[str, Any] = dict(request.query_params)
    ontology_ids = request.query_params.getlist("ontology_ids")
    if ontology_ids:
        query_payload["ontology_ids"] = ontology_ids
    graph_iris = request.query_params.getlist("graph_iri")
    if graph_iris:
        query_payload["graph_iris"] = graph_iris
    _collect_resource_ids(query_payload, ids)
    if request.method in UNSAFE_METHODS and "application/json" in request.headers.get(
        "content-type", ""
    ):
        try:
            _collect_resource_ids(await request.json(), ids)
        except Exception:
            pass
    if request.method == "POST" and request.url.path == "/api/semantic/graphs":
        ids = [(kind, value) for kind, value in ids if kind != "graph_iri"]
    if (
        request.method == "POST"
        and request.url.path in {"/api/semantic/graphs", "/api/semantic/graph-sets"}
        and not any(kind == "ontology_id" for kind, _value in ids)
    ):
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})
    explicit_project = any(kind == "project_id" for kind, _value in ids)
    org_only_without_scope = {
        "/api/semantic/edits/audits",
        "/api/semantic/status",
        "/api/semantic/validation-runs",
        "/api/semantic/reasoning-runs",
        "/api/semantic/rule-runs",
        "/api/semantic/projection-jobs",
        "/api/semantic/projections/status",
        "/api/semantic/migrations",
        "/api/semantic/canonical-mode",
        "/api/semantic/datasets:load",
        "/api/semantic/edits",
        "/api/semantic/export",
        "/api/semantic/resources",
        "/api/semantic/statements",
        "/api/semantic/derived-results:reconcile",
        "/api/semantic/derived-results:gc",
        "/api/semantic/canonical-writes:compile-and-apply",
        "/api/semantic/projections:reconcile",
    }
    if request.url.path in org_only_without_scope and not ids:
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})
    with request.app.state.session_factory() as session:
        for kind, value in ids:
            target_project = _project_for_resource(session, kind, value)
            if target_project is None:
                audit_security_event(
                    request.app.state.session_factory,
                    "authorization_failure",
                    "denied",
                    principal,
                    resource_type=kind,
                    resource_id=value,
                    details={"reason": "unresolved_owner"},
                )
                raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})
            if target_project is not None and target_project != principal.project_id:
                audit_security_event(
                    request.app.state.session_factory,
                    "authorization_failure",
                    "denied",
                    principal,
                    project_id=target_project,
                    resource_type=kind,
                    resource_id=value,
                    details={"reason": "project"},
                )
                if explicit_project:
                    raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})
                raise HTTPException(status_code=404, detail="Resource not found")


def principal_dependency(request: Request) -> AuthPrincipal:
    return current_principal(request)
