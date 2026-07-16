from __future__ import annotations

import json
from typing import Any

import pytest
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDFS

from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import SparqlResult
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_context_query import (
    SemanticContextQueryService,
    normalize_query_text,
)
from app.services.semantic_query_scope import (
    SemanticQueryScopeNotFound,
    SemanticQueryScopeNotReady,
    SemanticQueryScopeResolver,
)


pytestmark = pytest.mark.filterwarnings(
    "ignore:Dataset\\.(default_context|contexts) is deprecated:DeprecationWarning"
)


def _binding(value: str, kind: str = "uri") -> dict[str, str]:
    return {"type": kind, "value": value}


class FakeStore:
    def __init__(self, candidates: list[dict[str, Any]], neighbors=None) -> None:
        self.candidates = candidates
        self.neighbors = neighbors or []
        self.queries: list[str] = []

    def query_sparql(self, query, timeout_seconds, limit):
        self.queries.append(query)
        rows = self.neighbors if "semantic-context-neighborhood" in query else self.candidates
        return SparqlResult(
            result={"head": {"vars": []}, "results": {"bindings": rows}},
            truncated=False,
        )


class DatasetStore:
    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset

    def query_sparql(self, query, timeout_seconds, limit):
        result = self.dataset.query(query)
        return SparqlResult(result=json.loads(result.serialize(format="json")))


class FakeLineage:
    def get_lineage(self, **kwargs):
        return {
            "lineage_status": "complete",
            "evidence_status": "supported",
            "dependency_evidence_status": "supported",
            "items": [
                {
                    "supporting_context": {
                        "evidence_references": [
                            {
                                "id": "evidence-1",
                                "excerpt": "must never leave the lineage boundary",
                                "document_name": "secret.txt",
                            }
                        ],
                        "rationales": [{"text": "private rationale"}],
                    }
                }
            ],
            "warnings": [],
        }


class FakeShapes:
    def read_merged_guidance(self, graph_set_id, class_iri):
        return {
            "graph_set_id": graph_set_id,
            "generated_graph_iri": "https://secret.test/shapes",
            "fields": [
                {
                    "path": "https://example.test/datasetId",
                    "label": "数据集参数",
                    "datatype": "http://www.w3.org/2001/XMLSchema#string",
                    "min_count": 1,
                    "required": True,
                    "provenance": "generated",
                }
            ],
        }


def _ready_ontology(session, settings, project_id="project-1", ontology_id="ontology-1"):
    if session.get(ProjectModel, project_id) is None:
        session.add(ProjectModel(id=project_id, name=project_id, normalized_label=project_id))
    ontology = OntologyModel(
        id=ontology_id,
        project_id=project_id,
        name=ontology_id,
    )
    session.add(ontology)
    session.flush()
    OntologyWorkspaceService(session, settings).ensure(ontology)
    session.commit()
    return ontology


def _candidate_rows(settings: Settings, ontology_id: str) -> list[dict[str, Any]]:
    graph = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/{ontology_id}"
    workflow = "https://example.test/Workflow"
    return [
        {
            "graph": _binding(graph),
            "subject": _binding(workflow),
            "predicate": _binding("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            "object": _binding("http://www.w3.org/2002/07/owl#Class"),
            "subjectLabel": _binding("发布工作流", "literal"),
            "aliases": _binding("PublishWorkflow", "literal"),
            "description": _binding("用于发布业务流程", "literal"),
            "subjectTypes": _binding("http://www.w3.org/2002/07/owl#Class", "literal"),
        },
        {
            "graph": _binding(graph),
            "subject": _binding(workflow),
            "predicate": _binding("https://example.test/requiresParameter"),
            "object": {
                "type": "literal",
                "value": "datasetId",
                "datatype": "http://www.w3.org/2001/XMLSchema#string",
            },
            "subjectLabel": _binding("发布工作流", "literal"),
            "predicateLabel": _binding("需要参数", "literal"),
            "subjectTypes": _binding("http://www.w3.org/2002/07/owl#Class", "literal"),
        },
        {
            "graph": _binding(graph),
            "subject": _binding(workflow),
            "predicate": _binding("https://example.test/note"),
            "object": {"type": "literal", "value": "发布说明", "xml:lang": "zh"},
            "subjectLabel": _binding("发布工作流", "literal"),
            "predicateLabel": _binding("说明", "literal"),
            "subjectTypes": _binding("http://www.w3.org/2002/07/owl#Class", "literal"),
        },
    ]


def test_unified_query_returns_primary_related_and_only_evidence_ids(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    rows = _candidate_rows(settings, "ontology-1")
    store = FakeStore(rows[:1], neighbors=rows[1:])
    service = SemanticContextQueryService(
        in_memory_session,
        store,
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    )

    result = service.query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        query="发布工作流需要哪些参数",
        depth=1,
        limit=20,
    )

    assert result["result_status"] == "matched"
    assert result["primary_matches"][0]["kind"] == "concept"
    assert result["related_context"][0]["match"]["reasons"] == ["shape_constraint"]
    assert result["related_context"][0]["data"]["constraint"]["required"] is True
    facts = [item for item in result["related_context"] if item["data"].get("object")]
    assert next(item for item in facts if item["data"]["object"] == "datasetId")["data"][
        "object_datatype"
    ].endswith("#string")
    assert next(item for item in facts if item["data"]["object"] == "发布说明")["data"][
        "object_language"
    ] == "zh"
    assert result["primary_matches"][0]["evidence_reference_ids"] == ["evidence-1"]
    serialized = str(result)
    assert "must never leave" not in serialized
    assert "secret.txt" not in serialized
    assert "private rationale" not in serialized
    assert "graph_set" not in serialized
    assert "https://graphs.test" not in serialized
    assert "https://secret.test/shapes" not in serialized
    assert all("semantic-context" in query for query in store.queries)


def test_no_match_is_not_reported_as_unsupported(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    service = SemanticContextQueryService(
        in_memory_session,
        FakeStore(_candidate_rows(settings, "ontology-1")),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    )

    result = service.query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        query="完全不存在的词条",
        depth=0,
    )

    assert result["result_status"] == "no_match"
    assert result["primary_matches"] == []
    assert "unsupported" not in str(result).lower()


def test_project_scope_is_partial_but_explicit_scope_is_all_or_nothing(in_memory_session):
    settings = Settings()
    _ready_ontology(in_memory_session, settings, ontology_id="ready")
    in_memory_session.add(
        OntologyModel(id="incomplete", project_id="project-1", name="incomplete")
    )
    in_memory_session.commit()
    resolver = SemanticQueryScopeResolver(in_memory_session, settings)

    project_scope = resolver.resolve(
        project_id="project-1", scope_mode="project", ontology_ids=[]
    )
    assert project_scope.status == "partial"
    assert [item.ontology_id for item in project_scope.ontologies] == ["ready"]
    assert project_scope.excluded_ontologies[0]["ontology_id"] == "incomplete"

    with pytest.raises(SemanticQueryScopeNotReady):
        resolver.resolve(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ready", "incomplete"],
        )


def test_scope_does_not_leak_cross_project_ontology(in_memory_session):
    settings = Settings()
    _ready_ontology(in_memory_session, settings)
    _ready_ontology(
        in_memory_session,
        settings,
        project_id="project-2",
        ontology_id="ontology-2",
    )

    with pytest.raises(SemanticQueryScopeNotFound):
        SemanticQueryScopeResolver(in_memory_session, settings).resolve(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-2"],
        )


def test_query_normalization_supports_chinese_and_identifiers():
    _, chinese = normalize_query_text("发布工作流需要哪些参数")
    _, identifiers = normalize_query_text("publishWorkflow /api/workflow_id")

    assert "工作流" in chinese
    assert {"publish", "workflow", "api", "workflow", "id"} <= set(identifiers)


def test_candidate_query_filters_terms_before_limit(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    rows = _candidate_rows(settings, "ontology-1")
    store = FakeStore(rows[:1])
    service = SemanticContextQueryService(
        in_memory_session,
        store,
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    )

    result = service.query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        query="发布工作流",
        depth=0,
    )

    assert result["result_status"] == "matched"
    candidate_query = store.queries[0]
    assert "?candidateType" in candidate_query
    assert "FILTER(" in candidate_query
    assert candidate_query.index("FILTER(") < candidate_query.index("LIMIT")
    assert 'LCASE("发布工作流")' in candidate_query


def test_property_label_matches_facts_only_within_the_same_ontology(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="urn:scope:graph/")
    _ready_ontology(in_memory_session, settings, ontology_id="ontology-1")
    _ready_ontology(in_memory_session, settings, ontology_id="ontology-2")
    dataset = Dataset()
    shared_property = URIRef("urn:property:shared")
    graph = lambda role, ontology: dataset.graph(  # noqa: E731 - compact fixture helper
        URIRef(f"urn:scope:graph/{role}/{ontology}")
    )
    graph("ontology", "ontology-1").add(
        (shared_property, RDFS.label, Literal("Billing marker"))
    )
    graph("ontology", "ontology-2").add(
        (shared_property, RDFS.label, Literal("Private marker"))
    )
    graph("data", "ontology-1").add(
        (URIRef("urn:entity:billing"), shared_property, Literal("A"))
    )
    graph("data", "ontology-2").add(
        (URIRef("urn:entity:private"), shared_property, Literal("B"))
    )

    result = SemanticContextQueryService(
        in_memory_session,
        DatasetStore(dataset),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    ).query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1", "ontology-2"],
        query="billing",
        resource_types=["fact"],
        depth=0,
    )

    assert [item["ontology_id"] for item in result["primary_matches"]] == ["ontology-1"]
    assert result["primary_matches"][0]["data"]["subject"] == "urn:entity:billing"


def test_same_property_label_keeps_each_fact_in_its_own_ontology(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="urn:scope:graph/")
    _ready_ontology(in_memory_session, settings, ontology_id="ontology-1")
    _ready_ontology(in_memory_session, settings, ontology_id="ontology-2")
    dataset = Dataset()
    for ontology_id, property_iri, subject_iri in (
        ("ontology-1", "urn:property:first", "urn:entity:first"),
        ("ontology-2", "urn:property:second", "urn:entity:second"),
    ):
        dataset.graph(URIRef(f"urn:scope:graph/ontology/{ontology_id}")).add(
            (URIRef(property_iri), RDFS.label, Literal("Shared marker"))
        )
        dataset.graph(URIRef(f"urn:scope:graph/data/{ontology_id}")).add(
            (URIRef(subject_iri), URIRef(property_iri), Literal(ontology_id))
        )

    result = SemanticContextQueryService(
        in_memory_session,
        DatasetStore(dataset),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    ).query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1", "ontology-2"],
        query="shared marker",
        resource_types=["fact"],
        depth=0,
    )

    ownership = {
        item["data"]["subject"]: item["ontology_id"]
        for item in result["primary_matches"]
    }
    assert ownership == {
        "urn:entity:first": "ontology-1",
        "urn:entity:second": "ontology-2",
    }


def test_direct_matches_use_the_full_response_limit_without_false_truncation(
    in_memory_session,
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    graph_iri = "https://graphs.test/ontology/ontology-1"
    rows = [
        {
            "graph": _binding(graph_iri),
            "subject": _binding(f"https://example.test/Match{index}"),
            "predicate": _binding(
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
            ),
            "object": _binding("http://www.w3.org/2002/07/owl#Class"),
            "subjectLabel": _binding(f"Match {index}", "literal"),
            "subjectTypes": _binding(
                "http://www.w3.org/2002/07/owl#Class", "literal"
            ),
        }
        for index in range(12)
    ]
    service = SemanticContextQueryService(
        in_memory_session,
        FakeStore(rows),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    )

    twelve = service.query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        query="match",
        resource_types=["concept"],
        depth=0,
        limit=20,
    )
    one = SemanticContextQueryService(
        in_memory_session,
        FakeStore(rows[:1]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    ).query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        query="match",
        resource_types=["concept"],
        depth=1,
        limit=1,
    )

    assert len(twelve["primary_matches"]) == 12
    assert twelve["truncated"] is False
    assert len(one["primary_matches"]) == 1
    assert one["truncated"] is False


def test_scoped_sparql_excludes_non_member_shape_views(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)

    scope = SemanticQueryScopeResolver(in_memory_session, settings).resolve(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
    )

    assert "https://graphs.test/shapes/ontology-1" in scope.graph_iris
    assert "https://graphs.test/shapes/ontology-1/custom" not in scope.graph_iris
    assert "https://graphs.test/shapes/ontology-1/generated" not in scope.graph_iris
