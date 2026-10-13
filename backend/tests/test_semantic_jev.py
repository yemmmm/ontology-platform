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
    def existing_contract_query(queries, **kwargs):
        kwargs.setdefault("context_order", "graph_distance")
        return query(queries, **kwargs)

    yield service, graph, declare, existing_contract_query, vocab
    semantic_jev._SNAPSHOTS.clear()


def scorer(monkeypatch, values):
    seen = []

    def score(self, queries, items, **kwargs):
        seen.append((queries, items, kwargs))
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
    with pytest.raises(SemanticContextSnapshotChanged, match="visibility changed"):
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


def test_score_branches_inlines_context_and_uses_independent_scales(monkeypatch):
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
            response = Mock(status_code=200, headers={
                "x-opencode-upstream-model-id": "jev-1.13.0",
            })
            response.json.return_value = {
                "model": "jev-1.13-free",
                "answers": {
                    key: {"type": "score", "score": 2 if key.startswith("c") else 1}
                    for key in json["questions"]
                },
            }
            return response

    monkeypatch.setattr(httpx, "Client", Client)
    contexts = [
        {
            "candidate": {
                "id": "branch-a",
                "semantic_definition": {
                    "business_meaning": "规则入口",
                },
                "original_json": {"match": "original-match", "fusion": "original-fusion"},
                "data": {
                    "semantic_definition": {
                        "business_meaning": "规则入口",
                        "match": "business-match",
                        "fusion": "business-fusion",
                        "answer_score": "business-answer-score",
                    },
                    "original_json": {"match": "original-match", "fusion": "original-fusion"},
                },
                "match": {"score": 999},
                "fusion": {"best_evidence_tier": "exact"},
            },
            "root": {
                "id": "root-a", "match": {"score": 100},
                "data": {"semantic_definition": {"match": "root-business-match"}},
            },
            "path": [{
                "predicate": "hasRule", "fusion": {"score": 101},
                "data": {"original_json": {"fusion": "path-business-fusion"}},
            }],
            "via_edge": {
                "source": "root-a", "target": "branch-a", "answer_score": 102,
                "data": {"semantic_definition": {"answer_score": "edge-business-score"}},
            },
            "can_explore": True,
        },
        {
            "candidate": {"id": "terminal-a", "value": "未知"},
            "root": {"id": "root-a"},
            "path": [],
            "via_edge": None,
            "can_explore": False,
        },
    ]
    result = JevReranker(Settings(semantic_jev_api_key="test-only")).score_branches(
        ["关闭工单需要什么条件"], contexts
    )

    assert result["status"] == "applied"
    assert result["model"] == "jev-1.13.0"
    assert result["scores"] == [
        {"answer_score": 2.0, "exploration_score": 1.0, "status": "scored"},
        {"answer_score": 2.0, "exploration_score": None, "status": "scored"},
    ]
    questions = sent[0]["questions"]
    assert set(questions) == {"c0", "e0", "c1"}
    assert questions["c0"]["version"] == semantic_jev.JEV_RANKING_VERSION
    assert questions["e0"]["version"] == semantic_jev.JEV_EXPLORATION_VERSION
    assert questions["c1"]["version"] == semantic_jev.JEV_RANKING_VERSION
    serialized = json.dumps(questions, ensure_ascii=False)
    assert '"score": 999' not in serialized and '"score": 100' not in serialized
    assert '"score": 101' not in serialized and '"answer_score": 102' not in serialized
    assert '"best_evidence_tier": "exact"' not in serialized
    assert "business-match" in serialized and "business-fusion" in serialized
    assert "business-answer-score" in serialized and "original-match" in serialized
    assert "root-business-match" in serialized and "path-business-fusion" in serialized
    assert "edge-business-score" in serialized
    assert "规则入口" in serialized and "root-a" in serialized


def test_score_branches_keeps_successful_batches_when_later_batch_is_invalid(monkeypatch):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, endpoint, *, json, headers, timeout):
            calls.append(json)
            response = Mock(status_code=200, headers={
                "x-opencode-upstream-model-id": "jev-1.13.0",
            })
            if len(calls) == 1:
                response.json.return_value = {
                    "model": "jev-1.13.0",
                    "answers": {
                        key: {"type": "score", "score": 2}
                        for key in json["questions"]
                    },
                }
            else:
                response.json.return_value = {"model": "jev-1.13.0", "answers": {}}
            return response

    monkeypatch.setattr(httpx, "Client", Client)
    contexts = [
        {
            "candidate": {"id": "a", "text": "a" * 15_000},
            "root": {"id": "root-a"}, "path": [], "via_edge": None,
            "can_explore": True,
        },
        {
            "candidate": {"id": "b", "text": "b" * 15_000},
            "root": {"id": "root-b"}, "path": [], "via_edge": None,
            "can_explore": True,
        },
    ]
    result = JevReranker(Settings(semantic_jev_api_key="test-only")).score_branches(
        ["question"], contexts
    )

    assert len(calls) == 2
    assert result["status"] == "degraded"
    assert result["scores"][0] == {
        "answer_score": 2.0, "exploration_score": 2.0, "status": "scored",
    }
    assert result["scores"][1]["status"] == "unavailable"
    assert result["scores"][1]["reason"] == "invalid_answers"
    assert result["reason"] == "invalid_answers"


def test_score_branches_oversized_context_only_degrades_itself(monkeypatch):
    sent = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, endpoint, *, json, headers, timeout):
            sent.append(json)
            response = Mock(status_code=200, headers={
                "x-opencode-upstream-model-id": "jev-1.13.0",
            })
            response.json.return_value = {
                "model": "jev-1.13.0",
                "answers": {
                    key: {"type": "score", "score": 3}
                    for key in json["questions"]
                },
            }
            return response

    monkeypatch.setattr(httpx, "Client", Client)
    contexts = [
        {
            "candidate": {"id": "too-large", "text": "大" * 40_000},
            "root": {"id": "root"}, "path": [], "via_edge": None,
            "can_explore": True,
        },
        {
            "candidate": {"id": "small", "text": "可用"},
            "root": {"id": "root"}, "path": [], "via_edge": None,
            "can_explore": False,
        },
    ]
    result = JevReranker(Settings(semantic_jev_api_key="test-only")).score_branches(
        ["question"], contexts
    )

    assert len(sent) == 1 and set(sent[0]["questions"]) == {"c1"}
    assert result["scores"][0]["status"] == "unavailable"
    assert result["scores"][0]["reason"] == "candidate_exceeds_context"
    assert result["scores"][1] == {
        "answer_score": 3.0, "exploration_score": None, "status": "scored",
    }


def _large_branch_context(identifier, marker, *, can_explore=True):
    return {
        "candidate": {"id": identifier, "text": marker * 15_000},
        "root": {"id": f"root-{identifier}"},
        "path": [],
        "via_edge": None,
        "can_explore": can_explore,
    }


def test_score_branches_shares_one_deadline_across_batches(monkeypatch):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, endpoint, *, json, headers, timeout):
            calls.append(timeout)
            response = Mock(status_code=200, headers={
                "x-opencode-upstream-model-id": "jev-1.13.0",
            })
            response.json.return_value = {
                "model": "jev-1.13.0",
                "answers": {
                    key: {"type": "score", "score": 2}
                    for key in json["questions"]
                },
            }
            return response

    monotonic_values = iter((100.0, 100.2, 102.1))
    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(semantic_jev.time, "monotonic", lambda: next(monotonic_values))
    result = JevReranker(Settings(semantic_jev_api_key="test-only")).score_branches(
        ["question"],
        [_large_branch_context("a", "a"), _large_branch_context("b", "b")],
        timeout_seconds=2,
    )

    assert len(calls) == 1
    assert calls[0] == pytest.approx(1.8)
    assert result["scores"][0] == {
        "answer_score": 2.0, "exploration_score": 2.0, "status": "scored",
    }
    assert result["scores"][1]["status"] == "unavailable"
    assert result["scores"][1]["reason"] == "timeout"
    assert result["reason"] == "timeout"


def test_score_branches_discards_entire_batch_on_one_invalid_score(monkeypatch):
    sent = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, endpoint, *, json, headers, timeout):
            sent.append(json)
            response = Mock(status_code=200, headers={
                "x-opencode-upstream-model-id": "jev-1.13.0",
            })
            response.json.return_value = {
                "model": "jev-1.13.0",
                "answers": {
                    "c0": {"type": "score", "score": 2},
                    "e0": {"type": "score", "score": 1},
                    "c1": {"type": "score", "score": 4},
                },
            }
            return response

    monkeypatch.setattr(httpx, "Client", Client)
    result = JevReranker(Settings(semantic_jev_api_key="test-only")).score_branches(
        ["question"],
        [
            {"candidate": {"id": "a"}, "root": {}, "path": [],
             "via_edge": None, "can_explore": True},
            {"candidate": {"id": "b"}, "root": {}, "path": [],
             "via_edge": None, "can_explore": False},
        ],
    )

    assert set(sent[0]["questions"]) == {"c0", "e0", "c1"}
    assert result["status"] == "degraded" and result["reason"] == "invalid_score"
    assert result["scores"] == [
        {
            "answer_score": None, "exploration_score": None,
            "status": "unavailable", "reason": "invalid_score",
        },
        {
            "answer_score": None, "exploration_score": None,
            "status": "unavailable", "reason": "invalid_score",
        },
    ]


def test_score_branches_stops_after_upstream_model_drift(monkeypatch):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, endpoint, *, json, headers, timeout):
            calls.append(json)
            model = "jev-1.13.0" if len(calls) == 1 else "jev-1.14.0"
            response = Mock(status_code=200, headers={
                "x-opencode-upstream-model-id": model,
            })
            response.json.return_value = {
                "model": model,
                "answers": {
                    key: {"type": "score", "score": 2}
                    for key in json["questions"]
                },
            }
            return response

    monkeypatch.setattr(httpx, "Client", Client)
    result = JevReranker(Settings(semantic_jev_api_key="test-only")).score_branches(
        ["question"],
        [_large_branch_context("a", "a"), _large_branch_context("b", "b")],
        expected_model="jev-1.13.0",
    )

    assert len(calls) == 2
    assert result["model"] == "jev-1.13.0"
    assert result["scores"][0]["status"] == "scored"
    assert result["scores"][1]["status"] == "unavailable"
    assert result["scores"][1]["reason"] == "model_changed_during_scoring"
    assert result["reason"] == "model_changed_during_scoring"


def test_snapshot_helpers_preserve_identity_and_update_only_access_view():
    semantic_jev._SNAPSHOTS.clear()
    saved = semantic_jev.save_ranking_snapshot(
        "key", {"frozen": ["value"], "access_view": {"old": True}}, lifetime=60
    )
    by_id = semantic_jev.get_snapshot_by_id(saved["snapshot_id"])
    assert by_id["snapshot_id"] == saved["snapshot_id"]
    updated = semantic_jev.update_snapshot_access("key", {"new": True})
    assert updated["snapshot_id"] == saved["snapshot_id"]
    assert updated["expires"] == saved["expires"]
    assert updated["frozen"] == ["value"]
    assert updated["access_view"] == {"new": True}
    assert semantic_jev.discard_ranking_snapshot("key") is True
    assert semantic_jev.get_snapshot_by_id(saved["snapshot_id"]) is None
