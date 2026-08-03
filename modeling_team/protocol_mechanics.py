"""Protocol-only deterministic mechanics contract for the v2 runtime asset."""

from __future__ import annotations

import json
import hashlib
from typing import Any


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


# Public v2 mechanics are re-exported here because Protocol's staged runtime
# asset historically exposed one ``protocol_mechanics`` module.  The concrete
# implementation remains isolated in ``proof_v2`` to preserve v1 behavior.
try:  # pragma: no cover - direct stdio execution imports the sibling module
    from .proof_v2 import (
        ProofV2Error as _ProofV2Error,
        build_candidate_item_evidence_map as _build_candidate_item_evidence_map,
        canonical_bytes as proof_v2_canonical_bytes,
        canonical_digest as proof_v2_canonical_digest,
        citation_digest as proof_v2_citation_digest,
        citation_group_digest as _citation_group_digest,
        compare_dry_run_group_projection as _compare_dry_run_group_projection,
        inline_evidence_identity as _inline_evidence_identity,
        _validate_candidate as _validate_v2_candidate,
        validate_candidate_item_evidence_map as _validate_candidate_item_evidence_map,
        verify_postapply_evidence_bindings as _verify_postapply_evidence_bindings,
        verify_proof_v2 as _verify_proof_v2,
    )
except ImportError:  # pragma: no cover
    from proof_v2 import (
        ProofV2Error as _ProofV2Error,
        build_candidate_item_evidence_map as _build_candidate_item_evidence_map,
        canonical_bytes as proof_v2_canonical_bytes,
        canonical_digest as proof_v2_canonical_digest,
        citation_digest as proof_v2_citation_digest,
        citation_group_digest as _citation_group_digest,
        compare_dry_run_group_projection as _compare_dry_run_group_projection,
        inline_evidence_identity as _inline_evidence_identity,
        _validate_candidate as _validate_v2_candidate,
        validate_candidate_item_evidence_map as _validate_candidate_item_evidence_map,
        verify_postapply_evidence_bindings as _verify_postapply_evidence_bindings,
        verify_proof_v2 as _verify_proof_v2,
    )


def _v2_call(function: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except _ProofV2Error as exc:
        raise ProtocolRetrievalFallbackError(str(exc)) from exc


def build_candidate_item_evidence_map(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _v2_call(_build_candidate_item_evidence_map, *args, **kwargs)


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
    validated = _v2_call(_validate_v2_candidate, candidate_value)
    return {
        "status": "accepted",
        "candidate_revision": validated["candidate_revision"],
        "semantic_digest": validated["semantic_digest"],
        "candidate_digest": validated["candidate_digest"],
    }


def validate_candidate_item_evidence_map(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _v2_call(_validate_candidate_item_evidence_map, *args, **kwargs)


def compare_dry_run_group_projection(*args: Any, **kwargs: Any) -> list[dict[str, str]]:
    return _v2_call(_compare_dry_run_group_projection, *args, **kwargs)


def verify_postapply_evidence_bindings(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return _v2_call(_verify_postapply_evidence_bindings, *args, **kwargs)


def verify_proof_v2(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _v2_call(_verify_proof_v2, *args, **kwargs)


def citation_digest(*args: Any, **kwargs: Any) -> str:
    return _v2_call(proof_v2_citation_digest, *args, **kwargs)


def citation_group_digest(*args: Any, **kwargs: Any) -> str:
    return _v2_call(_citation_group_digest, *args, **kwargs)


def inline_evidence_identity(*args: Any, **kwargs: Any) -> str:
    return _v2_call(_inline_evidence_identity, *args, **kwargs)


def canonical_bytes(*args: Any, **kwargs: Any) -> bytes:
    return _v2_call(proof_v2_canonical_bytes, *args, **kwargs)


def canonical_digest(*args: Any, **kwargs: Any) -> str:
    return _v2_call(proof_v2_canonical_digest, *args, **kwargs)
