"""Opt-in R4.0-025 API/PostgreSQL/Oxigraph contract probe, without modeling starts."""
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select, or_

from app.core.config import Settings
from app.repositories import models as m
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import create_api_key
from subject_access_support import create_api_key as create_reader_key


@pytest.mark.skipif(os.getenv("RUN_R4025_HTTP") != "1", reason="opt-in isolated runtime probe")
def test_retirement_ordinary_rule_atomic_write_readback_and_protection():
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    token = uuid4().hex
    project_id = ontology_id = reader_user = None
    graphs, key_ids = [], []
    try:
        with factory() as session:
            record, key = create_api_key(session, name="r4025-" + token,
                                        project_id=None, scopes=["admin"], bootstrap=True)
            key_ids.append(record.id)
        with httpx.Client(base_url="http://127.0.0.1:8001", timeout=30,
                          headers={"Authorization": "Bearer " + key}) as client:
            def post(path, body, status=200):
                response = client.post("/api" + path, json=body)
                assert response.status_code == status, response.text
                return response.json()

            def get(path, params=None):
                response = client.get("/api" + path, params=params)
                assert response.status_code == 200, response.text
                return response.json()

            for route in ("validation-runs", "reasoning-runs", "derived-results:reconcile"):
                assert client.post("/api/semantic/" + route, json={}).status_code == 404
            project_id = post("/projects", {"name": "R4025 " + token}, 201)["id"]
            ontology = post(f"/projects/{project_id}/ontologies", {"name": "普通工单规则"}, 201)
            ontology_id = ontology["id"]
            graph_set = ontology["workspace"]["ontology_id"]
            graphs.extend(member["graph_iri"] for member in ontology["workspace"]["members"])
            assert not next(m for m in ontology["workspace"]["members"]
                            if m["role"] == "shapes")["editable"]
            build = post(f"/projects/{project_id}/build-sessions",
                         {"client_session_id": token}, 201)
            lease = post(f"/build-sessions/{build['id']}/ontology-leases/{ontology_id}:acquire",
                         {"client_request_id": token, "expected_session_revision": 1})
            version = get(f"/ontologies/{ontology_id}/modeling-context")["workspace"]["model_revision"]
            batch_path = f"/build-sessions/{build['id']}/modeling-batches"
            item = {"client_item_id": "rule", "command_kind": "create_entity", "payload": {
                "entity_id": token + "-shape-owl-rule", "label": "工单关闭规则",
                "semantic_definition": {"semantic_role": "Rule",
                    "business_meaning": "未验收工单不能关闭；SLA 从报修时间开始计时",
                    "applicability": "工单", "unknowns": ["超时例外待确认"]},
            }}
            request = dict(client_batch_id=token, ontology_id=ontology_id, mode="apply_atomic",
                           idempotency_key="apply", expected_model_revision=version,
                           lease_token=lease["lease_token"], items=[item])
            invalid = {**request, "client_batch_id": token + "-invalid", "idempotency_key": "invalid",
                       "mode": "apply_atomic", "lease_token": lease["lease_token"], "items": [item,
                       {"client_item_id": "bad", "command_kind": "create_entity",
                        "payload": {"label": "坏格式", "properties": []}}]}
            bad = post(batch_path, invalid)
            assert bad["attempt_status"] == "validation_failed"
            assert any("bad" in finding["client_item_ids"] for finding in bad["findings"])
            assert not get("/semantic/statements", {"ontology_id": graph_set})["items"]
            applied = post(batch_path, request)
            assert applied["attempt_status"] == "applied", applied["findings"]
            assert post(batch_path, request)["attempt_id"] == applied["attempt_id"]
            iri = applied["items"][0]["resource_outputs"]["resource_iri"]
            exact = get("/semantic/resources/" + iri, {"ontology_id": graph_set})
            definition = exact["properties"]["semantic_definition"]
            assert definition["unknowns"] == ["超时例外待确认"]
            assert "未验收工单不能关闭" in definition["business_meaning"]
            query = dict(project_id=project_id, scope_mode="ontologies", ontology_ids=[ontology_id],
                         query=iri, search_mode="lexical", depth=0)
            context = post("/semantic/context:query", query)
            assert context["primary_matches"][0]["iri"] == iri
            assert context["primary_matches"][0]["data"]["semantic_definition"] == definition
            assert "rule_definition" not in context["primary_matches"][0]["data"]
            for model in ("entity-shape", "class-shape-generated", "class-shape-custom",
                          "owl-consistency-summary", "entity-inferred-types"):
                response = client.get(f"/api/semantic/ontologies/{graph_set}/read-models/{model}")
                assert response.status_code == 400, response.text
            response = client.get(f"/api/semantic/ontologies/{graph_set}/read-models/entity-list",
                                  params={"include": "asserted-plus-reasoning"})
            assert response.status_code == 400
            post(f"/projects/{project_id}/protection-sets", dict(name="规则保护",
                 allowed_grants=["rule-owner"], members=[{"resource_iri": iri,
                                                          "ontology_id": ontology_id}]), 201)
            with factory() as session:
                record, reader = create_reader_key(session, name="r4025-reader-" + token,
                                                  project_id=project_id, scopes=["read"])
                key_ids.append(record.id)
                reader_user = record.user_id
                assert not session.scalar(select(m.SemanticValidationRunModel.id).where(
                    or_(*(m.SemanticValidationRunModel.data_graph_iris.contains([g]) for g in graphs))))
                assert not session.scalar(select(m.SemanticReasoningRunModel.id).where(
                    or_(*(m.SemanticReasoningRunModel.model_graph_iris.contains([g]) for g in graphs))))
            with httpx.Client(base_url=client.base_url, timeout=30,
                              headers={"Authorization": "Bearer " + reader}) as limited:
                response = limited.get("/api/semantic/resources/" + iri,
                                       params={"ontology_id": graph_set})
                assert response.status_code == 404
                response = limited.post("/api/semantic/context:query", json=query)
                assert response.status_code == 200
                assert response.json()["primary_matches"] == []
                assert "未验收工单不能关闭" not in response.text
                assert limited.post("/api" + batch_path, json=request).status_code == 403
    finally:
        with factory() as session:
            if ontology_id:
                ids = list(session.scalars(select(m.SemanticGraphSetModel.id).where(
                    m.SemanticGraphSetModel.scope_type == "ontology",
                    m.SemanticGraphSetModel.scope_id == ontology_id)))
                session.execute(delete(m.SemanticGraphSetModel).where(m.SemanticGraphSetModel.id.in_(ids)))
            if project_id:
                session.execute(delete(m.ProjectModel).where(m.ProjectModel.id == project_id))
            session.execute(delete(m.ApiKeyModel).where(m.ApiKeyModel.id.in_(key_ids)))
            if reader_user:
                session.execute(delete(m.UserModel).where(m.UserModel.id == reader_user))
            for model in (m.SemanticGraphRegistryModel, m.SemanticGraphRevisionModel):
                session.execute(delete(model).where(model.graph_iri.in_(graphs)))
            session.commit()
        for iri in graphs:
            store.drop_named_graph(iri)
