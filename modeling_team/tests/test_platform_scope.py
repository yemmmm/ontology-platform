from __future__ import annotations

import unittest

from modeling_team.platform_scope import PlatformScope


class ScopeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, path, body, key):
        self.calls.append((method, path))
        if method == "POST" and path == "/api/projects":
            return 201, {"id": "project-1"}
        if method == "POST" and path.endswith("/ontologies"):
            return 201, {"id": "ontology-1"}
        if path.endswith("workspace-context"):
            return 200, {"state": "ready"}
        if path.endswith("modeling-batches"):
            return 200, {"items": []}
        if path.endswith("build-context"):
            return 200, {"agent_state": {"active_sessions": [], "recent_sessions": []}}
        if method == "GET" and path.endswith("/ontologies"):
            return 200, [{"id": "ontology-1"}]
        if path == "/api/api-keys":
            return 201, {"id": "model-key", "plaintext_key": "secret"}
        if path.endswith(":revoke"):
            return 200, {"revoked_at": "now"}
        if method == "DELETE":
            return 204, None
        return 200, {"id": "project-1"}


class FailedSessionClient(ScopeClient):
    def __init__(self, attempt_status: str | None = None) -> None:
        super().__init__()
        self.cleanup_sessions = False
        self.attempt_status = attempt_status
        self.cancelled = False

    def __call__(self, method, path, body, key):
        self.calls.append((method, path))
        if self.cleanup_sessions and path.endswith("build-context"):
            return 200, {"agent_state": {"active_sessions": [{"id": "session-1"}], "recent_sessions": []}}
        if path == "/api/build-sessions/session-1":
            batches = []
            if self.attempt_status:
                batches = [{"latest_attempt": {"attempt_status": self.attempt_status}}]
            return 200, {
                "session": {"id": "session-1", "project_id": "project-1", "status": "cancelled" if self.cancelled else "active", "revision": 1},
                "modeling_batches": batches,
            }
        if path == "/api/build-sessions/session-1:cancel":
            self.cancelled = True
            return 200, {"session": {"status": "cancelled"}}
        return super().__call__(method, path, body, key)


class RetainedProducerClient(ScopeClient):
    def __init__(self) -> None:
        super().__init__()
        self.written = False
        self.session_visible = True
        self.session_ids = ["session-1"]
        self.session_status = "completed"
        self.foreign = False

    def __call__(self, method, path, body, key):
        if self.written and path.endswith("build-context"):
            sessions = [{"id": session_id} for session_id in self.session_ids] if self.session_visible else []
            return 200, {"agent_state": {"active_sessions": [], "recent_sessions": sessions}}
        if path == "/api/build-sessions/session-1" and self.written:
            return 200, {
                "session": {"id": "session-1", "project_id": "project-1", "status": self.session_status, "revision": 1},
                "involved_ontology_ids": ["foreign-ontology"] if self.foreign else ["ontology-1"],
                "modeling_batches": [],
                "leases": [{"state": "released"}],
            }
        if self.written and path.endswith("modeling-batches"):
            return 200, {"batches": [{"batch_id": "batch-1"}]}
        if path.endswith("modeling-context"):
            return 200, {
                "project": {"id": "project-1"},
                "ontology": {"id": "ontology-1"},
                "workspace": {"state": "ready", "workspace_version": "version-1"},
            }
        return super().__call__(method, path, body, key)


class TwoStageClient(ScopeClient):
    def __init__(self) -> None:
        super().__init__()
        self.deleted = False
        self.delete_key = None

    def __call__(self, method, path, body, key):
        self.calls.append((method, path))
        if method == "DELETE":
            self.deleted = True
            self.delete_key = key
            return 204, None
        if method == "GET" and path in {"/api/projects/project-1", "/api/ontologies/ontology-1"} and self.deleted:
            return 404, None
        if method == "GET" and path == "/api/api-keys/admin-id":
            return 200, {"id": "admin-id", "project_id": None, "revoked_at": None}
        if method == "GET" and path == "/api/api-keys":
            return 200, []
        if method == "POST" and path.endswith(":revoke"):
            return 200, {"id": path.split("/")[-1].removesuffix(":revoke"), "revoked_at": "now", "project_id": None}
        return super().__call__(method, path, body, key)


class DeleteRaisesClient(TwoStageClient):
    def __call__(self, method, path, body, key):
        if method == "DELETE":
            self.calls.append((method, path))
            raise RuntimeError("delete transport failed")
        return super().__call__(method, path, body, key)


class PlatformScopeTests(unittest.TestCase):
    def test_create_owns_and_deletes_only_its_empty_scope(self) -> None:
        client = ScopeClient()
        scope = PlatformScope(
            "http://example",
            "unit-run-123",
            lambda: ("admin", "admin-id"),
            lambda _: True,
            client,
        )
        scope.prepare({"mode": "create"})
        cleanup = scope.cleanup()
        self.assertTrue(cleanup["owned_project_deleted"])
        self.assertIn(("DELETE", "/api/projects/project-1"), client.calls)

    def test_owned_delete_freezes_two_stage_key_evidence_and_revokes_admin_after_delete(self) -> None:
        client = TwoStageClient()
        scope = PlatformScope(
            "http://example",
            "unit-run-123",
            lambda: ("admin", "admin-id"),
            lambda _: True,
            client,
        )
        scope.prepare({"mode": "create"})
        cleanup = scope.cleanup()
        first = cleanup["first_stage"]
        self.assertTrue(first["ready_for_delete"])
        self.assertEqual(first["bootstrap_admin"]["id"], "admin-id")
        self.assertTrue(first["bootstrap_admin"]["active"])
        self.assertTrue(first["bootstrap_admin"]["excluded_from_non_active_assertion"])
        self.assertTrue(first["project_scoped_keys"][0]["non_active"])
        self.assertEqual(cleanup["post_delete"]["active_project_residual_count"], 0)
        self.assertTrue(cleanup["post_delete"]["project_absent"])
        self.assertTrue(cleanup["post_delete"]["ontology_absent"])
        self.assertTrue(cleanup["second_stage"]["retained_org_admin_audit_row"]["retained"])
        self.assertTrue(cleanup["aggregate_keys_non_active"])
        delete_index = client.calls.index(("DELETE", "/api/projects/project-1"))
        revoke_indices = [index for index, call in enumerate(client.calls) if call == ("POST", "/api/api-keys/admin-id:revoke")]
        self.assertTrue(revoke_indices and revoke_indices[-1] > delete_index)
        self.assertEqual(client.delete_key, "admin")

    def test_delete_exception_still_revokes_org_admin_in_finally(self) -> None:
        client = DeleteRaisesClient()
        scope = PlatformScope(
            "http://example",
            "unit-run-123",
            lambda: ("admin", "admin-id"),
            lambda _: True,
            client,
        )
        scope.prepare({"mode": "create"})
        cleanup = scope.cleanup()
        self.assertEqual(cleanup["scope_disposition"], "delete-failed")
        self.assertTrue(cleanup["admin_key_revoked"])
        self.assertTrue(cleanup["second_stage"]["retained_org_admin_audit_row"]["retained"])

    def test_existing_never_deletes_fixture(self) -> None:
        client = ScopeClient()
        scope = PlatformScope(
            "http://example",
            "unit-run-123",
            lambda: ("admin", "admin-id"),
            lambda _: True,
            client,
        )
        scope.prepare(
            {"mode": "existing", "project_id": "project-1", "ontology_id": "ontology-1"}
        )
        cleanup = scope.cleanup()
        self.assertNotIn(("DELETE", "/api/projects/project-1"), client.calls)
        self.assertEqual(
            cleanup["existing_context_before"], cleanup["existing_context_after"]
        )

    def test_failed_empty_session_is_cancelled_before_owned_scope_deletion(self) -> None:
        client = FailedSessionClient()
        scope = PlatformScope(
            "http://example", "unit-run-123", lambda: ("admin", "admin-id"), lambda _: True, client
        )
        scope.prepare({"mode": "create"})
        client.cleanup_sessions = True
        cleanup = scope.cleanup()
        self.assertTrue(cleanup["sessions_terminal"])
        self.assertTrue(cleanup["owned_project_deleted"])
        self.assertIn(("POST", "/api/build-sessions/session-1:cancel"), client.calls)

    def test_applying_attempt_blocks_session_and_scope_cleanup(self) -> None:
        client = FailedSessionClient("applying")
        scope = PlatformScope(
            "http://example", "unit-run-123", lambda: ("admin", "admin-id"), lambda _: True, client
        )
        scope.prepare({"mode": "create"})
        client.cleanup_sessions = True
        cleanup = scope.cleanup()
        self.assertIn("in flight", cleanup["cleanup_blocker"])
        self.assertNotIn(("DELETE", "/api/projects/project-1"), client.calls)
        self.assertNotIn(("POST", "/api/build-sessions/session-1:cancel"), client.calls)

    def test_retained_producer_uses_actual_modeling_context_version(self) -> None:
        client = RetainedProducerClient()
        scope = PlatformScope(
            "http://example", "unit-run-123", lambda: ("admin", "admin-id"), lambda _: True, client
        )
        scope.retain_nonempty = True
        scope.terminal_results = {
            "coordinator": {"status": "completed"},
            "modeling": {"status": "completed"},
            "protocol": {"status": "completed"},
        }
        scope.prepare({"mode": "create"})
        client.written = True
        cleanup = scope.cleanup()
        self.assertEqual(cleanup["scope_disposition"], "retained-pending-acceptance")
        self.assertEqual(cleanup["workspace_version"], "version-1")
        self.assertEqual(cleanup["completed_session_id"], "session-1")
        self.assertEqual(scope.recheck_retained_producer()["workspace_version"], "version-1")

    def test_protocol_context_contains_only_mechanical_scope_identifiers(self) -> None:
        client = RetainedProducerClient()
        scope = PlatformScope(
            "http://example", "unit-run-123", lambda: ("admin", "admin-id"), lambda _: True, client
        )
        scope.prepare({"mode": "create"})
        self.assertEqual(
            scope.read_protocol_context(),
            {"project_id": "project-1", "ontology_id": "ontology-1", "workspace_version": "version-1"},
        )

    def test_successful_retention_rejects_zero_or_cancelled_session(self) -> None:
        for mode in ("zero", "cancelled", "active", "multiple", "foreign"):
            with self.subTest(mode=mode):
                client = RetainedProducerClient()
                scope = PlatformScope(
                    "http://example", "unit-run-123", lambda: ("admin", "admin-id"), lambda _: True, client
                )
                scope.retain_nonempty = True
                scope.terminal_results = {role: {"status": "completed"} for role in ("coordinator", "modeling", "protocol")}
                scope.prepare({"mode": "create"})
                client.written = True
                client.session_visible = mode != "zero"
                client.session_status = "cancelled" if mode == "cancelled" else "active" if mode == "active" else "completed"
                client.session_ids = ["session-1", "session-2"] if mode == "multiple" else ["session-1"]
                client.foreign = mode == "foreign"
                cleanup = scope.cleanup()
                self.assertIn(cleanup["scope_disposition"], {"failed-written-retained", "blocked"})
                self.assertNotIn(("POST", "/api/build-sessions/session-1:cancel"), client.calls)
