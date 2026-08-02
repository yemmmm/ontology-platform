"""Deterministic unified semantic context retrieval for external Agents."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from rdflib import Literal, URIRef
from rdflib.namespace import RDF
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.models import SemanticRuleDefinitionModel, SemanticRuleModel
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import AuthPrincipal
from app.services.ontology_lineage import LineageTargetNotFound, OntologyLineageService
from app.services.semantic_context_cursor import (
    CURSOR_KIND_CONTEXT,
    CURSOR_KIND_MATCH,
    ContextCursorCodec,
    ContextCursorInvalid,
    ContextCursorMismatch,
    ContextSnapshotChanged,
    CursorBinding,
    CursorPayload,
    binding_digest,
    make_binding,
)
from app.services.semantic_lineage_identity import (
    InvalidLineageStatement,
    canonical_iri,
    statement_id_for_quad,
)
from app.services.semantic_query_scope import SemanticQueryScope, SemanticQueryScopeResolver
from app.services.semantic_shape_endpoint_service import SemanticShapeEndpointService
from app.services.semantic_retrieval import (
    SemanticResourceRetrievalService,
    fuse_context_candidates,
    governed_mapping_lexical_candidates,
    promote_exact_label_candidates,
    recall_summary,
)
from app.services.semantic_sparql_templates import (
    semantic_context_candidates_query,
    semantic_context_neighborhood_query,
)
from app.services.operation_semantics import (
    OPERATION_SCHEMA_VERSION,
    OperationValidationError,
    operation_predicates,
    operation_vocabulary,
    validate_operation_payload,
)


RESOURCE_TYPE_ORDER = ("concept", "instance", "relation", "fact", "rule", "operation")
RESOURCE_TYPES = set(RESOURCE_TYPE_ORDER)
ASSERTION_TYPES = {"asserted", "derived"}
_KIND_ORDER = {kind: index for index, kind in enumerate(RESOURCE_TYPE_ORDER)}
_CLASS_TYPES = {
    "http://www.w3.org/2002/07/owl#Class",
    "http://www.w3.org/2000/01/rdf-schema#Class",
}
_RELATION_TYPES = {
    "http://www.w3.org/2002/07/owl#ObjectProperty",
    "http://www.w3.org/2002/07/owl#DatatypeProperty",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property",
}
_METADATA_PREDICATES = {
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://www.w3.org/2000/01/rdf-schema#comment",
    "http://www.w3.org/2004/02/skos/core#altLabel",
    "http://purl.org/dc/terms/description",
}


class SemanticContextQueryError(RuntimeError):
    status_code = 400
    code = "invalid_query"


class SemanticContextCursorInvalid(SemanticContextQueryError):
    status_code = 400
    code = "invalid_context_cursor"


class SemanticContextCursorMismatch(SemanticContextQueryError):
    status_code = 400
    code = "context_cursor_mismatch"


class SemanticContextSnapshotChanged(SemanticContextQueryError):
    status_code = 409
    code = "context_snapshot_changed"


class SemanticContextQueryService:
    """Run one lexical candidate, ranking, neighborhood, and lineage pipeline."""

    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticQueryScopeResolver,
        lineage_service: OntologyLineageService | None = None,
        shape_endpoint: SemanticShapeEndpointService | None = None,
        cursor_codec: ContextCursorCodec | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.lineage_service = lineage_service or OntologyLineageService(session, rdf_store)
        self.shape_endpoint = shape_endpoint or SemanticShapeEndpointService(
            session, rdf_store, scope_resolver.settings
        )
        self.operation_vocab = operation_vocabulary(scope_resolver.settings)
        self.operation_predicates = operation_predicates(scope_resolver.settings)
        self.operation_type = self.operation_vocab["type"]
        self.settings = scope_resolver.settings
        self.cursor_codec = cursor_codec

    def query(
        self,
        *,
        project_id: str,
        scope_mode: str,
        ontology_ids: list[str] | None,
        query: str,
        resource_types: list[str] | None = None,
        assertion_types: list[str] | None = None,
        search_mode: str = "hybrid",
        depth: int = 1,
        limit: int = 20,
        context_limit: int = 100,
        principal: AuthPrincipal | None = None,
        match_cursor: str | None = None,
        context_cursor: str | None = None,
    ) -> dict[str, Any]:
        """Backward-compatible single-expression entry point.

        Normalizes the legacy ``query`` string into a one-item ``queries``
        list and delegates to :meth:`query_multi`. Existing single-expression
        callers continue to work; new callers should use ``query_multi``.
        """
        return self.query_multi(
            project_id=project_id,
            scope_mode=scope_mode,
            ontology_ids=ontology_ids,
            queries=[query],
            resource_types=resource_types,
            assertion_types=assertion_types,
            search_mode=search_mode,
            depth=depth,
            limit=limit,
            context_limit=context_limit,
            principal=principal,
            match_cursor=match_cursor,
            context_cursor=context_cursor,
        )

    def query_multi(
        self,
        *,
        project_id: str,
        scope_mode: str,
        ontology_ids: list[str] | None,
        queries: list[str],
        resource_types: list[str] | None = None,
        assertion_types: list[str] | None = None,
        search_mode: str = "hybrid",
        depth: int = 1,
        limit: int = 20,
        context_limit: int = 100,
        principal: AuthPrincipal | None = None,
        match_cursor: str | None = None,
        context_cursor: str | None = None,
    ) -> dict[str, Any]:
        """Run the R1.2-004 multi-expression Context Query pipeline.

        See design §5 for the contract. This method resolves scope once,
        submits one bounded embedding batch for all distinct normalized
        expressions, fuses candidates before decoration/expansion, and emits
        one response with independent match/context page state and cursors.
        """
        if principal is None:
            raise SemanticContextQueryError(
                "A server-derived principal binding is required for Context Query"
            )
        if (match_cursor is not None) and (context_cursor is not None):
            raise SemanticContextQueryError(
                "Provide at most one of match_cursor or context_cursor"
            )
        normalized_input = _normalize_input_queries(queries)
        original_queries = list(normalized_input.original)
        execution_set = normalized_input.execution
        normalized_queries = [item.text for item in execution_set]
        if not execution_set:
            raise SemanticContextQueryError("queries must contain at least one expression")
        _validate_filters(resource_types, assertion_types, depth, limit)
        _validate_context_limit(context_limit)
        if search_mode not in {"hybrid", "lexical"}:
            raise SemanticContextQueryError("search_mode must be hybrid or lexical")
        selected_resource_types = set(resource_types or RESOURCE_TYPES)
        selected_assertion_types = set(assertion_types or ASSERTION_TYPES)

        scope = self.scope_resolver.resolve(
            project_id=project_id,
            scope_mode=scope_mode,
            ontology_ids=ontology_ids,
        )
        # REST injects one codec per application so ephemeral cursors survive
        # across requests.  Direct/MCP callers without an injected codec keep
        # the historical per-query construction semantics.
        cursor_codec = self.cursor_codec or ContextCursorCodec.from_settings(self.settings)
        workspace_versions = tuple(
            (entry.ontology_id, entry.workspace_version) for entry in scope.ontologies
        )
        source_signatures = tuple(
            (entry.ontology_id, entry.source_signature) for entry in scope.ontologies
        )
        binding = make_binding(
            principal=principal,
            project_id=project_id,
            scope_mode=scope_mode,
            ontology_ids=ontology_ids or [],
            original_queries=original_queries,
            normalized_queries=normalized_queries,
            resource_types=resource_types,
            assertion_types=assertion_types,
            search_mode=search_mode,
            depth=depth,
            limit=limit,
            context_limit=context_limit,
            workspace_versions=workspace_versions,
            source_signatures=source_signatures,
        )

        warnings: list[dict[str, str]] = [*scope.warnings, *_ontology_warnings(scope)]
        if not scope.graph_iris:
            return self._multi_response(
                scope=scope,
                original_queries=original_queries,
                normalized_queries=normalized_queries,
                primary=[],
                related=[],
                matched_queries_by_item={},
                fusion_by_item={},
                root_paths_by_item={},
                recall=self._empty_recall(search_mode),
                warnings=warnings,
                matches_truncated=False,
                context_truncated=False,
                match_cursor_out=None,
                context_cursor_out=None,
            )

        candidate_limit = min(5000, max(500, limit * 50))
        lexical_by_expression: list[list[dict[str, Any]]] = []
        retrieval_warnings: list[dict[str, str]] = []
        retrieval_indexes: list[dict[str, Any]] = []
        retrieval_completeness = "complete"
        for expression in execution_set:
            rows = self._lexical_candidate_rows(scope, expression.terms, candidate_limit)
            candidates = self._rdf_candidates(rows, scope, expression.text, expression.terms)
            candidates.extend(self._rule_candidates(scope, expression.text, expression.terms))
            if "operation" in selected_resource_types:
                candidates.extend(self._operation_candidates(scope, expression.text, expression.terms))
            candidates.extend(
                governed_mapping_lexical_candidates(
                    self.session,
                    ontology_ids=(entry.ontology_id for entry in scope.ontologies),
                    query=expression.text,
                    resource_kinds=selected_resource_types,
                )
            )
            for item in candidates:
                item.setdefault("_expression_indexes", set()).update(expression.original_indexes)
            lexical_by_expression.append(candidates)

        retrieval = SemanticResourceRetrievalService(self.session, self.settings).recall_multi(
            scope=scope,
            queries=[item.text for item in execution_set],
            resource_kinds=selected_resource_types - {"fact"},
            search_mode=search_mode,
            limit=limit,
        )
        retrieval_warnings = list(retrieval.get("warnings") or [])
        retrieval_indexes = list(retrieval.get("indexes") or [])
        retrieval_completeness = retrieval.get("completeness", "complete")
        for expression_index, candidates in enumerate(retrieval.get("candidates_by_query") or []):
            promoted = promote_exact_label_candidates(
                candidates, execution_set[expression_index].text
            )
            for item in promoted:
                item.setdefault("_expression_indexes", set()).update(
                    execution_set[expression_index].original_indexes
                )
            lexical_by_expression[expression_index] = fuse_context_candidates(
                lexical_by_expression[expression_index], promoted
            )

        warnings.extend(retrieval_warnings)
        fused, matched_queries_by_item, support_count_by_item = self._fuse_multi_expression(
            lexical_by_expression, execution_set
        )
        fused = [
            item
            for item in fused
            if item["kind"] in selected_resource_types
            and _assertion_filter_value(item["assertion_kind"]) in selected_assertion_types
        ]
        fusion_by_item = self._fusion_summary(
            fused, matched_queries_by_item, support_count_by_item
        )
        fused.sort(key=lambda item: _multi_sort_key(item, scope, fusion_by_item))
        fused = _dedupe_multi(fused)

        # Apply match cursor (resume after the bound sort key) and the match budget.
        match_payload = self._decode_cursor_opt(
            cursor_codec,
            match_cursor,
            binding=binding,
            expected_kind=CURSOR_KIND_MATCH,
        )
        if match_payload is not None:
            fused = _resume_after_key(fused, match_payload.resume_key)

        matches_truncated = len(fused) > limit
        primary = fused[:limit]
        next_match_cursor: str | None = None
        if matches_truncated:
            next_match_cursor = self._encode_cursor(
                cursor_codec,
                CursorPayload(
                    kind=CURSOR_KIND_MATCH,
                    binding_digest=binding_digest(binding),
                    workspace_versions=workspace_versions,
                    source_signatures=source_signatures,
                    resume_key=_match_resume_key(fused[limit]),
                    root_match_ids=(),
                ),
            )

        primary_ids = [self._identity_key(item) for item in primary]
        decorated_primary, related_raw, root_paths_by_item = self._expand_multi_primary(
            primary=primary,
            scope=scope,
            depth=depth,
            context_limit=context_limit,
            selected_resource_types=selected_resource_types,
            selected_assertion_types=selected_assertion_types,
        )

        # Apply context cursor within the bound root-match page only.
        context_payload = self._decode_cursor_opt(
            cursor_codec,
            context_cursor,
            binding=binding,
            expected_kind=CURSOR_KIND_CONTEXT,
        )
        if context_payload is not None:
            related_raw = _resume_context_after_key(related_raw, context_payload.resume_key)
        context_truncated = len(related_raw) > context_limit
        related_page = related_raw[:context_limit]
        next_context_cursor: str | None = None
        if context_truncated:
            next_context_cursor = self._encode_cursor(
                cursor_codec,
                CursorPayload(
                    kind=CURSOR_KIND_CONTEXT,
                    binding_digest=binding_digest(binding),
                    workspace_versions=workspace_versions,
                    source_signatures=source_signatures,
                    resume_key=_context_resume_key(related_raw[context_limit]),
                    root_match_ids=tuple(primary_ids),
                ),
            )

        decorated_related = self._decorate_related(related_page, scope, root_paths_by_item)
        if context_truncated:
            warnings.append(
                {"code": "context_truncated", "message": "Semantic context was truncated."}
            )
        if matches_truncated:
            warnings.append(
                {"code": "matches_truncated", "message": "Primary matches were truncated."}
            )
        if _has_ambiguous_match(decorated_primary):
            warnings.append(
                {
                    "code": "ambiguous_match",
                    "message": "Multiple primary matches share the same normalized label.",
                }
            )
        recall = recall_summary(decorated_primary, {"completeness": retrieval_completeness, "indexes": retrieval_indexes}, search_mode)
        if recall["match_status"] == "ambiguous" and not _has_ambiguous_match(decorated_primary):
            warnings.append(
                {
                    "code": "ambiguous_match",
                    "message": "Multiple primary matches have similar retrieval scores.",
                }
            )
        warnings.extend(
            warning
            for item in [*decorated_primary, *decorated_related]
            for warning in item.get("warnings", [])
        )
        return self._multi_response(
            scope=scope,
            original_queries=original_queries,
            normalized_queries=normalized_queries,
            primary=decorated_primary,
            related=decorated_related,
            matched_queries_by_item=matched_queries_by_item,
            fusion_by_item=fusion_by_item,
            root_paths_by_item=root_paths_by_item,
            recall=recall,
            warnings=warnings,
            matches_truncated=matches_truncated,
            context_truncated=context_truncated,
            match_cursor_out=next_match_cursor,
            context_cursor_out=next_context_cursor,
        )

    def _lexical_candidate_rows(
        self, scope: SemanticQueryScope, terms: list[str], candidate_limit: int
    ) -> list[dict[str, Any]]:
        candidate_fetch_limit = candidate_limit + 1
        raw_result = self.rdf_store.query_sparql(
            semantic_context_candidates_query(
                scope.graph_to_ontology,
                terms,
                candidate_fetch_limit,
                self.operation_type,
                self.operation_predicates,
            ),
            timeout_seconds=10,
            limit=candidate_fetch_limit,
        )
        rows = _bindings(raw_result.result)
        return rows[:candidate_limit]

    def _fuse_multi_expression(
        self,
        lexical_by_expression: list[list[dict[str, Any]]],
        execution_set: list["_ExecutionExpression"],
    ) -> tuple[
        list[dict[str, Any]],
        dict[tuple[str, str], list[dict[str, Any]]],
        dict[tuple[str, str], int],
    ]:
        by_key: dict[tuple[str, str], dict[str, Any]] = {}
        expression_indexes_by_key: dict[tuple[str, str], set[int]] = defaultdict(set)
        per_expression_evidence: dict[tuple[str, str], dict[int, dict[str, Any]]] = defaultdict(dict)

        for expression_index, candidates in enumerate(lexical_by_expression):
            for item in candidates:
                key = (item["ontology_id"], item["id"])
                existing = by_key.get(key)
                tagged = dict(item)
                tagged.pop("_expression_indexes", None)
                if existing is None:
                    by_key[key] = tagged
                    existing = tagged
                else:
                    merged = self._merge_into(existing, tagged)
                    existing = merged
                expression_indexes_by_key[key].update(
                    execution_set[expression_index].original_indexes
                )
                per_expression_evidence[key][expression_index] = {
                    "indexes": sorted(execution_set[expression_index].original_indexes),
                    "evidence_tier": _evidence_tier_for(existing),
                    "evidence": _evidence_payload(existing),
                }

        support_count_by_item: dict[tuple[str, str], int] = {}
        matched_queries_by_item: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for key, evidence_by_expression in per_expression_evidence.items():
            support_count_by_item[key] = len(evidence_by_expression)
            tier_groups: dict[str, list[int]] = defaultdict(list)
            for expression_index, evidence in evidence_by_expression.items():
                tier_groups[evidence["evidence_tier"]].extend(evidence["indexes"])
            ordered: list[dict[str, Any]] = []
            for tier in _TIER_ORDER:
                if tier not in tier_groups:
                    continue
                indexes = sorted(set(tier_groups[tier]))
                source_evidence = next(
                    evidence
                    for evidence in evidence_by_expression.values()
                    if evidence["evidence_tier"] == tier
                )
                ordered.append(
                    {
                        "indexes": indexes,
                        "evidence_tier": tier,
                        "evidence": source_evidence["evidence"],
                    }
                )
            matched_queries_by_item[key] = ordered

        for key, item in by_key.items():
            item.setdefault("_expression_indexes", set()).update(expression_indexes_by_key[key])

        return list(by_key.values()), matched_queries_by_item, support_count_by_item

    def _merge_into(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        match = existing.get("match") or {}
        incoming_match = incoming.get("match") or {}
        if not match:
            existing["match"] = incoming_match
            return existing
        if not incoming_match:
            return existing
        existing["match"]["lexical_score"] = max(
            int(match.get("lexical_score", match.get("score", 0)) or 0),
            int(incoming_match.get("lexical_score", incoming_match.get("score", 0)) or 0),
        )
        existing["match"]["reasons"] = sorted(
            set(match.get("reasons") or []) | set(incoming_match.get("reasons") or [])
        )
        existing["match"]["matched_fields"] = sorted(
            set(match.get("matched_fields") or []) | set(incoming_match.get("matched_fields") or [])
        )
        existing["match"]["matched_terms"] = sorted(
            set(match.get("matched_terms") or []) | set(incoming_match.get("matched_terms") or [])
        )
        semantic_similarity = match.get("semantic_similarity")
        if incoming_match.get("semantic_similarity") is not None:
            semantic_similarity = max(
                float(semantic_similarity or 0.0),
                float(incoming_match["semantic_similarity"]),
            )
        _normalise_match_local(existing, semantic_similarity)
        mapping_existing = existing.get("mapping_evidence") or (existing.get("data") or {}).get("mapping_evidence") or []
        mapping_incoming = incoming.get("mapping_evidence") or (incoming.get("data") or {}).get("mapping_evidence") or []
        if mapping_existing or mapping_incoming:
            merged = _dedupe_mapping_evidence([*mapping_existing, *mapping_incoming])
            existing["mapping_evidence"] = merged
            existing.setdefault("data", {})["mapping_evidence"] = merged
        return existing

    def _fusion_summary(
        self,
        items: list[dict[str, Any]],
        matched_queries_by_item: dict[tuple[str, str], list[dict[str, Any]]],
        support_count_by_item: dict[tuple[str, str], int],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        summary: dict[tuple[str, str], dict[str, Any]] = {}
        for item in items:
            key = self._identity_key(item)
            tiers = matched_queries_by_item.get(key, [])
            best_tier = _TIER_ORDER[-1]
            for tier in _TIER_ORDER:
                if any(entry["evidence_tier"] == tier for entry in tiers):
                    best_tier = tier
                    break
            summary[key] = {
                "best_evidence_tier": best_tier,
                "support_count": int(support_count_by_item.get(key, len(tiers))),
            }
        return summary

    def _expand_multi_primary(
        self,
        *,
        primary: list[dict[str, Any]],
        scope: SemanticQueryScope,
        depth: int,
        context_limit: int,
        selected_resource_types: set[str],
        selected_assertion_types: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[tuple[str, str], list[dict[str, Any]]]]:
        decorated_primary = [self._decorate(item, scope) for item in primary]
        related_raw: list[dict[str, Any]] = []
        root_paths_by_item: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        if context_limit <= 0 or depth <= 0 or not primary:
            return decorated_primary, related_raw, root_paths_by_item

        for rank, item in enumerate(primary):
            for related_item in self._related_for_root(
                item,
                scope=scope,
                depth=depth,
                context_limit=context_limit,
                selected_resource_types=selected_resource_types,
                selected_assertion_types=selected_assertion_types,
            ):
                key = self._identity_key(related_item)
                root_id = item["id"]
                root_paths_by_item[key].append(
                    {
                        "root_match_id": root_id,
                        "graph_distance": int(related_item.get("distance") or 1),
                        "_root_rank": rank,
                    }
                )
                related_item.setdefault("_seen_keys", set()).add(key)
                related_raw.append(related_item)

        # Dedupe by (ontology, kind, id), aggregating all root paths per identity.
        deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for item in related_raw:
            key = self._identity_key(item)
            existing = deduped.get(key)
            if existing is None:
                item = dict(item)
                item.pop("_seen_keys", None)
                deduped[key] = item
        for item in deduped.values():
            key = self._identity_key(item)
            paths = sorted(
                root_paths_by_item.get(key, []),
                key=lambda path: (path["_root_rank"], path["graph_distance"], path["root_match_id"]),
            )
            cleaned = [
                {"root_match_id": path["root_match_id"], "graph_distance": path["graph_distance"]}
                for path in paths
            ]
            root_paths_by_item[key] = cleaned

        ordered = list(deduped.values())
        ordered.sort(key=lambda item: _context_sort_key(item, scope, root_paths_by_item))
        return decorated_primary, ordered, root_paths_by_item

    def _related_for_root(
        self,
        root: dict[str, Any],
        *,
        scope: SemanticQueryScope,
        depth: int,
        context_limit: int,
        selected_resource_types: set[str],
        selected_assertion_types: set[str],
    ) -> list[dict[str, Any]]:
        related: list[dict[str, Any]] = []
        if context_limit <= 0:
            return related
        budget = context_limit
        if (
            "fact" in selected_resource_types
            and "asserted" in selected_assertion_types
        ):
            shape_items = self._shape_constraint_items([root], scope, limit=budget + 1)
            related.extend(shape_items[:budget])
            budget -= len(related)
        if budget <= 0:
            return related
        operation_context = self._operation_target_context(
            [root],
            scope,
            limit=budget + 1,
            enabled="concept" in selected_resource_types,
        )
        related.extend(operation_context[:budget])
        budget -= len(operation_context)
        if budget <= 0:
            return related
        neighborhood = self._expand_neighborhood(
            [root],
            scope,
            depth=depth,
            limit=budget + 1,
            resource_types=selected_resource_types,
            assertion_types=selected_assertion_types,
        )
        related.extend(neighborhood[:budget])
        return related

    def _decorate_related(
        self,
        items: list[dict[str, Any]],
        scope: SemanticQueryScope,
        root_paths_by_item: dict[tuple[str, str], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        decorated: list[dict[str, Any]] = []
        for item in items:
            decorated_item = self._decorate(item, scope)
            key = self._identity_key(item)
            decorated_item["root_paths"] = list(root_paths_by_item.get(key, []))
            decorated.append(decorated_item)
        return decorated

    def _identity_key(self, item: dict[str, Any]) -> tuple[str, str]:
        return (item["ontology_id"], item["id"])

    def _decode_cursor_opt(
        self,
        codec: ContextCursorCodec,
        token: str | None,
        *,
        binding: CursorBinding,
        expected_kind: str,
    ) -> CursorPayload | None:
        if token is None:
            return None
        try:
            return codec.decode(token, binding=binding, expected_kind=expected_kind)
        except ContextCursorInvalid as exc:
            raise SemanticContextCursorInvalid(str(exc)) from exc
        except ContextCursorMismatch as exc:
            raise SemanticContextCursorMismatch(str(exc)) from exc
        except ContextSnapshotChanged as exc:
            raise SemanticContextSnapshotChanged(str(exc)) from exc

    def _encode_cursor(self, codec: ContextCursorCodec, payload: CursorPayload) -> str:
        return codec.encode(payload)

    def _empty_recall(self, search_mode: str) -> dict[str, Any]:
        return {
            "mode": search_mode,
            "match_status": "no_match",
            "completeness": "complete",
            "indexes": [],
        }

    def _multi_response(
        self,
        *,
        scope: SemanticQueryScope,
        original_queries: list[str],
        normalized_queries: list[str],
        primary: list[dict[str, Any]],
        related: list[dict[str, Any]],
        matched_queries_by_item: dict[tuple[str, str], list[dict[str, Any]]],
        fusion_by_item: dict[tuple[str, str], dict[str, Any]],
        root_paths_by_item: dict[tuple[str, str], list[dict[str, Any]]],
        recall: dict[str, Any],
        warnings: list[dict[str, str]],
        matches_truncated: bool,
        context_truncated: bool,
        match_cursor_out: str | None,
        context_cursor_out: str | None,
    ) -> dict[str, Any]:
        decorated_primary: list[dict[str, Any]] = []
        for item in primary:
            key = self._identity_key(item)
            item_copy = dict(item)
            item_copy["matched_queries"] = list(matched_queries_by_item.get(key, []))
            item_copy["fusion"] = dict(fusion_by_item.get(key, {"best_evidence_tier": "semantic", "support_count": 0}))
            decorated_primary.append(item_copy)
        decorated_related: list[dict[str, Any]] = []
        for item in related:
            key = self._identity_key(item)
            item_copy = dict(item)
            item_copy["root_paths"] = list(root_paths_by_item.get(key, []))
            decorated_related.append(item_copy)
        truncated = bool(matches_truncated or context_truncated)
        # Legacy callers may still inspect ``query.text``/``normalized_terms``
        # when the request used the single-expression compatibility alias.
        query_echo: dict[str, Any] = {
            "queries": list(original_queries),
            "normalized_queries": list(normalized_queries),
        }
        if len(original_queries) == 1:
            text, terms = normalize_query_text(original_queries[0])
            query_echo["text"] = text
            query_echo["normalized_terms"] = terms
        return {
            "query": query_echo,
            "result_status": "matched" if decorated_primary else "no_match",
            "scope": scope.public_dict(),
            "primary_matches": decorated_primary,
            "related_context": decorated_related,
            "matches_page": {
                "returned": len(decorated_primary),
                "truncated": bool(matches_truncated),
                "next_match_cursor": match_cursor_out,
            },
            "context_page": {
                "returned": len(decorated_related),
                "truncated": bool(context_truncated),
                "next_context_cursor": context_cursor_out,
            },
            "truncated": truncated,
            "recall": recall,
            "warnings": _dedupe_warnings(warnings),
        }

    def _rdf_candidates(
        self,
        rows: list[dict[str, Any]],
        scope: SemanticQueryScope,
        text: str,
        terms: list[str],
    ) -> list[dict[str, Any]]:
        resources: dict[tuple[str, str], dict[str, Any]] = {}
        statements: list[dict[str, Any]] = []
        for row in rows:
            graph = _value(row, "graph")
            subject = _value(row, "subject")
            predicate = _value(row, "predicate")
            if not graph or not subject or graph not in scope.graph_to_ontology:
                continue
            ontology_id = scope.graph_to_ontology[graph]
            assertion_kind = scope.graph_assertion_kinds.get(graph, "asserted")
            subject_types = set(_split_aggregate(_value(row, "subjectTypes")))
            is_operation = self.operation_type in subject_types
            if _binding_type(row, "subject") == "uri":
                key = (ontology_id, subject)
                resource = resources.setdefault(
                    key,
                    {
                        "id": subject,
                        "kind": "instance",
                        # A property/resource can be classified as a
                        # relation by RDF type, but it is still a resource
                        # lineage target.  Keep this target kind explicit so
                        # decoration never infers statement lineage from the
                        # presentation ``kind`` alone.
                        "target_kind": "resource",
                        "ontology_id": ontology_id,
                        "iri": subject,
                        "label": None,
                        "labels": [],
                        "aliases": [],
                        "description": None,
                        "types": set(),
                        "distance": 0,
                        "assertion_kind": assertion_kind,
                        "data": {},
                    },
                )
                subject_label = _value(row, "subjectLabel")
                if subject_label and subject_label not in resource["labels"]:
                    resource["labels"].append(subject_label)
                for alias in _split_aggregate(_value(row, "aliases")):
                    if alias not in resource["aliases"]:
                        resource["aliases"].append(alias)
                resource["description"] = resource["description"] or _value(row, "description")
                resource["types"].update(subject_types)

                matched_field = _value(row, "matchedField")
                matched_value = _value(row, "matchedValue")
                if matched_field == "label" and matched_value:
                    if matched_value not in resource["labels"]:
                        resource["labels"].append(matched_value)
                elif matched_field == "alias" and matched_value:
                    if matched_value not in resource["aliases"]:
                        resource["aliases"].append(matched_value)
                elif matched_field == "description" and matched_value:
                    resource["description"] = resource["description"] or matched_value

            if (
                not predicate
                or predicate in _METADATA_PREDICATES
                or predicate in self.operation_predicates
                or is_operation
            ):
                continue
            statement = self._statement_item(row, scope, distance=0)
            if statement is None:
                continue
            predicate_label = (
                _value(row, "matchedValue") if _value(row, "matchedField") == "predicate" else None
            ) or _local_name(predicate)
            object_value = _value(row, "object")
            score = _best_match(
                text,
                terms,
                [
                    ("predicate", predicate_label, 550, "property_name"),
                    ("identifier", _local_name(predicate), 600, "identifier"),
                    ("value", object_value, 400, "fact_value"),
                ],
            )
            if score:
                statement["match"] = score
                statements.append(statement)

        candidates: list[dict[str, Any]] = []
        for resource in resources.values():
            types = resource.pop("types")
            labels = resource.pop("labels")
            if self.operation_type in types:
                continue
            if types & _CLASS_TYPES:
                resource["kind"] = "concept"
            elif types & _RELATION_TYPES:
                resource["kind"] = "relation"
            exact_label = next(
                (value for value in labels if _normalize_value(value) == _normalize_value(text)),
                None,
            )
            resource["data"] = {
                "rdf_types": sorted(types),
                "label_evidence": sorted(set(labels)),
            }
            resource["label"] = exact_label or (labels[0] if labels else _local_name(resource["iri"]))
            match = _best_match(
                text,
                terms,
                [
                    *(("label", value, 1000, "exact_label") for value in labels),
                    *(("alias", alias, 900, "exact_alias") for alias in resource["aliases"]),
                    ("identifier", resource["iri"], 600, "identifier"),
                    ("description", resource["description"], 450, "description"),
                ],
            )
            if match:
                resource["match"] = match
                candidates.append(resource)
        candidates.extend(statements)
        return candidates

    def _operation_candidates(
        self, scope: SemanticQueryScope, text: str, terms: list[str]
    ) -> list[dict[str, Any]]:
        graph_values = " ".join(URIRef(graph).n3() for graph in scope.graph_iris)
        v = self.operation_vocab
        query = f"""# template: semantic-context-operations
PREFIX rdf: <{RDF}>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?graph ?operation ?operationId ?name ?description ?target ?targetLabel
       ?parameters ?preconditions ?effects ?failures ?idempotency ?risk ?bindings
       ?credentials ?status ?schemaVersion
       (GROUP_CONCAT(DISTINCT STR(?alias); separator="|") AS ?aliases)
WHERE {{
  VALUES ?graph {{ {graph_values} }}
  GRAPH ?graph {{
    ?operation a <{v["type"]}> ;
      <{v["id"]}> ?operationId ;
      rdfs:label ?name ;
      <{v["target_resource_type_iri"]}> ?target ;
      <{v["parameters"]}> ?parameters ;
      <{v["preconditions"]}> ?preconditions ;
      <{v["effects"]}> ?effects ;
      <{v["possible_failures"]}> ?failures ;
      <{v["idempotency"]}> ?idempotency ;
      <{v["risk_level"]}> ?risk ;
      <{v["tool_bindings"]}> ?bindings ;
      <{v["credential_requirements"]}> ?credentials ;
      <{v["status"]}> ?status ;
      <{v["schema_version"]}> ?schemaVersion .
    OPTIONAL {{ ?operation rdfs:comment ?description . }}
    OPTIONAL {{ ?operation skos:altLabel ?alias . }}
    OPTIONAL {{ ?target rdfs:label ?targetLabel . }}
    FILTER(?status = "active" && ?schemaVersion = "{OPERATION_SCHEMA_VERSION}")
  }}
}}
GROUP BY ?graph ?operation ?operationId ?name ?description ?target ?targetLabel
         ?parameters ?preconditions ?effects ?failures ?idempotency ?risk ?bindings
         ?credentials ?status ?schemaVersion
ORDER BY ?graph ?operation
LIMIT 5000
"""
        try:
            result = self.rdf_store.query_sparql(query, timeout_seconds=10, limit=5000)
        except Exception:
            return []
        candidates = []
        for row in _bindings(result.result):
            graph = _value(row, "graph")
            iri = _value(row, "operation")
            if not graph or graph not in scope.graph_to_ontology or not iri:
                continue
            try:
                operation = {
                    "operation_id": _value(row, "operationId"),
                    "operation_iri": iri,
                    "name": _value(row, "name"),
                    "aliases": _split_aggregate(_value(row, "aliases")),
                    "description": _value(row, "description"),
                    "target_resource_type_iri": _value(row, "target"),
                    "parameters": json.loads(_value(row, "parameters") or "null"),
                    "preconditions": json.loads(_value(row, "preconditions") or "null"),
                    "effects": json.loads(_value(row, "effects") or "null"),
                    "possible_failures": json.loads(_value(row, "failures") or "null"),
                    "idempotency": json.loads(_value(row, "idempotency") or "null"),
                    "risk_level": _value(row, "risk"),
                    "tool_bindings": json.loads(_value(row, "bindings") or "null"),
                    "credential_requirements": json.loads(_value(row, "credentials") or "null"),
                    "status": _value(row, "status"),
                    "schema_version": _value(row, "schemaVersion"),
                }
                operation = validate_operation_payload(operation, settings=self.settings)
            except (OperationValidationError, TypeError, json.JSONDecodeError):
                continue
            match_fields: list[tuple[str, Any, int, str]] = [
                ("label", operation["name"], 1000, "exact_label"),
                *(("alias", alias, 900, "exact_alias") for alias in operation["aliases"]),
                ("identifier", iri, 600, "identifier"),
                ("description", operation.get("description"), 450, "description"),
                ("target", _value(row, "targetLabel"), 425, "target_resource_type"),
                ("target", operation["target_resource_type_iri"], 425, "target_resource_type"),
            ]
            match_fields.extend(_operation_lexical_fields(operation))
            match = _best_match(text, terms, match_fields)
            if match:
                candidates.append(
                    {
                        "id": iri,
                        "kind": "operation",
                        "ontology_id": scope.graph_to_ontology[graph],
                        "iri": iri,
                        "label": operation["name"],
                        "aliases": operation["aliases"],
                        "description": operation.get("description"),
                        "data": operation,
                        "distance": 0,
                        "assertion_kind": "asserted",
                        "match": match,
                        "_target_label": _value(row, "targetLabel"),
                    }
                )
        return candidates

    def _operation_target_context(
        self,
        primary: list[dict[str, Any]],
        scope: SemanticQueryScope,
        *,
        limit: int,
        enabled: bool,
    ) -> list[dict[str, Any]]:
        if not enabled or limit <= 0:
            return []
        result = []
        seen = set()
        for item in primary:
            if item["kind"] != "operation":
                continue
            target = item["data"]["target_resource_type_iri"]
            key = (item["ontology_id"], target)
            if key in seen:
                continue
            seen.add(key)
            result.append(
                {
                    "id": target,
                    "kind": "concept",
                    "ontology_id": item["ontology_id"],
                    "iri": target,
                    "label": item.pop("_target_label", None) or _local_name(target),
                    "aliases": [],
                    "description": None,
                    "data": {"rdf_types": sorted(_CLASS_TYPES)},
                    "distance": 1,
                    "assertion_kind": "asserted",
                    "match": {
                        "score": 250,
                        "matched_terms": [],
                        "matched_fields": ["target_resource_type"],
                        "reasons": ["operation_target_context"],
                    },
                }
            )
            if len(result) >= limit:
                break
        return result

    def _shape_constraint_items(
        self,
        primary: list[dict[str, Any]],
        scope: SemanticQueryScope,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        scope_by_ontology = {item.ontology_id: item for item in scope.ontologies}
        for match in primary:
            if match["kind"] not in {"concept", "instance"}:
                continue
            target_classes = (
                [match["iri"]]
                if match["kind"] == "concept"
                else list(match.get("data", {}).get("rdf_types", []))
            )
            ontology_scope = scope_by_ontology[match["ontology_id"]]
            for target_class in target_classes:
                try:
                    guidance = self.shape_endpoint.read_merged_guidance(
                        ontology_scope.graph_set_id, target_class
                    )
                except Exception:
                    continue
                for field in guidance.get("fields", []):
                    if not isinstance(field, dict):
                        continue
                    path = str(field.get("path") or field.get("name") or "constraint")
                    canonical_path: str | None = None
                    if field.get("provenance") == "generated":
                        try:
                            canonical_path = canonical_iri(path)
                        except (InvalidLineageStatement, ValueError):
                            # Shape guidance may contain a blank-node,
                            # relative, or otherwise non-RDF path.  Keep the
                            # visible constraint, but never turn its
                            # synthetic identity into a statement target.
                            canonical_path = None
                    item_id = hashlib.sha256(
                        f"{match['ontology_id']}:{target_class}:{path}".encode("utf-8")
                    ).hexdigest()
                    if item_id in seen:
                        continue
                    seen.add(item_id)
                    public_constraint = {
                        key: value
                        for key, value in field.items()
                        if key
                        in {
                            "path",
                            "name",
                            "label",
                            "datatype",
                            "class_iri",
                            "min_count",
                            "max_count",
                            "pattern",
                            "enumeration",
                            "description",
                            "required",
                            "provenance",
                        }
                    }
                    item = {
                        "id": item_id,
                        "kind": "fact",
                        "ontology_id": match["ontology_id"],
                        "iri": canonical_path
                        or (
                            path
                            if path.startswith(("http://", "https://", "urn:"))
                            else None
                        ),
                        "label": str(
                            field.get("label") or field.get("name") or _local_name(path)
                        ),
                        "aliases": [],
                        "description": field.get("description"),
                        "data": {
                            "target_class": target_class,
                            "constraint": public_constraint,
                        },
                        "distance": 1,
                        "assertion_kind": "asserted",
                        "match": {
                            "score": 275,
                            "matched_terms": [],
                            "matched_fields": ["constraint"],
                            "reasons": ["shape_constraint"],
                        },
                    }
                    if canonical_path is not None:
                        item["target_kind"] = "resource"
                        item["_lineage_target"] = {
                            "target_type": "resource",
                            "target_id": canonical_path,
                        }
                    items.append(item)
                    if len(items) >= limit:
                        return items
        return items

    def _rule_candidates(
        self, scope: SemanticQueryScope, text: str, terms: list[str]
    ) -> list[dict[str, Any]]:
        ontology_ids = [item.ontology_id for item in scope.ontologies]
        if not ontology_ids:
            return []
        rows = self.session.execute(
            select(SemanticRuleModel, SemanticRuleDefinitionModel)
            .join(
                SemanticRuleDefinitionModel,
                SemanticRuleDefinitionModel.id == SemanticRuleModel.current_definition_id,
            )
            .where(
                SemanticRuleModel.ontology_id.in_(ontology_ids),
                SemanticRuleModel.status == "active",
                SemanticRuleDefinitionModel.status == "active",
            )
            .order_by(SemanticRuleModel.ontology_id, SemanticRuleModel.rule_iri)
        )
        candidates: list[dict[str, Any]] = []
        for rule, definition in rows:
            description = (definition.rule_metadata or {}).get("description")
            match = _best_match(
                text,
                terms,
                [
                    ("label", definition.name, 1000, "exact_label"),
                    ("identifier", rule.rule_iri, 600, "identifier"),
                    ("description", description, 450, "description"),
                ],
            )
            if not match:
                continue
            candidates.append(
                {
                    "id": rule.rule_iri,
                    "kind": "rule",
                    "ontology_id": rule.ontology_id,
                    "iri": rule.rule_iri,
                    "label": definition.name,
                    "aliases": [],
                    "description": description,
                    "data": {
                        "definition_id": definition.id,
                        "version": definition.version,
                        "language": definition.language,
                        "input_roles": definition.input_roles,
                        "output_kind": definition.output_kind,
                    },
                    "distance": 0,
                    "assertion_kind": "asserted",
                    "match": match,
                }
            )
        return candidates

    def _expand_neighborhood(
        self,
        primary: list[dict[str, Any]],
        scope: SemanticQueryScope,
        *,
        depth: int,
        limit: int,
        resource_types: set[str],
        assertion_types: set[str],
    ) -> list[dict[str, Any]]:
        frontier = sorted(
            {
                item["iri"]
                for item in primary
                if item.get("iri") and str(item["iri"]).startswith(("http://", "https://", "urn:"))
            }
        )
        seen_anchors = set(frontier)
        seen_items = {item["id"] for item in primary}
        related: list[dict[str, Any]] = []
        for distance in range(1, depth + 1):
            if not frontier or len(related) >= limit:
                break
            query_limit = min(5000, max(100, (limit - len(related)) * 20))
            result = self.rdf_store.query_sparql(
                semantic_context_neighborhood_query(
                    scope.graph_iris,
                    frontier,
                    query_limit,
                    self.operation_type,
                    self.operation_predicates,
                ),
                timeout_seconds=10,
                limit=query_limit,
            )
            next_frontier: set[str] = set()
            for row in _bindings(result.result):
                item = self._statement_item(row, scope, distance=distance)
                if item is None or item["id"] in seen_items:
                    continue
                if item["kind"] not in resource_types:
                    continue
                if _assertion_filter_value(item["assertion_kind"]) not in assertion_types:
                    continue
                item["match"] = {
                    "score": max(1, 300 - distance * 50),
                    "matched_terms": [],
                    "matched_fields": ["neighborhood"],
                    "reasons": ["relation_neighborhood"],
                }
                related.append(item)
                seen_items.add(item["id"])
                for key in ("subject", "object"):
                    value = item["data"].get(key)
                    if isinstance(value, str) and value.startswith(("http://", "https://", "urn:")):
                        if value not in seen_anchors:
                            next_frontier.add(value)
                if len(related) >= limit:
                    break
            seen_anchors.update(next_frontier)
            frontier = sorted(next_frontier)
        return related

    def _statement_item(
        self, row: dict[str, Any], scope: SemanticQueryScope, *, distance: int
    ) -> dict[str, Any] | None:
        graph = _value(row, "graph")
        subject = _value(row, "subject")
        predicate = _value(row, "predicate")
        object_value = _value(row, "object")
        if not graph or not subject or not predicate or object_value is None:
            return None
        if graph not in scope.graph_to_ontology or predicate in _METADATA_PREDICATES:
            return None
        if predicate in self.operation_predicates:
            return None
        if _value(row, "subjectType") == self.operation_type:
            return None
        object_ntriples = _binding_n3(row.get("object"))
        try:
            statement_id = statement_id_for_quad(subject, predicate, object_ntriples, graph)
        except ValueError:
            return None
        is_relation = _binding_type(row, "object") in {"uri", "bnode"}
        subject_label = _value(row, "subjectLabel") or _local_name(subject)
        predicate_label = _value(row, "predicateLabel") or _local_name(predicate)
        return {
            "id": statement_id,
            "kind": "relation" if is_relation else "fact",
            "target_kind": "statement",
            "ontology_id": scope.graph_to_ontology[graph],
            "iri": predicate,
            "label": f"{subject_label} {predicate_label}".strip(),
            "aliases": [],
            "description": None,
            "data": {
                "subject": subject,
                "predicate": predicate,
                "object": object_value,
                "object_type": _binding_type(row, "object"),
                "object_datatype": _binding_attribute(row, "object", "datatype"),
                "object_language": _binding_attribute(row, "object", "xml:lang"),
            },
            "distance": distance,
            "assertion_kind": scope.graph_assertion_kinds.get(graph, "asserted"),
        }

    def _decorate(self, item: dict[str, Any], scope: SemanticQueryScope) -> dict[str, Any]:
        item = dict(item)
        item.pop("_target_label", None)
        is_shape_constraint = item.get("match", {}).get("reasons") == ["shape_constraint"]
        constraint = (item.get("data") or {}).get("constraint")
        is_generated_shape_constraint = (
            is_shape_constraint
            and isinstance(constraint, dict)
            and constraint.get("provenance") == "generated"
        )
        # ``_lineage_target`` is an internal hand-off from generated shape
        # guidance.  Only the resource/property projection emitted by this
        # service is trusted; all other markers fail closed and must never
        # become a public (or OntologyLineageService) target.
        raw_lineage_target = item.pop("_lineage_target", None)
        lineage_target: dict[str, str] | None = None
        expected_lineage_id: str | None = None
        if is_generated_shape_constraint:
            raw_constraint_path = constraint.get("path") or item.get("iri")
            if isinstance(raw_constraint_path, str):
                try:
                    expected_lineage_id = canonical_iri(raw_constraint_path)
                except (InvalidLineageStatement, ValueError):
                    expected_lineage_id = None
        if is_generated_shape_constraint and isinstance(raw_lineage_target, dict):
            candidate_type = raw_lineage_target.get("target_type")
            candidate_id = raw_lineage_target.get("target_id")
            if candidate_type == "resource" and isinstance(candidate_id, str):
                try:
                    canonical_target_id = canonical_iri(candidate_id)
                except (InvalidLineageStatement, ValueError):
                    canonical_target_id = None
                if (
                    canonical_target_id is not None
                    and expected_lineage_id is not None
                    and canonical_target_id == expected_lineage_id
                ):
                    lineage_target = {
                        "target_type": "resource",
                        "target_id": canonical_target_id,
                    }
        target_kind = item.get("target_kind")
        if is_shape_constraint:
            # Shape constraints are target-less projections unless the
            # generated property marker above validated successfully.
            target_kind = "resource" if lineage_target is not None else None
        elif target_kind not in {"resource", "statement"}:
            # Keep compatibility with semantic-retrieval candidates that
            # predate explicit target metadata.  A statement has the generic
            # subject/predicate/object shape; a relation-typed RDF resource
            # does not, even though its public ``kind`` is also ``relation``.
            data = item.get("data") or {}
            target_kind = (
                "statement"
                if item["kind"] == "fact"
                or (
                    item["kind"] == "relation"
                    and {"subject", "predicate", "object"}.issubset(data)
                )
                else "resource"
            )
        if target_kind is not None:
            item["target_kind"] = target_kind
        if lineage_target is not None:
            target_type = lineage_target["target_type"]
            target_id = lineage_target["target_id"]
        elif item["kind"] == "rule":
            target_type = "rule"
            target_id = item["id"]
        elif is_shape_constraint:
            # A shape constraint without a valid generated property IRI is a
            # read-model projection only.  Do not ask lineage to interpret its
            # synthetic hash as a persisted statement or resource.  The
            # synthetic marker remains internal and is omitted from the public
            # lineage envelope below.
            target_type = None
            target_id = None
        else:
            target_type = target_kind
            target_id = item["id"]
        if is_shape_constraint and lineage_target is None:
            evidence_ids = []
            lineage_status = "missing"
            evidence_status = "missing" if item["assertion_kind"] == "asserted" else "not_applicable"
            dependency_status = None
            proof_level = None
            lineage_warnings = []
        else:
            try:
                lineage = self.lineage_service.get_lineage(
                    ontology_id=item["ontology_id"],
                    target_type=target_type,
                    target_id=target_id,
                    include_history=False,
                    max_depth=1,
                    limit=50,
                )
                evidence_ids = sorted(set(_collect_evidence_ids(lineage.get("items", []))))
                lineage_status = lineage.get("lineage_status", "missing")
                evidence_status = lineage.get("evidence_status", "missing")
                dependency_status = lineage.get("dependency_evidence_status")
                proof_level = _find_first(lineage.get("items", []), "proof_level")
                lineage_warnings = lineage.get("warnings", [])
            except LineageTargetNotFound:
                evidence_ids = []
                lineage_status = "missing"
                evidence_status = (
                    "not_applicable" if item["assertion_kind"] != "asserted" else "missing"
                )
                dependency_status = "missing" if item["assertion_kind"] != "asserted" else None
                proof_level = None
                lineage_warnings = []

        derived_state = None
        if item["assertion_kind"] != "asserted":
            ontology = next(
                entry for entry in scope.ontologies if entry.ontology_id == item["ontology_id"]
            )
            derived_kind = "reasoning" if item["assertion_kind"] == "owl_inferred" else "rule"
            descriptor = ontology.derived_state.get(derived_kind, {})
            derived_state = {
                "kind": derived_kind,
                "status": descriptor.get("status"),
                "run_id": descriptor.get("run_id"),
                "proof_level": proof_level,
                "dependency_evidence_status": dependency_status,
            }
            evidence_ids = []
            evidence_status = "not_applicable"

        item_warnings: list[dict[str, str]] = []
        if evidence_status == "missing":
            item_warnings.append({"code": "evidence_missing", "message": "Evidence is missing."})
        if lineage_status in {"missing", "partial"}:
            item_warnings.append(
                {
                    "code": f"lineage_{lineage_status}",
                    "message": f"Lineage is {lineage_status}.",
                }
            )
        if derived_state and derived_state.get("status") == "stale":
            item_warnings.append(
                {"code": "derived_result_stale", "message": "Derived result is stale."}
            )
        item_warnings.extend(
            {"code": str(code), "message": str(code).replace("_", " ").capitalize() + "."}
            for code in lineage_warnings
            if code in {"lineage_truncated", "legacy_lineage_unavailable"}
        )
        lineage_public: dict[str, Any] = {"status": lineage_status}
        if target_type is not None and target_id is not None:
            lineage_public.update(target_type=target_type, target_id=target_id)
        return {
            **item,
            "assertion_type": _assertion_filter_value(item["assertion_kind"]),
            "evidence_reference_ids": evidence_ids,
            "evidence_status": evidence_status,
            "lineage": lineage_public,
            "derived_state": derived_state,
            "warnings": _dedupe_warnings(item_warnings),
        }

    @staticmethod
    def _legacy_response(
        text: str,
        terms: list[str],
        scope: SemanticQueryScope,
        primary: list[dict[str, Any]],
        related: list[dict[str, Any]],
        truncated: bool,
        warnings: list[dict[str, str]],
        recall: dict[str, Any],
    ) -> dict[str, Any]:
        """Compatibility envelope retained for tests that build responses directly."""
        return {
            "query": {"text": text, "normalized_terms": terms},
            "result_status": "matched" if primary else "no_match",
            "scope": scope.public_dict(),
            "primary_matches": primary,
            "related_context": related,
            "matches_page": {
                "returned": len(primary),
                "truncated": False,
                "next_match_cursor": None,
            },
            "context_page": {
                "returned": len(related),
                "truncated": False,
                "next_context_cursor": None,
            },
            "truncated": truncated,
            "recall": recall,
            "warnings": _dedupe_warnings(warnings),
        }


def normalize_query_text(query: str) -> tuple[str, list[str]]:
    if not isinstance(query, str):
        raise SemanticContextQueryError("query must be a string")
    text = query.strip()
    if not text:
        raise SemanticContextQueryError("query must be non-empty")
    if len(text) > 2000:
        raise SemanticContextQueryError("query may contain at most 2000 characters")
    normalized = unicodedata.normalize("NFKC", text).casefold()
    identifier_split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    identifier_split = unicodedata.normalize("NFKC", identifier_split).casefold()
    tokens = re.findall(r"[\w]+", identifier_split.replace("_", " ").replace("-", " "))
    terms: list[str] = [normalized]
    terms.extend(tokens)
    for token in tokens:
        if not re.search(r"[\u3400-\u9fff]", token):
            continue
        for size in range(min(6, len(token)), 1, -1):
            terms.extend(token[index : index + size] for index in range(len(token) - size + 1))
    unique = list(dict.fromkeys(term.strip() for term in terms if term.strip()))
    unique.sort(key=lambda term: (-len(term), normalized.find(term), term))
    return text, unique[:64]


def _validate_filters(
    resource_types: list[str] | None,
    assertion_types: list[str] | None,
    depth: int,
    limit: int,
) -> None:
    if resource_types is not None and (
        not resource_types or not set(resource_types) <= RESOURCE_TYPES
    ):
        raise SemanticContextQueryError("resource_types contains an unsupported value")
    if assertion_types is not None and (
        not assertion_types or not set(assertion_types) <= ASSERTION_TYPES
    ):
        raise SemanticContextQueryError("assertion_types contains an unsupported value")
    if not 0 <= depth <= 3:
        raise SemanticContextQueryError("depth must be between 0 and 3")
    if not 1 <= limit <= 100:
        raise SemanticContextQueryError("limit must be between 1 and 100")


def _best_match(
    text: str,
    terms: list[str],
    fields: Iterable[tuple[str, Any, int, str]],
) -> dict[str, Any] | None:
    normalized_query = _normalize_value(text)
    matches: list[tuple[int, str, str, str]] = []
    for field, raw_value, base_score, exact_reason in fields:
        value = _normalize_value(raw_value)
        if not value:
            continue
        matched_terms = [term for term in terms if term == value or term in value or value in term]
        if not matched_terms:
            continue
        exact = value == normalized_query or value in terms
        score = base_score if exact else max(1, base_score - 250)
        reason = exact_reason if exact else f"{field}_contains"
        for term in matched_terms:
            matches.append((score, term, field, reason))
    if not matches:
        return None
    score = max(item[0] for item in matches)
    return {
        "score": score,
        "matched_terms": sorted(
            {item[1] for item in matches}, key=lambda value: (-len(value), value)
        ),
        "matched_fields": sorted({item[2] for item in matches}),
        "reasons": sorted({item[3] for item in matches if item[0] == score}),
    }


def _normalize_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _operation_lexical_fields(
    operation: dict[str, Any],
) -> list[tuple[str, Any, int, str]]:
    fields: list[tuple[str, Any, int, str]] = []
    for parameter in operation["parameters"]:
        fields.extend(
            [
                ("parameter", parameter["name"], 425, "operation_parameter"),
                ("parameter", parameter.get("description"), 400, "operation_parameter"),
            ]
        )
    for field in ("preconditions", "effects"):
        for declaration in operation[field]:
            fields.extend(
                [
                    (field, declaration["name"], 425, f"operation_{field}"),
                    (field, declaration["description"], 400, f"operation_{field}"),
                ]
            )
    for failure in operation["possible_failures"]:
        fields.extend(
            [
                ("failure", failure["code"], 425, "operation_failure"),
                ("failure", failure["description"], 400, "operation_failure"),
            ]
        )
    for binding in operation["tool_bindings"]:
        for key in ("binding_id", "system", "operation_identifier", "version"):
            fields.append(("binding", binding.get(key), 425, "operation_binding"))
    for credential in operation["credential_requirements"]:
        fields.append(
            (
                "credential_type",
                credential["reference_type"],
                425,
                "operation_credential_type",
            )
        )
    return fields


def _bindings(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("results", {}).get("bindings", [])
    return rows if isinstance(rows, list) else []


def _value(row: dict[str, Any], key: str) -> str | None:
    binding = row.get(key)
    if not isinstance(binding, dict):
        return None
    value = binding.get("value")
    return str(value) if value is not None else None


def _binding_type(row: dict[str, Any], key: str) -> str | None:
    binding = row.get(key)
    return str(binding.get("type")) if isinstance(binding, dict) and binding.get("type") else None


def _binding_attribute(row: dict[str, Any], key: str, attribute: str) -> str | None:
    binding = row.get(key)
    if not isinstance(binding, dict) or binding.get(attribute) is None:
        return None
    return str(binding[attribute])


def _split_aggregate(value: str | None) -> list[str]:
    return [item for item in (value or "").split("|") if item]


def _binding_n3(binding: Any) -> str:
    if not isinstance(binding, dict):
        return Literal("").n3()
    value = str(binding.get("value", ""))
    if binding.get("type") == "uri":
        return URIRef(value).n3()
    if binding.get("type") == "bnode":
        return f"_:{value}"
    return Literal(
        value,
        lang=binding.get("xml:lang"),
        datatype=URIRef(binding["datatype"]) if binding.get("datatype") else None,
    ).n3()


def _local_name(iri: str) -> str:
    return re.split(r"[/#:]", iri.rstrip("/#:"))[-1] or iri


def _assertion_filter_value(assertion_kind: str) -> str:
    return "asserted" if assertion_kind == "asserted" else "derived"


def _sort_key(item: dict[str, Any], scope: SemanticQueryScope) -> tuple[Any, ...]:
    ontology_order = {entry.ontology_id: index for index, entry in enumerate(scope.ontologies)}
    stale_penalty = 100 if _item_is_stale(item, scope) else 0
    return (
        0 if item["match"].get("candidate_level") == "exact" else 1,
        -(item["match"]["score"] - stale_penalty),
        ontology_order.get(item["ontology_id"], len(ontology_order)),
        _KIND_ORDER.get(item["kind"], 99),
        _normalize_value(item.get("label")),
        item["id"],
    )


def _item_is_stale(item: dict[str, Any], scope: SemanticQueryScope) -> bool:
    if item["assertion_kind"] == "asserted":
        return False
    ontology = next(entry for entry in scope.ontologies if entry.ontology_id == item["ontology_id"])
    kind = "reasoning" if item["assertion_kind"] == "owl_inferred" else "rule"
    return ontology.derived_state.get(kind, {}).get("status") == "stale"


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item["ontology_id"], item["id"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _has_ambiguous_match(items: list[dict[str, Any]]) -> bool:
    labels: dict[str, set[str]] = defaultdict(set)
    for item in items:
        label = _normalize_value(item.get("label"))
        if label:
            labels[label].add(f"{item['ontology_id']}:{item['id']}")
    return any(len(ids) > 1 for ids in labels.values())


def _collect_evidence_ids(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        references = value.get("evidence_references")
        if isinstance(references, list):
            result.extend(
                str(reference["id"])
                for reference in references
                if isinstance(reference, dict) and reference.get("id")
            )
        for nested in value.values():
            result.extend(_collect_evidence_ids(nested))
    elif isinstance(value, list):
        for nested in value:
            result.extend(_collect_evidence_ids(nested))
    return result


def _find_first(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value and value[key] is not None:
            return value[key]
        for nested in value.values():
            found = _find_first(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_first(nested, key)
            if found is not None:
                return found
    return None


def _ontology_warnings(scope: SemanticQueryScope) -> list[dict[str, str]]:
    return [warning for ontology in scope.ontologies for warning in ontology.warnings]


_TIER_ORDER = ("exact", "semantic")


@dataclass(frozen=True)
class _ExecutionExpression:
    text: str
    terms: list[str]
    digest: str
    original_indexes: frozenset[int]


@dataclass(frozen=True)
class _NormalizedInput:
    original: tuple[str, ...]
    execution: list[_ExecutionExpression]


def _normalize_input_queries(queries: list[str] | None) -> _NormalizedInput:
    if not queries:
        raise SemanticContextQueryError("queries must contain at least one expression")
    stripped = [item.strip() for item in queries]
    if any(not item for item in stripped):
        raise SemanticContextQueryError("queries must contain non-empty expressions")
    if len(stripped) > 8:
        raise SemanticContextQueryError("queries may contain at most 8 expressions")
    if any(len(item) > 2000 for item in stripped):
        raise SemanticContextQueryError("queries entries must contain at most 2000 characters")
    if sum(len(item) for item in stripped) > 8000:
        raise SemanticContextQueryError("queries aggregate length must not exceed 8000 characters")
    by_digest: dict[str, _ExecutionExpression] = {}
    digest_to_indexes: dict[str, set[int]] = defaultdict(set)
    for index, raw in enumerate(stripped):
        text, terms = normalize_query_text(raw)
        digest = _expression_digest(text)
        digest_to_indexes[digest].add(index)
        by_digest.setdefault(
            digest,
            _ExecutionExpression(text=text, terms=terms, digest=digest, original_indexes=frozenset()),
        )
    execution: list[_ExecutionExpression] = []
    for digest, expression in by_digest.items():
        execution.append(
            _ExecutionExpression(
                text=expression.text,
                terms=expression.terms,
                digest=digest,
                original_indexes=frozenset(digest_to_indexes[digest]),
            )
        )
    execution.sort(key=lambda item: min(item.original_indexes))
    return _NormalizedInput(original=tuple(stripped), execution=execution)


def _expression_digest(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _validate_context_limit(context_limit: int) -> None:
    if not 0 <= context_limit <= 1000:
        raise SemanticContextQueryError("context_limit must be between 0 and 1000")


def _evidence_tier_for(item: dict[str, Any]) -> str:
    reasons = set((item.get("match") or {}).get("reasons") or [])
    candidate_level = (item.get("match") or {}).get("candidate_level")
    if candidate_level == "exact" or reasons & {
        "exact_label",
        "exact_alias",
        "exact_mapping",
        "identifier",
    }:
        return "exact"
    return "semantic"


def _evidence_payload(item: dict[str, Any]) -> list[dict[str, Any]]:
    match = item.get("match") or {}
    payload = {
        "matched_fields": list(match.get("matched_fields") or []),
        "reasons": list(match.get("reasons") or []),
        "score": match.get("score"),
    }
    mapping = item.get("mapping_evidence") or (item.get("data") or {}).get("mapping_evidence")
    if mapping:
        payload["mapping_evidence"] = list(mapping)
    return [payload]


def _normalise_match_local(item: dict[str, Any], semantic_similarity: float | None) -> None:
    match = item.get("match")
    if not isinstance(match, dict):
        return
    lexical_score = int(match.get("lexical_score", match.get("score", 0)) or 0)
    similarity = (
        semantic_similarity
        if semantic_similarity is not None
        else match.get("semantic_similarity")
    )
    semantic_rank = int(round(float(similarity) * 1000)) if similarity is not None else 0
    score = max(lexical_score, semantic_rank)
    match["score"] = score
    match["lexical_score"] = lexical_score
    if similarity is not None:
        match["semantic_similarity"] = round(float(similarity), 3)
    match["effective_score"] = round(score / 1000, 3)
    reasons = set(match.get("reasons") or [])
    exact = bool(reasons & {"exact_label", "exact_alias", "exact_mapping", "identifier"})
    match["candidate_level"] = "exact" if exact else match.get("candidate_level", "lexical_candidate")


def _dedupe_mapping_evidence(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")): item
        for item in records
        if isinstance(item, dict)
    }
    return [unique[key] for key in sorted(unique)]


def _multi_sort_key(
    item: dict[str, Any],
    scope: SemanticQueryScope,
    fusion_by_item: dict[tuple[str, str], dict[str, Any]],
) -> tuple[Any, ...]:
    ontology_order = {entry.ontology_id: index for index, entry in enumerate(scope.ontologies)}
    key = (item["ontology_id"], item["id"])
    fusion = fusion_by_item.get(key, {})
    tier_rank = 0 if fusion.get("best_evidence_tier") == "exact" else 1
    stale_penalty = 100 if _item_is_stale(item, scope) else 0
    score = (item.get("match") or {}).get("score", 0) or 0
    return (
        tier_rank,
        -(int(score) - stale_penalty),
        -int(fusion.get("support_count", 0)),
        ontology_order.get(item["ontology_id"], len(ontology_order)),
        _KIND_ORDER.get(item["kind"], 99),
        _normalize_value(item.get("label")),
        item["id"],
    )


def _dedupe_multi(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item["ontology_id"], item["id"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _match_resume_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["ontology_id"],
        item["id"],
    )


def _context_resume_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("ontology_id") or "",
        item.get("kind") or "",
        item.get("id") or "",
    )


def _resume_after_key(items: list[dict[str, Any]], key: tuple[Any, ...]) -> list[dict[str, Any]]:
    if not key:
        return items
    key_prefix = tuple(key[:2])
    for index, item in enumerate(items):
        if _match_resume_key(item) == key_prefix:
            return items[index:]
    # Fall back: resume key from a stale/rotated cursor stream is no longer present.
    return items


def _resume_context_after_key(
    items: list[dict[str, Any]], key: tuple[Any, ...]
) -> list[dict[str, Any]]:
    if not key:
        return items
    for index, item in enumerate(items):
        if _context_resume_key(item) == tuple(key):
            return items[index:]
    return items


def _context_sort_key(
    item: dict[str, Any],
    scope: SemanticQueryScope,
    root_paths_by_item: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[Any, ...]:
    ontology_order = {entry.ontology_id: index for index, entry in enumerate(scope.ontologies)}
    identity = (item["ontology_id"], item["id"])
    paths = root_paths_by_item.get(identity, [])
    min_distance = min((int(path["graph_distance"]) for path in paths), default=99)
    return (
        min_distance,
        _KIND_ORDER.get(item["kind"], 99),
        ontology_order.get(item["ontology_id"], len(ontology_order)),
        _normalize_value(item.get("label")),
        item["id"],
    )


def _dedupe_warnings(warnings: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for warning in warnings:
        key = (warning["code"], warning["message"])
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return result
