"""Exact ownership lifecycle for the R2.3-001 empty platform scope."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


class PlatformScopeError(RuntimeError):
    pass


class PlatformScopeMissingError(PlatformScopeError):
    """R3.0-015 S2: a recovery-binding resource is absent (scope_missing).

    Recovery never creates a blank replacement scope and pretends it resumed;
    the typed reason travels up to the resume entry unchanged.
    """


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
    existing_handoff: dict[str, Any] | None = None
    existing_strict: bool = False
    terminal_results: dict[str, dict[str, Any]] | None = None
    final_workspace_context: dict[str, Any] | None = None
    final_workspace_version: str | None = None
    completed_session_id: str | None = None
    scope_disposition: str | None = None
    # R3.0-006 M3: the full planned Ontology set once a topology decision's
    # ``ontology_plan`` has been applied (empty for the single-Ontology path).
    ontology_ids: list[str] = field(default_factory=list)
    completed_session_ids: dict[str, str] = field(default_factory=dict)
    # R3.0-015 S1 (design §3.3.5): set by the Runner cleanup path when at
    # least one fully published, digest-verifying checkpoint package references
    # the run.  An otherwise-empty owned scope is then retained (keys still
    # revoked) instead of taking the first-stage delete path.
    checkpoint_retention: dict[str, Any] | None = None
    # The host-selected operator owns run keys; scenario-map owners are unrelated.
    key_user_id: str | None = None

    def __post_init__(self) -> None:
        if self.request is None:
            self.request = lambda method, path, body, key: _http(
                self.base_url, method, path, body, key
            )

    def prepare(self, scope: dict[str, str]) -> None:
        mode = scope.get("mode")
        if mode not in {"create", "existing", "checkpoint"}:
            raise PlatformScopeError("scope.mode must be create, existing or checkpoint")
        self.mode = mode
        self.admin_key, self.admin_key_id = self.bootstrap_admin()
        try:
            principal = self._ok("GET", "/api/auth/me")
            self.key_user_id = principal.get("user_id")
            if not isinstance(self.key_user_id, str) or not self.key_user_id:
                raise PlatformScopeError("Team operator admin key has no enabled user binding")
            if mode == "create":
                self._create()
            elif mode == "checkpoint":
                self._checkpoint_binding(scope)
            else:
                self._existing(scope)
            if mode == "create" or scope.get("fork_created_by_run") == self.run_id:
                self._ok(
                    "POST", f"/api/projects/{self.project_id}/members",
                    {"user_id": self.key_user_id}, statuses={201},
                )
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
        self.existing_strict = isinstance(scope.get("handoff_path"), str)
        self.existing_context_before = self._existing_context(strict=self.existing_strict)

    def _checkpoint_binding(self, scope: dict[str, str]) -> None:
        """R3.0-015 S2 (design §5.2): rebind the exact recorded resources.

        The explicit checkpoint-binding entry loads the verified
        ``ontology_ids`` into the existing multi-Ontology path.  Every ID is
        bound by exact identity — the name-based ``apply_ontology_plan``
        creation path is never used by recovery.  A missing resource raises
        :class:`PlatformScopeMissingError` (``scope_missing``); no blank scope
        is created and faked as a resume.
        """

        project, ontology_ids = scope.get("project_id"), scope.get("ontology_ids")
        if not isinstance(project, str) or not project:
            raise PlatformScopeError("checkpoint scope requires a Project ID")
        if (
            not isinstance(ontology_ids, list)
            or not ontology_ids
            or not all(isinstance(item, str) and item for item in ontology_ids)
        ):
            raise PlatformScopeError(
                "checkpoint scope requires the verified ontology_ids list"
            )
        listed = self._ok("GET", f"/api/projects/{project}/ontologies")
        if not isinstance(listed, list):
            raise PlatformScopeError("Project Ontology listing is invalid")
        available = {
            item.get("id") for item in listed if isinstance(item, dict)
        }
        missing = [ontology_id for ontology_id in ontology_ids if ontology_id not in available]
        if missing:
            raise PlatformScopeMissingError(
                "checkpoint scope resources are missing: " + ", ".join(missing)
            )
        self.project_id, self.ontology_ids = project, list(ontology_ids)
        self.ontology_id, self.owned = ontology_ids[0], False
        self.existing_context_before = {
            ontology_id: self._single_ontology_context(ontology_id)
            for ontology_id in self.ontology_ids
        }

    def apply_ontology_plan(self, plan: Any) -> list[str]:
        """R3.0-006 M3: create every planned Ontology (idempotent, single writer).

        The first plan entry is the scope-precreated Ontology; the remaining
        N-1 are created by the Runner here.  Re-applying the same plan reuses
        already-created same-name Ontologies instead of duplicating them.
        """

        if self.ontology_ids:
            return list(self.ontology_ids)
        if (
            not isinstance(plan, list)
            or len(plan) < 2
            or not all(
                isinstance(entry, dict)
                and set(entry) == {"name", "slice_ids"}
                and isinstance(entry.get("name"), str)
                and bool(entry["name"].strip())
                and isinstance(entry.get("slice_ids"), list)
                and bool(entry["slice_ids"])
                and all(isinstance(item, str) and item for item in entry["slice_ids"])
                and len(set(entry["slice_ids"])) == len(entry["slice_ids"])
                for entry in plan
            )
        ):
            raise PlatformScopeError("ontology plan is structurally invalid")
        names = [entry["name"] for entry in plan]
        if len(set(names)) != len(names):
            raise PlatformScopeError("ontology plan names are not unique")
        if not self.project_id or not self.ontology_id:
            raise PlatformScopeError("scope identity is unavailable")
        listed = self._ok("GET", f"/api/projects/{self.project_id}/ontologies")
        if not isinstance(listed, list):
            raise PlatformScopeError("Project Ontology listing is invalid")
        existing = {
            item.get("name"): item.get("id")
            for item in listed
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("id"), str)
        }
        ontology_ids = [self.ontology_id]
        for entry in plan[1:]:
            name = entry["name"]
            ontology_id = existing.get(name)
            if ontology_id is None:
                ontology = self._ok(
                    "POST",
                    f"/api/projects/{self.project_id}/ontologies",
                    {
                        "name": name,
                        "description": "R3.0-006 ontology plan entry",
                        "external_mappings": {},
                    },
                    statuses={201},
                )
                ontology_id = (
                    ontology.get("id") if isinstance(ontology.get("id"), str) else None
                )
            if not ontology_id:
                raise PlatformScopeError("planned Ontology has no identity")
            ontology_ids.append(ontology_id)
        self.ontology_ids = ontology_ids
        return list(ontology_ids)

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

    def _single_ontology_context(self, ontology_id: str) -> dict[str, Any]:
        """Read one bound Ontology's clearance state (shared existing/S2 path)."""

        if not self.project_id:
            raise PlatformScopeError("scope identity is unavailable")
        context = self._ok("GET", f"/api/ontologies/{ontology_id}/workspace-context")
        if not isinstance(context, dict) or context.get("state") != "ready":
            raise PlatformScopeError("ontology workspace is not ready")
        batches = self._ok("GET", f"/api/ontologies/{ontology_id}/modeling-batches")
        items = batches.get("items", batches.get("batches", [])) if isinstance(batches, dict) else batches
        if not isinstance(items, list):
            raise PlatformScopeError("Modeling Batch history is invalid")
        build = self._ok("GET", f"/api/projects/{self.project_id}/build-context")
        agent_state = build.get("agent_state") if isinstance(build, dict) else None
        if not isinstance(agent_state, dict):
            raise PlatformScopeError("Build Context agent state is invalid")
        active = agent_state.get("active_sessions", [])
        recent = agent_state.get("recent_sessions", [])
        if not isinstance(active, list) or not isinstance(recent, list):
            raise PlatformScopeError("Build Context session state is invalid")
        leases = agent_state.get("active_leases", agent_state.get("leases", []))
        attempts = agent_state.get("in_flight_attempts", agent_state.get("inflight_attempts", []))
        if not isinstance(leases, list) or not isinstance(attempts, list):
            raise PlatformScopeError("Build Context Lease/Attempt state is invalid")
        if active or leases or attempts:
            raise PlatformScopeError("existing scope has active Session, Lease, or Attempt")
        fence = agent_state.get("fence")
        if isinstance(fence, dict) and fence.get("active") is True:
            raise PlatformScopeError("existing scope has an active fence")
        for summary in recent:
            if not isinstance(summary, dict):
                continue
            session_id = summary.get("id", summary.get("session_id"))
            if not isinstance(session_id, str) or not session_id:
                continue
            detail = self._ok("GET", f"/api/build-sessions/{session_id}")
            if not isinstance(detail, dict):
                raise PlatformScopeError("Build Session detail is invalid")
            session = detail.get("session", detail)
            if isinstance(session, dict) and session.get("project_id") not in {None, self.project_id}:
                raise PlatformScopeError("Build Session Project ownership drifted")
            batches_for_session = detail.get("modeling_batches", [])
            if any(
                isinstance(batch, dict)
                and isinstance(batch.get("latest_attempt"), dict)
                and batch["latest_attempt"].get("attempt_status") in {"applying", "recovering"}
                for batch in batches_for_session if isinstance(batches_for_session, list)
            ):
                raise PlatformScopeError("existing scope has an in-flight Attempt")
            leases_for_session = detail.get("leases", [])
            if isinstance(leases_for_session, list) and any(
                isinstance(lease, dict)
                and lease.get("state") not in {"released", "expired", "cancelled"}
                for lease in leases_for_session
            ):
                raise PlatformScopeError("existing scope has an active Lease")
            session_status = str(session.get("status", "")).lower() if isinstance(session, dict) else ""
            if session_status in {"active", "running", "in_progress", "applying", "recovering", "leased"}:
                raise PlatformScopeError("existing scope has an in-flight Build Session")
        workspace = context.get("workspace") if isinstance(context.get("workspace"), dict) else {}
        version = workspace.get("workspace_version") or context.get("workspace_version") or context.get("version")
        if version is None and isinstance(build, dict):
            platform_state = build.get("platform_state")
            ontologies = platform_state.get("ontologies", []) if isinstance(platform_state, dict) else []
            for ontology in ontologies if isinstance(ontologies, list) else []:
                if not isinstance(ontology, dict) or ontology.get("id") != ontology_id:
                    continue
                ontology_workspace = ontology.get("workspace")
                if isinstance(ontology_workspace, dict):
                    version = ontology_workspace.get("workspace_version")
                break
        graph_set = context.get("default_graph_set", context.get("graph_set"))
        graph_set_id = context.get("default_graph_set_id")
        if graph_set_id is None and isinstance(graph_set, dict):
            graph_set_id = graph_set.get("id")
        return {
            "workspace_state": context["state"],
            **({"workspace_version": version} if isinstance(version, str) and version else {}),
            **({"graph_set_id": graph_set_id} if graph_set_id is not None else {}),
            "modeling_batch_count": len(items),
            "recent_session_count": len(recent),
            "active_session_count": len(active),
            "active_lease_count": len(leases),
            "in_flight_attempt_count": len(attempts),
        }

    def _existing_context(self, *, strict: bool | None = None) -> dict[str, Any]:
        """Read a retained scope while allowing completed history."""

        if not self.ontology_id or not self.project_id:
            raise PlatformScopeError("existing scope identity is unavailable")
        result = self._single_ontology_context(self.ontology_id)
        strict = self.existing_strict if strict is None else strict
        if strict and not result.get("workspace_version"):
            raise PlatformScopeError("workspace context has no version")
        if strict and result.get("graph_set_id") is None:
            raise PlatformScopeError("workspace context has no default Graph Set")
        return result

    def _create_protocol_key(self) -> None:
        created = self._ok(
            "POST",
            "/api/api-keys",
            {
                "name": f"r2-3-001-{self.run_id}",
                "project_id": self.project_id,
                "scopes": ["model"],
                "user_id": self.key_user_id,
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
        if self.mode == "checkpoint":
            # R3.0-015 S2 (design §5.2): a recovery run owns only this round's
            # threads, credentials and Session/Lease.  The inherited scope —
            # empty or not — is never deleted by the recovery cleanup, and no
            # fence is force-cleared; only the newly issued keys are revoked.
            self.scope_disposition = "inherited-retained"
            evidence["scope_disposition"] = self.scope_disposition
            evidence["ontology_ids"] = list(self.ontology_ids)
            evidence["existing_context_before"] = self.existing_context_before
            if self.protocol_key_id and self.admin_key:
                evidence["protocol_key_revoked"] = self._revoke_project_key(evidence)
            self._revoke_keys(evidence)
            return evidence
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
                evidence["existing_context_after"] = self._existing_context(strict=self.existing_strict)
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
                    if len(self.ontology_ids) > 1:
                        # R3.0-006 M3: the retained evidence covers every
                        # planned Ontology (final context and workspace
                        # version per Ontology, one completed Build Session
                        # per Ontology).
                        contexts = {
                            ontology_id: self._modeling_context(ontology_id)
                            for ontology_id in self.ontology_ids
                        }
                        versions = {
                            ontology_id: self._workspace_version(context)
                            for ontology_id, context in contexts.items()
                        }
                        self.final_workspace_context = contexts[self.ontology_id]
                        self.final_workspace_version = versions[self.ontology_id]
                        self.scope_disposition = "retained-pending-acceptance"
                        evidence["scope_disposition"] = self.scope_disposition
                        evidence["ontology_ids"] = list(self.ontology_ids)
                        evidence["workspace_versions"] = versions
                        evidence["completed_session_ids"] = dict(
                            self.completed_session_ids
                        )
                    else:
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
                    if self.checkpoint_retention:
                        # R3.0-015 S1: this empty owned scope is referenced by
                        # published valid checkpoint packages, so it stays for
                        # recovery; every credential is still revoked.
                        self.scope_disposition = "retained-checkpoint-reference"
                        evidence["scope_disposition"] = self.scope_disposition
                        evidence["checkpoint_retention"] = dict(self.checkpoint_retention)
                        self._revoke_keys(evidence)
                        return evidence
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
                **(
                    {"ontology_ids": list(self.ontology_ids)}
                    if len(self.ontology_ids) > 1
                    else {}
                ),
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
        try:
            status, _ = self.request(
                "GET", f"/api/projects/{self.project_id}", None, self.admin_key
            )
        except Exception:
            status = 0
        checks["project_absent"] = status == 404
        ontology_ids = self.ontology_ids or (
            [self.ontology_id] if self.ontology_id else []
        )
        ontology_absent: dict[str, bool] = {}
        for ontology_id in ontology_ids:
            try:
                status, _ = self.request(
                    "GET", f"/api/ontologies/{ontology_id}", None, self.admin_key
                )
            except Exception:
                status = 0
            ontology_absent[ontology_id] = status == 404
        if ontology_absent:
            checks["ontology_absent"] = all(ontology_absent.values())
            if len(ontology_absent) > 1:
                checks["ontology_absent_by_id"] = ontology_absent
        else:
            checks["ontology_absent"] = None
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

    def _modeling_context(self, ontology_id: str | None = None) -> dict[str, Any]:
        ontology_id = ontology_id or self.ontology_id
        if not ontology_id:
            raise PlatformScopeError("ontology unavailable")
        context = self._ok("GET", f"/api/ontologies/{ontology_id}/modeling-context")
        if not isinstance(context, dict):
            raise PlatformScopeError("modeling context is invalid")
        project = context.get("project", {})
        ontology = context.get("ontology", {})
        if project.get("id") != self.project_id or ontology.get("id") != ontology_id:
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
        values: dict[str, str] = {
            "project_id": self.project_id,
            "ontology_id": self.ontology_id,
            "workspace_version": workspace_version,
        }
        # R3.0-006 M3: a multi-Ontology plan exposes the full planned set;
        # Protocol treats get_project_build_context as authoritative.
        if len(self.ontology_ids) > 1:
            values["ontology_ids"] = ",".join(self.ontology_ids)
        return values

    @staticmethod
    def _workspace_version(context: dict[str, Any]) -> str | None:
        workspace = context.get("workspace")
        value = workspace.get("workspace_version") if isinstance(workspace, dict) else None
        return value if isinstance(value, str) and value else None

    def _terminal_state(self, *, allow_cancel: bool, require_completed: bool) -> dict[str, Any]:
        """Cancel safe failed Sessions before any scope disposition is considered."""
        if not self.owned or not self.project_id or not self.admin_key:
            return {}
        # R3.0-006 M3: a multi-Ontology plan uses aggregate ownership — each
        # Session involves exactly one planned Ontology, the cross-Session
        # union is the whole plan, and completion means one completed owned
        # Build Session per planned Ontology.
        multi = len(self.ontology_ids) > 1
        plan_ids = set(self.ontology_ids) if multi else set()
        build = self._ok("GET", f"/api/projects/{self.project_id}/build-context")
        agent_state = build.get("agent_state") if isinstance(build, dict) else None
        if not isinstance(agent_state, dict):
            return {"cleanup_blocker": "Build Context agent state is invalid"}
        sessions = []
        for agent_field in ("active_sessions", "recent_sessions"):
            values = agent_state.get(agent_field)
            if not isinstance(values, list):
                return {"cleanup_blocker": f"Build Context {agent_field} is invalid"}
            sessions.extend(values)
        if not isinstance(sessions, list):
            return {"cleanup_blocker": "Build Context sessions are invalid"}
        seen_sessions: set[str] = set()
        completed_candidates: list[str] = []
        completed_by_ontology: dict[str, str] = {}
        involved_union: set[str] = set()
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
            if multi:
                if (
                    not involved
                    or len(set(involved)) != 1
                    or set(involved) - plan_ids
                ):
                    return {"cleanup_blocker": "Build Session Ontology ownership drifted"}
                involved_union.update(involved)
            elif involved and set(involved) != {self.ontology_id}:
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
            if multi:
                if state == "completed":
                    ontology_id = involved[0]
                    if ontology_id in completed_by_ontology:
                        return {
                            "success_blocker": "multiple completed owned Build Sessions for one planned Ontology"
                        }
                    completed_by_ontology[ontology_id] = session_id
                elif require_completed:
                    return {"success_blocker": "Build Session is cancelled or not completed"}
            elif involved == [self.ontology_id] or set(involved) == {self.ontology_id}:
                if state == "completed":
                    completed_candidates.append(session_id)
                elif require_completed:
                    return {"success_blocker": "Build Session is cancelled or not completed"}
        if multi:
            if involved_union != plan_ids:
                return {"cleanup_blocker": "Build Session Ontology coverage drifted"}
            if require_completed:
                if set(completed_by_ontology) != plan_ids:
                    return {
                        "success_blocker": "every planned Ontology requires exactly one completed owned Build Session"
                    }
                self.completed_session_ids = dict(completed_by_ontology)
                return {
                    "sessions_terminal": True,
                    "completed_session_ids": dict(self.completed_session_ids),
                }
            return {"sessions_terminal": True}
        if require_completed:
            if len(completed_candidates) != 1:
                return {"success_blocker": "successful producer requires exactly one completed owned Build Session"}
            self.completed_session_id = completed_candidates[0]
            return {"sessions_terminal": True, "completed_session_id": self.completed_session_id}
        return {"sessions_terminal": True}

    def _has_writes(self) -> bool:
        ontology_ids = self.ontology_ids or (
            [self.ontology_id] if self.ontology_id else []
        )
        for ontology_id in ontology_ids:
            if not ontology_id:
                continue
            batches = self._ok("GET", f"/api/ontologies/{ontology_id}/modeling-batches")
            items = batches.get("items", batches.get("batches", [])) if isinstance(batches, dict) else []
            if isinstance(items, list) and items:
                return True
        return False

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
