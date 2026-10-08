import json
import os

import pytest

from app.services.semantic_read_model import ReadModelError, SemanticReadModelService


class FakeSparqlResult:
    def __init__(self, rows):
        self._rows = rows

    @property
    def bindings(self):
        return self._rows


class FakeStore:
    def __init__(self, rows_by_template: dict[str, list[dict[str, str]]]):
        self.rows_by_template = rows_by_template
        self.last_query: str | None = None
        self.last_graph_iris: list[str] | None = None
        self.last_limit: int | None = None

    def query_read_model(self, query, graph_iris, timeout_seconds, limit):
        self.last_query = query
        self.last_graph_iris = list(graph_iris)
        self.last_limit = limit
        for marker, rows in self.rows_by_template.items():
            if marker in query:
                return FakeSparqlResult(rows)
        return FakeSparqlResult([])


class FakeScopeResolver:
    def __init__(self, resolution):
        self._resolution = resolution

    def resolve(self, graph_set_id, include="asserted", allow_stale_derived=True):
        # Replace dataclass to reflect the include parameter so the service
        # can add derived-result graphs as appropriate.
        from dataclasses import replace

        return replace(self._resolution, include=include)


def _resolution(
    graph_iris,
    reasoning=None,
    rule=None,
    signature="sig-1",
    members=None,
    derived_state=None,
):
    from app.services.semantic_read_scope import ScopeResolution

    # Handle reasoning/rule being either str (graph IRI) or dict (derived state).
    reasoning_iri = reasoning if isinstance(reasoning, str) else None
    rule_iri = rule if isinstance(rule, str) else None

    if derived_state is None:
        derived_state = {}
        if isinstance(reasoning, dict):
            derived_state["reasoning"] = reasoning
        if isinstance(rule, dict):
            derived_state["rule"] = rule

    # Auto-create members from graph_iris when not explicitly provided.
    if members is None:
        members = _members_from_iris(graph_iris, derived_state)
    elif not isinstance(members, list):
        members = list(members)

    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature=signature,
        include="asserted",
        source_graph_iris=graph_iris, shape_graph_iris=[],

        governance_graph_iris=[],
        reasoning_result_graph_iri=reasoning_iri,
        derived_state=derived_state,
        warnings=[],
        members=list(members),
    )


def _members_from_iris(graph_iris, derived_state):
    from app.services.semantic_read_scope import ScopeMember

    result = []
    for iri in graph_iris:
        if "/ontology/" in iri:
            role = "asserted_ontology"
        elif "/data/" in iri:
            role = "asserted_data"
        else:
            role = "asserted_data"
        result.append(
            ScopeMember(
                graph_iri=iri,
                role=role,
                derived_state=dict(derived_state),
            )
        )
    return result


def test_schema_summary_returns_envelope_with_assertion_metadata():
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/ontology/ov-1"]))
    store = FakeStore(
        {
            "schema-summary": [
                {
                    "class": "http://op/s/class/student",
                    "label": "Student",
                    "graph": "http://op/s/graph/ontology/ov-1",
                },
                {
                    "class": "http://op/s/class/course",
                    "label": "Course",
                    "graph": "http://op/s/graph/ontology/ov-1",
                },
            ]
        }
    )
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)
    envelope = service.read_model("gs-1", "ontology-schema-summary", include="asserted")
    assert envelope["graph_set_id"] == "gs-1"
    assert envelope["source_signature"] == "sig-1"
    assert envelope["projection_version"].startswith("semantic-read-v")
    assert len(envelope["items"]) == 2
    item = envelope["items"][0]
    assert item["assertion_kind"] == "asserted"
    assert item["source_graph_iri"] == "http://op/s/graph/ontology/ov-1"
    assert "evidence_status" not in item
    assert "staleness" in item


def test_unknown_model_raises():
    resolver = FakeScopeResolver(_resolution(["http://op/s/graph/data/ov-1"]))
    store = FakeStore({})
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)
    try:
        service.read_model("gs-1", "no-such-model")
        raise AssertionError("expected ReadModelError")
    except ReadModelError as exc:
        assert "no-such-model" in str(exc)


def test_entity_list_exposes_explicit_canonical_identity_projection():
    """Protocol receives semantic IDs and IRIs as independent backend fields."""

    data_iri = "https://example/graph/data/r23003"
    entity_iri = "https://example/entity/unknown-a"
    class_iri = "https://example/class/ExplicitUnknown"
    resolution = _resolution([data_iri])
    store = FakeStore(
        {
            "entity-list": [
                {
                    "entity": {"value": entity_iri, "type": "uri"},
                    "semantic_id": {"value": "unknown-a", "type": "literal"},
                    "class": {"value": class_iri, "type": "uri"},
                    "class_semantic_id": {"value": "ExplicitUnknown", "type": "literal"},
                    "graph": {"value": data_iri, "type": "uri"},
                }
            ]
        }
    )
    service = SemanticReadModelService(rdf_store=store, scope_resolver=FakeScopeResolver(resolution))

    item = service.read_model("gs-1", "entity-list")["items"][0]

    assert item["semantic_id"] == "unknown-a"
    assert item["entity_iri"] == entity_iri
    assert item["class_semantic_id"] == "ExplicitUnknown"
    assert item["class_iri"] == class_iri


def test_access_view_filters_rows_referencing_unauthorized_members():
    from app.services.semantic_access import SemanticAccessView

    resolver = FakeScopeResolver(
        _resolution(["http://op/s/graph/data/a", "http://op/s/graph/data/b"])
    )
    store = FakeStore(
        {
            "schema-summary": [
                {
                    "class": "http://op/s/class/x",
                    "label": "X",
                    "graph": "http://op/s/graph/data/a",
                },
                {
                    "class": "http://op/s/class/y",
                    "label": "Y",
                    "graph": "http://op/s/graph/data/b",
                },
            ]
        }
    )
    view = SemanticAccessView(
        requires_filtering=True,
        _unauthorized_iris=frozenset({"http://op/s/class/y"}),
    )
    service = SemanticReadModelService(
        rdf_store=store, scope_resolver=resolver, access_view=view
    )
    envelope = service.read_model("gs-1", "ontology-schema-summary")
    classes = {item["class_iri"] for item in envelope["items"]}
    assert classes == {"http://op/s/class/x"}
    assert envelope.get("warnings", []) == []


# ------------------------------------------------------------------
# graph-set-staleness composer
# ------------------------------------------------------------------


def test_graph_set_staleness_summary_assembles_members_and_count():
    """graph-set-staleness summary composes members, staleness, missing-evidence count.

    Phase 3 refactor: missing_evidence_count now comes from Postgres (the
    fact_evidence_bindings table), not the SPARQL COUNT that the old FakeStore
    row used to feed. Without a real session the count is 0 — the staleness
    composer no longer consults the SPARQL template at all.
    """

    resolution = _resolution(
        graph_iris=[
            "https://example/graph/ontology/x",
            "https://example/graph/data/x",
        ],
        reasoning={"status": "stale"},
        rule={"status": "current"},
    )
    store = FakeStore({
        "graph-set-staleness": [{"count": {"value": "3"}}],
    })
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=1,
    )

    envelope = service.read_model(
        graph_set_id="gs-1",
        model_name="graph-set-staleness",
        field_set="summary",
    )

    assert envelope["model_name"] == "graph-set-staleness"
    assert len(envelope["items"]) == 1
    item = envelope["items"][0]
    assert item["graph_set_id"] == "gs-1"
    assert "missing_evidence_count" not in item
    # Verify member-level data
    assert len(item["members"]) == 2
    roles = {m["role"] for m in item["members"]}
    assert roles == {"asserted_ontology", "asserted_data"}

    assert all("reasoning_stale" not in member for member in item["members"])
    assert "stale_derived_count" not in item

def test_graph_set_staleness_summary_handles_no_derived_pointers():
    """Missing derived pointers should yield null staleness, not crash."""

    resolution = _resolution(graph_iris=["https://example/graph/data/x"])
    store = FakeStore({"graph-set-staleness": [{"count": {"value": "0"}}]})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=1,
    )

    envelope = service.read_model(
        graph_set_id="gs-1",
        model_name="graph-set-staleness",
        field_set="summary",
    )
    member = envelope["items"][0]["members"][0]
    # With no derived state from resolver, staleness fields are None
    assert member.get("reasoning_stale") is None
    assert member.get("rule_stale") is None
    assert member.get("validation_stale") is None
    assert member.get("editable") is True
    assert member.get("role") == "asserted_data"


# Stage 2 §5.3 — entity-shape composer delegation ---------------------------------------


class FakeShapeEndpointService:
    """Test double for SemanticShapeEndpointService.read_merged_guidance."""

    def __init__(self, response: dict):
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def read_merged_guidance(self, graph_set_id: str, class_iri: str) -> dict:
        self.calls.append((graph_set_id, class_iri))
        return self._response


# Stage 2 §6.3 — fact-audit-queue composer ----------------------------------------------


def test_fact_audit_queue_kind_asserted_queries_data_graph_only():
    """kind=asserted restricts the SPARQL to asserted_data members and
    decorates each row with assertion_kind=asserted."""
    data_iri = "http://op.local/graph/data/ont-1"
    resolution = _resolution(
        graph_iris=[data_iri],
        reasoning="http://op.local/graph/reasoning-result/run-1",
        rule="http://op.local/graph/rule-result/run-2",
    )
    store = FakeStore({
        "fact-audit-queue": [
            {
                "subject": "http://op.local/ns/entity/alice",
                "subject_label": "Alice",
                "predicate": "http://op.local/ns/property/email",
                "predicate_label": "email",
                "object": "alice@example.com",
                "graph": data_iri,
            },
        ],
    })
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=500,
    )
    envelope = service.read_model(
        graph_set_id="gs-1",
        model_name="fact-audit-queue",
        kind="asserted",
        include="full-working-view",
    )
    # Store received only the data graph.
    assert store.last_graph_iris == [data_iri]
    assert len(envelope["items"]) == 1
    row = envelope["items"][0]
    assert row["subject_iri"] == "http://op.local/ns/entity/alice"
    assert row["predicate_iri"] == "http://op.local/ns/property/email"
    assert row["assertion_kind"] == "asserted"
    assert "evidence_status" not in row
    assert row["stale"] is False


def test_fact_audit_queue_kind_rule_derived_is_retired():
    """kind=rule_derived restricts the SPARQL to the effective rule-result
    graph."""
    data_iri = "http://op.local/graph/data/ont-1"
    rule_iri = "http://op.local/graph/rule-result/run-9"
    resolution = _resolution(
        graph_iris=[data_iri],
        rule=rule_iri,
        derived_state={
            "rule": {
                "status": "current",
                "run_id": "run-9",
                "result_graph_iri": rule_iri,
            },
        },
    )
    store = FakeStore({
        "fact-audit-queue": [
            {
                "subject": "http://op.local/ns/entity/alice",
                "subject_label": "Alice",
                "predicate": "http://op.local/ns/property/category",
                "predicate_label": "category",
                "object": "vip",
                "graph": rule_iri,
            },
        ],
    })
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=500,
    )
    with pytest.raises(ReadModelError, match="Unsupported fact-audit-queue kind"):
        service.read_model(graph_set_id="gs-1", model_name="fact-audit-queue", kind="rule_derived")
    assert store.last_query is None


def test_fact_audit_queue_rejects_missing_evidence_kind():
    """The retired missing-evidence projection is not a normal read model."""
    data_iri = "http://op.local/graph/data/ont-1"
    resolution = _resolution(graph_iris=[data_iri])
    store = FakeStore({
        "fact-audit-queue": [
            {
                "subject": "http://op.local/ns/entity/alice",
                "subject_label": "Alice",
                "predicate": "http://op.local/ns/property/email",
                "predicate_label": "email",
                "object": "alice@example.com",
                "graph": data_iri,
            },
        ],
    })
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=500,
    )
    with pytest.raises(ReadModelError, match="Unsupported fact-audit-queue kind"):
        service.read_model(
            graph_set_id="gs-1",
            model_name="fact-audit-queue",
            kind="missing_evidence",
        )


def test_fact_audit_queue_invalid_kind_raises_read_model_error():
    """An unknown kind value surfaces as a ReadModelError."""
    data_iri = "http://op.local/graph/data/ont-1"
    resolution = _resolution(graph_iris=[data_iri])
    store = FakeStore({})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=500,
    )
    import pytest

    with pytest.raises(ReadModelError) as exc_info:
        service.read_model(
            graph_set_id="gs-1",
            model_name="fact-audit-queue",
            kind="not_a_kind",
        )
    assert "kind" in str(exc_info.value).lower()


# R3.0-007 — entity-detail graph scoping and LIMIT semantics ------------------


R307_DATA_GRAPH = "https://r307.test/data/graph-1"
R307_REASONING_GRAPH = "https://r307.test/reasoning-result/run-1"
R307_RULE_GRAPH = "https://r307.test/rule-result/run-2"


def _r307_entity_detail_service(store, resolution=None, **service_kwargs):
    resolution = resolution or _resolution([R307_DATA_GRAPH])
    return SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        **service_kwargs,
    )


def test_entity_detail_compiles_with_graph_scoping_values():
    """S1: entity-detail compiles to a VALUES-bounded query (R3.0-007).

    The compiled query must bind ?graph to the scope's data graph IRIs so a
    shared store is not scanned across every project's named graphs.
    """
    store = FakeStore(
        {
            "entity-detail": [
                {
                    "entity": "https://r307.test/entity/T1",
                    "label": "r307-target",
                    "graph": R307_DATA_GRAPH,
                }
            ]
        }
    )
    service = _r307_entity_detail_service(store)

    envelope = service.read_model("gs-1", "entity-detail")

    assert store.last_query is not None
    assert "{graph_iris}" not in store.last_query
    assert f"VALUES ?graph {{ <{R307_DATA_GRAPH}> }}" in store.last_query
    # Default limit plus the R3.0-009 has_more probe row (D7).
    assert "LIMIT 501" in store.last_query
    assert len(envelope["items"]) == 1
    assert envelope["items"][0]["iri"] == "https://r307.test/entity/T1"


def test_entity_detail_without_source_graphs_returns_empty_without_query():
    """B1: no source graphs -> fail-closed empty envelope, no query issued."""
    store = FakeStore({"entity-detail": []})
    service = _r307_entity_detail_service(store, resolution=_resolution([]))

    envelope = service.read_model("gs-1", "entity-detail")

    assert envelope["items"] == []
    assert envelope["warnings"][0]["code"] == "read_model_no_source_graphs"
    assert store.last_query is None


def test_entity_detail_limit_semantics_bound_by_default_limit():
    """B4: the limit passed to the store and the compiled LIMIT reflect
    min(limit or default_limit, default_limit)."""
    # Default: no explicit limit -> template default_limit of 500, plus one
    # probe row so the envelope can report has_more (R3.0-009 §6.2 / D7).
    store = FakeStore({"entity-detail": []})
    _r307_entity_detail_service(store).read_model("gs-1", "entity-detail")
    assert store.last_limit == 501
    assert "LIMIT 501" in store.last_query

    # Explicit smaller limit is honored (plus the probe row).
    store = FakeStore({"entity-detail": []})
    _r307_entity_detail_service(store).read_model("gs-1", "entity-detail", limit=100)
    assert store.last_limit == 101
    assert "LIMIT 101" in store.last_query

    # Oversized limit is capped at default_limit (500) plus the probe row.
    store = FakeStore({"entity-detail": []})
    _r307_entity_detail_service(store).read_model("gs-1", "entity-detail", limit=9999)
    assert store.last_limit == 501
    assert "LIMIT 501" in store.last_query


def test_envelope_reports_paging_state_relative_to_visible_set():
    """D7 / R3.0-009 §6.2: every page carries machine-readable window state.

    ``has_more`` is computed from the authorized visible set (limit+1 probe
    row), ``truncated`` only when the fetch ceiling was reached, and
    ``complete`` is the conjunction of neither happening.
    """

    def _rows(count):
        return [
            {
                "entity": f"https://r307.test/entity/T{index}",
                "label": f"row-{index}",
                "graph": R307_DATA_GRAPH,
            }
            for index in range(count)
        ]

    # Under the limit: the page is complete, nothing more to fetch.
    store = FakeStore({"entity-detail": _rows(3)})
    envelope = _r307_entity_detail_service(store).read_model(
        "gs-1", "entity-detail", limit=100
    )
    assert envelope["paging"] == {
        "limit": 100,
        "returned": 3,
        "visible_count": 3,
        "has_more": False,
        "truncated": False,
        "complete": True,
    }

    # The probe row beyond the limit reports has_more, and the fetch ceiling
    # that made it visible is reported as truncation.
    store = FakeStore({"entity-detail": _rows(101)})
    envelope = _r307_entity_detail_service(store).read_model(
        "gs-1", "entity-detail", limit=100
    )
    assert envelope["paging"] == {
        "limit": 100,
        "returned": 100,
        "visible_count": 101,
        "has_more": True,
        "truncated": True,
        "complete": False,
    }
    assert len(envelope["items"]) == 100


def test_entity_list_paging_survives_post_processing_head_room():
    """D7: entity-list fetches extra rows for aggregation, so the ceiling can
    be hit while the aggregated page still fits — truncated must say so rather
    than claiming a complete projection."""
    data_iri = "https://example/graph/data/r23003"

    def _row(entity_index, class_index):
        return {
            "entity": {"value": f"https://example/entity/e{entity_index}", "type": "uri"},
            "semantic_id": {"value": f"e{entity_index}", "type": "literal"},
            "class": {"value": f"https://example/class/C{class_index}", "type": "uri"},
            "graph": {"value": data_iri, "type": "uri"},
        }

    # 8 class rows per entity x 50 entities plus 8 more for entity 0 = 408
    # rows, which is exactly the expanded fetch ceiling for limit=50, yet the
    # aggregation collapses to exactly 50 entities (one full page).
    rows = [_row(index, class_index) for index in range(50) for class_index in range(8)]
    rows.extend(_row(0, class_index) for class_index in range(100, 108))
    store = FakeStore({"entity-list": rows})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
    )
    envelope = service.read_model("gs-1", "entity-list", limit=50)

    assert envelope["paging"] == {
        "limit": 50,
        "returned": 50,
        "visible_count": 50,
        "has_more": False,
        "truncated": True,
        "complete": False,
    }
    assert len(envelope["items"]) == 50
    assert envelope["warnings"][0]["code"] == "read_model_rows_truncated"


def test_every_executable_template_binds_graph_iris():
    """F1 conservation gate: any template body with a SELECT must carry the
    {graph_iris} placeholder so no future template scans all named graphs."""
    from app.services.semantic_sparql_templates import list_templates

    violations = [
        template.name
        for template in list_templates()
        if "SELECT" in template.body and "{graph_iris}" not in template.body
    ]
    assert violations == []


def test_entity_detail_values_addition_preserves_decorated_row_shape():
    """F2: adding VALUES ?graph keeps ?graph a projected variable, so the
    decorator still maps it to source_graph_iri without any drift."""
    store = FakeStore(
        {
            "entity-detail": [
                {
                    "entity": "https://r307.test/entity/T1",
                    "label": "r307-target",
                    "graph": R307_DATA_GRAPH,
                }
            ]
        }
    )
    service = _r307_entity_detail_service(store)

    item = service.read_model("gs-1", "entity-detail")["items"][0]

    assert item["source_graph_iri"] == R307_DATA_GRAPH
    assert item["assertion_kind"] == "asserted"
    assert "evidence_status" not in item
    assert item["iri"] == "https://r307.test/entity/T1"
    assert item["label"] == "r307-target"


# ------------------------------------------------------------------
# R3.0-003 relational schema mapping read models
# ------------------------------------------------------------------

R3003_ONTOLOGY_GRAPH = "http://op/s/graph/ontology/ov-r3003"
R3003_BASE = "http://op/s/"


def _r3003_table_mapping_rows():
    return [
        {
            "table_mapping": f"{R3003_BASE}table-mapping/tm-1",
            "label": "work orders mapping",
            "table_name": "service.work_orders",
            "mapped_class": f"{R3003_BASE}class/WorkOrder",
            "column_mappings": json.dumps(
                [
                    {
                        "property_iri": f"{R3003_BASE}property/workOrderNo",
                        "column": "work_order_no",
                        "role": "business_key",
                    }
                ],
                ensure_ascii=False,
            ),
            "schema_source": "schema-dump-2026-08-22",
            "semantic_version": "v1",
            "graph": R3003_ONTOLOGY_GRAPH,
        }
    ]


def test_r3003_table_mapping_list_passes_detail_fields():
    resolver = FakeScopeResolver(_resolution([R3003_ONTOLOGY_GRAPH]))
    store = FakeStore({"table-mapping-list": _r3003_table_mapping_rows()})
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)

    item = service.read_model("gs-1", "table-mapping-list")["items"][0]

    assert item["iri"] == f"{R3003_BASE}table-mapping/tm-1"
    assert item["label"] == "work orders mapping"
    detail = item["detail_fields"]
    assert detail["table_name"] == "service.work_orders"
    assert detail["mapped_class"] == f"{R3003_BASE}class/WorkOrder"
    assert detail["schema_source"] == "schema-dump-2026-08-22"
    assert detail["semantic_version"] == "v1"
    assert json.loads(detail["column_mappings"])[0]["column"] == "work_order_no"


def test_r3003_detail_templates_bind_entity_iri():
    resolver = FakeScopeResolver(_resolution([R3003_ONTOLOGY_GRAPH]))
    store = FakeStore({"table-mapping-detail": _r3003_table_mapping_rows()})
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)
    entity = f"{R3003_BASE}table-mapping/tm-1"

    try:
        service.read_model("gs-1", "table-mapping-detail")
        raise AssertionError("expected ReadModelError")
    except ReadModelError as exc:
        assert "requires an entity IRI" in str(exc)

    item = service.read_model("gs-1", "table-mapping-detail", entity_iri=entity)["items"][0]
    assert item["detail_fields"]["table_name"] == "service.work_orders"
    assert f"VALUES ?table_mapping {{ <{entity}> }}" in store.last_query


def test_r3003_all_mapping_templates_declare_detail_variables():
    from app.services.semantic_sparql_templates import get_template

    for name in (
        "table-mapping-list",
        "table-mapping-detail",
        "join-mapping-list",
        "join-mapping-detail",
        "enum-meaning-list",
        "enum-meaning-detail",
        "metric-list",
        "metric-detail",
    ):
        template = get_template(name)
        assert template.detail_variables, name
        assert template.required_roles == ("asserted_ontology",), name


def test_r3003_existing_templates_stay_without_detail_fields():
    """Byte-regression: templates without declared detail variables keep
    their historical response shape (no detail_fields key)."""
    resolver = FakeScopeResolver(_resolution([R3003_ONTOLOGY_GRAPH]))
    store = FakeStore(
        {
            "schema-summary": [
                {
                    "class": f"{R3003_BASE}class/WorkOrder",
                    "label": "Work Order",
                    "graph": R3003_ONTOLOGY_GRAPH,
                }
            ]
        }
    )
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)
    item = service.read_model("gs-1", "ontology-schema-summary")["items"][0]
    assert "detail_fields" not in item


def test_r3003_access_view_hides_rows_by_detail_field_and_embedded_json():
    """Authorization A-consistency: a mapping row whose mapped_class or
    embedded column_mappings JSON references an unauthorized member is
    hidden entirely, without any change to decision logic."""
    from app.services.semantic_access import SemanticAccessView

    unauthorized = f"{R3003_BASE}class/ProtectedParty"
    rows = [
        _r3003_table_mapping_rows()[0],
        {
            "table_mapping": f"{R3003_BASE}table-mapping/tm-2",
            "label": "protected mapping",
            "table_name": "service.protected",
            "mapped_class": unauthorized,
            "column_mappings": json.dumps(
                [
                    {
                        "property_iri": f"{R3003_BASE}property/protectedNo",
                        "column": "protected_no",
                        "role": "business_key",
                    }
                ]
            ),
            "graph": R3003_ONTOLOGY_GRAPH,
        },
    ]
    resolver = FakeScopeResolver(_resolution([R3003_ONTOLOGY_GRAPH]))
    store = FakeStore({"table-mapping-list": rows})
    view = SemanticAccessView(
        requires_filtering=True,
        _unauthorized_iris=frozenset({unauthorized, f"{R3003_BASE}property/protectedNo"}),
    )
    service = SemanticReadModelService(
        rdf_store=store, scope_resolver=resolver, access_view=view
    )
    items = service.read_model("gs-1", "table-mapping-list")["items"]
    assert [item["iri"] for item in items] == [f"{R3003_BASE}table-mapping/tm-1"]


@pytest.mark.parametrize(
    ("model_name", "row", "expected"),
    [
        (
            "table-mapping-list",
            {
                "table_mapping": f"{R3003_BASE}table-mapping/tm-2",
                "label": "mapped definition",
                "mapped_class": f"{R3003_BASE}class/Legacy",
                "mapped_definition": f"{R3003_BASE}definition/WorkOrder",
                "mapping_definition": json.dumps({
                    "source_key": "ops",
                    "row_grain": "one work order row",
                }),
                "semantic_definition": json.dumps({
                    "semantic_role": "data_mapping",
                    "unknowns": ["business key"],
                }),
                "graph": R3003_ONTOLOGY_GRAPH,
            },
            {
                "mapped_class": f"{R3003_BASE}class/Legacy",
                "mapped_definition": f"{R3003_BASE}definition/WorkOrder",
                "mapping_definition": {"source_key": "ops", "row_grain": "one work order row"},
                "semantic_definition": {"semantic_role": "data_mapping", "unknowns": ["business key"]},
            },
        ),
        (
            "join-mapping-list",
            {
                "join_mapping": f"{R3003_BASE}join-mapping/jm-1",
                "label": "work order details",
                "mapping_definition": json.dumps({
                    "step_semantics": [{"step_index": 0, "cardinality": "one_to_many"}],
                }),
                "semantic_definition": json.dumps({"semantic_role": "data_mapping"}),
                "graph": R3003_ONTOLOGY_GRAPH,
            },
            {
                "mapping_definition": {"step_semantics": [{"step_index": 0, "cardinality": "one_to_many"}]},
                "semantic_definition": {"semantic_role": "data_mapping"},
            },
        ),
        (
            "enum-meaning-list",
            {
                "enum_meaning": f"{R3003_BASE}enum-meaning/status-open",
                "label": "open status",
                "table_mapping": f"{R3003_BASE}table-mapping/tm-2",
                "column": "status_code",
                "mapping_definition": json.dumps({"conversion_rule_iri": None}),
                "semantic_definition": json.dumps({"semantic_role": "data_mapping"}),
                "graph": R3003_ONTOLOGY_GRAPH,
            },
            {
                "table_mapping": f"{R3003_BASE}table-mapping/tm-2",
                "column": "status_code",
                "mapping_definition": {"conversion_rule_iri": None},
                "semantic_definition": {"semantic_role": "data_mapping"},
            },
        ),
        (
            "metric-list",
            {
                "metric": f"{R3003_BASE}metric/work-order-count",
                "label": "work order count",
                "mapping_definition": json.dumps({
                    "contexts": [{
                        "context_key": "orders",
                        "base_mapping_iri": f"{R3003_BASE}table-mapping/tm-2",
                        "base_role": "work_order",
                    }],
                }),
                "semantic_definition": json.dumps({"semantic_role": "data_mapping"}),
                "graph": R3003_ONTOLOGY_GRAPH,
            },
            {
                "mapping_definition": {
                    "contexts": [{
                        "context_key": "orders",
                        "base_mapping_iri": f"{R3003_BASE}table-mapping/tm-2",
                        "base_role": "work_order",
                    }]
                },
                "semantic_definition": {"semantic_role": "data_mapping"},
            },
        ),
    ],
)
def test_r4010_mapping_read_models_decode_mapping_and_semantic_annotations(
    model_name, row, expected
):
    resolver = FakeScopeResolver(_resolution([R3003_ONTOLOGY_GRAPH]))
    store = FakeStore({model_name: [row]})
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)

    item = service.read_model("gs-1", model_name)["items"][0]

    for field, value in expected.items():
        assert item["detail_fields"][field] == value


def test_r4010_mapping_annotation_references_are_filtered_before_pagination():
    from app.services.semantic_access import SemanticAccessView

    hidden = f"{R3003_BASE}mapping/hidden-rule"
    row = {
        "table_mapping": f"{R3003_BASE}table-mapping/tm-hidden",
        "label": "hidden nested reference",
        "mapping_definition": json.dumps({
            "source_key": "ops",
            "field_meanings": [{"column": "status", "conversion_rule_iri": hidden}],
        }),
        "graph": R3003_ONTOLOGY_GRAPH,
    }
    service = SemanticReadModelService(
        rdf_store=FakeStore({"table-mapping-list": [row]}),
        scope_resolver=FakeScopeResolver(_resolution([R3003_ONTOLOGY_GRAPH])),
        access_view=SemanticAccessView(
            requires_filtering=True,
            _unauthorized_iris=frozenset({hidden}),
        ),
    )

    envelope = service.read_model("gs-1", "table-mapping-list")

    assert envelope["items"] == []
    assert envelope["paging"]["visible_count"] == 0


# ------------------------------------------------------------------
# R3.0-003 D1 regression: templates must read the compiler's vocabulary
# namespace against a real SPARQL engine (Oxigraph). Gated like the
# sparql-runner tests: requires a running local Oxigraph server.
# ------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RUN_OXIGRAPH_SPARQL_RUNNER_TESTS") != "1",
    reason="requires a running local Oxigraph server",
)
def test_r3003_table_mapping_list_reads_compiler_vocabulary_on_real_store():
    import uuid

    from app.core.config import Settings
    from app.repositories.rdf_store import RdfStoreRepository
    from app.services.semantic_command_compiler import compile_command

    token = uuid.uuid4().hex
    settings = Settings(
        semantic_graph_iri_prefix=f"http://ontology-platform.test/r3003-d1/{token}/graph/",
    )
    # semantic_base_iri stays at the default: the compiler writes predicates
    # into {base}/vocab/ and the template prefix must resolve to the same
    # namespace, or this test fails — that is exactly the D1 regression.
    compiled = compile_command(
        "create_table_mapping",
        {
            "ontology_id": "o1",
            "table_mapping_id": "tm-d1",
            "name": "work orders mapping",
            "mapped_class_iri": f"{settings.semantic_base_iri.rstrip('/')}/class/WorkOrder",
            "table_name": "service.work_orders",
            "column_mappings": [
                {
                    "property_iri": f"{settings.semantic_base_iri.rstrip('/')}/property/workOrderNo",
                    "column": "work_order_no",
                    "role": "business_key",
                },
            ],
            "schema_source": "schema-dump-2026-08-22",
        },
        settings,
    )
    ontology_graph = compiled.target_graph_iris[0]
    statements = " ".join(f"{s} {p} {o} ." for s, p, o, _g in compiled.delta.inserts)
    store = RdfStoreRepository(os.environ.get("OXIGRAPH_URL", "http://127.0.0.1:7878"))
    try:
        store.update_sparql(f"INSERT DATA {{ GRAPH <{ontology_graph}> {{ {statements} }} }}")
        resolver = FakeScopeResolver(_resolution([ontology_graph]))
        service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)
        items = service.read_model("gs-1", "table-mapping-list")["items"]
        assert [item["iri"] for item in items] == [
            f"{settings.semantic_base_iri.rstrip('/')}/table-mapping/tm-d1"
        ]
        assert items[0]["detail_fields"]["table_name"] == "service.work_orders"
    finally:
        store.update_sparql(f"CLEAR GRAPH <{ontology_graph}>")
