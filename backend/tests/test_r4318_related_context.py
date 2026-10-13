"""R4.3-018 development checks: real SPARQL, HTTP scoring stub, frozen pagination."""
from __future__ import annotations

import copy
import json as json_lib
from unittest.mock import Mock

import httpx
import pytest
from rdflib import URIRef

from app.services import semantic_jev
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_context_cursor import ContextCursorInvalid, CursorPayload
from app.services.semantic_context_query import (
    SemanticContextCursorMismatch,
    SemanticContextSnapshotChanged,
)
from app.services.semantic_jev import JevReranker, RELATED_CONTEXT_INSTRUCTIONS
from test_r4008_context_query import context as original_context  # noqa: F401
from test_r4008_context_query import identity


@pytest.fixture
def context(original_context, monkeypatch):  # noqa: F811
    semantic_jev._SNAPSHOTS.clear()
    service, graph, declare, query, vocab = original_context
    service.settings.semantic_jev_enabled = True
    service.settings.semantic_jev_api_key = "test-only"
    monkeypatch.setattr(JevReranker, "score", lambda self, queries, items, **kw:
                        ([2.] * len(items), "actual-model"))
    monkeypatch.setattr(JevReranker, "score_branches", lambda self, queries, contexts, **kw: {
        "scores": [{"status": "scored", "answer_score": 2.,
                    "exploration_score": 2. if c["can_explore"] else None} for c in contexts],
        "status": "applied", "model": "actual-model"})
    yield service, graph, declare, query, vocab
    semantic_jev._SNAPSHOTS.clear()


def provider(monkeypatch, policy=lambda value: 1., *, failure=None, model="actual-model"):
    requests = []
    contexts = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, endpoint, *, json, headers, timeout):
            requests.append(copy.deepcopy(json))
            assert timeout > 0
            assert set(json_lib.loads(json["state"])) == {"original_queries"}
            answers = {}
            for name, question in json["questions"].items():
                assert name.startswith("c")
                assert question["context_version"] == "related-context-relevance-v1"
                value = json_lib.loads(question["instructions"][len(RELATED_CONTEXT_INSTRUCTIONS):])
                assert value["can_explore"] is False
                contexts.append(value)
                answers[name] = {"type": "score", "score": policy(value)}
            response = Mock(status_code=200, headers={"x-opencode-upstream-model-id": model})
            response.json.return_value = {"model": "alias", "answers": answers}
            if failure == "missing":
                response.json.return_value["answers"].pop(next(iter(answers)))
            if failure == "timeout":
                raise httpx.ReadTimeout("test")
            return response
    monkeypatch.setattr(httpx, "Client", Client)
    return contexts, requests


def link(graph, source, target, name="next"):
    graph.add((source, URIRef("https://business.test/" + name), target))


def scenario(context):
    _, graph, declare, _, _ = context
    root = declare("root", "Action", label="closeQuestion")
    bridge = declare("bridge", "Binding")
    mid = declare("mid", "Object")
    far = declare("far", "Rule", actionDefinition={"conditions": ["owner approved"],
                                                 "exceptions": ["emergency"],
                                                 "unknowns": ["approval timeout"]})
    link(graph, root, bridge)
    link(graph, bridge, mid)
    link(graph, mid, far)
    return root, bridge, mid, far


def query_options(strategy="fixed", **kwargs):
    return {"expansion_strategy": strategy, "semantic_roles": ["Action"], "depth": 3,
            "context_limit": 100, **kwargs}


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
@pytest.mark.parametrize("detail", ["full", "compact", "preview"])
def test_global_ranking_keeps_zero_and_far_evidence_across_projections(context, monkeypatch, strategy, detail):
    _, _, _, query, _ = context
    _, _, _, far = scenario(context)
    seen, _ = provider(monkeypatch, lambda value: 3 if value["candidate"].get("iri") == str(far)
                       and value["candidate"]["target_kind"] == "resource" else 0)
    opts = query_options(strategy, context_detail=detail)
    baseline = query(["closeQuestion"], **opts, context_order="graph_distance")
    result = query(["closeQuestion"], **opts)
    assert result["query"]["context_order"] == "relevance"
    assert result["context_page"]["ranking"]["status"] == "applied"
    assert result["related_context"][0]["id"] == str(far)
    assert result["context_page"]["ranking"]["filtered_count"] == 0
    assert {identity(r) for r in result["related_context"]} == {identity(r) for r in baseline["related_context"]}
    assert all(r["relevance"]["relevance_model"] == "actual-model" for r in result["related_context"])
    assert len(seen) == len({identity(c["candidate"]) for c in seen})
    assert all(c["candidate"].get("match") is None and c["candidate"].get("expansion") is None for c in seen)
    candidate = next(c for c in seen if c["candidate"].get("iri") == str(far)
                     and c["candidate"]["target_kind"] == "resource")
    assert candidate["candidate"]["data"]["action_definition"]["unknowns"] == ["approval timeout"]
    path = candidate["root_contexts"][0]["path"]
    assert [p["data"]["predicate"] for p in path if p["target_kind"] == "statement"] == [
        "https://business.test/next"] * 3
    if detail == "preview":
        assert "action_definition" not in result["related_context"][0].get("data", {})
        for root in result["primary_matches"]:
            for neighbor in root["neighbors"]:
                assert neighbor["preview_ref"] < len(result["related_context"])


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
@pytest.mark.parametrize("enabled", [True, False])
def test_frozen_pages_and_repeat_first_query_do_not_recall_expand_or_score(context, monkeypatch, strategy, enabled):
    service, _, _, query, _ = context
    scenario(context)
    provider(monkeypatch)
    service.settings.semantic_jev_enabled = enabled
    opts = query_options(strategy, context_limit=2)
    first = query(["closeQuestion"], **opts)
    assert first["context_page"]["ranking"]["status"] == ("applied" if enabled else "degraded")
    for name in ("_qualified_lexical_candidates", "_expand_neighborhood"):
        monkeypatch.setattr(service, name, Mock(side_effect=AssertionError(name)))
    monkeypatch.setattr(JevReranker, "score_context", Mock(side_effect=AssertionError("rescored")))
    repeated = query(["closeQuestion"], **opts)
    assert repeated["related_context"] == first["related_context"]
    assert repeated["context_page"]["ranking"]["snapshot_reused"] is True
    page = first
    rows = list(page["related_context"])
    for _ in range(30):
        cursor = page["context_page"]["next_context_cursor"]
        if not cursor:
            break
        page = query(["closeQuestion"], **opts, context_cursor=cursor)
        rows.extend(page["related_context"])
        assert page["context_page"]["ranking"]["elapsed_seconds"] == first["context_page"]["ranking"]["elapsed_seconds"]
    else:
        pytest.fail("pagination did not terminate")
    assert len(rows) == first["context_page"]["ranking"]["candidate_count"]
    assert len(rows) == len({identity(row) for row in rows})


@pytest.mark.parametrize("failure,score,model,reason", [
    ("missing", 1., "actual-model", "invalid_response"),
    ("timeout", 1., "actual-model", "timeout"),
    (None, True, "actual-model", "invalid_response"),
    (None, float("nan"), "actual-model", "invalid_response"),
    (None, 4., "actual-model", "invalid_response"),
    (None, 1., "different-model", "model_changed"),
])
def test_whole_set_fallback_and_safe_reason(context, monkeypatch, failure, score, model, reason):
    _, _, _, query, _ = context
    scenario(context)
    provider(monkeypatch, lambda c: score, failure=failure, model=model)
    opts = query_options()
    baseline = query(["closeQuestion"], **opts, context_order="graph_distance")
    result = query(["closeQuestion"], **opts)
    assert [identity(r) for r in result["related_context"]] == [identity(r) for r in baseline["related_context"]]
    assert result["context_page"]["ranking"]["reason"] == reason
    assert all(r["relevance"]["relevance_score"] is None
               and r["relevance"]["relevance_status"] == "unavailable" for r in result["related_context"])


@pytest.mark.parametrize("options", [{"depth": 0}, {"context_limit": 0}, {"context_order": "graph_distance"}])
def test_nonrequested_and_iri_never_score_context(context, monkeypatch, options):
    _, _, _, query, _ = context
    root, *_ = scenario(context)
    monkeypatch.setattr(JevReranker, "score_context", Mock(side_effect=AssertionError("scoring requested")))
    result = query(["closeQuestion"], **query_options(**options))
    assert result["context_page"]["ranking"]["status"] == "not_requested"
    anchor = query([str(root)], context_order="relevance", depth=1)
    assert anchor["query"]["context_order"] == "graph_distance"
    assert anchor["context_page"]["ranking"]["status"] == "not_requested"


@pytest.mark.parametrize("change", ["grant", "hidden", "timeout", "eviction", "ttl", "order"])
def test_fixed_relevance_visibility_and_configuration_binding(context, monkeypatch, change):
    service, graph, declare, query, _ = context
    root, *_ = scenario(context)
    hidden = declare("protected", "Object")
    link(graph, root, hidden)
    service.access_view = SemanticAccessView(requires_filtering=True,
                                           _unauthorized_iris=frozenset({str(hidden)}))
    provider(monkeypatch)
    opts = query_options(context_limit=2)
    first = query(["closeQuestion"], **opts)
    cursor = first["context_page"]["next_context_cursor"]
    if change == "grant":
        service.access_view = SemanticAccessView()
    elif change == "hidden":
        service.access_view = SemanticAccessView(requires_filtering=True,
                                               _unauthorized_iris=frozenset({str(hidden), "https://absent.test/"}))
    elif change == "timeout":
        service.settings.semantic_jev_timeout_seconds += 1
    elif change == "eviction":
        semantic_jev._SNAPSHOTS.clear()
    elif change == "ttl":
        for snapshot in semantic_jev._SNAPSHOTS.values():
            snapshot["expires"] = 0
    elif change == "order":
        opts["context_order"] = "graph_distance"
    if change == "hidden":
        page = query(["closeQuestion"], **opts, context_cursor=cursor)
        assert page["context_page"]["ranking"]["snapshot_reused"]
    else:
        error = SemanticContextCursorMismatch if change == "order" or change == "timeout" else SemanticContextSnapshotChanged
        with pytest.raises(error):
            query(["closeQuestion"], **opts, context_cursor=cursor)
    if change == "grant":
        fresh = query(["closeQuestion"], **opts)
        # Removing the last protection changes actual visibility without a model revision.
        remaining = list(fresh["related_context"])
        while cursor := fresh["context_page"]["next_context_cursor"]:
            fresh = query(["closeQuestion"], **opts, context_cursor=cursor)
            remaining.extend(fresh["related_context"])
        assert str(hidden) in {row.get("iri") for row in remaining}


def test_v4_signed_cursor_is_rejected(context):
    service = context[0]
    token = service.cursor_codec.encode(CursorPayload(kind="context", binding_digest="", model_revisions=(), version=4))
    with pytest.raises(ContextCursorInvalid, match="restart the query"):
        service.cursor_codec.decode(token, binding=None, expected_kind="context")


def test_related_http_prompt_removes_envelope_metadata_only(monkeypatch):
    seen, requests = provider(monkeypatch)
    item = {"id": "x", "ontology_id": "o", "kind": "instance", "match": {"score": 999},
            "relevance": {"relevance_score": 888}, "expansion": {"score_contexts": [777]},
            "data": {"match": 999, "relevance": 888, "expansion": 777}}
    settings = __import__("app.core.config", fromlist=["Settings"]).Settings(semantic_jev_api_key="test")
    result = JevReranker(settings).score_context(["公开问题"], [{"candidate": item, "root_contexts": [
        {"root": item, "path": [item], "resources": [item]}]}])
    assert result["status"] == "applied"
    assert len(requests) == 1
    for value in [seen[0]["candidate"], seen[0]["root_contexts"][0]["root"],
                  *seen[0]["root_contexts"][0]["path"], *seen[0]["root_contexts"][0]["resources"]]:
        assert not {"match", "relevance", "expansion"} & value.keys()
        assert value["data"] == item["data"]


@pytest.mark.parametrize("snapshot_changed", [False, True])
def test_incomplete_hydration_degrades_but_snapshot_change_is_not_swallowed(context, monkeypatch, snapshot_changed):
    from app.services import semantic_context_relevance
    from app.services.semantic_context_query import SemanticContextQueryError

    _, _, _, query, _ = context
    scenario(context)
    provider(monkeypatch)
    baseline = query(["closeQuestion"], **query_options(), context_order="graph_distance")
    error = (SemanticContextSnapshotChanged("changed") if snapshot_changed
             else SemanticContextQueryError("RDF chunk is incomplete"))
    monkeypatch.setattr(semantic_context_relevance, "context_inputs", Mock(side_effect=error))
    if snapshot_changed:
        with pytest.raises(SemanticContextSnapshotChanged):
            query(["closeQuestion"], **query_options())
    else:
        result = query(["closeQuestion"], **query_options())
        assert result["context_page"]["ranking"]["reason"] == "hydration_unavailable"
        assert [identity(r) for r in result["related_context"]] == [identity(r) for r in baseline["related_context"]]
        assert all(r["relevance"]["relevance_score"] is None for r in result["related_context"])
