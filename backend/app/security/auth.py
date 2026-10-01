from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import string
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.repositories.models import (
    ApiKeyModel,
    SecurityAuditEventModel,
    UserModel,
    ProjectUserMembershipModel,
    SemanticAccessRoleModel,
    SemanticAccessRoleMemberModel,
)
from app.services.semantic_protection_set import normalize_grants, ProtectionSetError

logger = logging.getLogger(__name__)
_password_hasher = PasswordHasher()
_BASE62 = string.ascii_letters + string.digits
_VALID_SCOPES = {"read", "model", "admin"}
_SCOPE_ORDER = {"read": 1, "model": 2, "admin": 3}
_AUDIT_DETAIL_KEYS = {
    "reason",
    "required_scope",
    "presented_auth_methods",
    "category",
    "name",
    "member_count",
    "allowed_grants",
    "grants_added",
    "grants_removed",
}


@dataclass(frozen=True)
class AuthPrincipal:
    subject_type: str
    subject_id: str
    actor: str
    scopes: frozenset[str]
    project_id: str | None
    auth_method: str
    semantic_grants: frozenset[str] = frozenset()
    user_id: str | None = None

    @property
    def effective_scopes(self) -> frozenset[str]:
        scopes = set(self.scopes)
        if "admin" in scopes:
            scopes.update(("model", "read"))
        if "model" in scopes:
            scopes.add("read")
        return frozenset(scopes)

    @property
    def is_org_admin(self) -> bool:
        return "admin" in self.effective_scopes and self.project_id is None


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def highest_scope(scopes: set[str] | frozenset[str]) -> str:
    return max(scopes, key=_SCOPE_ORDER.__getitem__)


def generate_api_key(scopes: set[str]) -> str:
    suffix = "".join(secrets.choice(_BASE62) for _ in range(32))
    return f"sk_{highest_scope(scopes)}_{suffix}"


def validate_scopes(scopes: list[str] | set[str], project_id: str | None) -> frozenset[str]:
    normalized = frozenset(scopes)
    if not normalized or not normalized <= _VALID_SCOPES:
        raise ValueError("scopes must contain only read, model, or admin")
    if project_id is None and "admin" not in normalized:
        raise ValueError("unbound API keys must include admin")
    return normalized


class AuthorizationDependencyError(RuntimeError):
    code = "dependency_error"
    status_code = 503

    def __init__(self):
        super().__init__("Subject authorization unavailable; retry after repairing the dependency")


def principal_from_key(
    session: Session, record: ApiKeyModel | None, *, auth_method: str = "bearer"
) -> AuthPrincipal | None:
    """Shared HTTP/MCP per-call resolution. Empty roles are a valid empty permission set."""
    if record is None or record.revoked_at is not None:
        return None
    try:
        scopes = validate_scopes(record.scopes, record.project_id)
    except (ValueError, TypeError):
        return None
    grants: set[str] = set()
    try:
        if record.user_id is not None:
            user = session.get(UserModel, record.user_id)
            if user is None or user.disabled_at is not None:
                return None
            if record.project_id is None and not user.is_org_admin:
                return None
        elif not (record.is_bootstrap and record.project_id is None and "admin" in scopes):
            return None
        if record.project_id is not None:
            if session.get(ProjectUserMembershipModel, (record.project_id, record.user_id)) is None:
                return None
            roles = session.scalars(
                select(SemanticAccessRoleModel)
                .join(
                    SemanticAccessRoleMemberModel,
                    (SemanticAccessRoleMemberModel.role_id == SemanticAccessRoleModel.id)
                    & (
                        SemanticAccessRoleMemberModel.project_id
                        == SemanticAccessRoleModel.project_id
                    ),
                )
                .where(
                    SemanticAccessRoleMemberModel.project_id == record.project_id,
                    SemanticAccessRoleMemberModel.user_id == record.user_id,
                )
            )
            for role in roles:
                if not isinstance(role.grants, list):
                    raise AuthorizationDependencyError()
                grants.update(normalize_grants(role.grants))
    except (SQLAlchemyError, ProtectionSetError) as exc:
        raise AuthorizationDependencyError() from exc
    return AuthPrincipal(
        subject_type="api_key",
        subject_id=record.id,
        actor=f"key:{record.name}",
        scopes=scopes,
        project_id=record.project_id,
        auth_method=auth_method,
        semantic_grants=frozenset(grants),
        user_id=record.user_id,
    )


def resolve_api_key(session: Session, plaintext: str) -> AuthPrincipal | None:
    try:
        record = session.scalar(
            select(ApiKeyModel).where(ApiKeyModel.key_hash == hash_api_key(plaintext))
        )
        return principal_from_key(session, record)
    except SQLAlchemyError as exc:
        raise AuthorizationDependencyError() from exc


def create_api_key(
    session: Session,
    *,
    name: str,
    project_id: str | None,
    scopes: list[str],
    plaintext: str | None = None,
    user_id: str | None = None,
    bootstrap: bool = False,
) -> tuple[ApiKeyModel, str]:
    normalized = validate_scopes(scopes, project_id)
    if user_id is None:
        if not (bootstrap and project_id is None and "admin" in normalized):
            raise ValueError("user_id is required")
    else:
        user = session.get(UserModel, user_id)
        if user is None or user.disabled_at is not None:
            raise ValueError("user_id must identify an enabled user")
        if project_id is None and not user.is_org_admin:
            raise ValueError("organization admin keys require an organization administrator")
        if (
            project_id is not None
            and session.get(ProjectUserMembershipModel, (project_id, user_id)) is None
        ):
            raise ValueError("user_id must be a member of the selected Project")
    key = plaintext or generate_api_key(set(normalized))
    expected_prefix = f"sk_{highest_scope(normalized)}_"
    if not key.startswith(expected_prefix) or len(key) != len(expected_prefix) + 32:
        raise ValueError("API key format does not match its highest scope")
    record = ApiKeyModel(
        id=str(uuid4()),
        name=name,
        key_hash=hash_api_key(key),
        project_id=project_id,
        scopes=sorted(normalized, key=_SCOPE_ORDER.__getitem__),
        user_id=user_id,
        is_bootstrap=bootstrap and user_id is None,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record, key


def audit_security_event(
    session_factory: sessionmaker,
    event_type: str,
    outcome: str,
    principal: AuthPrincipal | None = None,
    *,
    project_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    safe_details = {
        key: value for key, value in (details or {}).items() if key in _AUDIT_DETAIL_KEYS
    }
    try:
        with session_factory() as session:
            session.add(
                SecurityAuditEventModel(
                    id=str(uuid4()),
                    event_type=event_type,
                    outcome=outcome,
                    actor=principal.actor if principal else None,
                    auth_method=principal.auth_method if principal else None,
                    project_id=project_id or (principal.project_id if principal else None),
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details=safe_details,
                )
            )
            session.commit()
    except Exception:
        logger.exception("Failed to persist a redacted security event")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sign_session(user: UserModel, secret_key: str, *, now: int | None = None) -> str:
    payload = {
        "uid": user.id,
        "username": user.username,
        "version": user.session_version,
        "exp": (now or int(time.time())) + 7 * 24 * 60 * 60,
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _b64encode(hmac.new(secret_key.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def resolve_session(session: Session, token: str, secret_key: str) -> AuthPrincipal | None:
    try:
        body, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(secret_key.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64decode(body))
        if int(payload["exp"]) < int(time.time()):
            return None
        user = session.get(UserModel, payload["uid"])
        if (
            user is None
            or not user.is_org_admin
            or user.disabled_at is not None
            or user.username != payload["username"]
            or user.session_version != int(payload["version"])
        ):
            return None
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return AuthPrincipal(
        subject_type="user",
        subject_id=user.id,
        actor=f"user:{user.username}",
        scopes=frozenset({"admin"}),
        project_id=None,
        auth_method="session",
        user_id=user.id,
    )


def revoke_key(session: Session, record: ApiKeyModel) -> ApiKeyModel:
    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        session.commit()
        session.refresh(record)
    return record


def bootstrap_identities(session_factory: sessionmaker, settings: Settings) -> None:
    username = settings.ontology_bootstrap_admin_user
    password = settings.ontology_bootstrap_admin_password
    if bool(username) != bool(password):
        raise RuntimeError(
            "ONTOLOGY_BOOTSTRAP_ADMIN_USER and ONTOLOGY_BOOTSTRAP_ADMIN_PASSWORD must be set together"
        )
    if not username and not settings.ontology_bootstrap_admin_api_key:
        logger.warning("No bootstrap admin identity configured")
        return
    with session_factory() as session:
        if (
            username
            and session.scalar(select(UserModel).where(UserModel.username == username)) is None
        ):
            session.add(
                UserModel(
                    id=str(uuid4()),
                    username=username,
                    password_hash=hash_password(password),
                    is_org_admin=True,
                    session_version=1,
                )
            )
            session.commit()
        plaintext = settings.ontology_bootstrap_admin_api_key
        if plaintext:
            key_hash = hash_api_key(plaintext)
            existing = session.scalar(select(ApiKeyModel).where(ApiKeyModel.key_hash == key_hash))
            if existing is not None:
                if (
                    existing.user_id is None
                    and existing.project_id is None
                    and "admin" in existing.scopes
                ):
                    existing.is_bootstrap = True
                    session.commit()
                return
            named = session.scalar(select(ApiKeyModel).where(ApiKeyModel.name == "bootstrap-admin"))
            if named is not None:
                logger.warning("bootstrap-admin key already exists; refusing implicit replacement")
                return
            create_api_key(
                session,
                name="bootstrap-admin",
                project_id=None,
                scopes=["admin"],
                plaintext=plaintext,
                bootstrap=True,
            )


def ephemeral_secret_key(settings: Settings) -> str:
    if settings.secret_key:
        return settings.secret_key
    logger.warning("SECRET_KEY is unset; browser sessions will not survive process restart")
    return secrets.token_urlsafe(48)
