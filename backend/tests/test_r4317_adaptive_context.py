"""Independent R4.3-017 behavior checks using the existing real SPARQL fixture."""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from unittest.mock import Mock

import httpx
import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS

from app.repositories.rdf_store import SparqlQueryTimeout
from app.services import semantic_context_adaptive, semantic_jev
from app.services.semantic_access import SemanticAccessDependencyError, SemanticAccessView
from app.services.semantic_context_query import SemanticContextSnapshotChanged
from app.services.semantic_jev import JevReranker, JevScoringError
from test_r4008_context_query import context as original_context  # noqa: F401
from test_r4008_context_query import identity
from test_semantic_context_query import _principal, _ready_ontology


@pytest.fixture
def context(original_context, monkeypatch):  # noqa: F811
    semantic_jev._SNAPSHOTS.clear()
    service, graph, declare, query, vocab = original_context
    service.settings.semantic_jev_enabled = True
    service.settings.semantic_jev_api_key = "independent-test-only"
    monkeypatch.setattr(JevReranker, "score", lambda self, queries, items, **kwargs:
                        ([2.0] * len(items), "test-model"))
    yield service, graph, declare, query, vocab
    semantic_jev._SNAPSHOTS.clear()


def branches(monkeypatch, policy=None):
    seen = []

    def score(self, queries, contexts, **kwargs):
        seen.append((copy.deepcopy(queries), copy.deepcopy(contexts), kwargs))
        scores = []
        for value in contexts:
            answer, exploration = policy(value) if policy else (1, 2)
            scores.append({"answer_score": answer,
                           "exploration_score": exploration if value["can_explore"] else None,
                           "status": "scored"})
        return {"scores": scores, "status": "applied", "model": "test-model"}

    monkeypatch.setattr(JevReranker, "score_branches", score)
    return seen


def reads(monkeypatch, service):
    recorded = []
    original = service.rdf_store.query_sparql

    def query(sparql, *args, **kwargs):
        if "semantic-context-neighborhood" in sparql:
            match = re.search(r"VALUES \?anchor \{([^}]+)\}", sparql)
            recorded.append(tuple(re.findall(r"<([^>]+)>", match.group(1))))
        return original(sparql, *args, **kwargs)

    monkeypatch.setattr(service.rdf_store, "query_sparql", query)
    return recorded


def edge(graph, source, target, predicate="next"):
    graph.add((source, URIRef("https://business.test/" + predicate), target))


def resources(result):
    return {row.get("iri"): row for row in result["related_context"]
            if row.get("target_kind") == "resource"}


def all_pages(query, expression, **opts):
    result = query([expression], **opts)
    rows = list(result["related_context"])
    primary = copy.deepcopy(result["primary_matches"])
    for _ in range(100):
        token = result["context_page"]["next_context_cursor"]
        if not token:
            break
        result = query([expression], **opts, context_cursor=token)
        assert result["primary_matches"] == primary
        rows.extend(result["related_context"])
    else:
        pytest.fail("context pagination did not terminate")
    assert len(rows) == len({identity(row) for row in rows})
    return rows, result


def test_default_fixed_explicit_depth_and_iri_do_not_overexpand(context, monkeypatch):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="uniqueRoot")
    mid = declare("mid", "Object")
    edge(graph, root, mid)
    seen = branches(monkeypatch)
    default = query(["uniqueRoot"])
    assert default["query"]["depth"] == 3
    assert default["query"]["expansion_strategy"] == "adaptive"
    seen.clear()
    for options, depth, strategy in [({"depth": 1}, 1, "adaptive"),
                                     ({"expansion_strategy": "fixed"}, 1, "fixed"),
                                     ({"depth": 0}, 0, "adaptive")]:
        result = query(["uniqueRoot"], **options)
        assert result["query"]["depth"] == depth
        assert result["query"]["expansion_strategy"] == strategy
    anchor = query([str(root)])
    assert anchor["query"]["depth"] == 1
    assert anchor["query"]["expansion_strategy"] == "fixed"
    zero = query(["uniqueRoot"], context_limit=0)
    assert zero["context_page"]["expansion"]["status"] == "not_requested"
    assert not seen


def test_selects_before_reading_and_keeps_bridge_unknown_and_true_path(context, monkeypatch):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="closureQuestion")
    bridge = declare("bridge", "Binding", actionDefinition={"conditions": ["authorized"],
                                                           "unknowns": ["remote result"]})
    background = declare("background", "Object")
    rule = declare("rule", "Rule")
    unknown = declare("unknown", "Rule", actionDefinition={"unknowns": ["exception approval"]})
    fourth = declare("fourth", "Object")
    for source, target in [(root, bridge), (root, background), (bridge, rule),
                           (rule, unknown), (unknown, fourth)]:
        edge(graph, source, target)
    dead = declare("dead", "Object")
    edge(graph, background, dead)
    seen = branches(monkeypatch, lambda c: (0, 0) if c["candidate"].get("iri") == str(background)
                    else (0, 3) if c["candidate"].get("iri") in {str(bridge), str(rule)}
                    else (1, 0))
    recorded = reads(monkeypatch, service)
    result = query(["closureQuestion"], depth=3, context_limit=100)
    anchors = Counter(iri for batch in recorded for iri in batch)
    assert anchors == Counter({str(root): 1, str(bridge): 1, str(rule): 1})
    returned = resources(result)
    assert {str(bridge), str(background), str(rule), str(unknown)} <= returned.keys()
    assert str(dead) not in returned and str(fourth) not in returned
    assert "path_bridge" in returned[str(rule)]["expansion"]["retained_as"]
    assert "answer_evidence" in returned[str(unknown)]["expansion"]["retained_as"]
    assert returned[str(unknown)]["root_paths"][0]["graph_distance"] == 3
    contexts = [c for _, batch, _ in seen for c in batch]
    bridge_context = next(c for c in contexts if c["candidate"].get("iri") == str(bridge))
    assert bridge_context["candidate"]["data"]["action_definition"]["conditions"] == ["authorized"]
    assert bridge_context["via_edge"]["data"]["subject"] == str(root)
    assert bridge_context["via_edge"]["data"]["object"] == str(bridge)
    assert {c["candidate"].get("iri") for c in contexts if not c["can_explore"]} >= {str(unknown)}
    assert all(queries == ["closureQuestion"] for queries, _, _ in seen)


def test_new_arrival_can_reconsider_shared_node_and_cycles_reuse_reads(context, monkeypatch):
    service, graph, declare, query, _ = context
    first = declare("first", "Action", label="commonRoot")
    second = declare("second", "Action", label="commonRoot")
    shared = declare("shared", "Object", label="sameName")
    other = declare("other", "Object", label="sameName")
    deep = declare("deep", "Rule")
    for source, target in [(first, shared), (second, shared), (first, other),
                           (shared, deep), (shared, shared), (shared, first)]:
        edge(graph, source, target)
    seen = branches(monkeypatch, lambda c: (1, 0) if c["root"]["iri"] == str(first)
                    and c["candidate"].get("iri") == str(shared) else (1, 2))
    recorded = reads(monkeypatch, service)
    result = query(["commonRoot"], semantic_roles=["Action"], context_limit=100)
    returned = resources(result)
    assert {str(shared), str(other), str(deep)} <= returned.keys()
    roots = {path["root_match_id"] for path in returned[str(shared)]["root_paths"]}
    assert roots == {str(first), str(second)}
    assert Counter(iri for batch in recorded for iri in batch)[str(shared)] == 1
    arrivals = [c for _, batch, _ in seen for c in batch if c["candidate"].get("iri") == str(shared)]
    assert {c["root"]["iri"] for c in arrivals} == {str(first), str(second)}
    assert len(result["related_context"]) == len({identity(row) for row in result["related_context"]})
    assert any(row["data"].get("subject") == str(shared)
               and row["data"].get("object") == str(shared) for row in result["related_context"])
    assert sum(len(batch) for _, batch, _ in seen) < 100


def test_deep_structured_reference_preserves_source_and_field_path(context, monkeypatch):
    _, graph, declare, query, vocab = context
    root = declare("root", "Action", label="mappingQuestion")
    mid = declare("mid", "Object")
    mapping = declare("mapping", "Mapping", mappingDefinition={"field_meanings": [
        {"conversion_rule_iri": "https://business.test/rule"}]})
    graph.add((mapping, RDF.type, URIRef(vocab + "TableMapping")))
    rule = declare("rule", "Rule", actionDefinition={"unknowns": ["conversion undefined"]})
    edge(graph, root, mid)
    edge(graph, mid, mapping)
    branches(monkeypatch)
    result = query(["mappingQuestion"], depth=3, context_limit=100)
    assert str(rule) in resources(result)
    reference = next(row for row in result["related_context"]
                     if row["data"].get("derived_reference")
                     and row["data"].get("target_iri") == str(rule))
    assert reference["data"]["source_iri"] == str(mapping)
    assert reference["data"]["field_path"] == "data.mapping_definition.field_meanings[0].conversion_rule_iri"
    assert "subject" not in reference["data"]
    assert resources(result)[str(rule)]["root_paths"][0]["graph_distance"] == 3


def test_hidden_bridge_predicate_and_nested_reference_never_score_or_advance(context, monkeypatch):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="authorizationQuestion")
    hidden = declare("hidden", "Binding")
    remote = declare("remote", "Rule")
    nested = declare("nested", "Rule", actionDefinition={"refs": [{"iri": str(hidden)}]})
    public = declare("public", "Object")
    for source, target in [(root, hidden), (hidden, remote), (root, nested)]:
        edge(graph, source, target)
    edge(graph, root, public, "secretPredicate")
    service.access_view = SemanticAccessView(requires_filtering=True, _unauthorized_iris=frozenset(
        {str(hidden), "https://business.test/secretPredicate"}))
    seen = branches(monkeypatch)
    recorded = reads(monkeypatch, service)
    result = query(["authorizationQuestion"], context_limit=100)
    rendered = json.dumps([result, seen])
    for iri in (hidden, remote, nested, public):
        assert str(iri) not in rendered
    assert all(str(hidden) not in batch and str(nested) not in batch for batch in recorded)


def test_fact_projection_does_not_prevent_legal_internal_traversal(context, monkeypatch):
    _, graph, declare, query, _ = context
    root, mid = declare("root", "Action"), declare("mid", "Object")
    edge(graph, root, Literal("uniqueFactAnchor"), "marker")
    edge(graph, root, mid)
    edge(graph, mid, Literal("42"), "amount")
    branches(monkeypatch)
    result = query(["uniqueFactAnchor"], depth=2, resource_types=["fact"], context_limit=100)
    assert any(row["data"].get("object") == "42" for row in result["related_context"])
    assert all(row["kind"] == "fact" for row in result["related_context"])
    assert result["context_page"]["expansion"]["path_projection"] == "filtered"


@pytest.mark.parametrize("jev_mode", ["enabled", "disabled", "failed"])
def test_both_pages_freeze_even_without_primary_scoring(context, monkeypatch, jev_mode):
    service, graph, declare, query, _ = context
    for index in range(3):
        root = declare(f"root-{index}", "Action", label="pagedRoot")
        for number in range(5):
            edge(graph, root, Literal(f"fact-{index}-{number}"), f"value-{number}")
    shared = declare("shared", "Object")
    for index in range(3):
        edge(graph, URIRef(f"https://business.test/root-{index}"), shared)
    seen = branches(monkeypatch)
    if jev_mode == "disabled":
        service.settings.semantic_jev_enabled = False
    if jev_mode == "failed":
        def fail(*args, **kwargs):
            raise JevScoringError("test failure")
        monkeypatch.setattr(JevReranker, "score", fail)
        monkeypatch.setattr(JevReranker, "score_branches", fail)
    recorded = reads(monkeypatch, service)
    opts = {"semantic_roles": ["Action"], "depth": 2, "limit": 1, "context_limit": 2}
    first = query(["pagedRoot"], **opts)
    second = query(["pagedRoot"], **opts, match_cursor=first["matches_page"]["next_match_cursor"])
    expected_primary = copy.deepcopy(second["primary_matches"])
    before = (len(recorded), len(seen))
    rows = list(second["related_context"])
    token = second["context_page"]["next_context_cursor"]
    assert token
    while token:
        following = query(["pagedRoot"], **opts, context_cursor=token)
        assert following["primary_matches"] == expected_primary
        rows.extend(following["related_context"])
        token = following["context_page"]["next_context_cursor"]
    assert (len(recorded), len(seen)) == before
    assert len(rows) == len({identity(row) for row in rows})
    assert {row["data"].get("object") for row in rows} >= {f"fact-1-{number}" for number in range(5)}
    repeated = query(["pagedRoot"], **opts)
    assert repeated["related_context"] == first["related_context"]
    assert (len(recorded), len(seen)) == before


def restricted(*iris):
    return SemanticAccessView(requires_filtering=True, _unauthorized_iris=frozenset(map(str, iris)))


@pytest.mark.parametrize("cursor_kind", ["context", "match"])
def test_newly_public_content_without_revision_invalidates_old_cursor(context, monkeypatch, cursor_kind):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="visibilityRoot")
    declare("root-2", "Action", label="visibilityRoot")
    x, y = declare("x", "Rule"), declare("y", "Rule")
    edge(graph, root, x)
    for number in range(4):
        edge(graph, root, Literal(f"public-{number}"), f"value-{number}")
    branches(monkeypatch)
    service.access_view = restricted(x, y)
    opts = {"semantic_roles": ["Action"], "context_limit": 1, "limit": 1}
    original = query(["visibilityRoot"], **opts)
    cursor = original[f"{cursor_kind}_page" if cursor_kind == "context" else "matches_page"][
        f"next_{cursor_kind}_cursor"]
    assert cursor
    service.access_view = restricted(y)
    with pytest.raises(SemanticContextSnapshotChanged):
        query(["visibilityRoot"], **opts, **{f"{cursor_kind}_cursor": cursor})
    fresh_rows, _ = all_pages(query, "visibilityRoot", **opts)
    assert any(row.get("iri") == str(x) for row in fresh_rows)
    assert str(y) not in json.dumps(fresh_rows)


def test_pure_hidden_changes_reuse_frozen_selection_and_failed_validation_is_closed(context, monkeypatch):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="hiddenChangeRoot")
    x, y = declare("x", "Rule"), declare("y", "Rule")
    edge(graph, x, y)
    for number in range(4):
        edge(graph, root, Literal(f"public-{number}"), f"value-{number}")
    seen = branches(monkeypatch)
    service.access_view = restricted(x, y)
    opts = {"context_limit": 1, "semantic_roles": ["Action"]}
    result = query(["hiddenChangeRoot"], **opts)
    token = result["context_page"]["next_context_cursor"]
    # Absent IRI changes control data, but neither visible RDF nor a frozen item.
    service.access_view = restricted(x, y, "https://business.test/absent-protection-member")
    resumed = query(["hiddenChangeRoot"], **opts, context_cursor=token)
    assert resumed["primary_matches"] == result["primary_matches"]
    assert not seen
    service.access_view = restricted(y)
    original = service.rdf_store.query_sparql
    def failed(sparql, *args, **kwargs):
        raise SparqlQueryTimeout("authorization source comparison interrupted")
    monkeypatch.setattr(service.rdf_store, "query_sparql", failed)
    with pytest.raises(SemanticAccessDependencyError):
        query(["hiddenChangeRoot"], **opts, context_cursor=token)
    monkeypatch.setattr(service.rdf_store, "query_sparql", original)


@pytest.mark.parametrize("budget_name,value,reason", [
    ("scoring_context_budget", 1, "scoring_budget_reached"),
    ("work_budget", 4, "expansion_budget_reached"),
    ("deadline_seconds", 0, "time_budget_reached"),
])
def test_request_budget_keeps_base_and_reports_partial(context, monkeypatch, budget_name, value, reason):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="budgetRoot")
    for number in range(4):
        branch = declare(f"branch-{number}", "Binding")
        edge(graph, root, branch)
        edge(graph, branch, Literal("deep legal evidence"), "condition")
    branches(monkeypatch)
    monkeypatch.setitem(semantic_context_adaptive.ADAPTIVE_CONFIG, budget_name, value)
    result = query(["budgetRoot"], context_limit=100)
    expansion = result["context_page"]["expansion"]
    assert expansion["status"] == "partial"
    assert reason in expansion["stop_reasons"]
    assert result["related_context"]
    assert expansion["usage"]["scoring_contexts"] <= semantic_context_adaptive.ADAPTIVE_CONFIG["scoring_context_budget"]
    if budget_name == "work_budget":
        assert expansion["usage"]["visible_work_items"] <= value


def test_width_is_global_and_reserves_low_answer_bridge(context, monkeypatch):
    service, graph, declare, query, _ = context
    for number in range(2):
        root = declare(f"root-{number}", "Action", label="widthRoot")
        for suffix in ["answer", "bridge"]:
            child = declare(f"{suffix}-{number}", "Object")
            edge(graph, root, child)
            edge(graph, child, Literal("downstream condition"), "condition")
    branches(monkeypatch, lambda c: (0, 1) if "bridge" in c["candidate"].get("iri", "") else (3, 3))
    monkeypatch.setitem(semantic_context_adaptive.ADAPTIVE_CONFIG, "widths", [2, 1])
    monkeypatch.setitem(semantic_context_adaptive.ADAPTIVE_CONFIG, "bridge_slots", [1, 1])
    recorded = reads(monkeypatch, service)
    result = query(["widthRoot"], depth=2, semantic_roles=["Action"], context_limit=100)
    anchors = [iri for batch in recorded for iri in batch if not iri.rsplit("/", 1)[-1].startswith("root-")]
    assert len(anchors) == 2
    assert any("bridge" in iri for iri in anchors)
    assert "branch_width_limit" in result["context_page"]["expansion"]["stop_reasons"]


def test_branch_scoring_failure_keeps_unscored_and_stops_deep_reads(context, monkeypatch):
    service, graph, declare, query, _ = context
    root, bridge = declare("root", "Action", label="failureRoot"), declare("bridge", "Binding")
    edge(graph, root, bridge)
    def fail(*args, **kwargs):
        raise JevScoringError("scoring unavailable")
    monkeypatch.setattr(JevReranker, "score_branches", fail)
    recorded = reads(monkeypatch, service)
    result = query(["failureRoot"], context_limit=100)
    assert recorded == [(str(root),)]
    row = resources(result)[str(bridge)]
    assert "unscored" in row["expansion"]["retained_as"]
    assert row["expansion"]["score_contexts"][0]["answer_score"] is None
    assert result["context_page"]["expansion"]["selection_status"] == "degraded"


@pytest.mark.parametrize("detail", ["full", "compact", "preview"])
def test_projection_preserves_selection_state_and_preview_omits_full_body(context, monkeypatch, detail):
    _, graph, declare, query, _ = context
    root = declare("root", "Action", label="projectionRoot")
    branch = declare("branch", "Rule", actionDefinition={"conditions": ["a" * 400]})
    edge(graph, root, branch)
    branches(monkeypatch)
    result = query(["projectionRoot"], depth=2, context_detail=detail, context_limit=100)
    row = resources(result)[str(branch)]
    assert row["expansion"]["retained_as"]
    assert row["expansion"]["score_contexts"]
    assert result["primary_matches"][0]["match"]["relevance_score"] == 2.0
    if detail == "preview":
        assert "a" * 400 not in json.dumps(result["related_context"])


def test_same_iri_cross_ontology_keeps_stable_identity(context, in_memory_session, monkeypatch):
    service, graph, declare, _, vocab = context
    root = declare("root", "Action", label="crossRoot")
    target = declare("target", "Object")
    edge(graph, root, target)
    _ready_ontology(in_memory_session, service.settings, ontology_id="ontology-2")
    other = service.rdf_store.dataset.graph(URIRef("https://graphs.test/ontology/ontology-2"))
    other.add((target, RDFS.label, Literal("target")))
    other.add((target, URIRef(vocab + "semanticDefinition"), Literal('{"semantic_role":"Object"}')))
    branches(monkeypatch)
    result = service.query_multi(project_id="project-1", scope_mode="ontologies",
                                 ontology_ids=["ontology-1", "ontology-2"], queries=["crossRoot"],
                                 search_mode="lexical", principal=_principal(), context_limit=100)
    definitions = [row for row in result["related_context"]
                   if row.get("target_kind") == "resource" and row.get("iri") == str(target)]
    assert {row["ontology_id"] for row in definitions} == {"ontology-1", "ontology-2"}


def test_branch_upstream_model_drift_keeps_first_hop_and_does_not_advance(context, monkeypatch):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="modelDriftRoot")
    bridge = declare("bridge", "Binding")
    remote = declare("remote", "Rule")
    edge(graph, root, bridge)
    edge(graph, bridge, remote)
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
            response = Mock(status_code=200, headers={"x-opencode-upstream-model-id": "drifted-model"})
            response.json.return_value = {"model": "drifted-model", "answers": {
                key: {"type": "score", "score": 3} for key in json["questions"]}}
            return response

    monkeypatch.setattr(httpx, "Client", Client)
    recorded = reads(monkeypatch, service)
    result = query(["modelDriftRoot"], context_limit=100)
    assert sent
    assert recorded == [(str(root),)]
    assert str(bridge) in resources(result) and str(remote) not in resources(result)
    expansion = result["context_page"]["expansion"]
    assert expansion["selection_status"] == "degraded"
    assert expansion["scoring"]["model"] == "test-model"
    assert resources(result)[str(bridge)]["expansion"]["score_contexts"][0]["answer_score"] is None


def test_second_layer_read_failure_is_partial_and_preserves_base(context, monkeypatch):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="rdfFailureRoot")
    bridge = declare("bridge", "Binding")
    edge(graph, root, bridge)
    branches(monkeypatch)
    original = service.rdf_store.query_sparql

    def failed(sparql, *args, **kwargs):
        if "semantic-context-neighborhood" in sparql and re.search(
                rf"VALUES \?anchor \{{\s*<{re.escape(str(bridge))}>\s*\}}", sparql):
            raise SparqlQueryTimeout("selected branch RDF read timed out")
        return original(sparql, *args, **kwargs)

    monkeypatch.setattr(service.rdf_store, "query_sparql", failed)
    result = query(["rdfFailureRoot"], context_limit=100)
    assert str(bridge) in resources(result)
    assert result["context_page"]["expansion"]["status"] == "partial"


def test_primary_http_failure_does_not_retry_provider_for_branch_selection(context, monkeypatch):
    service, graph, declare, query, _ = context
    root = declare("root", "Action", label="primaryFailureRoot")
    bridge, remote = declare("bridge", "Binding"), declare("remote", "Rule")
    edge(graph, root, bridge)
    edge(graph, bridge, remote)
    def failed_primary(*args, **kwargs):
        raise JevScoringError("http_error")
    monkeypatch.setattr(JevReranker, "score", failed_primary)
    seen = branches(monkeypatch)
    recorded = reads(monkeypatch, service)
    result = query(["primaryFailureRoot"], context_limit=100)
    assert not seen
    assert recorded == [(str(root),)]
    assert str(bridge) in resources(result) and str(remote) not in resources(result)
    expansion = result["context_page"]["expansion"]
    assert expansion["selection_status"] == "degraded"
    assert "scoring_unavailable" in expansion["stop_reasons"]
