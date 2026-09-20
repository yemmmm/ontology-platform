"""R3.0-016 ledger #29: unresolved revision-0 members fail in backend vocabulary.

A graph-set member registered by ``update_membership`` stays at revision 0
until its first write materializes the graph.  Handing such an IRI to the RDF
store let a foreign ``graph does not exists`` reply become the only diagnostic,
which the modeling role could not self-diagnose.  The resolve helpers must name
the unmaterialized members themselves instead.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.mcp.tools import semantic as semantic_tools


def _member(graph_iri: str, role: str, revision: int) -> dict[str, Any]:
    return {
        "graph_iri": graph_iri,
        "role": role,
        "revision": revision,
        "required": True,
    }


def _stub_describe(monkeypatch: pytest.MonkeyPatch, members: list[dict[str, Any]]) -> None:
    monkeypatch.setattr(
        semantic_tools.SemanticGraphSetService,
        "describe",
        lambda self, graph_set_id: {"members": members},
    )


def test_resolve_data_graphs_names_never_materialized_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_describe(
        monkeypatch,
        [
            _member("http://ontology-platform.local/graph/materialized", "asserted_data", 2),
            _member("http://ontology-platform.local/graph/empty", "asserted_data", 0),
        ],
    )
    with pytest.raises(ValueError) as excinfo:
        semantic_tools._resolve_data_graphs(session=None, graph_set_id="gs-1")
    message = str(excinfo.value)
    assert message.startswith("graph set gs-1 has asserted_data member(s) with no materialized revision:")
    assert "http://ontology-platform.local/graph/empty" in message
    assert "materialize the graph" in message
    # The materialized sibling stays unnamed: it is not the problem.
    assert "http://ontology-platform.local/graph/materialized" not in message


def test_resolve_data_graphs_covers_reasoning_role_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # run_semantic_reasoning selects asserted_ontology + asserted_data; an
    # unmaterialized ontology-role member must trip the same guard.
    _stub_describe(
        monkeypatch,
        [
            _member("http://ontology-platform.local/graph/ontology", "asserted_ontology", 0),
            _member("http://ontology-platform.local/graph/data", "asserted_data", 3),
        ],
    )
    with pytest.raises(ValueError) as excinfo:
        semantic_tools._resolve_data_graphs(
            session=None,
            graph_set_id="gs-2",
            roles=("asserted_ontology", "asserted_data"),
        )
    message = str(excinfo.value)
    assert "asserted_ontology/asserted_data" in message
    assert "http://ontology-platform.local/graph/ontology" in message


def test_resolve_role_graphs_names_unmaterialized_shape_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_describe(
        monkeypatch,
        [_member("http://ontology-platform.local/graph/shapes", "shape", 0)],
    )
    with pytest.raises(ValueError) as excinfo:
        semantic_tools._resolve_role_graphs(session=None, graph_set_id="gs-3", role="shape")
    assert "shape member(s) with no materialized revision" in str(excinfo.value)


def test_resolve_helpers_pass_fully_materialized_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    members = [
        _member("http://ontology-platform.local/graph/data-a", "asserted_data", 1),
        _member("http://ontology-platform.local/graph/ontology-a", "asserted_ontology", 4),
        _member("http://ontology-platform.local/graph/shapes", "shape", 1),
    ]
    _stub_describe(monkeypatch, members)
    assert semantic_tools._resolve_data_graphs(session=None, graph_set_id="gs-4") == [
        "http://ontology-platform.local/graph/data-a"
    ]
    assert semantic_tools._resolve_data_graphs(
        session=None, graph_set_id="gs-4", roles=("asserted_ontology", "asserted_data")
    ) == [
        "http://ontology-platform.local/graph/data-a",
        "http://ontology-platform.local/graph/ontology-a",
    ]
    assert semantic_tools._resolve_role_graphs(
        session=None, graph_set_id="gs-4", role="shape"
    ) == ["http://ontology-platform.local/graph/shapes"]
