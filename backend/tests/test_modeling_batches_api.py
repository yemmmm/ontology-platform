"""REST contract coverage for R-004 Modeling Batches."""

from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.modeling_batches import router
from app.api.schemas import BuildSessionCreate
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import SparqlResult
from app.services.build_sessions import BuildSessionService
from app.services.modeling_workspace import ModelingWorkspaceVersionService
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
    version = ModelingWorkspaceVersionService(in_memory_session, settings).version_for("o")

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
            "expected_workspace_version": version,
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
    detail = client.get(f"/api/modeling-batches/{submitted['batch_id']}")
    listed = client.get(f"/api/build-sessions/{build['id']}/modeling-batches")
    context = client.get("/api/ontologies/o/modeling-context")
    assert detail.status_code == listed.status_code == context.status_code == 200
    assert detail.json()["attempts"][0]["attempt_id"] == submitted["attempt_id"]
    assert listed.json()["batches"][0]["batch_id"] == submitted["batch_id"]
    assert context.json()["workspace"]["workspace_version"] == version
    delta = client.get("/api/ontologies/o/semantic-read-models/delta")
    assert delta.status_code == 200, delta.text
    assert {warning["code"] for warning in delta.json()["warnings"]} == {
        "no_prior_graph_set"
    }


def test_rest_rejects_actor_and_target_overrides_before_processing(
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
            "expected_workspace_version": "v",
            "actor": "forged",
            "items": [
                {"client_item_id": "i", "command_kind": "create_class", "payload": {"name": "X"}}
            ],
        },
    )
    assert response.status_code == 422
