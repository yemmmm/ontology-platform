"""Protocol-only deterministic mechanics contract for the v2 runtime asset."""

from __future__ import annotations

import json
import hashlib
import base64
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

try:
    from .r23003_contract import (
        R2_3_003_TARGET_CLASS,
        R2_3_003_TARGET_SET,
        build_delete_impact_receipt,
        classify_delete_only_recovery,
        get_entity_statement_context,
        validate_candidate_delete_declaration,
        validate_r23003_candidate_declarations,
        validate_canonical_entity_projection,
    )
except ImportError:  # pragma: no cover - stdio/staged facade has no package sibling
    try:
        from r23003_contract import (  # type: ignore[no-redef]
            R2_3_003_TARGET_CLASS,
            R2_3_003_TARGET_SET,
            build_delete_impact_receipt,
            classify_delete_only_recovery,
            get_entity_statement_context,
            validate_candidate_delete_declaration,
            validate_r23003_candidate_declarations,
            validate_canonical_entity_projection,
        )
    except ImportError:  # staged Protocol asset intentionally contains no package files
        R2_3_003_TARGET_CLASS = "ExplicitUnknown"
        R2_3_003_TARGET_IDS = (
            "unknown-cross-release-output-meaning",
            "unknown-b-no-score-behavior",
        )
        R2_3_003_TARGET_SET = frozenset(R2_3_003_TARGET_IDS)

        def _003_bytes(value: Any) -> bytes:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

        def _003_digest(value: Any) -> str:
            return hashlib.sha256(_003_bytes(value)).hexdigest()

        def validate_candidate_delete_declaration(value: Any) -> dict[str, str]:
            if not isinstance(value, Mapping) or set(value) != {"semantic_id", "expected_class", "delete_mode"}:
                raise ValueError("delete_existing_entity fields drift")
            if value.get("semantic_id") not in R2_3_003_TARGET_SET or value.get("expected_class") != R2_3_003_TARGET_CLASS:
                raise ValueError("delete_existing_entity target is not frozen")
            if value.get("delete_mode") != "full_live_impact":
                raise ValueError("delete_existing_entity delete_mode is invalid")
            return {
                "semantic_id": str(value["semantic_id"]),
                "expected_class": R2_3_003_TARGET_CLASS,
                "delete_mode": "full_live_impact",
            }

        def validate_r23003_candidate_declarations(candidate: Any) -> tuple[dict[str, str], ...]:
            if not isinstance(candidate, Mapping) or not isinstance(candidate.get("items"), list):
                raise ValueError("R2.3-003 candidate items are invalid")
            declarations = [
                validate_candidate_delete_declaration(item.get("semantic"))
                for item in candidate["items"]
                if isinstance(item, Mapping) and item.get("item_kind") == "delete_existing_entity"
            ]
            if len(declarations) != 2:
                raise ValueError("R2.3-003 candidate must contain exactly two delete declarations")
            ids = tuple(item["semantic_id"] for item in declarations)
            if ids != tuple(R2_3_003_TARGET_IDS) or len(set(ids)) != 2:
                raise ValueError("R2.3-003 candidate delete declarations drift")
            return tuple(declarations)

        def validate_canonical_entity_projection(
            value: Any,
            *,
            project_id: str,
            ontology_id: str,
            workspace_version: str,
        ) -> dict[str, str]:
            required = {
                "semantic_id", "entity_iri", "class_semantic_id", "class_iri",
                "project_id", "ontology_id", "workspace_version",
            }
            if not isinstance(value, Mapping) or not required.issubset(value):
                raise ValueError("canonical entity projection fields are incomplete")
            for field in ("semantic_id", "class_semantic_id"):
                item = value.get(field)
                if not isinstance(item, str) or not item.strip() or "://" in item:
                    raise ValueError(f"canonical entity {field} is invalid")
            for field in ("entity_iri", "class_iri"):
                parsed = urlparse(value.get(field)) if isinstance(value.get(field), str) else None
                if parsed is None or not parsed.scheme or not parsed.netloc:
                    raise ValueError(f"canonical entity {field} is invalid")
            for field, expected in (
                ("project_id", project_id), ("ontology_id", ontology_id),
                ("workspace_version", workspace_version),
            ):
                if value.get(field) != expected:
                    raise ValueError(f"canonical entity {field} drifts")
            return {field: str(value[field]) for field in required}

        def _003_cursor_encode(value: Mapping[str, Any]) -> str:
            return "esc1." + base64.urlsafe_b64encode(_003_bytes(value)).decode("ascii").rstrip("=")

        def _003_cursor_decode(value: Any) -> dict[str, Any]:
            if not isinstance(value, str) or not value.startswith("esc1."):
                raise ValueError("entity statement cursor is invalid")
            try:
                padded = value[5:] + "=" * (-len(value[5:]) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError("entity statement cursor is invalid") from exc
            if not isinstance(decoded, dict):
                raise ValueError("entity statement cursor is invalid")
            return decoded

        def get_entity_statement_context(
            statements: Any,
            *,
            project_id: str,
            ontology_id: str,
            entity_iri: str,
            workspace_version: str,
            page_size: int = 100,
            cursor: str | None = None,
        ) -> dict[str, Any]:
            parsed = urlparse(entity_iri) if isinstance(entity_iri, str) else None
            if (
                parsed is None
                or not parsed.scheme
                or not parsed.netloc
                or isinstance(page_size, bool)
                or not isinstance(page_size, int)
                or not 0 < page_size <= 1000
            ):
                raise ValueError("entity statement scope/page is invalid")
            raw_rows = list(statements)
            if not all(isinstance(item, Mapping) for item in raw_rows):
                raise ValueError("entity statement projection contains a malformed statement")
            rows = [dict(item) for item in raw_rows]
            encoded = [_003_bytes(item) for item in rows]
            if len(set(encoded)) != len(encoded):
                raise ValueError("entity statement projection contains duplicate statements")
            ordered = [json.loads(item.decode("utf-8")) for item in sorted(encoded)]
            snapshot_digest = _003_digest(ordered)
            offset = 0
            if cursor is not None:
                token = _003_cursor_decode(cursor)
                for key, expected in {
                    "project_id": project_id, "ontology_id": ontology_id, "entity_iri": entity_iri,
                    "workspace_version": workspace_version, "snapshot_digest": snapshot_digest,
                }.items():
                    if token.get(key) != expected:
                        raise ValueError("entity statement cursor scope or snapshot drifted")
                offset = token.get("offset")
                if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
                    raise ValueError("entity statement cursor offset is invalid")
            if offset > len(ordered):
                raise ValueError("entity statement cursor is beyond snapshot")
            page = ordered[offset:offset + page_size]
            next_offset = offset + len(page)
            complete = next_offset >= len(ordered)
            next_cursor = None if complete else _003_cursor_encode({
                "project_id": project_id, "ontology_id": ontology_id, "entity_iri": entity_iri,
                "workspace_version": workspace_version, "snapshot_digest": snapshot_digest,
                "offset": next_offset,
            })
            return {
                "project_id": project_id, "ontology_id": ontology_id, "entity_iri": entity_iri,
                "workspace_version": workspace_version, "statements": page,
                "page_digest": _003_digest(page), "snapshot_digest": snapshot_digest,
                "next_cursor": next_cursor, "complete": complete,
            }

        def build_delete_impact_receipt(
            pages: Any,
            *,
            target_semantic_id: str,
            candidate_digest: str,
            project_id: str,
            ontology_id: str,
            workspace_version: str,
        ) -> dict[str, Any]:
            raw_pages = list(pages)
            if not raw_pages or not all(isinstance(page, Mapping) for page in raw_pages):
                raise ValueError("delete impact page chain is empty")
            page_list = [dict(page) for page in raw_pages]
            if not page_list or page_list[-1].get("complete") is not True:
                raise ValueError("delete impact page chain is incomplete")
            if any(page.get("complete") is True or not page.get("next_cursor") for page in page_list[:-1]):
                raise ValueError("delete impact page chain is incomplete")
            entity_iri = page_list[0].get("entity_iri")
            if not isinstance(entity_iri, str) or not entity_iri:
                raise ValueError("delete impact entity identity is missing")
            snapshots = {page.get("snapshot_digest") for page in page_list}
            if len(snapshots) != 1 or not isinstance(next(iter(snapshots)), str):
                raise ValueError("delete impact snapshot drifts")
            rows: list[dict[str, Any]] = []
            previous_next = None
            page_digests = []
            for index, page in enumerate(page_list):
                if index == 0:
                    if page.get("cursor") not in (None, ""):
                        raise ValueError("delete impact page chain starts at a non-root cursor")
                elif page.get("cursor") != previous_next:
                    raise ValueError("delete impact page cursor chain is out of order")
                if (
                    page.get("project_id") != project_id
                    or page.get("ontology_id") != ontology_id
                    or page.get("workspace_version") != workspace_version
                    or page.get("entity_iri") != entity_iri
                ):
                    raise ValueError("delete impact scope/entity drifts")
                values = page.get("statements")
                if not isinstance(values, list):
                    raise ValueError("delete impact statements are invalid")
                if any(not isinstance(item, Mapping) for item in values):
                    raise ValueError("delete impact statements are malformed")
                digest = _003_digest(values)
                if page.get("page_digest") != digest:
                    raise ValueError("delete impact page digest is invalid")
                page_digests.append(digest)
                rows.extend(dict(item) for item in values)
                previous_next = page.get("next_cursor")
            if page_list[-1].get("next_cursor") not in (None, ""):
                raise ValueError("delete impact terminal page has a cursor")
            encoded = [_003_bytes(item) for item in rows]
            if len(set(encoded)) != len(encoded):
                raise ValueError("delete impact page chain repeats a statement")
            ordered = [json.loads(item.decode("utf-8")) for item in sorted(encoded)]
            if next(iter(snapshots)) != _003_digest(ordered):
                raise ValueError("delete impact snapshot digest is invalid")
            receipt = {
                "schema_version": "r2-3-003-delete-impact/v1", "target_semantic_id": target_semantic_id,
                "project_id": project_id, "ontology_id": ontology_id, "workspace_version": workspace_version,
                "candidate_digest": candidate_digest, "entity_iri": entity_iri,
                "snapshot_digest": next(iter(snapshots)), "page_digests": page_digests, "statements": ordered,
                "complete": True,
            }
            if not isinstance(receipt["snapshot_digest"], str) or not receipt["snapshot_digest"]:
                raise ValueError("delete impact snapshot digest is missing")
            receipt["receipt_digest"] = _003_digest(receipt)
            return receipt

        def classify_delete_only_recovery(receipt: Mapping[str, Any], after: Mapping[str, Any]) -> str:
            if not isinstance(receipt, Mapping) or not isinstance(after, Mapping):
                return "partial_or_drifted"
            if receipt.get("complete") is not True or after.get("complete") is not True:
                return "partial_or_drifted"
            before = receipt.get("statements")
            observed = after.get("statements")
            if not isinstance(before, list) or not isinstance(observed, list):
                return "partial_or_drifted"
            before_bytes = {_003_bytes(item) for item in before if isinstance(item, Mapping)}
            after_bytes = {_003_bytes(item) for item in observed if isinstance(item, Mapping)}
            before_targets = set(receipt.get("target_semantic_ids", [])) or {receipt.get("target_semantic_id")}
            after_targets = set(after.get("target_semantic_ids", []))
            if after_bytes.issubset(before_bytes) and after_bytes == before_bytes and after_targets == before_targets:
                return "not_applied"
            if not after_targets and not after_bytes:
                return "applied"
            return "partial_or_drifted"

try:
    from .candidate_progress import (
        FormalCandidateError,
        formal_candidate_digests,
        validate_formal_candidate,
    )
except ImportError:  # pragma: no cover - stdio facade imports this module directly
    try:
        from candidate_progress import (  # type: ignore[no-redef]
            FormalCandidateError,
            formal_candidate_digests,
            validate_formal_candidate,
        )
    except ImportError:  # staged Protocol asset has no package siblings
        class FormalCandidateError(ValueError):
            pass

        def validate_formal_candidate(candidate: Any) -> dict[str, Any]:
            required = {
                "candidate_kind",
                "candidate_revision",
                "scope",
                "constraints",
                "items",
            }
            if not isinstance(candidate, dict) or set(candidate) != required:
                raise FormalCandidateError("formal candidate fields are not exact")
            if candidate.get("candidate_kind") != "platform-neutral-candidate-v2":
                raise FormalCandidateError("formal candidate kind is not platform-neutral-candidate-v2")
            revision = candidate.get("candidate_revision")
            if isinstance(revision, bool) or not (
                (isinstance(revision, int) and revision > 0)
                or (isinstance(revision, str) and bool(revision.strip()))
            ):
                raise FormalCandidateError("formal candidate revision is invalid")
            scope = candidate.get("scope")
            if not (
                (isinstance(scope, str) and bool(scope.strip()))
                or (isinstance(scope, dict) and bool(scope))
            ):
                raise FormalCandidateError("formal candidate scope is not bound")
            constraints = candidate.get("constraints")
            if not isinstance(constraints, list) or any(
                not isinstance(item, str) or not item.strip() for item in constraints
            ):
                raise FormalCandidateError("formal candidate constraints must be a string list")
            items = candidate.get("items")
            if not isinstance(items, list) or not items:
                raise FormalCandidateError("formal candidate items are empty")
            ids: set[str] = set()
            for item in items:
                if not isinstance(item, dict):
                    raise FormalCandidateError("formal candidate item must be an object")
                if any(
                    not isinstance(item.get(field), str) or not item[field].strip()
                    for field in ("item_id", "item_kind")
                ):
                    raise FormalCandidateError("formal candidate item identity is not bound")
                if item["item_id"] in ids:
                    raise FormalCandidateError("formal candidate item IDs are duplicated")
                ids.add(item["item_id"])
                if "semantic" not in item or item["semantic"] is None:
                    raise FormalCandidateError("formal candidate semantic payload is missing")
            return json.loads(json.dumps(candidate, ensure_ascii=False))

        def formal_candidate_digests(candidate: Any) -> tuple[str, str]:
            value = validate_formal_candidate(candidate)
            semantic = {
                key: value[key]
                for key in (
                    "candidate_kind",
                    "candidate_revision",
                    "scope",
                    "constraints",
                    "items",
                )
            }
            def encode(item: Any) -> bytes:
                return json.dumps(
                    item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            return hashlib.sha256(encode(value)).hexdigest(), hashlib.sha256(encode(semantic)).hexdigest()


def protocol_mechanics_contract(run_id: str) -> dict[str, Any]:
    """Return the R2.2 L3 semantic-free Protocol mechanics contract unchanged in meaning."""
    return {
        "contract_version": 1,
        "run_id": run_id,
        "owner": "protocol_only_deterministic_helper",
        "owns": [
            "stable_ids",
            "canonical_json_and_hashes",
            "atomic_publication",
            "public_request_schema_validation",
            "immutable_batch_freeze_and_replay",
            "workspace_revision_and_lease_state",
            "lease_renewal_and_checkpoint_bodies",
            "response_parsing",
            "cross_batch_platform_identity_binding",
        ],
        "forbidden": [
            "modeling_item_synthesis",
            "item_reordering",
            "semantic_repair",
            "query_authoring",
        ],
        "build_session_lifecycle": {
            "ordered_steps": [
                "create_session_without_nested_checkpoint",
                "save_initial_checkpoint",
                "acquire_lease_using_initial_checkpoint_revision",
                "semantic_batch_application_validation_reasoning_and_query",
                "refresh_session_before_final_checkpoint",
                "save_final_checkpoint",
                "complete_using_final_checkpoint_revision",
                "reread_completed_session",
            ],
            "create_session": {
                "tool": "create_build_session",
                "initial_checkpoint": "omit_or_null",
                "forbidden_nested_fields": ["run_id", "phase", "workspace", "checkpoint"],
                "receipt_bindings": {
                    "session_id": "create_receipt.session.id",
                    "revision": "create_receipt.session.revision",
                },
            },
            "initial_checkpoint": {
                "tool": "save_build_checkpoint",
                "fields": {
                    "session_id": "create_receipt.session.id",
                    "client_checkpoint_id": f"{run_id}-initial",
                    "expected_revision": "create_receipt.session.revision",
                    "phase": "modeling",
                    "current_step": "schema_and_instance_modeling",
                    "next_step": "validation_and_reasoning",
                    "ontology_id": "scope.ontology_id",
                    "blockers": [],
                },
                "receipt_binding": "initial_checkpoint_receipt.session.revision",
            },
            "lease": {
                "tool": "acquire_ontology_lease",
                "fields": {
                    "session_id": "create_receipt.session.id",
                    "ontology_id": "scope.ontology_id",
                    "client_request_id": f"{run_id}-lease",
                    "expected_session_revision": "initial_checkpoint_receipt.session.revision",
                    "rotate_token": False,
                },
            },
            "pre_final_session_refresh": {
                "after": [
                    "semantic_batch_application",
                    "semantic_validation",
                    "semantic_reasoning",
                    "governed_query",
                ],
                "tool": "get_build_session",
                "fields": {"session_id": "create_receipt.session.id"},
                "receipt_binding": "get_build_session_receipt.session.revision",
            },
            "final_checkpoint": {
                "after": [
                    "get_build_session_receipt.session.revision",
                ],
                "tool": "save_build_checkpoint",
                "fields": {
                    "session_id": "create_receipt.session.id",
                    "client_checkpoint_id": f"{run_id}-final",
                    "expected_revision": "get_build_session_receipt.session.revision",
                    "phase": "handoff",
                    "current_step": "semantic_acceptance_complete",
                    "next_step": "delivery_handoff",
                    "ontology_id": "scope.ontology_id",
                    "blockers": [],
                },
                "receipt_binding": "final_checkpoint_receipt.session.revision",
            },
            "complete_session": {
                "tool": "complete_build_session",
                "fields": {
                    "session_id": "create_receipt.session.id",
                    "client_request_id": f"{run_id}-complete",
                    "expected_revision": "final_checkpoint_receipt.session.revision",
                    "summary": "semantic acceptance complete",
                    "unresolved_items": [],
                },
                "reread": {
                    "tool": "get_build_session",
                    "fields": {"session_id": "create_receipt.session.id"},
                    "required_status": "completed",
                    "receipt_binding": "completed_session_receipt.session.revision",
                },
            },
        },
    }


def protocol_mechanics_contract_bytes(run_id: str) -> bytes:
    """Encode the contract once for staging and strict runtime verification."""
    return json.dumps(
        protocol_mechanics_contract(run_id),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


class ProtocolRetrievalFallbackError(ValueError):
    """The Protocol-only fallback cannot prove complete, scoped retrieval."""


_CANDIDATE_SCHEMA_VERSION = "candidate-required-assertions/v1"
_CANDIDATE_ITEM_FIELDS = (
    "graph_role",
    "subject",
    "predicate",
    "object",
    "object_kind",
    "object_datatype",
    "object_language",
)
_MATERIALIZED_QUAD_FIELDS = (
    "graph_role",
    "source_graph_iri",
    "subject",
    "predicate",
    "object",
    "object_kind",
    "object_datatype",
    "object_language",
)
_CANDIDATE_BINDING_FIELDS = (
    "schema_version",
    "candidate_revision",
    "delivery_id",
    "reply_chain",
    "semantic_digest",
)
_CANDIDATE_FIELDS = (
    *_CANDIDATE_BINDING_FIELDS,
    "candidate_digest",
    "items",
    "materialized_digest",
    "materialized_quads",
)
_LINEAGE_FIELDS = (
    *_CANDIDATE_BINDING_FIELDS,
    "candidate_digest",
    "materialized_digest",
    "max_depth",
    "records",
)
_LINEAGE_RECORD_FIELDS = ("fact_id", "quad", "response")

# R2.3 native proof v2 is intentionally a different envelope from the
# retained v1 proof.  Keeping the key set in one place makes wrapper dispatch
# fail closed for both omissions and unexpected wrapper fields.
_V2_PROOF_FIELDS = {
    "mode",
    "initial_modeling_context",
    "final_modeling_context",
    "workspace_context",
    "batch_inventory",
    "batch_details",
    "entities_read",
    "statements_read",
    "candidate_required_assertions",
    "term_bindings",
    "materialized_quads",
    "materialized_digest",
    "evidence_bindings",
    "statement_lineage",
    "pagination",
}


def _canonical_bytes(value: Any) -> bytes:
    """Return the one canonical JSON representation shared by all proof digests."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _strict_object(value: Any, fields: tuple[str, ...], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ProtocolRetrievalFallbackError(f"{name} has missing or extra fields")
    return value


def _strict_optional_string(value: Any, name: str) -> None:
    if value is not None and not _is_nonempty_string(value):
        raise ProtocolRetrievalFallbackError(f"{name} must be a string or null")


def _strict_digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ProtocolRetrievalFallbackError(f"{name} is invalid")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProtocolRetrievalFallbackError(f"{name} is invalid") from exc
    return value


def _sorted_unique(values: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    encoded = [_canonical_bytes(value) for value in values]
    if len(set(encoded)) != len(encoded):
        raise ProtocolRetrievalFallbackError(f"{name} contains duplicate canonical values")
    ordered = sorted(values, key=_canonical_bytes)
    if encoded != [_canonical_bytes(value) for value in ordered]:
        raise ProtocolRetrievalFallbackError(f"{name} is not canonically sorted")
    return ordered


def _candidate_item(value: Any) -> dict[str, Any]:
    item = _strict_object(value, _CANDIDATE_ITEM_FIELDS, "candidate assertion item")
    if item.get("graph_role") != "asserted_data":
        raise ProtocolRetrievalFallbackError("candidate assertion graph role is invalid")
    for field in ("subject", "predicate", "object", "object_kind"):
        if not _is_nonempty_string(item.get(field)):
            raise ProtocolRetrievalFallbackError(f"candidate assertion {field} is not bound")
    _strict_optional_string(item.get("object_datatype"), "candidate assertion object_datatype")
    _strict_optional_string(item.get("object_language"), "candidate assertion object_language")
    return item


def _materialized_quad(value: Any, data_graph: str) -> dict[str, Any]:
    quad = _strict_object(value, _MATERIALIZED_QUAD_FIELDS, "materialized quad")
    if quad.get("graph_role") != "asserted_data" or quad.get("source_graph_iri") != data_graph:
        raise ProtocolRetrievalFallbackError("materialized quad graph is invalid")
    for field in ("subject", "predicate", "object", "object_kind"):
        if not _is_nonempty_string(quad.get(field)):
            raise ProtocolRetrievalFallbackError(f"materialized quad {field} is not bound")
    _strict_optional_string(quad.get("object_datatype"), "materialized quad object_datatype")
    _strict_optional_string(quad.get("object_language"), "materialized quad object_language")
    return quad


def _candidate_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
    if candidate.get("schema_version") != _CANDIDATE_SCHEMA_VERSION:
        raise ProtocolRetrievalFallbackError("candidate schema version is invalid")
    for field in ("candidate_revision", "delivery_id"):
        if not _is_nonempty_string(candidate.get(field)):
            raise ProtocolRetrievalFallbackError(f"candidate {field} is not bound")
    chain = candidate.get("reply_chain")
    if (
        not isinstance(chain, list)
        or not chain
        or any(not _is_nonempty_string(item) for item in chain)
        or len(set(chain)) != len(chain)
    ):
        raise ProtocolRetrievalFallbackError("candidate reply_chain is invalid")
    return {field: candidate[field] for field in _CANDIDATE_BINDING_FIELDS}


def _verify_candidate_proof(
    candidate: Any,
    lineage_proof: Any,
    *,
    ontology_id: str,
    data_graph: str,
    statement_ids: set[str],
) -> dict[str, Any]:
    """Validate the strict platform-neutral candidate and its materialized lineage proof."""
    candidate = _strict_object(candidate, _CANDIDATE_FIELDS, "candidate_required_assertions")
    metadata = _candidate_metadata(candidate)
    items = candidate.get("items")
    quads = candidate.get("materialized_quads")
    if not isinstance(items, list) or not items:
        raise ProtocolRetrievalFallbackError("candidate assertion items are empty")
    if not isinstance(quads, list) or not quads:
        raise ProtocolRetrievalFallbackError("materialized quads are empty")
    normalized_items = [_candidate_item(item) for item in items]
    normalized_quads = [_materialized_quad(quad, data_graph) for quad in quads]
    _sorted_unique(normalized_items, "candidate assertion items")
    _sorted_unique(normalized_quads, "materialized quads")
    semantic_digest = _canonical_digest(
        {"schema_version": _CANDIDATE_SCHEMA_VERSION, "statements": normalized_items}
    )
    if candidate.get("semantic_digest") != semantic_digest:
        raise ProtocolRetrievalFallbackError("candidate semantic_digest drifts")
    candidate_digest = _canonical_digest(
        {
            "schema_version": _CANDIDATE_SCHEMA_VERSION,
            "candidate_revision": candidate["candidate_revision"],
            "delivery_id": candidate["delivery_id"],
            "reply_chain": candidate["reply_chain"],
            "semantic_digest": semantic_digest,
        }
    )
    if candidate.get("candidate_digest") != candidate_digest:
        raise ProtocolRetrievalFallbackError("candidate_digest drifts")
    expected_quads = [dict(item, source_graph_iri=data_graph) for item in normalized_items]
    expected_quads = [
        {field: quad[field] for field in _MATERIALIZED_QUAD_FIELDS} for quad in expected_quads
    ]
    if normalized_quads != sorted(expected_quads, key=_canonical_bytes):
        raise ProtocolRetrievalFallbackError("materialized quads do not match candidate items")
    materialized_digest = _canonical_digest(
        {"candidate_digest": candidate_digest, "quads": normalized_quads}
    )
    if candidate.get("materialized_digest") != materialized_digest:
        raise ProtocolRetrievalFallbackError("materialized_digest drifts")

    lineage = _strict_object(lineage_proof, _LINEAGE_FIELDS, "statement_lineage")
    _candidate_metadata(lineage)
    if any(lineage[field] != metadata[field] for field in _CANDIDATE_BINDING_FIELDS):
        raise ProtocolRetrievalFallbackError("statement lineage candidate binding drifts")
    if lineage.get("candidate_digest") != candidate_digest:
        raise ProtocolRetrievalFallbackError("statement lineage candidate_digest drifts")
    if lineage.get("materialized_digest") != materialized_digest:
        raise ProtocolRetrievalFallbackError("statement lineage materialized_digest drifts")
    max_depth = lineage.get("max_depth")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 0 <= max_depth <= 5:
        raise ProtocolRetrievalFallbackError("statement lineage max_depth is out of range")
    records = lineage.get("records")
    if not isinstance(records, list) or not records:
        raise ProtocolRetrievalFallbackError("statement lineage records are empty")
    normalized_records: list[dict[str, Any]] = []
    seen_fact_ids: set[str] = set()
    seen_quad_bytes: set[bytes] = set()
    quad_by_bytes = {_canonical_bytes(quad): quad for quad in normalized_quads}
    for record in records:
        record = _strict_object(record, _LINEAGE_RECORD_FIELDS, "statement lineage record")
        fact_id = _strict_digest(record.get("fact_id"), "statement lineage fact_id")
        if fact_id in seen_fact_ids:
            raise ProtocolRetrievalFallbackError("statement lineage contains duplicate fact ID")
        quad = _materialized_quad(record.get("quad"), data_graph)
        quad_bytes = _canonical_bytes(quad)
        if quad_bytes in seen_quad_bytes or quad_bytes not in quad_by_bytes:
            raise ProtocolRetrievalFallbackError("statement lineage quad is duplicate or unbound")
        seen_fact_ids.add(fact_id)
        seen_quad_bytes.add(quad_bytes)
        response = _fallback_response(record.get("response"), "statement lineage")
        computed_fact_id = _fallback_statement_fact_id(
            {**quad, "source_graph_iri": data_graph}, data_graph
        )
        if fact_id != computed_fact_id or fact_id not in statement_ids:
            raise ProtocolRetrievalFallbackError("statement lineage fact/quad mismatch")
        _fallback_exact_lineage(response, ontology_id, fact_id, quad, data_graph)
        normalized_records.append({"fact_id": fact_id, "quad": quad, "response": record["response"]})
    if seen_quad_bytes != set(quad_by_bytes) or len(seen_fact_ids) != len(normalized_quads):
        raise ProtocolRetrievalFallbackError("statement lineage is incomplete")
    return {
        "candidate": candidate,
        "lineage": lineage,
        "semantic_digest": semantic_digest,
        "candidate_digest": candidate_digest,
        "materialized_digest": materialized_digest,
        "fact_ids": seen_fact_ids,
    }


_RECEIPT_RESOURCE_COUNTS = {
    "create_class": "classes",
    "create_property": "properties",
    "create_relation_type": "relation_types",
    "create_shape": "shapes",
    "create_entity": "entities",
}


def _verify_scoped_retrieval_fallback_v1(proof: dict[str, Any]) -> dict[str, Any]:
    """Fail closed unless unmodified formal MCP reads prove complete scoped retrieval."""
    if not isinstance(proof, dict) or set(proof) != {
        "mode",
        "initial_modeling_context",
        "final_modeling_context",
        "workspace_context",
        "batch_inventory",
        "batch_details",
        "entities_read",
        "statements_read",
        "candidate_required_assertions",
        "statement_lineage",
    } or proof.get("mode") != "create":
        raise ProtocolRetrievalFallbackError("fallback requires a create scope")
    initial = _fallback_response(proof.get("initial_modeling_context"), "initial modeling context")
    final = _fallback_response(proof.get("final_modeling_context"), "final modeling context")
    workspace = _fallback_response(proof.get("workspace_context"), "workspace context")
    ontology_id = _fallback_context_ontology(initial, "initial")
    if _fallback_context_ontology(final, "final") != ontology_id:
        raise ProtocolRetrievalFallbackError("modeling context identity drifts")
    if _required_string(workspace, "ontology_id") != ontology_id:
        raise ProtocolRetrievalFallbackError("workspace does not bind the selected ontology")
    if workspace.get("state") != "ready":
        raise ProtocolRetrievalFallbackError("workspace is not ready")
    graph_set_id = _required_string(workspace, "default_graph_set_id")
    source_signature = _required_string(workspace, "source_signature")
    graphs = _fallback_workspace_graphs(workspace, ontology_id)
    initial_counts = _fallback_counts(initial)
    final_counts = _fallback_counts(final)
    if any(initial_counts[name] != 0 for name in initial_counts):
        raise ProtocolRetrievalFallbackError("fallback requires an initially empty create scope")

    inventory = proof.get("batch_inventory")
    if not isinstance(inventory, dict):
        raise ProtocolRetrievalFallbackError("batch inventory request is invalid")
    inventory_data = _fallback_response(inventory.get("response"), "batch inventory")
    requested_limit = inventory.get("requested_limit")
    if (
        not isinstance(requested_limit, int)
        or requested_limit <= 0
        or inventory.get("cursor") is not None
        or inventory.get("status_filter") is not None
    ):
        raise ProtocolRetrievalFallbackError("batch inventory must be unfiltered")
    inventory_batches = inventory_data.get("batches")
    if (
        not isinstance(inventory_batches, list)
        or requested_limit <= len(inventory_batches)
        or inventory_data.get("next_cursor") is not None
    ):
        raise ProtocolRetrievalFallbackError("batch inventory is incomplete")
    inventory_ids = {_required_string(item, "batch_id") for item in inventory_batches if isinstance(item, dict)}
    if len(inventory_ids) != len(inventory_batches):
        raise ProtocolRetrievalFallbackError("batch inventory item is invalid")

    detail_responses = proof.get("batch_details")
    if not isinstance(detail_responses, list) or not detail_responses:
        raise ProtocolRetrievalFallbackError("batch details are unavailable")
    details = [_fallback_response(value, "batch detail") for value in detail_responses]
    detail_ids = {_required_string(detail, "batch_id") for detail in details}
    if detail_ids != inventory_ids or len(detail_ids) != len(details):
        raise ProtocolRetrievalFallbackError("batch inventory does not exactly match details")

    applied: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for detail in details:
        if (
            detail.get("ontology_id") != ontology_id
            or not _is_nonempty_string(detail.get("build_session_id"))
            or not isinstance(detail.get("items"), list)
            or not isinstance(detail.get("attempts"), list)
        ):
            raise ProtocolRetrievalFallbackError("batch detail does not bind the selected scope")
        attempts = detail["attempts"]
        applied_attempts = [
            attempt
            for attempt in attempts
            if isinstance(attempt, dict)
            and attempt.get("mode") == "apply_atomic"
            and attempt.get("attempt_status") == "applied"
        ]
        non_write = not applied_attempts
        if non_write:
            if not attempts or any(
                not isinstance(attempt, dict)
                or attempt.get("mode") != "dry_run"
                or attempt.get("attempt_status") not in {"validated", "validation_failed"}
                for attempt in attempts
            ):
                raise ProtocolRetrievalFallbackError("non-write batch has applied state")
            continue
        if len(applied_attempts) != 1 or any(
            not isinstance(attempt, dict)
            or (
                attempt is not applied_attempts[0]
                and (
                    attempt.get("mode") != "dry_run"
                    or attempt.get("attempt_status") not in {"validated", "validation_failed"}
                )
            )
            for attempt in attempts
        ):
            raise ProtocolRetrievalFallbackError("write batch has an invalid attempt history")
        applied.append((detail, applied_attempts[0]))
    if not applied:
        raise ProtocolRetrievalFallbackError("fallback requires an applied write batch")

    expected_data_fact_ids: set[str] = set()
    entity_output_iris: set[str] = set()
    receipt_counts = {name: 0 for name in _RECEIPT_RESOURCE_COUNTS.values()}
    relation_sources: set[str] = set()
    chain = {initial.get("workspace", {}).get("workspace_version"): None}
    for detail, attempt in applied:
        before, after, normalized_delta = _fallback_applied_attempt(attempt)
        if before in chain and chain[before] is not None:
            raise ProtocolRetrievalFallbackError("applied workspace chain branches")
        chain[before] = after
        if _fallback_hash(normalized_delta) != _required_string(attempt, "delta_hash"):
            raise ProtocolRetrievalFallbackError("applied delta hash drifts")
        deltas = _fallback_delta_inserts(normalized_delta)
        detail_items = _fallback_applied_items(detail, attempt)
        for item in detail_items:
            command_kind = _required_string(item, "command_kind")
            expected_role = _FALLBACK_COMMAND_ROLES.get(command_kind)
            if expected_role is None:
                raise ProtocolRetrievalFallbackError("receipt contains a non-create command")
            output = item.get("resource_outputs")
            if command_kind == "create_relation":
                payload = item.get("payload")
                relation_quad = _fallback_relation_quad(payload, graphs["asserted_data"])
                if relation_quad not in deltas:
                    raise ProtocolRetrievalFallbackError("relation payload does not match applied data")
                relation_sources.add(relation_quad[0])
                continue
            if not isinstance(output, dict) or not _is_nonempty_string(output.get("resource_iri")):
                raise ProtocolRetrievalFallbackError("formal resource output is missing")
            output_iri = output["resource_iri"]
            if not any(
                _fallback_iri(quad[0]) == output_iri and quad[3] == graphs[expected_role]
                for quad in deltas
            ):
                raise ProtocolRetrievalFallbackError("command output does not bind its graph role")
            count_name = _RECEIPT_RESOURCE_COUNTS[command_kind]
            receipt_counts[count_name] += 1
            if command_kind == "create_entity":
                entity_output_iris.add(output_iri)
        for quad in deltas:
            if quad[3] not in graphs.values():
                raise ProtocolRetrievalFallbackError("applied delta targets an unknown graph")
            if quad[3] == graphs["asserted_data"]:
                expected_data_fact_ids.add(_fallback_fact_id_from_quad(quad))
    if any(receipt_counts[name] != final_counts[name] for name in receipt_counts):
        raise ProtocolRetrievalFallbackError("receipt-derived resource count drifts from modeling context")
    if len(relation_sources) != final_counts["relations"]:
        raise ProtocolRetrievalFallbackError("distinct relation-source count drifts from modeling context")
    cursor = initial.get("workspace", {}).get("workspace_version")
    visited = 0
    while cursor in chain and chain[cursor] is not None:
        cursor = chain[cursor]
        visited += 1
        if visited > len(applied):
            raise ProtocolRetrievalFallbackError("applied workspace chain loops")
    if cursor != final.get("workspace", {}).get("workspace_version") or visited != len(applied):
        raise ProtocolRetrievalFallbackError("applied workspace chain is not contiguous")

    entities = _fallback_read_model(
        proof.get("entities_read"),
        "entity read",
        graph_set_id=graph_set_id,
        source_signature=source_signature,
        model_name="entity-list",
    )
    entity_iris = {_required_string(item, "iri") for item in entities["items"] if isinstance(item, dict)}
    if any(
        not isinstance(item, dict) or item.get("source_graph_iri") != graphs["asserted_data"]
        for item in entities["items"]
    ):
        raise ProtocolRetrievalFallbackError("entity read is outside the asserted-data graph")
    if len(entity_iris) != len(entities["items"]) or entity_iris != entity_output_iris:
        raise ProtocolRetrievalFallbackError("entity read or formal output identity drifts")
    if len(entity_iris) != final_counts["entities"]:
        raise ProtocolRetrievalFallbackError("entity count drifts from modeling context")

    statements = proof.get("statements_read")
    if not isinstance(statements, dict):
        raise ProtocolRetrievalFallbackError("statement read request is invalid")
    requested_limit = statements.get("requested_limit")
    statement_data = _fallback_read_model(
        statements.get("response"),
        "statement read",
        graph_set_id=graph_set_id,
        source_signature=source_signature,
        model_name="statement-list",
    )
    expected_count = len(expected_data_fact_ids)
    if (
        not isinstance(requested_limit, int)
        or expected_count >= 1000
        or min(requested_limit, 1000) <= expected_count
    ):
        raise ProtocolRetrievalFallbackError("statement response capacity is unknown or insufficient")
    statement_ids = {_fallback_statement_fact_id(item, graphs["asserted_data"]) for item in statement_data["items"]}
    if statement_ids != expected_data_fact_ids:
        raise ProtocolRetrievalFallbackError("facts do not exactly equal reconstructed applied deltas")
    if len({_required_string(item, "subject") for item in statement_data["items"]}) != final_counts["facts"]:
        raise ProtocolRetrievalFallbackError("distinct fact-subject count drifts from modeling context")

    proof_result = _verify_candidate_proof(
        proof.get("candidate_required_assertions"),
        proof.get("statement_lineage"),
        ontology_id=ontology_id,
        data_graph=graphs["asserted_data"],
        statement_ids=statement_ids,
    )
    return {
        "complete": True,
        "ontology_id": ontology_id,
        "expected_triple_count": expected_count,
        "fact_subject_count": len({_required_string(item, "subject") for item in statement_data["items"]}),
        "relation_source_count": len(relation_sources),
        "candidate_digest": proof_result["candidate_digest"],
        "materialized_digest": proof_result["materialized_digest"],
    }


def verify_scoped_retrieval_fallback(proof: dict[str, Any]) -> dict[str, Any]:
    """Verify either the retained v1 proof or the strict native proof v2.

    The v1 envelope remains readable for historical retained runs.  New runs use
    the exact fifteen-member v2 envelope and are delegated to the isolated v2
    mechanics implementation so that v1 digest and lineage semantics cannot be
    accidentally relaxed while adding the new receipt-bound proof.
    """
    if isinstance(proof, dict) and set(proof) == _V2_PROOF_FIELDS:
        try:
            from .proof_v2 import verify_proof_v2
        except ImportError:  # pragma: no cover - direct stdio execution fallback
            from proof_v2 import verify_proof_v2
        try:
            return verify_proof_v2(proof)
        except Exception as exc:
            if isinstance(exc, ProtocolRetrievalFallbackError):
                raise
            raise ProtocolRetrievalFallbackError(str(exc)) from exc
    return _verify_scoped_retrieval_fallback_v1(proof)


_FALLBACK_COMMAND_ROLES = {
    "create_class": "asserted_ontology",
    "create_property": "asserted_ontology",
    "create_relation_type": "asserted_ontology",
    "create_shape": "shapes",
    "create_entity": "asserted_data",
    "create_relation": "asserted_data",
}


def _fallback_response(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"ok", "data"} or value.get("ok") is not True:
        raise ProtocolRetrievalFallbackError(f"{name} is not a full successful MCP envelope")
    data = value.get("data")
    if not isinstance(data, dict):
        raise ProtocolRetrievalFallbackError(f"{name} data is invalid")
    return data


def _fallback_read_model(
    value: Any,
    name: str,
    *,
    graph_set_id: str,
    source_signature: str,
    model_name: str,
) -> dict[str, Any]:
    data = _fallback_response(value, name)
    if (
        data.get("graph_set_id") != graph_set_id
        or data.get("source_signature") != source_signature
        or data.get("model_name") != model_name
        or data.get("include") != "asserted"
        or not isinstance(data.get("items"), list)
    ):
        raise ProtocolRetrievalFallbackError(f"{name} does not bind the verified workspace")
    return data


def _fallback_context_ontology(context: dict[str, Any], label: str) -> str:
    ontology = context.get("ontology")
    if not isinstance(ontology, dict):
        raise ProtocolRetrievalFallbackError(f"{label} modeling context is invalid")
    return _required_string(ontology, "id")


def _fallback_counts(context: dict[str, Any]) -> dict[str, int]:
    counts = context.get("resource_counts")
    required = (*_RECEIPT_RESOURCE_COUNTS.values(), "relations", "facts")
    if not isinstance(counts, dict) or any(
        not isinstance(counts.get(name), int) or counts[name] < 0 for name in required
    ):
        raise ProtocolRetrievalFallbackError("modeling context has invalid authoritative counts")
    return {name: counts[name] for name in required}


def _fallback_workspace_graphs(workspace: dict[str, Any], ontology_id: str) -> dict[str, str]:
    members = workspace.get("members")
    if not isinstance(members, list):
        raise ProtocolRetrievalFallbackError("workspace members are invalid")
    roles: dict[str, str] = {}
    for member in members:
        if not isinstance(member, dict):
            raise ProtocolRetrievalFallbackError("workspace member is invalid")
        role = member.get("role")
        if role not in {"asserted_ontology", "asserted_data", "shapes"}:
            continue
        if (
            role in roles
            or member.get("owner_type") != "ontology"
            or member.get("owner_id") != ontology_id
            or not _is_nonempty_string(member.get("graph_iri"))
        ):
            raise ProtocolRetrievalFallbackError("workspace graph role is invalid")
        roles[role] = member["graph_iri"]
    if set(roles) != {"asserted_ontology", "asserted_data", "shapes"}:
        raise ProtocolRetrievalFallbackError("workspace graph roles are incomplete")
    return roles


def _fallback_applied_attempt(attempt: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    workspace = attempt.get("workspace")
    normalized_delta = attempt.get("normalized_delta")
    if not isinstance(workspace, dict) or not isinstance(normalized_delta, dict):
        raise ProtocolRetrievalFallbackError("applied attempt is invalid")
    return (
        _required_string(workspace, "before_version"),
        _required_string(workspace, "after_version"),
        normalized_delta,
    )


def _fallback_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fallback_delta_inserts(value: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    if (
        set(value) != {"inserts", "deletes", "clear_graphs", "drop_graphs"}
        or not isinstance(value.get("inserts"), list)
        or value.get("deletes") != []
        or value.get("clear_graphs") != []
        or value.get("drop_graphs") != []
    ):
        raise ProtocolRetrievalFallbackError("applied delta is not create-only")
    return {_fallback_quad(quad) for quad in value["inserts"]}


def _fallback_quad(value: Any) -> tuple[str, str, str, str]:
    if not isinstance(value, list) or len(value) != 4 or not all(_is_nonempty_string(item) for item in value):
        raise ProtocolRetrievalFallbackError("applied delta quad is invalid")
    return value[0], value[1], value[2], value[3]


def _fallback_applied_items(detail: dict[str, Any], attempt: dict[str, Any]) -> list[dict[str, Any]]:
    results = attempt.get("items")
    if not isinstance(results, list):
        raise ProtocolRetrievalFallbackError("applied attempt results are invalid")
    commands = {_required_string(item, "item_id"): item for item in detail["items"] if isinstance(item, dict)}
    if len(commands) != len(detail["items"]):
        raise ProtocolRetrievalFallbackError("batch command item is invalid")
    selected: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict) or result.get("status") != "applied":
            raise ProtocolRetrievalFallbackError("applied attempt item is invalid")
        item_id = _required_string(result, "item_id")
        command = commands.get(item_id)
        if command is None:
            raise ProtocolRetrievalFallbackError("attempt result has no formal command")
        command = dict(command)
        command["resource_outputs"] = result.get("resource_outputs")
        selected.append(command)
    if not selected:
        raise ProtocolRetrievalFallbackError("applied attempt has no formal commands")
    return selected


def _fallback_relation_quad(payload: Any, data_graph: str) -> tuple[str, str, str, str]:
    if not isinstance(payload, dict):
        raise ProtocolRetrievalFallbackError("relation payload is invalid")
    return (
        f"<{_required_string(payload, 'source_entity_iri')}>",
        f"<{_required_string(payload, 'relation_type_iri')}>",
        f"<{_required_string(payload, 'target_entity_iri')}>",
        data_graph,
    )


def _fallback_fact_id_from_quad(quad: tuple[str, str, str, str]) -> str:
    subject, predicate, object_term, graph = quad
    return _fallback_fact_id(_fallback_iri(subject), _fallback_iri(predicate), object_term, graph)


def _fallback_statement_fact_id(value: Any, data_graph: str) -> str:
    if not isinstance(value, dict) or value.get("source_graph_iri") != data_graph:
        raise ProtocolRetrievalFallbackError("statement is outside the asserted-data graph")
    subject = _required_string(value, "subject")
    predicate = _required_string(value, "predicate")
    object_value = _required_string(value, "object")
    object_kind = value.get("object_kind")
    datatype = value.get("object_datatype")
    language = value.get("object_language")
    if object_kind == "iri" and datatype is None and language is None:
        object_term = f"<{object_value}>"
    elif object_kind == "literal" and (datatype is None or _is_nonempty_string(datatype)) and (
        language is None or _is_nonempty_string(language)
    ):
        escaped = object_value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        object_term = f'"{escaped}"'
        if language:
            object_term += f"@{language}"
        elif datatype:
            object_term += f"^^<{datatype}>"
    else:
        raise ProtocolRetrievalFallbackError("statement object metadata is invalid")
    fact_id = _fallback_fact_id(subject, predicate, object_term, data_graph)
    if value.get("fact_id") is not None and value.get("fact_id") != fact_id:
        raise ProtocolRetrievalFallbackError("statement fact ID is invalid")
    return fact_id


def _fallback_fact_id(subject: str, predicate: str, object_term: str, graph: str) -> str:
    canonical = f"<{subject}> <{predicate}> {object_term} <{graph}>"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fallback_iri(value: str) -> str:
    if len(value) < 3 or not value.startswith("<") or not value.endswith(">"):
        raise ProtocolRetrievalFallbackError("applied delta IRI is invalid")
    return value[1:-1]


def _fallback_exact_lineage(
    lineage: dict[str, Any], ontology_id: str, fact_id: str, assertion: Any, data_graph: str
) -> None:
    if (
        lineage.get("ontology_id") != ontology_id
        or lineage.get("truncated") is not False
        or lineage.get("target") != {"type": "statement", "id": fact_id}
        or not isinstance(lineage.get("items"), list)
    ):
        raise ProtocolRetrievalFallbackError("statement lineage scope is invalid")
    object_term = _fallback_statement_object_term(assertion)
    matching = [
        item
        for item in lineage["items"]
        if isinstance(item, dict)
        and item.get("statement_id") == fact_id
        and item.get("statement")
        == {
            "subject": _required_string(assertion, "subject"),
            "predicate": _required_string(assertion, "predicate"),
            "object": object_term,
        }
        and isinstance(item.get("technical_trace"), dict)
        and item["technical_trace"].get("graph_iri") == data_graph
        and isinstance(item.get("origins"), list)
        and bool(item["origins"])
        and isinstance(item.get("supporting_context"), dict)
        and bool(item["supporting_context"].get("evidence_references"))
    ]
    if not matching:
        raise ProtocolRetrievalFallbackError("candidate assertion lacks exact statement lineage")


def _fallback_statement_object_term(value: Any) -> str:
    copy = dict(value) if isinstance(value, dict) else value
    if not isinstance(copy, dict):
        raise ProtocolRetrievalFallbackError("statement is invalid")
    _fallback_statement_fact_id(copy, _required_string(copy, "source_graph_iri"))
    if copy["object_kind"] == "iri":
        return f"<{copy['object']}>"
    escaped = copy["object"].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    if copy.get("object_language"):
        return f'"{escaped}"@{copy["object_language"]}'
    if copy.get("object_datatype"):
        return f'"{escaped}"^^<{copy["object_datatype"]}>'
    return f'"{escaped}"'


def _required_string(value: dict[str, Any], field: str) -> str:
    candidate = value.get(field)
    if not _is_nonempty_string(candidate):
        raise ProtocolRetrievalFallbackError(f"{field} is not bound")
    return candidate


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _normalized_target_triple(value: Any, target_graph: str) -> tuple[str, str, str, str]:
    if not isinstance(value, dict) or value.get("operation") != "insert":
        raise ProtocolRetrievalFallbackError("applied delta is not a create-only insert")
    if value.get("graph") != target_graph:
        raise ProtocolRetrievalFallbackError("applied delta is outside the target data graph")
    return (
        _required_string(value, "subject"),
        _required_string(value, "predicate"),
        _required_string(value, "object"),
        target_graph,
    )


def _fact_triple(value: Any, ontology_id: str) -> tuple[str, str, str, str]:
    if not isinstance(value, dict) or value.get("ontology_id") != ontology_id:
        raise ProtocolRetrievalFallbackError("fact ownership is not bound to the selected ontology")
    return (
        _required_string(value, "subject"),
        _required_string(value, "predicate"),
        _required_string(value, "object"),
        _required_string(value, "graph"),
    )


def _proof_v2_module() -> Any:
    """Load proof-v2 only when a proof-gated operation actually needs it.

    The generic R2.3-005 Protocol asset deliberately does not mount ``proof_v2.py``.
    Keeping this import lazy lets the same mechanics wrapper provide the ordinary
    candidate receipt and retrieval fallback surface without making proof-v2 an
    unconditional runtime dependency.  Direct stdio execution still imports the
    sibling module from ``/opt`` through the fallback branch.
    """
    try:  # pragma: no cover - direct stdio execution imports the sibling module
        from . import proof_v2
    except ImportError:  # pragma: no cover
        try:
            from modeling_team import proof_v2
        except ImportError:
            import proof_v2

    return proof_v2


def _proof_v2_attr(name: str) -> Any:
    return getattr(_proof_v2_module(), name)


def _v2_call(function: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except Exception as exc:
        proof_error = None
        try:
            proof_error = _proof_v2_attr("ProofV2Error")
        except ImportError:
            pass
        if proof_error is not None and isinstance(exc, proof_error):
            raise ProtocolRetrievalFallbackError(str(exc)) from exc
        raise


def build_candidate_item_evidence_map(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _v2_call(_proof_v2_attr("build_candidate_item_evidence_map"), *args, **kwargs)


def _neutral_candidate_receipt(candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate the source-grounded, platform-neutral candidate used by R2.3-005.

    This is intentionally a small semantic envelope.  It proves that Protocol can
    consume the Modeling handoff and produce deterministic receipt material without
    requiring proof-v2 assertion IDs, matrix rows, platform IDs, or evidence-map
    files.  Batch/Item construction remains downstream Protocol work and never gets
    delegated back to Modeling.
    """
    required = {"candidate_kind", "candidate_revision", "scope", "constraints", "items"}
    if not required.issubset(candidate):
        missing = sorted(required - set(candidate))
        raise ProtocolRetrievalFallbackError(
            f"neutral candidate is missing required fields: {', '.join(missing)}"
        )
    if not _is_nonempty_string(candidate.get("candidate_kind")):
        raise ProtocolRetrievalFallbackError("neutral candidate kind is not bound")
    revision = candidate.get("candidate_revision")
    if isinstance(revision, bool) or not (
        (isinstance(revision, int) and revision > 0)
        or _is_nonempty_string(revision)
    ):
        raise ProtocolRetrievalFallbackError("neutral candidate revision is invalid")
    scope = candidate.get("scope")
    if not (_is_nonempty_string(scope) or (isinstance(scope, dict) and bool(scope))):
        raise ProtocolRetrievalFallbackError("neutral candidate scope is not bound")
    constraints = candidate.get("constraints")
    if not isinstance(constraints, list) or any(not _is_nonempty_string(value) for value in constraints):
        raise ProtocolRetrievalFallbackError("neutral candidate constraints are invalid")
    items = candidate.get("items")
    if not isinstance(items, list) or not items:
        raise ProtocolRetrievalFallbackError("neutral candidate items are empty")
    item_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ProtocolRetrievalFallbackError("neutral candidate item is invalid")
        for field in ("item_id", "item_kind"):
            if not _is_nonempty_string(item.get(field)):
                raise ProtocolRetrievalFallbackError(f"neutral candidate {field} is not bound")
        if item["item_id"] in item_ids:
            raise ProtocolRetrievalFallbackError("neutral candidate item IDs are duplicated")
        item_ids.add(item["item_id"])
        if "semantic" not in item or item["semantic"] is None:
            raise ProtocolRetrievalFallbackError("neutral candidate semantic payload is missing")
        citations = item.get("evidence_citations")
        if citations is not None and (
            not isinstance(citations, list)
            or any(not isinstance(citation, dict) for citation in citations)
        ):
            raise ProtocolRetrievalFallbackError("neutral candidate evidence citations are invalid")

    semantic_value = {
        "candidate_kind": candidate["candidate_kind"],
        "candidate_revision": revision,
        "scope": scope,
        "constraints": constraints,
        "items": items,
    }
    return {
        "status": "accepted",
        "candidate_revision": revision,
        "semantic_digest": _canonical_digest(semantic_value),
        "candidate_digest": _canonical_digest(candidate),
    }


def build_candidate_receipt(candidate: Any) -> dict[str, Any]:
    """Build the exact receipt for one immutable, fully validated v2 candidate.

    The caller supplies only the frozen candidate envelope. Proof-v2 owns the
    candidate schema, canonical ordering, citation checks, and digest bindings;
    this Protocol mechanics wrapper exposes only the four fields that may cross
    Team Transport. A deep JSON round-trip prevents the validator from
    normalizing or mutating caller-owned input.
    """
    if not isinstance(candidate, dict):
        raise ProtocolRetrievalFallbackError("candidate receipt candidate must be an object")
    try:
        candidate_value = json.loads(json.dumps(candidate, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ProtocolRetrievalFallbackError("candidate receipt candidate is not JSON") from exc
    if candidate_value.get("schema_version") == "candidate-required-assertions/v2":
        validated = _v2_call(_proof_v2_attr("_validate_candidate"), candidate_value)
        return {
            "status": "accepted",
            "candidate_revision": validated["candidate_revision"],
            "semantic_digest": validated["semantic_digest"],
            "candidate_digest": validated["candidate_digest"],
        }
    return _neutral_candidate_receipt(candidate_value)


def build_candidate_conflict(
    candidate: Any, conflict_code: Any, conflict_detail: Any
) -> dict[str, Any]:
    """Build the formal six-field conflict sibling without changing v1 receipts.

    The conflict is bound to the complete candidate exactly as received.  The
    caller cannot provide replacement digests or a reduced candidate, so a
    malformed candidate fails closed before any conflict envelope is emitted.
    """

    if not isinstance(conflict_code, str) or not conflict_code.strip():
        raise ProtocolRetrievalFallbackError("candidate conflict code is not bound")
    if not isinstance(conflict_detail, str) or not conflict_detail.strip():
        raise ProtocolRetrievalFallbackError("candidate conflict detail is not bound")
    try:
        validated = validate_formal_candidate(candidate)
        candidate_digest, semantic_digest = formal_candidate_digests(validated)
    except FormalCandidateError as exc:
        raise ProtocolRetrievalFallbackError(str(exc)) from exc
    return {
        "status": "conflict",
        "candidate_revision": validated["candidate_revision"],
        "semantic_digest": semantic_digest,
        "candidate_digest": candidate_digest,
        "conflict_code": conflict_code,
        "conflict_detail": conflict_detail,
    }


def build_existing_scope_candidate_conflict(
    candidate: Any,
    conflict_code: str,
    conflict_detail: str,
    *,
    original_delivery_id: str,
    receipt_digest: str,
    workspace_version: str,
) -> dict[str, Any]:
    """Build a typed pre-mutation 003 binding conflict.

    The normal six-field conflict remains unchanged for R2.3-005.  Existing
    scope live drift adds only receipt/delivery/workspace attribution and the
    explicit zero-mutation assertion needed to safely permit a full revision.
    """

    base = build_candidate_conflict(candidate, conflict_code, conflict_detail)
    for name, value in (
        ("original_delivery_id", original_delivery_id),
        ("receipt_digest", receipt_digest),
        ("workspace_version", workspace_version),
    ):
        if not _is_nonempty_string(value):
            raise ProtocolRetrievalFallbackError(f"typed candidate conflict {name} is invalid")
    base.update(
        {
            "original_delivery_id": original_delivery_id,
            "receipt_digest": receipt_digest,
            "workspace_version": workspace_version,
            "mutation_state": "zero-mutation",
        }
    )
    return base


_EXISTING_BINDING_SCHEMA = "r2-3-003-existing-entity-binding/v1"
_EXISTING_REF_FIELDS = {"semantic_id", "expected_class"}


def _existing_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _EXISTING_REF_FIELDS:
        raise ProtocolRetrievalFallbackError(
            "existing_entity_ref must contain only semantic_id and expected_class"
        )
    semantic_id = value.get("semantic_id")
    expected_class = value.get("expected_class")
    if not _is_nonempty_string(semantic_id) or not _is_nonempty_string(expected_class):
        raise ProtocolRetrievalFallbackError("existing_entity_ref identity is invalid")
    if "://" in semantic_id or "://" in expected_class:
        raise ProtocolRetrievalFallbackError("existing_entity_ref must remain platform-neutral")
    return {"semantic_id": semantic_id, "expected_class": expected_class}


def _existing_refs(value: Any) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        if "existing_entity_ref" in value:
            ref_value = value["existing_entity_ref"]
            # Item-kind form uses semantic directly; nested endpoint form uses
            # {existing_entity_ref: {semantic_id, expected_class}}.
            if isinstance(ref_value, Mapping):
                found.append(_existing_ref(ref_value))
            else:
                found.append(_existing_ref(value))
        elif set(value) == _EXISTING_REF_FIELDS:
            # ``item_kind=existing_entity_ref`` semantic payload.
            found.append(_existing_ref(value))
        for child in value.values():
            if child is not value:
                found.extend(_existing_refs(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_existing_refs(child))
    return found


def _read_model_entities(read_model: Any) -> list[Mapping[str, Any]]:
    if isinstance(read_model, Mapping):
        for key in ("entities", "items", "resources"):
            value = read_model.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        nested = read_model.get("data")
        if nested is not read_model:
            return _read_model_entities(nested)
    if isinstance(read_model, list):
        return [item for item in read_model if isinstance(item, Mapping)]
    raise ProtocolRetrievalFallbackError("existing binding read model is invalid")


def _row_semantic_id(row: Mapping[str, Any]) -> str | None:
    for key in ("semantic_id", "entity_id", "id"):
        value = row.get(key)
        if _is_nonempty_string(value):
            return value
    return None


def _row_class(row: Mapping[str, Any]) -> str | None:
    for key in (
        "class",
        "class_id",
        "class_semantic_id",
        "entity_class",
        "actual_class",
    ):
        value = row.get(key)
        if _is_nonempty_string(value):
            return value
    return None


def _row_iri(row: Mapping[str, Any]) -> str | None:
    for key in ("entity_iri", "iri", "resource_iri"):
        value = row.get(key)
        if _is_nonempty_string(value):
            return value
    return None


def _row_evidence(row: Mapping[str, Any]) -> Any:
    for key in ("read_evidence", "evidence", "receipt", "source"):
        if key in row and row[key] not in (None, "", [], {}):
            return row[key]
    return None


def _canonical_row_scope(
    row: Mapping[str, Any],
    *,
    project_id: str,
    ontology_id: str,
    workspace_version: str,
) -> dict[str, str]:
    """Validate the explicit backend entity projection without guessing IRIs."""

    canonical_markers = {
        "semantic_id",
        "entity_iri",
        "class_semantic_id",
        "class_iri",
        "project_id",
        "ontology_id",
        "workspace_version",
    }
    if not canonical_markers.issubset(row):
        raise ProtocolRetrievalFallbackError(
            "canonical entity projection fields are incomplete"
        )
    try:
        return validate_canonical_entity_projection(
            row,
            project_id=project_id,
            ontology_id=ontology_id,
            workspace_version=workspace_version,
        )
    except ValueError as exc:
        raise ProtocolRetrievalFallbackError(str(exc)) from exc


def build_existing_entity_binding_receipt(
    candidate: Any,
    read_model: Any,
    *,
    project_id: str,
    ontology_id: str,
    workspace_version: str,
    requirement_id: str = "R2.3-003",
) -> dict[str, Any]:
    """Bind neutral existing refs to one ontology-scoped live read model."""

    if requirement_id != "R2.3-003":
        raise ProtocolRetrievalFallbackError(
            "existing entity binding is restricted to R2.3-003"
        )
    normalized = _validate_translate_candidate(candidate)
    try:
        validate_r23003_candidate_declarations(normalized)
    except ValueError as exc:
        raise ProtocolRetrievalFallbackError(str(exc)) from exc
    if any(item.get("item_kind") == "delete_existing_entity" for item in normalized["items"]):
        if requirement_id != "R2.3-003":
            raise ProtocolRetrievalFallbackError(
                "delete_existing_entity is restricted to R2.3-003"
            )
        declarations = [
            validate_candidate_delete_declaration(item.get("semantic"))
            for item in normalized["items"]
            if item.get("item_kind") == "delete_existing_entity"
        ]
        if {item["semantic_id"] for item in declarations} != set(R2_3_003_TARGET_SET):
            raise ProtocolRetrievalFallbackError("R2.3-003 delete target set drifts")
    refs: dict[str, dict[str, str]] = {}
    for ref in _existing_refs(normalized):
        prior = refs.get(ref["semantic_id"])
        if prior is not None and prior != ref:
            raise ProtocolRetrievalFallbackError("existing_entity_ref expected Class drifts")
        refs[ref["semantic_id"]] = ref
    if not refs:
        raise ProtocolRetrievalFallbackError("candidate has no existing_entity_ref")
    for field, value in (
        ("project_id", project_id),
        ("ontology_id", ontology_id),
        ("workspace_version", workspace_version),
    ):
        if not _is_nonempty_string(value) or "://" in value:
            raise ProtocolRetrievalFallbackError(f"existing binding {field} is invalid")
    rows = _read_model_entities(read_model)
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        _canonical_row_scope(
            row,
            project_id=project_id,
            ontology_id=ontology_id,
            workspace_version=workspace_version,
        )
        semantic_id = _row_semantic_id(row)
        if semantic_id is None:
            continue
        if semantic_id in indexed:
            raise ProtocolRetrievalFallbackError("live read model contains duplicate semantic IDs")
        indexed[semantic_id] = row
    bindings: list[dict[str, Any]] = []
    for semantic_id in sorted(refs):
        ref = refs[semantic_id]
        row = indexed.get(semantic_id)
        if row is None:
            raise ProtocolRetrievalFallbackError(f"existing entity {semantic_id} is missing")
        actual_class = _row_class(row)
        entity_iri = _row_iri(row)
        if actual_class != ref["expected_class"]:
            raise ProtocolRetrievalFallbackError(f"existing entity {semantic_id} Class mismatches")
        if not isinstance(entity_iri, str) or "://" not in entity_iri:
            raise ProtocolRetrievalFallbackError(f"existing entity {semantic_id} IRI is invalid")
        evidence_value = _row_evidence(row)
        if evidence_value in (None, "", [], {}):
            raise ProtocolRetrievalFallbackError(f"existing entity {semantic_id} read evidence is missing")
        binding = {
                "semantic_id": semantic_id,
                "expected_class": ref["expected_class"],
                "actual_class": actual_class,
                "entity_iri": entity_iri,
                "read_evidence": evidence_value,
            }
        canonical = _canonical_row_scope(
            row,
            project_id=project_id,
            ontology_id=ontology_id,
            workspace_version=workspace_version,
        )
        if canonical is not None:
            binding.update(
                {
                    "class_semantic_id": canonical["class_semantic_id"],
                    "class_iri": canonical["class_iri"],
                    "project_id": canonical["project_id"],
                    "ontology_id": canonical["ontology_id"],
                    "workspace_version": canonical["workspace_version"],
                }
            )
        bindings.append(binding)
    receipt = {
        "schema_version": _EXISTING_BINDING_SCHEMA,
        "requirement_id": requirement_id,
        "candidate_digest": _canonical_digest(normalized),
        "project_id": project_id,
        "ontology_id": ontology_id,
        "workspace_version": workspace_version,
        "bindings": bindings,
    }
    receipt["receipt_digest"] = _canonical_digest(receipt)
    return receipt


build_existing_binding_receipt = build_existing_entity_binding_receipt


def validate_existing_entity_binding_receipt(
    candidate: Any,
    receipt: Any,
    *,
    project_id: str | None = None,
    ontology_id: str | None = None,
    workspace_version: str | None = None,
) -> dict[str, Any]:
    """Validate the frozen binding receipt before translation or mutation."""

    normalized = _validate_translate_candidate(candidate)
    if not isinstance(receipt, Mapping):
        raise ProtocolRetrievalFallbackError("existing binding receipt is invalid")
    expected_keys = {
        "schema_version",
        "requirement_id",
        "candidate_digest",
        "project_id",
        "ontology_id",
        "workspace_version",
        "bindings",
        "receipt_digest",
    }
    if set(receipt) != expected_keys or receipt.get("schema_version") != _EXISTING_BINDING_SCHEMA:
        raise ProtocolRetrievalFallbackError("existing binding receipt fields drift")
    if receipt.get("requirement_id") != "R2.3-003":
        raise ProtocolRetrievalFallbackError("existing binding receipt requirement drifts")
    if receipt.get("candidate_digest") != _canonical_digest(normalized):
        raise ProtocolRetrievalFallbackError("existing binding receipt candidate drifted")
    for field, expected in (
        ("project_id", project_id),
        ("ontology_id", ontology_id),
        ("workspace_version", workspace_version),
    ):
        value = receipt.get(field)
        if not _is_nonempty_string(value) or (expected is not None and value != expected):
            raise ProtocolRetrievalFallbackError(f"existing binding receipt {field} drifts")
    bindings = receipt.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ProtocolRetrievalFallbackError("existing binding receipt bindings are invalid")
    refs = {ref["semantic_id"]: ref for ref in _existing_refs(normalized)}
    seen: set[str] = set()
    normalized_bindings: list[dict[str, Any]] = []
    for item in bindings:
        if not isinstance(item, Mapping):
            raise ProtocolRetrievalFallbackError("existing binding receipt item is invalid")
        required = {"semantic_id", "expected_class", "actual_class", "entity_iri", "read_evidence"}
        canonical_fields = {"class_semantic_id", "class_iri", "project_id", "ontology_id", "workspace_version"}
        if set(item) not in (required, required | canonical_fields):
            raise ProtocolRetrievalFallbackError("existing binding receipt item fields drift")
        semantic_id = item.get("semantic_id")
        if not _is_nonempty_string(semantic_id) or semantic_id in seen:
            raise ProtocolRetrievalFallbackError("existing binding receipt has duplicate IDs")
        ref = refs.get(semantic_id)
        if ref is None or item.get("expected_class") != ref["expected_class"]:
            raise ProtocolRetrievalFallbackError("existing binding receipt ref mismatch")
        if item.get("actual_class") != item.get("expected_class"):
            raise ProtocolRetrievalFallbackError("existing binding receipt Class mismatch")
        if not _is_nonempty_string(item.get("entity_iri")) or "://" not in item["entity_iri"]:
            raise ProtocolRetrievalFallbackError("existing binding receipt IRI is invalid")
        if item.get("read_evidence") in (None, "", [], {}):
            raise ProtocolRetrievalFallbackError("existing binding receipt evidence is missing")
        if set(item) == required | canonical_fields:
            try:
                validate_canonical_entity_projection(
                    item,
                    project_id=str(receipt["project_id"]),
                    ontology_id=str(receipt["ontology_id"]),
                    workspace_version=str(receipt["workspace_version"]),
                )
            except ValueError as exc:
                raise ProtocolRetrievalFallbackError(str(exc)) from exc
        seen.add(semantic_id)
        normalized_bindings.append(dict(item))
    if seen != set(refs):
        raise ProtocolRetrievalFallbackError("existing binding receipt does not cover candidate refs")
    if list(sorted(seen)) != [item["semantic_id"] for item in normalized_bindings]:
        raise ProtocolRetrievalFallbackError("existing binding receipt ordering is not canonical")
    body = dict(receipt)
    supplied_digest = body.pop("receipt_digest")
    if supplied_digest != _canonical_digest(body):
        raise ProtocolRetrievalFallbackError("existing binding receipt digest is invalid")
    return json.loads(json.dumps(dict(receipt), ensure_ascii=False))


validate_existing_binding_receipt = validate_existing_entity_binding_receipt


# --- R3.0-009 unified read/receipt bind entry (legal zero class) -------------
#
# The R2.3 class-first contract above keeps its mandatory Class. The 009 read
# model makes a formal Class optional, so this separate entry binds existing
# entities whose visible formal Class set may be empty, while every visible
# asserted type edge is still verified independently. A known Class IRI whose
# own identity metadata is missing stays readable as an explicit
# ``incomplete_class_identity`` state instead of being reported as "no class".

_UNIFIED_BINDING_SCHEMA = "r3-0-009-existing-entity-binding/v1"
_UNIFIED_CLASS_STATES = ("classified", "incomplete_class_identity", "unclassified")


def _unified_ref(value: Any) -> dict[str, Any]:
    """One existing-entity ref; ``expected_class`` may be None (zero class)."""

    if not isinstance(value, Mapping) or set(value) != _EXISTING_REF_FIELDS:
        raise ProtocolRetrievalFallbackError(
            "existing_entity_ref must contain only semantic_id and expected_class"
        )
    semantic_id = value.get("semantic_id")
    expected_class = value.get("expected_class")
    if not _is_nonempty_string(semantic_id) or "://" in semantic_id:
        raise ProtocolRetrievalFallbackError("existing_entity_ref identity is invalid")
    if expected_class is not None:
        if not _is_nonempty_string(expected_class) or "://" in expected_class:
            raise ProtocolRetrievalFallbackError("existing_entity_ref Class is invalid")
    return {"semantic_id": semantic_id, "expected_class": expected_class}


def validate_unified_entity_projection(
    value: Any,
    *,
    project_id: str,
    ontology_id: str,
    workspace_version: str,
) -> dict[str, Any]:
    """009 canonical entity projection: the Class is optional, identity is not.

    ``semantic_id``/``entity_iri``/project/ontology/workspace stay mandatory.
    The Class pair is checked as a state: both set (classified), only the IRI
    set (incomplete class identity, the node stays readable), or both absent
    (legal zero class). A ``class_semantic_id`` without a ``class_iri`` is
    never accepted because no IRI could locate that identity.
    """

    required = {
        "semantic_id",
        "entity_iri",
        "class_semantic_id",
        "class_iri",
        "project_id",
        "ontology_id",
        "workspace_version",
    }
    if not isinstance(value, Mapping) or not required.issubset(value):
        raise ValueError("canonical entity projection fields are incomplete")
    result: dict[str, Any] = {field: value.get(field) for field in required}
    semantic_id = result["semantic_id"]
    if not isinstance(semantic_id, str) or not semantic_id.strip() or "://" in semantic_id:
        raise ValueError("canonical entity semantic_id is invalid")
    parsed = urlparse(result["entity_iri"]) if isinstance(result["entity_iri"], str) else None
    if parsed is None or not parsed.scheme or not parsed.netloc:
        raise ValueError("canonical entity entity_iri is invalid")
    class_semantic_id = result["class_semantic_id"]
    if class_semantic_id is not None and (
        not isinstance(class_semantic_id, str) or not class_semantic_id.strip() or "://" in class_semantic_id
    ):
        raise ValueError("canonical entity class_semantic_id is invalid")
    class_iri = result["class_iri"]
    if class_iri is not None:
        parsed_class = urlparse(class_iri) if isinstance(class_iri, str) else None
        if parsed_class is None or not parsed_class.scheme or not parsed_class.netloc:
            raise ValueError("canonical entity class_iri is invalid")
    if class_semantic_id is not None and class_iri is None:
        raise ValueError("canonical entity class identity has no IRI")
    for field, expected in (
        ("project_id", project_id),
        ("ontology_id", ontology_id),
        ("workspace_version", workspace_version),
    ):
        if not isinstance(result[field], str) or result[field] != expected:
            raise ValueError(f"canonical entity {field} drifts")
    return result


def _unified_class_state(row: Mapping[str, Any]) -> str:
    """Class state of one canonical 009 row; never guesses a Class."""

    class_semantic_id = row.get("class_semantic_id")
    class_iri = row.get("class_iri")
    if class_iri in (None, "") and class_semantic_id in (None, ""):
        return "unclassified"
    if class_semantic_id in (None, ""):
        return "incomplete_class_identity"
    return "classified"


def build_unified_entity_binding_receipt(
    candidate: Any,
    read_model: Any,
    *,
    project_id: str,
    ontology_id: str,
    workspace_version: str,
) -> dict[str, Any]:
    """Bind neutral existing refs to one ontology-scoped 009 read model.

    Same mechanics as the R2.3-003 entry, with the 009 projection contract: a
    ref may expect no Class, in which case the live row must be genuinely
    unclassified — an incomplete class identity is reported, never silently
    treated as "definitely no class".
    """

    normalized = _validate_translate_candidate(candidate)
    refs: dict[str, dict[str, Any]] = {}
    for value in _unified_refs(normalized):
        prior = refs.get(value["semantic_id"])
        if prior is not None and prior != value:
            raise ProtocolRetrievalFallbackError("existing_entity_ref expected Class drifts")
        refs[value["semantic_id"]] = value
    if not refs:
        raise ProtocolRetrievalFallbackError("candidate has no existing_entity_ref")
    for field, value in (
        ("project_id", project_id),
        ("ontology_id", ontology_id),
        ("workspace_version", workspace_version),
    ):
        if not _is_nonempty_string(value) or "://" in value:
            raise ProtocolRetrievalFallbackError(f"existing binding {field} is invalid")
    rows = _read_model_entities(read_model)
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        try:
            validate_unified_entity_projection(
                row,
                project_id=project_id,
                ontology_id=ontology_id,
                workspace_version=workspace_version,
            )
        except ValueError as exc:
            raise ProtocolRetrievalFallbackError(str(exc)) from exc
        semantic_id = _row_semantic_id(row)
        if semantic_id is None:
            continue
        if semantic_id in indexed:
            raise ProtocolRetrievalFallbackError("live read model contains duplicate semantic IDs")
        indexed[semantic_id] = row
    bindings: list[dict[str, Any]] = []
    for semantic_id in sorted(refs):
        ref = refs[semantic_id]
        row = indexed.get(semantic_id)
        if row is None:
            raise ProtocolRetrievalFallbackError(f"existing entity {semantic_id} is missing")
        canonical = validate_unified_entity_projection(
            row,
            project_id=project_id,
            ontology_id=ontology_id,
            workspace_version=workspace_version,
        )
        actual_class = _row_class(row) or canonical.get("class_semantic_id")
        class_state = _unified_class_state(canonical)
        if ref["expected_class"] is None:
            # Every visible asserted type edge is verified: a row that still
            # carries Class identity cannot satisfy a zero-class expectation.
            if class_state != "unclassified":
                raise ProtocolRetrievalFallbackError(
                    f"existing entity {semantic_id} still carries Class identity"
                )
            expected_class: str | None = None
        else:
            if actual_class != ref["expected_class"]:
                raise ProtocolRetrievalFallbackError(f"existing entity {semantic_id} Class mismatches")
            expected_class = ref["expected_class"]
        entity_iri = _row_iri(row)
        if not isinstance(entity_iri, str) or "://" not in entity_iri:
            raise ProtocolRetrievalFallbackError(f"existing entity {semantic_id} IRI is invalid")
        evidence_value = _row_evidence(row)
        if evidence_value in (None, "", [], {}):
            raise ProtocolRetrievalFallbackError(f"existing entity {semantic_id} read evidence is missing")
        binding = {
            "semantic_id": semantic_id,
            "expected_class": expected_class,
            "actual_class": actual_class,
            "class_state": class_state,
            "entity_iri": entity_iri,
            "read_evidence": evidence_value,
            "class_semantic_id": canonical["class_semantic_id"],
            "class_iri": canonical["class_iri"],
            "project_id": canonical["project_id"],
            "ontology_id": canonical["ontology_id"],
            "workspace_version": canonical["workspace_version"],
        }
        bindings.append(binding)
    receipt = {
        "schema_version": _UNIFIED_BINDING_SCHEMA,
        "requirement_id": "R3.0-009",
        "candidate_digest": _canonical_digest(normalized),
        "project_id": project_id,
        "ontology_id": ontology_id,
        "workspace_version": workspace_version,
        "bindings": bindings,
    }
    receipt["receipt_digest"] = _canonical_digest(receipt)
    return receipt


def _unified_refs(value: Any) -> list[dict[str, Any]]:
    """Same traversal as :func:`_existing_refs` with 009 ref rules."""

    found: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        if "existing_entity_ref" in value:
            ref_value = value["existing_entity_ref"]
            if isinstance(ref_value, Mapping):
                found.append(_unified_ref(ref_value))
            else:
                found.append(_unified_ref(value))
        elif set(value) == _EXISTING_REF_FIELDS:
            found.append(_unified_ref(value))
        for child in value.values():
            if child is value:
                continue
            found.extend(_unified_refs(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_unified_refs(child))
    return found


def validate_unified_entity_binding_receipt(
    candidate: Any,
    receipt: Any,
    *,
    project_id: str | None = None,
    ontology_id: str | None = None,
    workspace_version: str | None = None,
) -> dict[str, Any]:
    """Validate a frozen 009 binding receipt before it is used for identity."""

    normalized = _validate_translate_candidate(candidate)
    if not isinstance(receipt, Mapping):
        raise ProtocolRetrievalFallbackError("existing binding receipt is invalid")
    required = {
        "schema_version",
        "requirement_id",
        "candidate_digest",
        "project_id",
        "ontology_id",
        "workspace_version",
        "bindings",
        "receipt_digest",
    }
    if set(receipt) != required or receipt.get("schema_version") != _UNIFIED_BINDING_SCHEMA:
        raise ProtocolRetrievalFallbackError("existing binding receipt fields drift")
    if receipt.get("requirement_id") != "R3.0-009":
        raise ProtocolRetrievalFallbackError("existing binding receipt requirement drifts")
    if receipt.get("candidate_digest") != _canonical_digest(normalized):
        raise ProtocolRetrievalFallbackError("existing binding receipt candidate drifted")
    for field, expected in (
        ("project_id", project_id),
        ("ontology_id", ontology_id),
        ("workspace_version", workspace_version),
    ):
        value = receipt.get(field)
        if not _is_nonempty_string(value) or (expected is not None and value != expected):
            raise ProtocolRetrievalFallbackError(f"existing binding receipt {field} drifts")
    refs = {ref["semantic_id"]: ref for ref in _unified_refs(normalized)}
    bindings = receipt.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ProtocolRetrievalFallbackError("existing binding receipt bindings are invalid")
    seen: set[str] = set()
    for item in bindings:
        if not isinstance(item, Mapping) or set(item) != {
            "semantic_id",
            "expected_class",
            "actual_class",
            "class_state",
            "entity_iri",
            "read_evidence",
            "class_semantic_id",
            "class_iri",
            "project_id",
            "ontology_id",
            "workspace_version",
        }:
            raise ProtocolRetrievalFallbackError("existing binding receipt item fields drift")
        semantic_id = item.get("semantic_id")
        if not _is_nonempty_string(semantic_id) or semantic_id in seen:
            raise ProtocolRetrievalFallbackError("existing binding receipt has duplicate IDs")
        ref = refs.get(semantic_id)
        if ref is None or item.get("expected_class") != ref["expected_class"]:
            raise ProtocolRetrievalFallbackError("existing binding receipt ref mismatch")
        try:
            canonical = validate_unified_entity_projection(
                item,
                project_id=str(receipt["project_id"]),
                ontology_id=str(receipt["ontology_id"]),
                workspace_version=str(receipt["workspace_version"]),
            )
        except ValueError as exc:
            raise ProtocolRetrievalFallbackError(str(exc)) from exc
        state = _unified_class_state(canonical)
        if item.get("class_state") != state:
            raise ProtocolRetrievalFallbackError("existing binding receipt class state drifts")
        if ref["expected_class"] is None and state != "unclassified":
            raise ProtocolRetrievalFallbackError("existing binding receipt zero-class state drifts")
        if ref["expected_class"] is not None and item.get("actual_class") != ref["expected_class"]:
            raise ProtocolRetrievalFallbackError("existing binding receipt Class mismatch")
        if not _is_nonempty_string(item.get("entity_iri")) or "://" not in item["entity_iri"]:
            raise ProtocolRetrievalFallbackError("existing binding receipt IRI is invalid")
        if item.get("read_evidence") in (None, "", [], {}):
            raise ProtocolRetrievalFallbackError("existing binding receipt evidence is missing")
        seen.add(semantic_id)
    if seen != set(refs):
        raise ProtocolRetrievalFallbackError("existing binding receipt does not cover candidate refs")
    if list(sorted(seen)) != [item["semantic_id"] for item in bindings]:
        raise ProtocolRetrievalFallbackError("existing binding receipt ordering is not canonical")
    body = dict(receipt)
    supplied_digest = body.pop("receipt_digest")
    if supplied_digest != _canonical_digest(body):
        raise ProtocolRetrievalFallbackError("existing binding receipt digest is invalid")
    return json.loads(json.dumps(dict(receipt), ensure_ascii=False))


def translate_candidate_to_batches(
    candidate: Any,
    existing_binding_receipt: Any | None = None,
    *,
    requirement_id: str | None = None,
    deletion_impact_receipts: Mapping[str, Any] | None = None,
    phase_a_readback: bool = False,
) -> dict[str, Any]:
    """Deterministically translate one frozen candidate into a batch plan.

    This is the systemic R2.3-005 fix for Protocol translation variance: the
    candidate -> platform-batch mapping is ~100% deterministic mechanics, so it
    is owned by this tool rather than by model reasoning.  The function is a pure
    candidate-bound transform: frozen candidate in, ordered batch plan out.  It
    makes no platform calls and emits no receipts; every resource identity is
    candidate-bound, so the plan is fully reproducible at translation time.

    The plan follows the cross-batch dependency order
    ``class -> property -> entity -> relation -> shape`` and binds the
    candidate's own IDs onto every create_* payload so the platform produces
    readable, deterministic resource IRIs (``/class/{id}``, ``/property/{id}``,
    ``/entity/{id}``, ``/shape/{id}``) instead of UUID IRIs.  Object-valued
    predicates always go through ``create_property`` with ``object_class_id``;
    ``create_relation_type`` is never emitted for candidate predicates.

    Items that are not platform create resources (``consumer_query`` is retrieval
    metadata, ``negative_probe`` is a validation probe) are skipped silently.  Any
    item that cannot be translated is omitted and recorded in ``conflicts``.
    """
    normalized = _validate_translate_candidate(candidate)
    if requirement_id == "R2.3-003":
        try:
            validate_r23003_candidate_declarations(normalized)
        except ValueError as exc:
            raise ProtocolRetrievalFallbackError(str(exc)) from exc
    existing_refs = _existing_refs(normalized)
    if existing_refs:
        if requirement_id != "R2.3-003":
            raise ProtocolRetrievalFallbackError(
                "existing_entity_ref is only accepted by R2.3-003"
            )
        if existing_binding_receipt is None:
            raise ProtocolRetrievalFallbackError("existing binding receipt is required")
        validated_receipt = validate_existing_entity_binding_receipt(
            normalized, existing_binding_receipt
        )
        existing_bindings = {
            item["semantic_id"]: item["entity_iri"]
            for item in validated_receipt["bindings"]
        }
    else:
        if existing_binding_receipt is not None or requirement_id == "R2.3-003":
            if existing_binding_receipt is not None:
                raise ProtocolRetrievalFallbackError("existing binding receipt has no candidate refs")
            # The requirement-specific path must not silently accept a create-only
            # candidate: callers should make the scope mode explicit.
            if requirement_id == "R2.3-003":
                raise ProtocolRetrievalFallbackError("R2.3-003 candidate has no existing refs")
        existing_bindings = {}
    revision = normalized["candidate_revision"]
    items = normalized["items"]

    declared_entity_ids: set[str] = set()
    for item in items:
        if item["item_kind"] in {"entity", "explicit_unknown"}:
            entity_id = item["semantic"].get("entity_id")
            if _is_nonempty_string(entity_id):
                declared_entity_ids.add(entity_id)
    declared_predicates: dict[str, dict[str, Any]] = {}
    for item in items:
        if item["item_kind"] != "predicate":
            continue
        semantic = item["semantic"]
        name = semantic.get("predicate")
        if _is_nonempty_string(name):
            declared_predicates[name] = semantic

    staged: dict[str, list[dict[str, Any]]] = {stage: [] for stage in _TRANSLATE_STAGE_ORDER}
    delete_items: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for item in items:
        kind = item["item_kind"]
        semantic = item["semantic"]
        item_id = item["item_id"]
        citations = item.get("evidence_citations") or []
        evidence = _inline_evidence(citations)
        handler = _TRANSLATE_ITEM_HANDLERS.get(kind)
        if kind in {"consumer_query", "negative_probe"}:
            continue
        if kind == "existing_entity_ref":
            # A binding declaration is read-only metadata; it never becomes a
            # create/update command.  Relations consume the frozen IRI below.
            continue
        if kind == "delete_existing_entity":
            if requirement_id != "R2.3-003":
                conflicts.append(_conflict(item_id, "delete_requires_existing_contract", requirement_id))
                continue
            try:
                declaration = validate_candidate_delete_declaration(semantic)
                if not existing_refs:
                    raise _TranslateConflict(
                        "delete_requires_existing_binding",
                        "delete-only target requires an existing_entity_ref binding",
                    )
                if not phase_a_readback:
                    raise _TranslateConflict(
                        "phase_a_readback_required",
                        "delete-only Phase B requires a durable Phase A readback",
                    )
                if not isinstance(deletion_impact_receipts, Mapping):
                    raise _TranslateConflict("delete_impact_receipt_required", "tool-owned impact receipt is required")
                impact = deletion_impact_receipts.get(declaration["semantic_id"])
                if not isinstance(impact, Mapping):
                    raise _TranslateConflict("delete_impact_receipt_required", "target impact receipt is missing")
                if impact.get("target_semantic_id") != declaration["semantic_id"]:
                    raise _TranslateConflict("delete_impact_target_drift", "impact receipt target drifts")
                if any(
                    impact.get(field) != validated_receipt.get(field)
                    for field in ("project_id", "ontology_id", "workspace_version")
                ):
                    raise _TranslateConflict("delete_impact_scope_drift", "impact receipt scope drifts")
                if impact.get("candidate_digest") != _canonical_digest(normalized):
                    raise _TranslateConflict("delete_impact_candidate_drift", "impact receipt candidate digest drifts")
                if impact.get("complete") is not True:
                    raise _TranslateConflict("delete_impact_incomplete", "impact receipt is incomplete")
                if (
                    not isinstance(impact.get("statements"), list)
                    or not isinstance(impact.get("page_digests"), list)
                    or not _is_nonempty_string(impact.get("snapshot_digest"))
                ):
                    raise _TranslateConflict("delete_impact_incomplete", "impact receipt statement pages are incomplete")
                supplied_digest = impact.get("receipt_digest")
                body = dict(impact)
                body.pop("receipt_digest", None)
                if supplied_digest != _canonical_digest(body):
                    raise _TranslateConflict("delete_impact_digest_invalid", "impact receipt digest is invalid")
                target_iri = next(
                    (
                        row.get("entity_iri")
                        for row in validated_receipt["bindings"]
                        if row.get("semantic_id") == declaration["semantic_id"]
                    ),
                    None,
                )
                if not isinstance(target_iri, str) or "://" not in target_iri:
                    raise _TranslateConflict("delete_binding_missing", "delete target has no live IRI binding")
                if impact.get("entity_iri") != target_iri:
                    raise _TranslateConflict("delete_impact_entity_drift", "impact receipt entity IRI drifts")
                delete_items.append(
                    {
                        "client_item_id": item_id,
                        "command_kind": "delete_entity",
                        "payload": {
                            "entity_iri": target_iri,
                            "semantic_id": declaration["semantic_id"],
                            "expected_class": declaration["expected_class"],
                            "impact_receipt_digest": str(supplied_digest),
                            # Persist the complete tool-owned before-set with the
                            # delete command.  Recovery must compare the exact
                            # receipt-bound incident statements; a digest alone
                            # cannot distinguish a full delete from a partial or
                            # drifted delete after an uncertain SQL commit.
                            "impact_receipt": json.loads(
                                json.dumps(dict(impact), ensure_ascii=False)
                            ),
                        },
                        "evidence": evidence,
                    }
                )
            except _TranslateConflict as exc:
                conflicts.append(_conflict(item_id, exc.code, exc.detail))
            except (ValueError, KeyError, TypeError) as exc:
                conflicts.append(_conflict(item_id, "delete_impact_invalid", exc))
            continue
        if handler is None:
            conflicts.append(_conflict(item_id, "unsupported_item_kind", kind))
            continue
        try:
            if kind == "relation" and existing_bindings:
                command_kind, payload = _translate_existing_relation(
                    semantic, declared_entity_ids, declared_predicates, existing_bindings
                )
            else:
                command_kind, payload = handler(semantic, declared_entity_ids, declared_predicates)
        except _TranslateConflict as exc:
            conflicts.append(_conflict(item_id, exc.code, exc.detail))
            continue
        stage = _TRANSLATE_STAGE_FOR_COMMAND[command_kind]
        staged[stage].append(
            {
                "client_item_id": item_id,
                "command_kind": command_kind,
                "payload": payload,
                "evidence": evidence,
            }
        )

    batches: list[dict[str, Any]] = []
    for index, stage in enumerate(_TRANSLATE_STAGE_ORDER, start=1):
        stage_items = sorted(staged[stage], key=lambda value: value["client_item_id"])
        if not stage_items:
            continue
        batches.append(
            {
                "stage_kind": stage,
                "client_batch_id": f"{revision}-stage{index}-{stage}",
                "idempotency_key": f"{revision}-stage{index}-{stage}-v1",
                "apply_idempotency_key": f"{revision}-stage{index}-{stage}-apply-v1",
                "items": stage_items,
            }
        )

    if delete_items:
        # Keep each wildcard delete in its own Phase-B batch.  The platform's
        # conflict validator treats wildcard delete effects for separate
        # targets as overlapping when they share a batch, even though each
        # command carries its own receipt-bound target.  Candidate validation
        # fixes the target order, so preserve that order here and bind each
        # retry identity to the frozen target semantic ID.
        for delete_item in delete_items:
            target_semantic_id = delete_item["payload"]["semantic_id"]
            batch_suffix = f"phase-b-delete-only-{target_semantic_id}"
            batches.append(
                {
                    "stage_kind": "delete-only",
                    "client_batch_id": f"{revision}-{batch_suffix}",
                    "idempotency_key": f"{revision}-{batch_suffix}-v1",
                    "apply_idempotency_key": f"{revision}-{batch_suffix}-apply-v1",
                    "phase": "B",
                    "delete_only": True,
                    "items": [delete_item],
                }
            )

    result = {
        "candidate_kind": normalized["candidate_kind"],
        "candidate_revision": revision,
        "semantic_digest": _canonical_digest(
            {
                "candidate_kind": normalized["candidate_kind"],
                "candidate_revision": revision,
                "scope": normalized["scope"],
                "constraints": normalized["constraints"],
                "items": items,
            }
        ),
        "stage_order": list(_TRANSLATE_STAGE_ORDER),
        # R2.3-009 start7/8 (2026-08-20): the platform binds one idempotency key
        # to one request hash (content, mode, expected workspace version), so a
        # dry-run key and its apply must differ, and a retry after any apply or
        # version change must not reuse a burned key.  Own that convention here
        # instead of leaving it to agent derivation.
        "key_convention": (
            "dry_run submits with idempotency_key; apply_atomic submits with "
            "apply_idempotency_key for the same batch; run each batch's dry_run "
            "then apply_atomic before starting the next batch; if a submission "
            "returns idempotency_conflict or the expected workspace version "
            "changed, retry the affected mode with the trailing -vN incremented "
            "(v1 -> v2) and identical request content"
        ),
        "batches": batches,
        "conflicts": conflicts,
    }
    if existing_refs:
        result["requirement_id"] = "R2.3-003"
        result["existing_binding_receipt_digest"] = validated_receipt["receipt_digest"]
    if delete_items:
        result["phase_a_readback"] = True
        result["delete_only_batch"] = True
    return result


class _TranslateConflict(Exception):
    """A single candidate item cannot be translated into a platform command."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


_TRANSLATE_PLATFORM_IRI_BASE = "http://ontology-platform.local/semantic"
_TRANSLATE_STAGE_ORDER = ("class", "property", "entity", "relation", "shape")
_TRANSLATE_STAGE_FOR_COMMAND = {
    "create_class": "class",
    "create_property": "property",
    "create_entity": "entity",
    "create_relation": "relation",
    "create_shape": "shape",
}


def _validate_translate_candidate(candidate: Any) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ProtocolRetrievalFallbackError("translate candidate must be an object")
    try:
        normalized = json.loads(json.dumps(candidate, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ProtocolRetrievalFallbackError("translate candidate is not JSON") from exc
    if normalized.get("candidate_kind") != "platform-neutral-candidate-v2":
        raise ProtocolRetrievalFallbackError("translate candidate kind is not platform-neutral-candidate-v2")
    revision = normalized.get("candidate_revision")
    if isinstance(revision, bool) or not (
        (isinstance(revision, int) and revision > 0) or _is_nonempty_string(revision)
    ):
        raise ProtocolRetrievalFallbackError("translate candidate revision is invalid")
    scope = normalized.get("scope")
    if not (_is_nonempty_string(scope) or (isinstance(scope, dict) and bool(scope))):
        raise ProtocolRetrievalFallbackError("translate candidate scope is not bound")
    constraints = normalized.get("constraints")
    if not isinstance(constraints, list) or any(
        not _is_nonempty_string(value) for value in constraints
    ):
        raise ProtocolRetrievalFallbackError("translate candidate constraints are invalid")
    items = normalized.get("items")
    if not isinstance(items, list) or not items:
        raise ProtocolRetrievalFallbackError("translate candidate items are empty")
    item_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ProtocolRetrievalFallbackError("translate candidate item is invalid")
        for field in ("item_id", "item_kind"):
            if not _is_nonempty_string(item.get(field)):
                raise ProtocolRetrievalFallbackError(f"translate candidate {field} is not bound")
        if item["item_id"] in item_ids:
            raise ProtocolRetrievalFallbackError("translate candidate item IDs are duplicated")
        item_ids.add(item["item_id"])
        semantic = item.get("semantic")
        if not isinstance(semantic, dict) or not semantic:
            raise ProtocolRetrievalFallbackError("translate candidate semantic payload is missing")
        citations = item.get("evidence_citations")
        if citations is not None and (
            not isinstance(citations, list)
            or any(not isinstance(citation, dict) for citation in citations)
        ):
            raise ProtocolRetrievalFallbackError("translate candidate evidence citations are invalid")
    return normalized


def _inline_evidence(citations: list[Any]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        document_name = citation.get("document_name")
        excerpt = citation.get("excerpt")
        if _is_nonempty_string(document_name) and _is_nonempty_string(excerpt):
            evidence.append({"document_name": document_name, "excerpt": excerpt})
    return evidence


def _conflict(item_id: str, code: str, detail: Any) -> dict[str, Any]:
    return {"item_id": item_id, "code": code, "detail": str(detail)}


def _require_semantic_string(semantic: dict[str, Any], field: str) -> str:
    value = semantic.get(field)
    if not _is_nonempty_string(value):
        raise _TranslateConflict(f"missing_{field}", f"semantic.{field} is not bound")
    return value


def _platform_resource_iri(kind: str, resource_id: str) -> str:
    return f"{_TRANSLATE_PLATFORM_IRI_BASE}/{kind}/{resource_id}"


def _translate_class(
    semantic: dict[str, Any], _entities: set[str], _predicates: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    class_id = _require_semantic_string(semantic, "class_id")
    payload: dict[str, Any] = {"class_id": class_id, "name": class_id}
    description = semantic.get("description")
    if _is_nonempty_string(description):
        payload["description"] = description
    superclass = semantic.get("superclass")
    if _is_nonempty_string(superclass):
        payload["parent_class_ids"] = [superclass]
    return "create_class", payload


def _translate_predicate(
    semantic: dict[str, Any], _entities: set[str], _predicates: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    name = _require_semantic_string(semantic, "predicate")
    domain = _require_semantic_string(semantic, "domain")
    predicate_kind = semantic.get("predicate_kind")
    payload: dict[str, Any] = {"property_id": name, "class_id": domain, "name": name}
    description = semantic.get("description")
    if _is_nonempty_string(description):
        payload["description"] = description
    if predicate_kind == "fact":
        range_value = semantic.get("range")
        if not _is_nonempty_string(range_value):
            raise _TranslateConflict("missing_range", "semantic.range is not bound for a fact predicate")
        payload["datatype"] = range_value
    elif predicate_kind == "relation":
        range_value = semantic.get("range")
        if not _is_nonempty_string(range_value):
            raise _TranslateConflict("missing_range", "semantic.range is not bound for a relation predicate")
        payload["object_class_id"] = range_value
    else:
        raise _TranslateConflict(
            "unsupported_predicate_kind",
            f"predicate_kind '{predicate_kind}' is not fact or relation",
        )
    return "create_property", payload


def _translate_entity(
    semantic: dict[str, Any], _entities: set[str], _predicates: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    entity_id = _require_semantic_string(semantic, "entity_id")
    class_ref = _require_semantic_string(semantic, "class")
    values = semantic.get("values")
    if not isinstance(values, dict) or not values:
        raise _TranslateConflict("missing_values", "semantic.values is not bound")
    label = values.get("label")
    if not _is_nonempty_string(label):
        raise _TranslateConflict("missing_label", "semantic.values.label is not bound")
    properties = {key: value for key, value in values.items() if key != "label"}
    payload: dict[str, Any] = {
        "entity_id": entity_id,
        "class_iri_or_legacy_id": class_ref,
        "label": label,
        "properties": properties,
    }
    return "create_entity", payload


def _translate_relation(
    semantic: dict[str, Any], entities: set[str], predicates: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    subject = _require_semantic_string(semantic, "subject")
    obj = _require_semantic_string(semantic, "object")
    predicate = _require_semantic_string(semantic, "predicate")
    if subject not in entities:
        raise _TranslateConflict(
            "unbound_relation_subject", f"subject '{subject}' is not a declared entity"
        )
    if obj not in entities:
        raise _TranslateConflict(
            "unbound_relation_object", f"object '{obj}' is not a declared entity"
        )
    declared = predicates.get(predicate)
    if declared is None:
        raise _TranslateConflict(
            "unbound_relation_predicate", f"predicate '{predicate}' is not declared"
        )
    if declared.get("predicate_kind") != "relation":
        raise _TranslateConflict(
            "relation_predicate_not_object_property",
            f"predicate '{predicate}' is not a relation predicate",
        )
    payload = {
        "source_entity_iri": _platform_resource_iri("entity", subject),
        "relation_type_iri": _platform_resource_iri("property", predicate),
        "target_entity_iri": _platform_resource_iri("entity", obj),
    }
    return "create_relation", payload


def _translate_existing_relation(
    semantic: dict[str, Any],
    entities: set[str],
    predicates: dict[str, dict[str, Any]],
    existing_bindings: Mapping[str, str],
) -> tuple[str, dict[str, Any]]:
    """Translate a relation while resolving only receipt-backed endpoints."""

    def endpoint(value: Any, field: str) -> str:
        if isinstance(value, Mapping) and set(value) == {"existing_entity_ref"}:
            ref = _existing_ref(value["existing_entity_ref"])
            try:
                return existing_bindings[ref["semantic_id"]]
            except KeyError as exc:
                raise _TranslateConflict(
                    f"unbound_existing_relation_{field}",
                    f"existing entity '{ref['semantic_id']}' has no binding receipt",
                ) from exc
        if not _is_nonempty_string(value):
            raise _TranslateConflict(f"missing_{field}", f"semantic.{field} is not bound")
        if value in existing_bindings:
            # A bare semantic ID is not a receipt-backed reference; requiring
            # the explicit neutral wrapper prevents accidental IRI guessing.
            raise _TranslateConflict(
                f"unbound_existing_relation_{field}",
                f"semantic.{field} must use existing_entity_ref",
            )
        if value not in entities:
            raise _TranslateConflict(
                f"unbound_relation_{field}", f"{field} '{value}' is not a declared entity"
            )
        return _platform_resource_iri("entity", value)

    subject = endpoint(semantic.get("subject"), "subject")
    target = endpoint(semantic.get("object"), "object")
    predicate = _require_semantic_string(semantic, "predicate")
    declared = predicates.get(predicate)
    if declared is None:
        raise _TranslateConflict(
            "unbound_relation_predicate", f"predicate '{predicate}' is not declared"
        )
    if declared.get("predicate_kind") != "relation":
        raise _TranslateConflict(
            "relation_predicate_not_object_property",
            f"predicate '{predicate}' is not a relation predicate",
        )
    return "create_relation", {
        "source_entity_iri": subject,
        "relation_type_iri": _platform_resource_iri("property", predicate),
        "target_entity_iri": target,
    }


def _translate_shape(
    semantic: dict[str, Any], _entities: set[str], _predicates: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    shape_id = _require_semantic_string(semantic, "shape_id")
    target_class = _require_semantic_string(semantic, "target_class")
    paths = semantic.get("paths")
    if not isinstance(paths, list) or not paths:
        raise _TranslateConflict("missing_paths", "semantic.paths is not bound")
    constraints: list[dict[str, Any]] = []
    for path in paths:
        if not isinstance(path, dict):
            raise _TranslateConflict("invalid_path", "a shape path is not an object")
        predicate = path.get("predicate")
        if not _is_nonempty_string(predicate):
            raise _TranslateConflict("missing_path_predicate", "a shape path predicate is not bound")
        constraint: dict[str, Any] = {"path_id": predicate}
        for field, target in (("min_count", "min_count"), ("max_count", "max_count")):
            if path.get(field) is not None:
                constraint[target] = path[field]
        if _is_nonempty_string(path.get("datatype")):
            constraint["datatype"] = path["datatype"]
        if _is_nonempty_string(path.get("pattern")):
            constraint["pattern"] = path["pattern"]
        if _is_nonempty_string(path.get("description")):
            constraint["description"] = path["description"]
        constraints.append(constraint)
    payload = {"shape_id": shape_id, "target_class_id": target_class, "constraints": constraints}
    return "create_shape", payload


_TRANSLATE_ITEM_HANDLERS = {
    "class": _translate_class,
    "predicate": _translate_predicate,
    "entity": _translate_entity,
    "explicit_unknown": _translate_entity,
    "relation": _translate_relation,
    "shape": _translate_shape,
}


def validate_candidate_item_evidence_map(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _v2_call(_proof_v2_attr("validate_candidate_item_evidence_map"), *args, **kwargs)


def compare_dry_run_group_projection(*args: Any, **kwargs: Any) -> list[dict[str, str]]:
    return _v2_call(_proof_v2_attr("compare_dry_run_group_projection"), *args, **kwargs)


def verify_postapply_evidence_bindings(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _v2_call(_proof_v2_attr("verify_postapply_evidence_bindings"), *args, **kwargs)


def verify_proof_v2(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _v2_call(_proof_v2_attr("verify_proof_v2"), *args, **kwargs)


def citation_digest(*args: Any, **kwargs: Any) -> str:
    return _v2_call(_proof_v2_attr("citation_digest"), *args, **kwargs)


def citation_group_digest(*args: Any, **kwargs: Any) -> str:
    return _v2_call(_proof_v2_attr("citation_group_digest"), *args, **kwargs)


def inline_evidence_identity(*args: Any, **kwargs: Any) -> str:
    return _v2_call(_proof_v2_attr("inline_evidence_identity"), *args, **kwargs)


def canonical_bytes(*args: Any, **kwargs: Any) -> bytes:
    return _v2_call(_proof_v2_attr("canonical_bytes"), *args, **kwargs)


def canonical_digest(*args: Any, **kwargs: Any) -> str:
    return _v2_call(_proof_v2_attr("canonical_digest"), *args, **kwargs)
