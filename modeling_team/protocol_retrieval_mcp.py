"""Minimal stdio MCP facade for active Protocol candidate mechanics.

Historical retrieval-proof helpers remain importable for offline fixtures, but
the production facade does not publish or dispatch them.
"""

from __future__ import annotations

import json
import hashlib
import os
import stat
import sys
from pathlib import Path
from typing import Any

from protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_candidate_conflict,
    build_candidate_receipt,
    build_candidate_item_evidence_map,
    build_unified_resource_binding_receipt,
    inspect_model_associations,
    protocol_mechanics_contract_bytes,
    translate_candidate_to_batches,
    validate_candidate_item_evidence_map,
    verify_scoped_retrieval_fallback,
)


TOOL_NAME = "verify_scoped_retrieval_fallback"
EVIDENCE_MAP_TOOL_NAME = "write_candidate_item_evidence_map"
CANDIDATE_RECEIPT_TOOL_NAME = "build_candidate_receipt"
CANDIDATE_CONFLICT_TOOL_NAME = "build_candidate_conflict"
TRANSLATE_CANDIDATE_TOOL_NAME = "translate_candidate_to_batches"
RESOURCE_BINDING_RECEIPT_TOOL_NAME = "build_unified_resource_binding_receipt"
MODEL_ASSOCIATION_TOOL_NAME = "inspect_model_associations"
EVIDENCE_MAP_RELATIVE_PATH = Path("evidence/candidate-item-evidence-map.json")
RUNTIME_RUN_ID_ENV = "PROTOCOL_RUNTIME_RUN_ID"
# Historical environment name retained only so offline fixtures can refer to
# it; the production facade never reads it.
PROOF_GATE_ENV = "PROTOCOL_PROOF_GATE"
FORMAL_CANDIDATE_GATE_ENV = "PROTOCOL_FORMAL_CANDIDATE_GATE"
RUNTIME_CONTEXT_PATH = Path("/opt/mechanics-contract.json")
REQUIRED_PROOF_ARGUMENTS = (
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
)
V2_REQUIRED_PROOF_ARGUMENTS = (
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
)
_PROOF_ARGUMENT_TYPES = {
    "mode": str,
    "initial_modeling_context": dict,
    "final_modeling_context": dict,
    "workspace_context": dict,
    "batch_inventory": dict,
    "batch_details": list,
    "entities_read": dict,
    "statements_read": dict,
    "candidate_required_assertions": dict,
    "statement_lineage": dict,
}
_V2_PROOF_ARGUMENT_TYPES = {
    "mode": str,
    "initial_modeling_context": dict,
    "final_modeling_context": dict,
    "workspace_context": dict,
    "batch_inventory": dict,
    "batch_details": list,
    "entities_read": dict,
    "statements_read": dict,
    "candidate_required_assertions": dict,
    "term_bindings": list,
    "materialized_quads": list,
    "materialized_digest": str,
    "evidence_bindings": list,
    "statement_lineage": (dict, list),
    "pagination": dict,
}


def _formal_envelope_schema(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "description": description,
        "required": ["ok", "data"],
        "additionalProperties": False,
        "properties": {
            "ok": {"type": "boolean", "description": "Unmodified MCP success indicator."},
            "data": {"type": "object", "description": "Unmodified MCP response payload."},
        },
    }


def _candidate_item_schema() -> dict[str, Any]:
    fields = [
        "graph_role",
        "subject",
        "predicate",
        "object",
        "object_kind",
        "object_datatype",
        "object_language",
    ]
    return {
        "type": "object",
        "required": fields,
        "additionalProperties": False,
        "properties": {
            "graph_role": {"type": "string", "enum": ["asserted_data"]},
            "subject": {"type": "string"},
            "predicate": {"type": "string"},
            "object": {"type": "string"},
            "object_kind": {"type": "string"},
            "object_datatype": {"type": ["string", "null"]},
            "object_language": {"type": ["string", "null"]},
        },
    }


def _materialized_quad_schema() -> dict[str, Any]:
    fields = [
        "graph_role",
        "source_graph_iri",
        "subject",
        "predicate",
        "object",
        "object_kind",
        "object_datatype",
        "object_language",
    ]
    return {
        "type": "object",
        "required": fields,
        "additionalProperties": False,
        "properties": {
            "graph_role": {"type": "string", "enum": ["asserted_data"]},
            "source_graph_iri": {"type": "string"},
            "subject": {"type": "string"},
            "predicate": {"type": "string"},
            "object": {"type": "string"},
            "object_kind": {"type": "string"},
            "object_datatype": {"type": ["string", "null"]},
            "object_language": {"type": ["string", "null"]},
        },
    }


def _exact_fields(value: object, fields: tuple[str, ...], name: str) -> str | None:
    if not isinstance(value, dict) or set(value) != set(fields):
        return f"{name} must contain exactly its required fields"
    return None


def _proof_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_nested_proof(arguments: dict[str, Any]) -> str | None:
    candidate_fields = (
        "schema_version",
        "candidate_revision",
        "delivery_id",
        "reply_chain",
        "semantic_digest",
        "candidate_digest",
        "items",
        "materialized_digest",
        "materialized_quads",
    )
    lineage_fields = (
        "schema_version",
        "candidate_revision",
        "delivery_id",
        "reply_chain",
        "semantic_digest",
        "candidate_digest",
        "materialized_digest",
        "max_depth",
        "records",
    )
    candidate = arguments.get("candidate_required_assertions")
    lineage = arguments.get("statement_lineage")
    error = _exact_fields(candidate, candidate_fields, "candidate_required_assertions")
    if error:
        return error
    error = _exact_fields(lineage, lineage_fields, "statement_lineage")
    if error:
        return error
    assert isinstance(candidate, dict) and isinstance(lineage, dict)
    if candidate.get("schema_version") != "candidate-required-assertions/v1":
        return "candidate schema_version is invalid"
    if lineage.get("schema_version") != candidate.get("schema_version"):
        return "statement lineage schema_version drifts"
    if not isinstance(candidate.get("items"), list) or not candidate["items"]:
        return "candidate_required_assertions.items must be non-empty"
    if not isinstance(candidate.get("materialized_quads"), list) or not candidate["materialized_quads"]:
        return "candidate_required_assertions.materialized_quads must be non-empty"
    if not isinstance(lineage.get("records"), list) or not lineage["records"]:
        return "statement_lineage.records must be non-empty"
    if isinstance(lineage.get("max_depth"), bool) or not isinstance(lineage.get("max_depth"), int) or not 0 <= lineage["max_depth"] <= 5:
        return "statement_lineage.max_depth must be an integer from 0 through 5"
    item_fields = (
        "graph_role",
        "subject",
        "predicate",
        "object",
        "object_kind",
        "object_datatype",
        "object_language",
    )
    quad_fields = (
        "graph_role",
        "source_graph_iri",
        "subject",
        "predicate",
        "object",
        "object_kind",
        "object_datatype",
        "object_language",
    )
    for field in ("candidate_revision", "delivery_id"):
        if not isinstance(candidate.get(field), str) or not candidate[field]:
            return f"candidate {field} is invalid"
    chain = candidate.get("reply_chain")
    if (
        not isinstance(chain, list)
        or not chain
        or any(not isinstance(item, str) or not item for item in chain)
        or len(set(chain)) != len(chain)
    ):
        return "candidate reply_chain is invalid"
    if any(lineage.get(field) != candidate.get(field) for field in ("candidate_revision", "delivery_id", "reply_chain")):
        return "statement lineage candidate binding drifts"
    for item in candidate["items"]:
        error = _exact_fields(item, item_fields, "candidate assertion item")
        if error:
            return error
        if item.get("graph_role") != "asserted_data" or any(
            not isinstance(item.get(field), str) or not item[field]
            for field in ("subject", "predicate", "object", "object_kind")
        ) or any(
            value is not None and (not isinstance(value, str) or not value)
            for value in (item.get("object_datatype"), item.get("object_language"))
        ):
            return "candidate assertion item values are invalid"
    for quad in candidate["materialized_quads"]:
        error = _exact_fields(quad, quad_fields, "materialized quad")
        if error:
            return error
        if quad.get("graph_role") != "asserted_data" or any(
            not isinstance(quad.get(field), str) or not quad[field]
            for field in ("source_graph_iri", "subject", "predicate", "object", "object_kind")
        ) or any(
            value is not None and (not isinstance(value, str) or not value)
            for value in (quad.get("object_datatype"), quad.get("object_language"))
        ):
            return "materialized quad values are invalid"
    canonical_items = sorted(candidate["items"], key=lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    item_bytes = [json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") for value in candidate["items"]]
    if len(set(item_bytes)) != len(item_bytes) or candidate["items"] != canonical_items:
        return "candidate assertion items are not canonical and unique"
    canonical_quads = sorted(candidate["materialized_quads"], key=lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    quad_bytes = [json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") for value in candidate["materialized_quads"]]
    if len(set(quad_bytes)) != len(quad_bytes) or candidate["materialized_quads"] != canonical_quads:
        return "materialized quads are not canonical and unique"
    semantic_digest = _proof_digest({"schema_version": "candidate-required-assertions/v1", "statements": candidate["items"]})
    if candidate.get("semantic_digest") != semantic_digest:
        return "candidate semantic_digest drifts"
    candidate_digest = _proof_digest({
        "schema_version": "candidate-required-assertions/v1",
        "candidate_revision": candidate["candidate_revision"],
        "delivery_id": candidate["delivery_id"],
        "reply_chain": candidate["reply_chain"],
        "semantic_digest": semantic_digest,
    })
    if candidate.get("candidate_digest") != candidate_digest:
        return "candidate_digest drifts"
    if lineage.get("semantic_digest") != semantic_digest or lineage.get("candidate_digest") != candidate_digest:
        return "statement lineage digest drifts"
    materialized_digest = _proof_digest({"candidate_digest": candidate_digest, "quads": candidate["materialized_quads"]})
    if candidate.get("materialized_digest") != materialized_digest or lineage.get("materialized_digest") != materialized_digest:
        return "materialized_digest drifts"
    for record in lineage["records"]:
        error = _exact_fields(record, ("fact_id", "quad", "response"), "statement lineage record")
        if error:
            return error
        error = _exact_fields(record.get("quad"), quad_fields, "statement lineage record quad")
        if error:
            return error
        response = record.get("response")
        if (
            not isinstance(response, dict)
            or set(response) != {"ok", "data"}
            or response.get("ok") is not True
            or not isinstance(response.get("data"), dict)
        ):
            return "statement lineage response must be a full successful envelope"
    if len({json.dumps(record["quad"], ensure_ascii=False, sort_keys=True, separators=(",", ":")) for record in lineage["records"]}) != len(lineage["records"]):
        return "statement lineage contains duplicate quads"
    return None


def _legacy_v1_proof_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Direct arguments for the formal retrieval-fallback proof; never wrap them in a proof object.",
        "required": list(REQUIRED_PROOF_ARGUMENTS),
        "additionalProperties": False,
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["create"],
                "description": "Fallback scope mode; MUST equal the exact literal `create` accepted by the native verifier.",
            },
            "initial_modeling_context": _formal_envelope_schema(
                "Initial get_modeling_context formal response."
            ),
            "final_modeling_context": _formal_envelope_schema(
                "Final get_modeling_context formal response."
            ),
            "workspace_context": _formal_envelope_schema(
                "Stable final get_ontology_workspace_context formal response."
            ),
            "batch_inventory": {
                "type": "object",
                "description": "Stable unfiltered Session Batch inventory request and formal response.",
                "required": ["requested_limit", "response"],
                "additionalProperties": False,
                "properties": {
                    "requested_limit": {
                        "type": "integer",
                        "description": "Inventory request limit used for the no-cursor proof.",
                    },
                    "cursor": {
                        "type": ["string", "null"],
                        "description": "Inventory request cursor; stable proof uses null.",
                    },
                    "status_filter": {
                        "type": ["string", "null"],
                        "description": "Inventory status filter; stable proof is unfiltered.",
                    },
                    "response": _formal_envelope_schema(
                        "Unmodified list_session_modeling_batches formal response."
                    ),
                },
            },
            "batch_details": {
                "type": "array",
                "description": "Unmodified get_modeling_batch formal responses for every inventory Batch.",
                "items": _formal_envelope_schema("One unmodified get_modeling_batch formal response."),
            },
            "entities_read": _formal_envelope_schema(
                "Unmodified asserted entity-list read-model formal response."
            ),
            "statements_read": {
                "type": "object",
                "description": "Bounded asserted statement-list request and formal response.",
                "required": ["requested_limit", "response"],
                "additionalProperties": False,
                "properties": {
                    "requested_limit": {
                        "type": "integer",
                        "description": "Statement-list request limit used for capacity proof.",
                    },
                    "response": _formal_envelope_schema(
                        "Unmodified asserted statement-list formal response."
                    ),
                },
            },
            "candidate_required_assertions": {
                "type": "object",
                "description": "Strict candidate-required-assertions/v1 binding and materialization.",
                "required": [
                    "schema_version",
                    "candidate_revision",
                    "delivery_id",
                    "reply_chain",
                    "semantic_digest",
                    "candidate_digest",
                    "items",
                    "materialized_digest",
                    "materialized_quads",
                ],
                "additionalProperties": False,
                "properties": {
                    "schema_version": {"type": "string"},
                    "candidate_revision": {"type": "string"},
                    "delivery_id": {"type": "string"},
                    "reply_chain": {"type": "array", "items": {"type": "string"}},
                    "semantic_digest": {"type": "string"},
                    "candidate_digest": {"type": "string"},
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": _candidate_item_schema(),
                    },
                    "materialized_digest": {"type": "string"},
                    "materialized_quads": {
                        "type": "array",
                        "minItems": 1,
                        "items": _materialized_quad_schema(),
                    },
                },
            },
            "statement_lineage": {
                "type": "object",
                "description": "Strict candidate binding and one-to-one computed fact lineage.",
                "required": [
                    "schema_version",
                    "candidate_revision",
                    "delivery_id",
                    "reply_chain",
                    "semantic_digest",
                    "candidate_digest",
                    "materialized_digest",
                    "max_depth",
                    "records",
                ],
                "additionalProperties": False,
                "properties": {
                    "schema_version": {"type": "string"},
                    "candidate_revision": {"type": "string"},
                    "delivery_id": {"type": "string"},
                    "reply_chain": {"type": "array", "items": {"type": "string"}},
                    "semantic_digest": {"type": "string"},
                    "candidate_digest": {"type": "string"},
                    "materialized_digest": {"type": "string"},
                    "max_depth": {"type": "integer", "minimum": 0, "maximum": 5},
                    "records": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["fact_id", "quad", "response"],
                            "additionalProperties": False,
                            "properties": {
                                "fact_id": {"type": "string"},
                                "quad": _materialized_quad_schema(),
                                "response": _formal_envelope_schema(
                                    "Unmodified inspect_semantic_statement_provenance formal response."
                                ),
                            },
                        },
                    },
                },
            },
        },
    }


def _v2_citation_schema() -> dict[str, Any]:
    fields = [
        "document_name",
        "excerpt",
        "source_artifact_sha256",
        "source_locator",
        "excerpt_sha256",
        "owner_answer_id",
    ]
    return {
        "type": "object",
        "required": fields,
        "additionalProperties": False,
        "properties": {
            "document_name": {"type": "string"},
            "excerpt": {"type": "string"},
            "source_artifact_sha256": {"type": "string"},
            "source_locator": {"type": "string"},
            "excerpt_sha256": {"type": "string"},
            "owner_answer_id": {"type": ["string", "null"]},
        },
    }


def _v2_term_binding_schema() -> dict[str, Any]:
    fields = [
        "assertion_id",
        "term_position",
        "candidate_term",
        "binding_kind",
        "client_item_id",
        "batch_id",
        "applied_attempt_id",
        "quad_digest",
        "delta_index",
        "resource_output_iri",
    ]
    return {
        "type": "object",
        "required": fields,
        "additionalProperties": False,
        "properties": {
            "assertion_id": {"type": "string"},
            "term_position": {"type": "string", "enum": ["subject", "predicate", "object"]},
            "candidate_term": {"type": "string"},
            "binding_kind": {"type": "string", "enum": ["literal_delta", "resource_output", "relation_delta", "vocabulary"]},
            "client_item_id": {"type": "string"},
            "batch_id": {"type": "string"},
            "applied_attempt_id": {"type": "string"},
            "quad_digest": {"type": "string"},
            "delta_index": {"type": "integer", "minimum": 0},
            "resource_output_iri": {"type": ["string", "null"]},
        },
    }


def _v2_quad_schema() -> dict[str, Any]:
    return _materialized_quad_schema()


def _proof_input_schema() -> dict[str, Any]:
    """Advertise v2 as the current tool contract; v1 remains read-compatible."""
    fields = list(V2_REQUIRED_PROOF_ARGUMENTS)
    item_fields = [
        "assertion_id",
        "graph_role",
        "subject",
        "predicate",
        "object",
        "object_kind",
        "object_datatype",
        "object_language",
        "evidence_citations",
    ]
    evidence_fields = [
        "assertion_id",
        "citation_digest",
        "evidence_reference_id",
        "client_item_id",
        "batch_id",
        "fact_id",
        "inline_evidence_identity",
        "citation_group_digest",
    ]
    page_fields = [
        "stream_kind",
        "request_fingerprint_sha256",
        "page_index",
        "request_cursor",
        "next_cursor",
        "response_digest",
        "root_match_ids_digest",
        "response",
    ]
    envelope = _formal_envelope_schema("Unmodified formal MCP response payload.")
    return {
        "type": "object",
        "description": "Direct arguments for the strict native retrieval proof v2; never wrap them in a proof object.",
        "required": fields,
        "additionalProperties": False,
        "properties": {
            "mode": {"type": "string", "enum": ["create"], "description": "MUST equal the exact literal `create`."},
            "initial_modeling_context": envelope,
            "final_modeling_context": envelope,
            "workspace_context": envelope,
            "batch_inventory": {
                "type": "object",
                "required": ["requested_limit", "response"],
                "additionalProperties": False,
                "properties": {
                    "requested_limit": {"type": "integer", "minimum": 1},
                    "cursor": {"type": ["string", "null"]},
                    "status_filter": {"type": ["string", "null"]},
                    "response": envelope,
                },
            },
            "batch_details": {"type": "array", "items": envelope},
            "entities_read": envelope,
            "statements_read": {
                "type": "object",
                "required": ["requested_limit", "response"],
                "additionalProperties": False,
                "properties": {"requested_limit": {"type": "integer", "minimum": 1}, "response": envelope},
            },
            "candidate_required_assertions": {
                "type": "object",
                "required": ["schema_version", "candidate_revision", "delivery_id", "reply_chain", "semantic_digest", "candidate_digest", "items"],
                "additionalProperties": False,
                "properties": {
                    "schema_version": {"type": "string", "enum": ["candidate-required-assertions/v2"]},
                    "candidate_revision": {"type": "string"},
                    "delivery_id": {"type": "string"},
                    "reply_chain": {"type": "array", "items": {"type": "string"}},
                    "semantic_digest": {"type": "string"},
                    "candidate_digest": {"type": "string"},
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": item_fields,
                            "additionalProperties": False,
                            "properties": {
                                "assertion_id": {"type": "string"},
                                "graph_role": {"type": "string", "enum": ["asserted_data"]},
                                "subject": {"type": "string"},
                                "predicate": {"type": "string"},
                                "object": {"type": "string"},
                                "object_kind": {"type": "string"},
                                "object_datatype": {"type": ["string", "null"]},
                                "object_language": {"type": ["string", "null"]},
                                "evidence_citations": {"type": "array", "minItems": 1, "items": _v2_citation_schema()},
                            },
                        },
                    },
                },
            },
            "term_bindings": {"type": "array", "minItems": 1, "items": _v2_term_binding_schema()},
            "materialized_quads": {"type": "array", "minItems": 1, "items": _v2_quad_schema()},
            "materialized_digest": {"type": "string"},
            "evidence_bindings": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": evidence_fields,
                    "additionalProperties": False,
                    "properties": {field: {"type": "string"} for field in evidence_fields},
                },
            },
            "statement_lineage": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["assertion_id", "fact_id", "quad", "target", "response"],
                    "additionalProperties": False,
                    "properties": {
                        "assertion_id": {"type": "string"},
                        "fact_id": {"type": "string"},
                        "quad": _v2_quad_schema(),
                        "target": {
                            "type": "object",
                            "required": ["target_kind", "target_id"],
                            "additionalProperties": False,
                            "properties": {"target_kind": {"type": "string", "enum": ["resource", "statement"]}, "target_id": {"type": "string"}},
                        },
                        "response": envelope,
                    },
                },
            },
            "pagination": {
                "type": "object",
                "required": ["schema_version", "streams"],
                "additionalProperties": False,
                "properties": {
                    "schema_version": {"type": "string"},
                    "streams": {
                        "type": "array",
                        "minItems": 2,
                        "items": {
                            "type": "object",
                            "required": ["stream_kind", "pages"],
                            "additionalProperties": False,
                            "properties": {
                                "stream_kind": {"type": "string", "enum": ["matches", "context"]},
                                "pages": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {
                                        "type": "object",
                                        "required": page_fields,
                                        "additionalProperties": False,
                                        "properties": {
                                            "stream_kind": {"type": "string", "enum": ["matches", "context"]},
                                            "request_fingerprint_sha256": {"type": "string"},
                                            "page_index": {"type": "integer", "minimum": 0},
                                            "request_cursor": {"type": ["string", "null"]},
                                            "next_cursor": {"type": ["string", "null"]},
                                            "response_digest": {"type": "string"},
                                            "root_match_ids_digest": {"type": "string"},
                                            "response": envelope,
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def _result(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": "Fail-closed verification of generic ontology-scoped retrieval fallback proof.",
        "inputSchema": _proof_input_schema(),
    }


def _candidate_item_evidence_map_schema() -> dict[str, Any]:
    """Advertise the only Protocol-owned candidate-map producer contract."""
    item_fields = [
        "assertion_id",
        "graph_role",
        "subject",
        "predicate",
        "object",
        "object_kind",
        "object_datatype",
        "object_language",
        "evidence_citations",
    ]
    candidate_fields = [
        "schema_version",
        "candidate_revision",
        "delivery_id",
        "reply_chain",
        "semantic_digest",
        "candidate_digest",
        "items",
    ]
    return {
        "type": "object",
        "description": (
            "Build and immutably write the strict v1 candidate Evidence map in the current "
            "Protocol runtime work directory; the run ID comes from the Host-bound runtime "
            "context, and the output path is fixed and not an argument."
        ),
        "required": ["candidate", "client_item_ids"],
        "additionalProperties": False,
        "properties": {
            "candidate": {
                "type": "object",
                "required": candidate_fields,
                "additionalProperties": False,
                "properties": {
                    "schema_version": {
                        "type": "string",
                        "enum": ["candidate-required-assertions/v2"],
                    },
                    "candidate_revision": {"type": "string", "minLength": 1},
                    "delivery_id": {"type": "string", "minLength": 1},
                    "reply_chain": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "semantic_digest": {"type": "string", "minLength": 64, "maxLength": 64},
                    "candidate_digest": {"type": "string", "minLength": 64, "maxLength": 64},
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": item_fields,
                            "additionalProperties": False,
                            "properties": {
                                "assertion_id": {"type": "string", "minLength": 1},
                                "graph_role": {"type": "string", "enum": ["asserted_data"]},
                                "subject": {"type": "string", "minLength": 1},
                                "predicate": {"type": "string", "minLength": 1},
                                "object": {"type": "string", "minLength": 1},
                                "object_kind": {"type": "string", "minLength": 1},
                                "object_datatype": {"type": ["string", "null"]},
                                "object_language": {"type": ["string", "null"]},
                                "evidence_citations": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": _v2_citation_schema(),
                                },
                            },
                        },
                    },
                },
            },
            "client_item_ids": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": {"type": "string", "minLength": 1},
            },
        },
    }


def _evidence_map_tool() -> dict[str, Any]:
    return {
        "name": EVIDENCE_MAP_TOOL_NAME,
        "description": (
            "Build the frozen candidate-item Evidence map with the canonical proof-v2 builder, "
            "validate it, and write exactly one immutable runtime-local map file."
        ),
        "inputSchema": _candidate_item_evidence_map_schema(),
    }


def _candidate_receipt_schema() -> dict[str, Any]:
    """Advertise the candidate-only deterministic receipt producer contract."""
    # The old proof gate is intentionally ignored.  The production candidate
    # receipt surface stays platform-neutral even when an archived Task or
    # environment sets PROTOCOL_PROOF_GATE=1; proof-v2 remains offline code.
    candidate_schema = _neutral_candidate_schema()
    description = (
        "Validate one source-grounded, platform-neutral semantic candidate and return a "
        "deterministic four-field Protocol receipt. Protocol owns candidate-v2/Batch "
        "translation; callers do not provide platform IDs, Batch fields, or proof metadata."
    )
    return {
        "type": "object",
        "description": description,
        "required": ["candidate"],
        "additionalProperties": False,
        "properties": {"candidate": candidate_schema},
    }


def _neutral_candidate_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": (
            "Platform-neutral semantic candidate from Modeling. Protocol translates this "
            "candidate into deterministic candidate-v3/Batch requests."
        ),
        "required": ["candidate_kind", "candidate_revision", "scope", "constraints", "items"],
        "additionalProperties": False,
        "properties": {
            "candidate_kind": {"type": "string", "minLength": 1},
            "candidate_revision": {"oneOf": [{"type": "integer", "minimum": 1}, {"type": "string", "minLength": 1}]},
            "scope": {"oneOf": [{"type": "string", "minLength": 1}, {"type": "object", "minProperties": 1}]},
            "constraints": {"type": "array", "items": {"type": "string"}},
            "items": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["item_id", "item_kind", "semantic"],
                    "additionalProperties": False,
                    "properties": {
                        "item_id": {"type": "string", "minLength": 1},
                        "item_kind": {"type": "string", "minLength": 1},
                        "semantic": {},
                    },
                },
            },
        },
    }


def _candidate_receipt_tool() -> dict[str, Any]:
    return {
        "name": CANDIDATE_RECEIPT_TOOL_NAME,
        "description": (
            "Build a deterministic accepted receipt from the Modeling candidate; the caller "
            "must send the returned exact payload through Team Transport."
        ),
        "inputSchema": _candidate_receipt_schema(),
    }


def _candidate_conflict_tool() -> dict[str, Any]:
    return {
        "name": CANDIDATE_CONFLICT_TOOL_NAME,
        "description": (
            "Build a deterministic formal conflict bound to the complete current candidate. "
            "Use only after attempting the accepted receipt builder; send the exact returned "
            "six-field payload through Team Transport."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["candidate", "conflict_code", "conflict_detail"],
            "additionalProperties": False,
            "properties": {
                "candidate": _candidate_receipt_schema()["properties"]["candidate"],
                "conflict_code": {"type": "string", "minLength": 1},
                "conflict_detail": {"type": "string", "minLength": 1},
            },
        },
    }


def _translate_candidate_tool() -> dict[str, Any]:
    return {
        "name": TRANSLATE_CANDIDATE_TOOL_NAME,
        "description": (
            "Deterministically translate one frozen platform-neutral-candidate-v3 into an "
            "ordered, submit-ready batch plan (definitions -> table/join/enum/metric mappings "
            "-> relations -> shapes for mapping candidates; legacy class -> property -> entity "
            "-> relation -> shape otherwise). Pure candidate-bound mechanics: no platform calls, no receipts. Every "
            "create_* payload binds the candidate's own ID so the platform emits readable "
            "resource IRIs; object predicates always use create_property+object_class_id. "
            "R2.3-005 and ordinary candidates pass only candidate; R2.3-003 may additionally "
            "pass its requirement ID, existing binding receipt, deletion-impact receipts, and "
            "Phase-A readback flag so the native plan owns the final ordered delete-only Phase-B batches."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["candidate"],
            "additionalProperties": False,
            "properties": {
                "candidate": _neutral_candidate_schema(),
                "requirement_id": {
                    "type": "string",
                    "enum": ["R2.3-003", "R4.0-010"],
                    "description": "R2.3-003 entity deletion or R4.0-010 resource-kind governed bindings.",
                },
                "existing_binding_receipt": {
                    "type": "object",
                    "description": "Protocol-owned canonical identity/read receipt for existing refs; R4.0-010 receipts preserve resource_kind.",
                },
                "deletion_impact_receipts": {
                    "type": "object",
                    "additionalProperties": {"type": "object"},
                    "description": "Complete tool-owned live incident-statement receipts keyed by semantic ID.",
                },
                "phase_a_readback": {
                    "type": "boolean",
                    "description": "True only after durable Phase-A write/readback; required before Phase B.",
                },
                "semantic_base_iri": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Protocol host semantic namespace for this isolated workspace; kept "
                        "outside the neutral candidate. Defaults to the local platform namespace."
                    ),
                },
            },
        },
    }


def _resource_binding_receipt_tool() -> dict[str, Any]:
    return {
        "name": RESOURCE_BINDING_RECEIPT_TOOL_NAME,
        "description": (
            "Bind active R4.0-010 existing_resource_ref items to one unmodified, authorized "
            "governed resource read envelope. The selected Project/Ontology/workspace scope "
            "is explicit; resource kind, stable ID and actual IRI come from the read envelope. "
            "No asserted_data statement shortcut or entity-only binding is accepted."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["candidate", "read_envelope", "scope"],
            "additionalProperties": False,
            "properties": {
                "candidate": _neutral_candidate_schema(),
                "read_envelope": {
                    "type": ["object", "array"],
                    "description": (
                        "Unmodified response from an authorized governed resource/read-model "
                        "read; exact resource reads and list envelopes are accepted."
                    ),
                },
                "scope": {
                    "type": "object",
                    "required": ["project_id", "ontology_id", "workspace_version"],
                    "additionalProperties": False,
                    "properties": {
                        "project_id": {"type": "string", "minLength": 1},
                        "ontology_id": {"type": "string", "minLength": 1},
                        "workspace_version": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }


def _validate_translate_candidate_arguments(arguments: object) -> str | None:
    if not isinstance(arguments, dict):
        return "translate candidate arguments must be an object"
    allowed = {
        "candidate",
        "requirement_id",
        "existing_binding_receipt",
        "deletion_impact_receipts",
        "phase_a_readback",
        "semantic_base_iri",
    }
    if not set(arguments).issubset(allowed):
        return "translate candidate arguments contain unsupported fields"
    if not isinstance(arguments.get("candidate"), dict):
        return "translate candidate candidate must be an object"
    if set(arguments) == {"candidate"}:
        return None
    if arguments.get("requirement_id") not in {"R2.3-003", "R4.0-010"} and set(arguments) != {
        "candidate", "semantic_base_iri"
    }:
        return "translate candidate extensions are restricted to R2.3-003 or R4.0-010"
    if "existing_binding_receipt" in arguments and not isinstance(
        arguments["existing_binding_receipt"], dict
    ):
        return "translate candidate existing_binding_receipt must be an object"
    if "deletion_impact_receipts" in arguments and not isinstance(
        arguments["deletion_impact_receipts"], dict
    ):
        return "translate candidate deletion_impact_receipts must be an object"
    if "phase_a_readback" in arguments and not isinstance(arguments["phase_a_readback"], bool):
        return "translate candidate phase_a_readback must be a boolean"
    if "semantic_base_iri" in arguments and (
        not isinstance(arguments["semantic_base_iri"], str)
        or not arguments["semantic_base_iri"].strip()
    ):
        return "translate candidate semantic_base_iri must be a non-empty string"
    return None


def _validate_resource_binding_receipt_arguments(arguments: object) -> str | None:
    if not isinstance(arguments, dict) or set(arguments) != {
        "candidate", "read_envelope", "scope"
    }:
        return "resource binding receipt arguments must contain exactly candidate, read_envelope and scope"
    if not isinstance(arguments.get("candidate"), dict):
        return "resource binding receipt candidate must be an object"
    if not isinstance(arguments.get("read_envelope"), (dict, list)):
        return "resource binding receipt read_envelope must be an object or array"
    scope = arguments.get("scope")
    if not isinstance(scope, dict) or set(scope) != {
        "project_id", "ontology_id", "workspace_version"
    }:
        return "resource binding receipt scope must contain exactly project_id, ontology_id and workspace_version"
    if any(
        not isinstance(scope.get(field), str) or not scope[field].strip()
        for field in ("project_id", "ontology_id", "workspace_version")
    ):
        return "resource binding receipt scope fields must be non-empty strings"
    return None


def _formal_candidate_gate_enabled() -> bool:
    return os.environ.get(FORMAL_CANDIDATE_GATE_ENV, "0") == "1"


def _validate_candidate_receipt_arguments(arguments: object) -> str | None:
    if not isinstance(arguments, dict) or set(arguments) != {"candidate"}:
        return "candidate receipt arguments must contain exactly candidate"
    if not isinstance(arguments.get("candidate"), dict):
        return "candidate receipt candidate must be an object"
    return None


def _validate_candidate_conflict_arguments(arguments: object) -> str | None:
    if not isinstance(arguments, dict) or set(arguments) != {
        "candidate",
        "conflict_code",
        "conflict_detail",
    }:
        return "candidate conflict arguments must contain exactly candidate, conflict_code and conflict_detail"
    if not isinstance(arguments.get("candidate"), dict):
        return "candidate conflict candidate must be an object"
    if not isinstance(arguments.get("conflict_code"), str) or not arguments["conflict_code"].strip():
        return "candidate conflict code must be a non-empty string"
    if not isinstance(arguments.get("conflict_detail"), str) or not arguments["conflict_detail"].strip():
        return "candidate conflict detail must be a non-empty string"
    return None


def _validate_evidence_map_arguments(arguments: object) -> str | None:
    fields = {"candidate", "client_item_ids"}
    if not isinstance(arguments, dict) or set(arguments) != fields:
        return "candidate evidence-map arguments must contain exactly candidate and client_item_ids"
    if not isinstance(arguments.get("candidate"), dict):
        return "candidate evidence-map candidate must be an object"
    mapping = arguments.get("client_item_ids")
    if (
        not isinstance(mapping, dict)
        or not mapping
        or any(not isinstance(key, str) or not key for key in mapping)
        or any(not isinstance(value, str) or not value for value in mapping.values())
    ):
        return "candidate evidence-map client_item_ids must be a non-empty string mapping"
    return None


def _authorized_runtime_run_id() -> str:
    """Resolve the active run only from Host-owned runtime context.

    The MCP caller cannot select a run ID.  Codex injects the environment value
    into this private server, while the immutable mechanics contract is mounted
    at the fixed path.  Requiring their canonical bytes to match binds every
    emitted map to the Adapter-staged run and fails closed on missing, tampered,
    or cross-run context.
    """
    run_id = os.environ.get(RUNTIME_RUN_ID_ENV)
    if not isinstance(run_id, str) or not run_id:
        raise ProtocolRetrievalFallbackError("candidate evidence-map runtime run ID is unavailable")
    descriptor = -1
    try:
        flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
        descriptor = os.open(RUNTIME_CONTEXT_PATH, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o444
        ):
            raise ProtocolRetrievalFallbackError("candidate evidence-map runtime context metadata is invalid")
        payload = bytearray()
        while chunk := os.read(descriptor, 65536):
            payload.extend(chunk)
        actual = bytes(payload)
    except ProtocolRetrievalFallbackError:
        raise
    except OSError as exc:
        raise ProtocolRetrievalFallbackError("candidate evidence-map runtime context is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    expected = protocol_mechanics_contract_bytes(run_id)
    if actual != expected:
        raise ProtocolRetrievalFallbackError("candidate evidence-map runtime context drifts")
    return run_id


def _write_candidate_item_evidence_map(
    evidence_map: dict[str, Any], *, root: Path | None = None
) -> dict[str, Any]:
    """Write one canonical map in the current Protocol work directory.

    ``root`` is private test plumbing; the MCP contract never accepts an output
    path.  A repeated call with identical canonical bytes is idempotent, while
    any content or metadata drift fails closed without replacing the file.
    """
    runtime_root = Path.cwd() if root is None else root
    try:
        runtime_root = runtime_root.resolve(strict=True)
        root_stat = os.lstat(runtime_root)
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise ProtocolRetrievalFallbackError("candidate evidence-map runtime work root is invalid")
        evidence_dir = runtime_root / EVIDENCE_MAP_RELATIVE_PATH.parent
        evidence_dir.mkdir(mode=0o700, exist_ok=True)
        evidence_stat = os.lstat(evidence_dir)
        if (
            stat.S_ISLNK(evidence_stat.st_mode)
            or not stat.S_ISDIR(evidence_stat.st_mode)
            or evidence_stat.st_uid != os.getuid()
        ):
            raise ProtocolRetrievalFallbackError("candidate evidence-map directory is invalid")
        target = runtime_root / EVIDENCE_MAP_RELATIVE_PATH
        canonical = (
            json.dumps(evidence_map, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(target, flags, 0o600)
        except FileExistsError:
            read_flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
            descriptor = -1
            try:
                descriptor = os.open(target, read_flags)
                metadata = os.fstat(descriptor)
                existing = bytearray()
                while chunk := os.read(descriptor, 65536):
                    existing.extend(chunk)
            except OSError as exc:
                raise ProtocolRetrievalFallbackError("candidate evidence-map existing file is unavailable") from exc
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or bytes(existing) != canonical
            ):
                raise ProtocolRetrievalFallbackError("candidate evidence-map already exists with drift")
            return evidence_map
        try:
            offset = 0
            while offset < len(canonical):
                offset += os.write(descriptor, canonical[offset:])
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        return evidence_map
    except ProtocolRetrievalFallbackError:
        raise
    except (OSError, ValueError) as exc:
        raise ProtocolRetrievalFallbackError("candidate evidence-map write failed") from exc


def _validate_arguments(arguments: object) -> str | None:
    if not isinstance(arguments, dict):
        return "tool arguments must be an object"
    if set(arguments) == set(V2_REQUIRED_PROOF_ARGUMENTS):
        if any(
            not isinstance(arguments[name], expected)
            for name, expected in _V2_PROOF_ARGUMENT_TYPES.items()
        ):
            return "tool arguments have invalid v2 proof field types"
        if arguments["mode"] != "create":
            return "mode must equal the exact literal create"
        return None
    if set(arguments) != set(REQUIRED_PROOF_ARGUMENTS):
        return "tool arguments must contain exactly the required proof fields"
    if any(not isinstance(arguments[name], expected) for name, expected in _PROOF_ARGUMENT_TYPES.items()):
        return "tool arguments have invalid proof field types"
    if arguments["mode"] != "create":
        return "mode must equal the exact literal create"
    nested_error = _validate_nested_proof(arguments)
    if nested_error is not None:
        return nested_error
    return None


def _model_association_tool() -> dict[str, Any]:
    return {
        "name": MODEL_ASSOCIATION_TOOL_NAME,
        "description": (
            "R4.0-024 read-only association scan over unchanged governed SPARQL page responses. "
            "Use the mounted fixed query over all authorized asserted graphs, followed by a "
            "bounded final snapshot read. Reports candidates and repairable coverage feedback; "
            "never judges business meaning, writes resources or grants completion."
        ),
        "inputSchema": {
            "type": "object", "additionalProperties": False,
            "required": ["project_id", "ontology_ids", "asserted_graph_iris", "read_pages",
                         "final_read", "semantic_base_iri"],
            "properties": {
                "project_id": {"type": "string", "minLength": 1},
                "ontology_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "asserted_graph_iris": {"type": "array", "items": {"type": "string"},
                                        "minItems": 1},
                "read_pages": {"type": "array", "items": {"type": "object"},
                               "description": "Ordered {request, response} reads; preserve MCP envelopes."},
                "final_read": {"type": "object", "description": "Same fixed query at OFFSET 0, result_limit=1, after the last page."},
                "semantic_base_iri": {"type": "string", "minLength": 1},
                "focus_iris": {"type": "array", "items": {"type": "string"},
                               "description": "Optional approved modeling scope. Omit to inspect all observed business resources; includes existing/shared definitions when applicable."},
            },
        },
    }


def handle(request: object) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return _error(None, -32600, "invalid request")
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _result(
            request_id,
            {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "protocol_mechanics", "version": "1"}},
        )
    if method == "tools/list":
        # R4.0-012: source-tracing publication is no longer an active
        # Protocol capability.  The old builders and proof schema remain
        # importable for historical offline fixtures, but the verifier is not
        # a production MCP capability.  Do not re-open it from an environment
        # variable or an archived Task.
        tools = [_candidate_receipt_tool(), _resource_binding_receipt_tool()]
        tools.append(_translate_candidate_tool())
        tools.append(_model_association_tool())
        if _formal_candidate_gate_enabled():
            tools.insert(1, _candidate_conflict_tool())
        return _result(
            request_id,
            {"tools": tools},
        )
    if method != "tools/call" or not isinstance(params, dict):
        return _error(request_id, -32601, "method or tool is unavailable")
    arguments = params.get("arguments")
    if params.get("name") == MODEL_ASSOCIATION_TOOL_NAME:
        schema = _model_association_tool()["inputSchema"]
        if (not isinstance(arguments, dict) or not set(schema["required"]) <= set(arguments)
                or set(arguments) - set(schema["properties"])):
            return _error(request_id, -32602, "Use the mounted model-check required fields; raw reads are unchanged {request, response} envelopes")
        try:
            scan = inspect_model_associations(**arguments)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            return _error(request_id, -32602, f"Correct the model-check input: {exc}")
        return _result(request_id, {
            "content": [{"type": "text", "text": json.dumps(scan, ensure_ascii=False)}],
            "structuredContent": scan,
        })
    if params.get("name") == CANDIDATE_RECEIPT_TOOL_NAME:
        error = _validate_candidate_receipt_arguments(arguments)
        if error is not None:
            return _error(request_id, -32602, error)
        assert isinstance(arguments, dict)
        candidate = arguments["candidate"]
        assert isinstance(candidate, dict)
        try:
            receipt = build_candidate_receipt(candidate)
        except ProtocolRetrievalFallbackError as exc:
            return _error(request_id, -32012, f"candidate receipt failed: {exc}")
        payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return _result(
            request_id,
            {
                "content": [{"type": "text", "text": payload}],
                "structuredContent": receipt,
            },
        )
    if params.get("name") == RESOURCE_BINDING_RECEIPT_TOOL_NAME:
        error = _validate_resource_binding_receipt_arguments(arguments)
        if error is not None:
            return _error(request_id, -32602, error)
        assert isinstance(arguments, dict)
        candidate = arguments["candidate"]
        read_envelope = arguments["read_envelope"]
        scope = arguments["scope"]
        assert isinstance(candidate, dict) and isinstance(scope, dict)
        try:
            receipt = build_unified_resource_binding_receipt(
                candidate,
                read_envelope,
                project_id=scope["project_id"],
                ontology_id=scope["ontology_id"],
                workspace_version=scope["workspace_version"],
            )
        except ProtocolRetrievalFallbackError as exc:
            return _error(request_id, -32015, f"resource binding receipt failed: {exc}")
        payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return _result(
            request_id,
            {
                "content": [{"type": "text", "text": payload}],
                "structuredContent": receipt,
            },
        )
    if params.get("name") == CANDIDATE_CONFLICT_TOOL_NAME:
        if not _formal_candidate_gate_enabled():
            return _error(request_id, -32601, "method or tool is unavailable")
        error = _validate_candidate_conflict_arguments(arguments)
        if error is not None:
            return _error(request_id, -32602, error)
        assert isinstance(arguments, dict)
        candidate = arguments["candidate"]
        assert isinstance(candidate, dict)
        try:
            conflict = build_candidate_conflict(
                candidate,
                arguments["conflict_code"],
                arguments["conflict_detail"],
            )
        except ProtocolRetrievalFallbackError as exc:
            return _error(request_id, -32013, f"candidate conflict failed: {exc}")
        payload = json.dumps(conflict, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return _result(
            request_id,
            {
                "content": [{"type": "text", "text": payload}],
                "structuredContent": conflict,
            },
        )
    if params.get("name") == EVIDENCE_MAP_TOOL_NAME:
        # Keep the historical name recognizable so callers receive the normal
        # unknown-tool contract rather than accidentally writing a map.
        return _error(request_id, -32601, "method or tool is unavailable")
    if params.get("name") == TRANSLATE_CANDIDATE_TOOL_NAME:
        error = _validate_translate_candidate_arguments(arguments)
        if error is not None:
            return _error(request_id, -32602, error)
        assert isinstance(arguments, dict)
        candidate = arguments["candidate"]
        assert isinstance(candidate, dict)
        try:
            if set(arguments) == {"candidate"}:
                plan = translate_candidate_to_batches(candidate)
            else:
                plan = translate_candidate_to_batches(
                    candidate,
                    arguments.get("existing_binding_receipt"),
                    requirement_id=arguments.get("requirement_id"),
                    deletion_impact_receipts=arguments.get("deletion_impact_receipts"),
                    phase_a_readback=arguments.get("phase_a_readback", False),
                    semantic_base_iri=arguments.get("semantic_base_iri"),
                )
        except ProtocolRetrievalFallbackError as exc:
            return _error(request_id, -32014, f"candidate translation failed: {exc}")
        payload = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return _result(
            request_id,
            {
                "content": [{"type": "text", "text": payload}],
                "structuredContent": plan,
            },
        )
    # The native proof verifier is retained only as an offline helper.  It is
    # deliberately unavailable through this production facade for every
    # environment and every historical Task configuration.
    if params.get("name") == TOOL_NAME:
        return _error(request_id, -32601, "method or tool is unavailable")
    return _error(request_id, -32601, "method or tool is unavailable")


def main() -> int:
    for line in sys.stdin:
        try:
            response = handle(json.loads(line))
        except json.JSONDecodeError:
            response = _error(None, -32700, "parse error")
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
