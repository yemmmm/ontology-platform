"""R1.2-005 focused regression: MCP ``get_semantic_rule_definition`` parity.

Covers shared test plan sections 4 (RD-01..RD-08), 5 (AU-02/AU-03), and
7 (RG-04) against the existing REST by-ID read and the new thin MCP adapter.
The adapter must reuse the existing service, access check, and serializer;
these tests prove parity and authorization rather than exercising a second
response schema.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.mcp.runtime as mcp_runtime
from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.semantic import router
from app.core.config import Settings
from app.mcp.runtime import set_runtime_principal
from app.mcp.server import mcp
from app.mcp.tools import register_all
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import SparqlResult, UpdateResult
from app.services.semantic_rule_definition import SemanticRuleDefinitionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeStore:
    """Minimal RDF store stub sufficient for rule-definition create/read."""

    def __init__(self) -> None:
        self._stored: dict[str, str] = {}
        self._exist: set[str] = set()

    def query_sparql(self, _query, _timeout_seconds, _limit):
        return SparqlResult(result={"head": {"vars": []}, "results": {"bindings": []}})

    def update_sparql(self, _update):
        return UpdateResult()

    def graph_exists(self, graph_iri):
        return graph_iri in self._exist

    def get_graph(self, _graph_iri, _format):
        return ""

    def set_graph(self, graph_iri, content):
        self._stored[graph_iri] = content
        self._exist.add(graph_iri)

    def clear_graph(self, graph_iri):
        self._exist.discard(graph_iri)
        return UpdateResult()

    def graph_content_hash(self, _graph_iri):
        return None


@pytest.fixture(autouse=True)
def _register_mcp_tools() -> None:
    """Ensure the new MCP tool is registered before each test runs."""
    register_all(mcp)


def _seed_project_ontology(session, *, project_id: str, ontology_id: str) -> None:
    session.add(ProjectModel(id=project_id, name=project_id, normalized_label=project_id))
    session.add(OntologyModel(id=ontology_id, project_id=project_id, name=ontology_id))
    session.commit()


def _rest_client(session, store: _FakeStore) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def session_override():
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings()
    return TestClient(app)


def _mcp_tool_fn():
    """Return the registered ``get_semantic_rule_definition`` callable.

    Calling it goes through ``_run_tool`` exactly as in production, so the
    PROJECT_RESOURCE pre-authorization and the body access check both run.
    """
    return mcp._tool_manager.get_tool("get_semantic_rule_definition").fn


def _bind_mcp_session(session, monkeypatch) -> None:
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(mcp_runtime, "get_resources", lambda: (factory, None, None))


# ---------------------------------------------------------------------------
# Fixtures: build Platform DSL + SPARQL CONSTRUCT definitions
# ---------------------------------------------------------------------------


@pytest.fixture()
def platform_dsl_definition(in_memory_session):
    _seed_project_ontology(
        in_memory_session,
        project_id="r12-005-project",
        ontology_id="r12-005-ontology",
    )
    settings = Settings()
    service = SemanticRuleDefinitionService(in_memory_session, settings)
    rule = service.create_rule(
        rule_iri="urn:example:resource-intensive",
        name="Resource-intensive synthetic workflow runs",
        language="platform_dsl",
        body={
            "when": [
                {"s": "?run", "p": "<http://example.test/total_tokens>", "o": "?total_tokens>"},
                {"filter": {"gte": ["?total_tokens>", 50000]}},
            ],
            "then": [
                {
                    "s": "?run",
                    "p": "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
                    "o": "<http://example.test/ResourceIntensiveWorkflowRun>",
                }
            ],
            "explain": "Mark workflow runs whose total_tokens crosses 50000.",
        },
        input_roles=["asserted_data"],
        priority=20,
        metadata={"source": "dify-reference"},
        ontology_id="r12-005-ontology",
    )
    return rule


@pytest.fixture()
def sparql_definition(in_memory_session):
    _seed_project_ontology(
        in_memory_session,
        project_id="r12-005-sparql-project",
        ontology_id="r12-005-sparql-ontology",
    )
    settings = Settings()
    service = SemanticRuleDefinitionService(in_memory_session, settings)
    rule = service.create_rule(
        rule_iri="urn:example:sparql-construct-template",
        name="SPARQL CONSTRUCT reference template",
        language="sparql_construct",
        body={
            "template": (
                "CONSTRUCT { ?run a <http://example.test/TaggedWorkflowRun> } "
                "WHERE { ?run <http://example.test/tag> ?tag }"
            )
        },
        input_roles=["asserted_data"],
        ontology_id="r12-005-sparql-ontology",
    )
    return rule


# ---------------------------------------------------------------------------
# RD-01 / RD-02 / RD-03 / RD-07 / RD-08: REST/MCP parity + DSL body content
# ---------------------------------------------------------------------------


_CORE_KEYS = (
    "id",
    "ontology_id",
    "rule_iri",
    "name",
    "language",
    "version",
    "status",
    "body",
    "input_roles",
    "output_kind",
    "uses_inferred_facts",
    "requires_review",
    "priority",
    "safety_profile",
    "metadata",
)


def test_rd01_rd02_rest_and_mcp_payloads_match_core_fields(
    in_memory_session,
    mcp_principal_factory,
    monkeypatch,
    platform_dsl_definition,
) -> None:
    rule = platform_dsl_definition
    store = _FakeStore()
    client = _rest_client(in_memory_session, store)

    rest_response = client.get(f"/api/semantic/rule-definitions/{rule.id}")
    assert rest_response.status_code == 200
    rest_payload = rest_response.json()

    mcp_principal_factory(
        in_memory_session,
        project_id="r12-005-project",
        scopes=["read"],
    )
    _bind_mcp_session(in_memory_session, monkeypatch)
    mcp_result = _mcp_tool_fn()(rule.id)

    assert mcp_result["ok"] is True
    mcp_payload = mcp_result["data"]
    for key in _CORE_KEYS:
        assert mcp_payload[key] == rest_payload[key], f"parity drift on key={key!r}"


def test_rd03_rd04_platform_dsl_body_preserves_threshold_and_template(
    in_memory_session,
    mcp_principal_factory,
    monkeypatch,
    platform_dsl_definition,
) -> None:
    rule = platform_dsl_definition
    mcp_principal_factory(
        in_memory_session,
        project_id="r12-005-project",
        scopes=["read"],
    )
    _bind_mcp_session(in_memory_session, monkeypatch)
    payload = _mcp_tool_fn()(rule.id)["data"]

    body_json = payload["body"]
    serialized = repr(body_json)
    assert "total_tokens" in serialized
    assert "gte" in serialized
    assert 50000 in body_json["when"][1]["filter"]["gte"]
    assert "ResourceIntensiveWorkflowRun" in serialized
    # RD-04: ``status`` must not be invented as a rule condition.
    when_filters = [
        clause.get("filter") for clause in body_json["when"] if "filter" in clause
    ]
    flat_operands = [
        operand
        for clause in when_filters
        for operands in (clause.values() if clause else [])
        for operand in (operands if isinstance(operands, list) else [operands])
    ]
    assert not any(
        isinstance(operand, str) and "status" in operand.lower()
        for operand in flat_operands
    )


def test_rd05_sparql_construct_body_returned_without_normalization(
    in_memory_session,
    mcp_principal_factory,
    monkeypatch,
    sparql_definition,
) -> None:
    rule = sparql_definition
    mcp_principal_factory(
        in_memory_session,
        project_id="r12-005-sparql-project",
        scopes=["read"],
    )
    _bind_mcp_session(in_memory_session, monkeypatch)
    payload = _mcp_tool_fn()(rule.id)["data"]

    assert payload["language"] == "sparql_construct"
    body = payload["body"]
    # The stored template must be returned verbatim with no Platform DSL
    # ``when``/``then`` keys invented by the adapter.
    assert "template" in body
    assert "CONSTRUCT" in body["template"]
    assert "WHERE" in body["template"]
    assert "when" not in body
    assert "then" not in body


def test_rd07_rd08_metadata_and_iri_round_trip(
    in_memory_session,
    mcp_principal_factory,
    monkeypatch,
    platform_dsl_definition,
) -> None:
    rule = platform_dsl_definition
    mcp_principal_factory(
        in_memory_session,
        project_id="r12-005-project",
        scopes=["read"],
    )
    _bind_mcp_session(in_memory_session, monkeypatch)
    payload = _mcp_tool_fn()(rule.id)["data"]

    assert payload["rule_iri"] == "urn:example:resource-intensive"
    assert payload["ontology_id"] == "r12-005-ontology"
    assert payload["metadata"] == {"source": "dify-reference"}
    assert payload["priority"] == 20


# ---------------------------------------------------------------------------
# AU-02: foreign-Project MCP read must not return Definition body
# ---------------------------------------------------------------------------


def test_au02_foreign_project_mcp_call_returns_no_definition_data(
    in_memory_session,
    mcp_principal_factory,
    monkeypatch,
) -> None:
    _seed_project_ontology(
        in_memory_session,
        project_id="r12-005-owner",
        ontology_id="r12-005-owner-onto",
    )
    _seed_project_ontology(
        in_memory_session,
        project_id="r12-005-foreign",
        ontology_id="r12-005-foreign-onto",
    )
    service = SemanticRuleDefinitionService(in_memory_session, Settings())
    rule = service.create_rule(
        rule_iri="urn:example:owner-only",
        name="owner only",
        language="platform_dsl",
        body={
            "when": [
                {"s": "?run", "p": "<http://example.test/total_tokens>", "o": "?total_tokens>"},
                {"filter": {"gte": ["?total_tokens>", 50000]}},
            ],
            "then": [
                {
                    "s": "?run",
                    "p": "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
                    "o": "<http://example.test/ResourceIntensiveWorkflowRun>",
                }
            ],
        },
        input_roles=["asserted_data"],
        ontology_id="r12-005-owner-onto",
    )

    mcp_principal_factory(
        in_memory_session,
        project_id="r12-005-foreign",
        scopes=["read"],
    )
    _bind_mcp_session(in_memory_session, monkeypatch)
    result = _mcp_tool_fn()(rule.id)

    assert result["ok"] is False
    # Design accepts transport-specific error mapping; both not_found and
    # forbidden_scope are valid as long as no Definition data leaks.
    assert result.get("error_code") in {"not_found", "forbidden_scope"}
    assert result.get("data") in (None, {}, "") or "data" not in result
    envelope_repr = repr(result)
    assert "ResourceIntensiveWorkflowRun" not in envelope_repr
    assert "total_tokens" not in envelope_repr


# ---------------------------------------------------------------------------
# AU-03: unknown Definition ID must return ok=False without body
# ---------------------------------------------------------------------------


def test_au03_unknown_definition_id_returns_no_definition_data(
    in_memory_session,
    mcp_principal_factory,
    monkeypatch,
) -> None:
    from uuid import uuid4

    _seed_project_ontology(
        in_memory_session,
        project_id="r12-005-au3",
        ontology_id="r12-005-au3-onto",
    )
    mcp_principal_factory(
        in_memory_session,
        project_id="r12-005-au3",
        scopes=["read"],
    )
    _bind_mcp_session(in_memory_session, monkeypatch)
    result = _mcp_tool_fn()(str(uuid4()))

    assert result["ok"] is False
    assert result.get("data") in (None, {}, "") or "data" not in result


# ---------------------------------------------------------------------------
# RG-04: MCP registry exposes exactly one new read tool with one required input
# ---------------------------------------------------------------------------


def test_rg04_mcp_registry_lists_new_tool_with_single_required_input() -> None:
    import asyncio

    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert "get_semantic_rule_definition" in tools

    schema = tools["get_semantic_rule_definition"].inputSchema or {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    assert set(properties.keys()) == {"rule_definition_id"}
    assert required == ["rule_definition_id"]


# ---------------------------------------------------------------------------
# DS-03: ordinary Rules summary must not embed the definition body
# ---------------------------------------------------------------------------
# R1.2-005 does not modify Context Query or the Rules read model. The compact
# rule candidate shape (``SemanticContextQueryService._rule_candidates``)
# already excludes ``body``; existing context-query tests cover that contract.
# A duplicated assertion here would re-test an unchanged service and is therefore
# intentionally omitted to keep this focused regression minimal.


# ---------------------------------------------------------------------------
# Fixture hygiene: drop the runtime principal after each test so the
# process-wide MCP singleton does not leak identity into later tests.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_runtime_principal_after_test() -> None:
    yield
    set_runtime_principal(None)
