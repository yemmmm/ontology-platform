"""Bounded, layer-by-layer selection of already authorized semantic context."""

from __future__ import annotations

import copy
import hashlib
import json
import time
from collections import defaultdict

from app.services.semantic_jev import JEV_RANKING_VERSION, JevReranker, JevScoringError

ADAPTIVE_VERSION = "adaptive-context-v1"
ADAPTIVE_CONFIG = {
    "version": ADAPTIVE_VERSION,
    "answer_min": 1,
    "exploration_min": 1,
    "widths": [32, 16],
    "bridge_slots": [8, 4],
    "work_budget": 5000,
    "scoring_context_budget": 512,
    "deadline_seconds": 30,
}


def selection_config_digest(settings):
    return digest([ADAPTIVE_CONFIG, settings.semantic_jev_timeout_seconds])


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()


class AdaptiveContextExpansion:
    """Concrete selection policy; RDF reads and authorization remain on the service."""

    def __init__(self, service, scope, roots, queries, depth, resource_types, assertion_types):
        self.service = service
        self.scope = scope
        self.roots = roots
        self.queries = queries
        self.depth = depth
        self.resource_types = resource_types
        self.assertion_types = assertion_types
        self.config = ADAPTIVE_CONFIG
        self.items = {}
        self.base_origins = {}
        self.retained = defaultdict(set)
        self.scores = defaultdict(list)
        self.links_cache = {}
        self.seen_contexts = set()
        self.stop_reasons = []
        self.hints = {}
        self.partial = False
        self.degraded = False
        ranking = service._jev_ranking or {}
        self.scoring_stopped = (ranking.get("status") == "degraded"
                                and ranking.get("reason") != "candidate_exceeds_context")
        self.scoring_count = 0
        self.width_usage = [0, 0]
        self.model = (service._jev_ranking or {}).get("model")

    def key(self, item):
        return self.service._identity_key(item)

    @staticmethod
    def edge(item):
        return item.get("target_kind") in {"statement", "derived_reference"} or (
            {"subject", "predicate", "object"} <= item.get("data", {}).keys()
        )

    def stop(self, reason, contexts=(), *, partial=True):
        if reason not in self.stop_reasons:
            self.stop_reasons.append(reason)
        self.partial |= partial
        for context in contexts:
            item = context["candidate"]
            if self.edge(item) or not item.get("iri"):
                continue
            self.hints[self.key(item)] = {
                "iri": item["iri"], "ontology_id": item["ontology_id"],
                "stopped_at_depth": context["distance"], "reason": reason,
            }

    def remember(self, item, root, path, distance):
        key = self.key(item)
        self.items.setdefault(key, copy.deepcopy(item))

    def keep(self, context, reason):
        candidate = context["candidate"]
        self.retained[self.key(candidate)].add(reason)
        # Actual path closure, including low-answer bridge nodes and real edges.
        for item in context["path"]:
            self.retained[self.key(item)].add("path_bridge")

    def links(self, source, *, base=False):
        key = self.key(source)
        if key not in self.links_cache:
            if not base and time.monotonic() >= self.service._adaptive_deadline:
                raise TimeoutError("time_budget_reached")
            self.service._adaptive_read_deadline = None if base else self.service._adaptive_deadline
            try:
                source = {**copy.deepcopy(source), "distance": 0}
                self.service._adaptive_partial_items = {}
                try:
                    self.links_cache[key] = self.service._related_for_root(
                        source, scope=self.scope, depth=1, context_limit=self.config["work_budget"],
                        selected_resource_types=set(self.service._all_resource_types),
                        selected_assertion_types=self.assertion_types,
                    )
                except (TimeoutError, *self.service._rdf_read_errors) as exc:
                    self.stop("time_budget_reached" if isinstance(exc, TimeoutError)
                              else "rdf_read_unavailable", [{"candidate": source,
                                                             "distance": source.get("distance", 0)}])
                    # Values already authorized and hydrated before the failing read survive.
                    self.links_cache[key] = list(self.service._adaptive_partial_items.values())
            finally:
                self.service._adaptive_read_deadline = None
        return self.links_cache[key]

    def arrivals(self, root, source, prefix, distance, *, base=False):
        contexts = []
        try:
            values = self.links(source, base=base)
        except (TimeoutError, JevScoringError):
            self.stop("time_budget_reached", [{"candidate": source, "distance": distance - 1}])
            return contexts
        except self.service._rdf_read_errors:
            self.stop("expansion_budget_reached", [{"candidate": source,
                                                    "distance": distance - 1}])
            return contexts
        iri = source.get("iri")
        resources = defaultdict(list)
        for item in values:
            if not self.edge(item) and item.get("iri"):
                resources[item["iri"]].append(item)
        for item in values:
            if base:
                self.remember(item, root, prefix + [item], distance)
                self.retained[self.key(item)].add("base_context")
                self.base_origins[(self.key(root), self.key(item))] = distance
            if not self.edge(item):
                continue
            data = item.get("data", {})
            subject = data.get("subject") or data.get("source_iri")
            target = data.get("object") or data.get("target_iri")
            uri_target = data.get("object_type") == "uri" or data.get("derived_reference")
            if subject != iri and not (uri_target and target == iri):
                continue
            edge_path = prefix + [item]
            self.remember(item, root, edge_path, distance)
            contexts.append(self.context(root, item, item, edge_path, distance, False))
            other = target if subject == iri else subject
            if subject == iri and not uri_target:
                continue
            for endpoint in resources.get(other, []):
                # Self/back edges survive closure, but never spawn a cycle task.
                if self.key(endpoint) in {self.key(value) for value in prefix}:
                    continue
                path = edge_path + [endpoint]
                self.remember(endpoint, root, path, distance)
                contexts.append(self.context(root, endpoint, item, path, distance,
                                             distance < self.depth))
        return contexts

    def context(self, root, item, edge, path, distance, can_explore):
        return {"root": root, "candidate": item, "via_edge": edge, "path": path,
                "distance": distance, "can_explore": can_explore}

    def score(self, contexts):
        pending = []
        for context in contexts:
            identity = digest([self.key(context["root"]), self.key(context["candidate"]),
                               [self.key(item) for item in context["path"]]])
            if identity not in self.seen_contexts:
                self.seen_contexts.add(identity)
                pending.append(context)
        remaining = self.config["scoring_context_budget"] - self.scoring_count
        submitted, overflow = pending[:remaining], pending[remaining:]
        if overflow:
            self.stop("scoring_budget_reached", overflow)
            for context in overflow:
                self.unavailable(context)
        time_left = min(self.service._adaptive_deadline - time.monotonic(),
                        self.service._jev_remaining_seconds)
        if not submitted:
            return []
        if time_left <= 0 or self.scoring_stopped or not self.service.settings.semantic_jev_enabled:
            reason = "time_budget_reached" if time_left <= 0 else "scoring_unavailable"
            self.stop(reason, submitted)
            self.degraded = True
            for context in submitted:
                self.unavailable(context)
            return []
        start = time.monotonic()
        self.scoring_count += len(submitted)
        try:
            from app.services.semantic_context_query import _public_item

            inputs = [{"candidate": _public_item(context["candidate"]),
                       "root": _public_item(context["root"]),
                       "via_edge": _public_item(context["via_edge"]),
                       "path": [_public_item(item) for item in context["path"]],
                       "can_explore": context["can_explore"]} for context in submitted]
            result = JevReranker(self.service.settings).score_branches(
                self.queries, inputs, timeout_seconds=time_left, expected_model=self.model,
            )
        except JevScoringError:
            result = {"scores": [{"status": "unavailable"}] * len(submitted),
                      "status": "degraded", "reason": "scoring_unavailable"}
        finally:
            self.service._jev_remaining_seconds = max(
                0, self.service._jev_remaining_seconds - (time.monotonic() - start)
            )
        if result.get("model"):
            self.model = result["model"]
        if result.get("status") == "degraded":
            self.degraded = True
            self.stop("scoring_unavailable", submitted)
            if result.get("reason") != "candidate_exceeds_context":
                self.scoring_stopped = True
        qualified = []
        for context, score in zip(submitted, result["scores"], strict=True):
            if score.get("status") != "scored":
                self.unavailable(context)
                continue
            self.scores[self.key(context["candidate"])].append(self.metadata(context, score))
            if context["distance"] > 1 and score["answer_score"] >= self.config["answer_min"]:
                self.keep(context, "answer_evidence")
            if (context["can_explore"] and score.get("exploration_score") is not None
                    and score["exploration_score"] >= self.config["exploration_min"]):
                qualified.append((context, score))
        return qualified

    def metadata(self, context, score):
        edge = context["via_edge"]
        root = context["root"]
        return {"root": {"ontology_id": root["ontology_id"], "id": root["id"],
                         "kind": root["kind"]},
                "via_edge": {"ontology_id": edge["ontology_id"], "id": edge["id"],
                             "kind": edge["kind"]},
                "path_digest": digest([self.key(item) for item in context["path"]]),
                "answer_score": score.get("answer_score"),
                "exploration_score": score.get("exploration_score"), "scale": [0, 3],
                "answer_version": JEV_RANKING_VERSION,
                "exploration_version": "jev-context-exploration-v1", "model": self.model,
                "status": score.get("status", "unavailable")}

    def unavailable(self, context):
        self.degraded = True
        self.keep(context, "unscored")
        self.scores[self.key(context["candidate"])].append(
            self.metadata(context, {"status": "unavailable"})
        )

    def select(self, qualified, level):
        qualified.sort(key=lambda pair: (-pair[1]["exploration_score"], -pair[1]["answer_score"],
                                        self.key(pair[0]["candidate"]),
                                        digest([self.key(item) for item in pair[0]["path"]])))
        by_endpoint = {}
        for context, score in qualified:
            by_endpoint.setdefault(self.key(context["candidate"]), (context, score))
        candidates = list(by_endpoint.values())
        bridges = [pair for pair in candidates if pair[1]["answer_score"] < self.config["answer_min"]]
        chosen = bridges[:self.config["bridge_slots"][level]]
        chosen_ids = {self.key(pair[0]["candidate"]) for pair in chosen}
        chosen += [pair for pair in candidates if self.key(pair[0]["candidate"]) not in chosen_ids][
            :self.config["widths"][level] - len(chosen)
        ]
        chosen_ids = {self.key(pair[0]["candidate"]) for pair in chosen}
        rejected = [context for context, _ in candidates
                    if self.key(context["candidate"]) not in chosen_ids]
        if rejected:
            self.stop("branch_width_limit", rejected, partial=False)
        self.width_usage[level] = len(chosen_ids)
        # Keep distinct real arrival contexts for a selected endpoint, reusing its read.
        return [context for context, _ in qualified if self.key(context["candidate"]) in chosen_ids]

    def run(self):
        service = self.service
        service._work_items = set()
        service._work_stopped = False
        service._visible_work_budget = self.config["work_budget"]
        contexts = []
        for root in self.roots:
            self.items[self.key(root)] = root
            self.retained[self.key(root)].add("base_context")
            if self.edge(root):
                sources = service._adaptive_statement_endpoints(root, self.scope)
            else:
                sources = [root]
            for source in sources:
                prefix = [root] if source is root else [root, source]
                self.items.setdefault(self.key(source), source)
                self.retained[self.key(source)].add("base_context")
                contexts.extend(self.arrivals(root, source, prefix, 1, base=True))
            if service._work_stopped:
                break
        for distance in range(1, self.depth + 1):
            if distance == 1:
                contexts = [context for context in contexts if context["can_explore"]]
            if not contexts:
                break
            qualified = self.score(contexts)
            if distance >= self.depth or self.scoring_stopped or service._work_stopped:
                break
            selected = self.select(qualified, distance - 1)
            following = []
            for context in selected:
                if time.monotonic() >= service._adaptive_deadline:
                    self.stop("time_budget_reached", selected)
                    break
                following.extend(self.arrivals(context["root"], context["candidate"],
                                               context["path"], distance + 1))
                if service._work_stopped:
                    break
            contexts = following
        if service._work_stopped:
            self.stop("expansion_budget_reached")
        # Only add already-read real connections whose endpoints survived selection.
        kept_iris = {self.items[key].get("iri") for key in self.retained if not self.edge(self.items[key])}
        for key, item in self.items.items():
            data = item.get("data", {})
            if self.edge(item) and (data.get("object_type") == "uri" or data.get("derived_reference")):
                if ((data.get("subject") or data.get("source_iri")) in kept_iris
                        and (data.get("object") or data.get("target_iri")) in kept_iris):
                    self.retained[key].add("connection")
        primary_keys = {self.key(root) for root in self.roots}
        paths = self.selected_paths()
        rows = []
        for key, reasons in self.retained.items():
            if key in primary_keys:
                continue
            item = self.items[key]
            if not paths[key] or item["kind"] not in self.resource_types:
                continue
            item = copy.deepcopy(item)
            item["distance"] = min(path["graph_distance"] for path in paths[key])
            item["expansion"] = {"retained_as": sorted(reasons),
                                 "score_contexts": self.scores[key]}
            rows.append(item)
        from app.services.semantic_context_query import _context_sort_key

        rows.sort(key=lambda item: _context_sort_key(item, self.scope, paths))
        if not self.stop_reasons:
            self.stop_reasons.append("depth_limit" if contexts else "policy_complete")
        service._expansion = {
            "status": "partial" if self.partial else "complete", "strategy": "adaptive",
            "version": ADAPTIVE_VERSION, "completeness_scope": "selected_subgraph",
            "selection_status": "degraded" if self.degraded else (
                "applied" if self.scoring_count else "not_requested"),
            "stop_reasons": self.stop_reasons,
            "path_projection": "partial" if self.partial else (
                "filtered" if self.resource_types != set(service._all_resource_types) else "complete"),
            "budgets": copy.deepcopy(self.config),
            "usage": {"visible_work_items": len(service._work_items),
                      "scoring_contexts": self.scoring_count, "widths": self.width_usage,
                      "elapsed_seconds": round(time.monotonic() - service._query_started, 6)},
            "scoring": {"model": self.model, "answer_version": JEV_RANKING_VERSION,
                        "exploration_version": "jev-context-exploration-v1"},
            "resume_hints": [value for _, value in sorted(self.hints.items())][:16],
            "hints_truncated": len(self.hints) > 16,
        }
        return [service._decorate(item, self.scope) for item in self.roots], rows, paths

    def selected_paths(self):
        """Shortest source distances on the kept, actually read graph only."""
        paths = defaultdict(list)
        resources = defaultdict(list)
        adjacency = defaultdict(list)
        for key in self.retained:
            item = self.items[key]
            if not self.edge(item):
                resources[item.get("iri")].append(key)
                continue
            data = item.get("data", {})
            subject = data.get("subject") or data.get("source_iri")
            target = data.get("object") or data.get("target_iri")
            is_uri = data.get("object_type") == "uri" or data.get("derived_reference")
            adjacency[subject].append((key, target if is_uri else None))
            if is_uri and not data.get("derived_reference"):
                adjacency[target].append((key, subject))
        for root in self.roots:
            data = root.get("data", {})
            if self.edge(root):
                anchors = [data.get("subject")]
                if data.get("object_type") == "uri":
                    anchors.append(data.get("object"))
            else:
                anchors = [root.get("iri")]
            seen = {iri: 0 for iri in anchors if iri}
            distances = {}
            for iri in seen:
                distances.update({key: 0 for key in resources[iri]})
            for distance in range(1, self.depth + 1):
                frontier = [iri for iri, value in seen.items() if value == distance - 1]
                for iri in frontier:
                    for edge_key, target in adjacency[iri]:
                        distances[edge_key] = min(distances.get(edge_key, distance), distance)
                        if target is None:
                            continue
                        for key in resources[target]:
                            distances[key] = min(distances.get(key, distance), distance)
                        if target not in seen:
                            seen[target] = distance
            # Existing producer-only one-hop context has no inferred connection.
            for (root_key, key), distance in self.base_origins.items():
                if root_key == self.key(root) and key in self.retained:
                    distances.setdefault(key, distance)
            for key, distance in distances.items():
                paths[key].append({"root_match_id": root["id"],
                                   "root_ontology_id": root["ontology_id"],
                                   "graph_distance": distance})
        return paths
