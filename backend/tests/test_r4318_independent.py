"""Independent R4.3-018 contracts over real SPARQL and local HTTP scoring."""
from __future__ import annotations

import copy
import json
from unittest.mock import Mock

import httpx
import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from app.services import semantic_jev
from app.services.semantic_access import SemanticAccessDependencyError, SemanticAccessView
from app.services.semantic_context_query import (
    SemanticContextCursorMismatch,
    SemanticContextSnapshotChanged,
)
from app.services.semantic_jev import RELATED_CONTEXT_INSTRUCTIONS
from test_r4008_context_query import context as original_context  # noqa: F401
from test_r4008_context_query import identity
from test_r4317_adaptive_context import edge, reads, restricted
from test_semantic_context_query import _principal, _ready_ontology


@pytest.fixture
def context(original_context):  # noqa: F811
    semantic_jev._SNAPSHOTS.clear()
    service, graph, declare, query, vocab = original_context
    service.settings.semantic_jev_enabled = True
    service.settings.semantic_jev_api_key = "independent-local-test"
    yield service, graph, declare, query, vocab
    semantic_jev._SNAPSHOTS.clear()


def provider(monkeypatch, score=None, failure=None):
    """Stub transport only; use the production Jev adapter and ranking service."""
    calls = []
    contexts = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, endpoint, *, json: dict, headers, timeout):
            calls.append(copy.deepcopy(json))
            answers = {}
            related = []
            for key, question in json["questions"].items():
                if question.get("context_version") == "related-context-relevance-v1":
                    value = __import__("json").loads(
                        question["instructions"].removeprefix(RELATED_CONTEXT_INSTRUCTIONS)
                    )
                    contexts.append(value)
                    related.append(value)
                    answer = score(value) if score else 1
                else:
                    answer = 2
                answers[key] = {"type": "score", "score": answer}
            payload = {"model": "actual-test-model", "answers": answers}
            if related and failure:
                failure(payload, related, calls)
            response = Mock(status_code=200, headers={})
            response.json.return_value = payload
            return response

    monkeypatch.setattr(httpx, "Client", Client)
    return calls, contexts


def drain(query, expression, **opts):
    page = query([expression], **opts)
    rows = list(page["related_context"])
    primary = copy.deepcopy(page["primary_matches"])
    initial_ranking = copy.deepcopy(page["context_page"]["ranking"])
    while token := page["context_page"]["next_context_cursor"]:
        page = query([expression], **opts, context_cursor=token)
        assert page["primary_matches"] == primary
        assert {k: v for k, v in page["context_page"]["ranking"].items()
                if k != "snapshot_reused"} == {
                    k: v for k, v in initial_ranking.items() if k != "snapshot_reused"}
        rows.extend(page["related_context"])
    assert len(rows) == len({identity(row) for row in rows})
    return rows, page


def values(rows):
    return {identity(row): (row.get("data"), row.get("root_paths")) for row in rows}


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
def test_order_modes_and_non_requested_boundaries(context, monkeypatch, strategy):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="modeRoot")
    edge(graph, root, declare("near", "Object"))
    _, seen = provider(monkeypatch)
    result = query(["modeRoot"], expansion_strategy=strategy, depth=1)
    assert result["query"]["context_order"] == "relevance"
    assert result["context_page"]["ranking"]["status"] == "applied"
    assert len(seen) == len(result["related_context"])
    seen.clear()
    old = query(["modeRoot"], expansion_strategy=strategy, depth=1,
                context_order="graph_distance")
    assert old["context_page"]["ranking"]["status"] == "not_requested"
    assert values(old["related_context"]) == values(result["related_context"])
    for expression, opts in [(str(root), {}), ("modeRoot", {"depth": 0}),
                             ("modeRoot", {"context_limit": 0}), ("absentzzzz", {})]:
        page = query([expression], **opts)
        assert page["context_page"]["ranking"]["status"] == "not_requested"
    assert not seen


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
def test_whole_union_sort_dedup_zero_ties_and_frozen_pages(context, monkeypatch, strategy):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="wholeRoot")
    other = declare("other-root", "Action", label="wholeRoot")
    bridge = declare("bridge", "Binding")
    far = declare("far", "Rule", actionDefinition={"conditions": ["approved"],
                                                   "unknowns": ["remote approval"]})
    near = declare("near", "Object")
    for source, target in [(root, bridge), (other, bridge), (bridge, far),
                           (root, near), (far, bridge)]:
        edge(graph, source, target)
    edge(graph, far, Literal("explicit unknown", lang="zh"), "exception")
    def score(candidate):
        return 3 if candidate["candidate"].get("iri") == str(far) else 0
    calls, seen = provider(monkeypatch, score)
    recorded = reads(monkeypatch, service)
    opts = {"expansion_strategy": strategy, "semantic_roles": ["Action"], "depth": 3,
            "context_limit": 2}
    baseline, _ = drain(query, "wholeRoot", **opts, context_order="graph_distance")
    ranked, _ = drain(query, "wholeRoot", **opts)
    assert values(ranked) == values(baseline)
    assert ranked[0]["iri"] == str(far)
    assert [identity(r) for r in ranked[1:]] == [identity(r) for r in baseline
                                                if r.get("iri") != str(far)]
    assert len(seen) == len(ranked)
    shared = next(c for c in seen if c["candidate"].get("iri") == str(bridge))
    assert len(shared["root_contexts"]) == 2
    assert all(len(c["root_contexts"]) <= 2 for c in seen)
    assert all(r["relevance"]["relevance_status"] == "scored" for r in ranked)
    before = (len(calls), len(recorded))
    # Repeat first query reuses the complete context snapshot as well as the roots.
    repeated = query(["wholeRoot"], **opts)
    assert repeated["context_page"]["ranking"]["snapshot_reused"]
    assert (len(calls), len(recorded)) == before


def test_complete_input_reverse_literal_predicate_and_business_metadata(context, monkeypatch):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="inputRoot")
    rule = declare("rule", "Rule", actionDefinition={
        "conditions": ["permit"], "exceptions": ["urgent"], "unknowns": ["unconfirmed"],
        "match": "business-match", "fusion": {"relevance": "business-relevance"},
    })
    pred = declare("constrains", "Relationship", actionDefinition={"meaning": "actual direction"})
    graph.add((rule, pred, root))
    graph.add((rule, URIRef("https://business.test/threshold"), Literal("42", datatype=XSD.integer)))
    # Predicate and IRI-looking literal have graph content but are not traversal endpoints.
    edge(graph, pred, declare("predicate-remote", "Rule"))
    edge(graph, root, Literal("https://business.test/literal-node"), "text")
    edge(graph, URIRef("https://business.test/literal-node"), declare("literal-remote", "Rule"))
    calls, seen = provider(monkeypatch)
    result = query(["inputRoot"], expansion_strategy="fixed", depth=2)
    assert result["context_page"]["ranking"]["status"] == "applied"
    own = next(c for c in seen if c["candidate"].get("iri") == str(rule))
    definition = own["candidate"]["data"]["action_definition"]
    assert definition["unknowns"] == ["unconfirmed"]
    assert definition["exceptions"] == ["urgent"]
    assert definition["match"] == "business-match"
    assert definition["fusion"]["relevance"] == "business-relevance"
    path = own["root_contexts"][0]["path"]
    statements = [v["data"] for v in path if v.get("target_kind") == "statement"]
    assert any(v["subject"] == str(rule) and v["object"] == str(root)
               and v["predicate"] == str(pred) for v in statements)
    assert any(r["iri"] == str(pred) and r["data"]["action_definition"]["meaning"]
               == "actual direction" for r in own["root_contexts"][0]["resources"])
    fact = next(c for c in seen if c["candidate"]["data"].get("object") == "42")
    assert fact["candidate"]["data"]["object_datatype"] == str(XSD.integer)
    for c in seen:
        for item in [c["candidate"], *[v for rc in c["root_contexts"] for v in rc["path"]]]:
            assert not {"match", "fusion", "relevance", "expansion"}.intersection(item)
    encoded = json.dumps(calls)
    assert "predicate-remote" not in encoded
    assert "literal-remote" not in encoded
    assert all(json.loads(call["state"]) == {"original_queries": ["inputRoot"]}
               for call in calls if any(q.get("context_version") for q in call["questions"].values()))


@pytest.mark.parametrize("detail", ["full", "compact", "preview"])
def test_projection_ranking_and_neighbor_references(context, monkeypatch, detail):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="projectionRoot")
    for n in range(3):
        item = declare(f"item-{n}", "Rule", actionDefinition={"unknowns": ["private-long-input" * 20]})
        edge(graph, root, item)
    provider(monkeypatch, lambda c: 3 if c["candidate"].get("iri", "").endswith("item-2") else 0)
    result = query(["projectionRoot"], expansion_strategy="fixed", context_detail=detail,
                   context_limit=2)
    assert result["related_context"][0]["iri"].endswith("item-2")
    assert all(r["relevance"]["relevance_scale"] == [0, 3] for r in result["related_context"])
    assert result["primary_matches"][0]["match"]["relevance_score"] == 2
    if detail == "preview":
        assert "private-long-input" not in json.dumps(result["related_context"])
        for neighbor in result["primary_matches"][0]["neighbors"]:
            row = result["related_context"][neighbor["preview_ref"]]
            assert any(result["primary_matches"][p["root_index"]]["id"] == str(root)
                       for p in row["root_paths"])


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
def test_disabled_snapshot_without_root_rank_survives_provider_recovery(context, monkeypatch, strategy):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="disabledRoot")
    for n in range(5):
        edge(graph, root, Literal(f"fact-{n}"), f"p{n}")
    service.settings.semantic_jev_enabled = False
    calls, _ = provider(monkeypatch)
    recorded = reads(monkeypatch, service)
    opts = {"expansion_strategy": strategy, "context_limit": 1, "depth": 1}
    first = query(["disabledRoot"], **opts)
    assert first["context_page"]["ranking"]["reason"] == "scoring_disabled"
    assert first["context_page"]["next_context_cursor"]
    # Transport recovery leaves the frozen degraded ranking unchanged.
    monkeypatch.setattr(service, "_qualified_lexical_candidates", Mock(side_effect=AssertionError("recall")))
    monkeypatch.setattr(service, "_neighborhood_chunks", Mock(side_effect=AssertionError("expand")))
    before = len(recorded)
    rows = list(first["related_context"])
    page = first
    while token := page["context_page"]["next_context_cursor"]:
        page = query(["disabledRoot"], **opts, context_cursor=token)
        rows.extend(page["related_context"])
        assert page["context_page"]["ranking"]["status"] == "degraded"
        assert all(r["relevance"]["relevance_score"] is None for r in page["related_context"])
    assert len(rows) == len({identity(r) for r in rows})
    assert len(recorded) == before and not calls


@pytest.mark.parametrize("mutation", ["release-last", "revoke", "hidden", "dependency", "config",
                                     "restart", "ttl", "revision", "index"])
def test_fixed_relevance_authorization_and_snapshot_changes(context, monkeypatch, mutation):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="accessRoot")
    hidden = declare("hidden", "Rule")
    edge(graph, root, hidden)
    for n in range(3):
        edge(graph, root, Literal(f"fact-{n}"), f"p{n}")
    provider(monkeypatch)
    service.access_view = restricted(hidden)
    opts = {"expansion_strategy": "fixed", "context_limit": 1}
    first = query(["accessRoot"], **opts)
    token = first["context_page"]["next_context_cursor"]
    assert token
    if mutation == "release-last":
        service.access_view = SemanticAccessView()
    elif mutation == "revoke":
        service.access_view = restricted(hidden, root)
    elif mutation in {"hidden", "dependency"}:
        service.access_view = restricted(hidden, "https://business.test/absent")
        if mutation == "dependency":
            from app.repositories.rdf_store import RdfStoreError
            monkeypatch.setattr(service.rdf_store, "query_sparql", Mock(side_effect=RdfStoreError("failed")))
    elif mutation == "config":
        service.settings.semantic_jev_timeout_seconds += 1
    elif mutation == "restart":
        semantic_jev._SNAPSHOTS.clear()
    elif mutation == "ttl":
        for snapshot in semantic_jev._SNAPSHOTS.values():
            snapshot["expires"] = 0
    elif mutation == "revision":
        from app.repositories.models import OntologyModel
        ontology = service.session.get(OntologyModel, "ontology-1")
        ontology.model_revision += 1
        service.session.commit()
    elif mutation == "index":
        from app.services.semantic_retrieval import PgVectorRetrievalRepository
        monkeypatch.setattr(PgVectorRetrievalRepository, "index_status", Mock(return_value={"changed": True}))
    if mutation == "hidden":
        resumed = query(["accessRoot"], **opts, context_cursor=token)
        assert resumed["context_page"]["ranking"]["snapshot_reused"]
    else:
        error = SemanticAccessDependencyError if mutation == "dependency" else (
            SemanticContextCursorMismatch if mutation == "config" else SemanticContextSnapshotChanged)
        with pytest.raises(error):
            query(["accessRoot"], **opts, context_cursor=token)
    if mutation == "release-last":
        rows, _ = drain(query, "accessRoot", **opts)
        assert any(r.get("iri") == str(hidden) for r in rows)


@pytest.mark.parametrize("bad", [True, float("nan"), -1, 4, "2", None])
def test_invalid_scores_degrade_entire_set(context, monkeypatch, bad):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="invalidRoot")
    edge(graph, root, declare("near", "Rule"))
    provider(monkeypatch, lambda c: bad if c["candidate"].get("target_kind") == "resource" else 3)
    old = query(["invalidRoot"], expansion_strategy="fixed", context_order="graph_distance")
    result = query(["invalidRoot"], expansion_strategy="fixed")
    assert [identity(r) for r in result["related_context"]] == [identity(r) for r in old["related_context"]]
    assert result["context_page"]["ranking"]["status"] == "degraded"
    assert result["context_page"]["ranking"]["reason"] == "invalid_response"
    assert all(r["relevance"]["relevance_score"] is None and r["relevance"]["relevance_model"] is None
               for r in result["related_context"])


@pytest.mark.parametrize("failure_mode", ["missing", "model"])
def test_partial_http_batch_failure_publishes_no_partial_scores(context, monkeypatch, failure_mode):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="batchRoot")
    for n in range(12):
        child = declare(f"child-{n}", "Rule", actionDefinition={"conditions": ["x" * 2500]})
        edge(graph, root, child)
    related_batches = []

    def fail(payload, candidates, calls):
        related_batches.append(candidates)
        if len(related_batches) == 2:
            if failure_mode == "missing":
                payload["answers"].pop(next(iter(payload["answers"])))
            else:
                payload["model"] = "different-actual-model"

    provider(monkeypatch, failure=fail)
    old = query(["batchRoot"], expansion_strategy="fixed", context_order="graph_distance")
    result = query(["batchRoot"], expansion_strategy="fixed")
    ranking = result["context_page"]["ranking"]
    assert len(related_batches) == 2
    assert ranking["status"] == "degraded"
    assert 0 < ranking["scored_count"] < ranking["candidate_count"]
    assert ranking["reason"] == ("invalid_response" if failure_mode == "missing" else "model_changed")
    assert [identity(r) for r in result["related_context"]] == [identity(r) for r in old["related_context"]]
    assert all(r["relevance"]["relevance_status"] == "unavailable" for r in result["related_context"])


def test_oversized_complete_value_is_not_truncated_or_dropped(context, monkeypatch):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="oversizeRoot")
    child = declare("child", "Rule", actionDefinition={"unknowns": ["界" * 11000]})
    edge(graph, root, child)
    provider(monkeypatch)
    result = query(["oversizeRoot"], expansion_strategy="fixed")
    assert result["context_page"]["ranking"]["reason"] == "candidate_exceeds_context"
    assert next(r for r in result["related_context"] if r.get("iri") == str(child))["data"][
        "action_definition"]["unknowns"] == ["界" * 11000]
    assert all(r["relevance"]["relevance_score"] is None for r in result["related_context"])


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
def test_statement_root_keeps_actual_edge_and_filtered_internal_path(context, monkeypatch, strategy):
    _, graph, declare, query, _ = context
    root = declare("root", "Action")
    middle = declare("middle", "Binding")
    graph.add((root, URIRef("https://business.test/marker"), Literal("zxqstatementanchor")))
    edge(graph, root, middle)
    edge(graph, middle, Literal("necessary fact"), "condition")
    _, seen = provider(monkeypatch)
    result = query(["zxqstatementanchor"], expansion_strategy=strategy,
                   depth=2, resource_types=["fact"])
    assert result["context_page"]["ranking"]["status"] == "applied"
    assert result["context_page"]["expansion"]["path_projection"] == "filtered"
    assert all(r["kind"] == "fact" for r in result["related_context"])
    candidate = next(c for c in seen if c["candidate"]["data"].get("object") == "necessary fact")
    context_path = candidate["root_contexts"][0]["path"]
    assert context_path[0]["data"]["object"] == "zxqstatementanchor"
    assert any(p["data"].get("subject") == str(root) and p["data"].get("object") == str(middle)
               for p in context_path)
    assert context_path[-1]["data"]["object"] == "necessary fact"


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
def test_derived_reference_keeps_field_path_and_distinct_ontology_values(context, in_memory_session,
                                                                     monkeypatch, strategy):
    service, graph, declare, _, vocab = context
    target = declare("target", "Rule", actionDefinition={"unknowns": ["first-definition"]})
    mapping = declare("mapping", "Mapping", label="derivedRootQuestion", mappingDefinition={
        "field_meanings": [{"conversion_rule_iri": str(target)}]})
    graph.add((mapping, RDF.type, URIRef(vocab + "TableMapping")))
    _ready_ontology(in_memory_session, service.settings, ontology_id="ontology-2")
    other = service.rdf_store.dataset.graph(URIRef("https://graphs.test/ontology/ontology-2"))
    other.add((target, RDFS.label, Literal("target-second")))
    other.add((target, URIRef(vocab + "actionDefinition"), Literal(json.dumps({
        "unknowns": ["second-definition"]}))))
    _, seen = provider(monkeypatch)
    result = service.query_multi(project_id="project-1", scope_mode="ontologies",
                                 ontology_ids=["ontology-1", "ontology-2"],
                                 queries=["derivedRootQuestion"], search_mode="lexical",
                                 expansion_strategy=strategy, depth=1, principal=_principal())
    assert result["context_page"]["ranking"]["status"] == "applied"
    refs = [c for c in seen if c["candidate"].get("target_kind") == "derived_reference"]
    assert len(refs) == 1
    data = refs[0]["candidate"]["data"]
    assert data["field_path"] == "data.mapping_definition.field_meanings[0].conversion_rule_iri"
    assert data["source_iri"] == str(mapping) and data["target_iri"] == str(target)
    assert "subject" not in data
    targets = [c for c in seen if c["candidate"].get("iri") == str(target)
               and c["candidate"].get("target_kind") == "resource"]
    assert {c["candidate"]["ontology_id"] for c in targets} == {"ontology-1", "ontology-2"}
    assert {c["candidate"]["data"]["action_definition"]["unknowns"][0] for c in targets} == {
        "first-definition", "second-definition"}
    for c in targets:
        assert c["root_contexts"][0]["path"][-1]["ontology_id"] == c["candidate"]["ontology_id"]
        assert any(p.get("target_kind") == "derived_reference" for p in c["root_contexts"][0]["path"])


def test_source_only_producer_input_has_origin_without_invented_statement(context):
    from app.services.semantic_context_relevance import context_inputs
    service, _, _, query, _ = context
    query(["absent-source-fixture"], depth=0)
    root = {"id": "op", "iri": "https://business.test/op", "kind": "operation",
            "ontology_id": "ontology-1", "data": {"target_resource_type_iri": "https://business.test/Type"}}
    # Execute the actual producer; no edge has been read or stored for this source.
    scope = service.scope_resolver.resolve(project_id="project-1", scope_mode="ontologies",
                                           ontology_ids=["ontology-1"])
    item = service._operation_target_context([root], scope, limit=None, enabled=True)[0]
    service._request_depth = 1
    service._context_material = {service._identity_key(root): {
        service._identity_key(root): root, service._identity_key(item): item}}
    inputs = context_inputs(service, scope, [root], [item], {
        service._identity_key(item): [{"root_match_id": "op", "root_ontology_id": "ontology-1"}]})
    rc = inputs[0]["root_contexts"][0]
    assert rc["connection_status"] == "source_only" and rc["path"] == []
    assert rc["root"]["data"]["target_resource_type_iri"] == item["iri"]
    assert inputs[0]["candidate"]["origin"] == "resource"


@pytest.mark.parametrize("count", [512, 513])
def test_real_union_candidate_budget_boundary_keeps_all_rows(context, monkeypatch, count):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="budgetRootQuestion")
    # Labels are metadata; the semantic definition contributes one statement.
    for n in range(count - 1):
        edge(graph, root, Literal(str(n)), f"value{n}")
    _, seen = provider(monkeypatch)
    result = query(["budgetRootQuestion"], expansion_strategy="fixed", semantic_roles=["Action"],
                   context_limit=1000)
    ranking = result["context_page"]["ranking"]
    assert ranking["candidate_count"] == count
    assert len(result["related_context"]) == count
    if count == 512:
        assert ranking["status"] == "applied" and len(seen) == count
    else:
        assert ranking["reason"] == "candidate_budget_reached" and not seen
        assert all(r["relevance"]["relevance_score"] is None for r in result["related_context"])


def test_shared_request_scoring_budget_exhausted_by_primary_does_not_add_time(context, monkeypatch):
    import time
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="sharedBudgetRoot")
    edge(graph, root, declare("child", "Rule"))
    now = [time.monotonic()]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    calls, seen = provider(monkeypatch)
    original_score = semantic_jev.JevReranker.score

    def delayed_score(self, *args, **kwargs):
        result = original_score(self, *args, **kwargs)
        now[0] += self.settings.semantic_jev_timeout_seconds
        return result

    monkeypatch.setattr(semantic_jev.JevReranker, "score", delayed_score)
    result = query(["sharedBudgetRoot"], expansion_strategy="fixed")
    assert result["related_context"]
    assert result["context_page"]["ranking"]["reason"] == "timeout"
    assert len(calls) == 1 and not seen


@pytest.mark.parametrize("failure", ["timeout", "incomplete"])
def test_referenced_definition_hydration_failure_degrades_complete_set(context, monkeypatch, failure):
    from app.repositories.rdf_store import SparqlQueryTimeout
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="zxqhydrationtoken")
    child = declare("child", "Rule")
    predicate = declare("linkedBy", "Relationship")
    edge(graph, root, child, "linkedBy")
    provider(monkeypatch)
    original = service.rdf_store.query_sparql
    original_hydrate = service._hydrate_candidates
    hits = []

    def hydrate(items, scope):
        # Earlier retrieval may already have hydrated the predicate. Exercise the
        # real uncached referenced-definition read at the scoring boundary.
        if service._adaptive_read_deadline is not None:
            service._description_cache.pop(("ontology-1", str(predicate)), None)
        return original_hydrate(items, scope)

    def read(sparql, *args, **kwargs):
        if (service._adaptive_read_deadline is not None
                and "semantic-context-resource-descriptions" in sparql and str(predicate) in sparql):
            hits.append(sparql)
            if failure == "timeout":
                raise SparqlQueryTimeout("raw upstream private payload must remain opaque")
            result = original(sparql, *args, **kwargs)
            result.truncated = True
            return result
        return original(sparql, *args, **kwargs)

    monkeypatch.setattr(service.rdf_store, "query_sparql", read)
    monkeypatch.setattr(service, "_hydrate_candidates", hydrate)
    result = query(["zxqhydrationtoken"], expansion_strategy="fixed", semantic_roles=["Action"])
    assert hits
    assert result["context_page"]["ranking"]["reason"] == "hydration_unavailable"
    assert result["related_context"]
    assert all(r["relevance"]["relevance_score"] is None for r in result["related_context"])
    assert "raw upstream" not in json.dumps(result)


def test_duplicate_answer_mapping_in_real_http_json_is_invalid(context, monkeypatch):
    service = context[0]

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            return httpx.Response(200, content=b'{"model":"actual-test-model","answers":{'
                                  b'"c0":{"type":"score","score":0},'
                                  b'"c0":{"type":"score","score":3}}}')

    monkeypatch.setattr(httpx, "Client", Client)
    result = semantic_jev.JevReranker(service.settings).score_context(
        ["question"], [{"candidate": {"id": "one", "data": {"unknowns": ["explicit unknown"]}},
                        "root_contexts": []}])
    assert result["status"] == "degraded"
    assert result["scores"][0]["answer_score"] is None


def test_adaptive_partial_selection_can_have_applied_context_ranking(context, monkeypatch):
    from app.services import semantic_context_adaptive
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="partialRootQuestion")
    for n in range(3):
        child = declare(f"child-{n}", "Binding")
        edge(graph, root, child)
        edge(graph, child, Literal("deep condition"), "value")
    provider(monkeypatch)
    monkeypatch.setitem(semantic_context_adaptive.ADAPTIVE_CONFIG, "scoring_context_budget", 1)
    result = query(["partialRootQuestion"], semantic_roles=["Action"], depth=3)
    assert result["context_page"]["expansion"]["status"] == "partial"
    assert result["context_page"]["ranking"]["status"] == "applied"
    assert result["context_page"]["ranking"]["filtered_count"] == 0


@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
def test_match_next_page_gets_its_own_context_ranking_and_shared_origin(context, monkeypatch, strategy):
    _, graph, declare, query, _ = context
    shared = declare("shared", "Object")
    for n in range(2):
        root = declare(f"root-{n}", "Action", label="matchPageQuestion")
        edge(graph, root, shared)
    _, seen = provider(monkeypatch)
    opts = {"expansion_strategy": strategy, "semantic_roles": ["Action"], "depth": 1,
            "limit": 1}
    first = query(["matchPageQuestion"], **opts)
    previous = len(seen)
    second = query(["matchPageQuestion"], **opts,
                   match_cursor=first["matches_page"]["next_match_cursor"])
    assert len(seen) > previous
    assert first["primary_matches"][0]["id"] != second["primary_matches"][0]["id"]
    for page in (first, second):
        assert page["context_page"]["ranking"]["status"] == "applied"
        row = next(r for r in page["related_context"] if r.get("iri") == str(shared))
        assert row["root_paths"] == [{"root_match_id": page["primary_matches"][0]["id"],
                                     "root_ontology_id": "ontology-1", "graph_distance": 1}]
