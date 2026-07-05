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


def _add_pointer(session, kind, status="current", iri=None):
    session.add(
        SemanticDerivedResultPointerModel(
            id=f"ptr-{kind}",
            graph_set_id="gs-1",
            result_kind=kind,
            run_id=f"run-{kind}",
            result_graph_iri=iri or f"http://op/s/graph/{kind}-result/run-1",
            source_signature="sig-1",
            status=status,
            became_current_at=datetime.now(UTC),
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
