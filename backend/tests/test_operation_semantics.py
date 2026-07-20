from __future__ import annotations

import json

import pytest
from rdflib import Dataset, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from app.core.config import Settings
from app.repositories.rdf_store import SparqlResult
from app.security.auth import AuthPrincipal
from app.services.operation_semantics import (
    JSON_DATATYPE,
    OperationValidationError,
    decode_operations,
    operation_quads,
    operation_vocabulary,
    validate_operation_payload,
)
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_command_compiler import compile_command
from app.services.semantic_context_query import SemanticContextQueryService
from app.services.semantic_query_scope import SemanticQueryScopeResolver
from app.repositories.models import OntologyModel, ProjectModel


def _principal() -> AuthPrincipal:
    return AuthPrincipal(
        subject_type="api_key",
        subject_id="test-principal",
        actor="key:test-principal",
        scopes=frozenset({"read"}),
        project_id=None,
        auth_method="bearer",
    )


def _settings() -> Settings:
    return Settings(
        semantic_base_iri="https://r007.test/semantic/",
        semantic_graph_iri_prefix="https://r007.test/graph/",
    )


def _operation(**overrides):
    value = {
        "operation_id": "publish-workflow",
        "name": "发布工作流",
        "aliases": ["Publish workflow"],
        "description": "发布一个工作流",
        "target_resource_type_iri": "https://example.test/Workflow",
        "parameters": [
            {
                "name": "workflow_id",
                "description": "工作流标识",
                "required": True,
                "value_type": "string",
                "enum_values": [],
                "default_value": None,
                "constraints": {"min_length": 1},
            }
        ],
        "preconditions": [{"name": "draft", "description": "工作流处于草稿状态"}],
        "effects": [{"name": "published", "description": "工作流变为已发布"}],
        "possible_failures": [
            {"code": "not_found", "description": "工作流不存在", "retryable": False}
        ],
        "idempotency": {"kind": "conditional", "description": "版本内幂等"},
        "risk_level": "medium",
        "tool_bindings": [
            {
                "binding_id": "generic-http-publish",
                "kind": "http_api",
                "system": "workflow-system",
                "operation_identifier": "POST /workflows/{workflow_id}/publish",
                "version": "v1",
            }
        ],
        "credential_requirements": [
            {
                "name": "Runtime API credential",
                "reference_type": "api_key",
                "description": "调用方运行时提供",
                "required": True,
            }
        ],
        "status": "active",
        "schema_version": "operation-v1",
    }
    value.update(overrides)
    return value


def test_operation_codec_is_canonical_and_id_derived():
    settings = _settings()
    operation = validate_operation_payload(_operation(), settings=settings)
    first = operation_quads(operation, settings, "ontology-1")
    second = operation_quads(dict(reversed(list(operation.items()))), settings, "ontology-1")

    assert first == second
    assert operation["operation_iri"] == ("https://r007.test/semantic/operation/publish-workflow")
    json_objects = [obj for _subject, _predicate, obj, _graph in first if str(JSON_DATATYPE) in obj]
    assert json_objects

    graph = Graph()
    graph.add((URIRef("https://example.test/Workflow"), RDF.type, OWL.Class))
    for subject, predicate, obj, _graph in first:
        graph.parse(data=f"{subject} {predicate} {obj} .", format="turtle")
    assert decode_operations(graph, settings)[0] == operation


def test_operation_validation_rejects_secret_and_inconsistent_parameter():
    settings = _settings()
    with pytest.raises(OperationValidationError) as secret:
        validate_operation_payload(
            _operation(tool_bindings=[{"token": "must-not-be-returned"}]), settings=settings
        )
    assert secret.value.code == "operation_secret_forbidden"
    assert "must-not-be-returned" not in str(secret.value)

    invalid = _operation()
    invalid["parameters"][0]["default_value"] = 7
    with pytest.raises(OperationValidationError) as parameter:
        validate_operation_payload(invalid, settings=settings)
    assert parameter.value.code == "invalid_operation_payload"


def test_operation_rdf_rejects_unknown_secret_predicate():
    settings = _settings()
    graph = Graph()
    graph.add((URIRef("https://example.test/Workflow"), RDF.type, OWL.Class))
    quads = operation_quads(_operation(), settings, "ontology-1")
    for subject, predicate, obj, _graph in quads:
        graph.parse(data=f"{subject} {predicate} {obj} .", format="turtle")
    operation_iri = URIRef("https://r007.test/semantic/operation/publish-workflow")
    graph.add((operation_iri, URIRef("https://r007.test/semantic/vocab/token"), Literal("leak")))

    with pytest.raises(OperationValidationError) as rejected:
        decode_operations(graph, settings)

    assert rejected.value.code == "operation_secret_forbidden"
    assert "leak" not in str(rejected.value)


def test_operation_compilers_create_patch_and_delete_use_one_graph():
    settings = _settings()
    created = compile_command("create_operation", {"ontology_id": "o1", **_operation()}, settings)
    updated = compile_command(
        "update_operation",
        {"ontology_id": "o1", "operation_id": "publish-workflow", "parameters": []},
        settings,
    )
    deleted = compile_command(
        "delete_operation", {"ontology_id": "o1", "operation_id": "publish-workflow"}, settings
    )

    assert created.metadata["operation_iri"] == updated.metadata["operation_iri"]
    assert created.target_graph_iris == updated.target_graph_iris == deleted.target_graph_iris
    assert any("parameters" in predicate for _s, predicate, _o, _g in updated.delta.deletes)
    assert deleted.delta.deletes[0][1:] == ("?p", "?o", created.target_graph_iris[0])


class _DatasetStore:
    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset

    def query_sparql(self, query, timeout_seconds, limit):
        result = self.dataset.query(query)
        return SparqlResult(result=json.loads(result.serialize(format="json")), truncated=False)


class _Lineage:
    def get_lineage(self, **_kwargs):
        return {
            "lineage_status": "complete",
            "evidence_status": "missing",
            "items": [],
            "warnings": [],
        }


class _Shapes:
    def read_merged_guidance(self, *_args, **_kwargs):
        return {"fields": []}


def test_context_query_returns_structured_operation_and_hides_raw_json(in_memory_session):
    settings = _settings()
    in_memory_session.add(ProjectModel(id="p1", name="P1", normalized_label="p1"))
    ontology = OntologyModel(id="o1", project_id="p1", name="O1")
    in_memory_session.add(ontology)
    in_memory_session.flush()
    OntologyWorkspaceService(in_memory_session, settings).ensure(ontology)
    in_memory_session.commit()

    dataset = Dataset()
    graph_iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/o1"
    graph = dataset.graph(URIRef(graph_iri))
    target = URIRef("https://example.test/Workflow")
    graph.add((target, RDF.type, OWL.Class))
    graph.add((target, RDFS.label, Literal("工作流")))
    for subject, predicate, obj, _graph in operation_quads(_operation(), settings, "o1"):
        statement = Graph()
        statement.parse(data=f"{subject} {predicate} {obj} .", format="turtle")
        graph.add(next(iter(statement)))
    service = SemanticContextQueryService(
        in_memory_session,
        _DatasetStore(dataset),
        SemanticQueryScopeResolver(in_memory_session, settings),
        lineage_service=_Lineage(),
        shape_endpoint=_Shapes(),
    )

    result = service.query(
        project_id="p1",
        scope_mode="ontologies",
        ontology_ids=["o1"],
        query="workflow_id",
        depth=0,
        principal=_principal(),
    )
    assert result["primary_matches"][0]["kind"] == "operation"
    assert result["primary_matches"][0]["data"]["parameters"][0]["name"] == "workflow_id"
    assert "raw" not in str(result).lower()

    fact_only = service.query(
        project_id="p1",
        scope_mode="ontologies",
        ontology_ids=["o1"],
        query="workflow_id",
        resource_types=["fact"],
        depth=0,
        principal=_principal(),
    )
    assert fact_only["result_status"] == "no_match"
    assert "workflow_id" not in str(fact_only["primary_matches"])


def test_direct_rdf_shape_uses_controlled_vocabulary_only():
    vocab = operation_vocabulary(_settings())
    assert all("dify" not in value.casefold() for value in vocab.values())
