"""Real SPARQL pipeline with controlled external scores; pagination and authorization."""
import json
from unittest.mock import Mock

import httpx
import pytest
from rdflib import URIRef

from app.core.config import Settings
from app.services import semantic_jev
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_context_query import SemanticContextSnapshotChanged
from app.services.semantic_jev import JevReranker, JevScoringError
from test_r4008_context_query import context as original_context  # noqa: F401


@pytest.fixture
def context(original_context):  # noqa: F811
    semantic_jev._SNAPSHOTS.clear()
    service, graph, declare, query, vocab = original_context
    service.settings.semantic_jev_enabled = True
    service.settings.semantic_jev_api_key = "test-only"
    yield service, graph, declare, query, vocab
    semantic_jev._SNAPSHOTS.clear()


def scorer(monkeypatch, values):
    seen = []

    def score(self, queries, items):
        seen.append((queries, items))
        return [values[item["label"]] for item in items], "jev-1.13.0"

    monkeypatch.setattr(JevReranker, "score", score)
    return seen


def test_filter_boundary_scores_and_pages_reuse_recall(context, monkeypatch):
    service, _, declare, query, _ = context
    for name in ("topic answer", "topic entry", "topic boundary", "topic unrelated"):
        declare(name.replace(" ", "-"), label=name,
                semanticDefinition={"business_meaning": name, "unknowns": ["未知"]})
    seen = scorer(monkeypatch, {"topic answer": 2.9, "topic entry": 1,
                               "topic boundary": .5, "topic unrelated": .49})
    first = query(["topic"], depth=0, limit=1, resource_types=["instance"])
    assert first["primary_matches"][0]["label"] == "topic answer"
    match = first["primary_matches"][0]["match"]
    assert match["relevance_score"] == 2.9 and match["relevance_scale"] == [0, 3]
    assert match["relevance_model"] == "jev-1.13.0"
    assert first["recall"]["ranking"]["filtered_count"] == 1
    assert not first["recall"]["ranking"]["cache_hit"]
    assert seen[0][1][0]["data"]["semantic_definition"]["unknowns"] == ["未知"]
    monkeypatch.setattr(service, "_qualified_lexical_candidates", Mock(side_effect=AssertionError("recalled again")))
    rows = list(first["primary_matches"])
    page = first
    while cursor := page["matches_page"]["next_match_cursor"]:
        page = query(["topic"], depth=0, limit=1, resource_types=["instance"], match_cursor=cursor)
        assert page["recall"]["ranking"]["cache_hit"]
        rows.extend(page["primary_matches"])
    assert [row["label"] for row in rows] == ["topic answer", "topic entry", "topic boundary"]
    assert len(seen) == 1
    same_query = query(["topic"], depth=0, limit=1, resource_types=["instance"])
    assert same_query["primary_matches"] == first["primary_matches"]


def test_exact_expression_exempt_and_exact_iri_bypasses(context, monkeypatch):
    _, _, declare, query, _ = context
    exact = declare("exact", label="topic")
    declare("other", label="topic answer")
    seen = scorer(monkeypatch, {"topic": .02, "topic answer": 2.9})
    result = query(["topic"], depth=0)
    assert result["primary_matches"][0]["id"] == str(exact)
    assert result["primary_matches"][0]["match"]["relevance_score"] == .02
    assert result["recall"]["ranking"]["filtered_count"] == 0
    query([str(exact)], depth=0)
    assert len(seen) == 1


def test_fallback_keeps_order_no_filter_and_is_paged_consistently(context, monkeypatch):
    service, _, declare, query, _ = context
    declare("a", label="topic a")
    declare("b", label="topic b")
    broken = Mock(side_effect=JevScoringError("http_451"))
    monkeypatch.setattr(JevReranker, "score", broken)
    first = query(["topic"], depth=0, limit=1)
    assert first["primary_matches"][0]["match"]["relevance_score"] is None
    assert first["recall"]["ranking"]["status"] == "degraded"
    assert first["recall"]["ranking"]["filtered_count"] == 0
    assert any(w["code"] == "jev_reranking_degraded" for w in first["warnings"])
    second = query(["topic"], depth=0, limit=1, match_cursor=first["matches_page"]["next_match_cursor"])
    assert second["primary_matches"][0]["id"] != first["primary_matches"][0]["id"]
    assert broken.call_count == 1


def test_all_filtered_empty_result_and_no_fabricated_relevance(context, monkeypatch):
    _, _, declare, query, _ = context
    declare("a", label="topic a")
    scorer(monkeypatch, {"topic a": .1})
    result = query(["topic"], depth=0)
    assert result["result_status"] == "no_match" and result["primary_matches"] == []
    assert result["matches_page"]["next_match_cursor"] is None
    assert result["recall"]["ranking"]["filtered_count"] == 1


def test_authorized_only_to_provider_and_cache_permissions_change(context, monkeypatch):
    service, _, declare, query, _ = context
    hidden = declare("hidden", label="topic secret")
    declare("a", label="topic a")
    declare("b", label="topic b")
    service.access_view = SemanticAccessView(requires_filtering=True, _unauthorized_iris=frozenset({str(hidden)}))
    seen = scorer(monkeypatch, {"topic a": 2, "topic b": 1})
    first = query(["topic"], depth=0, limit=1)
    assert str(hidden) not in json.dumps(seen)
    service.access_view = SemanticAccessView(requires_filtering=True,
                                           _unauthorized_iris=frozenset({str(hidden), first["primary_matches"][0]["id"]}))
    with pytest.raises(SemanticContextSnapshotChanged, match="snapshot expired or changed"):
        query(["topic"], depth=0, limit=1, match_cursor=first["matches_page"]["next_match_cursor"])
    fresh = query(["topic"], depth=0, limit=1)
    assert fresh["primary_matches"][0]["label"] == "topic b"


@pytest.mark.parametrize("change", ["threshold", "credential", "eviction", "ttl"])
def test_cursor_cannot_rescore_on_cache_miss(context, monkeypatch, change):
    service, _, declare, query, _ = context
    declare("a", label="topic a")
    declare("b", label="topic b")
    seen = scorer(monkeypatch, {"topic a": 2, "topic b": 1})
    first = query(["topic"], depth=0, limit=1)
    if change == "threshold":
        service.settings.semantic_jev_min_score = 1.5
    elif change == "credential":
        service.settings.semantic_jev_api_key = "new-test-key"
    elif change == "eviction":
        semantic_jev._SNAPSHOTS.clear()
    else:
        for snapshot in semantic_jev._SNAPSHOTS.values():
            snapshot["expires"] = 0
    with pytest.raises(SemanticContextSnapshotChanged, match="restart the query"):
        query(["topic"], depth=0, limit=1, match_cursor=first["matches_page"]["next_match_cursor"])
    assert len(seen) == 1


def test_context_pages_preserve_roots_and_snapshot_copy(context, monkeypatch):
    _, graph, declare, query, _ = context
    root = declare("root", label="topic root")
    for name in ("n1", "n2", "n3"):
        graph.add((root, URIRef("https://business.test/link"), declare(name)))
    seen = scorer(monkeypatch, {"topic root": 2.5})
    first = query(["topic"], limit=1, context_limit=1)
    first["primary_matches"][0]["match"]["relevance_score"] = 999
    page = query(["topic"], limit=1, context_limit=1, context_cursor=first["context_page"]["next_context_cursor"])
    assert page["primary_matches"][0]["match"]["relevance_score"] == 2.5
    assert len(seen) == 1


def test_client_batches_all_candidates_and_accepts_typed_scores(monkeypatch):
    sent = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, endpoint, *, json, headers, timeout):
            sent.append(json)
            response = Mock(status_code=200, headers={"x-opencode-upstream-model-id": "jev-1.13.0"})
            response.json.return_value = {"model": "jev-1.13-free", "answers": {
                k: {"type": "score", "score": int(k[1:]) % 3} for k in json["questions"]}}
            return response
    monkeypatch.setattr(httpx, "Client", Client)
    candidates = [{"label": f"candidate-{i}", "definition": "未知条件" * 100} for i in range(100)]
    scores, model = JevReranker(Settings(semantic_jev_api_key="test-only")).score(["question"], candidates)
    assert len(sent) > 1 and sum(len(r["questions"]) for r in sent) == 100
    assert scores == [i % 3 for i in range(100)] and model == "jev-1.13.0"


def test_revision_change_invalidates_cached_cursor(context, monkeypatch):
    from app.repositories.models import OntologyModel
    _, _, declare, query, _ = context
    declare("a", label="topic a")
    declare("b", label="topic b")
    seen = scorer(monkeypatch, {"topic a": 2, "topic b": 1})
    first = query(["topic"], depth=0, limit=1)
    service = context[0]
    ontology = service.session.get(OntologyModel, "ontology-1")
    ontology.model_revision += 1
    service.session.commit()
    with pytest.raises(SemanticContextSnapshotChanged):
        query(["topic"], depth=0, limit=1, match_cursor=first["matches_page"]["next_match_cursor"])
    assert len(seen) == 1


@pytest.mark.parametrize("bad", [None, True, float("nan"), 4, -1])
def test_client_proxy_isolation_and_invalid_scores(monkeypatch, bad):
    sent = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {"proxy": "http://127.0.0.1:1080", "trust_env": False}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, endpoint, *, json, headers, timeout):
            sent.append(json)
            response = Mock(status_code=200, headers={})
            response.json.return_value = {"model": "jev-1.13.0", "answers": {
                k: {"type": "score", "score": bad} for k in json["questions"]}}
            return response
    monkeypatch.setattr(httpx, "Client", Client)
    candidate = {"id": "x", "label": "entry", "data": {"unknowns": ["missing rule"]},
                 "match": {"score": 999}}
    with pytest.raises(JevScoringError):
        JevReranker(Settings(semantic_jev_api_key="test-only")).score(["question"], [candidate])
    assert "candidates" not in sent[0]["state"]
    instructions = sent[0]["questions"]["c0"]["instructions"]
    assert "missing rule" in instructions and '"score": 999' not in instructions
