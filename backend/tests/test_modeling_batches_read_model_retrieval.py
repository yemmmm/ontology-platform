"""Public Ontology read-model search uses the shared scoped recall contract."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.modeling_batches import router
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.services.ontology_workspace import OntologyWorkspaceService


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.bindings = rows


class _Store:
    def query_read_model(self, query, graph_iris, timeout_seconds, limit):  # noqa: ARG002
        if "# template: entity-list" in query:
            return _Result([])
        if "# template: statement-list" in query:
            return _Result(
                [
                    {
                        "subject": {"type": "uri", "value": "https://example.test/WorkflowB"},
                        "predicate": {"type": "uri", "value": "https://example.test/hasContract"},
                        "object": {"type": "uri", "value": "https://example.test/ContractV2"},
                        "graph": {"type": "uri", "value": graph_iris[0]},
                    }
                ]
            )
        if "# template: schema-summary" in query:
            # The q adapter must discard these non-matching topology rows.
            return _Result(
                [
                    {
                        "class": "https://example.test/Unrelated",
                        "label": "未匹配类",
                        "graph": graph_iris[0],
                    },
                    {
                        "class": "https://example.test/Other",
                        "label": "另一个类",
                        "graph": graph_iris[0],
                    },
                ]
            )
        return _Result([])


def _seed_ready_workspace(session: Session, settings: Settings) -> str:
    session.add(ProjectModel(id="project-public-search", name="Public", normalized_label="public"))
    ontology = OntologyModel(
        id="ontology-public-search",
        project_id="project-public-search",
        name="Public search",
    )
    session.add(ontology)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.commit()
    return ontology.id


def _client(session: Session, settings: Settings) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = _Store
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_public_entity_and_class_read_models_filter_q_and_merge_scoped_recall(
    in_memory_session, monkeypatch
) -> None:
    settings = Settings(semantic_graph_iri_prefix="https://public-search.test/graphs")
    ontology_id = _seed_ready_workspace(in_memory_session, settings)

    def recall_graph_set(_self, *, resource_kinds, **_kwargs):
        if resource_kinds == {"instance"}:
            return {
                "candidates": [
                    {
                        "id": "https://example.test/CustomerSupportWorkflowInstance",
                        "kind": "instance",
                        "ontology_id": ontology_id,
                        "iri": "https://example.test/CustomerSupportWorkflowInstance",
                        "label": "Customer Support Workflow Instance",
                        "labels": [
                            {
                                "predicate": "http://www.w3.org/2000/01/rdf-schema#label",
                                "value": "Customer Support Workflow Instance",
                                "language": "en",
                            },
                            {
                                "predicate": "http://www.w3.org/2000/01/rdf-schema#label",
                                "value": "客户支持工作流实例",
                                "language": "zh",
                            },
                        ],
                        "aliases": [],
                        "description": None,
                        "data": {"rdf_types": ["https://example.test/Workflow"]},
                        "assertion_kind": "asserted",
                        "match": {
                            "score": 820,
                            "lexical_score": 0,
                            "semantic_similarity": 0.82,
                            "reasons": ["semantic_candidate"],
                            "candidate_level": "semantic_candidate",
                        },
                    }
                ],
                "indexes": [{"ontology_id": ontology_id, "status": "current"}],
                "warnings": [],
                "completeness": "complete",
            }
        return {
            "candidates": [
                {
                    "id": "https://example.test/CustomerSupportWorkflow",
                    "kind": "concept",
                    "ontology_id": ontology_id,
                    "iri": "https://example.test/CustomerSupportWorkflow",
                    "label": "Customer Support Workflow",
                    "labels": [
                        {
                            "predicate": "http://www.w3.org/2000/01/rdf-schema#label",
                            "value": "Customer Support Workflow",
                            "language": "en",
                        },
                        {
                            "predicate": "http://www.w3.org/2000/01/rdf-schema#label",
                            "value": "客户支持工作流",
                            "language": "zh",
                        },
                    ],
                    "aliases": [],
                    "description": None,
                    "data": {"rdf_types": []},
                    "assertion_kind": "asserted",
                    "match": {
                        "score": 637,
                        "lexical_score": 0,
                        "semantic_similarity": 0.637,
                        "reasons": ["semantic_candidate"],
                        "candidate_level": "semantic_candidate",
                    },
                }
            ],
            "indexes": [{"ontology_id": ontology_id, "status": "current"}],
            "warnings": [],
            "completeness": "complete",
        }

    monkeypatch.setattr(
        "app.api.modeling_batches.SemanticResourceRetrievalService.recall_graph_set",
        recall_graph_set,
    )
    client = _client(in_memory_session, settings)

    entities = client.get(
        f"/api/ontologies/{ontology_id}/semantic-read-models/entities",
        params={"q": "客户支持工作流实例"},
    )
    assert entities.status_code == 200, entities.text
    entity_body = entities.json()
    assert entity_body["model_name"] == "entity-list"
    assert entity_body["recall"]["match_status"] == "exact"
    assert [item["iri"] for item in entity_body["items"]] == [
        "https://example.test/CustomerSupportWorkflowInstance"
    ]
    assert entity_body["items"][0]["class_iri"] == "https://example.test/Workflow"
    assert entity_body["items"][0]["label"] == "客户支持工作流实例"

    classes = client.get(
        f"/api/ontologies/{ontology_id}/semantic-read-models/classes",
        params={"q": "客户支持工作流"},
    )
    assert classes.status_code == 200, classes.text
    class_body = classes.json()
    assert class_body["model_name"] == "ontology-schema-summary"
    assert class_body["recall"]["match_status"] == "exact"
    assert [item["iri"] for item in class_body["items"]] == [
        "https://example.test/CustomerSupportWorkflow"
    ]
    assert class_body["items"][0]["label"] == "客户支持工作流"


def test_public_ontology_facts_read_model_preserves_statement_bindings(in_memory_session) -> None:
    settings = Settings(semantic_graph_iri_prefix="https://public-search.test/graphs")
    ontology_id = _seed_ready_workspace(in_memory_session, settings)

    response = _client(in_memory_session, settings).get(
        f"/api/ontologies/{ontology_id}/semantic-read-models/facts"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model_name"] == "statement-list"
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["subject"] == "https://example.test/WorkflowB"
    assert item["predicate"] == "https://example.test/hasContract"
    assert item["object"] == "https://example.test/ContractV2"
    assert item["object_kind"] == "iri"
