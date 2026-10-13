"""Versioned, integrity-protected continuation cursors for Context Query.

R1.2-004 cursors carry only the minimum continuation keys and a binding
fingerprint. They never carry raw query text. A configured stable signing
secret makes cursors survive process restart; without one, the codec
derives a process-local ephemeral key and advertises that limitation via
``ContextCursorCodec.capabilities``. Rotation or restart then invalidates
outstanding cursors as ``invalid_context_cursor`` rather than resuming
against an unverified version.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.security.auth import AuthPrincipal


CURSOR_VERSION = 4
CURSOR_KIND_MATCH = "match"
CURSOR_KIND_CONTEXT = "context"
CURSOR_KINDS = (CURSOR_KIND_MATCH, CURSOR_KIND_CONTEXT)


class ContextCursorError(RuntimeError):
    """Base class for stable cursor failures.

    ``code`` is one of: ``invalid_context_cursor``, ``context_cursor_mismatch``,
    ``context_snapshot_changed``. ``status_code`` mirrors the HTTP mapping used
    by the REST adapter.
    """

    code = "invalid_context_cursor"
    status_code = 400


class ContextCursorInvalid(ContextCursorError):
    code = "invalid_context_cursor"
    status_code = 400


class ContextCursorMismatch(ContextCursorError):
    code = "context_cursor_mismatch"
    status_code = 400


class ContextSnapshotChanged(ContextCursorError):
    code = "context_snapshot_changed"
    status_code = 409


@dataclass(frozen=True)
class CursorBinding:
    """Caller-supplied continuation request that must match the cursor."""

    principal: AuthPrincipal
    project_id: str
    scope_mode: str
    ontology_ids: tuple[str, ...]
    original_queries: tuple[str, ...]
    normalized_queries: tuple[str, ...]
    resource_types: tuple[str, ...]
    assertion_types: tuple[str, ...]
    search_mode: str
    depth: int
    limit: int
    context_limit: int
    model_revisions: tuple[tuple[str, int], ...]
    semantic_roles: tuple[str, ...] = ()
    # These fields are optional so older direct callers keep the historical
    # fixed/full/empty binding while new adaptive requests bind their full
    # selection contract.
    expansion_strategy: str = "fixed"
    context_detail: str = "full"
    selection_config_digest: str = ""


@dataclass(frozen=True)
class CursorPayload:
    """Minimal continuation keys plus a binding fingerprint."""

    kind: str
    binding_digest: str
    model_revisions: tuple[tuple[str, int], ...]
    resume_key: tuple[Any, ...] = ()
    root_match_ids: tuple[str, ...] = ()
    match_page_start_key: tuple[Any, ...] = ()
    root_match_digest: str = ""
    candidate_digest: str = ""
    context_digest: str = ""
    ranking_snapshot_id: str = ""
    issued_at: int = 0
    version: int = CURSOR_VERSION
    context_snapshot_id: str = ""


@dataclass
class ContextCursorCodec:
    """Sign and verify Context Query cursors.

    The codec is process-local by default. Configure
    ``semantic_context_query_cursor_signing_secret`` for stable cursors that
    survive restart.
    """

    secret: str
    lifetime_seconds: int
    stable_secret: bool
    ephemeral_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))

    @classmethod
    def from_settings(cls, settings: Settings) -> "ContextCursorCodec":
        secret = settings.semantic_context_query_cursor_signing_secret
        return cls(
            secret=secret,
            lifetime_seconds=settings.semantic_context_query_cursor_lifetime_seconds,
            stable_secret=bool(secret),
        )

    @property
    def capabilities(self) -> dict[str, Any]:
        return {
            "version": CURSOR_VERSION,
            "kinds": list(CURSOR_KINDS),
            "lifetime_seconds": self.lifetime_seconds,
            "stable_secret_configured": self.stable_secret,
        }

    def encode(self, payload: CursorPayload) -> str:
        if payload.kind not in CURSOR_KINDS:
            raise ContextCursorInvalid(f"Unsupported cursor kind: {payload.kind}")
        body = {
            "v": payload.version,
            "k": payload.kind,
            "b": payload.binding_digest,
            "mr": [list(item) for item in payload.model_revisions],
            "r": list(payload.resume_key),
            "ms": list(payload.match_page_start_key),
            "rd": payload.root_match_digest,
            "cd": payload.candidate_digest,
            "xd": payload.context_digest,
            "rs": payload.ranking_snapshot_id,
            "cs": payload.context_snapshot_id,
            "i": int(payload.issued_at or time.time()),
        }
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        body_b64 = _b64encode(raw)
        signature = _sign(self._signing_key(), body_b64)
        return f"{body_b64}.{signature}"

    def decode(
        self,
        token: str,
        *,
        binding: CursorBinding,
        expected_kind: str,
    ) -> CursorPayload:
        if expected_kind not in CURSOR_KINDS:
            raise ContextCursorInvalid(f"Unsupported cursor kind: {expected_kind}")
        if not isinstance(token, str) or "." not in token:
            raise ContextCursorInvalid("Cursor is malformed")
        body_b64, signature = token.split(".", 1)
        expected = _sign(self._signing_key(), body_b64)
        if not hmac.compare_digest(signature, expected):
            raise ContextCursorInvalid("Cursor signature is invalid")
        try:
            payload = json.loads(_b64decode(body_b64).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ContextCursorInvalid("Cursor payload is malformed") from exc
        if payload.get("v") != CURSOR_VERSION:
            raise ContextCursorInvalid("Cursor version is unsupported")
        kind = payload.get("k")
        if kind not in CURSOR_KINDS:
            raise ContextCursorInvalid("Cursor kind is unsupported")
        if kind != expected_kind:
            raise ContextCursorInvalid(
                f"Cursor kind {kind} cannot be used as {expected_kind}"
            )
        issued_at = int(payload.get("i") or 0)
        if issued_at <= 0 or time.time() - issued_at > self.lifetime_seconds:
            raise ContextCursorInvalid("Cursor is expired")
        binding_digest = _binding_digest(binding)
        if not hmac.compare_digest(str(payload.get("b") or ""), binding_digest):
            raise ContextCursorMismatch("Cursor no longer matches the request parameters")
        pairs = payload.get("mr")
        if not isinstance(pairs, list) or any(
            not isinstance(pair, list) or len(pair) != 2
            or not isinstance(pair[0], str) or type(pair[1]) is not int or pair[1] < 0
            for pair in pairs
        ):
            raise ContextCursorInvalid("Cursor model revisions are malformed")
        model_revisions = tuple((pair[0], pair[1]) for pair in pairs)
        if model_revisions != binding.model_revisions:
            raise ContextSnapshotChanged(
                "Ontology model_revision no longer matches the cursor"
            )
        return CursorPayload(
            kind=kind,
            binding_digest=binding_digest,
            model_revisions=model_revisions,
            resume_key=tuple(_normalise_resume_key(item) for item in payload.get("r") or []),
            root_match_ids=tuple(str(item) for item in payload.get("rm") or []),
            match_page_start_key=tuple(
                _normalise_resume_key(item) for item in payload.get("ms") or []
            ),
            root_match_digest=str(payload.get("rd") or ""),
            candidate_digest=str(payload.get("cd") or ""),
            context_digest=str(payload.get("xd") or ""),
            ranking_snapshot_id=str(payload.get("rs") or ""),
            context_snapshot_id=str(payload.get("cs") or ""),
            issued_at=issued_at,
            version=int(payload.get("v") or CURSOR_VERSION),
        )

    def _signing_key(self) -> bytes:
        if self.secret:
            return self.secret.encode("utf-8")
        return self.ephemeral_token.encode("utf-8")


def make_binding(
    *,
    principal: AuthPrincipal,
    project_id: str,
    scope_mode: str,
    ontology_ids: list[str] | tuple[str, ...],
    original_queries: list[str] | tuple[str, ...],
    normalized_queries: list[str] | tuple[str, ...],
    resource_types: list[str] | tuple[str, ...] | None,
    assertion_types: list[str] | tuple[str, ...] | None,
    search_mode: str,
    depth: int,
    limit: int,
    context_limit: int,
    model_revisions: list[tuple[str, int]] | tuple[tuple[str, int], ...],
    semantic_roles: list[str] | None = None,
    expansion_strategy: str = "fixed",
    context_detail: str = "full",
    selection_config_digest: str = "",
) -> CursorBinding:
    return CursorBinding(
        principal=principal,
        project_id=project_id,
        scope_mode=scope_mode,
        ontology_ids=tuple(ontology_ids),
        original_queries=tuple(original_queries),
        normalized_queries=tuple(normalized_queries),
        resource_types=tuple(resource_types or ()),
        assertion_types=tuple(assertion_types or ()),
        search_mode=search_mode,
        depth=depth,
        limit=limit,
        context_limit=context_limit,
        model_revisions=tuple(model_revisions),
        semantic_roles=tuple(semantic_roles or ()),
        expansion_strategy=expansion_strategy,
        context_detail=context_detail,
        selection_config_digest=selection_config_digest,
    )


def _binding_digest(binding: CursorBinding) -> str:
    return binding_digest(binding)


def binding_digest(binding: CursorBinding) -> str:
    """Stable SHA-256 fingerprint of the cursor binding."""
    payload = {
        "subject_type": binding.principal.subject_type,
        "subject_id": binding.principal.subject_id,
        "actor": binding.principal.actor,
        "user_id": binding.principal.user_id,
        "effective_scopes": sorted(binding.principal.effective_scopes),
        "semantic_grants": sorted(binding.principal.semantic_grants),
        "project_id": binding.principal.project_id,
        "scope_project_id": binding.project_id,
        "scope_mode": binding.scope_mode,
        "ontology_ids": list(binding.ontology_ids),
        "original_queries": list(binding.original_queries),
        "normalized_queries": list(binding.normalized_queries),
        "resource_types": list(binding.resource_types),
        "assertion_types": list(binding.assertion_types),
        "semantic_roles": list(binding.semantic_roles),
        "search_mode": binding.search_mode,
        "depth": binding.depth,
        "limit": binding.limit,
        "context_limit": binding.context_limit,
        "expansion_strategy": binding.expansion_strategy,
        "context_detail": binding.context_detail,
        "selection_config_digest": binding.selection_config_digest,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalise_resume_key(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_normalise_resume_key(item) for item in value)
    return value


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(key: bytes, body: str) -> str:
    return _b64encode(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())
