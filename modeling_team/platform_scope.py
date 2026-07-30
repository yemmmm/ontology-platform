"""Exact ownership lifecycle for the R2.3-001 empty platform scope."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


class PlatformScopeError(RuntimeError):
    pass


def _http(
    base_url: str, method: str, path: str, body: dict[str, Any] | None, key: str
) -> tuple[int, Any]:
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base_url + path,
        data=payload,
        method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read() or b"null")
        except json.JSONDecodeError:
            value = None
        return exc.code, value


@dataclass
class PlatformScope:
    base_url: str
    run_id: str
    bootstrap_admin: Callable[[], tuple[str, str]]
    revoke_admin: Callable[[str], bool]
    request: (
        Callable[[str, str, dict[str, Any] | None, str], tuple[int, Any]] | None
    ) = None
    admin_key: str | None = None
    admin_key_id: str | None = None
    protocol_key: str | None = None
    protocol_key_id: str | None = None
    project_id: str | None = None
    ontology_id: str | None = None
    mode: str | None = None
    owned: bool = False
    existing_context_before: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.request is None:
            self.request = lambda method, path, body, key: _http(
                self.base_url, method, path, body, key
            )

    def prepare(self, scope: dict[str, str]) -> None:
        mode = scope.get("mode")
        if mode not in {"create", "existing"}:
            raise PlatformScopeError("scope.mode must be create or existing")
        self.mode = mode
        self.admin_key, self.admin_key_id = self.bootstrap_admin()
        try:
            if mode == "create":
                self._create()
            else:
                self._existing(scope)
            self._create_protocol_key()
        except Exception:
            self.cleanup()
            raise

    def _ok(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        statuses: set[int] = {200},
    ) -> Any:
        if not self.admin_key:
            raise PlatformScopeError("admin key unavailable")
        assert self.request is not None
        status, value = self.request(method, path, body, self.admin_key)
        if status not in statuses:
            raise PlatformScopeError(
                f"platform request {method} {path} failed ({status})"
            )
        return value

    def _create(self) -> None:
        project = self._ok(
            "POST",
            "/api/projects",
            {
                "name": f"R2.3 team {self.run_id}",
                "description": "owned empty Team Runner scope",
            },
            statuses={201},
        )
        self.project_id = (
            project.get("id") if isinstance(project.get("id"), str) else None
        )
        if not self.project_id:
            raise PlatformScopeError("created Project has no identity")
        ontology = self._ok(
            "POST",
            f"/api/projects/{self.project_id}/ontologies",
            {
                "name": f"R2.3 {self.run_id}",
                "description": "owned empty ontology",
                "external_mappings": {},
            },
            statuses={201},
        )
        self.ontology_id = (
            ontology.get("id") if isinstance(ontology.get("id"), str) else None
        )
        if not self.ontology_id:
            raise PlatformScopeError("created Ontology has no identity")
        self.owned = True
        self._empty_context()

    def _existing(self, scope: dict[str, str]) -> None:
        project, ontology = scope.get("project_id"), scope.get("ontology_id")
        if not project or not ontology:
            raise PlatformScopeError("existing scope requires Project and Ontology IDs")
        self._ok("GET", f"/api/projects/{project}")
        listed = self._ok("GET", f"/api/projects/{project}/ontologies")
        if not isinstance(listed, list):
            raise PlatformScopeError("Project Ontology listing is invalid")
        if not any(
            item.get("id") == ontology for item in listed if isinstance(item, dict)
        ):
            raise PlatformScopeError("Ontology does not belong to existing Project")
        self.project_id, self.ontology_id, self.owned = project, ontology, False
        self.existing_context_before = self._empty_context()

    def _empty_context(self) -> dict[str, Any]:
        if not self.ontology_id:
            raise PlatformScopeError("ontology unavailable")
        context = self._ok(
            "GET", f"/api/ontologies/{self.ontology_id}/workspace-context"
        )
        if context.get("state") != "ready":
            raise PlatformScopeError("ontology workspace is not ready")
        batches = self._ok(
            "GET", f"/api/ontologies/{self.ontology_id}/modeling-batches"
        )
        items = batches.get("items", batches.get("batches", []))
        if not isinstance(items, list) or items:
            raise PlatformScopeError("R2.3-001 scope has Modeling Batch history")
        build = self._ok("GET", f"/api/projects/{self.project_id}/build-context")
        sessions = build.get("recent_sessions", build.get("sessions", []))
        if not isinstance(sessions, list) or sessions:
            raise PlatformScopeError("R2.3-001 scope is not empty")
        return {
            "workspace_state": context["state"],
            "modeling_batch_count": len(items),
            "recent_session_count": len(sessions),
        }

    def _create_protocol_key(self) -> None:
        created = self._ok(
            "POST",
            "/api/api-keys",
            {
                "name": f"r2-3-001-{self.run_id}",
                "project_id": self.project_id,
                "scopes": ["model"],
            },
            statuses={201},
        )
        self.protocol_key, self.protocol_key_id = (
            created.get("plaintext_key"),
            created.get("id"),
        )
        if not isinstance(self.protocol_key, str) or not isinstance(
            self.protocol_key_id, str
        ):
            raise PlatformScopeError("Protocol key creation failed")

    def cleanup(self) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "mode": self.mode,
            "project_id": self.project_id,
            "ontology_id": self.ontology_id,
            "owned": self.owned,
        }
        if self.protocol_key_id and self.admin_key:
            assert self.request is not None
            status, value = self.request(
                "POST",
                f"/api/api-keys/{self.protocol_key_id}:revoke",
                None,
                self.admin_key,
            )
            evidence["protocol_key_revoked"] = (
                status == 200
                and isinstance(value, dict)
                and bool(value.get("revoked_at"))
            )
        if not self.owned and self.mode == "existing":
            evidence["existing_context_before"] = self.existing_context_before
            try:
                evidence["existing_context_after"] = self._empty_context()
            except PlatformScopeError as exc:
                evidence["existing_context_after_error"] = str(exc)
        if self.owned and self.project_id and self.admin_key:
            try:
                self._empty_context()
                assert self.request is not None
                status, _ = self.request(
                    "DELETE", f"/api/projects/{self.project_id}", None, self.admin_key
                )
                evidence["owned_project_deleted"] = status == 204
            except PlatformScopeError as exc:
                evidence["owned_project_preserved"] = str(exc)
        if self.admin_key_id:
            evidence["admin_key_revoked"] = self.revoke_admin(self.admin_key_id)
        self.protocol_key = self.admin_key = None
        return evidence
