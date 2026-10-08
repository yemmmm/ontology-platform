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
    assert result.shape_graph_iris == []
    assert result.reasoning_result_graph_iri is None
    assert not hasattr(result, "rule_result_graph_iri")


def test_full_working_view_includes_all_current_pointers(in_memory_session):
    _make_graph_set(
        in_memory_session,
        [("http://op/s/graph/data/ov-1", "asserted_data")],
    )
    _add_pointer(in_memory_session, "reasoning")
    _add_pointer(in_memory_session, "rule")
    resolver = SemanticReadScopeResolver(in_memory_session)
    result = resolver.resolve("gs-1", include="full-working-view")
    assert result.reasoning_result_graph_iri is None
    assert "rule" not in result.derived_state


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
