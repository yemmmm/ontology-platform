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

    def query_read_model(self, query, graph_iris, timeout_seconds, limit):
        self.last_query = query
        self.last_graph_iris = list(graph_iris)
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
    from app.services.semantic_read_scope import ScopeMember, ScopeResolution

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
        source_graph_iris=graph_iris,
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=reasoning_iri,
        rule_result_graph_iri=rule_iri,
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


def test_schema_summary_returns_envelope_with_origin_metadata():
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
    assert item["evidence_status"] == "not_applicable"
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


def test_full_working_view_includes_reasoning_and_rule_graphs():
    resolver = FakeScopeResolver(
        _resolution(
            ["http://op/s/graph/data/ov-1"],
            reasoning="http://op/s/graph/reasoning-result/run-1",
            rule="http://op/s/graph/rule-result/run-2",
        )
    )
    store = FakeStore(
        {
            "entity-detail": [
                {
                    "entity": "http://op/s/entity/alice",
                    "graph": "http://op/s/graph/data/ov-1",
                }
            ]
        }
    )
    service = SemanticReadModelService(rdf_store=store, scope_resolver=resolver)
    service.read_model("gs-1", "entity-detail", include="full-working-view")
    assert "http://op/s/graph/reasoning-result/run-1" in store.last_graph_iris
    assert "http://op/s/graph/rule-result/run-2" in store.last_graph_iris


def test_visibility_policy_filters_restricted_graphs():
    from app.services.semantic_visibility import SemanticVisibilityPolicy

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
    policy = SemanticVisibilityPolicy(
        graph_labels={"http://op/s/graph/data/b": "restricted"}
    )
    service = SemanticReadModelService(
        rdf_store=store, scope_resolver=resolver, visibility_policy=policy
    )
    envelope = service.read_model(
        "gs-1",
        "ontology-schema-summary",
        visibility_context={"labels": ["internal"]},
    )
    iris = {item["source_graph_iri"] for item in envelope["items"]}
    assert iris == {"http://op/s/graph/data/a"}
    assert any(w["code"] == "visibility_graph_omitted" for w in envelope["warnings"])


# ------------------------------------------------------------------
# graph-set-staleness composer
# ------------------------------------------------------------------


def test_graph_set_staleness_summary_assembles_members_and_count():
    """graph-set-staleness summary composes members, staleness, missing-evidence count."""

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
    assert item["missing_evidence_count"] == 3
    # Verify member-level data
    assert len(item["members"]) == 2
    roles = {m["role"] for m in item["members"]}
    assert roles == {"asserted_ontology", "asserted_data"}

    # Check staleness per member derived from the scope resolution
    for m in item["members"]:
        if m["role"] == "asserted_ontology":
            assert m["reasoning_stale"] is True
            assert m["rule_stale"] is False
            assert m["validation_stale"] is None
        elif m["role"] == "asserted_data":
            assert m["reasoning_stale"] is True
            assert m["rule_stale"] is False


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


def test_entity_shape_composer_delegates_to_shape_endpoint_service():
    """entity-shape read model short-circuits the SPARQL body and calls
    SemanticShapeEndpointService.read_merged_guidance with the entity's
    class IRI. The single item in the envelope is the merged guidance."""
    resolution = _resolution(graph_iris=["https://example/graph/data/x"])
    store = FakeStore({})
    merged = {
        "target_class": "http://op.local/ns/class/c1",
        "fields": [{"path": "http://op.local/ns/property/p1", "provenance": "generated"}],
    }
    shape_service = FakeShapeEndpointService(merged)
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=1,
        shape_endpoint=shape_service,
    )

    envelope = service.read_model(
        graph_set_id="gs-1",
        model_name="entity-shape",
        entity_iri="http://op.local/ns/entity/e1",
        class_iri="http://op.local/ns/class/c1",
    )

    # Composer delegated with the right IRIs.
    assert shape_service.calls == [("gs-1", "http://op.local/ns/class/c1")]
    # Envelope carries a single item wrapping the merged guidance.
    assert len(envelope["items"]) == 1
    assert envelope["items"][0]["target_class"] == "http://op.local/ns/class/c1"
    assert envelope["items"][0]["fields"][0]["path"] == "http://op.local/ns/property/p1"
    # And the store was never queried.
    assert store.last_query is None


def test_entity_shape_composer_requires_class_iri():
    """Calling entity-shape without a class_iri (and no entity_iri resolver)
    raises ReadModelError with a clear message."""
    resolution = _resolution(graph_iris=["https://example/graph/data/x"])
    store = FakeStore({})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=1,
        shape_endpoint=FakeShapeEndpointService({}),
    )

    import pytest

    with pytest.raises(ReadModelError) as exc_info:
        service.read_model(
            graph_set_id="gs-1",
            model_name="entity-shape",
        )
    assert "class_iri" in str(exc_info.value)


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
    # evidence_status defaults to with_evidence for asserted triples (no
    # missing-evidence marker on the subject).
    assert row["evidence_status"] == "with_evidence"
    assert row["stale"] is False


def test_fact_audit_queue_kind_inferred_queries_reasoning_result_graph():
    """kind=inferred restricts the SPARQL to the effective reasoning-result
    graph and decorates each row with assertion_kind=inferred + the
    run_id / staleness state."""
    data_iri = "http://op.local/graph/data/ont-1"
    reasoning_iri = "http://op.local/graph/reasoning-result/run-1"
    resolution = _resolution(
        graph_iris=[data_iri],
        reasoning=reasoning_iri,
        derived_state={
            "reasoning": {
                "status": "current",
                "run_id": "run-1",
                "result_graph_iri": reasoning_iri,
            },
        },
    )
    store = FakeStore({
        "fact-audit-queue": [
            {
                "subject": "http://op.local/ns/entity/alice",
                "subject_label": "Alice",
                "predicate": "http://op.local/ns/property/parent",
                "predicate_label": "parent",
                "object": "http://op.local/ns/entity/parent-bob",
                "graph": reasoning_iri,
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
        kind="inferred",
        include="asserted-plus-reasoning",
    )
    assert store.last_graph_iris == [reasoning_iri]
    row = envelope["items"][0]
    assert row["assertion_kind"] == "inferred"
    assert row["derived_from"]["run_id"] == "run-1"


def test_fact_audit_queue_kind_rule_derived_queries_rule_result_graph():
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
    envelope = service.read_model(
        graph_set_id="gs-1",
        model_name="fact-audit-queue",
        kind="rule_derived",
        include="asserted-plus-rules",
    )
    assert store.last_graph_iris == [rule_iri]
    row = envelope["items"][0]
    assert row["assertion_kind"] == "rule_derived"
    assert row["derived_from"]["run_id"] == "run-9"


def test_fact_audit_queue_kind_missing_evidence_filters_data_graph_rows():
    """kind=missing_evidence queries the asserted data graph but filters rows
    to those whose subject carries op:evidenceStatus "missing_evidence".
    assertion_kind on those rows is "missing_evidence" and evidence_status
    is "missing_evidence"."""
    data_iri = "http://op.local/graph/data/ont-1"
    resolution = _resolution(graph_iris=[data_iri])
    store = FakeStore({
        "missing-evidence-list": [
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
        kind="missing_evidence",
    )
    assert len(envelope["items"]) == 1
    row = envelope["items"][0]
    assert row["assertion_kind"] == "missing_evidence"
    assert row["evidence_status"] == "missing_evidence"


def test_fact_audit_queue_inferred_with_stale_pointer_marks_rows_stale():
    """When the reasoning-result pointer is stale, every inferred row carries
    stale=True plus a stale_reason."""
    data_iri = "http://op.local/graph/data/ont-1"
    reasoning_iri = "http://op.local/graph/reasoning-result/run-1"
    resolution = _resolution(
        graph_iris=[data_iri],
        reasoning=reasoning_iri,
        derived_state={
            "reasoning": {
                "status": "stale",
                "run_id": "run-1",
                "result_graph_iri": reasoning_iri,
            },
        },
    )
    store = FakeStore({
        "fact-audit-queue": [
            {
                "subject": "http://op.local/ns/entity/alice",
                "subject_label": "Alice",
                "predicate": "http://op.local/ns/property/parent",
                "predicate_label": "parent",
                "object": "http://op.local/ns/entity/parent-bob",
                "graph": reasoning_iri,
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
        kind="inferred",
        include="asserted-plus-reasoning",
    )
    row = envelope["items"][0]
    assert row["stale"] is True
    assert row["stale_reason"] is not None


def test_fact_audit_queue_inferred_without_pointer_emits_warning():
    """When kind=inferred but no reasoning-result pointer exists, the
    composer returns an empty list with a warning so the frontend can show
    a 'click Generate to run reasoning' empty state."""
    data_iri = "http://op.local/graph/data/ont-1"
    # No reasoning pointer in resolution.
    resolution = _resolution(graph_iris=[data_iri])
    store = FakeStore({})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
        timeout_seconds=10,
        default_limit=500,
    )
    envelope = service.read_model(
        graph_set_id="gs-1",
        model_name="fact-audit-queue",
        kind="inferred",
    )
    assert envelope["items"] == []
    assert any(
        w.get("code") == "fact_audit_no_inferred_pointer"
        for w in envelope["warnings"]
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
