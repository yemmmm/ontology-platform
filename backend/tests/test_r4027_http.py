"""Opt-in R4.0-027 contract test with PostgreSQL, Oxigraph and the running API."""

import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import Settings
from app.repositories import models as m
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import create_api_key
from app.services.semantic_derived_state import SemanticRevisionService
from app.services.semantic_projection_job import SemanticProjectionJobService
from app.services.semantic_read_scope import SemanticReadScopeResolver


@pytest.mark.skipif(os.getenv("RUN_R4027_HTTP") != "1", reason="opt-in isolated runtime probe")
def test_numbered_writes_drift_reads_and_rebuild():
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    token = uuid4().hex
    project_id = ontology_id = key_id = None
    graphs = []
    try:
        with factory() as session:
            record, key = create_api_key(
                session, name="r4027-" + token, project_id=None, scopes=["admin"], bootstrap=True
            )
            key_id = record.id
        with httpx.Client(
            base_url="http://127.0.0.1:8001/api",
            timeout=60,
            headers={"Authorization": "Bearer " + key},
        ) as client:

            def post(path, body, status=200):
                response = client.post(path, json=body)
                assert response.status_code == status, response.text
                return response.json()

            def get(path):
                response = client.get(path)
                assert response.status_code == 200, response.text
                return response.json()

            project_id = post("/projects", {"name": "R4027 " + token}, 201)["id"]
            ontology_id = post(
                f"/projects/{project_id}/ontologies", {"name": "Revision test"}, 201
            )["id"]
            with factory() as session:
                graphs.append(session.get(m.OntologyModel, ontology_id).model_graph_iri)
            context_path = f"/ontologies/{ontology_id}/modeling-context"
            assert get(context_path)["workspace"]["model_revision"] == 0
            build = post(
                f"/projects/{project_id}/build-sessions", {"client_session_id": token}, 201
            )
            lease = post(
                f"/build-sessions/{build['id']}/ontology-leases/{ontology_id}:acquire",
                {"client_request_id": token, "expected_session_revision": 1},
            )
            batch_path = f"/build-sessions/{build['id']}/modeling-batches"
            items = [
                {
                    "client_item_id": "e" + str(i),
                    "command_kind": "create_entity",
                    "payload": {
                        "entity_id": token + str(i),
                        "label": "Revision object " + str(i),
                    },
                }
                for i in range(2)
            ]
            request = dict(
                client_batch_id=token,
                ontology_id=ontology_id,
                mode="dry_run",
                idempotency_key="dry",
                expected_model_revision=0,
                items=items,
            )
            for invalid in ("legacy-hash", "0", True, -1):
                post(batch_path, {**request, "expected_model_revision": invalid}, 422)
            assert post(batch_path, request)["attempt_status"] == "validated"
            assert get(context_path)["workspace"]["model_revision"] == 0
            request.update(
                mode="apply_atomic", idempotency_key="apply", lease_token=lease["lease_token"]
            )
            applied = post(batch_path, request)
            assert applied["attempt_status"] == "applied", applied["findings"]
            assert applied["workspace"]["before_version"] == 0
            assert applied["workspace"]["after_version"] == 1
            assert post(batch_path, request)["attempt_id"] == applied["attempt_id"]
            assert get(context_path)["workspace"]["model_revision"] == 1
            iri = applied["items"][0]["resource_outputs"]["resource_iri"]
            exact = get(f"/semantic/resources/{iri}?ontology_id={ontology_id}")
            assert exact["model_revision"] == 1
            drifted = post(batch_path, {**request, "idempotency_key": "stale"}, 409)
            assert drifted["detail"]["current_model_revision"] == 1
            query = dict(
                project_id=project_id,
                scope_mode="ontologies",
                ontology_ids=[ontology_id],
                query="Revision object",
                search_mode="lexical",
                depth=0,
                limit=1,
            )
            first = post("/semantic/context:query", query)
            cursor = first["matches_page"]["next_match_cursor"]
            assert cursor
            assert first["scope"]["ontologies"][0]["model_revision"] == 1
            edited = post(
                "/semantic/edits",
                dict(
                    ontology_id=ontology_id,
                    format="turtle",
                    content='<urn:r4027:new> <http://www.w3.org/2000/01/rdf-schema#label> "Revision object new" .',
                ),
            )
            assert edited["applied"]
            assert get(context_path)["workspace"]["model_revision"] == 2
            post("/semantic/context:query", {**query, "match_cursor": cursor}, 409)
            rebuild = post(f"/semantic/ontologies/{ontology_id}/retrieval:rebuild", {})
            assert rebuild["status"] == "current", rebuild
            assert rebuild["model_revision"] == 2
            assert get(context_path)["workspace"]["model_revision"] == 2
            resumed = {
                **request,
                "client_batch_id": token + "-next",
                "idempotency_key": "next",
                "expected_model_revision": 2,
                "items": [
                    {
                        "client_item_id": "third",
                        "command_kind": "create_entity",
                        "payload": {"entity_id": token + "-third", "label": "Next"},
                    }
                ],
            }
            assert post(batch_path, resumed)["workspace"]["after_version"] == 3

            # A separate committed SQL session changes the model while this
            # builder still holds its original ORM objects and input scope.
            class ChangingWriter:
                kind = "search"

                def rebuild(self, **_kwargs):
                    with factory() as writer:
                        SemanticRevisionService(writer).bump_revisions(graphs)
                        writer.commit()
                    return {"document_count": 1}

            with factory() as session:
                jobs = SemanticProjectionJobService(
                    session, {"search": ChangingWriter()}, SemanticReadScopeResolver
                )
                job = jobs.create_job(ontology_id, "search", "r4027-test")
                assert job.model_revision == 3
                assert jobs.run_job(job.id).status == "stale"
                assert not session.scalar(
                    select(m.SemanticProjectionManifestModel.id).where(
                        m.SemanticProjectionManifestModel.active_job_id == job.id
                    )
                )
            assert get(context_path)["workspace"]["model_revision"] == 4
    finally:
        with factory() as session:
            if ontology_id:
                for model in (m.SemanticProjectionManifestModel, m.SemanticProjectionJobModel):
                    session.execute(delete(model).where(model.ontology_id == ontology_id))
            if project_id:
                session.execute(delete(m.ProjectModel).where(m.ProjectModel.id == project_id))
            if key_id:
                session.execute(delete(m.ApiKeyModel).where(m.ApiKeyModel.id == key_id))
            for model in (
                m.SemanticGraphStateModel,
                m.SemanticGraphRevisionModel,
                m.SemanticGraphRegistryModel,
            ):
                session.execute(delete(model).where(model.graph_iri.in_(graphs)))
            session.commit()
        for graph in graphs:
            store.drop_named_graph(graph)
