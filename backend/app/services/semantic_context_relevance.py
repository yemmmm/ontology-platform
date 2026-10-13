"""R4.3-018: rank the complete, bounded context before taking a page."""
from __future__ import annotations

import math
import time
from collections import defaultdict

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.rdf_store import RdfStoreError
from app.services.semantic_jev import (
    JEV_RANKING_VERSION,
    RELATED_CONTEXT_CONFIG,
    RELATED_CONTEXT_VERSION,
    JevReranker,
    JevScoringError,
)


def ranking_state(order, count=0):
    return {
        "requested_order": order, "effective_order": "graph_distance",
        "status": "not_requested", "version": RELATED_CONTEXT_VERSION,
        "score_version": JEV_RANKING_VERSION, "score_scale": [0, 3],
        "model": None, "reason": None, "candidate_count": count, "scored_count": 0,
        "filtered_count": 0, "ranking_scope": "current_match_page_bounded_context",
        "elapsed_seconds": 0, "snapshot_reused": False,
    }


def relevance(score=None, model=None, status="not_requested"):
    return {"relevance_score": score, "relevance_scale": [0, 3],
            "relevance_model": model, "relevance_version": JEV_RANKING_VERSION,
            "relevance_status": status}


def canonical_paths(service, root, material, depth):
    """One shortest stable chain per candidate on actually read edges, without more traversal."""
    key = service._identity_key
    resources = defaultdict(list)
    adjacency = defaultdict(list)
    for identity, item in sorted(material.items()):
        data = item.get("data", {})
        if item.get("target_kind") not in {"statement", "derived_reference"}:
            if item.get("iri"):
                resources[item["iri"]].append(item)
            continue
        subject = data.get("subject") or data.get("source_iri")
        target = data.get("object") or data.get("target_iri")
        is_uri = data.get("object_type") == "uri" or data.get("derived_reference")
        adjacency[subject].append((item, target if is_uri else None))
        if is_uri and not data.get("derived_reference"):
            adjacency[target].append((item, subject))
    result = {key(root): [root]}
    data = root.get("data", {})
    if root.get("target_kind") == "statement":
        anchors = [data.get("subject")]
        if data.get("object_type") == "uri":
            anchors.append(data.get("object"))
    else:
        anchors = [root.get("iri")]
    frontier = {}
    for iri in anchors:
        if not iri:
            continue
        endpoints = resources.get(iri, [])
        path = [root] if root.get("iri") == iri else [root] + endpoints[:1]
        frontier[iri] = path
        for item in endpoints:
            result[key(item)] = [root] if key(item) == key(root) else [root, item]
    seen = set(frontier)
    for _ in range(depth):
        following = {}
        # The lexicographic path identity breaks ties independently of read order.
        for iri, prefix in sorted(frontier.items(), key=lambda pair: tuple(key(i) for i in pair[1])):
            for edge, target in sorted(adjacency[iri], key=lambda pair: key(pair[0])):
                path = prefix + [edge]
                result.setdefault(key(edge), path)
                if target is None:
                    continue
                for endpoint in resources[target]:
                    result.setdefault(key(endpoint), path + [endpoint])
                if target not in seen:
                    candidate = path + resources[target][:1]
                    previous = following.get(target)
                    if previous is None or tuple(key(i) for i in candidate) < tuple(key(i) for i in previous):
                        following[target] = candidate
        seen.update(following)
        frontier = following
    return result


def context_inputs(service, scope, roots, rows, paths):
    from app.services.semantic_context_query import _public_item

    key = service._identity_key
    roots_by_key = {key(root): root for root in roots}
    chains = {identity: canonical_paths(service, root, service._context_material.get(identity, {}),
                                       service._request_depth)
              for identity, root in roots_by_key.items()}
    # Definitions only: hydration may read an already referenced predicate/endpoint,
    # but never its next neighborhood. Keep separate Ontology variants.
    iris = set()
    for material in service._context_material.values():
        for item in material.values():
            data = item.get("data", {})
            iris.update(value for value in (
                data.get("subject"), data.get("source_iri"), data.get("predicate"),
                data.get("target_iri"), data.get("object") if data.get("object_type") == "uri" else None,
            ) if value)
    seeds = [{"id": iri, "iri": iri, "kind": "instance", "ontology_id": entry.ontology_id,
              "data": {}, "assertion_kind": "asserted"}
             for iri in sorted(iris) for entry in scope.ontologies]
    service._hydrate_candidates(seeds, scope)
    definitions = defaultdict(list)
    for seed in seeds:
        own = service._description_cache[(seed["ontology_id"], seed["iri"])].get("_own_rows", [])
        if not own:
            continue
        resource = service._resource_from_rows(own, scope, seed["iri"])
        if resource is not None and service.access_view.filter_candidate(resource):
            identity = key(resource)
            if identity not in service._work_items:
                if len(service._work_items) >= service._visible_work_budget:
                    raise JevScoringError("candidate_budget_reached")
                service._work_items.add(identity)
            definitions[seed["iri"]].append(_public_item(resource))
    inputs = []
    for item in rows:
        root_contexts = []
        for root_key, root in sorted(roots_by_key.items()):
            if not any(path.get("root_ontology_id") == root["ontology_id"]
                       and path["root_match_id"] == root["id"] for path in paths[key(item)]):
                continue
            path = chains[root_key].get(key(item))
            resources = {}
            missing = set()
            for value in path or [item]:
                data = value.get("data", {})
                references = [data.get("subject"), data.get("source_iri"), data.get("predicate"),
                              data.get("target_iri")]
                if data.get("object_type") == "uri":
                    references.append(data.get("object"))
                for iri in references:
                    if not iri:
                        continue
                    if not definitions[iri]:
                        missing.add(iri)
                    for definition in definitions[iri]:
                        resources[key(definition)] = definition
            root_contexts.append({
                "root": _public_item(root),
                "connection_status": "connected" if path else "source_only",
                "path": [_public_item(value) for value in path] if path else [],
                "resources": [value for _, value in sorted(resources.items())],
                "definition_not_saved": sorted(missing),
            })
        inputs.append({"candidate": _public_item(item), "root_contexts": root_contexts})
    return inputs


def safe_reason(reason):
    if reason in {"candidate_budget_reached", "hydration_unavailable"}:
        return reason
    if reason in {"api_key_not_configured", "scoring_disabled"}:
        return "scoring_disabled"
    if "exceeds_context" in reason:
        return "candidate_exceeds_context"
    if "timeout" in reason or reason == "time_budget_reached":
        return "timeout"
    if "model_changed" in reason:
        return "model_changed"
    return "invalid_response"


def rank_context(service, scope, roots, rows, paths, queries):
    from app.services.semantic_context_query import (
        SemanticContextQueryError, SemanticContextSnapshotChanged, _context_sort_key,
    )

    state = ranking_state(service._context_order, len(rows))
    service._context_ranking = state
    for item in rows:
        item["relevance"] = relevance()
    if service._context_order != "relevance" or not rows:
        return rows
    started = time.monotonic()
    deadline = service._query_started + RELATED_CONTEXT_CONFIG["deadline_seconds"]
    reason = None
    scores = []
    model = None
    try:
        if not service.settings.semantic_jev_enabled or not service.settings.semantic_jev_api_key:
            raise JevScoringError("scoring_disabled")
        if len(rows) > RELATED_CONTEXT_CONFIG["candidate_budget"]:
            raise JevScoringError("candidate_budget_reached")
        models = {value for value in [(service._jev_ranking or {}).get("model"),
                                     service._expansion.get("scoring", {}).get("model")] if value}
        if len(models) > 1:
            raise JevScoringError("model_changed")
        remaining = min(service._jev_remaining_seconds, deadline - time.monotonic())
        if remaining <= 0:
            raise JevScoringError("timeout")
        service._adaptive_read_deadline = deadline
        try:
            inputs = context_inputs(service, scope, roots, rows, paths)
        except TimeoutError:
            raise JevScoringError("timeout") from None
        except SemanticContextSnapshotChanged:
            raise
        except (RdfStoreError, SQLAlchemyError, SemanticContextQueryError):
            raise JevScoringError("hydration_unavailable") from None
        finally:
            service._adaptive_read_deadline = None
        remaining = min(service._jev_remaining_seconds, deadline - time.monotonic())
        if remaining <= 0:
            raise JevScoringError("timeout")
        scoring_started = time.monotonic()
        try:
            result = JevReranker(service.settings).score_context(
                queries, inputs, timeout_seconds=remaining, expected_model=next(iter(models), None),
            )
        finally:
            service._jev_remaining_seconds = max(
                0, service._jev_remaining_seconds - (time.monotonic() - scoring_started)
            )
        scores = result.get("scores", [])
        model = result.get("model")
        if len(scores) != len(rows):
            raise JevScoringError("invalid_response")
        valid = [score.get("status") == "scored"
                 and type(score.get("answer_score")) in (int, float)
                 and math.isfinite(score["answer_score"]) and 0 <= score["answer_score"] <= 3
                 for score in scores]
        state["scored_count"] = sum(valid)
        if result.get("status") != "applied" or not all(valid):
            raise JevScoringError(result.get("reason", "invalid_response"))
        if not isinstance(model, str) or not model:
            raise JevScoringError("invalid_response")
        if models and model not in models:
            raise JevScoringError("model_changed")
    except JevScoringError as exc:
        reason = safe_reason(str(exc))
    state["elapsed_seconds"] = round(time.monotonic() - started, 6)
    if reason:
        state.update(status="degraded", reason=reason)
        for item in rows:
            item["relevance"] = relevance(status="unavailable")
    else:
        state.update(status="applied", model=model, effective_order="relevance")
        for item, score in zip(rows, scores, strict=True):
            item["relevance"] = relevance(float(score["answer_score"]), model, "scored")
        rows.sort(key=lambda item: (-item["relevance"]["relevance_score"],
                                   _context_sort_key(item, scope, paths)))
    return rows
