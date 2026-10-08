from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_retrieval import SemanticResourceRetrievalService


class Embeddings:
    def __init__(self, dimensions):
        self.dimensions = dimensions
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [[1.0] * self.dimensions for _ in texts]


def vector_row(index, hidden=False):
    return {
        "resource_iri": f"https://business.test/{index:04}",
        "resource_kind": "instance",
        "assertion_kind": "asserted",
        "label": f"candidate {index}",
        "labels": [],
        "aliases": [],
        "descriptions": [],
        "rdf_types": [],
        "mapping_evidence": [{"nested": {"reference": "https://business.test/hidden"}}]
        if hidden
        else [],
        "similarity": 0.9000000001 - index * 0.00000000001,
        "distance": 0.0999999999 + index * 0.00000000001,
    }


def reader(in_memory_session, rows):
    settings = Settings(embedding_dimensions=256)
    embeddings = Embeddings(settings.embedding_dimensions)
    retrieval = SemanticResourceRetrievalService(
        in_memory_session, settings, embedding_client=embeddings
    )
    retrieval.repository.index_status = lambda **kwargs: {"status": "current", "ontology_id": "o"}
    scans = []

    def scan(**kwargs):
        scans.append(kwargs)
        eligible = rows
        if kwargs.get("after") is not None:
            after = kwargs["after"]
            eligible = [row for row in rows if (row["distance"], row["resource_iri"]) > after]
        return eligible[: kwargs["limit"]]

    retrieval.repository.exact_cosine_candidates = scan
    scope = SimpleNamespace(
        ontologies=(
            SimpleNamespace(
                ontology_id="o",

                model_revision=1,
            ),
        )
    )
    return retrieval, embeddings, scans, scope


def test_hidden_raw_vector_windows_do_not_starve_visible_candidates(in_memory_session):
    rows = [vector_row(i, hidden=i < 125) for i in range(128)]
    retrieval, embeddings, scans, scope = reader(in_memory_session, rows)
    view = SemanticAccessView(
        requires_filtering=True, _unauthorized_iris=frozenset({"https://business.test/hidden"})
    )
    result = retrieval.recall_multi(
        scope=scope,
        queries=["one", "two"],
        resource_kinds={"instance"},
        search_mode="hybrid",
        limit=1,
        candidate_filter=lambda items: [item for item in items if view.filter_candidate(item)],
    )
    assert embeddings.calls == [["one", "two"]]
    assert all(len(items) == 3 for items in result["candidates_by_query"])
    assert result["completeness"] == "complete"
    assert len(scans) == 6
    assert scans[1]["after"] == (rows[49]["distance"], rows[49]["resource_iri"])
    assert scans[2]["after"] == (rows[99]["distance"], rows[99]["resource_iri"])


def test_vector_qualified_window_requires_extra_visible_candidate(in_memory_session):
    retrieval, _, scans, scope = reader(in_memory_session, [vector_row(i) for i in range(51)])
    result = retrieval.recall_multi(
        scope=scope,
        queries=["one"],
        resource_kinds={"instance"},
        search_mode="hybrid",
        limit=1,
        candidate_filter=lambda items: items,
    )
    assert len(result["candidates_by_query"][0]) == 50
    assert result["completeness"] == "degraded"
    assert "candidate_window_incomplete" in {warning["code"] for warning in result["warnings"]}
    retrieval, _, scans, scope = reader(in_memory_session, [vector_row(i) for i in range(50)])
    result = retrieval.recall_multi(
        scope=scope,
        queries=["one"],
        resource_kinds={"instance"},
        search_mode="hybrid",
        limit=1,
        candidate_filter=lambda items: items,
    )
    assert result["completeness"] == "complete"
    assert not result["warnings"]
    assert len(scans) == 2


def test_role_mismatches_continue_raw_vector_scan(in_memory_session):
    retrieval, _, scans, scope = reader(in_memory_session, [vector_row(i) for i in range(130)])
    result = retrieval.recall_multi(
        scope=scope,
        queries=["one"],
        resource_kinds={"instance"},
        search_mode="hybrid",
        limit=1,
        candidate_filter=lambda items: [
            item for item in items if int(item["iri"].rsplit("/", 1)[-1]) >= 129
        ],
    )
    assert len(result["candidates_by_query"][0]) == 1
    assert len(scans) == 3
    assert result["completeness"] == "complete"


def test_hydration_failure_propagates_instead_of_vector_degraded(in_memory_session):
    from app.repositories.rdf_store import SparqlQueryTimeout

    retrieval, _, scans, scope = reader(in_memory_session, [vector_row(1)])

    def failure(items):
        raise SparqlQueryTimeout("hydrate timeout")

    with pytest.raises(SparqlQueryTimeout):
        retrieval.recall_multi(
            scope=scope,
            queries=["one"],
            resource_kinds={"instance"},
            search_mode="hybrid",
            limit=1,
            candidate_filter=failure,
        )
