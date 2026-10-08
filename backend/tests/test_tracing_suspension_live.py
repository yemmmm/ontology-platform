"""Opt-in HTTP + PostgreSQL/Oxigraph checks using isolated test resources."""

from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.repositories import models as m
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import create_api_key


TRACE_FIELDS = {
    "evidence_ids",
    "evidence_reference_ids",
    "evidence_status",
    "evidence_bindings",
    "dependency_evidence_status",
    "missing_evidence_dependencies",
    "lineage",
    "proof_level",
    "lineage_premises",
    "lineage_proof_level",
    "lineage_origin_metadata",
}


def _assert_no_trace_fields(value):
    if isinstance(value, dict):
        assert TRACE_FIELDS.isdisjoint(value), TRACE_FIELDS.intersection(value)
        for child in value.values():
            _assert_no_trace_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_trace_fields(child)


@pytest.mark.skipif(os.getenv("RUN_TRACING_SUSPENSION_LIVE") != "1", reason="opt-in live stores")
def test_live_writes_reads_and_rule_retirement_without_trace_collection():
    """Verify public contracts, SQL boundaries and real RDF results together."""
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    suffix = uuid4().hex
    project_id = ontology_id = key_id = ontology_id = key_actor = None
    graphs: set[str] = set()
    rule_definition_ids: list[str] = []
    client = None
    try:
        with factory() as session:
            key, plaintext = create_api_key(
                session, name=f"r4012-live-{suffix}", project_id=None, scopes=["admin"]
            )
            key_id = key.id
            key_actor = f"key:{key.name}"
        client = httpx.Client(
            base_url=os.getenv("TRACING_SUSPENSION_HTTP_BASE_URL", "http://127.0.0.1:8001"),
            headers={"Authorization": "Bearer " + plaintext},
            timeout=90,
        )

        def post(path, payload, status=200):
            response = client.post("/api" + path, json=payload)
            assert response.status_code == status, response.text
            return response.json()

        def get(path):
            response = client.get("/api" + path)
            assert response.status_code == 200, response.text
            return response.json()

        project = post("/projects", {"name": f"R4012 contract {suffix}"}, 201)
        project_id = project["id"]
        ontology = post(f"/projects/{project_id}/ontologies", {"name": "Contract model"}, 201)
        ontology_id = ontology["id"]
        ontology_id = ontology["workspace"]["ontology_id"]
        members = {item["role"]: item["graph_iri"] for item in ontology["workspace"]["members"]}
        graphs.update(members.values())
        retired_paths = [
            f"/projects/{project_id}/evidence-artifacts",
            f"/projects/{project_id}/evidence-references",
            f"/projects/{project_id}/evidence-associations",
            f"/ontologies/{ontology_id}/lineage",
            f"/semantic/ontologies/{ontology_id}/missing-evidence-facts",
        ]
        for retired_path in retired_paths:
            response = client.get("/api" + retired_path)
            assert response.status_code == 404, response.text
        retired_tools = {
            "create_evidence_reference",
            "list_evidence_references",
            "get_evidence_reference",
            "associate_evidence_reference",
            "get_ontology_lineage",
            "inspect_semantic_statement_provenance",
        }
        assert retired_tools.isdisjoint(tool["name"] for tool in get("/mcp/tools")["tools"])
        build = post(f"/projects/{project_id}/build-sessions", {"client_session_id": suffix}, 201)
        session_id = build["id"]
        lease = post(
            f"/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire",
            {"client_request_id": suffix, "expected_session_revision": build["revision"]},
        )
        version = get(f"/ontologies/{ontology_id}/modeling-context")["workspace"][
            "workspace_version"
        ]
        items = [
            {
                "client_item_id": "device",
                "command_kind": "create_class",
                "payload": {"class_id": suffix, "name": "Evidence inspection equipment"},
            }
        ]
        batch = {
            "client_batch_id": suffix,
            "ontology_id": ontology_id,
            "idempotency_key": f"dry-{suffix}",
            "mode": "dry_run",
            "expected_workspace_version": version,
            "items": items,
        }
        path = f"/build-sessions/{session_id}/modeling-batches"
        dry_run = post(path, batch)
        assert dry_run["attempt_status"] == "validated"
        assert "operation_plan" not in dry_run
        assert not any("evidence" in finding["code"] for finding in dry_run["findings"])
        _assert_no_trace_fields(dry_run)
        applied_request = dict(
            batch,
            mode="apply_atomic",
            idempotency_key=f"apply-{suffix}",
            lease_token=lease["lease_token"],
        )
        applied = post(path, applied_request)
        assert applied["attempt_status"] == "applied"
        replay = post(path, applied_request)
        assert replay["attempt_id"] == applied["attempt_id"]
        _assert_no_trace_fields(applied)
        assert "Evidence inspection equipment" in store.get_graph(
            members["asserted_ontology"], "turtle"
        )
        export_path = f"/api/semantic/ontologies/{ontology_id}/export"
        ordinary_export = client.get(export_path)
        assert ordinary_export.status_code == 200, ordinary_export.text
        assert "Evidence inspection equipment" in ordinary_export.text
        for retired_value in ("true", "false"):
            retired_export = client.get(export_path, params={"include_evidence": retired_value})
            assert retired_export.status_code == 422, retired_export.text
            assert retired_export.json()["detail"]["code"] == "unsupported_parameter"
        denied_export = httpx.get(client.base_url.join(export_path), timeout=15)
        assert denied_export.status_code == 401, denied_export.text
        obsolete = dict(
            batch, client_batch_id=f"obsolete-{suffix}", idempotency_key=f"old-{suffix}"
        )
        obsolete["items"] = [dict(items[0], evidence=[])]
        assert client.post("/api" + path, json=obsolete).status_code == 422

        canonical = {
            "command_kind": "create_entity",
            "ontology_id": ontology_id,
            "payload": {
                "ontology_id": ontology_id,
                "entity_id": suffix,
                "label": f"Device {suffix}",
            },

        }
        rejected = client.post(
            "/api/semantic/canonical-writes:compile-and-apply", json=dict(canonical, evidence=[])
        )
        assert rejected.status_code == 422, rejected.text
        entity_write = post("/semantic/canonical-writes:compile-and-apply", canonical)
        assert entity_write["applied"] is True
        _assert_no_trace_fields(entity_write)
        assert f"Device {suffix}" in store.get_graph(members["asserted_data"], "turtle")

        for detail in ("full", "compact"):
            context = post(
                "/semantic/context:query",
                {
                    "project_id": project_id,
                    "scope_mode": "ontologies",
                    "ontology_ids": [ontology_id],
                    "query": f"Device {suffix}",
                    "search_mode": "lexical",
                    "context_detail": detail,
                },
            )
            assert context["result_status"] == "matched"
            _assert_no_trace_fields(context)
        facts = get(
            f"/semantic/ontologies/{ontology_id}/read-models/fact-audit-queue?kind=asserted"
        )
        assert facts["items"]
        _assert_no_trace_fields(facts)

        for method, path in [("POST", "/semantic/rule-definitions"),
                             ("POST", f"/semantic/ontologies/{ontology_id}/rule-runs"),
                             ("POST", f"/semantic/ontologies/{ontology_id}/construct-runs"),
                             ("GET", "/semantic/rule-runs")]:
            response = client.request(method, "/api" + path, json={})
            assert response.status_code == 404, response.text
        reasoning = post(
            f"/semantic/ontologies/{ontology_id}/reasoning-runs",
            {
                "tasks": ["consistency"],
                "persist_result_graph": True,
            },
        )
        assert reasoning["status"] == "succeeded", reasoning.get("error")
        assert reasoning["consistent"] is True
        if reasoning["result_graph_iri"]:
            graphs.add(reasoning["result_graph_iri"])
        _assert_no_trace_fields(reasoning)
        with factory() as session:
            for model, predicate in [
                (m.EvidenceReferenceModel, m.EvidenceReferenceModel.project_id == project_id),
                (m.EvidenceAssociationModel, m.EvidenceAssociationModel.project_id == project_id),
                (m.FactEvidenceBindingModel, m.FactEvidenceBindingModel.graph_iri.in_(graphs)),
                (
                    m.SemanticStatementOccurrenceModel,
                    m.SemanticStatementOccurrenceModel.ontology_id == ontology_id,
                ),
            ]:
                assert (
                    session.scalar(select(func.count()).select_from(model).where(predicate)) == 0
                ), model.__tablename__
            assert session.scalar(
                select(func.count())
                .select_from(m.SemanticEditAuditModel)
                .where(m.SemanticEditAuditModel.actor == key_actor)
            ) > 0
    finally:
        # Discover owned identities, including requests whose response did not arrive.
        with factory() as session:
            if ontology_id:
                graphs.update(
                    session.scalars(
                        select(m.SemanticGraphRegistryModel.graph_iri).where(
                            m.SemanticGraphRegistryModel.semantic_owner_type == "ontology",
                            m.SemanticGraphRegistryModel.semantic_owner_id == ontology_id,
                        )
                    )
                )
            if ontology_id:
                for model in [
                    m.SemanticRuleRunModel,
                    m.SemanticReasoningRunModel,
                    m.SemanticValidationRunModel,
                ]:
                    rows = session.scalars(
                        select(model).where(
                            model.run_metadata["ontology_id"].as_string() == ontology_id
                        )
                    ).all()
                    for row in rows:
                        for attr in ["result_graph_iri", "rule_run_graph_iri", "report_graph_iri"]:
                            value = getattr(row, attr, None)
                            if value:
                                graphs.add(value)
                        session.delete(row)
            session.commit()
        if client:
            for definition_id in rule_definition_ids:
                response = client.delete(f"/api/semantic/rule-definitions/{definition_id}")
                assert response.status_code in (200, 204, 404), response.text
            if project_id:
                response = client.delete(f"/api/projects/{project_id}")
                assert response.status_code in (200, 204, 404), response.text
            client.close()
        with factory() as session:
            for model in [
                m.SemanticGraphStateModel,
                m.SemanticGraphRevisionModel,
                m.SemanticGraphRegistryModel,
            ]:
                session.execute(delete(model).where(model.graph_iri.in_(graphs)))
            if ontology_id:
                session.execute(
                    delete(m.SemanticGraphSetModel).where(
                        m.SemanticGraphSetModel.id == ontology_id
                    )
                )
            if key_id:
                session.execute(
                    delete(m.SemanticEditAuditModel).where(
                        m.SemanticEditAuditModel.actor == key_actor
                    )
                )
                session.execute(delete(m.ApiKeyModel).where(m.ApiKeyModel.id == key_id))
            session.commit()
            if key_actor:
                assert session.scalar(
                    select(func.count())
                    .select_from(m.SemanticEditAuditModel)
                    .where(m.SemanticEditAuditModel.actor == key_actor)
                ) == 0
        for graph in graphs:
            store.drop_named_graph(graph)
