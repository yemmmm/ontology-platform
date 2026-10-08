"""Opt-in public HTTP mapping contracts using only owned fixture resources."""

import os
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import Settings
from app.repositories import models as m
from app.repositories.postgres import create_session_factory
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import create_api_key
from app.services.semantic_export import namespace_from_settings


@pytest.mark.skipif(
    os.getenv("RUN_RELATIONAL_MAPPING_HTTP") != "1", reason="opt-in restarted HTTP app"
)
def test_public_four_kind_write_receipt_exact_read_context_and_export():
    settings = Settings()
    factory = create_session_factory(settings)
    store = RdfStoreRepository(settings.oxigraph_url)
    ns = namespace_from_settings(settings)
    token = uuid4().hex
    project_id = ontology_id = key_id = None
    graphs, graph_sets = [], []
    try:
        with factory() as session:
            record, key = create_api_key(
                session,
                name=f"r4010-http-{token}",
                project_id=None,
                scopes=["admin"],
                bootstrap=True,
            )
            key_id = record.id
        with httpx.Client(
            base_url=os.getenv("RELATIONAL_MAPPING_HTTP_BASE_URL", "http://127.0.0.1:8001"),
            headers={"Authorization": "Bearer " + key},
            timeout=60,
        ) as client:

            def post(path, value, status=200):
                response = client.post("/api" + path, json=value)
                assert response.status_code == status, response.text
                return response.json()

            def get(path, params=None):
                response = client.get("/api" + path, params=params)
                assert response.status_code == 200, response.text
                return response.json()

            project_id = post("/projects", {"name": f"R4010 HTTP {token}"}, 201)["id"]
            ontology = post(f"/projects/{project_id}/ontologies", {"name": "Fixture mappings"}, 201)
            ontology_id = ontology["id"]
            graph_set = ontology["workspace"]["ontology_id"]
            graph_sets.append(graph_set)
            graphs.extend(member["graph_iri"] for member in ontology["workspace"]["members"])
            build = post(
                f"/projects/{project_id}/build-sessions", {"client_session_id": token}, 201
            )
            lease = post(
                f"/build-sessions/{build['id']}/ontology-leases/{ontology_id}:acquire",
                {"client_request_id": token, "expected_session_revision": 1},
            )
            ids = {
                name: f"{token}-{name}"
                for name in (
                    "object",
                    "key",
                    "time",
                    "relation",
                    "left",
                    "right",
                    "join",
                    "enum-left",
                    "enum-right",
                    "metric",
                )
            }

            def uri(kind, name):
                return str(ns.resource(kind, ids[name]))

            annotation = {
                "semantic_role": "data_mapping",
                "business_meaning": "Fixture interpretation",
                "unknowns": ["object identity and cardinality unconfirmed"],
            }
            items = [
                {
                    "client_item_id": "object",
                    "command_kind": "create_entity",
                    "payload": {
                        "entity_id": ids["object"],
                        "label": "Fixture shared definition",
                        "semantic_definition": {
                            "semantic_role": "object",
                            "business_meaning": "Shared fixture object",
                        },
                    },
                },
                *[
                    {
                        "client_item_id": name,
                        "command_kind": "create_property",
                        "payload": {"property_id": ids[name], "name": name, "datatype": datatype},
                    }
                    for name, datatype in (("key", "string"), ("time", "dateTime"))
                ],
                {
                    "client_item_id": "relation",
                    "command_kind": "create_relation_type",
                    "payload": {"relation_type_id": ids["relation"], "name": "Fixture association"},
                },
            ]
            for name in ("left", "right"):
                items.append(
                    {
                        "client_item_id": name,
                        "command_kind": "create_table_mapping",
                        "payload": {
                            "table_mapping_id": ids[name],
                            "name": f"Fixture {name}",
                            "mapped_definition_iri": uri("entity", "object"),
                            "table_name": "records",
                            "column_mappings": [
                                {"column": "id", "property_iri": uri("property", "key")},
                                {"column": "at", "property_iri": uri("property", "time")},
                                {"column": "technical_join"},
                            ],
                            "schema_source": "isolated fixture schema",
                            "mapping_definition": {
                                "source_key": name,
                                "row_grain": "one fixture record",
                                "object_key_columns": None,
                                "record_key_columns": ["id"],
                            },
                            "semantic_definition": annotation,
                        },
                    }
                )
                items.append(
                    {
                        "client_item_id": "enum-" + name,
                        "command_kind": "create_enum_meaning",
                        "payload": {
                            "enum_meaning_id": ids["enum-" + name],
                            "name": "Fixture code " + name,
                            "property_iri": uri("property", "key"),
                            "enum_value": "A",
                            "business_meaning": "source-specific meaning " + name,
                            "table_mapping_iri": uri("table-mapping", name),
                            "column": "id",
                            "schema_source": "isolated fixture schema",
                            "semantic_definition": annotation,
                            "mapping_definition": {"conversion_rule_iri": None},
                        },
                    }
                )
            items.append(
                {
                    "client_item_id": "join",
                    "command_kind": "create_join_mapping",
                    "payload": {
                        "join_mapping_id": ids["join"],
                        "name": "Fixture explicit association",
                        "relation_type_iri": uri("relation-type", "relation"),
                        "join_direction": "forward",
                        "join_path": [
                            {
                                "from_mapping_iri": uri("table-mapping", "left"),
                                "to_mapping_iri": uri("table-mapping", "right"),
                                "from_role": "base",
                                "to_role": "detail",
                                "from_columns": ["technical_join"],
                                "to_columns": ["technical_join"],
                            }
                        ],
                        "schema_source": "isolated fixture schema",
                        "semantic_definition": annotation,
                        "mapping_definition": {"duplicate_risk": "unconfirmed"},
                    },
                }
            )
            items.append(
                {
                    "client_item_id": "metric",
                    "command_kind": "create_metric_definition",
                    "payload": {
                        "metric_id": ids["metric"],
                        "name": "Fixture count with unknown identity",
                        "grain": [uri("property", "key")],
                        "time_field": uri("property", "time"),
                        "aggregation": "count",
                        "null_value_rule": "unknown",
                        "denominator_rule": "not applicable",
                        "filters": [],
                        "schema_source": "isolated fixture schema",
                        "semantic_definition": annotation,
                        "mapping_definition": {
                            "contexts": [
                                {
                                    "context_key": "selected",
                                    "base_mapping_iri": uri("table-mapping", "left"),
                                    "base_role": "base",
                                    "join_mapping_iris": [uri("join-mapping", "join")],
                                    "property_bindings": [
                                        {
                                            "property_iri": uri("property", "time"),
                                            "table_mapping_iri": uri("table-mapping", "left"),
                                            "role": "base",
                                            "column": "at",
                                        }
                                    ],
                                    "counted_identity": None,
                                    "duplicate_handling": None,
                                    "conversion_rule_iris": [],
                                }
                            ]
                        },
                    },
                }
            )
            version = get(f"/ontologies/{ontology_id}/modeling-context")["workspace"][
                "workspace_version"
            ]
            request = {
                "client_batch_id": token,
                "ontology_id": ontology_id,
                "mode": "dry_run",
                "idempotency_key": "dry-" + token,
                "expected_workspace_version": version,
                "items": items,
            }
            path = f"/build-sessions/{build['id']}/modeling-batches"
            checked = post(path, request)
            assert checked["attempt_status"] == "validated", json.dumps(checked["findings"])
            applied_request = dict(
                request,
                mode="apply_atomic",
                idempotency_key="apply-" + token,
                lease_token=lease["lease_token"],
            )
            applied = post(path, applied_request)
            assert applied["attempt_status"] == "applied", applied["findings"]
            assert post(path, applied_request)["attempt_id"] == applied["attempt_id"]
            resources = {
                entry["client_item_id"]: entry["resource_outputs"]["resource_iri"]
                for entry in applied["items"]
            }
            ordinary = get(
                "/semantic/resources/" + resources["object"], {"ontology_id": graph_set}
            )
            assert ordinary["properties"]["semantic_definition"]["semantic_role"] == "object"
            entity_list = get(f"/semantic/ontologies/{graph_set}/read-models/entity-list")
            assert resources["object"] in {row["iri"] for row in entity_list["items"]}
            assert not {
                resources[name]
                for name in ("left", "right", "join", "enum-left", "enum-right", "metric")
            } & {row["iri"] for row in entity_list["items"]}
            exact_reads = []
            for key_name, model in (
                ("left", "table-mapping"),
                ("join", "join-mapping"),
                ("enum-left", "enum-meaning"),
                ("metric", "metric"),
            ):
                exact = get(
                    "/semantic/resources/" + resources[key_name], {"ontology_id": graph_set}
                )
                assert exact["properties"]["semantic_definition"] == annotation
                assert isinstance(exact["properties"]["mapping_definition"], dict)
                exact_reads.append(exact)
                detail = get(
                    f"/semantic/ontologies/{graph_set}/read-models/{model}-detail",
                    {"entity": resources[key_name], "field_set": "detail"},
                )
                assert detail["items"][0]["iri"] == resources[key_name]
            from modeling_team.tests.test_r4010_mapping_contract import _active_protocol_facade

            facade = _active_protocol_facade()
            existing_candidate = {
                "candidate_kind": "platform-neutral-candidate-v3",
                "candidate_revision": 1,
                "scope": "fixture-existing-mappings",
                "constraints": [],
                "items": [
                    {
                        "item_id": "link-type",
                        "item_kind": "predicate",
                        "semantic": {
                            "predicate": token + "-link",
                            "predicate_kind": "relation",
                        },
                    },
                    *[
                        {
                            "item_id": "link-" + kind,
                            "item_kind": "relation",
                            "semantic": {
                                "predicate": token + "-link",
                                "subject": {
                                    "existing_resource_ref": {
                                        "semantic_id": ids["left"],
                                        "resource_kind": "table_mapping",
                                    }
                                },
                                "object": {
                                    "existing_resource_ref": {
                                        "semantic_id": ids[name],
                                        "resource_kind": kind,
                                    }
                                },
                            },
                        }
                        for name, kind in (
                            ("join", "join_mapping"),
                            ("enum-left", "enum_meaning"),
                            ("metric", "metric"),
                        )
                    ],
                ],
            }
            scope_context = get(f"/ontologies/{ontology_id}/modeling-context")
            scope = dict(
                project_id=project_id,
                ontology_id=ontology_id,
                workspace_version=scope_context["workspace"]["workspace_version"],
            )
            bound = facade.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": facade.RESOURCE_BINDING_RECEIPT_TOOL_NAME,
                        "arguments": {
                            "candidate": existing_candidate,
                            "read_envelope": {"items": exact_reads},
                            "scope": scope,
                        },
                    },
                }
            )
            assert "error" not in bound, bound
            receipt = bound["result"]["structuredContent"]
            assert len(receipt["bindings"]) == 4
            translated = facade.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": facade.TRANSLATE_CANDIDATE_TOOL_NAME,
                        "arguments": {
                            "candidate": existing_candidate,
                            "requirement_id": "R4.0-010",
                            "existing_binding_receipt": receipt,
                            "semantic_base_iri": scope_context["semantic_base_iri"],
                        },
                    },
                }
            )
            assert "error" not in translated, translated
            assert not translated["result"]["structuredContent"]["conflicts"]
            for mode in ("full", "compact"):
                context = post(
                    "/semantic/context:query",
                    {
                        "project_id": project_id,
                        "scope_mode": "ontologies",
                        "ontology_ids": [ontology_id],
                        "query": "Fixture explicit association",
                        "search_mode": "lexical",
                        "context_detail": mode,
                        "depth": 2,
                    },
                )
                assert context["result_status"] == "matched", context
            response = client.get(f"/api/semantic/ontologies/{graph_set}/export")
            assert response.status_code == 200, response.text
            assert "mappingDefinition" in response.text
            assert "Fixture shared definition" in response.text
    finally:
        with factory() as session:
            if ontology_id:
                graph_sets = list(
                    session.scalars(
                        select(m.SemanticGraphSetModel.id).where(
                            m.SemanticGraphSetModel.scope_type == "ontology",
                            m.SemanticGraphSetModel.scope_id == ontology_id,
                        )
                    )
                )
                session.execute(
                    delete(m.SemanticGraphSetModel).where(
                        m.SemanticGraphSetModel.id.in_(graph_sets)
                    )
                )
            if project_id:
                session.execute(delete(m.ProjectModel).where(m.ProjectModel.id == project_id))
            if key_id:
                session.execute(delete(m.ApiKeyModel).where(m.ApiKeyModel.id == key_id))
            for model in (m.SemanticGraphRegistryModel, m.SemanticGraphRevisionModel):
                session.execute(delete(model).where(model.graph_iri.in_(graphs)))
            session.commit()
        for iri in graphs:
            store.drop_named_graph(iri)
