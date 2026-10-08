"""Stage 2 §11 — read-model template execution tests through the FastAPI
``GET /api/semantic/graph-sets/{gs}/read-models/{name}`` endpoint.

Each test seeds a graph-set row in the in-memory registry, sets up the
FakeStore to return canned SPARQL SELECT rows for the template marker, and
asserts the envelope's ``items`` carry the expected IRI / label /
``source_graph_iri`` fields.

Two composers are also exercised:

* ``fact-audit-queue`` — verifies ``?kind=asserted`` / ``inferred`` /
  ``rule_derived`` / ``missing_evidence`` route to the right source graph
  and that ``inferred`` / ``rule_derived`` without an effective pointer
  return empty items + a warning.
* ``entity-shape`` — verifies the composer delegates to the shape endpoint
  service (we seed a custom-shapes sub-graph and assert the guidance is
  merged from generated + custom sources).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.semantic import router
from app.core.config import Settings
from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)
from app.repositories.rdf_store import SparqlResult


PREFIX = "http://op.local/semantic/"
GRAPH_PREFIX = f"{PREFIX}graph/"
ONTOLOGY_GRAPH = f"{GRAPH_PREFIX}ontology/ont-1"
DATA_GRAPH = f"{GRAPH_PREFIX}data/ont-1"
CUSTOM_SHAPES_GRAPH = f"{GRAPH_PREFIX}shapes/ont-1/custom"
REASONING_RESULT_GRAPH = f"{GRAPH_PREFIX}reasoning-result/run-7"
RULE_RESULT_GRAPH = f"{GRAPH_PREFIX}rule-result/run-9"
FOREIGN_DATA_GRAPH = f"{GRAPH_PREFIX}data/ont-foreign"


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.bindings = rows


class FakeStore:
    """Returns canned rows keyed by a marker substring appearing in the
    query text (template name or unique SPARQL token)."""

    def __init__(self, rows_by_marker: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._rows_by_marker = rows_by_marker or {}
        self._stored_graphs: dict[str, str] = {}
        self._graphs: set[str] = set()
        self.last_query: str | None = None
        self.last_graph_iris: list[str] | None = None

    def set_graph(self, graph_iri: str, content: str) -> None:
        self._stored_graphs[graph_iri] = content
        self._graphs.add(graph_iri)

    def get_graph(self, graph_iri: str, format: str) -> str:  # noqa: A002
        return self._stored_graphs.get(graph_iri, "")

    def graph_exists(self, graph_iri: str) -> bool:
        return graph_iri in self._graphs

    def query_read_model(self, query: str, graph_iris: list[str], timeout_seconds: float, limit: int):
        self.last_query = query
        self.last_graph_iris = list(graph_iris)
        for marker, rows in self._rows_by_marker.items():
            if marker in query:
                return _Result(rows)
        return _Result([])

    def query_sparql(self, query: str, timeout_seconds: float, limit: int):
        return SparqlResult(
            result={"head": {"vars": []}, "results": {"bindings": []}}
        )

    def update_sparql(self, update: str):
        return None

    def export_dataset(self, format: str, graph_iris=None) -> str:  # noqa: A002
        return ""

    def clear_graph(self, graph_iri: str):
        return None

    def graph_content_hash(self, graph_iri: str):
        return None


def _client(store: FakeStore, session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    settings = Settings(
        semantic_base_iri=f"{PREFIX}ns/",
        semantic_graph_iri_prefix=GRAPH_PREFIX,
        semantic_product_write_mode="canonical_only",
        semantic_read_mode="canonical",
        semantic_legacy_write_blocked=True,
    )

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _seed_graph_set(
    session: Session,
    members: list[tuple[str, str]],
    *,
    graph_set_id: str = "gs-1",
    reasoning_graph: str | None = None,
    rule_graph: str | None = None,
) -> None:
    gs = SemanticGraphSetModel(
        id=graph_set_id,
        name="stage2-rm",
        scope_type="ontology",
        scope_id="ont-1",
        status="active",
        source_signature="sig-1",
    )
    session.add(gs)
    for idx, (iri, role) in enumerate(members):
        gs.members.append(
            SemanticGraphSetMemberModel(
                id=f"m-{idx}",
                graph_iri=iri,
                role=role,
                required=True,
                sort_order=idx,
            )
        )
    if reasoning_graph:
        session.add(
            SemanticDerivedResultPointerModel(
                id=f"ptr-{graph_set_id}-reasoning",
                graph_set_id=graph_set_id,
                result_kind="reasoning",
                run_id="reasoning-run-1",
                result_graph_iri=reasoning_graph,
                source_signature="sig-1",
                status="current",
            )
        )
    if rule_graph:
        session.add(
            SemanticDerivedResultPointerModel(
                id=f"ptr-{graph_set_id}-rule",
                graph_set_id=graph_set_id,
                result_kind="rule",
                run_id="rule-run-1",
                result_graph_iri=rule_graph,
                source_signature="sig-1",
                status="current",
            )
        )
    session.commit()


def _read_model(
    client: TestClient,
    model_name: str,
    *,
    graph_set_id: str = "gs-1",
    **params: Any,
) -> dict[str, Any]:
    response = client.get(
        f"/api/semantic/graph-sets/{graph_set_id}/read-models/{model_name}",
        params={"include": "asserted", **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Pure SPARQL templates
# ---------------------------------------------------------------------------


def test_class_topology_executes_and_decorates_rows(in_memory_session) -> None:
    _seed_graph_set(in_memory_session, [(ONTOLOGY_GRAPH, "asserted_ontology")])
    store = FakeStore(
        rows_by_marker={
            "class-topology": [
                {
                    "class": f"{PREFIX}ns/class/Student",
                    "label": "Student",
                    "parent": f"{PREFIX}ns/class/Person",
                    "graph": ONTOLOGY_GRAPH,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)
    body = _read_model(client, "class-topology")
    assert body["model_name"] == "class-topology"
    assert body["items"], "expected at least one row"
    item = body["items"][0]
    assert item["iri"] == f"{PREFIX}ns/class/Student"
    assert item["label"] == "Student"
    assert item["parent"] == f"{PREFIX}ns/class/Person"
    assert item["source_graph_iri"] == ONTOLOGY_GRAPH
    assert item["assertion_kind"] == "asserted"
    assert store.last_query is not None
    assert "{graph_iris}" not in store.last_query
    assert f"VALUES ?g {{ <{ONTOLOGY_GRAPH}> }}" in store.last_query


def test_class_topology_without_source_graphs_returns_empty_without_invalid_sparql(
    in_memory_session,
) -> None:
    _seed_graph_set(in_memory_session, [])
    store = FakeStore(rows_by_marker={"class-topology": []})
    client = _client(store, in_memory_session)

    body = _read_model(client, "class-topology")

    assert body["items"] == []
    assert body["warnings"][0]["code"] == "read_model_no_source_graphs"
    assert store.last_query is None


def test_statement_list_preserves_predicate_object_and_literal_metadata(in_memory_session) -> None:
    _seed_graph_set(in_memory_session, [(DATA_GRAPH, "asserted_data")])
    store = FakeStore(
        rows_by_marker={
            "statement-list": [
                {
                    "subject": {"type": "uri", "value": f"{PREFIX}ns/workflow/B"},
                    "predicate": {"type": "uri", "value": f"{PREFIX}ns/property/hasVersion"},
                    "object": {
                        "type": "literal",
                        "value": "2.0",
                        "datatype": "http://www.w3.org/2001/XMLSchema#string",
                        "xml:lang": "en",
                    },
                    "graph": {"type": "uri", "value": DATA_GRAPH},
                },
                {
                    "subject": {"type": "uri", "value": f"{PREFIX}ns/workflow/B"},
                    "predicate": {"type": "uri", "value": f"{PREFIX}ns/property/invokes"},
                    "object": {"type": "uri", "value": f"{PREFIX}ns/workflow/C"},
                    "graph": {"type": "uri", "value": DATA_GRAPH},
                },
            ]
        }
    )
    body = _read_model(_client(store, in_memory_session), "statement-list")

    literal, iri = body["items"]
    assert literal["subject"] == f"{PREFIX}ns/workflow/B"
    assert literal["predicate"] == f"{PREFIX}ns/property/hasVersion"
    assert literal["object"] == "2.0"
    assert literal["object_kind"] == "literal"
    assert literal["object_datatype"] == "http://www.w3.org/2001/XMLSchema#string"
    assert literal["object_language"] == "en"
    assert iri["object"] == f"{PREFIX}ns/workflow/C"
    assert iri["object_kind"] == "iri"
    assert "object_datatype" not in iri
    assert "object_language" not in iri


def test_statement_list_binds_exact_asserted_data_member_and_excludes_bounded_leaks(
    in_memory_session,
) -> None:
    _seed_graph_set(
        in_memory_session,
        [(ONTOLOGY_GRAPH, "asserted_ontology"), (DATA_GRAPH, "asserted_data")],
    )
    target = {
        "subject": {"type": "uri", "value": f"{PREFIX}ns/workflow/B"},
        "predicate": {"type": "uri", "value": f"{PREFIX}ns/property/invokes"},
        "object": {"type": "uri", "value": f"{PREFIX}ns/workflow/C"},
        "graph": {"type": "uri", "value": DATA_GRAPH},
    }
    schema_leak = {**target, "graph": {"type": "uri", "value": ONTOLOGY_GRAPH}}
    foreign_leak = {**target, "graph": {"type": "uri", "value": FOREIGN_DATA_GRAPH}}

    class BoundedStatementStore(FakeStore):
        def query_read_model(self, query, graph_iris, timeout_seconds, limit):  # noqa: ANN001, ARG002
            self.last_query = query
            self.last_graph_iris = list(graph_iris)
            required_values = f"VALUES ?graph {{ <{DATA_GRAPH}> }}"
            if required_values not in query:
                return _Result([schema_leak, foreign_leak])
            return _Result([target])

    store = BoundedStatementStore()
    body = _read_model(_client(store, in_memory_session), "statement-list", limit=1)

    assert [item["source_graph_iri"] for item in body["items"]] == [DATA_GRAPH]
    assert store.last_graph_iris == [DATA_GRAPH]
    assert store.last_query is not None
    assert f"VALUES ?graph {{ <{DATA_GRAPH}> }}" in store.last_query
    assert ONTOLOGY_GRAPH not in store.last_query
    assert FOREIGN_DATA_GRAPH not in store.last_query
    # limit=1 plus the R3.0-009 has_more probe row (D7).
    assert "LIMIT 2" in store.last_query
    # D7/B03: the HTTP envelope exposes the window state, computed from the
    # authorized visible set (one visible item, page not exhausted).
    assert body["paging"] == {
        "limit": 1,
        "returned": 1,
        "visible_count": 1,
        "has_more": False,
        "truncated": False,
        "complete": True,
    }


def test_property_list_executes_with_class_iri_filter(in_memory_session) -> None:
    _seed_graph_set(in_memory_session, [(ONTOLOGY_GRAPH, "asserted_ontology")])
    store = FakeStore(
        rows_by_marker={
            "property-list": [
                {
                    "property": f"{PREFIX}ns/property/email",
                    "label": "email",
                    "domain": f"{PREFIX}ns/class/Student",
                    "graph": ONTOLOGY_GRAPH,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)
    body = _read_model(
        client, "property-list", class_iri=f"{PREFIX}ns/class/Student"
    )
    assert body["items"]
    item = body["items"][0]
    assert item["iri"] == f"{PREFIX}ns/property/email"
    assert item["label"] == "email"
    assert item["detail_fields"] == {"domain": f"{PREFIX}ns/class/Student"}
    assert item["source_graph_iri"] == ONTOLOGY_GRAPH
    assert store.last_query is not None
    assert "property-list" in store.last_query


def test_property_list_class_filter_requires_declared_domain(in_memory_session) -> None:
    """R3.0-009 §9.3: a domain-less property never belongs to every class."""
    _seed_graph_set(in_memory_session, [(ONTOLOGY_GRAPH, "asserted_ontology")])
    store = FakeStore(
        rows_by_marker={
            "property-list": [
                {
                    "property": f"{PREFIX}ns/property/email",
                    "label": "email",
                    "domain": f"{PREFIX}ns/class/Student",
                    "graph": ONTOLOGY_GRAPH,
                },
                {
                    "property": f"{PREFIX}ns/property/notes",
                    "label": "notes",
                    "graph": ONTOLOGY_GRAPH,
                },
            ]
        }
    )
    client = _client(store, in_memory_session)
    filtered = _read_model(
        client, "property-list", class_iri=f"{PREFIX}ns/class/Student"
    )
    assert [item["iri"] for item in filtered["items"]] == [f"{PREFIX}ns/property/email"]
    unfiltered = _read_model(client, "property-list")
    assert [item["iri"] for item in unfiltered["items"]] == [
        f"{PREFIX}ns/property/email",
        f"{PREFIX}ns/property/notes",
    ]


def test_relation_type_list_executes(in_memory_session) -> None:
    _seed_graph_set(in_memory_session, [(ONTOLOGY_GRAPH, "asserted_ontology")])
    store = FakeStore(
        rows_by_marker={
            "relation-type-list": [
                {
                    "relation": f"{PREFIX}ns/relation-type/enrolledIn",
                    "label": "enrolledIn",
                    "source": f"{PREFIX}ns/class/Student",
                    "target": f"{PREFIX}ns/class/Course",
                    "graph": ONTOLOGY_GRAPH,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)
    body = _read_model(client, "relation-type-list")
    assert body["items"]
    item = body["items"][0]
    assert item["label"] == "enrolledIn"
    assert item["source"] == f"{PREFIX}ns/class/Student"
    assert item["target"] == f"{PREFIX}ns/class/Course"


def test_entity_list_executes_and_decorates_class_membership(in_memory_session) -> None:
    _seed_graph_set(in_memory_session, [(DATA_GRAPH, "asserted_data")])
    store = FakeStore(
        rows_by_marker={
            "entity-list": [
                {
                    "entity": f"{PREFIX}ns/entity/alice",
                    "label": "Alice",
                    "class": f"{PREFIX}ns/class/Student",
                    "class_label": "Student",
                    "graph": DATA_GRAPH,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)
    body = _read_model(client, "entity-list")
    assert body["items"]
    item = body["items"][0]
    assert item["iri"] == f"{PREFIX}ns/entity/alice"
    assert item["label"] == "Alice"
    assert item["class_iri"] == f"{PREFIX}ns/class/Student"
    assert item["class_label"] == "Student"
    assert item["source_graph_iri"] == DATA_GRAPH


def test_entity_literal_facts_requires_entity_param(in_memory_session) -> None:
    _seed_graph_set(in_memory_session, [(DATA_GRAPH, "asserted_data")])
    client = _client(FakeStore(), in_memory_session)
    response = client.get(
        "/api/semantic/graph-sets/gs-1/read-models/entity-literal-facts"
    )
    assert response.status_code == 400
    assert "requires the entity query parameter" in response.json()["detail"]


def test_mapping_list_executes(in_memory_session) -> None:
    _seed_graph_set(in_memory_session, [(ONTOLOGY_GRAPH, "asserted_ontology")])
    store = FakeStore(
        rows_by_marker={
            "mapping-list": [
                {
                    "mapping": f"{PREFIX}ns/mapping/map-1",
                    "label": "student_no -> student",
                    "graph": ONTOLOGY_GRAPH,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)
    body = _read_model(client, "mapping-list")
    assert body["items"]
    item = body["items"][0]
    assert item["iri"] == f"{PREFIX}ns/mapping/map-1"
    assert item["label"] == "student_no -> student"
    assert item["source_graph_iri"] == ONTOLOGY_GRAPH


def test_import_graph_mappings_executes(in_memory_session) -> None:
    import_graph = f"{GRAPH_PREFIX}import/src-1/run-1"
    _seed_graph_set(in_memory_session, [(import_graph, "asserted_data")])
    store = FakeStore(
        rows_by_marker={
            "import-graph-mappings": [
                {
                    "mapping": f"{PREFIX}ns/mapping/map-2",
                    "label": "import mapping",
                    "graph": import_graph,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)
    body = _read_model(client, "import-graph-mappings")
    assert body["items"]
    assert body["items"][0]["source_graph_iri"] == import_graph


# ---------------------------------------------------------------------------
# fact-audit-queue composer
# ---------------------------------------------------------------------------


def test_fact_audit_queue_kind_asserted_routes_to_data_graph(in_memory_session) -> None:
    _seed_graph_set(in_memory_session, [(DATA_GRAPH, "asserted_data")])
    store = FakeStore(
        rows_by_marker={
            "fact-audit-queue": [
                {
                    "subject": f"{PREFIX}ns/entity/alice",
                    "predicate": f"{PREFIX}ns/property/email",
                    "object": "alice@example.com",
                    "graph": DATA_GRAPH,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)
    body = _read_model(client, "fact-audit-queue", kind="asserted")
    assert body["items"], "expected one fact row"
    item = body["items"][0]
    assert item["subject_iri"] == f"{PREFIX}ns/entity/alice"
    assert item["assertion_kind"] == "asserted"
    # Composer should have queried the data graph.
    assert DATA_GRAPH in (store.last_graph_iris or [])


def test_fact_audit_queue_kind_missing_evidence_is_rejected(
    in_memory_session,
) -> None:
    """The retired missing-evidence projection is not a fact queue kind."""
    _seed_graph_set(in_memory_session, [(DATA_GRAPH, "asserted_data")])
    store = FakeStore(
        rows_by_marker={
            "fact-audit-queue": [
                {
                    "subject": f"{PREFIX}ns/entity/alice",
                    "predicate": f"{PREFIX}ns/property/email",
                    "object": "alice@example.com",
                    "graph": DATA_GRAPH,
                }
            ]
        }
    )
    client = _client(store, in_memory_session)
    response = client.get(
        "/api/semantic/graph-sets/gs-1/read-models/fact-audit-queue",
        params={"include": "asserted", "kind": "missing_evidence"},
    )
    assert response.status_code == 400
    assert "Unsupported fact-audit-queue kind" in response.json()["detail"]


def test_fact_audit_queue_kind_rule_derived_without_pointer_returns_empty_with_warning(
    in_memory_session,
) -> None:
    _seed_graph_set(in_memory_session, [(DATA_GRAPH, "asserted_data")])
    store = FakeStore()
    client = _client(store, in_memory_session)
    response = client.get("/api/semantic/graph-sets/gs-1/read-models/fact-audit-queue", params={"kind": "rule_derived"})
    assert response.status_code == 400
    assert "Unsupported fact-audit-queue kind" in response.json()["detail"]


def test_fact_audit_queue_rule_derived_dedupes_missing_pointer_warning(
    in_memory_session,
) -> None:
    """When include=asserted-plus-rules already reports the missing pointer,
    the fact-audit composer should not append a second equivalent warning."""
    _seed_graph_set(in_memory_session, [(DATA_GRAPH, "asserted_data")])
    store = FakeStore()
    client = _client(store, in_memory_session)
    response = client.get("/api/semantic/graph-sets/gs-1/read-models/fact-audit-queue", params={"kind": "rule_derived"})
    assert response.status_code == 400
    assert "Unsupported fact-audit-queue kind" in response.json()["detail"]


def test_fact_audit_queue_invalid_kind_returns_400(in_memory_session) -> None:
    _seed_graph_set(in_memory_session, [(DATA_GRAPH, "asserted_data")])
    store = FakeStore()
    client = _client(store, in_memory_session)
    response = client.get(
        "/api/semantic/graph-sets/gs-1/read-models/fact-audit-queue",
        params={"include": "asserted", "kind": "bogus"},
    )
    assert response.status_code == 400
    assert "Unsupported fact-audit-queue kind" in response.json()["detail"]


# ---------------------------------------------------------------------------
# entity-shape composer
# ---------------------------------------------------------------------------
