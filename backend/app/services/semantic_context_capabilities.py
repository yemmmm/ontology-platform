"""R1.2-007 capability discovery metadata for the Context Query contract.

This surface advertises the public limits and cursor support introduced by
R1.2-004 without creating a new endpoint. The MCP catalog route attaches the
metadata to its existing response; API/MCP documentation reference the same
constant.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.services.semantic_context_adaptive import ADAPTIVE_CONFIG, ADAPTIVE_VERSION
from app.services.semantic_context_cursor import ContextCursorCodec
from app.services.semantic_jev import RELATED_CONTEXT_CONFIG, RELATED_CONTEXT_VERSION


def context_query_capabilities(settings: Settings) -> dict[str, Any]:
    codec = ContextCursorCodec.from_settings(settings)
    return {
        "queries": {
            "min": settings.semantic_context_query_min_queries,
            "max": settings.semantic_context_query_max_queries,
            "item_char_limit": settings.semantic_context_query_item_char_limit,
            "aggregate_char_limit": settings.semantic_context_query_aggregate_char_limit,
        },
        "query": {
            "alias_for": "queries[0]",
            "char_limit": settings.semantic_context_query_item_char_limit,
        },
        "limit": {
            "default": settings.semantic_context_query_match_limit_default,
            "max": settings.semantic_context_query_match_limit_max,
        },
        "context_limit": {
            "default": settings.semantic_context_query_context_limit_default,
            "max": settings.semantic_context_query_context_limit_max,
            "min": 0,
            "controls": "returned_page_size",
        },
        "semantic_roles": {
            "optional": True, "match": "declared_exact_case_sensitive",
            "combine": "or", "applies_to": "primary_matches",
        },
        "result_scope": "authorized_query_scope",
        "expansion": {
            "strategies": ["adaptive", "fixed"],
            "default_strategy": "adaptive",
            "default_depth": {"adaptive": 3, "fixed": 1},
            "iri_default": {"strategy": "fixed", "depth": 1},
            "depth": {
                "min": 0,
                "max": min(settings.semantic_context_query_depth_max, 3),
                "explicit_is_upper_bound": True,
                "zero_disables_expansion": True,
            },
            "adaptive": {
                "version": ADAPTIVE_VERSION,
                "config": dict(ADAPTIVE_CONFIG),
            },
            "visible_work_budget": ADAPTIVE_CONFIG["work_budget"],
            "statuses": ["complete", "partial", "not_requested"],
            "complete_within": ["scope", "assertion_types", "depth", "current_match_page"],
            "completeness_scope": {
                "adaptive": "selected_subgraph",
                "fixed": "requested_depth",
                "applies_within": ["authorized_query_scope", "current_match_page"],
            },
            "business_completeness": False,
        },
        "context_order": {
            "default": "relevance", "choices": ["relevance", "graph_distance"],
            "iri_effective": "graph_distance", "version": RELATED_CONTEXT_VERSION,
            "config": dict(RELATED_CONTEXT_CONFIG),
            "ranking_scope": "current_match_page_bounded_context",
            "sort_before_paging": True, "additional_filtering": False,
            "statuses": ["applied", "degraded", "not_requested"],
            "frozen_strategies": ["fixed", "adaptive"],
        },
        "context_detail": {
            "rest_default": "full", "mcp_default": "compact",
            "applies_to": "related_context", "primary_matches": "full",
            "compact_omits": [],
            "omission_marker": "projection.omitted_fields",
        },
        "depth": {
            "default": 3,
            "max": min(settings.semantic_context_query_depth_max, 3),
            "default_by_strategy": {"adaptive": 3, "fixed": 1},
        },
        "cursors": codec.capabilities,
    }
