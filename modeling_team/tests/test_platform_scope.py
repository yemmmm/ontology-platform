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
            return 200, {"recent_sessions": []}
        if method == "GET" and path.endswith("/ontologies"):
            return 200, [{"id": "ontology-1"}]
        if path == "/api/api-keys":
            return 201, {"id": "model-key", "plaintext_key": "secret"}
        if path.endswith(":revoke"):
            return 200, {"revoked_at": "now"}
        if method == "DELETE":
            return 204, None
        return 200, {"id": "project-1"}


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
