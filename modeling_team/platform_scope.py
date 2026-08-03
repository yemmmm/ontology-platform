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
    terminal_results: dict[str, dict[str, Any]] | None = None
    final_workspace_context: dict[str, Any] | None = None
    final_workspace_version: str | None = None
    completed_session_id: str | None = None
    scope_disposition: str | None = None

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
        agent_state = build.get("agent_state") if isinstance(build, dict) else None
        if not isinstance(agent_state, dict):
            raise PlatformScopeError("Build Context agent state is invalid")
        active = agent_state.get("active_sessions")
        recent = agent_state.get("recent_sessions")
        if not isinstance(active, list) or not isinstance(recent, list) or active or recent:
            raise PlatformScopeError("R2.3-001 scope is not empty")
        return {
            "workspace_state": context["state"],
            "modeling_batch_count": len(items),
            "recent_session_count": len(active) + len(recent),
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
        try:
            nonempty = self._has_writes() if self.owned and self.admin_key else False
            success_intent = nonempty and self._producer_completed() and self._retain_nonempty()
            terminal = self._terminal_state(
                allow_cancel=not success_intent, require_completed=success_intent
            )
        except Exception as exc:
            evidence["cleanup_blocker"] = str(exc)
            evidence["scope_disposition"] = "blocked"
            if self.protocol_key_id and self.admin_key:
                evidence["protocol_key_revoked"] = self._revoke_project_key(evidence)
            self._revoke_keys(evidence)
            return evidence
        evidence.update(terminal)
        evidence["no_in_flight_attempts"] = not bool(terminal.get("cleanup_blocker"))
        if terminal.get("cleanup_blocker"):
            evidence["scope_disposition"] = "blocked"
            if self.protocol_key_id and self.admin_key:
                evidence["protocol_key_revoked"] = self._revoke_project_key(evidence)
            self._revoke_keys(evidence)
            return evidence
        if self.protocol_key_id and self.admin_key:
            evidence["protocol_key_revoked"] = self._revoke_project_key(evidence)
        if not self.owned and self.mode == "existing":
            evidence["existing_context_before"] = self.existing_context_before
            try:
                evidence["existing_context_after"] = self._empty_context()
            except PlatformScopeError as exc:
                evidence["existing_context_after_error"] = str(exc)
        if self.owned and self.project_id and self.admin_key:
            try:
                succeeded = self._producer_completed()
                if nonempty and succeeded and self._retain_nonempty():
                    if terminal.get("success_blocker"):
                        self.scope_disposition = "failed-written-retained"
                        evidence["scope_disposition"] = self.scope_disposition
                        evidence["owned_project_preserved"] = terminal["success_blocker"]
                        self._revoke_keys(evidence)
                        return evidence
                    context = self._modeling_context()
                    self.final_workspace_context = context
                    self.scope_disposition = "retained-pending-acceptance"
                    self.final_workspace_version = self._workspace_version(context)
                    evidence["scope_disposition"] = self.scope_disposition
                    evidence["workspace_version"] = self.final_workspace_version
                    evidence["completed_session_id"] = self.completed_session_id
                elif nonempty:
                    self.scope_disposition = "failed-written-retained"
                    evidence["scope_disposition"] = self.scope_disposition
                    evidence["owned_project_preserved"] = "non-empty scope is not Runner-deletable"
                else:
                    first_stage = self._first_stage_delete_evidence(evidence, terminal)
                    evidence["first_stage"] = first_stage
                    if not first_stage.get("ready_for_delete"):
                        evidence["scope_disposition"] = "blocked"
                        evidence["owned_project_preserved"] = "first-stage cleanup evidence is incomplete"
                    else:
                        status = 0
                        value: Any = None
                        try:
                            assert self.request is not None
                            status, value = self.request(
                                "DELETE", f"/api/projects/{self.project_id}", None, self.admin_key
                            )
                            evidence["owned_project_deleted"] = status == 204
                            evidence["post_delete"] = self._post_delete_evidence()
                            evidence["scope_disposition"] = "deleted-empty" if status == 204 else "delete-failed"
                        except Exception as exc:
                            evidence["delete_error"] = str(exc)
                            evidence["scope_disposition"] = "delete-failed"
                        finally:
                            # The authenticated deletion credential is revoked even when DELETE or
                            # the post-delete rereads raise; no later cleanup path may retain it.
                            self._revoke_keys(evidence)
                            evidence.setdefault("second_stage", {})["delete_response"] = {
                                "status": status,
                                "body_type": type(value).__name__,
                            }
                            evidence["aggregate_keys_non_active"] = bool(
                                evidence.get("protocol_key_revoked")
                                and evidence.get("admin_key_revoked")
                            )
                        return evidence
            except PlatformScopeError as exc:
                evidence["owned_project_preserved"] = str(exc)
        self._revoke_keys(evidence)
        evidence["aggregate_keys_non_active"] = bool(
            evidence.get("protocol_key_revoked", True) and evidence.get("admin_key_revoked")
        )
        return evidence

    def _revoke_keys(self, evidence: dict[str, Any]) -> None:
        admin_id = self.admin_key_id
        admin_key = self.admin_key
        if admin_id:
            receipt: dict[str, Any] = {"id": admin_id, "project_id": None}
            revoked = False
            # Prefer the authenticated API receipt so revoked_at and the retained org audit row
            # are directly evidenced; the callback remains the narrow local fallback used by the
            # foreground CLI and older test doubles.
            if admin_key and self.request is not None:
                try:
                    status, value = self.request(
                        "POST", f"/api/api-keys/{admin_id}:revoke", None, admin_key
                    )
                    if status == 200 and isinstance(value, dict):
                        receipt.update(value)
                        revoked = bool(value.get("revoked_at"))
                except Exception:
                    revoked = False
            try:
                callback_result = self.revoke_admin(admin_id)
                revoked = revoked or bool(callback_result)
            except Exception as exc:
                evidence["admin_key_revoke_error"] = str(exc)
            receipt["non_active"] = revoked and bool(receipt.get("revoked_at"))
            receipt["active"] = False if receipt["non_active"] else None
            evidence["admin_key_revoked"] = receipt["non_active"]
            evidence["second_stage"] = {
                "org_admin_key": receipt,
                "retained_org_admin_audit_row": {
                    "key_id": admin_id,
                    "project_id": None,
                    "revoked_at": receipt.get("revoked_at"),
                    "retained": receipt["non_active"],
                },
            }
        self.protocol_key = self.admin_key = None
        self.admin_key_id = None

    def _revoke_project_key(self, evidence: dict[str, Any]) -> bool:
        if not self.protocol_key_id or not self.admin_key or self.request is None:
            return False
        key_id = self.protocol_key_id
        try:
            status, value = self.request(
                "POST", f"/api/api-keys/{key_id}:revoke", None, self.admin_key
            )
        except Exception as exc:
            evidence["protocol_key_revoke_error"] = str(exc)
            return False
        receipt = {
            "id": key_id,
            "project_id": self.project_id,
            "revoked_at": value.get("revoked_at") if isinstance(value, dict) else None,
            "non_active": status == 200 and isinstance(value, dict) and bool(value.get("revoked_at")),
            "active": False if status == 200 and isinstance(value, dict) and value.get("revoked_at") else None,
        }
        evidence["project_scoped_keys"] = [receipt]
        self.protocol_key = self.protocol_key_id = None
        return bool(receipt["non_active"])

    def _first_stage_delete_evidence(
        self, evidence: dict[str, Any], terminal: dict[str, Any]
    ) -> dict[str, Any]:
        admin_id = self.admin_key_id
        admin_status = self._key_status(admin_id) if admin_id and self.admin_key else {}
        project_keys = evidence.get("project_scoped_keys", [])
        ready = bool(
            isinstance(project_keys, list)
            and all(
                isinstance(item, dict) and item.get("non_active") is True for item in project_keys
            )
            and isinstance(admin_id, str)
            and admin_status.get("active") is True
            and terminal.get("sessions_terminal") is True
            and not terminal.get("cleanup_blocker")
        )
        return {
            "project_scoped_keys": project_keys,
            "bootstrap_admin": {
                "id": admin_id,
                "status": admin_status.get("status", "UNKNOWN"),
                "active": admin_status.get("active"),
                "purpose": "authenticated_project_delete",
                "excluded_from_non_active_assertion": True,
            },
            "session_terminal": terminal.get("sessions_terminal") is True,
            "lease_auto_released": terminal.get("sessions_terminal") is True,
            "lease_release_receipts": "terminal_state_reread",
            "no_in_flight_attempts": not bool(terminal.get("cleanup_blocker")),
            "ownership": {
                "owned": self.owned,
                "project_id": self.project_id,
                "ontology_id": self.ontology_id,
            },
            "cleanup_receipts": {
                "protocol_key_revoked": evidence.get("protocol_key_revoked") is True,
                "terminal_state_reread": terminal.get("sessions_terminal") is True,
                "scope_disposition": evidence.get("scope_disposition"),
            },
            "ready_for_delete": ready,
        }

    def _key_status(self, key_id: str | None) -> dict[str, Any]:
        if not key_id or not self.admin_key or self.request is None:
            return {}
        try:
            status, value = self.request("GET", f"/api/api-keys/{key_id}", None, self.admin_key)
        except Exception:
            return {}
        if status != 200 or not isinstance(value, dict):
            return {}
        revoked_at = value.get("revoked_at")
        return {
            "id": key_id,
            "status": "ACTIVE" if revoked_at is None else "NON_ACTIVE",
            "active": revoked_at is None,
            "revoked_at": revoked_at,
            "project_id": value.get("project_id"),
        }

    def _post_delete_evidence(self) -> dict[str, Any]:
        if not self.admin_key or self.request is None:
            return {
                "project_absent": None,
                "ontology_absent": None,
                "active_project_residual_count": None,
                "residual_counts": None,
            }
        checks: dict[str, Any] = {}
        for label, path in (
            ("project_absent", f"/api/projects/{self.project_id}"),
            ("ontology_absent", f"/api/ontologies/{self.ontology_id}"),
        ):
            try:
                status, _ = self.request("GET", path, None, self.admin_key)
            except Exception:
                status = 0
            checks[label] = status == 404
        try:
            status, value = self.request("GET", "/api/api-keys", None, self.admin_key)
            if status != 200 or not isinstance(value, list):
                checks["active_project_residual_count"] = None
                checks["fk_cascade"] = None
                checks["residual_counts"] = None
                return checks
            rows = value
            checks["active_project_residual_count"] = sum(
                1
                for row in rows
                if isinstance(row, dict)
                and row.get("project_id") == self.project_id
                and row.get("revoked_at") is None
            )
            checks["fk_cascade"] = checks["active_project_residual_count"] == 0
            absent = checks["project_absent"] is True and checks["ontology_absent"] is True
            checks["residual_counts"] = {
                "project": 0 if absent else None,
                "ontology": 0 if absent else None,
                "session": 0 if absent else None,
                "lease": 0 if absent else None,
                "project_scoped_key": checks["active_project_residual_count"],
            }
        except Exception:
            checks["active_project_residual_count"] = None
            checks["fk_cascade"] = None
            checks["residual_counts"] = None
        return checks

    def _workspace_context(self) -> dict[str, Any]:
        if not self.ontology_id:
            raise PlatformScopeError("ontology unavailable")
        context = self._ok("GET", f"/api/ontologies/{self.ontology_id}/workspace-context")
        if not isinstance(context, dict) or context.get("state") != "ready":
            raise PlatformScopeError("ontology workspace is not ready")
        return context

    def _modeling_context(self) -> dict[str, Any]:
        if not self.ontology_id:
            raise PlatformScopeError("ontology unavailable")
        context = self._ok("GET", f"/api/ontologies/{self.ontology_id}/modeling-context")
        if not isinstance(context, dict):
            raise PlatformScopeError("modeling context is invalid")
        project = context.get("project", {})
        ontology = context.get("ontology", {})
        if project.get("id") != self.project_id or ontology.get("id") != self.ontology_id:
            raise PlatformScopeError("modeling context ownership drifted")
        version = self._workspace_version(context)
        if not version:
            raise PlatformScopeError("modeling context has no workspace version")
        return context

    def read_protocol_context(self) -> dict[str, str]:
        """Return the non-secret mechanical scope needed for Protocol batch envelopes."""
        if not self.project_id or not self.ontology_id:
            raise PlatformScopeError("Protocol scope context is unavailable")
        context = self._modeling_context()
        workspace_version = self._workspace_version(context)
        if not workspace_version:
            raise PlatformScopeError("Protocol scope context has no workspace version")
        return {
            "project_id": self.project_id,
            "ontology_id": self.ontology_id,
            "workspace_version": workspace_version,
        }

    @staticmethod
    def _workspace_version(context: dict[str, Any]) -> str | None:
        workspace = context.get("workspace")
        value = workspace.get("workspace_version") if isinstance(workspace, dict) else None
        return value if isinstance(value, str) and value else None

    def _terminal_state(self, *, allow_cancel: bool, require_completed: bool) -> dict[str, Any]:
        """Cancel safe failed Sessions before any scope disposition is considered."""
        if not self.owned or not self.project_id or not self.admin_key:
            return {}
        build = self._ok("GET", f"/api/projects/{self.project_id}/build-context")
        agent_state = build.get("agent_state") if isinstance(build, dict) else None
        if not isinstance(agent_state, dict):
            return {"cleanup_blocker": "Build Context agent state is invalid"}
        sessions = []
        for field in ("active_sessions", "recent_sessions"):
            values = agent_state.get(field)
            if not isinstance(values, list):
                return {"cleanup_blocker": f"Build Context {field} is invalid"}
            sessions.extend(values)
        if not isinstance(sessions, list):
            return {"cleanup_blocker": "Build Context sessions are invalid"}
        seen_sessions: set[str] = set()
        completed_candidates: list[str] = []
        for summary in sessions:
            if not isinstance(summary, dict) or not isinstance(summary.get("id"), str):
                return {"cleanup_blocker": "Build Session identity is ambiguous"}
            session_id = summary["id"]
            if session_id in seen_sessions:
                continue
            seen_sessions.add(session_id)
            detail = self._ok("GET", f"/api/build-sessions/{session_id}")
            batches = detail.get("modeling_batches", []) if isinstance(detail, dict) else []
            if any(
                isinstance(batch, dict)
                and isinstance(batch.get("latest_attempt"), dict)
                and batch["latest_attempt"].get("attempt_status") in {"applying", "recovering"}
                for batch in batches
            ):
                return {"cleanup_blocker": "an owned Modeling Batch Attempt is in flight"}
            session = detail.get("session", {}) if isinstance(detail, dict) else {}
            if not isinstance(session, dict) or session.get("project_id") != self.project_id:
                return {"cleanup_blocker": "Build Session ownership drifted"}
            involved = detail.get("involved_ontology_ids", []) if isinstance(detail, dict) else []
            if not isinstance(involved, list):
                return {"cleanup_blocker": "Build Session Ontology ownership is invalid"}
            if involved and set(involved) != {self.ontology_id}:
                return {"cleanup_blocker": "Build Session Ontology ownership drifted"}
            state = session.get("status") if isinstance(session, dict) else None
            if state not in {"completed", "cancelled"}:
                if not allow_cancel:
                    return {"success_blocker": "Build Session is not completed"}
                revision = session.get("revision") if isinstance(session, dict) else None
                if not isinstance(revision, int):
                    return {"cleanup_blocker": "Build Session revision is unavailable"}
                self._ok(
                    "POST",
                    f"/api/build-sessions/{session_id}:cancel",
                    {"client_request_id": f"r2-3-002-cleanup-{self.run_id}-{session_id}", "expected_revision": revision, "reason": "R2.3-002 terminal cleanup"},
                )
                detail = self._ok("GET", f"/api/build-sessions/{session_id}")
                session = detail.get("session", {}) if isinstance(detail, dict) else {}
                state = session.get("status") if isinstance(session, dict) else None
                if state not in {"completed", "cancelled"}:
                    return {"cleanup_blocker": "Build Session did not reach a terminal state"}
            leases = detail.get("leases", []) if isinstance(detail, dict) else []
            if not isinstance(leases, list):
                return {"cleanup_blocker": "Build Session Lease state is invalid"}
            if any(not isinstance(lease, dict) or lease.get("state") != "released" for lease in leases):
                return {
                    "success_blocker" if require_completed else "cleanup_blocker": "an owned Ontology Lease is not released"
                }
            if involved == [self.ontology_id] or set(involved) == {self.ontology_id}:
                if state == "completed":
                    completed_candidates.append(session_id)
                elif require_completed:
                    return {"success_blocker": "Build Session is cancelled or not completed"}
        if require_completed:
            if len(completed_candidates) != 1:
                return {"success_blocker": "successful producer requires exactly one completed owned Build Session"}
            self.completed_session_id = completed_candidates[0]
            return {"sessions_terminal": True, "completed_session_id": self.completed_session_id}
        return {"sessions_terminal": True}

    def _has_writes(self) -> bool:
        if not self.ontology_id:
            return False
        batches = self._ok("GET", f"/api/ontologies/{self.ontology_id}/modeling-batches")
        items = batches.get("items", batches.get("batches", [])) if isinstance(batches, dict) else []
        return isinstance(items, list) and bool(items)

    def _retain_nonempty(self) -> bool:
        # Scope receives its policy from the TeamRun when constructed by the delivery controller.
        return bool(getattr(self, "retain_nonempty", False))

    def _producer_completed(self) -> bool:
        return bool(self.terminal_results) and all(
            item.get("status") == "completed" for item in self.terminal_results.values()
        )

    def recheck_retained_producer(self) -> dict[str, Any]:
        if self.scope_disposition != "retained-pending-acceptance":
            raise PlatformScopeError("scope is not a retained producer")
        if not self.admin_key:
            self.admin_key, self.admin_key_id = self.bootstrap_admin()
        try:
            context = self._modeling_context()
            terminal = self._terminal_state(allow_cancel=False, require_completed=True)
            if terminal.get("cleanup_blocker") or terminal.get("success_blocker"):
                raise PlatformScopeError(terminal.get("cleanup_blocker") or terminal["success_blocker"])
            if terminal.get("completed_session_id") != self.completed_session_id:
                raise PlatformScopeError("retained Build Session identity drifted")
            version = self._workspace_version(context)
            if version != self.final_workspace_version:
                raise PlatformScopeError("retained workspace version drifted")
            return {
                "project_id": self.project_id,
                "ontology_id": self.ontology_id,
                "workspace_version": version,
                "scope_disposition": self.scope_disposition,
            }
        finally:
            if self.admin_key_id:
                self.revoke_admin(self.admin_key_id)
            self.admin_key = self.admin_key_id = None
