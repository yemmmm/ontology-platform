"""Independent R4.0-006 acceptance: real bearer/session and MCP authentication.

SQLite proves control-plane transactions and authorization; the reused RDF fixture
proves filtering contracts, not live semantic-engine or modeling quality.
"""
from dataclasses import replace
import json
import asyncio
import os
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from rdflib import Dataset, URIRef

from app.api.deps import get_rdf_store, get_settings
from app.core.config import Settings
from app.main import create_app
from app.mcp import runtime
from app.mcp.server import mcp
from app.repositories.models import (
    ApiKeyModel, OntologyModel, ProjectModel, ProjectUserMembershipModel,
    SemanticAccessRoleModel, SemanticProtectionSetModel,
    SemanticAccessRoleMemberModel, SemanticProtectionSetMemberModel, UserModel,
    SemanticGraphRegistryModel,
    SemanticGraphStateModel, SemanticGraphRevisionModel,
)
from app.repositories.rdf_store import SparqlResult
from app.repositories.rdf_store import RdfStoreRepository
from app.repositories.postgres import create_session_factory
from app.services.checkpoint_data import CheckpointDataService
from test_checkpoint_data import Store as SnapshotStore
from app.security.auth import create_api_key, hash_password, resolve_api_key, sign_session
from app.security.http import SESSION_COOKIE
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_context_cursor import (
    CursorBinding, CursorPayload, ContextCursorCodec, ContextCursorMismatch, binding_digest,
)
from test_semantic_access_http import AccessStore, COST_IRI, PUBLIC_IRI


@pytest.fixture
def independent_env(in_memory_session):
    session = in_memory_session
    settings = Settings()
    admin = UserModel(id=str(uuid4()), username="independent-admin", is_org_admin=True,
                      password_hash=hash_password("acceptance-password"))
    session.add_all([admin, ProjectModel(id="p", name="P", normalized_label="p"),
                     ProjectModel(id="p2", name="P2", normalized_label="p2")])
    session.commit()
    org, org_key = create_api_key(session, name="independent-org", project_id=None,
                                  scopes=["admin"], user_id=admin.id)
    _, bootstrap_key = create_api_key(session, name="server-bootstrap", project_id=None,
                                      scopes=["admin"], bootstrap=True)
    ontology = OntologyModel(id="o", project_id="p", name="O")
    session.add(ontology)
    session.flush()
    service = OntologyWorkspaceService(session, settings)
    service.ensure(ontology)
    context = service.context("o")
    graph = context["model_graph_iri"]
    for name in ("g1", "g2"):
        session.add(SemanticProtectionSetModel(id=name, project_id="p", name=name,
                                                allowed_grants=[name]))
        session.flush()
        session.add(SemanticProtectionSetMemberModel(protection_set_id=name,
                                                     resource_iri=COST_IRI, ontology_id="o"))
    session.commit()
    factory = sessionmaker(bind=session.get_bind(), autoflush=False)
    app = create_app()
    app.state.session_factory = factory
    app.state.session_secret = "independent-session-secret"
    store = AccessStore(graph)
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield {"client": client, "factory": factory, "org": org_key,
               "bootstrap": bootstrap_key, "admin": admin.id,
               "graph_set": context["ontology_id"], "store": store}
    runtime.set_runtime_principal(None)


def call(env, method, path, key=None, status=200, **kwargs):
    response = env["client"].request(method, path,
        headers={"Authorization": f"Bearer {key or env['org']}"}, **kwargs)
    assert response.status_code == status, response.text
    if not response.content:
        return None
    return response.json() if "json" in response.headers.get("content-type", "") else response.text


def user(env, project="p"):
    result = call(env, "POST", "/api/users", status=201,
                  json={"username": f"consumer-{uuid4()}"})
    call(env, "POST", f"/api/projects/{project}/members", status=201,
         json={"user_id": result["id"]})
    return result["id"]


def key(env, uid, project="p", scopes=None):
    return call(env, "POST", "/api/api-keys", status=201,
                json={"name": "personal", "user_id": uid, "project_id": project,
                      "scopes": scopes or ["read"]})


def role(env, name=None, grants=None, project="p", **fields):
    return call(env, "POST", f"/api/projects/{project}/semantic-access-roles", status=201,
                json={"name": name or str(uuid4()), "grants": grants or [], **fields})


def assign(env, uid, roles, project="p", status=200):
    return call(env, "PUT", f"/api/projects/{project}/members/{uid}/roles", status=status,
                json={"role_ids": roles})


def resource(env, token, iri=COST_IRI, status=200):
    return call(env, "GET", f"/api/semantic/resources/{iri}", token, status,
                params={"ontology_id": env["graph_set"]})


def activate_mcp(env, token, monkeypatch):
    monkeypatch.setenv("ONTOLOGY_MCP_API_KEY", token)
    monkeypatch.setattr(runtime, "create_session_factory", lambda _: env["factory"])
    monkeypatch.setattr(runtime, "get_resources", lambda: (env["factory"], None, object()))
    return runtime.authenticate_runtime()


def brief():
    return mcp._tool_manager.get_tool("get_project_brief").fn(project_id="p")


def test_independent_identity_multi_key_or_and_scope(independent_env):
    env = independent_env
    uid = user(env)
    read = key(env, uid)
    model = key(env, uid, scopes=["model"])
    for credential in (read, model):
        assert credential["user_id"] == uid
        assert "semantic_grants" not in credential
        metadata = call(env, "GET", f"/api/api-keys/{credential['id']}")
        assert "plaintext_key" not in metadata
        resource(env, credential["plaintext_key"], status=404)
        resource(env, credential["plaintext_key"], PUBLIC_IRI)
    r1 = role(env, grants=["g1", "g1"])
    r2 = role(env, grants=["g2"])
    assert r1["grants"] == ["g1"]
    assign(env, uid, [r1["id"], r2["id"], r1["id"]])
    for credential in (read, model):
        resource(env, credential["plaintext_key"])
    call(env, "DELETE", f"/api/projects/p/semantic-access-roles/{r1['id']}", status=204)
    resource(env, read["plaintext_key"])
    assign(env, uid, [])
    resource(env, read["plaintext_key"], status=404)
    resource(env, read["plaintext_key"], PUBLIC_IRI)
    call(env, "POST", "/api/projects/p/semantic-access-roles", model["plaintext_key"], 403,
         json={"name": "forbidden", "grants": ["g1"]})


def test_independent_project_boundaries_and_atomic_roles(independent_env):
    env = independent_env
    uid = user(env)
    admin_key = key(env, uid, scopes=["admin"])["plaintext_key"]
    r1 = role(env, name="same", grants=["g1"])
    r2 = role(env, name="same", grants=["g2"], project="p2")
    assign(env, uid, [r1["id"]])
    assign(env, uid, [r1["id"], r2["id"]], status=422)
    current = call(env, "GET", f"/api/projects/p/members/{uid}/roles")
    assert current["role_ids"] == [r1["id"]]
    for path in ("/api/users", f"/api/users/{uid}", "/api/projects/p2/members",
                 "/api/projects/p2/semantic-access-roles"):
        call(env, "GET", path, admin_key, 403)
    outside = call(env, "POST", "/api/users", status=201,
                   json={"username": f"outside-{uuid4()}"})["id"]
    errors = [call(env, "POST", "/api/api-keys", admin_key, 404,
                   json={"name": "outside", "user_id": target, "project_id": "p", "scopes": ["read"]})
              for target in (outside, str(uuid4()))]
    assert errors[0] == errors[1]
    call(env, "POST", "/api/projects/p/members", admin_key, 403, json={"user_id": uid})
    assert call(env, "GET", "/api/projects/p/members", admin_key) == [
        {"user_id": uid, "username": call(env, "GET", f"/api/users/{uid}")["username"],
         "project_id": "p"}]
    call(env, "POST", "/api/api-keys", status=422,
         json={"name": "bad", "user_id": uid, "project_id": "p2", "scopes": ["read"]})
    call(env, "POST", "/api/projects/p/semantic-access-roles", status=409,
         json={"name": "same"})


def test_independent_legacy_grants_and_principal_spoof_rejected(independent_env):
    env = independent_env
    uid = user(env)
    credential = key(env, uid)
    for extra in ({"semantic_grants": ["g1"]}, {"role": "admin"}, {"is_bootstrap": True}):
        call(env, "POST", "/api/api-keys", status=422,
             json={"name": "bad", "user_id": uid, "project_id": "p",
                   "scopes": ["read"], **extra})
    call(env, "POST", "/api/api-keys", status=422,
         json={"name": "bootstrap-admin", "project_id": None, "scopes": ["admin"]})
    for fields in ({"semantic_grants": ["g1"]}, {"user_id": env["admin"]},
                   {"project_id": "p2"}):
        call(env, "PATCH", f"/api/api-keys/{credential['id']}", status=422,
             json={"name": "renamed", **fields})
    call(env, "POST", "/api/users", status=422,
         json={"username": "promoted", "is_org_admin": True})
    principal = call(env, "GET", "/api/auth/me", credential["plaintext_key"],
                     params={"user_id": env["admin"], "role": "admin"})
    assert principal["user_id"] == uid and principal["scopes"] == ["read"]
    resource(env, credential["plaintext_key"], status=404)


def test_independent_normal_session_and_admin_read_key(independent_env):
    env = independent_env
    uid = user(env)
    with env["factory"]() as session:
        ordinary = session.get(UserModel, uid)
        ordinary.password_hash = hash_password("acceptance-password")
        session.commit()
        forged = sign_session(ordinary, "independent-session-secret")
    denied = env["client"].post("/api/auth/login", json={
        "username": ordinary.username, "password": "acceptance-password"})
    assert denied.status_code == 401
    env["client"].cookies.set(SESSION_COOKIE, forged)
    assert env["client"].get("/api/users").status_code == 401
    env["client"].cookies.clear()
    valid = env["client"].post("/api/auth/login", json={
        "username": "independent-admin", "password": "acceptance-password"})
    assert valid.status_code == 200
    assert env["client"].get("/api/users").status_code == 200
    env["client"].cookies.clear()
    call(env, "POST", "/api/projects/p/members", status=201, json={"user_id": env["admin"]})
    read = key(env, env["admin"])["plaintext_key"]
    call(env, "GET", "/api/users", read, 403)
    resource(env, read, status=404)


def test_independent_continuous_mcp_refresh_and_dependency_recovery(independent_env, monkeypatch):
    env = independent_env
    uid = user(env)
    token = key(env, uid)["plaintext_key"]
    r = role(env, grants=[" g1 ", "g2"])
    activate_mcp(env, token, monkeypatch)
    assert brief()["ok"] is True
    assert runtime.runtime_principal().semantic_grants == frozenset()
    assign(env, uid, [r["id"]])
    assert brief()["ok"] is True
    assert runtime.runtime_principal().semantic_grants == frozenset({" g1 ", "g2"})
    resource(env, token)  # g2 matches; grant strings are not silently stripped.
    with env["factory"]() as session:
        session.get(SemanticAccessRoleModel, r["id"]).grants = {"broken": True}
        session.commit()
    call(env, "GET", "/api/auth/me", token, 503)
    result = brief()
    assert result["ok"] is False and result["error_code"] == "dependency_error"
    with env["factory"]() as session:
        session.get(SemanticAccessRoleModel, r["id"]).grants = []
        session.commit()
    assert brief()["ok"] is True
    resource(env, token, status=404)
    assign(env, uid, [])
    call(env, "GET", "/api/auth/me", token)


def test_independent_owned_org_key_disable_demote_mcp_and_bootstrap(independent_env, monkeypatch):
    env = independent_env
    activate_mcp(env, env["org"], monkeypatch)
    assert brief()["ok"] is True
    call(env, "PATCH", f"/api/users/{env['admin']}", json={"disabled": True})
    call(env, "GET", "/api/auth/me", env["org"], 401)
    assert brief()["ok"] is False
    call(env, "GET", "/api/users", env["bootstrap"])
    call(env, "PATCH", f"/api/users/{env['admin']}", env["bootstrap"],
         json={"disabled": False})
    assert brief()["ok"] is True
    with env["factory"]() as session:
        session.get(UserModel, env["admin"]).is_org_admin = False
        session.commit()
    call(env, "GET", "/api/auth/me", env["org"], 401)
    assert brief()["ok"] is False
    call(env, "GET", "/api/users", env["bootstrap"])


def test_independent_user_and_membership_lifecycle(independent_env, monkeypatch):
    env = independent_env
    uid = user(env)
    credential = key(env, uid)
    token = credential["plaintext_key"]
    call(env, "POST", "/api/projects/p2/members", status=201, json={"user_id": uid})
    other = key(env, uid, project="p2")["plaintext_key"]
    activate_mcp(env, token, monkeypatch)
    call(env, "PATCH", f"/api/users/{uid}", json={"disabled": True})
    call(env, "GET", "/api/auth/me", token, 401)
    assert brief()["ok"] is False
    call(env, "PATCH", f"/api/users/{uid}", json={"disabled": False})
    call(env, "GET", "/api/auth/me", token)
    assert brief()["ok"] is True
    assign(env, uid, [role(env, grants=["g1"])["id"]])
    call(env, "DELETE", f"/api/projects/p/members/{uid}", status=204)
    call(env, "GET", "/api/auth/me", token, 401)
    assert brief()["ok"] is False
    call(env, "GET", "/api/auth/me", other)
    call(env, "POST", "/api/projects/p/members", status=201, json={"user_id": uid})
    call(env, "GET", "/api/auth/me", token, 401)
    assert call(env, "GET", f"/api/projects/p/members/{uid}/roles")["role_ids"] == []
    assert call(env, "GET", f"/api/api-keys/{credential['id']}")["revoked_at"]
    resource(env, key(env, uid)["plaintext_key"], PUBLIC_IRI)
    call(env, "DELETE", "/api/projects/p2", status=204)
    call(env, "GET", "/api/auth/me", other, 401)
    call(env, "GET", f"/api/users/{uid}")


def test_independent_cursor_effective_permissions(independent_env):
    env = independent_env
    uid = user(env)
    token = key(env, uid)["plaintext_key"]
    r1 = role(env, grants=["g1", "g2"])
    r2 = role(env, grants=["g2", "g1"])
    assign(env, uid, [r1["id"]])
    def binding():
        with env["factory"]() as session:
            principal = resolve_api_key(session, token)
        return CursorBinding(principal=principal, project_id="p", scope_mode="project",
            ontology_ids=("o",), original_queries=("q",), normalized_queries=("q",),
            resource_types=(), assertion_types=(), search_mode="lexical", depth=0,
            limit=1, context_limit=1, model_revisions=())
    original = binding()
    codec = ContextCursorCodec(secret="acceptance-secret", lifetime_seconds=3600, stable_secret=True)
    cursor = codec.encode(CursorPayload(kind="match", binding_digest=binding_digest(original),
                                        model_revisions=()))
    assign(env, uid, [r2["id"]])
    codec.decode(cursor, binding=binding(), expected_kind="match")
    assign(env, uid, [])
    with pytest.raises(ContextCursorMismatch):
        codec.decode(cursor, binding=binding(), expected_kind="match")
    for principal in (replace(original.principal, scopes=frozenset({"model"})),
                      replace(original.principal, user_id="someone-else"),
                      replace(original.principal, subject_id="another-key")):
        with pytest.raises(ContextCursorMismatch):
            codec.decode(cursor, binding=replace(original, principal=principal), expected_kind="match")


def test_independent_filtering_after_http_role_change(independent_env):
    env = independent_env
    uid = user(env)
    token = key(env, uid)["plaintext_key"]
    graph_set = env["graph_set"]
    r = role(env, grants=["g1"])
    for roles, allowed in (([], False), ([r["id"]], True), ([], False)):
        assign(env, uid, roles)
        resource(env, token, status=200 if allowed else 404)
        statements = call(env, "GET", "/api/semantic/statements", token,
                          params={"ontology_id": graph_set})
        assert (COST_IRI in str(statements)) == allowed
        rows = call(env, "GET", f"/api/semantic/ontologies/{graph_set}/read-models/entity-list", token)
        assert (COST_IRI in str(rows)) == allowed
        export = call(env, "GET", f"/api/semantic/ontologies/{graph_set}/export", token)
        parsed = Dataset()
        parsed.parse(data=export, format="trig")
        assert any(s == URIRef(COST_IRI) for s, _, _, _ in parsed.quads()) == allowed
        sparql = call(env, "POST", "/api/semantic/sparql:query", token,
                      200 if allowed else 409,
                      json={"project_id": "p", "scope_mode": "ontologies", "ontology_ids": ["o"],
                            "query": "SELECT * WHERE { ?s ?p ?o }"})
        assert (COST_IRI in str(sparql)) == allowed
        assert all(field not in str(rows) for field in ("semantic_grants", "role_ids", "allowed_grants"))


def test_independent_business_role_mapping_api_and_rdf_gap(independent_env, monkeypatch):
    env = independent_env
    uid = user(env)
    token = key(env, uid)["plaintext_key"]
    definition = {"semantic_role": "business_role"}
    previous = env["store"].query_sparql
    def query(query, timeout_seconds, limit):
        if query.startswith("SELECT ?definition WHERE"):
            return SparqlResult(result={"results": {"bindings": [
                {"definition": {"type": "literal", "value": json.dumps(definition)}}
            ] if definition else []}}, result_format="application/sparql-results+json")
        return previous(query, timeout_seconds, limit)
    monkeypatch.setattr(env["store"], "query_sparql", query)
    same = role(env, name="Business Reviewer", grants=[])
    assert same["business_role_status"] == "unassociated"
    resource(env, token, status=404)
    mapped = role(env, name="explicit", grants=["g1"], business_role_iri="urn:role",
                  business_role_ontology_id="o")
    assert mapped["business_role_status"] == "valid"
    call(env, "POST", "/api/projects/p2/semantic-access-roles", status=422,
         json={"name": "cross", "business_role_iri": "urn:role", "business_role_ontology_id": "o"})
    call(env, "POST", "/api/projects/p/semantic-access-roles", status=422,
         json={"name": "incomplete", "business_role_iri": "urn:role"})
    assign(env, uid, [mapped["id"]])
    resource(env, token)
    definition.clear()
    gap = call(env, "GET", f"/api/projects/p/semantic-access-roles/{mapped['id']}")
    assert gap["business_role_status"] == "missing"
    assert gap["grants"] == ["g1"]
    resource(env, token)
    repaired = call(env, "PATCH", f"/api/projects/p/semantic-access-roles/{mapped['id']}",
                    json={"business_role_iri": None, "business_role_ontology_id": None})
    assert repaired["business_role_status"] == "unassociated"


def test_independent_sql_dependency_retry_http_and_mcp(independent_env, monkeypatch):
    env = independent_env
    token = key(env, user(env))["plaintext_key"]
    activate_mcp(env, token, monkeypatch)
    from sqlalchemy.orm import Session
    original = Session.get
    def unavailable(session, entity, ident, *args, **kwargs):
        if entity is UserModel:
            raise SQLAlchemyError("independent injected user dependency failure")
        return original(session, entity, ident, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Session, "get", unavailable)
        error = call(env, "GET", "/api/auth/me", token, 503)
        assert error["detail"]["code"] == "dependency_error"
        assert brief()["error_code"] == "dependency_error"
    call(env, "GET", "/api/auth/me", token)
    assert brief()["ok"] is True


def test_independent_fork_keeps_protection_without_subject_assignments(independent_env):
    env = independent_env
    uid = user(env)
    key(env, uid)
    assign(env, uid, [role(env, grants=["g1"])["id"]])
    settings = Settings()
    store = SnapshotStore()
    with env["factory"]() as session:
        workspace = OntologyWorkspaceService(session, settings).context("o")
        graph = workspace["model_graph_iri"]
        store.graphs[graph] = f'<{COST_IRI}> <urn:label> "private" .'
        service = CheckpointDataService(session, store)
        snapshot = service.capture("p", ["o"])
        session.commit()
        result = service.fork(snapshot, name="independent fork", settings=settings)
        target = result["project_id"]
        for model in (ApiKeyModel, ProjectUserMembershipModel, SemanticAccessRoleModel,
                      SemanticAccessRoleMemberModel):
            assert list(session.scalars(select(model).where(model.project_id == target))) == []
        protections = list(session.scalars(select(SemanticProtectionSetModel).where(
            SemanticProtectionSetModel.project_id == target)))
        assert len(protections) == 2 and {g for p in protections for g in p.allowed_grants} == {"g1", "g2"}
        assert session.get(UserModel, uid) is not None


@pytest.mark.skipif(os.getenv("RUN_R4006_INDEPENDENT_LIVE") != "1", reason="opt-in live stores")
def test_independent_live_http_and_persistent_stdio_mcp():
    """Real migrated PG/Oxigraph, live HTTP and one persistent stdio MCP process."""
    import httpx
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    admin_id = str(uuid4())
    users = [admin_id]
    projects = []
    graphs = []
    graph_sets = []
    with factory() as session:
        session.add(UserModel(id=admin_id, username=f"r4006-live-admin-{uuid4()}", is_org_admin=True))
        session.commit()
        _, org_token = create_api_key(session, name="r4006-independent-live", project_id=None,
                                      scopes=["admin"], user_id=admin_id)
    try:
        with httpx.Client(base_url="http://127.0.0.1:8001", timeout=30) as client:
            env = {"client": client, "org": org_token}
            project = call(env, "POST", "/api/projects", status=201, json={"name": f"r4006-live-{uuid4()}"})
            project_id = project["id"]
            projects.append(project_id)
            ontology = call(env, "POST", f"/api/projects/{project_id}/ontologies", status=201,
                            json={"name": "Acceptance"})
            ontology_id = ontology["id"]
            context = ontology["workspace"]
            graphs.append(context["model_graph_iri"])
            graph = context["model_graph_iri"]
            graph_set = context["ontology_id"]
            graph_sets.append(graph_set)
            iri = f"urn:r4006-live:{uuid4()}"
            public = f"urn:r4006-public:{uuid4()}"
            business = f"urn:r4006-role:{uuid4()}"
            predicate = settings.semantic_base_iri.rstrip("/") + "/vocab/semanticDefinition"
            ttl = (f'<{iri}> <http://www.w3.org/2000/01/rdf-schema#label> "secret-cost" .\n'
                   f'<{public}> <http://www.w3.org/2000/01/rdf-schema#label> "public" .\n'
                   f'<{business}> <{predicate}> \'{{"semantic_role":"business_role"}}\' .')
            store.put_named_graph(graph, ttl, "turtle")
            uid = user(env, project=project_id)
            users.append(uid)
            token = key(env, uid, project=project_id)["plaintext_key"]
            call(env, "POST", f"/api/projects/{project_id}/protection-sets", status=201,
                 json={"name": "private", "allowed_grants": ["private"],
                       "members": [{"resource_iri": iri, "ontology_id": ontology_id}]})
            mapped = role(env, name="live-business-role", grants=["private"], project=project_id,
                          business_role_iri=business, business_role_ontology_id=ontology_id)
            assert mapped["business_role_status"] == "valid"
            def exact(expected):
                return call(env, "GET", f"/api/semantic/resources/{iri}", token, expected,
                            params={"ontology_id": graph_set})
            async def scenario():
                process_env = dict(os.environ)
                process_env["ONTOLOGY_MCP_API_KEY"] = token
                process_env.pop("ONTOLOGY_PLATFORM_CANDIDATE_GATE_PATH", None)
                params = StdioServerParameters(command=sys.executable,
                    args=["-m", "app.mcp.server"], env=process_env, cwd=os.getcwd())
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        async def exported(expected):
                            result = await session.call_tool("export_semantic_ontology", {"ontology_id": graph_set})
                            data = json.loads(next(c.text for c in result.content if c.type == "text"))
                            assert data["ok"] is True, data
                            dataset = Dataset().parse(data=data["data"]["payload"], format="trig")
                            assert any(s == URIRef(iri) for s, _, _, _ in dataset.quads()) == expected
                            return data
                        exact(404)
                        await exported(False)
                        assign(env, uid, [mapped["id"]], project=project_id)
                        exact(200)
                        await exported(True)
                        assign(env, uid, [], project=project_id)
                        exact(404)
                        await exported(False)
                        call(env, "PATCH", f"/api/users/{uid}", json={"disabled": True})
                        exact(401)
                        result = await session.call_tool("export_semantic_ontology", {"ontology_id": graph_set})
                        data = json.loads(next(c.text for c in result.content if c.type == "text"))
                        assert data["ok"] is False and "credential" in data["error"].lower(), data
                        call(env, "PATCH", f"/api/users/{uid}", json={"disabled": False})
                        exact(404)
                        await exported(False)
            asyncio.run(scenario())
            # Removing the real RDF declaration is a visible mapping gap, never a grant mutation.
            store.put_named_graph(graph, ttl.split(f'<{business}>')[0], "turtle")
            gap = call(env, "GET", f"/api/projects/{project_id}/semantic-access-roles/{mapped['id']}")
            assert gap["business_role_status"] == "missing" and gap["grants"] == ["private"]
            print("LIVE independent PASS: real HTTP, PG/Oxigraph, persistent MCP role refresh, disable/enable, RDF mapping gap")
    finally:
        for graph in graphs:
            store.drop_named_graph(graph)
            assert not store.graph_exists(graph)
        cleanup_live_workspace(factory, graphs, graph_sets)
        with factory() as session:
            session.execute(delete(ProjectModel).where(ProjectModel.id.in_(projects)))
            session.execute(delete(ApiKeyModel).where(ApiKeyModel.user_id.in_(users)))
            session.execute(delete(UserModel).where(UserModel.id.in_(users)))
            session.commit()
            assert not list(session.scalars(select(ProjectModel.id).where(ProjectModel.id.in_(projects))))
            assert not list(session.scalars(select(UserModel.id).where(UserModel.id.in_(users))))


def cleanup_live_workspace(factory, graphs, graph_sets):
    """Generic graph registry/set ownership is not covered by project SQL CASCADE."""
    with factory() as session:
        session.execute(delete(SemanticGraphSetMemberModel).where(
            SemanticGraphSetMemberModel.ontology_id.in_(graph_sets)))
        session.execute(delete(SemanticGraphSetModel).where(SemanticGraphSetModel.id.in_(graph_sets)))
        for model in (SemanticGraphStateModel, SemanticGraphRevisionModel, SemanticGraphRegistryModel):
            session.execute(delete(model).where(model.graph_iri.in_(graphs)))
        session.commit()
        assert not list(session.scalars(select(SemanticGraphRegistryModel.id).where(
            SemanticGraphRegistryModel.graph_iri.in_(graphs))))
        assert not list(session.scalars(select(SemanticGraphSetModel.id).where(
            SemanticGraphSetModel.id.in_(graph_sets))))
