"""REST contract coverage for R-004 Modeling Batches."""

from collections.abc import Generator
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.modeling_batches import router
from app.api.schemas import BuildSessionCreate
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import SparqlResult
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency
from app.services.build_sessions import BuildSessionService
from app.services.modeling_workspace import OntologyModelRevisionService
from app.services.ontology_workspace import OntologyWorkspaceService


class NoWriteRdfStore:
    def graph_exists(self, _graph_iri):
        return False

    def get_graph(self, _graph_iri, _format):
        return ""

    def query_read_model(self, **_kwargs):
        return SparqlResult(result={"head": {"vars": []}, "results": {"bindings": []}})


def test_rest_submit_get_list_and_context_share_the_persisted_contract(
    in_memory_session: Session,
) -> None:
    settings = Settings(
        semantic_graph_iri_prefix="https://r004-api.test/graph/",
        semantic_base_iri="https://r004-api.test/resource/",
        semantic_product_write_mode="rdf_primary",
    )
    in_memory_session.add(ProjectModel(id="p", name="P", normalized_label="p"))
    ontology = OntologyModel(id="o", project_id="p", name="O")
    in_memory_session.add(ontology)
    in_memory_session.flush()
    OntologyWorkspaceService(in_memory_session, settings).ensure(ontology)
    in_memory_session.commit()
    build, _created = BuildSessionService(in_memory_session, settings).create_session(
        "p", BuildSessionCreate(client_session_id="rest-agent")
    )
    version = OntologyModelRevisionService(in_memory_session, settings).version_for("o")

    app = FastAPI()
    app.include_router(router, prefix="/api")

    def db() -> Generator[Session, None, None]:
        yield in_memory_session

    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_rdf_store] = lambda: NoWriteRdfStore()
    client = TestClient(app)
    response = client.post(
        f"/api/build-sessions/{build['id']}/modeling-batches",
        json={
            "client_batch_id": "rest-batch",
            "ontology_id": "o",
            "idempotency_key": "rest-attempt",
            "mode": "dry_run",
            "expected_model_revision": version,
            "items": [
                {
                    "client_item_id": "class",
                    "command_kind": "create_class",
                    "payload": {"name": "Customer"},
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    submitted = response.json()
    assert submitted["attempt_status"] == "validated"
    assert "operation_plan" not in submitted
    detail = client.get(f"/api/modeling-batches/{submitted['batch_id']}")
    listed = client.get(f"/api/build-sessions/{build['id']}/modeling-batches")
    context = client.get("/api/ontologies/o/modeling-context")
    assert detail.status_code == listed.status_code == context.status_code == 200
    assert detail.json()["attempts"][0]["attempt_id"] == submitted["attempt_id"]
    assert listed.json()["batches"][0]["batch_id"] == submitted["batch_id"]
    assert context.json()["workspace"]["model_revision"] == version
    delta = client.get("/api/ontologies/o/semantic-read-models/delta")
    assert delta.status_code == 400, delta.text
    assert delta.json()["detail"]["code"] == "unsupported_read_model"
    for alias, canonical in (
        ("classes", "ontology-schema-summary"),
        ("entities", "entity-list"),
        ("facts", "statement-list"),
    ):
        read = client.get(f"/api/ontologies/o/semantic-read-models/{alias}")
        assert read.status_code == 200, read.text
        assert read.json()["model_name"] == canonical


@pytest.mark.parametrize("model_name", ["entity-list", "entity-detail", "entities"])
def test_entity_read_models_supply_current_identity_for_approved_reuse(
    in_memory_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    model_name: str,
) -> None:
    # Only public, synthetic identities; the real semantic service decorates
    # the RDF response, and the unchanged runner guard checks the resulting page.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from modeling_team import runner
    from modeling_team.staged_decisions import candidate_item_digest

    settings = Settings(
        semantic_graph_iri_prefix="https://read-api.test/graph/",
        semantic_base_iri="https://read-api.test/resource/",
    )
    in_memory_session.add(ProjectModel(id="p", name="P", normalized_label="p"))
    ontology = OntologyModel(id="o", project_id="p", name="O")
    in_memory_session.add(ontology)
    in_memory_session.flush()
    OntologyWorkspaceService(in_memory_session, settings).ensure(ontology)
    ontology.model_revision = 7
    in_memory_session.commit()
    iri = "https://read-api.test/resource/public-entity"
    queries = []

    class EntityReadRdfStore(NoWriteRdfStore):
        def query_read_model(self, **kwargs):
            queries.append(kwargs["query"])
            return SparqlResult(
                result={
                    "head": {"vars": ["entity", "semantic_id", "label", "graph"]},
                    "results": {
                        "bindings": [
                            {
                                "entity": {"type": "uri", "value": iri},
                                "semantic_id": {"type": "literal", "value": "public-entity"},
                                "label": {"type": "literal", "value": "Public entity"},
                                "graph": {"type": "uri", "value": ontology.model_graph_iri},
                            }
                        ]
                    },
                }
            )

    app = FastAPI()
    app.include_router(router, prefix="/api")

    def db() -> Generator[Session, None, None]:
        yield in_memory_session

    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_rdf_store] = lambda: EntityReadRdfStore()
    app.dependency_overrides[principal_dependency] = lambda: AuthPrincipal(
        subject_type="api_key",
        subject_id="public-reader",
        actor="public-reader",
        scopes=frozenset({"read"}),
        project_id="p",
        auth_method="api_key",
    )
    client = TestClient(app)
    response = client.get(
        f"/api/ontologies/o/semantic-read-models/{model_name}",
        params={"entity_iri": iri, "limit": 1},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    canonical = "entity-list" if model_name == "entities" else model_name
    assert data["model_name"] == canonical
    assert f"# template: {canonical}" in queries[-1]
    if model_name == "entity-detail":
        assert f"VALUES ?entity {{ <{iri}> }}" in queries[-1]
    assert data["ontology_id"] == "o"
    assert type(data["model_revision"]) is int
    assert data["model_revision"] == 7
    assert data["items"][0]["iri"] == iri
    if canonical == "entity-list":
        assert data["items"][0]["entity_iri"] == iri
        assert data["items"][0]["project_id"] == "p"
        assert data["items"][0]["model_revision"] == 7
    context = client.get("/api/ontologies/o/modeling-context")
    assert context.status_code == 200, context.text
    assert context.json()["workspace"]["model_revision"] == data["model_revision"]

    # MCP uses this existing ok/data envelope for a successful adapter read.
    # Candidate/approval parsing is isolated; the actual reuse guard is invoked.
    ref = "observed-read.json"
    artifact = tmp_path / ref
    artifact.write_text(json.dumps({"ok": True, "data": data}))
    item = {"item_id": "reused", "label": "Public entity"}
    decisions = [
        {
            "decision": "approved",
            "target_id": "reused",
            "candidate_id": "public",
            "content_revision": 1,
            "content_digest": candidate_item_digest(item),
        }
    ]
    monkeypatch.setattr(runner, "load_unified_candidate", lambda _path: {"items": [item]})
    monkeypatch.setattr(runner, "load_approvals", lambda _path: {"decisions": decisions})
    record = {
        "tool": "get_ontology_read_model",
        "successful": True,
        "request_arguments": {"ontology_id": "o", "model_name": model_name},
        "response_digest": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }
    owner = SimpleNamespace(
        run=SimpleNamespace(root=tmp_path),
        acceptance=SimpleNamespace(_platform_read_artifacts={ref: record}),
        _checkpoint_platform_bindings=lambda: {"ontology_ids": ["o"]},
        staged_plan_read_forwarder=lambda _tool, _args: {"ok": True, "data": context.json()},
    )
    plan = {
        "projection": {
            "candidate_id": "public",
            "candidate_revision": 1,
            "ontology_id": "o",
            "decision_bindings": [],
            "identity_bindings": [
                {
                    "candidate_item_id": "reused",
                    "resource_iri": iri,
                    "evidence_ref": ref,
                }
            ],
        }
    }
    assert runner.TeamRunner._validated_reuse_bindings(owner, plan) == {
        "reused": {"resource_iri": iri, "read_ref": ref, "ontology_id": "o", "model_revision": 7},
    }
    decisions[0]["content_digest"] = "mismatched"
    with pytest.raises(runner.StagedSubmissionRejection) as rejected:
        runner.TeamRunner._validated_reuse_bindings(owner, plan)
    assert rejected.value.data["reason_code"] == "approval_content_mismatch"


def test_rest_accepts_actor_hint_but_uses_authenticated_actor(
    in_memory_session: Session,
) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def db() -> Generator[Session, None, None]:
        yield in_memory_session

    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_settings] = lambda: Settings()
    app.dependency_overrides[get_rdf_store] = lambda: NoWriteRdfStore()
    client = TestClient(app)
    response = client.post(
        "/api/build-sessions/unknown/modeling-batches",
        json={
            "client_batch_id": "b",
            "ontology_id": "o",
            "idempotency_key": "k",
            "expected_model_revision": 1,
            "actor": "forged",
            "items": [
                {"client_item_id": "i", "command_kind": "create_class", "payload": {"name": "X"}}
            ],
        },
    )
    # Unknown session is reached after the compatibility-only actor field is
    # accepted; the field must not be rejected by Pydantic or become authority.
    assert response.status_code == 404
