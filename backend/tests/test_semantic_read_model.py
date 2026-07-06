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
