"""Deterministic unified semantic context retrieval for external Agents."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from rdflib import Literal, URIRef
from rdflib.namespace import RDF
from sqlalchemy.orm import Session

from app.repositories.models import OntologyModel
from app.repositories.rdf_store import RdfStoreRepository
from app.security.auth import AuthPrincipal
from app.services.semantic_access import SemanticAccessView
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
from app.services.semantic_export import namespace_from_settings
from app.services.semantic_lineage_identity import (
    statement_id_for_quad,
)
from app.services.semantic_query_scope import SemanticQueryScope, SemanticQueryScopeResolver
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
    semantic_context_resource_descriptions_query,
    _context_row_key,
)
from app.services.operation_semantics import (
    OPERATION_SCHEMA_VERSION,
    OperationValidationError,
    operation_predicates,
    operation_vocabulary,
    validate_operation_payload,
)


RESOURCE_TYPE_ORDER = (
    "concept",
    "instance",
    "relation",
    "fact",
    "operation",
    "mapping",
    "metric",
)
RESOURCE_TYPES = set(RESOURCE_TYPE_ORDER)
CONTEXT_EXPANSION_BUDGET = 5000
RDF_READ_CHUNK_SIZE = 500
_ANNOTATION_NAMES = {
    "semantic_definition": "semanticDefinition",
    "mapping_definition": "mappingDefinition",
    "action_definition": "actionDefinition",
    "parameter_definition": "parameterDefinition",
}
ASSERTION_TYPES = {"asserted"}
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
_TBOX_PREDICATES = {
    str(RDF.type),
    "http://www.w3.org/2000/01/rdf-schema#domain",
    "http://www.w3.org/2000/01/rdf-schema#range",
    "http://www.w3.org/2000/01/rdf-schema#subClassOf",
    "http://www.w3.org/2000/01/rdf-schema#subPropertyOf",
    "http://www.w3.org/2002/07/owl#equivalentClass",
    "http://www.w3.org/2002/07/owl#equivalentProperty",
    "http://www.w3.org/2002/07/owl#inverseOf",
}
# Consumer-facing related-context priority.  Asserted business statements come
# first, schema scaffolding and generated shape projections last.  This is the
# one total order used by the public response; primary-match ordering is not
# affected.
_CONTEXT_ORIGIN_RANK = {
    "asserted_literal": 0,
    "asserted_relation": 1,
    "resource": 2,
    "derived_reference": 2,
    "derived_statement": 3,
    "tbox_statement": 5,
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
    """Run one lexical candidate, ranking, and neighborhood pipeline."""

    def __init__(
        self,
        session: Session,
        rdf_store: RdfStoreRepository,
        scope_resolver: SemanticQueryScopeResolver,
        # Kept as an ignored compatibility slot for older dependency wiring.
        # Context Query no longer performs a lineage lookup for any result.
        lineage_service: Any | None = None,
        cursor_codec: ContextCursorCodec | None = None,
        access_view: SemanticAccessView | None = None,
    ) -> None:
        self.session = session
        self.rdf_store = rdf_store
        self.scope_resolver = scope_resolver
        self.access_view = access_view or SemanticAccessView.all_visible()
        self.operation_vocab = operation_vocabulary(scope_resolver.settings)
        self.operation_predicates = operation_predicates(scope_resolver.settings)
        self.operation_type = self.operation_vocab["type"]
        self.settings = scope_resolver.settings
        self.cursor_codec = cursor_codec
        self._semantic_roles = None
        self._description_cache = {}
        self._resource_cache = {}
        self._request_assertions = set(ASSERTION_TYPES)

    def query(
        self,
        *,
        project_id: str,
        scope_mode: str,
        ontology_ids: list[str] | None,
        query: str,
        resource_types: list[str] | None = None,
        assertion_types: list[str] | None = None,
        semantic_roles: list[str] | None = None,
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
            semantic_roles=semantic_roles,
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
        semantic_roles: list[str] | None = None,
        search_mode: str = "hybrid",
        depth: int = 1,
        limit: int = 20,
        context_limit: int = 100,
        principal: AuthPrincipal | None = None,
        match_cursor: str | None = None,
        context_cursor: str | None = None,
        context_detail: str = "full",
    ) -> dict[str, Any]:
        """Run the R1.2-004 multi-expression Context Query pipeline.

        See design §5 for the contract. This method resolves scope once,
        submits one bounded embedding batch for all distinct normalized
        expressions, fuses candidates before decoration/expansion, and emits
        one response with independent match/context page state and cursors.
        ``context_detail`` selects the ``related_context`` row projection:
        ``compact`` keeps identity/kind/label/statement essentials/evidence
        status/root paths only.
        """
        semantic_roles = _normalize_semantic_roles(semantic_roles)
        self._semantic_roles = semantic_roles
        self._description_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._resource_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._candidate_window_incomplete = False
        self._expansion = {"status": "not_requested"}
        self._request_depth = depth
        self._request_assertions = set(assertion_types or ASSERTION_TYPES)
        if principal is None:
            raise SemanticContextQueryError(
                "A server-derived principal binding is required for Context Query"
            )
        if context_detail not in {"full", "compact"}:
            raise SemanticContextQueryError("context_detail must be full or compact")
        if (match_cursor is not None) and (context_cursor is not None):
            raise SemanticContextQueryError(
                "Provide at most one of match_cursor or context_cursor"
            )
        if len(queries) == 1 and _is_iri_anchor(queries[0]):
            if match_cursor is not None:
                raise SemanticContextQueryError(
                    "match_cursor cannot be used with an exact IRI anchor"
                )
            return self._query_anchor(
                anchor_iri=queries[0].strip(),
                project_id=project_id,
                scope_mode=scope_mode,
                ontology_ids=ontology_ids,
                resource_types=resource_types,
                assertion_types=assertion_types,
                semantic_roles=semantic_roles,
                search_mode=search_mode,
                depth=depth,
                limit=limit,
                context_limit=context_limit,
                principal=principal,
                context_cursor=context_cursor,
                context_detail=context_detail,
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
            semantic_roles=semantic_roles,
            search_mode=search_mode,
            depth=depth,
            limit=limit,
            context_limit=context_limit,
            workspace_versions=workspace_versions,
            source_signatures=source_signatures,
        )

        match_payload = self._decode_cursor_opt(
            cursor_codec, match_cursor, binding=binding, expected_kind=CURSOR_KIND_MATCH,
        )
        context_payload = self._decode_cursor_opt(
            cursor_codec, context_cursor, binding=binding, expected_kind=CURSOR_KIND_CONTEXT,
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
                context_detail=context_detail,
            )

        candidate_limit = min(5000, max(500, limit * 50))
        lexical_by_expression: list[list[dict[str, Any]]] = []
        retrieval_warnings: list[dict[str, str]] = []
        retrieval_indexes: list[dict[str, Any]] = []
        retrieval_completeness = "complete"
        for expression in execution_set:
            candidates = self._qualified_lexical_candidates(
                scope, expression.text, expression.terms, candidate_limit,
                selected_resource_types, selected_assertion_types,
            )
            if "operation" in selected_resource_types:
                candidates.extend(self._operation_candidates(scope, expression.text, expression.terms))
            if "mapping" in selected_resource_types:
                candidates.extend(self._mapping_candidates(scope, expression.text, expression.terms))
            if "metric" in selected_resource_types:
                candidates.extend(self._metric_candidates(scope, expression.text, expression.terms))
            candidates.extend(
                governed_mapping_lexical_candidates(
                    self.session,
                    ontology_ids=(entry.ontology_id for entry in scope.ontologies),
                    query=expression.text,
                    resource_kinds=selected_resource_types,
                )
            )
            # R3.0-004: apply the authorization view to every candidate source
            # (lexical RDF, rules, operations, governed mappings) before
            # fusion so ranking, fusion summaries, truncation, and cursors
            # are computed on the authorized subset only.
            candidates = self._qualified_candidates(
                candidates, scope, selected_resource_types, selected_assertion_types
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
            candidate_filter=lambda items: self._qualified_candidates(
                items, scope, selected_resource_types, selected_assertion_types
            ),
        )
        retrieval_warnings = list(retrieval.get("warnings") or [])
        retrieval_indexes = list(retrieval.get("indexes") or [])
        retrieval_completeness = retrieval.get("completeness", "complete")
        for expression_index, candidates in enumerate(retrieval.get("candidates_by_query") or []):
            promoted = promote_exact_label_candidates(
                candidates, execution_set[expression_index].text
            )
            promoted = self._qualified_candidates(
                promoted, scope, selected_resource_types, selected_assertion_types
            )
            for item in promoted:
                item.setdefault("_expression_indexes", set()).update(
                    execution_set[expression_index].original_indexes
                )
            lexical_by_expression[expression_index] = fuse_context_candidates(
                lexical_by_expression[expression_index], promoted
            )

        if self._candidate_window_incomplete:
            retrieval_completeness = "degraded"
            warnings.append({
                "code": "candidate_window_incomplete",
                "message": "Qualified candidate window is incomplete; narrow the query or use an IRI.",
            })
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

        candidate_digest = _visible_digest(fused)
        payload = context_payload or match_payload
        if payload is not None and payload.candidate_digest != candidate_digest:
            raise SemanticContextSnapshotChanged("Visible candidates no longer match the cursor")
        if context_payload is not None:
            fused = _resume_after_key(fused, context_payload.match_page_start_key)
        elif match_payload is not None:
            fused = _resume_after_key(fused, match_payload.resume_key)

        matches_truncated = len(fused) > limit
        primary = fused[:limit]
        root_digest = _root_digest(primary)
        if context_payload is not None and context_payload.root_match_digest != root_digest:
            raise SemanticContextSnapshotChanged("Visible roots no longer match the cursor")
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
                    candidate_digest=candidate_digest,
                ),
            )

        decorated_primary, related_raw, root_paths_by_item = self._expand_multi_primary(
            primary=primary,
            scope=scope,
            depth=depth,
            context_limit=context_limit,
            selected_resource_types=selected_resource_types,
            selected_assertion_types=selected_assertion_types,
        )

        # Apply context cursor within the bound root-match page only.
        context_digest = self._visible_context_digest(related_raw, root_paths_by_item)
        if context_payload is not None:
            if context_payload.context_digest != context_digest:
                raise SemanticContextSnapshotChanged("Visible context no longer matches the cursor")
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
                    match_page_start_key=_match_resume_key(primary[0]),
                    root_match_digest=root_digest,
                    candidate_digest=candidate_digest,
                    context_digest=context_digest,
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
            context_detail=context_detail,
        )

    def _query_anchor(
        self,
        *,
        anchor_iri: str,
        project_id: str,
        scope_mode: str,
        ontology_ids: list[str] | None,
        resource_types: list[str] | None,
        assertion_types: list[str] | None,
        semantic_roles: list[str] | None,
        search_mode: str,
        depth: int,
        limit: int,
        context_limit: int,
        principal: AuthPrincipal | None,
        context_cursor: str | None,
        context_detail: str = "full",
    ) -> dict[str, Any]:
        """Exact-IRI mode.

        The original interface accepts an absolute IRI as ``query``.  It skips
        lexical/semantic recall and returns that node as the sole primary match,
        with its graph neighborhood in ``related_context``.  Context cursors
        continue the same exact anchor page.
        """
        _validate_filters(resource_types, assertion_types, depth, limit)
        _validate_context_limit(context_limit)
        if search_mode not in {"hybrid", "lexical"}:
            raise SemanticContextQueryError("search_mode must be hybrid or lexical")
        if context_detail not in {"full", "compact"}:
            raise SemanticContextQueryError("context_detail must be full or compact")
        selected_resource_types = set(resource_types or RESOURCE_TYPES)
        selected_assertion_types = set(assertion_types or ASSERTION_TYPES)
        scope = self.scope_resolver.resolve(
            project_id=project_id,
            scope_mode=scope_mode,
            ontology_ids=ontology_ids,
        )
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
            original_queries=[anchor_iri],
            normalized_queries=[anchor_iri],
            resource_types=resource_types,
            assertion_types=assertion_types,
            semantic_roles=semantic_roles,
            search_mode=search_mode,
            depth=depth,
            limit=limit,
            context_limit=context_limit,
            workspace_versions=workspace_versions,
            source_signatures=source_signatures,
        )
        context_payload = self._decode_cursor_opt(
            cursor_codec, context_cursor, binding=binding, expected_kind=CURSOR_KIND_CONTEXT,
        )
        warnings: list[dict[str, str]] = [*scope.warnings, *_ontology_warnings(scope)]
        empty_recall = {
            "mode": "anchor",
            "match_status": "no_match",
            "completeness": "complete",
        }
        if not scope.graph_iris:
            return self._multi_response(
                scope=scope,
                original_queries=[anchor_iri],
                normalized_queries=[anchor_iri],
                primary=[],
                related=[],
                matched_queries_by_item={},
                fusion_by_item={},
                root_paths_by_item={},
                recall=empty_recall,
                warnings=warnings,
                matches_truncated=False,
                context_truncated=False,
                match_cursor_out=None,
                context_cursor_out=None,
                context_detail=context_detail,
            )
        anchor_item = self._resource_item(scope, anchor_iri)
        if anchor_item is not None:
            qualified = self._qualified_candidates(
                [anchor_item], scope, selected_resource_types, selected_assertion_types
            )
            anchor_item = qualified[0] if qualified else None
        candidate_digest = _visible_digest([anchor_item] if anchor_item else [])
        if context_payload is not None and context_payload.candidate_digest != candidate_digest:
            raise SemanticContextSnapshotChanged("Visible anchor no longer matches the cursor")
        if anchor_item is None:
            warnings.append(
                {
                    "code": "anchor_not_found",
                    "message": "The exact IRI is not present in the current semantic scope.",
                }
            )
            return self._multi_response(
                scope=scope,
                original_queries=[anchor_iri],
                normalized_queries=[anchor_iri],
                primary=[],
                related=[],
                matched_queries_by_item={},
                fusion_by_item={},
                root_paths_by_item={},
                recall=empty_recall,
                warnings=warnings,
                matches_truncated=False,
                context_truncated=False,
                match_cursor_out=None,
                context_cursor_out=None,
                context_detail=context_detail,
            )

        decorated_primary, related_raw, root_paths_by_item = self._expand_multi_primary(
            primary=[anchor_item],
            scope=scope,
            depth=depth,
            context_limit=context_limit,
            selected_resource_types=selected_resource_types,
            selected_assertion_types=selected_assertion_types,
        )
        context_digest = self._visible_context_digest(related_raw, root_paths_by_item)
        if context_payload is not None:
            if context_payload.context_digest != context_digest:
                raise SemanticContextSnapshotChanged("Visible context no longer matches the cursor")
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
                    match_page_start_key=_match_resume_key(anchor_item),
                    root_match_digest=_root_digest([anchor_item]),
                    candidate_digest=candidate_digest,
                    context_digest=context_digest,
                ),
            )
        if context_truncated:
            warnings.append(
                {"code": "context_truncated", "message": "Semantic context was truncated."}
            )
        decorated_related = self._decorate_related(
            related_page, scope, root_paths_by_item
        )
        warnings.extend(
            warning
            for item in [*decorated_primary, *decorated_related]
            for warning in item.get("warnings", [])
        )
        identity = self._identity_key(anchor_item)
        matched_queries_by_item = {
            identity: [{"indexes": [0], "evidence_tier": "exact"}]
        }
        fusion_by_item = {
            identity: {"best_evidence_tier": "exact", "support_count": 1}
        }
        return self._multi_response(
            scope=scope,
            original_queries=[anchor_iri],
            normalized_queries=[anchor_iri],
            primary=decorated_primary,
            related=decorated_related,
            matched_queries_by_item=matched_queries_by_item,
            fusion_by_item=fusion_by_item,
            root_paths_by_item=root_paths_by_item,
            recall={"mode": "anchor", "match_status": "exact", "completeness": "complete"},
            warnings=warnings,
            matches_truncated=False,
            context_truncated=context_truncated,
            match_cursor_out=None,
            context_cursor_out=next_context_cursor,
            context_detail=context_detail,
        )

    def _selected_graphs(self, scope: SemanticQueryScope) -> list[str]:
        return [
            graph for graph in scope.graph_iris
            if _assertion_filter_value(scope.graph_assertion_kinds.get(graph, "asserted"))
            in self._request_assertions
        ]

    def _read_chunks(self, build_query):
        """Stable RDF continuation; raw/hidden rows never consume a visible budget."""
        after = None
        while True:
            result = self.rdf_store.query_sparql(
                build_query(RDF_READ_CHUNK_SIZE, after),
                timeout_seconds=10, limit=RDF_READ_CHUNK_SIZE,
            )
            rows = _bindings(result.result)
            yield rows
            if len(rows) < RDF_READ_CHUNK_SIZE:
                return
            key = _value(rows[-1], "rowKey")
            if not key or key == after:
                raise SemanticContextQueryError("RDF continuation key is missing or did not advance")
            after = key

    def _hydrate_candidates(
        self, items: list[dict[str, Any]], scope: SemanticQueryScope,
    ) -> list[dict[str, Any]]:
        resources = [item for item in items if not _is_statement(item)]
        iris = sorted({item["iri"] for item in resources if item.get("iri")})
        missing = [iri for iri in iris if any(
            (entry.ontology_id, iri) not in self._description_cache for entry in scope.ontologies
        )]
        vocab = str(namespace_from_settings(self.settings).vocab)
        predicates = {vocab + name: field for field, name in _ANNOTATION_NAMES.items()}
        if missing:
            rows_by_resource: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for rows in self._read_chunks(lambda limit, after: (
                semantic_context_resource_descriptions_query(
                    self._selected_graphs(scope), missing, limit, list(predicates), after,
                )
            )):
                for row in rows:
                    graph, subject = _value(row, "graph"), _value(row, "subject")
                    if graph in scope.graph_to_ontology and subject in missing:
                        rows_by_resource[(scope.graph_to_ontology[graph], subject)].append(row)
            for iri in missing:
                for ontology in scope.ontologies:
                    key = (ontology.ontology_id, iri)
                    own_rows = rows_by_resource.get(key, [])
                    values: dict[str, set[str]] = defaultdict(set)
                    annotation_terms: dict[str, dict[str, str]] = defaultdict(dict)
                    for row in own_rows:
                        predicate, value = _value(row, "predicate"), _value(row, "object")
                        if predicate and value is not None:
                            values[predicate].add(value)
                            if predicate in predicates:
                                annotation_terms[predicate][_binding_n3(row["object"])] = value
                    payload: dict[str, Any] = {"data": {}, "_annotation_values": [
                        value for values_ in values.values() for value in sorted(values_)
                    ]}
                    diagnostics = []
                    # Full values stay available for authorization before any projection.
                    for predicate, field in predicates.items():
                        raw_values = list(annotation_terms[predicate].values())
                        if not raw_values:
                            continue
                        if len(raw_values) != 1:
                            diagnostics.append({"field": field, "code": "ambiguous_annotation"})
                            continue
                        try:
                            value = json.loads(raw_values[0])
                            if not isinstance(value, dict):
                                raise ValueError("Annotation must be a JSON object")
                        except (ValueError, TypeError):
                            diagnostics.append({"field": field, "code": "invalid_annotation"})
                            continue
                        payload["data"][field] = value
                    if diagnostics:
                        payload["data"]["annotation_read_diagnostics"] = diagnostics
                    descriptions = sorted(
                        values.get("http://www.w3.org/2000/01/rdf-schema#comment", set())
                        | values.get("http://purl.org/dc/terms/description", set())
                    )
                    if descriptions:
                        payload["description"] = descriptions[0]
                    labels = sorted(values.get("http://www.w3.org/2000/01/rdf-schema#label", ()))
                    if labels:
                        payload["labels"] = labels
                        payload["label"] = labels[0]
                    aliases = sorted(values.get("http://www.w3.org/2004/02/skos/core#altLabel", ()))
                    if aliases:
                        payload["aliases"] = aliases
                    types = sorted(values.get(str(RDF.type), ()))
                    if types:
                        payload["data"]["rdf_types"] = types
                    if own_rows:
                        payload["_own_rows"] = own_rows
                    self._description_cache[key] = payload
        for item in resources:
            payload = self._description_cache.get((item["ontology_id"], item.get("iri")), {})
            item["data"] = {**(item.get("data") or {}), **payload.get("data", {})}
            if "description" in payload:
                item["description"] = payload["description"]
            item["_annotation_values"] = payload.get("_annotation_values", [])
        return items

    def _qualified_candidates(
        self, items: list[dict[str, Any]], scope: SemanticQueryScope,
        resource_types: set[str], assertion_types: set[str],
    ) -> list[dict[str, Any]]:
        self._hydrate_candidates(items, scope)
        for item in items:
            if not _is_statement(item) and item["kind"] in {"operation", "mapping", "metric"}:
                own_rows = self._description_cache.get(
                    (item["ontology_id"], item.get("iri")), {}
                ).get("_own_rows", [])
                if own_rows:
                    projection = self._resource_from_rows(own_rows, scope, item["iri"])
                    if projection is not None:
                        item["data"] = {**item["data"], **projection["data"]}
        return [item for item in items if (
            item["kind"] in resource_types
            and _assertion_filter_value(item["assertion_kind"]) in assertion_types
            and self.access_view.filter_candidate(item)
            and (not self._semantic_roles or (
                not _is_statement(item)
                and (item.get("data", {}).get("semantic_definition") or {}).get("semantic_role")
                in self._semantic_roles
            ))
        )]

    def _qualified_lexical_candidates(
        self, scope: SemanticQueryScope, text: str, terms: list[str], limit: int,
        resource_types: set[str], assertion_types: set[str],
    ) -> list[dict[str, Any]]:
        # Resources can have many matching literals split across raw chunks.
        # Hydrate each complete resource before counting its identity once.
        candidates: dict[tuple[str, str, str], dict[str, Any]] = {}
        for rows in self._read_chunks(lambda chunk_limit, after: (
            semantic_context_candidates_query(
                scope.graph_to_ontology, terms, chunk_limit, self.operation_type,
                self.operation_predicates, after,
            )
        )):
            items = self._rdf_candidates(rows, scope, text, terms)
            for item in self._qualified_candidates(items, scope, resource_types, assertion_types):
                key = self._identity_key(item)
                if key in candidates:
                    candidates[key] = self._merge_into(candidates[key], item)
                else:
                    candidates[key] = item
                if len(candidates) > limit:
                    self._candidate_window_incomplete = True
                    return list(candidates.values())[:limit]
        return list(candidates.values())

    def _resource_item(self, scope: SemanticQueryScope, iri: str) -> dict[str, Any] | None:
        seed = [{"iri": iri, "id": iri, "kind": "instance", "ontology_id": entry.ontology_id,
                 "data": {}, "assertion_kind": "asserted"} for entry in scope.ontologies]
        self._hydrate_candidates(seed, scope)
        for entry in scope.ontologies:
            rows = self._description_cache[(entry.ontology_id, iri)].get("_own_rows", [])
            if rows:
                return self._resource_from_rows(rows, scope, iri)
        # An IRI used only as an endpoint still exists, but a hidden edge must
        # not be used to disclose that existence.
        for rows in self._read_chunks(lambda limit, after: semantic_context_neighborhood_query(
            self._selected_graphs(scope), [iri], limit, self.operation_type,
            self.operation_predicates, after,
        )):
            visible = [row for row in rows if self.access_view.filter_candidate(
                self._statement_item(row, scope, distance=0) or {}
            )]
            if visible:
                return self._resource_from_rows(visible, scope, iri)
        return None

    def _resource_from_rows(self, rows, scope, iri):
        item = _anchor_candidate_from_rows(rows, scope, iri)
        if item is None:
            return None
        key = (item["ontology_id"], iri)
        if key in self._resource_cache:
            return dict(self._resource_cache[key])
        self._hydrate_candidates([item], scope)
        # Read the existing specialized projections rather than exposing
        # Operation internals as ordinary neighboring triples.
        if item["kind"] in {"operation", "mapping", "metric"}:
            producer = getattr(self, f"_{item['kind']}_candidates")
            projected = producer(scope, iri, [iri], resource_iris=[iri])
            projected = [candidate for candidate in projected
                         if candidate["ontology_id"] == item["ontology_id"]]
            if projected:
                item = projected[0]
                self._hydrate_candidates([item], scope)
        self._resource_cache[key] = item
        return dict(item)

    def _producer_rows(self, query: str):
        """Continue existing specialized RDF projections by their complete row identity."""
        select_end = query.index("WHERE")
        select_body = query[:select_end]
        # Existing aggregate aliases are presentation fields, not row identity.
        select_body = re.sub(r"\([^\n]*\)", "", select_body)
        variables = tuple(dict.fromkeys(re.findall(r"\?\w+", select_body)))
        query = query[:select_end] + " ?rowKey " + query[select_end:]
        close = query.rfind("\n}")
        query = query[:close] + "\n  BIND(" + _context_row_key(variables) + (
            " AS ?rowKey)\n  {continuation}\n"
        ) + query[close:]
        if "GROUP BY" in query:
            query = query.replace("\nORDER BY", " ?rowKey\nORDER BY", 1)
        query = re.sub(r"ORDER BY[^\n]*", "ORDER BY ?rowKey", query)
        query = query.replace("LIMIT 5000", "LIMIT {chunk_limit}")
        for rows in self._read_chunks(lambda limit, after: query.replace(
            "{chunk_limit}", str(limit)
        ).replace(
            "{continuation}", f"FILTER(?rowKey > {Literal(after).n3()})" if after else ""
        )):
            yield from rows

    def _visible_context_digest(self, items, paths):
        return _json_digest({
            "items": _visible_digest(items),
            "paths": [[list(key), value] for key, value in sorted(paths.items())],
            "expansion": self._expansion,
        })

    def _verify_scope_snapshot(self, scope: SemanticQueryScope) -> None:
        project_id = scope.project_id
        # Re-read committed metadata rather than an SQLAlchemy identity-map copy.
        self.session.expire_all()
        # Check only the already-bound Ontologies; do not resolve the Project or
        # rerun discovery/recall for every expression or for the final fence.
        for entry in scope.ontologies:
            ontology = self.session.get(OntologyModel, entry.ontology_id)
            if ontology is None or ontology.project_id != project_id:
                raise SemanticContextSnapshotChanged("Semantic scope changed during the query")
            readiness = self.scope_resolver.readiness.evaluate(ontology)
            if (
                not readiness.queryable or readiness.read_scope is None
                or readiness.workspace_version != entry.workspace_version
                or readiness.read_scope.source_signature != entry.source_signature
            ):
                raise SemanticContextSnapshotChanged("Semantic scope changed during the query")


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
                key = (item["ontology_id"], item["kind"], item["id"])
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
        self, *, primary, scope, depth, context_limit,
        selected_resource_types, selected_assertion_types,
    ):
        decorated_primary = [self._decorate(item, scope) for item in primary]
        related_raw = []
        root_paths_by_item = defaultdict(list)
        self._work_items: set[tuple[str, str, str]] = set()
        self._expansion = {"status": "not_requested"}
        self._work_stopped = False
        if context_limit <= 0 or depth <= 0:
            return decorated_primary, related_raw, root_paths_by_item
        self._expansion = {"status": "complete"}
        primary_keys = {self._identity_key(item) for item in primary}
        for rank, root in enumerate(primary):
            for item in self._related_for_root(
                root, scope=scope, depth=depth, context_limit=CONTEXT_EXPANSION_BUDGET,
                selected_resource_types=selected_resource_types,
                selected_assertion_types=selected_assertion_types,
            ):
                key = self._identity_key(item)
                if key in primary_keys:
                    continue
                root_paths_by_item[key].append({
                    "root_match_id": root["id"],
                    "graph_distance": int(item.get("distance") or 1), "_root_rank": rank,
                })
                related_raw.append(item)
            if self._work_stopped:
                break
        deduped = {self._identity_key(item): item for item in related_raw}
        for key in deduped:
            shortest = {}
            for path in root_paths_by_item[key]:
                rank = path["_root_rank"]
                if rank not in shortest or path["graph_distance"] < shortest[rank]["graph_distance"]:
                    shortest[rank] = path
            root_paths_by_item[key] = [
                {"root_match_id": path["root_match_id"], "graph_distance": path["graph_distance"]}
                for _, path in sorted(shortest.items())
            ]
        ordered = sorted(deduped.values(), key=lambda item: _context_sort_key(
            item, scope, root_paths_by_item,
        ))
        return decorated_primary, ordered, root_paths_by_item

    def _accept_work(self, item):
        if not self.access_view.filter_candidate(item):
            return False
        key = self._identity_key(item)
        if key not in self._work_items:
            if len(self._work_items) >= CONTEXT_EXPANSION_BUDGET:
                self._work_stopped = True
                self._expansion = {"status": "partial", "reason": "expansion_budget_reached"}
                return False
            self._work_items.add(key)
        return True

    def _related_for_root(
        self, root, *, scope, depth, context_limit,
        selected_resource_types, selected_assertion_types,
    ):
        related = []
        # Structured mapping annotations contain a small, closed set of
        # resource-reference fields.  They are not RDF triples, but they are
        # still directional semantic links for a Consumer.  Project these
        # links before ordinary graph expansion so the endpoint remains
        # available when the JSON literal is the only connection.
        related.extend(self._structured_reference_items(
            root,
            scope,
            selected_resource_types=selected_resource_types,
            selected_assertion_types=selected_assertion_types,
        ))
        if self._work_stopped:
            return related
        # All producers share the visible work budget; the page size is applied
        # only after their complete visible union has been sorted.
        for item in self._operation_target_context([root], scope, limit=None, enabled=True):
            self._hydrate_candidates([item], scope)
            if self._accept_work(item) and item["kind"] in selected_resource_types:
                related.append(item)
            if self._work_stopped:
                return related
        related.extend(self._expand_neighborhood(
            [root], scope, depth=depth, limit=CONTEXT_EXPANSION_BUDGET,
            resource_types=selected_resource_types, assertion_types=selected_assertion_types,
        ))
        return related

    def _structured_reference_items(
        self,
        source: dict[str, Any],
        scope: SemanticQueryScope,
        *,
        selected_resource_types: set[str],
        selected_assertion_types: set[str],
    ) -> list[dict[str, Any]]:
        """Expose approved JSON mapping references as derived context edges.

        The edge identity is deliberately separate from an RDF statement:
        ``subject + predicate + field_path + target`` is hashed into ``id``;
        the public payload carries ``source_path`` and ``derived_reference``
        instead of pretending the JSON field was stored as a graph triple.
        Only fixed mapping fields are inspected.  Arbitrary JSON strings never
        become graph endpoints.
        """
        source_iri = source.get("iri")
        if not isinstance(source_iri, str) or not source_iri:
            return []
        vocab = str(namespace_from_settings(self.settings).vocab)
        items: list[dict[str, Any]] = []
        for reference in _structured_mapping_references(source, vocab):
            target = reference["target"]
            # The target is included in the full value authorization check;
            # filtering only the endpoint resource would leak its existence
            # through a derived edge.
            edge = {
                "id": _structured_reference_id(
                    source_iri,
                    reference["predicate"],
                    reference["field_path"],
                    target,
                ),
                "kind": "relation",
                "target_kind": "derived_reference",
                "ontology_id": source.get("ontology_id"),
                "iri": target,
                "label": f"{_local_name(source_iri)} → {_local_name(target)}",
                "aliases": [],
                "description": None,
                "data": {
                    "source_iri": source_iri,
                    "target_iri": target,
                    "predicate": reference["predicate"],
                    "field_path": reference["field_path"],
                    "source_path": reference["field_path"],
                    "json_path": reference["json_path"],
                    "derived_reference": True,
                },
                "distance": max(1, int(source.get("distance") or 0) + 1),
                "assertion_kind": source.get("assertion_kind", "asserted"),
                "match": _neighborhood_match(max(1, int(source.get("distance") or 0) + 1)),
            }
            if not self.access_view.filter_candidate(edge):
                continue
            if _assertion_filter_value(edge["assertion_kind"]) not in selected_assertion_types:
                continue
            if self._accept_work(edge) and "relation" in selected_resource_types:
                items.append(edge)
            if self._work_stopped:
                break

            # A visible target resource gives the Consumer the usual resource
            # projection and keeps the derived edge useful across Ontologies.
            target_resource = self._resource_item(scope, target)
            if target_resource is None or not self.access_view.filter_candidate(target_resource):
                continue
            target_resource["distance"] = edge["distance"]
            target_resource["match"] = _neighborhood_match(edge["distance"])
            if _assertion_filter_value(target_resource.get("assertion_kind", "asserted")) not in selected_assertion_types:
                continue
            if self._accept_work(target_resource) and target_resource.get("kind") in selected_resource_types:
                items.append(target_resource)
            if self._work_stopped:
                break
        return items


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

    def _identity_key(self, item: dict[str, Any]) -> tuple[str, str, str]:
        return (item["ontology_id"], item["kind"], item["id"])

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
        context_detail: str = "full",
    ) -> dict[str, Any]:
        self._verify_scope_snapshot(scope)
        decorated_primary: list[dict[str, Any]] = []
        for item in primary:
            key = self._identity_key(item)
            item_copy = _public_item(item)
            item_copy["matched_queries"] = [
                {
                    "indexes": list(entry.get("indexes") or []),
                    "evidence_tier": entry.get("evidence_tier"),
                }
                for entry in matched_queries_by_item.get(key, [])
                if isinstance(entry, Mapping)
            ]
            item_copy["fusion"] = dict(
                fusion_by_item.get(key, {"best_evidence_tier": "semantic", "support_count": 0})
            )
            decorated_primary.append(item_copy)
        decorated_related: list[dict[str, Any]] = []
        for item in related:
            item_copy = _public_item(item)
            key = self._identity_key(item)
            item_copy["root_paths"] = list(root_paths_by_item.get(key, []))
            decorated_related.append(item_copy)
        if context_detail == "compact":
            decorated_related = [
                _compact_related_row(row) for row in decorated_related
            ]
        if self._expansion["status"] == "partial":
            warnings.append({
                "code": "context_expansion_incomplete",
                "message": "Context expansion is incomplete; narrow the query or continue from an IRI.",
            })
        truncated = bool(matches_truncated or context_truncated)
        # The consumer already knows what it asked for.  Keep only the stable
        # echo needed by multi-expression callers and cursor binding.
        query_echo: dict[str, Any] = {
            "queries": list(original_queries),
            "normalized_queries": list(normalized_queries),
            "semantic_roles": self._semantic_roles,
            "depth": self._request_depth,
            "result_scope": "authorized_query_scope",
        }
        return {
            "query": query_echo,
            "result_status": "matched" if decorated_primary else "no_match",
            "scope": _public_scope(scope.public_dict()),
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
                "expansion": dict(self._expansion),
            },
            "truncated": truncated,
            "recall": _public_recall(recall),
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
                        # target. Keep this target kind explicit so decoration
                        # never infers statement identity from presentation
                        # ``kind`` alone.
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
        self._hydrate_candidates(list(resources.values()), scope)
        for resource in resources.values():
            payload = self._description_cache.get((resource["ontology_id"], resource["iri"]), {})
            types = resource.pop("types") | set(resource["data"].get("rdf_types", []))
            labels = sorted(set(resource.pop("labels")) | set(payload.get("labels", [])))
            resource["aliases"] = sorted(set(resource["aliases"]) | set(payload.get("aliases", [])))
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
                **resource["data"],
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
        self, scope: SemanticQueryScope, text: str, terms: list[str],
        resource_iris: list[str] | None = None
    ) -> list[dict[str, Any]]:
        graph_values = " ".join(URIRef(graph).n3() for graph in scope.graph_iris)
        v = self.operation_vocab
        resource_values = (
            "VALUES ?operation { " + " ".join(URIRef(iri).n3() for iri in resource_iris) + " }"
            if resource_iris else ""
        )
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
  {resource_values}
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
        candidates = []
        for row in self._producer_rows(query):
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
            if resource_iris and iri in resource_iris:
                match = _neighborhood_match(1)
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

    def _mapping_candidates(
        self, scope: SemanticQueryScope, text: str, terms: list[str],
        resource_iris: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Lexical candidates for relational schema mapping resources
        (TableMapping / JoinMapping / EnumValueMeaning), pattern-aligned with
        ``_operation_candidates``: explicit graph scope injection, exact
        label first, reference fields carried in the candidate ``data``
        payload so consumers see the reference topology."""
        graph_values = " ".join(URIRef(graph).n3() for graph in scope.graph_iris)
        vocab = str(namespace_from_settings(self.settings).vocab)
        resource_values = (
            "VALUES ?mapping { " + " ".join(URIRef(iri).n3() for iri in resource_iris) + " }"
            if resource_iris else ""
        )
        query = f"""# template: semantic-context-mappings
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX op: <{vocab}>
SELECT ?graph ?mapping ?type ?label ?mappedClass ?mappedDefinition ?mappedRelation
       ?mappedProperty ?tableName ?enumValue ?businessMeaning ?columnMappings ?joinPath
       ?schemaSource ?semanticValue ?tableMapping ?column ?mappingDefinition
WHERE {{
  VALUES ?graph {{ {graph_values} }}
  {resource_values}
  VALUES ?type {{ op:TableMapping op:JoinMapping op:EnumValueMeaning }}
  GRAPH ?graph {{
    ?mapping a ?type ;
             rdfs:label ?label .
    OPTIONAL {{ ?mapping op:mappedClass ?mappedClass . }}
    OPTIONAL {{ ?mapping op:mappedDefinition ?mappedDefinition . }}
    OPTIONAL {{ ?mapping op:mappedRelationType ?mappedRelation . }}
    OPTIONAL {{ ?mapping op:mappedProperty ?mappedProperty . }}
    OPTIONAL {{ ?mapping op:tableMapping ?tableMapping . }}
    OPTIONAL {{ ?mapping op:columnName ?column . }}
    OPTIONAL {{ ?mapping op:tableName ?tableName . }}
    OPTIONAL {{ ?mapping op:enumValue ?enumValue . }}
    OPTIONAL {{ ?mapping op:businessMeaning ?businessMeaning . }}
    OPTIONAL {{ ?mapping op:columnMappings ?columnMappings . }}
    OPTIONAL {{ ?mapping op:joinPath ?joinPath . }}
    OPTIONAL {{ ?mapping op:schemaSource ?schemaSource . }}
    OPTIONAL {{ ?mapping op:semanticValue ?semanticValue . }}
    OPTIONAL {{ ?mapping op:mappingDefinition ?mappingDefinition . }}
  }}
}}
ORDER BY ?graph ?mapping
LIMIT 5000
"""
        candidates: list[dict[str, Any]] = []
        for row in self._producer_rows(query):
            graph = _value(row, "graph")
            iri = _value(row, "mapping")
            if not graph or graph not in scope.graph_to_ontology or not iri:
                continue
            label = _value(row, "label") or _local_name(iri)
            data: dict[str, Any] = {
                "rdf_types": [_value(row, "type")],
                "label_evidence": [label],
            }
            for payload_key, row_key in (
                ("mapped_class", "mappedClass"),
                ("mapped_definition", "mappedDefinition"),
                ("mapped_relation", "mappedRelation"),
                ("mapped_property", "mappedProperty"),
                ("table_mapping", "tableMapping"),
                ("column", "column"),
                ("table_name", "tableName"),
                ("enum_value", "enumValue"),
                ("business_meaning", "businessMeaning"),
                ("schema_source", "schemaSource"),
                ("semantic_value", "semanticValue"),
            ):
                value = _value(row, row_key)
                if value:
                    data[payload_key] = value
            for payload_key, row_key in (("column_mappings", "columnMappings"), ("join_path", "joinPath")):
                value = _value(row, row_key)
                if value:
                    try:
                        data[payload_key] = json.loads(value)
                    except json.JSONDecodeError:
                        data[payload_key] = value
            mapping_definition = _json_value(_value(row, "mappingDefinition"))
            if mapping_definition is not None:
                data["mapping_definition"] = mapping_definition
            match = _best_match(
                text,
                terms,
                [
                    ("label", label, 1000, "exact_label"),
                    ("identifier", iri, 600, "identifier"),
                    ("table_name", data.get("table_name"), 500, "table_name"),
                    ("enum_value", data.get("enum_value"), 450, "enum_value"),
                    ("description", data.get("business_meaning"), 450, "description"),
                ],
            )
            if resource_iris and iri in resource_iris:
                match = _neighborhood_match(1)
            if match:
                candidates.append(
                    {
                        "id": iri,
                        "kind": "mapping",
                        "ontology_id": scope.graph_to_ontology[graph],
                        "iri": iri,
                        "label": label,
                        "aliases": [],
                        "description": None,
                        "data": data,
                        "distance": 0,
                        "assertion_kind": "asserted",
                        "match": match,
                    }
                )
        return candidates

    def _metric_candidates(
        self, scope: SemanticQueryScope, text: str, terms: list[str],
        resource_iris: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Lexical candidates for MetricDefinition resources (label/comment)."""
        graph_values = " ".join(URIRef(graph).n3() for graph in scope.graph_iris)
        vocab = str(namespace_from_settings(self.settings).vocab)
        resource_values = (
            "VALUES ?metric { " + " ".join(URIRef(iri).n3() for iri in resource_iris) + " }"
            if resource_iris else ""
        )
        query = f"""# template: semantic-context-metrics
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX op: <{vocab}>
SELECT ?graph ?metric ?label ?comment ?grain ?timeField ?measure ?aggregation ?filters
       ?mappingDefinition
WHERE {{
  VALUES ?graph {{ {graph_values} }}
  {resource_values}
  GRAPH ?graph {{
    ?metric a op:MetricDefinition ;
            rdfs:label ?label .
    OPTIONAL {{ ?metric rdfs:comment ?comment . }}
    OPTIONAL {{ ?metric op:metricGrain ?grain . }}
    OPTIONAL {{ ?metric op:metricTimeField ?timeField . }}
    OPTIONAL {{ ?metric op:metricMeasure ?measure . }}
    OPTIONAL {{ ?metric op:metricAggregation ?aggregation . }}
    OPTIONAL {{ ?metric op:metricFilters ?filters . }}
    OPTIONAL {{ ?metric op:mappingDefinition ?mappingDefinition . }}
  }}
}}
ORDER BY ?graph ?metric
LIMIT 5000
"""
        candidates: list[dict[str, Any]] = []
        for row in self._producer_rows(query):
            graph = _value(row, "graph")
            iri = _value(row, "metric")
            if not graph or graph not in scope.graph_to_ontology or not iri:
                continue
            label = _value(row, "label") or _local_name(iri)
            data: dict[str, Any] = {
                "rdf_types": [f"{vocab}MetricDefinition"],
                "label_evidence": [label],
            }
            for payload_key, row_key in (
                ("time_field", "timeField"),
                ("measure", "measure"),
                ("aggregation", "aggregation"),
            ):
                value = _value(row, row_key)
                if value:
                    data[payload_key] = value
            grain_value = _value(row, "grain")
            if grain_value:
                try:
                    data["grain"] = json.loads(grain_value)
                except json.JSONDecodeError:
                    data["grain"] = grain_value
            filters_value = _value(row, "filters")
            if filters_value:
                try:
                    data["filters"] = json.loads(filters_value)
                except json.JSONDecodeError:
                    data["filters"] = filters_value
            mapping_definition = _json_value(_value(row, "mappingDefinition"))
            if mapping_definition is not None:
                data["mapping_definition"] = mapping_definition
            comment = _value(row, "comment")
            match = _best_match(
                text,
                terms,
                [
                    ("label", label, 1000, "exact_label"),
                    ("identifier", iri, 600, "identifier"),
                    ("description", comment, 450, "description"),
                ],
            )
            if resource_iris and iri in resource_iris:
                match = _neighborhood_match(1)
            if match:
                candidates.append(
                    {
                        "id": iri,
                        "kind": "metric",
                        "ontology_id": scope.graph_to_ontology[graph],
                        "iri": iri,
                        "label": label,
                        "aliases": [],
                        "description": comment,
                        "data": data,
                        "distance": 0,
                        "assertion_kind": "asserted",
                        "match": match,
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
        if not enabled or (limit is not None and limit <= 0):
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
            if limit is not None and len(result) >= limit:
                break
        return result


    def _expand_neighborhood(
        self, primary, scope, *, depth, limit, resource_types, assertion_types,
    ):
        anchors = set()
        for item in primary:
            if _is_statement(item):
                data = item.get("data") or {}
                if data.get("subject"):
                    anchors.add(data["subject"])
                if data.get("object_type") == "uri":
                    anchors.add(data["object"])
            elif item.get("iri"):
                anchors.add(item["iri"])
        frontier = sorted(anchors)
        seen_anchors = set(frontier)
        seen_items = set()
        related = []
        for distance in range(1, depth + 1):
            if not frontier or self._work_stopped:
                break
            next_frontier = set()
            for rows in self._read_chunks(lambda chunk_limit, after: (
                semantic_context_neighborhood_query(
                    self._selected_graphs(scope), frontier, chunk_limit,
                    self.operation_type, self.operation_predicates, after,
                )
            )):
                statements = [item for row in rows
                              if (item := self._statement_item(row, scope, distance=distance))]
                # Batch hydration of endpoint descriptions before authorization,
                # with no JSON strings converted into implicit traversal links.
                endpoint_seeds = {}
                for item in statements:
                    data = item["data"]
                    endpoints = [data["subject"]]
                    if data.get("object_type") == "uri":
                        endpoints.append(data["object"])
                    for iri in endpoints:
                        endpoint_seeds[(item["ontology_id"], iri)] = {
                            "id": iri, "iri": iri, "kind": "instance",
                            "target_kind": "resource", "ontology_id": item["ontology_id"],
                            "data": {}, "assertion_kind": item["assertion_kind"],
                        }
                self._hydrate_candidates(list(endpoint_seeds.values()), scope)
                for item in statements:
                    key = self._identity_key(item)
                    if key in seen_items:
                        continue
                    seen_items.add(key)
                    data = item["data"]
                    endpoints = [data["subject"]]
                    if data.get("object_type") == "uri":
                        endpoints.append(data["object"])
                    seeds = [endpoint_seeds[(item["ontology_id"], iri)] for iri in endpoints]
                    endpoint_resources = []
                    for iri, seed in zip(endpoints, seeds):
                        own_definitions = [
                            entry for entry in scope.ontologies
                            if self._description_cache[(entry.ontology_id, iri)].get("_own_rows")
                        ]
                        resource_items = [
                            self._resource_from_rows(
                                self._description_cache[(entry.ontology_id, iri)]["_own_rows"],
                                scope, iri,
                            ) for entry in own_definitions
                        ]
                        if not resource_items:
                            resource_items = [{
                                **seed, "label": _local_name(iri), "distance": distance,
                                "match": _neighborhood_match(distance),
                            }]
                        endpoint_resources.append([resource for resource in resource_items
                                                   if resource is not None])
                    if not self.access_view.filter_candidate(item) or any(
                        not self.access_view.filter_candidate(resource)
                        for resources in endpoint_resources for resource in resources
                    ):
                        continue
                    if not self._accept_work(item):
                        if self._work_stopped:
                            return related
                        continue
                    item["match"] = _neighborhood_match(distance)
                    if item["kind"] in resource_types:
                        related.append(item)
                    for iri, resource_items in zip(endpoints, endpoint_resources):
                        if iri not in seen_anchors:
                            next_frontier.add(iri)
                        for resource in resource_items:
                            if resource is None:
                                continue
                            resource["distance"] = distance
                            resource["match"] = _neighborhood_match(distance)
                            if self._accept_work(resource) and resource["kind"] in resource_types:
                                related.append(resource)
                            if self._work_stopped:
                                return related
                if self._work_stopped:
                    return related
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
                "graph_iri": graph,
                "subject": subject,
                "subject_label": subject_label,
                "predicate": predicate,
                "predicate_label": predicate_label,
                "object": object_value,
                "object_type": _binding_type(row, "object"),
                "object_datatype": _binding_attribute(row, "object", "datatype"),
                "object_language": _binding_attribute(row, "object", "xml:lang"),
                "object_label": _value(row, "objectLabel"),
            },
            "distance": distance,
            "assertion_kind": scope.graph_assertion_kinds.get(graph, "asserted"),
        }

    def _decorate(self, item: dict[str, Any], scope: SemanticQueryScope) -> dict[str, Any]:
        item = dict(item)
        item.pop("_target_label", None)
        item.pop("_lineage_target", None)
        target_kind = item.get("target_kind")
        if target_kind not in {"resource", "statement", "derived_reference"}:
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
        derived_state = None
        if item["assertion_kind"] != "asserted":
            ontology = next(
                entry for entry in scope.ontologies if entry.ontology_id == item["ontology_id"]
            )
            derived_kind = "reasoning"
            descriptor = ontology.derived_state.get(derived_kind, {})
            derived_state = {
                "kind": derived_kind,
                "status": descriptor.get("status"),
                "run_id": descriptor.get("run_id"),
            }

        item_warnings: list[dict[str, str]] = list(item.get("warnings") or [])
        if item.get("data", {}).get("annotation_read_diagnostics"):
            item_warnings.append({
                "code": "annotation_read_diagnostic",
                "message": "An existing annotation could not be read unambiguously; inspect its statement.",
            })
        if derived_state and derived_state.get("status") == "stale":
            item_warnings.append(
                {"code": "derived_result_stale", "message": "Derived result is stale."}
            )
        return {
            **item,
            "assertion_type": _assertion_filter_value(item["assertion_kind"]),
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


def _is_iri_anchor(value: Any) -> bool:
    """Return True for a single-expression query that is an exact IRI lookup."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if text != value or any(character.isspace() for character in text):
        return False
    parsed = urlsplit(text)
    return parsed.scheme.lower() in {"http", "https", "urn"} and bool(
        parsed.netloc or parsed.path
    )


def _anchor_candidate_from_rows(
    rows: list[dict[str, Any]],
    scope: "SemanticQueryScope",
    anchor_iri: str,
) -> dict[str, Any] | None:
    """Build one exact resource candidate from anchor neighborhood rows."""
    ontology_id: str | None = None
    labels: list[str] = []
    aliases: list[str] = []
    descriptions: list[str] = []
    types: set[str] = set()
    for row in rows:
        subject = _value(row, "subject")
        graph = _value(row, "graph")
        predicate = _value(row, "predicate")
        object_value = _value(row, "object")
        if graph in scope.graph_to_ontology and ontology_id is None:
            ontology_id = scope.graph_to_ontology[graph]
        if subject != anchor_iri:
            continue
        if predicate == "http://www.w3.org/2000/01/rdf-schema#label" and object_value:
            labels.append(object_value)
        elif predicate == "http://www.w3.org/2004/02/skos/core#altLabel" and object_value:
            aliases.append(object_value)
        elif predicate in {
            "http://www.w3.org/2000/01/rdf-schema#comment",
            "http://purl.org/dc/terms/description",
        } and object_value:
            descriptions.append(object_value)
        elif predicate == str(RDF.type) and object_value:
            types.add(object_value)
    if ontology_id is None:
        return None
    labels = sorted(set(labels))
    types = set(types)
    if types & _CLASS_TYPES:
        kind = "concept"
    elif types & _RELATION_TYPES:
        kind = "relation"
    elif any(str(value) for value in types if _local_name(str(value)) == "Operation"):
        kind = "operation"
    elif any(
        str(value)
        for value in types
        if _local_name(str(value)) in {"TableMapping", "JoinMapping", "EnumValueMeaning"}
    ):
        kind = "mapping"
    elif any(str(value) for value in types if _local_name(str(value)) == "MetricDefinition"):
        kind = "metric"
    else:
        kind = "instance"
    return {
        "id": anchor_iri,
        "kind": kind,
        "target_kind": "resource",
        "ontology_id": ontology_id,
        "iri": anchor_iri,
        "label": labels[0] if labels else _local_name(anchor_iri),
        "labels": labels,
        "aliases": aliases,
        "description": descriptions[0] if descriptions else None,
        "types": types,
        "data": {
            "rdf_types": sorted(types),
            "label_evidence": labels,
        },
        "distance": 0,
        "assertion_kind": scope.graph_assertion_kinds.get(
            next(
                (
                    graph_iri
                    for graph_iri, candidate_ontology in scope.graph_to_ontology.items()
                    if candidate_ontology == ontology_id
                ),
                "",
            ),
            "asserted",
        ),
        "match": {
            "score": 1000,
            "matched_terms": [anchor_iri],
            "matched_fields": ["iri"],
            "reasons": ["exact_iri"],
        },
    }


def _origin_for(item: Mapping[str, Any], data: Mapping[str, Any]) -> str:
    """Classify one public match without trusting presentation ``kind`` alone."""
    if item.get("target_kind") == "derived_reference" or data.get("derived_reference"):
        return "derived_reference"
    if {"subject", "predicate", "object"} <= set(data):
        predicate = data.get("predicate")
        if isinstance(predicate, str) and predicate in _TBOX_PREDICATES:
            return "tbox_statement"
        if item.get("assertion_kind") != "asserted":
            return "derived_statement"
        object_type = data.get("object_type")
        return "asserted_relation" if object_type in {"uri", "bnode"} else "asserted_literal"
    return "resource"


def _public_match(item: Mapping[str, Any]) -> dict[str, Any]:
    match = item.get("match") if isinstance(item.get("match"), Mapping) else {}
    result: dict[str, Any] = {}
    for key in ("score", "candidate_level", "lexical_score"):
        value = match.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result[key] = value
        elif isinstance(value, str):
            result[key] = value
    for key in ("matched_fields", "reasons"):
        value = match.get(key)
        if isinstance(value, list):
            result[key] = [str(item) for item in value]
    return result


def _public_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Project one decorated internal item to the stable consumer response.

    Redundant display fields and producer-only state are omitted; multi-expression
    support metadata, mapping evidence, and Protocol gate fields remain available.
    """
    data = dict(item.get("data") or {})
    public: dict[str, Any] = {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "origin": _origin_for(item, data),
        "label": item.get("label"),
        "iri": item.get("iri"),
        "ontology_id": item.get("ontology_id"),
        "assertion_kind": item.get("assertion_kind"),
        "data": data,
        "warnings": list(item.get("warnings") or []),
        "description": item.get("description"),
        "assertion_type": item.get("assertion_type"),
        "derived_state": item.get("derived_state"),
        "match": _public_match(item),
    }
    if item.get("target_kind") is not None:
        public["target_kind"] = item.get("target_kind")
    if item.get("mapping_evidence") is not None:
        public["mapping_evidence"] = item.get("mapping_evidence")
    return {key: value for key, value in public.items() if value is not None}


def _public_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    ontologies = scope.get("ontologies")
    compact_ontologies = []
    if isinstance(ontologies, list):
        for ontology in ontologies:
            if not isinstance(ontology, Mapping):
                continue
            compact_ontologies.append(
                {
                    "ontology_id": ontology.get("ontology_id"),
                    "workspace_version": ontology.get("workspace_version"),
                }
            )
    return {
        "project_id": scope.get("project_id"),
        "mode": scope.get("mode"),
        "status": scope.get("status"),
        "ontologies": compact_ontologies,
    }


def _public_recall(recall: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: recall.get(key)
        for key in ("mode", "match_status", "completeness")
        if recall.get(key) is not None
    }


def _context_rank(item: Mapping[str, Any]) -> int:
    return _CONTEXT_ORIGIN_RANK.get(
        _origin_for(item, item.get("data") if isinstance(item.get("data"), Mapping) else {}),
        2,
    )


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


def _json_value(value: str | None) -> Any:
    """Decode one JSON literal while retaining an invalid literal verbatim.

    Mapping annotations are authored as JSON, but direct RDF edits can leave
    malformed values behind.  Read paths preserve that value for the existing
    annotation diagnostics instead of inventing a projection or dropping it.
    """
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value


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
    kind = "reasoning"
    return ontology.derived_state.get(kind, {}).get("status") == "stale"


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item["ontology_id"], item["kind"], item["id"])
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
    key = (item["ontology_id"], item["kind"], item["id"])
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
        key = (item["ontology_id"], item["kind"], item["id"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _match_resume_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["ontology_id"],
        item["kind"],
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
    for index, item in enumerate(items):
        if _match_resume_key(item) == tuple(key):
            return items[index:]
    raise SemanticContextSnapshotChanged("Visible match continuation no longer exists")


def _resume_context_after_key(
    items: list[dict[str, Any]], key: tuple[Any, ...]
) -> list[dict[str, Any]]:
    if not key:
        return items
    for index, item in enumerate(items):
        if _context_resume_key(item) == tuple(key):
            return items[index:]
    raise SemanticContextSnapshotChanged("Visible context continuation no longer exists")


def _context_sort_key(
    item: dict[str, Any],
    scope: SemanticQueryScope,
    root_paths_by_item: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[Any, ...]:
    ontology_order = {entry.ontology_id: index for index, entry in enumerate(scope.ontologies)}
    identity = (item["ontology_id"], item["kind"], item["id"])
    paths = root_paths_by_item.get(identity, [])
    min_distance = min((int(path["graph_distance"]) for path in paths), default=99)
    return (
        min_distance,
        _context_rank(item),
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


def _normalize_semantic_roles(roles: list[str] | None) -> list[str] | None:
    if roles is None:
        return None
    if not isinstance(roles, list) or not roles or any(
        not isinstance(role, str) or not role.strip() for role in roles
    ):
        raise SemanticContextQueryError("semantic_roles must be a non-empty list of non-empty strings")
    return sorted({role.strip() for role in roles})


def _is_statement(item: Mapping[str, Any]) -> bool:
    return item.get("target_kind") == "statement" or {"subject", "predicate", "object"} <= set(
        item.get("data") or {}
    )


def _structured_mapping_references(
    item: Mapping[str, Any], vocab: str
) -> list[dict[str, str]]:
    """Return only the R4.0-010 closed set of nested IRI references.

    ``mapping_definition`` is intentionally treated by resource kind.  This
    prevents a future free-form annotation field, a table name, or an example
    value from silently becoming an executable-looking semantic edge.
    """
    data = item.get("data")
    if not isinstance(data, Mapping) or item.get("kind") not in {"mapping", "metric"}:
        return []
    resource_types = {
        _local_name(str(value)) for value in (data.get("rdf_types") or [])
        if isinstance(value, str)
    }
    references: list[dict[str, str]] = []

    def add(value: Any, path: str, predicate_name: str) -> None:
        if not isinstance(value, str) or not _is_reference_iri(value):
            return
        references.append({
            "target": value,
            "predicate": vocab + predicate_name,
            "field_path": f"data.{path}",
            "json_path": path,
        })

    def add_list_field(
        field: str, keys: tuple[str, ...], predicate_name: str,
    ) -> None:
        values = data.get(field)
        if not isinstance(values, list):
            return
        for index, entry in enumerate(values):
            if not isinstance(entry, Mapping):
                continue
            for key in keys:
                add(entry.get(key), f"{field}[{index}].{key}", predicate_name)

    mapping_definition = data.get("mapping_definition")
    if not isinstance(mapping_definition, Mapping):
        mapping_definition = {}

    if "TableMapping" in resource_types:
        add_list_field("column_mappings", ("property_iri",), "columnMappings")
        for index, entry in enumerate(mapping_definition.get("identifiers") or []):
            if isinstance(entry, Mapping):
                add(entry.get("property_iri"), f"mapping_definition.identifiers[{index}].property_iri", "mappingDefinition")
        for index, entry in enumerate(mapping_definition.get("field_meanings") or []):
            if isinstance(entry, Mapping):
                add(entry.get("conversion_rule_iri"), f"mapping_definition.field_meanings[{index}].conversion_rule_iri", "mappingDefinition")
    elif "JoinMapping" in resource_types:
        add_list_field(
            "join_path",
            ("from_mapping_iri", "to_mapping_iri"),
            "joinPath",
        )
        for index, entry in enumerate(mapping_definition.get("step_semantics") or []):
            if isinstance(entry, Mapping):
                add(entry.get("condition_rule_iri"), f"mapping_definition.step_semantics[{index}].condition_rule_iri", "mappingDefinition")
    elif "EnumValueMeaning" in resource_types:
        add(
            mapping_definition.get("conversion_rule_iri"),
            "mapping_definition.conversion_rule_iri",
            "mappingDefinition",
        )
    elif "MetricDefinition" in resource_types:
        contexts = mapping_definition.get("contexts")
        if isinstance(contexts, list):
            for context_index, context in enumerate(contexts):
                if not isinstance(context, Mapping):
                    continue
                prefix = f"mapping_definition.contexts[{context_index}]"
                add(context.get("base_mapping_iri"), f"{prefix}.base_mapping_iri", "mappingDefinition")
                for index, value in enumerate(context.get("join_mapping_iris") or []):
                    add(value, f"{prefix}.join_mapping_iris[{index}]", "mappingDefinition")
                for index, binding in enumerate(context.get("property_bindings") or []):
                    if not isinstance(binding, Mapping):
                        continue
                    add(binding.get("property_iri"), f"{prefix}.property_bindings[{index}].property_iri", "mappingDefinition")
                    add(binding.get("table_mapping_iri"), f"{prefix}.property_bindings[{index}].table_mapping_iri", "mappingDefinition")
                for index, identity in enumerate(context.get("counted_identity") or []):
                    if not isinstance(identity, Mapping):
                        continue
                    add(identity.get("table_mapping_iri"), f"{prefix}.counted_identity[{index}].table_mapping_iri", "mappingDefinition")
                for index, value in enumerate(context.get("conversion_rule_iris") or []):
                    add(value, f"{prefix}.conversion_rule_iris[{index}]", "mappingDefinition")
    return references


def _is_reference_iri(value: str) -> bool:
    parsed = urlsplit(value.strip())
    return parsed.scheme.lower() in {"http", "https", "urn"} and bool(
        parsed.netloc or parsed.path
    )


def _structured_reference_id(
    subject: str, predicate: str, field_path: str, target: str
) -> str:
    preimage = json.dumps(
        [subject, predicate, field_path, target],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "urn:ontology-platform:derived-reference:" + hashlib.sha256(
        preimage.encode("utf-8")
    ).hexdigest()


def _neighborhood_match(distance: int) -> dict[str, Any]:
    return {"score": max(1, 300 - distance * 50), "matched_terms": [],
            "matched_fields": ["neighborhood"], "reasons": ["relation_neighborhood"]}


def _json_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                     default=lambda item: sorted(item) if isinstance(item, set) else str(item))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _visible_digest(items: list[dict[str, Any]]) -> str:
    return _json_digest([
        {"item": _public_item(item), "annotation_values": item.get("_annotation_values", [])}
        for item in items
    ])


def _root_digest(items: list[dict[str, Any]]) -> str:
    return _json_digest([_match_resume_key(item) for item in items])


def _compact_related_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Keep ordinary semantic values while omitting ranking diagnostics."""
    return {key: value for key, value in row.items() if key != "match"}
