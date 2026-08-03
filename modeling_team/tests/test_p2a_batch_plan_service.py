from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.schemas import (
    BuildSessionCreate,
    ModelingBatchSubmit,
    ModelingItemInput,
    OntologyLeaseAcquire,
)
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.postgres import Base
from app.repositories.rdf_store import GraphWriteResult
from app.services.build_sessions import BuildSessionService
from app.services.modeling_batches import ModelingBatchService
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.ontology_workspace import OntologyWorkspaceService
from modeling_team.matrix_artifact import load_matrix
from modeling_team.p2a_batch_plan import ASSERTION_CLIENT_ITEM_IDS, build_p2a_batch_plan
from modeling_team.p2a_protocol_driver import _generated_candidate
from modeling_team.proof_v2 import build_candidate_item_evidence_map


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(element, compiler, **kwargs):  # noqa: ARG001
    return "JSON"


class FakeRdfStore:
    def __init__(self) -> None:
        self.deltas = []

    def graph_exists(self, _graph_iri):
        return False

    def get_graph(self, _graph_iri, _format):
        return ""

    def apply_dataset_delta(self, delta):
        self.deltas.append(delta)
        return GraphWriteResult(
            graph_iri=delta.affected_graph_iris()[0] if delta.affected_graph_iris() else "",
            applied=not delta.is_empty,
            inserted_quad_count=len(delta.inserts),
            deleted_quad_count=len(delta.deletes),
        )


def test_exact_four_plan_compiles_and_service_dry_run_has_zero_rdf_side_effects():
    root = Path(__file__).resolve().parents[2]
    candidate, _selected = _generated_candidate(load_matrix(root))
    evidence_map = build_candidate_item_evidence_map(
        candidate,
        ASSERTION_CLIENT_ITEM_IDS,
        run_id="p2a-service-integration",
    )
    receipt = {
        "status": "accepted",
        "candidate_revision": candidate["candidate_revision"],
        "semantic_digest": candidate["semantic_digest"],
        "candidate_digest": candidate["candidate_digest"],
    }
    plan = build_p2a_batch_plan(
        candidate,
        evidence_map,
        receipt,
        expected_run_id="p2a-service-integration",
    )
    items = [ModelingItemInput.model_validate(item) for item in plan["items"]]

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    settings = Settings(
        semantic_graph_iri_prefix="https://p2a.test/graph/",
        semantic_base_iri="https://p2a.test/resource/",
        semantic_product_write_mode="rdf_primary",
    )
    rdf = FakeRdfStore()
    with factory() as session:
        project_id = "p2a-project"
        ontology_id = "p2a-ontology"
        session.add(ProjectModel(id=project_id, name="P2a", normalized_label="p2a"))
        ontology = OntologyModel(
            id=ontology_id,
            project_id=project_id,
            name="P2a ontology",
        )
        session.add(ontology)
        session.flush()
        OntologyWorkspaceService(session, settings).ensure(ontology)
        session.commit()
        build = BuildSessionService(session, settings)
        build_session, _created = build.create_session(
            project_id,
            BuildSessionCreate(client_session_id="p2a-agent-session"),
        )
        build.acquire_ontology_lease(
            build_session["id"],
            ontology_id,
            OntologyLeaseAcquire(
                client_request_id="p2a-lease",
                expected_session_revision=1,
            ),
        )
        version = ModelingWorkspaceVersionService(session, settings).version_for(ontology_id)
        service = ModelingBatchService(session, settings, rdf)  # type: ignore[arg-type]
        result = service.submit(
            build_session["id"],
            ModelingBatchSubmit(
                client_batch_id="p2a-exact-four",
                ontology_id=ontology_id,
                idempotency_key="p2a-exact-four-dry-run",
                mode="dry_run",
                expected_workspace_version=version,
                items=items,
            ),
        )

    engine.dispose()
    assert result["attempt_status"] == "validated"
    assert [item["client_item_id"] for item in result["items"]] == list(
        ASSERTION_CLIENT_ITEM_IDS.values()
    )
    assert len(result["operation_plan"]["evidence"]) == 4
    assert not any(finding["blocking"] for finding in result["findings"])
    assert rdf.deltas == []
    normalized = json.dumps(result["normalized_delta"], sort_keys=True)
    assert "published" in normalized
    assert "http://www.w3.org/2001/XMLSchema#string" not in normalized
