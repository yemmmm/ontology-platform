"""R1.2-007 capability discovery metadata for the Context Query contract.

This surface advertises the public limits and cursor support introduced by
R1.2-004 without creating a new endpoint. The MCP catalog route attaches the
metadata to its existing response; API/MCP documentation reference the same
constant.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.services.semantic_context_cursor import ContextCursorCodec


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
        },
        "depth": {
            "default": settings.semantic_context_query_depth_default,
            "max": settings.semantic_context_query_depth_max,
        },
        "cursors": codec.capabilities,
    }
