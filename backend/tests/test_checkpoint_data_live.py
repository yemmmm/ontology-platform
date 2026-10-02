"""Opt-in PostgreSQL + Oxigraph round trip using only test-owned resources."""

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from uuid import uuid4

import pytest
import httpx
from sqlalchemy import delete, select

from app.core.config import Settings
from app.repositories import models as m
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import RdfStoreRepository
from app.services.checkpoint_data import CheckpointDataService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.security.auth import create_api_key


@pytest.mark.skipif(os.getenv("RUN_CHECKPOINT_DATA_LIVE") != "1", reason="opt-in live stores")
def test_postgres_oxigraph_snapshot_fork_roundtrip():
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    project_id, ontology_id, target_project_id = (str(uuid4()) for _ in range(3))
    project_ids = [project_id, target_project_id]
    ontology_ids = [ontology_id]
    graph_iris = []
    base_url = os.getenv("CHECKPOINT_DATA_HTTP_BASE_URL")
    key_id = None
    headers = {}
    try:
        with factory() as session:
            if base_url:
                key_record, key = create_api_key(
                    session, name="r3017-live-check", project_id=None, scopes=["admin"]
                )
                key_id = key_record.id
                headers = {"Authorization": "Bearer " + key}
            session.add(
                m.ProjectModel(id=project_id, name="R3017 live source", normalized_label="test")
            )
            session.flush()
            ontology = m.OntologyModel(id=ontology_id, project_id=project_id, name="Business")
            session.add(ontology)
            session.flush()
            workspace = OntologyWorkspaceService(session, settings)
            workspace.ensure(ontology)
            context = workspace.context(ontology_id)
            graph_iris.extend(item["graph_iri"] for item in context["members"])
            session.commit()
        iri = graph_iris[0]
        store.put_named_graph(iri, '<urn:r3017:Order> <urn:label> "Before writer" .', "turtle")
        capture_started = Event()

        def capture():
            if base_url:
                capture_started.set()
                response = httpx.post(
                    base_url + "/api/checkpoint-data/capture",
                    headers=headers,
                    json={"project_id": project_id, "ontology_ids": [ontology_id]},
                    timeout=20,
                )
                assert response.status_code == 200, response.text
                return response.json()
            with factory() as session:
                capture_started.set()
                return CheckpointDataService(session, store).capture(project_id, [ontology_id])

        with ThreadPoolExecutor(max_workers=1) as pool, factory() as writer:
            writer.scalar(
                select(m.ProjectModel).where(m.ProjectModel.id == project_id).with_for_update()
            )
            writer.scalar(
                select(m.OntologyModel).where(m.OntologyModel.id == ontology_id).with_for_update()
            )
            future = pool.submit(capture)
            assert capture_started.wait(5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
            # Update a different SQL row: the Ontology lock row itself does
            # not change, so repeatable-read cannot rely on a serialization
            # error to detect an incorrectly early transaction snapshot.
            writer.get(m.ProjectModel, project_id).description = "Saved generation"
            store.put_named_graph(iri, '<urn:r3017:Order> <urn:label> "Saved" .', "turtle")
            writer.commit()
            snapshot = future.result(timeout=15)
        assert snapshot["tables"]["projects"][0]["description"] == "Saved generation"
        assert "Saved" in snapshot["graphs"][iri]
        store.put_named_graph(iri, '<urn:r3017:Order> <urn:label> "Later" .', "turtle")
        with factory() as session:
            if base_url:
                response = httpx.post(
                    base_url + "/api/checkpoint-data/fork",
                    headers=headers,
                    json={
                        "snapshot": snapshot,
                        "name": "R3017 live fork",
                        "target_project_id": target_project_id,
                    },
                    timeout=30,
                )
                assert response.status_code == 200, response.text
                result = response.json()
                denied = httpx.patch(
                    base_url + f"/api/projects/{project_id}",
                    headers=headers,
                    json={"name": "should remain sealed"},
                )
                assert denied.status_code == 409, denied.text
                assert (
                    httpx.get(base_url + f"/api/projects/{project_id}", headers=headers).status_code
                    == 200
                )
            else:
                result = CheckpointDataService(session, store).fork(
                    snapshot,
                    name="R3017 live fork",
                    settings=settings,
                    target_project_id=target_project_id,
                )
            ontology_ids.extend(result["ontology_ids"])
            graph_iris.extend(result["identity_mapping"][item] for item in list(graph_iris))
            assert session.get(m.OntologyModel, ontology_id).status == "archived"
            assert (
                OntologyWorkspaceService(session, settings).context(result["ontology_ids"][0])[
                    "state"
                ]
                == "ready"
            )
        new_iri = result["identity_mapping"][iri]
        assert "Saved" in store.get_graph(new_iri, "turtle")
        assert "Later" in store.get_graph(iri, "turtle")
        store.put_named_graph(new_iri, '<urn:r3017:Order> <urn:label> "Continued" .', "turtle")
        assert "Continued" in store.get_graph(new_iri, "turtle")
        assert "Later" in store.get_graph(iri, "turtle")
    finally:
        # Discover identities even when a response/assertion failed after commit.
        with factory() as session:
            ontology_ids = list(
                session.scalars(
                    select(m.OntologyModel.id).where(m.OntologyModel.project_id.in_(project_ids))
                )
            )
            graph_iris = list(
                set(graph_iris)
                | set(
                    session.scalars(
                        select(m.SemanticGraphRegistryModel.graph_iri).where(
                            m.SemanticGraphRegistryModel.semantic_owner_type == "ontology",
                            m.SemanticGraphRegistryModel.semantic_owner_id.in_(ontology_ids),
                        )
                    )
                )
            )
            sets = list(
                session.scalars(
                    select(m.SemanticGraphSetModel.id).where(
                        m.SemanticGraphSetModel.scope_type == "ontology",
                        m.SemanticGraphSetModel.scope_id.in_(ontology_ids),
                    )
                )
            )
            session.execute(
                delete(m.SemanticGraphSetMemberModel).where(
                    m.SemanticGraphSetMemberModel.graph_set_id.in_(sets)
                )
            )
            session.execute(
                delete(m.SemanticGraphSetModel).where(m.SemanticGraphSetModel.id.in_(sets))
            )
            for model in (
                m.SemanticGraphStateModel,
                m.SemanticGraphRevisionModel,
                m.SemanticGraphRegistryModel,
            ):
                session.execute(delete(model).where(model.graph_iri.in_(graph_iris)))
            session.execute(delete(m.ProjectModel).where(m.ProjectModel.id.in_(project_ids)))
            if key_id is not None:
                session.execute(delete(m.ApiKeyModel).where(m.ApiKeyModel.id == key_id))
            session.commit()
        for graph in graph_iris:
            store.drop_named_graph(graph)
