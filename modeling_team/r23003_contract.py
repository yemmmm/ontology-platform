"""Small, deterministic contracts shared by the R2.3-003 formal path.

The existing-scope contract deliberately keeps business semantics out of the
Runner.  This module contains only identity/pagination/recovery mechanics so
that the same checks can be used by the Protocol adapter and deterministic
tests without making the R2.3-005 create-only path aware of deletes.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlparse


R2_3_003_TARGET_CLASS = "ExplicitUnknown"
R2_3_003_TARGET_IDS = (
    "unknown-cross-release-output-meaning",
    "unknown-b-no-score-behavior",
)
R2_3_003_TARGET_SET = frozenset(R2_3_003_TARGET_IDS)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def deletion_policy() -> dict[str, Any]:
    """Return the immutable policy projection used by 003 tickets/candidates."""

    return {
        "mode": "resolve-and-delete-targets",
        "targets": [
            {"semantic_id": semantic_id, "expected_class": R2_3_003_TARGET_CLASS}
            for semantic_id in R2_3_003_TARGET_IDS
        ],
        "preserve_non_targets": True,
    }


def validate_deletion_policy(value: Any, *, requirement_id: str = "R2.3-003") -> dict[str, Any]:
    """Validate the structured unknown policy, failing closed on target drift."""

    if requirement_id != "R2.3-003":
        raise ValueError("deletion-aware policy is restricted to R2.3-003")
    if not isinstance(value, Mapping) or set(value) != {"mode", "targets", "preserve_non_targets"}:
        raise ValueError("R2.3-003 unknown policy fields drift")
    if value.get("mode") != "resolve-and-delete-targets" or value.get("preserve_non_targets") is not True:
        raise ValueError("R2.3-003 unknown policy mode/preserve flag is invalid")
    targets = value.get("targets")
    if not isinstance(targets, list) or len(targets) != len(R2_3_003_TARGET_IDS):
        raise ValueError("R2.3-003 unknown policy target count is invalid")
    normalized: list[dict[str, str]] = []
    for target in targets:
        if not isinstance(target, Mapping) or set(target) != {"semantic_id", "expected_class"}:
            raise ValueError("R2.3-003 unknown policy target fields drift")
        semantic_id = target.get("semantic_id")
        expected_class = target.get("expected_class")
        if not isinstance(semantic_id, str) or not semantic_id or "://" in semantic_id:
            raise ValueError("R2.3-003 target semantic ID is invalid")
        if expected_class != R2_3_003_TARGET_CLASS:
            raise ValueError("R2.3-003 target Class drifts")
        normalized.append({"semantic_id": semantic_id, "expected_class": expected_class})
    if tuple(item["semantic_id"] for item in normalized) != R2_3_003_TARGET_IDS:
        raise ValueError("R2.3-003 target IDs or order drift")
    return {
        "mode": "resolve-and-delete-targets",
        "targets": normalized,
        "preserve_non_targets": True,
    }


def validate_candidate_delete_declaration(value: Any) -> dict[str, str]:
    """Validate the Agent-owned delete intent (no IRI/triples/digest allowed)."""

    if not isinstance(value, Mapping) or set(value) != {"semantic_id", "expected_class", "delete_mode"}:
        raise ValueError("delete_existing_entity fields drift")
    semantic_id = value.get("semantic_id")
    expected_class = value.get("expected_class")
    if semantic_id not in R2_3_003_TARGET_SET or expected_class != R2_3_003_TARGET_CLASS:
        raise ValueError("delete_existing_entity target is not frozen")
    if value.get("delete_mode") != "full_live_impact":
        raise ValueError("delete_existing_entity delete_mode is invalid")
    return {
        "semantic_id": str(semantic_id),
        "expected_class": str(expected_class),
        "delete_mode": "full_live_impact",
    }


def validate_r23003_candidate_declarations(candidate: Any) -> tuple[dict[str, str], ...]:
    """Require exactly the frozen two delete declarations in a 003 candidate.

    This gate runs before live binding/impact reads.  A set comparison alone is
    insufficient: duplicate declarations, zero declarations, and an extra
    declaration can otherwise collapse to the same frozen ID set while still
    producing an unsafe number of delete commands.
    """

    if not isinstance(candidate, Mapping):
        raise ValueError("R2.3-003 candidate is invalid")
    items = candidate.get("items")
    if not isinstance(items, list):
        raise ValueError("R2.3-003 candidate items are invalid")
    declarations: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("R2.3-003 candidate item is invalid")
        if item.get("item_kind") != "delete_existing_entity":
            continue
        try:
            declarations.append(validate_candidate_delete_declaration(item.get("semantic")))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    if len(declarations) != len(R2_3_003_TARGET_IDS):
        raise ValueError("R2.3-003 candidate must contain exactly two delete declarations")
    ids = tuple(item["semantic_id"] for item in declarations)
    if len(set(ids)) != len(ids) or set(ids) != R2_3_003_TARGET_SET:
        raise ValueError("R2.3-003 candidate delete declarations drift")
    if ids != R2_3_003_TARGET_IDS:
        raise ValueError("R2.3-003 candidate delete declarations must be frozen ordered")
    return tuple(declarations)


def validate_canonical_entity_projection(
    value: Any,
    *,
    project_id: str,
    ontology_id: str,
    model_revision: int,
) -> dict[str, str]:
    """Validate the backend's explicit entity identity projection.

    Protocol must consume these fields as opaque values.  In particular, it may
    not recover ``semantic_id`` or a Class by splitting an IRI.
    """

    required = {
        "semantic_id",
        "entity_iri",
        "class_semantic_id",
        "class_iri",
        "project_id",
        "ontology_id",
        "model_revision",
    }
    if not isinstance(value, Mapping) or not required.issubset(value):
        raise ValueError("canonical entity projection fields are incomplete")
    result = {field: value.get(field) for field in required}
    for field in ("semantic_id", "class_semantic_id"):
        item = result[field]
        if not isinstance(item, str) or not item.strip() or "://" in item:
            raise ValueError(f"canonical entity {field} is invalid")
    for field in ("entity_iri", "class_iri"):
        item = result[field]
        parsed = urlparse(item) if isinstance(item, str) else None
        if parsed is None or not parsed.scheme or not parsed.netloc:
            raise ValueError(f"canonical entity {field} is invalid")
    for field, expected in (
        ("project_id", project_id),
        ("ontology_id", ontology_id),
        ("model_revision", model_revision),
    ):
        if result[field] != expected or (type(result[field]) is not int if field == "model_revision" else not isinstance(result[field], str)):
            raise ValueError(f"canonical entity {field} drifts")
    return {field: result[field] for field in required}


def _cursor_encode(value: Mapping[str, Any]) -> str:
    raw = base64.urlsafe_b64encode(_canonical_bytes(value)).decode("ascii").rstrip("=")
    return f"esc1.{raw}"


def _cursor_decode(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.startswith("esc1."):
        raise ValueError("entity statement cursor is invalid")
    raw = value[5:]
    try:
        padded = raw + "=" * (-len(raw) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("entity statement cursor is invalid") from exc
    if not isinstance(decoded, dict):
        raise ValueError("entity statement cursor is invalid")
    return decoded


def get_entity_statement_context(
    statements: Iterable[Mapping[str, Any]],
    *,
    project_id: str,
    ontology_id: str,
    entity_iri: str,
    model_revision: int,
    page_size: int = 100,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Build one complete, opaque-cursor entity statement page.

    ``statements`` is an already scope-filtered backend response.  The helper
    still rejects duplicate canonical statements and snapshots the complete
    sequence before slicing, which prevents a caller from treating a truncated
    page as a complete delete impact read.
    """

    if not all(isinstance(item, str) and item for item in (project_id, ontology_id)) or type(model_revision) is not int or model_revision < 0:
        raise ValueError("entity statement scope is invalid")
    parsed = urlparse(entity_iri) if isinstance(entity_iri, str) else None
    if parsed is None or not parsed.scheme or not parsed.netloc:
        raise ValueError("entity statement entity IRI is invalid")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 0 < page_size <= 1000:
        raise ValueError("entity statement page_size is invalid")
    supplied = list(statements)
    if any(not isinstance(item, Mapping) for item in supplied):
        raise ValueError("entity statement projection contains a malformed statement")
    normalized = [dict(item) for item in supplied]
    encoded = [_canonical_bytes(item) for item in normalized]
    if len(set(encoded)) != len(encoded):
        raise ValueError("entity statement projection contains duplicate statements")
    ordered = [json.loads(payload.decode("utf-8")) for payload in sorted(encoded)]
    snapshot_digest = canonical_digest(ordered)
    offset = 0
    if cursor is not None:
        token = _cursor_decode(cursor)
        expected = {
            "project_id": project_id,
            "ontology_id": ontology_id,
            "entity_iri": entity_iri,
            "model_revision": model_revision,
            "snapshot_digest": snapshot_digest,
        }
        for key, value in expected.items():
            if token.get(key) != value:
                raise ValueError("entity statement cursor scope or snapshot drifted")
        offset = token.get("offset")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("entity statement cursor offset is invalid")
    if offset > len(ordered):
        raise ValueError("entity statement cursor is beyond snapshot")
    page = ordered[offset : offset + page_size]
    next_offset = offset + len(page)
    complete = next_offset >= len(ordered)
    next_cursor = None
    if not complete:
        next_cursor = _cursor_encode(
            {
                "project_id": project_id,
                "ontology_id": ontology_id,
                "entity_iri": entity_iri,
                "model_revision": model_revision,
                "snapshot_digest": snapshot_digest,
                "offset": next_offset,
            }
        )
    return {
        "project_id": project_id,
        "ontology_id": ontology_id,
        "entity_iri": entity_iri,
        "model_revision": model_revision,
        "statements": page,
        "page_digest": canonical_digest(page),
        "snapshot_digest": snapshot_digest,
        "next_cursor": next_cursor,
        "complete": complete,
    }


def build_delete_impact_receipt(
    pages: Iterable[Mapping[str, Any]],
    *,
    target_semantic_id: str,
    candidate_digest: str,
    project_id: str,
    ontology_id: str,
    model_revision: int,
) -> dict[str, Any]:
    """Freeze a complete page chain as tool-owned delete impact evidence."""

    raw_pages = list(pages)
    if not raw_pages or not all(isinstance(page, Mapping) for page in raw_pages):
        raise ValueError("delete impact page chain is empty")
    page_list = [dict(page) for page in raw_pages]
    entity_iri = page_list[0].get("entity_iri")
    if not isinstance(entity_iri, str) or not entity_iri:
        raise ValueError("delete impact entity identity is missing")
    for page in page_list:
        if (
            page.get("project_id") != project_id
            or page.get("ontology_id") != ontology_id
            or page.get("model_revision") != model_revision
            or page.get("entity_iri") != entity_iri
        ):
            raise ValueError("delete impact scope/entity drifts")
    # A paginated chain is complete only when every intermediate page advertises
    # a continuation and the final page alone advertises completion.  Requiring
    # ``complete`` on every page would incorrectly reject a valid >1 page read,
    # while accepting a truncated chain would make delete recovery unsafe.
    if page_list[-1].get("complete") is not True:
        raise ValueError("delete impact page chain is incomplete")
    if any(page.get("complete") is True or not page.get("next_cursor") for page in page_list[:-1]):
        raise ValueError("delete impact page chain is incomplete")
    snapshots = {page.get("snapshot_digest") for page in page_list}
    if len(snapshots) != 1 or not isinstance(next(iter(snapshots)), str) or not next(iter(snapshots)):
        raise ValueError("delete impact snapshot drifts")
    previous_next: str | None = None
    statements: list[dict[str, Any]] = []
    computed_page_digests: list[str] = []
    for index, page in enumerate(page_list):
        if index == 0:
            if page.get("cursor") not in (None, ""):
                raise ValueError("delete impact page chain starts at a non-root cursor")
        elif page.get("cursor") != previous_next:
            raise ValueError("delete impact page cursor chain is out of order")
        values = page.get("statements")
        if not isinstance(values, list):
            raise ValueError("delete impact statements are invalid")
        if any(not isinstance(item, Mapping) for item in values):
            raise ValueError("delete impact statements are malformed")
        expected_page_digest = canonical_digest(values)
        if page.get("page_digest") != expected_page_digest:
            raise ValueError("delete impact page digest is invalid")
        computed_page_digests.append(expected_page_digest)
        statements.extend(dict(item) for item in values)
        previous_next = page.get("next_cursor")
    if page_list[-1].get("next_cursor") not in (None, ""):
        raise ValueError("delete impact terminal page has a cursor")
    encoded = [_canonical_bytes(item) for item in statements]
    if len(set(encoded)) != len(encoded):
        raise ValueError("delete impact page chain repeats a statement")
    statements = [json.loads(item.decode("utf-8")) for item in sorted(encoded)]
    if next(iter(snapshots)) != canonical_digest(statements):
        raise ValueError("delete impact snapshot digest is invalid")
    receipt = {
        "schema_version": "r2-3-003-delete-impact/v1",
        "target_semantic_id": target_semantic_id,
        "project_id": project_id,
        "ontology_id": ontology_id,
        "model_revision": model_revision,
        "candidate_digest": candidate_digest,
        "entity_iri": entity_iri,
        "snapshot_digest": next(iter(snapshots)),
        "page_digests": computed_page_digests,
        "statements": statements,
        "complete": True,
    }
    if not isinstance(receipt["snapshot_digest"], str) or not receipt["snapshot_digest"]:
        raise ValueError("delete impact snapshot digest is missing")
    receipt["receipt_digest"] = canonical_digest(receipt)
    return receipt


def classify_delete_only_recovery(
    receipt: Mapping[str, Any],
    after: Mapping[str, Any],
) -> str:
    """Classify receipt-bound delete-only state for safe mechanical recovery."""

    if not isinstance(receipt, Mapping) or not isinstance(after, Mapping):
        return "partial_or_drifted"
    if receipt.get("complete") is not True or after.get("complete") is not True:
        return "partial_or_drifted"
    before_statements = receipt.get("statements")
    after_statements = after.get("statements")
    before_targets = set(receipt.get("target_semantic_ids", []))
    if not before_targets:
        target = receipt.get("target_semantic_id")
        if isinstance(target, str):
            before_targets = {target}
    after_targets = set(after.get("target_semantic_ids", []))
    if not isinstance(before_statements, list) or not isinstance(after_statements, list):
        return "partial_or_drifted"
    if any(not isinstance(item, Mapping) for item in (*before_statements, *after_statements)):
        return "partial_or_drifted"
    before_bytes = {_canonical_bytes(item) for item in before_statements}
    after_bytes = {_canonical_bytes(item) for item in after_statements}
    new_edge = not after_bytes.issubset(before_bytes)
    if not new_edge and after_targets == before_targets and after_bytes == before_bytes:
        return "not_applied"
    if not after_targets and not after_bytes:
        return "applied"
    return "partial_or_drifted"


__all__ = [
    "R2_3_003_TARGET_CLASS",
    "R2_3_003_TARGET_IDS",
    "R2_3_003_TARGET_SET",
    "build_delete_impact_receipt",
    "canonical_digest",
    "classify_delete_only_recovery",
    "deletion_policy",
    "get_entity_statement_context",
    "validate_candidate_delete_declaration",
    "validate_r23003_candidate_declarations",
    "validate_canonical_entity_projection",
    "validate_deletion_policy",
]
