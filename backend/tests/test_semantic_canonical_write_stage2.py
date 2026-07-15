"""Stage 2 §11 — canonical-write end-to-end integration tests.

These tests exercise the full FastAPI request flow through the
``POST /api/semantic/canonical-writes:compile-and-apply`` endpoint for each
Stage 2 product command kind. They verify:

* the request is accepted (200),
* the response reports ``applied: true``,
* the FakeStore captured a non-empty SPARQL UPDATE,
* the UPDATE contains the expected key terms (class IRI, label, etc.),
* the response's ``graph_revisions`` map bumps the affected graph.

The FakeStore stands in for Oxigraph; it captures the SPARQL UPDATE strings
emitted by ``apply_dataset_delta``. The graphs are registered in the in-memory
SQLite registry so the canonical-write service's managed-graph and
direct-editable-category checks succeed.

A small negative test exercises a non-existent class delete path.
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
from app.repositories.models import SemanticGraphRegistryModel
from app.repositories.rdf_store import RdfStoreRepository, SparqlResult, UpdateResult


PREFIX = "http://op.local/semantic/"
GRAPH_PREFIX = f"{PREFIX}graph/"


def _settings() -> Settings:
    return Settings(
        semantic_base_iri=f"{PREFIX}ns/",
        semantic_graph_iri_prefix=GRAPH_PREFIX,
        # Enable the canonical writer (default is legacy_only, which blocks
        # canonical writes; Stage 2 product APIs must route through the
        # canonical writer per spec §3.3.1).
        semantic_product_write_mode="canonical_only",
        semantic_read_mode="canonical",
        semantic_legacy_write_blocked=True,
    )


class FakeStore(RdfStoreRepository):
    """In-memory RDF store stub capturing UPDATE/QUERY strings.

    Subclasses the production repository so that ``apply_dataset_delta``
    and ``query_read_model`` work unchanged; only the I/O primitives are
    overridden.
    """

    def __init__(self) -> None:  # noqa: D401 - test helper
        # Skip the parent __init__ to avoid spinning up httpx clients against
        # a non-existent Oxigraph. We re-initialise the small set of attrs
        # apply_dataset_delta / query_read_model actually use.
        self.updates: list[str] = []
        self.clears: list[str] = []
        self.queries: list[str] = []
        self._stored: dict[str, str] = {}
        self._graphs: set[str] = set()

    def query_sparql(self, query: str, timeout_seconds: float, limit: int):
        self.queries.append(query)
        return SparqlResult(
            result={"head": {"vars": []}, "results": {"bindings": []}}
        )

    def update_sparql(self, update: str):
        self.updates.append(update)
        return UpdateResult()

    def export_dataset(self, format: str, graph_iris=None) -> str:  # noqa: A002
        return ""

    def graph_exists(self, graph_iri: str) -> bool:
        return graph_iri in self._graphs

    def get_graph(self, graph_iri: str, format: str) -> str:  # noqa: A002
        return self._stored.get(graph_iri, "")

    def set_graph(self, graph_iri: str, content: str) -> None:
        self._stored[graph_iri] = content
        self._graphs.add(graph_iri)

    def clear_graph(self, graph_iri: str):
        self.clears.append(graph_iri)
        self._graphs.discard(graph_iri)
        return UpdateResult()

    def graph_content_hash(self, graph_iri: str):
        return None


def _client(
    store: FakeStore,
    session: Session,
    settings: Settings | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: (settings or _settings())
    return TestClient(app)


def _register_graph(session: Session, graph_iri: str, category: str) -> None:
    """Insert a graph registry row so canonical-write sees a managed graph."""
    from uuid import uuid4

    session.add(
        SemanticGraphRegistryModel(
            id=str(uuid4()),
            graph_iri=graph_iri,
            category=category,
            semantic_owner_type="ontology",
            semantic_owner_id="ont-1",
            mutable_by_direct_edit=True,
        )
    )
    session.commit()


def _ontology_graph_iri() -> str:
    return f"{GRAPH_PREFIX}ontology/ont-1"


def _data_graph_iri() -> str:
    return f"{GRAPH_PREFIX}data/ont-1"


def _shapes_custom_graph_iri() -> str:
    return f"{GRAPH_PREFIX}shapes/ont-1/custom"


def _import_graph_iri() -> str:
    return f"{GRAPH_PREFIX}import/src-1/run-1"


def _reasoning_result_graph_iri() -> str:
    return f"{GRAPH_PREFIX}reasoning-result/run-7"


def _rule_result_graph_iri() -> str:
    return f"{GRAPH_PREFIX}rule-result/run-9"


def _create_graph_set(client: TestClient, members: list[dict[str, Any]]) -> str:
    response = client.post(
        "/api/semantic/graph-sets",
        json={
            "name": "stage2-e2e",
            "scope_type": "ontology",
            "scope_id": "ont-1",
            "members": members,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _apply(
    client: TestClient,
    graph_set_id: str,
    command_kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        "/api/semantic/canonical-writes:compile-and-apply",
        json={
            "command_kind": command_kind,
            "graph_set_id": graph_set_id,
            "payload": payload,
            "validate_edit": False,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _assert_apply_payload(
    body: dict[str, Any],
    store: FakeStore,
    expected_graph_iri: str,
    keywords: list[str],
) -> None:
    assert body["applied"] is True
    assert store.updates, "no SPARQL UPDATE captured by FakeStore"
    # The graph_iri must be bumped in revisions.
    assert body["graph_revisions"].get(expected_graph_iri, 0) >= 1
    update_blob = "\n".join(store.updates)
    for kw in keywords:
        assert kw in update_blob, (
            f"expected keyword {kw!r} in SPARQL UPDATE; got:\n{update_blob}"
        )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _seed_default_graph_set(client: TestClient, session: Session) -> str:
    """Pre-register an ontology + data + custom shape graph and create a
    graph set with all three roles."""
    for graph_iri, category in [
        (_ontology_graph_iri(), "ontology"),
        (_data_graph_iri(), "data"),
        (_shapes_custom_graph_iri(), "data"),
    ]:
        _register_graph(session, graph_iri, category)
    return _create_graph_set(
        client,
        members=[
            {"graph_iri": _ontology_graph_iri(), "role": "asserted_ontology"},
            {"graph_iri": _data_graph_iri(), "role": "asserted_data"},
            {"graph_iri": _shapes_custom_graph_iri(), "role": "shape_graph_custom"},
        ],
    )


# ---------------------------------------------------------------------------
# Classes — 10 kinds
# ---------------------------------------------------------------------------


def test_update_class_apply_writes_label_replace_to_ontology_graph(
    in_memory_session,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "update_class",
        {
            "ontology_id": "ont-1",
            "class_id": "class-1",
            "name": "Student v2",
        },
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        [
            "DELETE { GRAPH",
            "WHERE { GRAPH",
            "INSERT DATA",
            "/ns/class/class-1>",
            '"Student v2"',
        ],
    )


def test_delete_class_apply_writes_subject_wildcard_delete_and_soft_marker(
    in_memory_session,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "delete_class",
        {"ontology_id": "ont-1", "class_id": "class-1"},
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        ["/ns/class/class-1>", "deprecated"],
    )


def test_create_property_apply_writes_owl_datatype_property(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "create_property",
        {
            "ontology_id": "ont-1",
            "class_id": "class-1",
            "property_id": "prop-1",
            "name": "email",
            "description": "Student email",
            "datatype": "xsd:string",
        },
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        [
            "/ns/property/prop-1>",
            "DatatypeProperty",
            '"email"',
        ],
    )


def test_update_property_apply_replaces_label_and_range(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "update_property",
        {
            "ontology_id": "ont-1",
            "property_id": "prop-1",
            "name": "email v2",
            "datatype": "xsd:integer",
        },
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        ["/ns/property/prop-1>", '"email v2"'],
    )


def test_delete_property_apply_emits_subject_wildcard_delete(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "delete_property",
        {"ontology_id": "ont-1", "property_id": "prop-1"},
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        ["/ns/property/prop-1>", "?p", "?o"],
    )


def test_update_relation_type_apply_replaces_label_and_endpoints(
    in_memory_session,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "update_relation_type",
        {
            "ontology_id": "ont-1",
            "relation_type_id": "rel-1",
            "name": "enrolledIn v2",
            "source_class_id": "class-2",
            "target_class_id": "class-3",
        },
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        ["/ns/relation-type/rel-1>", '"enrolledIn v2"'],
    )


def test_delete_relation_type_apply_emits_subject_wildcard_delete(
    in_memory_session,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "delete_relation_type",
        {"ontology_id": "ont-1", "relation_type_id": "rel-1"},
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        ["/ns/relation-type/rel-1>", "?p", "?o"],
    )


def test_create_shape_apply_writes_node_shape_into_custom_subgraph(
    in_memory_session,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "create_shape",
        {
            "ontology_id": "ont-1",
            "target_class_id": "class-1",
            "shape_id": "shape-1",
            "constraints": [{"path_id": "prop-1", "min_count": 1}],
        },
    )
    _assert_apply_payload(
        body,
        store,
        _shapes_custom_graph_iri(),
        [
            "/ns/shape/shape-1>",
            "#NodeShape",
            "#targetClass",
            "#minCount",
        ],
    )


def test_update_shape_apply_replaces_constraints(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "update_shape",
        {
            "ontology_id": "ont-1",
            "target_class_id": "class-1",
            "shape_id": "shape-1",
            "constraints": [{"path_id": "prop-2", "max_count": 1}],
        },
    )
    _assert_apply_payload(
        body,
        store,
        _shapes_custom_graph_iri(),
        ["/ns/shape/shape-1>", "#maxCount"],
    )


def test_delete_shape_apply_emits_subject_wildcard_delete(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "delete_shape",
        {"ontology_id": "ont-1", "shape_id": "shape-1"},
    )
    _assert_apply_payload(
        body,
        store,
        _shapes_custom_graph_iri(),
        ["/ns/shape/shape-1>", "?p", "?o"],
    )


# ---------------------------------------------------------------------------
# Entities — 5 kinds
# ---------------------------------------------------------------------------


def test_create_entity_apply_writes_named_individual_into_data_graph(
    in_memory_session,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "create_entity",
        {
            "ontology_id": "ont-1",
            "entity_id": "entity-1",
            "class_iri_or_legacy_id": "class-1",
            "label": "Alice",
            "aliases": ["Al"],
            "properties": {
                "http://op.local/ns/property/email": "alice@example.com",
            },
        },
    )
    _assert_apply_payload(
        body,
        store,
        _data_graph_iri(),
        [
            "/ns/entity/entity-1>",
            "NamedIndividual",
            '"Alice"',
        ],
    )


def test_update_entity_apply_replaces_label_aliases_and_properties(
    in_memory_session,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "update_entity",
        {
            "ontology_id": "ont-1",
            "entity_id": "entity-1",
            "label": "Alice v2",
            "aliases": ["Al2"],
            "properties": {
                "http://op.local/ns/property/email": "alice2@example.com",
            },
        },
    )
    _assert_apply_payload(
        body,
        store,
        _data_graph_iri(),
        ["/ns/entity/entity-1>", '"Alice v2"'],
    )


def test_delete_entity_apply_cascades_to_relations(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "delete_entity",
        {"ontology_id": "ont-1", "entity_id": "entity-1"},
    )
    _assert_apply_payload(
        body,
        store,
        _data_graph_iri(),
        ["/ns/entity/entity-1>", "?s", "?p"],
    )


def test_create_relation_apply_writes_asserted_relation_triple(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "create_relation",
        {
            "ontology_id": "ont-1",
            "source_entity_iri": "http://op.local/ns/entity/entity-1",
            "relation_type_iri": "http://op.local/ns/relation-type/rel-1",
            "target_entity_iri": "http://op.local/ns/entity/entity-2",
        },
    )
    _assert_apply_payload(
        body,
        store,
        _data_graph_iri(),
        [
            "/ns/entity/entity-1>",
            "/ns/relation-type/rel-1>",
            "/ns/entity/entity-2>",
        ],
    )


def test_delete_relation_apply_targets_specific_triple_pattern(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "delete_relation",
        {
            "ontology_id": "ont-1",
            "source_entity_iri": "http://op.local/ns/entity/entity-1",
            "relation_type_iri": "http://op.local/ns/relation-type/rel-1",
            "target_entity_iri": "http://op.local/ns/entity/entity-2",
        },
    )
    _assert_apply_payload(
        body,
        store,
        _data_graph_iri(),
        [
            "/ns/entity/entity-1>",
            "/ns/relation-type/rel-1>",
            "/ns/entity/entity-2>",
        ],
    )


# ---------------------------------------------------------------------------
# Catalog — 3 kinds
# ---------------------------------------------------------------------------


def test_create_mapping_apply_writes_semantic_mapping(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "create_mapping",
        {
            "ontology_id": "ont-1",
            "mapping_id": "map-1",
            "external_field_iri": "http://op.local/ns/external-field/field-1",
            "target_type": "class",
            "target_iri": "http://op.local/ns/class/class-1",
            "join_key": '{"entity_property": "id"}',
            "confidence": 0.92,
            "owner": "owner-1",
        },
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        ["/ns/mapping/map-1>", "SemanticMapping", "externalField"],
    )


def test_update_mapping_apply_patches_join_key_confidence_and_owner(
    in_memory_session,
) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "update_mapping",
        {
            "ontology_id": "ont-1",
            "mapping_id": "map-1",
            "join_key": '{"k": "v2"}',
            "confidence": 0.8,
            "owner": "owner-3",
        },
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        ["/ns/mapping/map-1>", "owner-3"],
    )


def test_delete_mapping_apply_emits_subject_wildcard_delete(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "delete_mapping",
        {"ontology_id": "ont-1", "mapping_id": "map-1"},
    )
    _assert_apply_payload(
        body,
        store,
        _ontology_graph_iri(),
        ["/ns/mapping/map-1>", "?p", "?o"],
    )


# ---------------------------------------------------------------------------
# FactAudit — 1 kind
# ---------------------------------------------------------------------------


def test_review_assertion_apply_writes_rdf_star_reification(in_memory_session) -> None:
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    body = _apply(
        client,
        graph_set_id,
        "review_assertion",
        {
            "ontology_id": "ont-1",
            "assertion_kind": "asserted",
            "subject_iri": "http://op.local/ns/entity/alice",
            "predicate_iri": "http://op.local/ns/property/email",
            "object_value": "alice@example.com",
            "decision": "approved",
            "reason": "looks good",
            "reviewed_by": "user:alice",
        },
    )
    _assert_apply_payload(
        body,
        store,
        _data_graph_iri(),
        [
            "auditStatus",
            "approved",
            "reviewReason",
            "looks good",
        ],
    )


# ---------------------------------------------------------------------------
# Negative paths
# ---------------------------------------------------------------------------


def test_review_assertion_rejected_decision_without_fix_proposal_returns_400(
    in_memory_session,
) -> None:
    """Compiler-side validation surfaces as a structured 400 (the schema has
    already accepted the kind, so the error happens inside the service)."""
    store = FakeStore()
    client = _client(store, in_memory_session)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    response = client.post(
        "/api/semantic/canonical-writes:compile-and-apply",
        json={
            "command_kind": "review_assertion",
            "graph_set_id": graph_set_id,
            "payload": {
                "ontology_id": "ont-1",
                "assertion_kind": "asserted",
                "subject_iri": "http://op.local/ns/entity/alice",
                "predicate_iri": "http://op.local/ns/property/email",
                "object_value": "alice@example.com",
                "decision": "rejected",
                "reason": "nope",
                "reviewed_by": "user:alice",
            },
            "validate_edit": False,
        },
    )
    assert response.status_code == 400
    assert store.updates == []


def test_canonical_writer_blocked_when_in_legacy_only_mode(in_memory_session) -> None:
    """Default mode (legacy_only) refuses canonical writes with 409.

    Documents the mode gate so accidental rollback of the Stage 2 cutover is
    caught at the API boundary.
    """
    store = FakeStore()
    settings = Settings(
        semantic_base_iri=f"{PREFIX}ns/",
        semantic_graph_iri_prefix=GRAPH_PREFIX,
        semantic_product_write_mode="legacy_only",
        semantic_read_mode="canonical",
        semantic_legacy_write_blocked=False,
    )
    client = _client(store, in_memory_session, settings=settings)
    graph_set_id = _seed_default_graph_set(client, in_memory_session)

    response = client.post(
        "/api/semantic/canonical-writes:compile-and-apply",
        json={
            "command_kind": "update_class",
            "graph_set_id": graph_set_id,
            "payload": {
                "ontology_id": "ont-1",
                "class_id": "class-1",
                "name": "X",
            },
            "validate_edit": False,
        },
    )
    assert response.status_code == 409
    assert store.updates == []
