"""R4.0-006 developer boundary tests with real credential resolution and SQL."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.repositories import models as m
from app.security.auth import (
    AuthorizationDependencyError,
    create_api_key,
    principal_from_key,
    resolve_api_key,
)
from app.services.subject_access import replace_roles, business_role_status
from app.services.semantic_context_cursor import ContextCursorMismatch
from test_semantic_context_cursor import _binding, _codec, _fill_payload


def seed(s):
    s.add_all([m.ProjectModel(id=p, name=p, normalized_label=p) for p in ("p", "q")])
    s.add(m.UserModel(id="u", username="u"))
    s.flush()
    s.add(m.ProjectUserMembershipModel(project_id="p", user_id="u"))
    s.add_all(
        [
            m.SemanticAccessRoleModel(id=r, project_id=p, name=r, grants=g)
            for r, p, g in [
                ("r", "p", [" cost ", "cost"]),
                ("same", "p", ["cost", " cost "]),
                ("else", "q", ["else"]),
            ]
        ]
    )
    s.commit()
    return create_api_key(s, name="personal", project_id="p", scopes=["read"], user_id="u")


def test_multiple_keys_share_roles_but_preserve_scope(in_memory_session):
    s = in_memory_session
    _, key1 = seed(s)
    _, key2 = create_api_key(s, name="model", project_id="p", scopes=["model"], user_id="u")
    assert resolve_api_key(s, key1).semantic_grants == set()
    replace_roles(s, "p", "u", ["r", "same", "r"])
    for key in (key1, key2):
        p = resolve_api_key(s, key)
        assert p.user_id == "u"
        assert p.semantic_grants == {" cost ", "cost"}
    assert resolve_api_key(s, key1).effective_scopes == {"read"}
    assert resolve_api_key(s, key2).effective_scopes == {"read", "model"}
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        replace_roles(s, "p", "u", ["else"])
    assert resolve_api_key(s, key1).semantic_grants == {" cost ", "cost"}
    replace_roles(s, "p", "u", [])
    assert resolve_api_key(s, key1).semantic_grants == set()


def test_permission_change_invalidates_cursor_but_equivalent_roles_do_not(in_memory_session):
    s = in_memory_session
    _, token = seed(s)
    replace_roles(s, "p", "u", ["r"])
    binding = _binding(principal=resolve_api_key(s, token))
    codec = _codec()
    cursor = codec.encode(_fill_payload(codec, binding))
    replace_roles(s, "p", "u", ["same"])
    same = replace(binding, principal=resolve_api_key(s, token))
    assert codec.decode(cursor, expected_kind="match", binding=same)
    replace_roles(s, "p", "u", [])
    with pytest.raises(ContextCursorMismatch):
        codec.decode(
            cursor,
            expected_kind="match",
            binding=replace(binding, principal=resolve_api_key(s, token)),
        )


@pytest.mark.parametrize("bad", [{}, ["bad\n"], ["a", 2], "cost", ["x" * 129]])
def test_corrupt_grants_are_dependency_failure_not_empty(in_memory_session, bad):
    s = in_memory_session
    _, key = seed(s)
    replace_roles(s, "p", "u", ["r"])
    s.get(m.SemanticAccessRoleModel, "r").grants = bad
    s.commit()
    with pytest.raises(AuthorizationDependencyError):
        resolve_api_key(s, key)
    s.get(m.SemanticAccessRoleModel, "r").grants = []
    s.commit()
    assert resolve_api_key(s, key).semantic_grants == set()


def test_database_failure_has_retryable_dependency_contract(in_memory_session, monkeypatch):
    s = in_memory_session
    record, _ = seed(s)

    def unavailable(*args, **kwargs):
        raise SQLAlchemyError("unavailable")

    monkeypatch.setattr(s, "get", unavailable)
    with pytest.raises(AuthorizationDependencyError):
        principal_from_key(s, record)


def test_database_prevents_cross_project_assignment_and_cascades(in_memory_session):
    s = in_memory_session
    seed(s)
    s.add(m.SemanticAccessRoleMemberModel(project_id="p", user_id="u", role_id="else"))
    with pytest.raises(IntegrityError):
        s.commit()
    s.rollback()
    replace_roles(s, "p", "u", ["r"])
    s.delete(s.get(m.ProjectModel, "p"))
    s.commit()
    assert s.get(m.UserModel, "u") is not None
    assert s.get(m.SemanticAccessRoleModel, "else") is not None
    assert s.get(m.ProjectUserMembershipModel, ("p", "u")) is None
    assert s.get(m.SemanticAccessRoleMemberModel, ("p", "u", "r")) is None


def test_business_role_mapping_reads_declared_meaning_and_gap(in_memory_session):
    import json
    from app.core.config import Settings
    from app.repositories.rdf_store import SparqlResult
    from app.services.ontology_workspace import OntologyWorkspaceService
    from app.services.subject_access import save_role
    from fastapi import HTTPException

    s = in_memory_session
    seed(s)
    o = m.OntologyModel(id=str(uuid4()), project_id="p", name="O")
    s.add(o)
    s.flush()
    OntologyWorkspaceService(s, Settings()).ensure(o)
    s.commit()

    class Store:
        definition = {"semantic_role": "business_role"}

        def query_sparql(self, query, timeout_seconds, limit):
            return SparqlResult(
                result={
                    "results": {
                        "bindings": [{"definition": {"value": json.dumps(self.definition)}}]
                        if self.definition
                        else []
                    }
                },
                result_format="application/sparql-results+json",
            )

    store = Store()
    values = {
        "name": "business",
        "grants": ["cost"],
        "business_role_iri": "urn:role",
        "business_role_ontology_id": o.id,
    }
    role = save_role(s, store, Settings(), "p", values)
    assert business_role_status(s, store, Settings(), "p", o.id, "urn:role") == "valid"
    store.definition = None
    assert business_role_status(s, store, Settings(), "p", o.id, "urn:role") == "missing"
    assert role.grants == ["cost"]
    store.definition = {"semantic_role": "object"}
    with pytest.raises(HTTPException):
        save_role(s, store, Settings(), "p", values, role)
    assert business_role_status(s, store, Settings(), "q", o.id, "urn:role") == "missing"


def test_project_admin_cannot_probe_global_user_existence(r008_client):
    e = r008_client
    with e["factory"]() as session:
        user = m.UserModel(id=str(uuid4()), username="outside-project")
        session.add(user)
        session.commit()
        foreign_id = user.id
    results = []
    for uid in (foreign_id, "does-not-exist"):
        response = e["client"].post(
            "/api/api-keys",
            json={
                "name": "probe",
                "project_id": e["ids"]["p1"],
                "user_id": uid,
                "scopes": ["read"],
            },
            headers={"Authorization": f"Bearer {e['p1_admin_key']}"},
        )
        assert response.status_code == 404
        results.append(response.json())
    assert results[0] == results[1]
