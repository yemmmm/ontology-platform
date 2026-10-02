"""Opt-in isolated PostgreSQL/Oxigraph/API roundtrip; never invokes business APIs."""

import json
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
from modeling_team.protocol_mechanics import (
    translate_candidate_to_batches,
    build_unified_resource_binding_receipt,
)
from modeling_team.tests.test_r4011_api_mapping_contract import (
    candidate,
    unified_candidate,
    unified_plan,
)
from subject_access_support import create_api_key as create_reader_key


@pytest.mark.skipif(
    os.getenv("RUN_API_MAPPING_HTTP") != "1", reason="opt-in real isolated API graph"
)
@pytest.mark.parametrize("form", ["neutral", "unified"])
def test_api_mapping_batch_read_revision_context_and_protection(form):
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    token = uuid4().hex
    project_id = ontology_id = reader_user = None
    graphs = []
    key_ids = []
    try:
        with factory() as session:
            record, key = create_api_key(
                session, name="r4011-" + token, project_id=None, scopes=["admin"], bootstrap=True
            )
            key_ids.append(record.id)
        with httpx.Client(
            base_url=os.getenv("API_MAPPING_HTTP_BASE_URL", "http://127.0.0.1:8001"),
            headers={"Authorization": "Bearer " + key},
            timeout=120,
        ) as client:

            def post(path, value, status=200):
                response = client.post("/api" + path, json=value)
                assert response.status_code == status, response.text
                return response.json()

            def get(path, params=None):
                response = client.get("/api" + path, params=params)
                assert response.status_code == 200, response.text
                return response.json()

            project_id = post("/projects", {"name": "R4011 " + token}, 201)["id"]
            ontology = post(
                f"/projects/{project_id}/ontologies", {"name": "Catalog API fixture"}, 201
            )
            ontology_id = ontology["id"]
            graph_set = ontology["workspace"]["default_graph_set_id"]
            graphs.extend(member["graph_iri"] for member in ontology["workspace"]["members"])
            build = post(
                f"/projects/{project_id}/build-sessions", {"client_session_id": token}, 201
            )
            lease = post(
                f"/build-sessions/{build['id']}/ontology-leases/{ontology_id}:acquire",
                {"client_request_id": token, "expected_session_revision": 1},
            )
            scope = get(f"/ontologies/{ontology_id}/modeling-context")
            base = scope["semantic_base_iri"]
            value = candidate() if form == "neutral" else unified_candidate()
            # Fixture-local IDs remain unique even in a global semantic namespace.
            if form == "neutral":
                for row in value["items"]:
                    semantic = row["semantic"]
                    for field in (
                        "entity_id",
                        "class_id",
                        "operation_id",
                        "table_mapping_id",
                        "enum_meaning_id",
                    ):
                        if field in semantic:
                            semantic[field] = token + "-" + semantic[field]
                    if row["item_kind"] == "predicate":
                        semantic["predicate"] = token + "-" + semantic["predicate"]
                    if row["item_kind"] == "relation":
                        semantic["predicate"] = token + "-" + semantic["predicate"]
                    if "target_class" in semantic:
                        semantic["target_class"] = token + "-" + semantic["target_class"]
                plan = translate_candidate_to_batches(value, semantic_base_iri=base)
            else:
                for row in value["items"]:
                    semantic = row["value"]
                    for field in ("entity_id", "table_mapping_id", "enum_meaning_id"):
                        if field in semantic:
                            semantic[field] = token + "-" + semantic[field]
                    if "predicate" in semantic:
                        semantic["predicate"] = token + "-" + semantic["predicate"]
                plan = unified_plan(value, semantic_base_iri=base)
            assert not plan["conflicts"]
            path = f"/build-sessions/{build['id']}/modeling-batches"
            receipts = {}

            def apply(items, batch_id):
                version = get(f"/ontologies/{ontology_id}/modeling-context")["workspace"][
                    "workspace_version"
                ]
                request = dict(
                    client_batch_id=batch_id,
                    ontology_id=ontology_id,
                    mode="dry_run",
                    idempotency_key="dry-" + batch_id,
                    expected_workspace_version=version,
                    items=items,
                )
                checked = post(path, request)
                assert checked["attempt_status"] == "validated", json.dumps(checked["findings"])
                request.update(
                    mode="apply_atomic",
                    idempotency_key="apply-" + batch_id,
                    lease_token=lease["lease_token"],
                )
                applied = post(path, request)
                assert applied["attempt_status"] == "applied", json.dumps(applied["findings"])
                assert post(path, request)["attempt_id"] == applied["attempt_id"]
                return applied

            for ordinal, batch in enumerate(plan["batches"]):
                applied = apply(batch["items"], token + "-" + str(ordinal))
                receipts.update(
                    {
                        i["client_item_id"]: i["resource_outputs"]["resource_iri"]
                        for i in applied["items"]
                        if "resource_iri" in i["resource_outputs"]
                    }
                )

            def exact(name):
                return get("/semantic/resources/" + receipts[name], {"graph_set_id": graph_set})

            assert (
                exact("query-a")["properties"]["semantic_definition"]["semantic_role"]
                == "interface_mapping"
            )
            for name in ("path-id", "body-id", "query-id", "nested-id", "item-id", "task-id"):
                assert exact(name)["properties"]["parameter_definition"]["cardinality"] == "single"
            assert (
                len(
                    {
                        receipts[n]
                        for n in (
                            "path-id",
                            "body-id",
                            "query-id",
                            "nested-id",
                            "item-id",
                            "task-id",
                        )
                    }
                )
                == 6
            )
            assert exact("no-body")["properties"]["semantic_definition"][
                "business_meaning"
            ].startswith("204")
            assert (
                "not a catalog object"
                in exact("accepted")["properties"]["semantic_definition"]["business_meaning"]
            )
            assert exact("conversion")["properties"]["semantic_definition"]["conflicting_meanings"]
            assert (
                "API ID and database key"
                in exact("composite-id")["properties"]["semantic_definition"]["unknowns"][0]
            )
            if form == "neutral":
                operation_context = post(
                    "/semantic/context:query",
                    dict(
                        project_id=project_id,
                        scope_mode="ontologies",
                        ontology_ids=[ontology_id],
                        query=receipts["reserve-operation"],
                        resource_types=["operation"],
                        search_mode="lexical",
                        depth=0,
                    ),
                )
                operation = operation_context["primary_matches"][0]["data"]
                assert [b["binding_id"] for b in operation["tool_bindings"]] == [
                    "reserve-v1",
                    "reserve-v2",
                ]
                assert operation["tool_bindings"][1]["version"] == "v2"

            if form == "neutral":
                existing_refs = dict(
                    candidate_kind="platform-neutral-candidate-v3",
                    candidate_revision=1,
                    scope="API reused resources",
                    constraints=[],
                    items=[
                        dict(
                            item_id="existing-" + kind,
                            item_kind="existing_resource_ref",
                            semantic=dict(semantic_id=token + "-" + name, resource_kind=kind),
                        )
                        for kind, name in (
                            ("operation", "reserve-operation"),
                            ("table_mapping", "catalog-table"),
                        )
                    ],
                )
                current_scope = get(f"/ontologies/{ontology_id}/modeling-context")
                receipt = build_unified_resource_binding_receipt(
                    existing_refs,
                    {"items": [exact("reserve-operation"), exact("catalog-table")]},
                    project_id=project_id,
                    ontology_id=ontology_id,
                    workspace_version=current_scope["workspace"]["workspace_version"],
                )
                assert {r["resource_kind"] for r in receipt["bindings"]} == {
                    "operation",
                    "table_mapping",
                }
                reused = translate_candidate_to_batches(
                    existing_refs,
                    existing_binding_receipt=receipt,
                    requirement_id="R4.0-010",
                    semantic_base_iri=base,
                )
                assert not reused["conflicts"]
                assert reused["batches"] == []  # references are not recreated entities

            for detail in ("full", "compact"):
                context = post(
                    "/semantic/context:query",
                    dict(
                        project_id=project_id,
                        scope_mode="ontologies",
                        ontology_ids=[ontology_id],
                        query=receipts["query-a"],
                        search_mode="lexical",
                        semantic_roles=["interface_mapping"],
                        context_detail=detail,
                        depth=3,
                        context_limit=2,
                    ),
                )
                assert context["result_status"] == "matched", context
                assert context["primary_matches"][0]["iri"] == receipts["query-a"]
                assert len(context["related_context"]) <= 2
                # Returned bounded context must disclose completeness/pagination.
                assert context["recall"]["completeness"] == "complete"
                assert context["context_page"]["next_context_cursor"]
                assert context["truncated"]
            export = client.get(f"/api/semantic/graph-sets/{graph_set}/export")
            assert export.status_code == 200, export.text
            assert "202 means accepted" in export.text
            assert receipts["path-id"] in export.text
            # Compatible field rename keeps resource/parameter identities and no accidental duplicate.
            apply(
                [
                    dict(
                        client_item_id="rename",
                        command_kind="update_entity",
                        payload={
                            "entity_iri": receipts["path-id"],
                            "properties": {token + "-memberName": "item_key"},
                        },
                    )
                ],
                token + "-rename",
            )
            assert exact("path-id")["iri"] == receipts["path-id"]
            assert receipts["original"] != receipts["replacement"]
            statements = get("/semantic/statements", {"graph_set_id": graph_set, "limit": 1000})
            assert any(
                r.get("subject") == receipts["path-id"] and r.get("object") == "item_key"
                for r in statements["items"]
            ), statements

            # Ordinary reference revision uses exact endpoints and can be repaired in the same session.
            edge_payload = dict(
                source_entity_iri=receipts["map-call-replacement"],
                relation_type_iri=base.rstrip("/") + "/property/" + token + "-forField",
                target_entity_iri=receipts["body-id"],
            )
            for action in ("delete_relation", "create_relation"):
                apply(
                    [dict(client_item_id=action, command_kind=action, payload=edge_payload)],
                    token + "-" + action,
                )
                current = get("/semantic/statements", {"graph_set_id": graph_set, "limit": 5000})
                present = any(
                    r.get("subject") == edge_payload["source_entity_iri"]
                    and r.get("predicate") == edge_payload["relation_type_iri"]
                    and r.get("object") == edge_payload["target_entity_iri"]
                    for r in current["items"]
                )
                assert present == (action == "create_relation")

            # Real server identity resolver, current protection set, and reader without its grant.
            hidden = [receipts[n] for n in ("path-id", "lookup-rule", "map-call-original")]
            post(
                f"/projects/{project_id}/protection-sets",
                dict(
                    name="Restricted mapping",
                    allowed_grants=["fixture-sensitive"],
                    members=[{"resource_iri": iri, "ontology_id": ontology_id} for iri in hidden],
                ),
                201,
            )
            with factory() as session:
                record, reader = create_reader_key(
                    session, name="r4011-reader-" + token, project_id=project_id, scopes=["read"]
                )
                key_ids.append(record.id)
                reader_user = record.user_id
            with httpx.Client(
                base_url=client.base_url, headers={"Authorization": "Bearer " + reader}, timeout=120
            ) as limited:
                missing = base.rstrip("/") + "/entity/" + token + "-missing"
                # Hidden and absent resources share the existing 404 contract.
                missing_read = limited.get(
                    "/api/semantic/resources/" + missing, params={"graph_set_id": graph_set}
                )
                assert missing_read.status_code == 404
                for iri in hidden:
                    read = limited.get(
                        "/api/semantic/resources/" + iri, params={"graph_set_id": graph_set}
                    )
                    assert read.status_code == 404
                    assert read.json() == {"detail": f"Resource not found: {iri}"}
                list_path = f"/api/semantic/graph-sets/{graph_set}/read-models/entity-list"
                all_visible = limited.get(list_path, params={"limit": 1000})
                first_page = limited.get(list_path, params={"limit": 1})
                assert all_visible.status_code == first_page.status_code == 200
                assert first_page.json()["items"] == all_visible.json()["items"][:1]
                assert first_page.json()["paging"]["visible_count"] == len(
                    all_visible.json()["items"]
                )
                assert all(iri not in all_visible.text for iri in hidden)
                response = limited.get(f"/api/semantic/graph-sets/{graph_set}/export")
                assert response.status_code == 200, response.text
                assert all(iri not in response.text for iri in hidden)
                context = limited.post(
                    "/api/semantic/context:query",
                    json=dict(
                        project_id=project_id,
                        scope_mode="ontologies",
                        ontology_ids=[ontology_id],
                        query=receipts["map-call-original"],
                        search_mode="lexical",
                        depth=3,
                    ),
                )
                assert context.status_code == 200, context.text
                assert all(
                    iri not in context.text
                    for iri in hidden
                    if iri != receipts["map-call-original"]
                )
                assert context.json()["primary_matches"] == []
    finally:
        with factory() as session:
            if ontology_id:
                sets = list(
                    session.scalars(
                        select(m.SemanticGraphSetModel.id).where(
                            m.SemanticGraphSetModel.scope_type == "ontology",
                            m.SemanticGraphSetModel.scope_id == ontology_id,
                        )
                    )
                )
                session.execute(
                    delete(m.SemanticGraphSetModel).where(m.SemanticGraphSetModel.id.in_(sets))
                )
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
