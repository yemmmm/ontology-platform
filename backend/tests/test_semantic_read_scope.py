from datetime import UTC, datetime

from app.repositories.models import (
    SemanticDerivedResultPointerModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)
from app.services.semantic_read_scope import (
    ReadScopeError,
    ScopeResolution,
    SemanticReadScopeResolver,
)


def _make_graph_set(session, members):
    gs = SemanticGraphSetModel(
        id="gs-1",
        name="demo",
        scope_type="ontology_version",
        scope_id="ov-1",
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
    session.commit()
    return gs


def _add_pointer(
    session,
    kind,
    status="current",
    iri=None,
    pointer_id=None,
    run_id=None,
    became_current_at=None,
):
    session.add(
        SemanticDerivedResultPointerModel(
            id=pointer_id or f"ptr-{kind}",
            graph_set_id="gs-1",
            result_kind=kind,
            run_id=run_id or f"run-{kind}",
            result_graph_iri=iri or f"http://op/s/graph/{kind}-result/run-1",
            source_signature="sig-1",
            status=status,
            became_current_at=became_current_at or datetime.now(UTC),
        )
    )
    session.commit()


def test_asserted_scope_returns_only_source_graphs(in_memory_session):
    _make_graph_set(
        in_memory_session,
        [
            ("http://op/s/graph/ontology/ov-1", "asserted_ontology"),
            ("http://op/s/graph/data/ov-1", "asserted_data"),
            ("http://op/s/graph/shapes/ov-1", "shape"),
        ],
    )
    resolver = SemanticReadScopeResolver(in_memory_session)
    result = resolver.resolve("gs-1", include="asserted")
    assert isinstance(result, ScopeResolution)
    assert set(result.source_graph_iris) == {
        "http://op/s/graph/ontology/ov-1",
        "http://op/s/graph/data/ov-1",
    }
    assert result.shape_graph_iris == ["http://op/s/graph/shapes/ov-1"]
    assert result.reasoning_result_graph_iri is None
    assert result.rule_result_graph_iri is None


def test_asserted_plus_reasoning_includes_current_pointer(in_memory_session):
    _make_graph_set(
        in_memory_session,
        [("http://op/s/graph/ontology/ov-1", "asserted_ontology")],
    )
    _add_pointer(in_memory_session, "reasoning")
    resolver = SemanticReadScopeResolver(in_memory_session)
    result = resolver.resolve("gs-1", include="asserted-plus-reasoning")
    assert result.reasoning_result_graph_iri == "http://op/s/graph/reasoning-result/run-1"
    assert result.rule_result_graph_iri is None


def test_full_working_view_includes_all_current_pointers(in_memory_session):
    _make_graph_set(
        in_memory_session,
        [("http://op/s/graph/data/ov-1", "asserted_data")],
    )
    _add_pointer(in_memory_session, "reasoning")
    _add_pointer(in_memory_session, "rule")
    resolver = SemanticReadScopeResolver(in_memory_session)
    result = resolver.resolve("gs-1", include="full-working-view")
    assert result.reasoning_result_graph_iri == "http://op/s/graph/reasoning-result/run-1"
    assert result.rule_result_graph_iri == "http://op/s/graph/rule-result/run-1"


def test_scope_prefers_current_pointers_over_superseded_rows(in_memory_session):
    _make_graph_set(
        in_memory_session,
        [("http://op/s/graph/data/ov-1", "asserted_data")],
    )
    _add_pointer(
        in_memory_session,
        "reasoning",
        pointer_id="ptr-reasoning-current",
        run_id="run-reasoning-current",
        iri="http://op/s/graph/reasoning-result/current",
        status="current",
        became_current_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    _add_pointer(
        in_memory_session,
        "reasoning",
        pointer_id="ptr-reasoning-superseded",
        run_id="run-reasoning-superseded",
        iri="http://op/s/graph/reasoning-result/superseded",
        status="superseded",
        became_current_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    _add_pointer(
        in_memory_session,
        "rule",
        pointer_id="ptr-rule-current",
        run_id="run-rule-current",
        iri="http://op/s/graph/rule-result/current",
        status="current",
        became_current_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    _add_pointer(
        in_memory_session,
        "rule",
        pointer_id="ptr-rule-superseded",
        run_id="run-rule-superseded",
        iri="http://op/s/graph/rule-result/superseded",
        status="superseded",
        became_current_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    resolver = SemanticReadScopeResolver(in_memory_session)
    result = resolver.resolve("gs-1", include="full-working-view")

    assert result.reasoning_result_graph_iri == "http://op/s/graph/reasoning-result/current"
    assert result.rule_result_graph_iri == "http://op/s/graph/rule-result/current"
    assert result.derived_state["reasoning"] == {
        "status": "current",
        "run_id": "run-reasoning-current",
        "result_graph_iri": "http://op/s/graph/reasoning-result/current",
    }
    assert result.derived_state["rule"] == {
        "status": "current",
        "run_id": "run-rule-current",
        "result_graph_iri": "http://op/s/graph/rule-result/current",
    }
    assert result.members[0].derived_state["reasoning"]["result_graph_iri"] == (
        "http://op/s/graph/reasoning-result/current"
    )
    assert result.members[0].derived_state["rule"]["result_graph_iri"] == (
        "http://op/s/graph/rule-result/current"
    )


def test_scope_uses_latest_current_pointer_when_duplicate_current_rows_exist(
    in_memory_session,
):
    _make_graph_set(
        in_memory_session,
        [("http://op/s/graph/data/ov-1", "asserted_data")],
    )
    _add_pointer(
        in_memory_session,
        "rule",
        pointer_id="ptr-rule-new",
        run_id="run-rule-new",
        iri="http://op/s/graph/rule-result/new",
        status="current",
        became_current_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    _add_pointer(
        in_memory_session,
        "rule",
        pointer_id="ptr-rule-old",
        run_id="run-rule-old",
        iri="http://op/s/graph/rule-result/old",
        status="current",
        became_current_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    resolver = SemanticReadScopeResolver(in_memory_session)
    result = resolver.resolve("gs-1", include="asserted-plus-rules")

    assert result.rule_result_graph_iri == "http://op/s/graph/rule-result/new"
    assert result.derived_state["rule"] == {
        "status": "current",
        "run_id": "run-rule-new",
        "result_graph_iri": "http://op/s/graph/rule-result/new",
    }


def test_stale_pointer_with_allow_stale_false_raises(in_memory_session):
    _make_graph_set(
        in_memory_session,
        [("http://op/s/graph/data/ov-1", "asserted_data")],
    )
    _add_pointer(in_memory_session, "reasoning", status="stale")
    resolver = SemanticReadScopeResolver(in_memory_session)
    try:
        resolver.resolve(
            "gs-1", include="asserted-plus-reasoning", allow_stale_derived=False
        )
        raise AssertionError("expected ReadScopeError")
    except ReadScopeError as exc:
        assert "stale" in str(exc).lower()


def test_stale_pointer_with_allow_stale_true_produces_warning(in_memory_session):
    _make_graph_set(
        in_memory_session,
        [("http://op/s/graph/data/ov-1", "asserted_data")],
    )
    _add_pointer(in_memory_session, "reasoning", status="stale")
    resolver = SemanticReadScopeResolver(in_memory_session)
    result = resolver.resolve(
        "gs-1", include="asserted-plus-reasoning", allow_stale_derived=True
    )
    assert result.reasoning_result_graph_iri == "http://op/s/graph/reasoning-result/run-1"
    assert any(w["code"] == "stale_reasoning_result" for w in result.warnings)


def test_missing_pointer_for_required_scope_warns(in_memory_session):
    _make_graph_set(
        in_memory_session,
        [("http://op/s/graph/data/ov-1", "asserted_data")],
    )
    resolver = SemanticReadScopeResolver(in_memory_session)
    result = resolver.resolve(
        "gs-1", include="asserted-plus-rules", allow_stale_derived=True
    )
    assert result.rule_result_graph_iri is None
    assert any(w["code"] == "missing_rule_result" for w in result.warnings)


def test_unknown_include_raises(in_memory_session):
    _make_graph_set(
        in_memory_session,
        [("http://op/s/graph/data/ov-1", "asserted_data")],
    )
    resolver = SemanticReadScopeResolver(in_memory_session)
    try:
        resolver.resolve("gs-1", include="no-such")
        raise AssertionError("expected ReadScopeError")
    except ReadScopeError as exc:
        assert "include" in str(exc).lower()


def test_unknown_graph_set_raises(in_memory_session):
    resolver = SemanticReadScopeResolver(in_memory_session)
    try:
        resolver.resolve("missing-gs")
        raise AssertionError("expected ReadScopeError")
    except ReadScopeError as exc:
        assert "not found" in str(exc).lower()
