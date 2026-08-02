from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import OWL, RDFS

from app.core.config import Settings
from app.repositories.models import (
    DataResourceModel,
    DataSourceModel,
    ExternalFieldModel,
    OntologyModel,
    ProjectModel,
    SemanticMappingModel,
)
from app.repositories.rdf_store import SparqlResult
from app.security.auth import AuthPrincipal
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_context_query import (
    SemanticContextQueryError,
    SemanticContextQueryService,
    normalize_query_text,
)
from app.services.semantic_query_scope import (
    SemanticQueryScopeNotFound,
    SemanticQueryScopeNotReady,
    SemanticQueryScopeResolver,
)


def _principal(project_id: str | None = None) -> AuthPrincipal:
    return AuthPrincipal(
        subject_type="api_key",
        subject_id="test-principal",
        actor="key:test-principal",
        scopes=frozenset({"read"}),
        project_id=project_id,
        auth_method="bearer",
    )


def _lexical_recall(candidates):
    """Adapter so monkeypatches remain readable across single/multi pipelines."""

    def _recall_multi(*_args, **_kwargs):
        return {
            "candidates_by_query": [candidates],
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        }

    return _recall_multi


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


class RecordingLineage:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get_lineage(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "lineage_status": "complete",
            "evidence_status": "supported",
            "items": [],
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


def _mapping(
    *,
    mapping_id: str,
    ontology_id: str,
    target_id: str,
    target_type: str = "class",
    external_field: str = "customer_id",
) -> SemanticMappingModel:
    return SemanticMappingModel(
        id=mapping_id,
        project_id="project-1",
        ontology_id=ontology_id,
        target_type=target_type,
        target_id=target_id,
        data_source_id=f"source-{mapping_id}",
        resource_id=f"resource-{mapping_id}",
        field_id=f"field-{mapping_id}",
        external_resource_name="customers",
        external_field_name=external_field,
        join_key={"customer_id": "customer_id"},
        status="active",
    )


def _persist_mapping(session, mapping: SemanticMappingModel) -> None:
    """Seed the governed catalog chain required by SemanticMappingModel FKs."""
    if session.get(ProjectModel, mapping.project_id) is None:
        session.add(
            ProjectModel(
                id=mapping.project_id,
                name=mapping.project_id,
                normalized_label=mapping.project_id,
            )
        )
        session.flush()
    if session.get(OntologyModel, mapping.ontology_id) is None:
        session.add(
            OntologyModel(
                id=mapping.ontology_id,
                project_id=mapping.project_id,
                name=mapping.ontology_id,
            )
        )
        session.flush()
    session.add(
        DataSourceModel(
            id=mapping.data_source_id,
            project_id=mapping.project_id,
            name=mapping.data_source_id,
            source_type="database",
        )
    )
    session.flush()
    session.add(
        DataResourceModel(
            id=mapping.resource_id,
            project_id=mapping.project_id,
            data_source_id=mapping.data_source_id,
            name=mapping.resource_id,
        )
    )
    session.flush()
    session.add(
        ExternalFieldModel(
            id=mapping.field_id,
            project_id=mapping.project_id,
            data_source_id=mapping.data_source_id,
            data_resource_id=mapping.resource_id,
            name=mapping.external_field_name,
        )
    )
    session.flush()
    session.add(mapping)


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
        principal=_principal(),
    )

    assert result["result_status"] == "matched"
    assert result["primary_matches"][0]["kind"] == "concept"
    shape_item = next(
        item
        for item in result["related_context"]
        if item["match"]["reasons"] == ["shape_constraint"]
    )
    assert shape_item["data"]["constraint"]["required"] is True
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


def test_generated_shape_constraint_projects_property_lineage_target(
    in_memory_session,
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    lineage_result = {
        "lineage_status": "complete",
        "evidence_status": "supported",
        "items": [
            {
                "supporting_context": {
                    "evidence_references": [{"id": "property-evidence"}]
                }
            }
        ],
        "warnings": [],
    }

    class EvidenceLineage(RecordingLineage):
        def get_lineage(self, **kwargs):
            self.calls.append(kwargs)
            return lineage_result

    evidence_lineage = EvidenceLineage()
    service = SemanticContextQueryService(
        in_memory_session,
        FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=evidence_lineage,
        shape_endpoint=FakeShapes(),
    )
    scope = service.scope_resolver.resolve(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
    )
    primary = [
        {
            "id": "https://example.test/Workflow",
            "kind": "concept",
            "ontology_id": "ontology-1",
            "iri": "https://example.test/Workflow",
            "data": {},
        }
    ]

    items = service._shape_constraint_items(primary, scope, limit=10)
    assert len(items) == 1
    shape_item = items[0]
    property_iri = "https://example.test/datasetId"
    expected_id = hashlib.sha256(
        f"ontology-1:https://example.test/Workflow:{property_iri}".encode("utf-8")
    ).hexdigest()
    assert shape_item["id"] == expected_id
    assert shape_item["kind"] == "fact"
    assert shape_item["data"]["constraint"]["provenance"] == "generated"
    assert shape_item["target_kind"] == "resource"
    assert shape_item["_lineage_target"] == {
        "target_type": "resource",
        "target_id": property_iri,
    }

    decorated = service._decorate(shape_item, scope)
    assert "_lineage_target" not in decorated
    assert decorated["lineage"] == {
        "target_type": "resource",
        "target_id": property_iri,
        "status": "complete",
    }
    assert decorated["evidence_reference_ids"] == ["property-evidence"]
    assert decorated["warnings"] == []
    assert evidence_lineage.calls[0]["target_type"] == "resource"
    assert evidence_lineage.calls[0]["target_id"] == property_iri
    assert evidence_lineage.calls[0]["target_id"] != shape_item["id"]


@pytest.mark.parametrize(
    "field",
    [
        {"path": "https://example.test/custom", "provenance": "custom"},
        {"path": "https://example.test/merged", "provenance": "merged"},
        {"path": "_:blank", "provenance": "generated"},
        {"path": "relative/property", "provenance": "generated"},
    ],
)
def test_shape_constraint_without_generated_canonical_property_fails_closed(
    in_memory_session, field
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)

    class ShapeEndpoint:
        def read_merged_guidance(self, graph_set_id, class_iri):  # noqa: ARG002
            return {"fields": [field]}

    lineage = RecordingLineage()
    service = SemanticContextQueryService(
        in_memory_session,
        FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=lineage,
        shape_endpoint=ShapeEndpoint(),
    )
    scope = service.scope_resolver.resolve(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
    )
    primary = [
        {
            "id": "https://example.test/Workflow",
            "kind": "concept",
            "ontology_id": "ontology-1",
            "iri": "https://example.test/Workflow",
            "data": {},
        }
    ]

    shape_item = service._shape_constraint_items(primary, scope, limit=10)[0]
    assert "_lineage_target" not in shape_item
    assert "target_kind" not in shape_item
    decorated = service._decorate(shape_item, scope)
    assert "_lineage_target" not in decorated
    assert decorated["lineage"] == {"status": "missing"}
    assert {warning["code"] for warning in decorated["warnings"]} == {
        "evidence_missing",
        "lineage_missing",
    }
    assert lineage.calls == []


def test_shape_constraint_unknown_internal_lineage_marker_is_stripped(
    in_memory_session,
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    lineage = RecordingLineage()
    service = SemanticContextQueryService(
        in_memory_session,
        FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=lineage,
        shape_endpoint=FakeShapes(),
    )
    scope = service.scope_resolver.resolve(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
    )
    shape_item = {
        "id": "synthetic-shape-id",
        "kind": "fact",
        "ontology_id": "ontology-1",
        "iri": None,
        "label": "custom",
        "aliases": [],
        "description": None,
        "data": {
            "target_class": "https://example.test/Workflow",
            "constraint": {"path": "relative/property", "provenance": "custom"},
        },
        "distance": 1,
        "assertion_kind": "asserted",
        "match": {
            "score": 275,
            "matched_terms": [],
            "matched_fields": ["constraint"],
            "reasons": ["shape_constraint"],
        },
        "_lineage_target": {
            "target_type": "synthetic",
            "target_id": "synthetic-shape-id",
        },
    }

    decorated = service._decorate(shape_item, scope)

    assert "_lineage_target" not in decorated
    assert "target_kind" not in decorated
    assert decorated["lineage"] == {"status": "missing"}
    assert "synthetic" not in str(decorated["lineage"])
    assert {warning["code"] for warning in decorated["warnings"]} == {
        "evidence_missing",
        "lineage_missing",
    }
    assert lineage.calls == []


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
        principal=_principal(),
    )

    assert result["result_status"] == "no_match"
    assert result["primary_matches"] == []
    assert "unsupported" not in str(result).lower()


def test_exact_mapping_evidence_precedes_higher_scoring_semantic_candidate(
    in_memory_session, monkeypatch
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    target_iri = "https://example.test/Customer"
    _persist_mapping(
        in_memory_session,
        _mapping(
            mapping_id="mapping-customer-id",
            ontology_id="ontology-1",
            target_id=target_iri,
        ),
    )
    in_memory_session.commit()

    semantic_candidates = [
        {
            "id": "https://example.test/SemanticCandidate",
            "kind": "concept",
            "ontology_id": "ontology-1",
            "iri": "https://example.test/SemanticCandidate",
            "label": "Semantic candidate",
            "aliases": [],
            "description": None,
            "data": {"rdf_types": []},
            "distance": 0,
            "assertion_kind": "asserted",
            "match": {
                "score": 950,
                "lexical_score": 0,
                "semantic_similarity": 0.95,
                "effective_score": 0.95,
                "candidate_level": "semantic_candidate",
                "method": "semantic",
                "matched_terms": [],
                "matched_fields": [],
                "reasons": ["semantic_candidate"],
            },
        }
    ]

    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        _lexical_recall(semantic_candidates),
    )
    result = SemanticContextQueryService(
        in_memory_session,
        FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    ).query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        query="class",
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    assert [item["iri"] for item in result["primary_matches"]] == [
        target_iri,
        "https://example.test/SemanticCandidate",
    ]
    mapping_match = result["primary_matches"][0]
    assert mapping_match["match"]["candidate_level"] == "exact"
    assert mapping_match["match"]["reasons"] == ["exact_mapping"]
    assert mapping_match["match"]["matched_fields"] == ["mapping_target_type"]
    assert mapping_match["mapping_evidence"] == [
        {
            "mapping_id": "mapping-customer-id",
            "target_type": "class",
            "external_field": "customer_id",
            "join_keys": "customer_id",
        }
    ]


def test_exact_alias_precedes_higher_scoring_semantic_candidate(
    in_memory_session, monkeypatch
):
    """The Context exact layer is independent from semantic score magnitude."""

    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)

    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        _lexical_recall(
            [
                {
                    "id": "https://example.test/SemanticCandidate",
                    "kind": "concept",
                    "ontology_id": "ontology-1",
                    "iri": "https://example.test/SemanticCandidate",
                    "label": "Semantic candidate",
                    "aliases": [],
                    "description": None,
                    "data": {"rdf_types": []},
                    "distance": 0,
                    "assertion_kind": "asserted",
                    "match": {
                        "score": 950,
                        "lexical_score": 0,
                        "semantic_similarity": 0.95,
                        "effective_score": 0.95,
                        "candidate_level": "semantic_candidate",
                        "method": "semantic",
                        "matched_terms": [],
                        "matched_fields": [],
                        "reasons": ["semantic_candidate"],
                    },
                }
            ]
        ),
    )
    result = SemanticContextQueryService(
        in_memory_session,
        FakeStore(_candidate_rows(settings, "ontology-1")[:1]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    ).query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        query="PublishWorkflow",
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    assert [item["iri"] for item in result["primary_matches"]] == [
        "https://example.test/Workflow",
        "https://example.test/SemanticCandidate",
    ]
    assert result["primary_matches"][0]["match"]["candidate_level"] == "exact"
    assert result["primary_matches"][0]["match"]["reasons"] == ["exact_alias"]


def test_scoped_semantic_chinese_label_recovers_exact_label_when_lexical_scan_is_empty(
    in_memory_session, monkeypatch
):
    """A current scoped document may repair a missing lexical-SPARQL row only.

    This models the live Chinese-label failure: the asserted label is present
    in the current retrieval partition, but no lexical row made it into the
    candidate scan.  Scope is still constrained by the recall service.
    """
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        _lexical_recall(
            [
                {
                    "id": "https://example.test/CustomerSupportWorkflow",
                    "kind": "concept",
                    "ontology_id": "ontology-1",
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
                    "distance": 0,
                    "assertion_kind": "asserted",
                    "match": {
                        "score": 637,
                        "lexical_score": 0,
                        "semantic_similarity": 0.637,
                        "effective_score": 0.637,
                        "candidate_level": "semantic_candidate",
                        "method": "semantic",
                        "matched_terms": [],
                        "matched_fields": [],
                        "reasons": ["semantic_candidate"],
                    },
                }
            ]
        ),
    )
    result = SemanticContextQueryService(
        in_memory_session,
        FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    ).query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        query="客户支持工作流",
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    match = result["primary_matches"][0]["match"]
    assert result["recall"]["match_status"] == "exact"
    assert match["candidate_level"] == "exact"
    assert match["lexical_score"] == 1000
    assert match["matched_fields"] == ["label"]
    assert match["reasons"] == ["exact_label", "semantic_candidate"]


def test_bilingual_rdf_label_match_uses_matched_value_not_sampled_display_label(
    in_memory_session, monkeypatch
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    graph = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/ontology-1"
    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        _lexical_recall([]),
    )
    result = SemanticContextQueryService(
        in_memory_session,
        FakeStore(
            [
                {
                    "graph": _binding(graph),
                    "subject": _binding("https://example.test/CustomerSupportWorkflow"),
                    "predicate": _binding("http://www.w3.org/2000/01/rdf-schema#label"),
                    "object": _binding("客户支持工作流", "literal"),
                    "subjectLabel": _binding("Customer Support Workflow", "literal"),
                    "subjectTypes": _binding(
                        "http://www.w3.org/2002/07/owl#Class", "literal"
                    ),
                    "matchedField": _binding("label", "literal"),
                    "matchedValue": _binding("客户支持工作流", "literal"),
                }
            ]
        ),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    ).query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        query="客户支持工作流",
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    match = result["primary_matches"][0]["match"]
    assert result["primary_matches"][0]["label"] == "客户支持工作流"
    assert result["recall"]["match_status"] == "exact"
    assert match["candidate_level"] == "exact"
    assert match["reasons"] == ["exact_label"]


def test_mapping_evidence_stays_with_its_same_ontology_target(in_memory_session, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings, ontology_id="ontology-1")
    _ready_ontology(in_memory_session, settings, ontology_id="ontology-2")
    _persist_mapping(
        in_memory_session,
        _mapping(
            mapping_id="mapping-one",
            ontology_id="ontology-1",
            target_id="https://example.test/CustomerOne",
        ),
    )
    _persist_mapping(
        in_memory_session,
        _mapping(
            mapping_id="mapping-two",
            ontology_id="ontology-2",
            target_id="https://example.test/CustomerTwo",
        ),
    )
    in_memory_session.commit()

    monkeypatch.setattr(
        "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
        _lexical_recall([]),
    )
    result = SemanticContextQueryService(
        in_memory_session,
        FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    ).query(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1", "ontology-2"],
        query="customer_id",
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    assert [
        (item["ontology_id"], item["iri"], item["mapping_evidence"][0]["mapping_id"])
        for item in result["primary_matches"]
    ] == [
        ("ontology-1", "https://example.test/CustomerOne", "mapping-one"),
        ("ontology-2", "https://example.test/CustomerTwo", "mapping-two"),
    ]


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
        principal=_principal(),
    )

    assert result["result_status"] == "matched"
    candidate_query = store.queries[0]
    assert "?candidateType" in candidate_query
    assert "FILTER(" in candidate_query
    assert candidate_query.index("FILTER(") < candidate_query.index("LIMIT")
    assert 'LCASE("发布工作流")' in candidate_query


def test_object_property_resource_and_relation_fact_use_distinct_lineage_targets(
    in_memory_session,
):
    settings = Settings(semantic_graph_iri_prefix="urn:scope:graph/")
    _ready_ontology(in_memory_session, settings, ontology_id="ontology-1")
    graph = "urn:scope:graph/ontology/ontology-1"
    property_iri = "urn:property:owns"
    rows = [
        {
            "graph": _binding(graph),
            "subject": _binding(property_iri),
            "predicate": _binding(str(RDFS.label)),
            "object": _binding("owns", "literal"),
            "subjectLabel": _binding("owns", "literal"),
            "subjectTypes": _binding(str(OWL.ObjectProperty), "literal"),
        },
        {
            "graph": _binding(graph),
            "subject": _binding("urn:entity:alice"),
            "predicate": _binding(property_iri),
            "object": _binding("urn:entity:bob"),
            "subjectLabel": _binding("Alice", "literal"),
            "predicateLabel": _binding("owns", "literal"),
        },
    ]
    lineage = RecordingLineage()
    service = SemanticContextQueryService(
        in_memory_session,
        FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=lineage,
        shape_endpoint=FakeShapes(),
    )
    scope = service.scope_resolver.resolve(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
    )

    candidates = service._rdf_candidates(rows, scope, "owns", ["owns"])
    property_resource = next(item for item in candidates if item["id"] == property_iri)
    relation_fact = next(
        item
        for item in candidates
        if item["kind"] == "relation" and item["target_kind"] == "statement"
    )
    assert property_resource["kind"] == "relation"
    assert property_resource["target_kind"] == "resource"
    assert relation_fact["data"]["subject"] == "urn:entity:alice"

    decorated_property = service._decorate(property_resource, scope)
    decorated_fact = service._decorate(relation_fact, scope)
    calls_by_id = {call["target_id"]: call["target_type"] for call in lineage.calls}
    assert decorated_property["lineage"]["target_type"] == "resource"
    assert decorated_fact["lineage"]["target_type"] == "statement"
    assert calls_by_id[property_iri] == "resource"
    assert calls_by_id[relation_fact["id"]] == "statement"


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
        principal=_principal(),
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
        principal=_principal(),
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
        principal=_principal(),
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
        principal=_principal(),
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


# ---------------------------------------------------------------------------
# R1.2-004 multi-expression Context Query (service-level coverage for
# FQ/RS/FU/CX/PG/DG/PF cases that can be proven with controlled fixtures).
# ---------------------------------------------------------------------------


class _CallSpy:
    """Wraps a fake recall_multi implementation and records call count."""

    def __init__(self, candidates_by_query):
        self._candidates_by_query = candidates_by_query
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        return {
            "candidates_by_query": self._candidates_by_query,
            "indexes": [],
            "warnings": [],
            "completeness": "complete",
        }


def _concept_candidate(
    *,
    iri,
    label,
    ontology_id="ontology-1",
    score=600,
    reasons=("semantic_candidate",),
    candidate_level="semantic_candidate",
    similarity=0.6,
):
    return {
        "id": iri,
        "kind": "concept",
        "ontology_id": ontology_id,
        "iri": iri,
        "label": label,
        "aliases": [],
        "description": None,
        "data": {"rdf_types": []},
        "distance": 0,
        "assertion_kind": "asserted",
        "match": {
            "score": score,
            "lexical_score": 0,
            "semantic_similarity": similarity,
            "effective_score": (round(similarity, 3) if similarity is not None else 1.0),
            "candidate_level": candidate_level,
            "method": "semantic",
            "matched_terms": [],
            "matched_fields": [],
            "reasons": list(reasons),
        },
    }


def _exact_candidate(
    *,
    iri,
    label,
    ontology_id="ontology-1",
    reason="exact_label",
    score=1000,
):
    candidate = _concept_candidate(
        iri=iri,
        label=label,
        ontology_id=ontology_id,
        score=score,
        reasons=(reason,),
        candidate_level="exact",
        similarity=None,
    )
    candidate["match"]["lexical_score"] = score
    candidate["match"]["semantic_similarity"] = None
    candidate["match"]["effective_score"] = 1.0
    candidate["match"]["method"] = "label"
    return candidate


def _multi_service(in_memory_session, settings, store, recall_multi=None, monkeypatch=None):
    if recall_multi is not None and monkeypatch is not None:
        monkeypatch.setattr(
            "app.services.semantic_context_query.SemanticResourceRetrievalService.recall_multi",
            recall_multi,
        )
    return SemanticContextQueryService(
        in_memory_session,
        store,
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    )


def test_multi_expression_echoes_original_queries_and_dedupes(in_memory_session, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    # Two normalized duplicates ("x") plus one distinct ("y") -> execution set size 2.
    spy = _CallSpy([[], []])
    service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)

    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["x", "x", "y"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    assert result["query"]["queries"] == ["x", "x", "y"]
    # Normalized duplicates collapse to one execution entry, preserving first-seen order.
    assert result["query"]["normalized_queries"] == ["x", "y"]
    # One scope resolution, one embedding batch (PF-01).
    assert spy.calls == 1


def test_multi_expression_support_count_does_not_boost_duplicates(
    in_memory_session, monkeypatch
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    shared = _concept_candidate(iri="https://example.test/Shared", label="shared")
    other = _concept_candidate(
        iri="https://example.test/Other", label="other", score=400, similarity=0.4
    )
    spy = _CallSpy([[shared], [other]])
    service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)

    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["a", "b", "a"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    shared_match = next(
        item for item in result["primary_matches"] if item["iri"] == "https://example.test/Shared"
    )
    # "a" appears twice in input but its normalized duplicate only supports once.
    assert shared_match["fusion"]["support_count"] == 1
    assert result["query"]["queries"] == ["a", "b", "a"]


def test_multi_expression_exact_evidence_ranks_above_semantic_only(in_memory_session, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    exact = _exact_candidate(iri="https://example.test/Exact", label="exact")
    weak = _concept_candidate(
        iri="https://example.test/Weak",
        label="weak",
        score=950,
        similarity=0.95,
    )
    spy = _CallSpy([[exact, weak]])
    service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)

    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    assert [item["iri"] for item in result["primary_matches"]] == [
        "https://example.test/Exact",
        "https://example.test/Weak",
    ]
    assert result["primary_matches"][0]["fusion"]["best_evidence_tier"] == "exact"


def test_multi_expression_same_tier_higher_score_ranks_first(in_memory_session, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    higher = _concept_candidate(
        iri="https://example.test/Higher", label="higher", score=900, similarity=0.9
    )
    lower = _concept_candidate(
        iri="https://example.test/Lower", label="lower", score=400, similarity=0.4
    )
    spy = _CallSpy([[higher, lower]])
    service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)

    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    assert [item["iri"] for item in result["primary_matches"]] == [
        "https://example.test/Higher",
        "https://example.test/Lower",
    ]


def test_multi_expression_support_count_breaks_ties_within_tier(in_memory_session, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    supported = _concept_candidate(
        iri="https://example.test/Supported", label="supported", score=500, similarity=0.5
    )
    alone = _concept_candidate(
        iri="https://example.test/Alone", label="alone", score=500, similarity=0.5
    )
    spy = _CallSpy([[supported, alone], [supported]])
    service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)

    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["a", "b"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    assert [item["iri"] for item in result["primary_matches"]] == [
        "https://example.test/Supported",
        "https://example.test/Alone",
    ]
    assert result["primary_matches"][0]["fusion"]["support_count"] == 2
    assert result["primary_matches"][1]["fusion"]["support_count"] == 1


def test_multi_expression_reorder_invariance(in_memory_session, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    a = _concept_candidate(
        iri="https://example.test/A", label="a", score=500, similarity=0.5
    )
    b = _concept_candidate(
        iri="https://example.test/B", label="b", score=500, similarity=0.5
    )

    def run(queries, candidates_by_query):
        spy = _CallSpy(candidates_by_query)
        service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)
        return service.query_multi(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-1"],
            queries=queries,
            resource_types=["concept"],
            depth=0,
            principal=_principal(),
        )

    first = run(["x", "y"], [[a, b], [a]])
    second = run(["y", "x"], [[a], [a, b]])
    assert [item["iri"] for item in first["primary_matches"]] == [
        item["iri"] for item in second["primary_matches"]
    ]
    assert [item["fusion"]["support_count"] for item in first["primary_matches"]] == [
        item["fusion"]["support_count"] for item in second["primary_matches"]
    ]


def test_multi_expression_matched_queries_correlate_by_index(in_memory_session, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    shared = _concept_candidate(
        iri="https://example.test/Shared", label="shared", score=500, similarity=0.5
    )
    spy = _CallSpy([[shared], [shared]])
    service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)

    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["first", "second"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    matched = result["primary_matches"][0]["matched_queries"]
    indexes = sorted({index for entry in matched for index in entry["indexes"]})
    assert indexes == [0, 1]


def test_multi_expression_match_pagination_returns_match_cursor_only(
    in_memory_session, monkeypatch
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    candidates = [
        _concept_candidate(
            iri=f"https://example.test/Item{index}",
            label=f"item{index}",
            score=500 - index,
            similarity=0.5,
        )
        for index in range(5)
    ]
    spy = _CallSpy([candidates])
    service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)

    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=0,
        limit=2,
        context_limit=0,
        principal=_principal(),
    )

    assert len(result["primary_matches"]) == 2
    assert result["matches_page"]["truncated"] is True
    assert result["matches_page"]["next_match_cursor"] is not None
    assert result["context_page"]["truncated"] is False
    assert result["context_page"]["next_context_cursor"] is None
    assert result["truncated"] is True


def test_multi_expression_context_limit_zero_returns_no_context(in_memory_session, monkeypatch):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    candidate = _exact_candidate(iri="https://example.test/Exact", label="exact")
    spy = _CallSpy([[candidate]])
    service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)

    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["exact"],
        resource_types=["concept"],
        depth=1,
        context_limit=0,
        principal=_principal(),
    )

    assert len(result["primary_matches"]) == 1
    assert result["related_context"] == []
    assert result["context_page"]["next_context_cursor"] is None


def test_multi_expression_match_cursor_continues_global_stream(
    in_memory_session, monkeypatch
):
    settings = Settings(
        semantic_graph_iri_prefix="https://graphs.test/",
        semantic_context_query_cursor_signing_secret="stable-test-secret",
    )
    _ready_ontology(in_memory_session, settings)
    candidates = [
        _concept_candidate(
            iri=f"https://example.test/Item{index}",
            label=f"item{index}",
            score=500 - index,
            similarity=0.5,
        )
        for index in range(4)
    ]
    spy = _CallSpy([candidates])
    service = _multi_service(in_memory_session, settings, FakeStore([]), spy, monkeypatch)

    first = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=0,
        limit=2,
        context_limit=0,
        principal=_principal(),
    )
    cursor = first["matches_page"]["next_match_cursor"]
    assert cursor is not None

    second = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=0,
        limit=2,
        context_limit=0,
        principal=_principal(),
        match_cursor=cursor,
    )

    first_ids = [item["iri"] for item in first["primary_matches"]]
    second_ids = [item["iri"] for item in second["primary_matches"]]
    assert set(first_ids).isdisjoint(set(second_ids))
    assert len(second["primary_matches"]) == 2
    assert second["matches_page"]["truncated"] is False


def test_multi_expression_degraded_recall_returns_partial_results(
    in_memory_session, monkeypatch
):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    candidate = _concept_candidate(
        iri="https://example.test/Available", label="available", score=500, similarity=0.5
    )

    def recall_multi(*_args, **_kwargs):
        return {
            "candidates_by_query": [[candidate]],
            "indexes": [{"ontology_id": "ontology-1", "status": "stale"}],
            "warnings": [
                {"code": "vector_index_stale", "message": "Semantic vector recall is unavailable for one Ontology."}
            ],
            "completeness": "degraded",
        }

    service = _multi_service(in_memory_session, settings, FakeStore([]), recall_multi, monkeypatch)

    result = service.query_multi(
        project_id="project-1",
        scope_mode="ontologies",
        ontology_ids=["ontology-1"],
        queries=["topic"],
        resource_types=["concept"],
        depth=0,
        principal=_principal(),
    )

    assert result["result_status"] == "matched"
    assert result["recall"]["completeness"] == "degraded"
    assert len(result["primary_matches"]) == 1


def test_multi_expression_rejects_missing_principal(in_memory_session):
    settings = Settings(semantic_graph_iri_prefix="https://graphs.test/")
    _ready_ontology(in_memory_session, settings)
    service = SemanticContextQueryService(
        in_memory_session,
        FakeStore([]),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=FakeLineage(),
        shape_endpoint=FakeShapes(),
    )
    with pytest.raises(SemanticContextQueryError):
        service.query_multi(
            project_id="project-1",
            scope_mode="ontologies",
            ontology_ids=["ontology-1"],
            queries=["topic"],
            depth=0,
        )
