"""Team operator membership and keys through real authentication and SQL APIs.

Ontology lifecycle replies reuse the bounded stand-in; identity/access replies
traverse the real application, without launching a semantic modeling run.
"""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.repositories import models as m
from app.repositories import postgres
from modeling_team.__main__ import _bootstrap_helpers
from modeling_team.platform_scope import PlatformScope, PlatformScopeError
from modeling_team.modeling_readonly import ModelingReadKeyLifecycle

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mode", ["create", "fork", "existing", "checkpoint"])
def test_operator_binding_membership_and_key_scope(r008_client, monkeypatch, mode):
    client, factory = r008_client["client"], r008_client["factory"]
    with factory() as db:
        operator = db.get(m.ApiKeyModel, r008_client["ids"]["org_key_id"])
        operator.name = "operator-admin"
        user_id = operator.user_id
        db.commit()
        users_before = db.scalar(select(func.count(m.UserModel.id)))
        roles_before = db.scalar(select(func.count(m.SemanticAccessRoleModel.id)))
    monkeypatch.setattr(postgres, "create_session_factory", lambda _settings: factory)
    create, revoke = _bootstrap_helpers(ROOT)
    calls = []
    project = r008_client["ids"]["p2"]
    if mode == "fork":
        response = client.post(
            "/api/projects",
            json={"name": "fork-target"},
            headers={"Authorization": "Bearer " + r008_client["org_key"]},
        )
        assert response.status_code == 201
        project = response.json()["id"]

    def request(method, path, body, key):
        calls.append((method, path, body))
        if path.endswith("/ontologies"):
            return (201, {"id": "ontology"}) if method == "POST" else (200, [{"id": "ontology"}])
        if path.endswith("workspace-context"):
            return 200, {"state": "ready", "ontology_id": "ontology", "model_revision": 0}
        if path.endswith("modeling-batches"):
            return 200, {"items": []}
        if path.endswith("build-context"):
            return 200, {"agent_state": {"active_sessions": [], "recent_sessions": []}}
        response = client.request(
            method, path, json=body, headers={"Authorization": "Bearer " + key}
        )
        return response.status_code, response.json() if response.content else None

    scope = PlatformScope("http://test", "identity-test", create, revoke, request)
    incoming = (
        {"mode": "create"}
        if mode == "create"
        else {
            "mode": "checkpoint" if mode in ("fork", "checkpoint") else "existing",
            "project_id": project,
            "ontology_id": "ontology",
            "ontology_ids": ["ontology"],
        }
    )
    if mode == "fork":
        incoming["fork_created_by_run"] = "identity-test"
    if mode in ("existing", "checkpoint"):
        with pytest.raises(PlatformScopeError, match=r"failed \(422\)"):
            scope.prepare(incoming)
        assert not any(method == "POST" and path.endswith("/members") for method, path, _ in calls)
        with factory() as db:
            assert db.get(m.ProjectUserMembershipModel, (project, user_id)) is None
        return
    try:
        scope.prepare(incoming)
        lifecycle = ModelingReadKeyLifecycle(scope)
        record = lifecycle.create(
            project_id=scope.project_id, ontology_id="ontology", run_id="identity-test"
        )
        read_key = lifecycle.plaintext_for(record.key_id)
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer " + read_key})
        assert response.status_code == 200
        assert response.json()["user_id"] == user_id
        assert response.json()["project_id"] == scope.project_id
        assert response.json()["scopes"] == ["read"]
        with factory() as db:
            protocol = db.get(m.ApiKeyModel, scope.protocol_key_id)
            assert protocol.user_id == user_id and protocol.project_id == scope.project_id
            assert protocol.scopes == ["model"]
            assert db.get(m.ProjectUserMembershipModel, (scope.project_id, user_id)) is not None
            assert db.scalar(select(func.count(m.UserModel.id))) == users_before
            assert db.scalar(select(func.count(m.SemanticAccessRoleModel.id))) == roles_before
        lifecycle.revoke(record.key_id)
    finally:
        # Cleanup only issued test keys; project fixtures are disposed with SQLite.
        scope.mode = "checkpoint"
        scope.cleanup()
