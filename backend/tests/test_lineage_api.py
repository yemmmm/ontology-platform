"""REST contract for the ontology-scoped R-005 lineage endpoint."""

from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.ontologies import router
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel, SemanticEditAuditModel
from app.repositories.rdf_store import RdfGraphDelta
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_lineage_recorder import SemanticLineageRecorder


def _client(session: Session) -> tuple[TestClient, str]:
    settings = Settings(semantic_graph_iri_prefix="https://lineage-api.test/graph/")
    session.add(ProjectModel(id="p", name="P", normalized_label="p"))
    ontology = OntologyModel(id="o", project_id="p", name="O")
    session.add(ontology)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.commit()
    workspace = OntologyWorkspaceService(session, settings).context(ontology.id)
    graph_set_id = workspace["default_graph_set_id"]
    graph = next(
        member["graph_iri"] for member in workspace["members"] if member["role"] == "asserted_data"
    )
    session.add(
        SemanticEditAuditModel(
            id="audit",
            actor=None,
            reason=None,
            input_format="canonical-write",
            target_graph_iri=graph,
            affected_graph_iris=[graph],
            graph_delta={},
            applied=True,
        )
    )
    occurrence = SemanticLineageRecorder(session).record_asserted_delta(
        delta=RdfGraphDelta(
            inserts=[
                (
                    "<https://lineage-api.test/entity/alice>",
                    "<https://lineage-api.test/property/name>",
                    '"Alice"',
                    graph,
                )
            ]
        ),
        graph_revisions={graph: 1},
        audit_id="audit",
        ontology_id=ontology.id,
        graph_set_id=graph_set_id,
    )[0]
    session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api")

    def db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_rdf_store] = lambda: object()
    return TestClient(app), occurrence.statement_id


def test_rest_returns_shared_lineage_shape_and_stable_errors(in_memory_session) -> None:
    client, statement_id = _client(in_memory_session)
    response = client.get(
        "/api/ontologies/o/lineage",
        params={"target_type": "statement", "target_id": statement_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ontology_id"] == "o"
    assert body["target"] == {"type": "statement", "id": statement_id}
    assert body["evidence_status"] == "missing"
    assert body["items"][0]["supporting_context"]["evidence_references"] == []
    assert body["items"][0]["supporting_context"]["edit_audits"][0]["actor"] is None
    assert body["items"][0]["supporting_context"]["edit_audits"][0]["reason"] is None

    invalid = client.get(
        "/api/ontologies/o/lineage",
        params={"target_type": "statement", "target_id": statement_id, "max_depth": 6},
    )
    missing = client.get(
        "/api/ontologies/o/lineage",
        params={"target_type": "statement", "target_id": "0" * 64},
    )
    assert invalid.status_code == 422
    assert missing.status_code == 404


def test_rest_does_not_accept_graph_scope_overrides(in_memory_session) -> None:
    client, statement_id = _client(in_memory_session)
    response = client.get(
        "/api/ontologies/o/lineage",
        params={
            "target_type": "statement",
            "target_id": statement_id,
            "graph_set_id": "forged",
            "graph_iri": "https://forged.test/g",
        },
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["technical_trace"]["graph_set_id"] != "forged"
