from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.repositories.models import ApiKeyModel, ProjectModel, UserModel
from app.security.auth import (
    AuthPrincipal,
    audit_security_event,
    create_api_key,
    revoke_key,
    sign_session,
    validate_scopes,
    verify_password,
)
from app.security.http import CSRF_COOKIE, SESSION_COOKIE, principal_dependency

router = APIRouter(tags=["authentication"])
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_LOGIN_WINDOW_SECONDS = 60.0
_LOGIN_LIMIT = 5


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=4096)


class PrincipalRead(BaseModel):
    subject_type: str
    subject_id: str
    actor: str
    scopes: list[str]
    project_id: str | None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_id: str | None = None
    scopes: list[str] = Field(min_length=1)


class ApiKeyRead(BaseModel):
    id: str
    name: str
    project_id: str | None
    scopes: list[str]
    created_at: datetime
    revoked_at: datetime | None

    @classmethod
    def from_record(cls, record: ApiKeyModel) -> "ApiKeyRead":
        return cls(
            id=record.id,
            name=record.name,
            project_id=record.project_id,
            scopes=list(record.scopes),
            created_at=record.created_at,
            revoked_at=record.revoked_at,
        )


class ApiKeyCreated(ApiKeyRead):
    plaintext_key: str


def _principal_read(principal: AuthPrincipal) -> PrincipalRead:
    return PrincipalRead(
        subject_type=principal.subject_type,
        subject_id=principal.subject_id,
        actor=principal.actor,
        scopes=sorted(principal.effective_scopes),
        project_id=principal.project_id,
    )


def _require_admin(principal: AuthPrincipal) -> None:
    if "admin" not in principal.effective_scopes:
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})


@router.post("/auth/login", response_model=PrincipalRead)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db_session),
) -> PrincipalRead:
    now = time.monotonic()
    bucket_key = f"{request.client.host if request.client else 'unknown'}:{payload.username}"
    failures = _login_failures[bucket_key]
    while failures and failures[0] < now - _LOGIN_WINDOW_SECONDS:
        failures.popleft()
    if len(failures) >= _LOGIN_LIMIT:
        audit_security_event(
            request.app.state.session_factory,
            "login_failure",
            "rate_limited",
            details={"reason": "rate_limited"},
        )
        raise HTTPException(status_code=429, detail={"code": "login_rate_limited"})
    user = session.scalar(select(UserModel).where(UserModel.username == payload.username))
    if user is None or not verify_password(user.password_hash, payload.password):
        failures.append(now)
        audit_security_event(
            request.app.state.session_factory,
            "login_failure",
            "denied",
            details={"reason": "invalid_credentials"},
        )
        raise HTTPException(status_code=401, detail={"code": "invalid_authentication"})
    failures.clear()
    principal = AuthPrincipal(
        subject_type="user",
        subject_id=user.id,
        actor=f"user:{user.username}",
        scopes=frozenset({"admin"}),
        project_id=None,
        auth_method="session",
    )
    secure = request.app.state.settings.app_env.lower() in {"production", "prod"}
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(user, request.app.state.session_secret),
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=7 * 24 * 60 * 60,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )
    audit_security_event(request.app.state.session_factory, "login_success", "success", principal)
    return _principal_read(principal)


@router.get("/auth/me", response_model=PrincipalRead)
def me(principal: Annotated[AuthPrincipal, Depends(principal_dependency)]) -> PrincipalRead:
    return _principal_read(principal)


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/api-keys", response_model=list[ApiKeyRead])
def list_api_keys(
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> list[ApiKeyRead]:
    _require_admin(principal)
    statement = select(ApiKeyModel).order_by(ApiKeyModel.created_at.desc())
    if not principal.is_org_admin:
        statement = statement.where(ApiKeyModel.project_id == principal.project_id)
    return [ApiKeyRead.from_record(row) for row in session.scalars(statement)]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_key(
    payload: ApiKeyCreate,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> ApiKeyCreated:
    _require_admin(principal)
    if principal.is_org_admin:
        pass
    elif payload.project_id != principal.project_id:
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})
    if not set(payload.scopes) <= principal.effective_scopes:
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})
    if payload.project_id is not None and session.get(ProjectModel, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        validate_scopes(payload.scopes, payload.project_id)
        record, plaintext = create_api_key(
            session,
            name=payload.name,
            project_id=payload.project_id,
            scopes=payload.scopes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_security_event(
        request.app.state.session_factory,
        "api_key_created",
        "success",
        principal,
        project_id=record.project_id,
        resource_type="api_key",
        resource_id=record.id,
    )
    return ApiKeyCreated(**ApiKeyRead.from_record(record).model_dump(), plaintext_key=plaintext)


def _visible_key(session: Session, key_id: str, principal: AuthPrincipal) -> ApiKeyModel:
    record = session.get(ApiKeyModel, key_id)
    if record is None or (not principal.is_org_admin and record.project_id != principal.project_id):
        raise HTTPException(status_code=404, detail="API key not found")
    return record


@router.get("/api-keys/{key_id}", response_model=ApiKeyRead)
def get_api_key(
    key_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> ApiKeyRead:
    _require_admin(principal)
    return ApiKeyRead.from_record(_visible_key(session, key_id, principal))


@router.post("/api-keys/{key_id}:revoke", response_model=ApiKeyRead)
def revoke_api_key(
    key_id: str,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_dependency)],
    session: Session = Depends(get_db_session),
) -> ApiKeyRead:
    _require_admin(principal)
    record = _visible_key(session, key_id, principal)
    if record.project_id is None and not principal.is_org_admin:
        raise HTTPException(status_code=403, detail={"code": "forbidden_scope"})
    record = revoke_key(session, record)
    audit_security_event(
        request.app.state.session_factory,
        "api_key_revoked",
        "success",
        principal,
        project_id=record.project_id,
        resource_type="api_key",
        resource_id=record.id,
    )
    return ApiKeyRead.from_record(record)
