"""Neutral model-candidate normalization for the v5 role boundary."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .contracts import FrameworkError


def _item_id_for_path(candidate: Any, path: str) -> Any:
    """Return the candidate item identity addressed by an item JSON Pointer."""

    segments = path.split("/")
    if len(segments) < 3 or segments[1] != "items" or not segments[2].isdigit():
        return None
    items = candidate.get("items") if isinstance(candidate, Mapping) else None
    index = int(segments[2])
    if not isinstance(items, list) or index >= len(items):
        return None
    item = items[index]
    return item.get("item_id") if isinstance(item, Mapping) else None


def normalize_model_candidate(candidate: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Copy and validate a neutral candidate, filling only omitted neutral fields.

    ``relation_endpoints`` and ``shared_scope`` are optional at the role-delivery
    boundary only because the unified graph contract gives both fields explicit
    ``null`` meaning.  No business payload is inferred or rewritten.
    """

    if candidate is None:
        return None

    # Reuse the pure contract only when there is a candidate; normal v5 imports
    # and fields-only submissions must not initialize the legacy package.
    from modeling_team.staged_decisions import validate_unified_candidate

    normalized = deepcopy(candidate)
    if isinstance(normalized, dict) and isinstance(normalized.get("items"), list):
        for item in normalized["items"]:
            if not isinstance(item, dict):
                continue
            item.setdefault("relation_endpoints", None)
            item.setdefault("shared_scope", None)

    issues = validate_unified_candidate(normalized)
    if issues:
        raise FrameworkError(
            "model_candidate_invalid",
            errors=[
                {
                    "code": issue.reason_code,
                    "path": issue.artifact or "/",
                    "item_id": _item_id_for_path(normalized, issue.artifact),
                    "message": issue.detail,
                }
                for issue in issues
            ],
        )
    return normalized
