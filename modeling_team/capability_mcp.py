"""Runner-private capability broker and its stdio MCP client.

The broker is intentionally separate from Team Transport.  A private Unix
socket authenticates one opaque, task-scoped token and dispatches only the fixed
operations for Protocol, Coordinator, or Acceptance.  The small stdio facade is
the MCP client registered in those Agent configs; it never receives a raw carrier
or platform socket.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import socket
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any


# One lock shared across every role endpoint so concurrent role threads can
# append to a single shared audit log without interleaving partial lines.
_AUDIT_LOCK = threading.Lock()


COORDINATOR_OPERATIONS: tuple[str, ...] = (
    "coordinator_ticket_draft",
    "coordinator_publish_acceptance_ticket",
    "coordinator_get_verdict",
)
COORDINATOR_FORMAL_OPERATIONS: tuple[str, ...] = (
    *COORDINATOR_OPERATIONS,
    "coordinator_ticket_draft_from_delivery",
)
PROTOCOL_OPERATIONS: tuple[str, ...] = (
    "protocol_list_platform_artifacts",
    "protocol_build_acceptance_stage_handoff",
    "protocol_build_candidate_receipt",
    "protocol_build_candidate_conflict",
)
PROTOCOL_STAGE_OPERATIONS: tuple[str, ...] = PROTOCOL_OPERATIONS[:2]
# R3.0-008B: the staged protocol role additionally owns the Runner-private
# Modeling Batch submission capability.  The role registry carries the full
# superset so the dispatcher can validate it; every endpoint assembly still
# picks its exact operation set, so non-staged endpoints never configure the
# staged operation.
STAGED_PROTOCOL_OPERATION = "protocol_staged_submit_modeling_batch"
# Historical name retained for reading old run manifests.  R4.0-012 removes
# the operation from every active capability surface; it is deliberately not
# included in the active operation tuple or schema registry below.
STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION = "protocol_staged_associate_evidence"
STAGED_PROTOCOL_RUN_OPERATIONS: tuple[str, ...] = (
    STAGED_PROTOCOL_OPERATION,
)
UNIFIED_PROTOCOL_RUN_OPERATIONS: tuple[str, ...] = (
    *STAGED_PROTOCOL_RUN_OPERATIONS,
    "protocol_execute_approved_plans",
    "protocol_inspect_associations",
    "protocol_check_plan_coverage",
)
STAGED_PROTOCOL_OPERATIONS: tuple[str, ...] = (*PROTOCOL_OPERATIONS, *STAGED_PROTOCOL_RUN_OPERATIONS)
# R4.0-024: a staged unified surface also advertises the existing artifact
# listing capability.  ``protocol_inspect_associations`` resolves read refs
# only from Runner-observed platform records, so Protocol must be able to
# discover canonical ``artifact_path`` values instead of transcribing pages or
# inventing aliases.  Kept duplicate-free so a formal assembly that already
# includes ``PROTOCOL_OPERATIONS`` never lists one operation twice.
STAGED_UNIFIED_PROTOCOL_OPERATIONS: tuple[str, ...] = (
    *UNIFIED_PROTOCOL_RUN_OPERATIONS,
    "protocol_list_platform_artifacts",
)
UNIFIED_PROTOCOL_OPERATIONS: tuple[str, ...] = (*PROTOCOL_OPERATIONS, *UNIFIED_PROTOCOL_RUN_OPERATIONS)
MODELING_OPERATIONS: tuple[str, ...] = ("modeling_publish_staged_candidate",)
DIRECT_MODELING_OPERATIONS: tuple[str, ...] = (
    "modeling_submit_model_changes", "modeling_inspect_associations", "modeling_finish_changes",
)
ACCEPTANCE_OPERATIONS: tuple[str, ...] = (
    "acceptance_get_ticket",
    "acceptance_child_start",
    "acceptance_child_get_report",
    "acceptance_child_recycle",
    "acceptance_get_failure_record",
    "build_acceptance_verdict",
    "submit_acceptance_result",
    "acceptance_get_verdict",
)
ROLE_OPERATIONS: dict[str, tuple[str, ...]] = {
    # The endpoint narrows this list for legacy carriers.  Keeping the formal
    # operation in the role registry lets the dispatcher validate it without
    # advertising the delivery-bound capability to an unbound carrier.
    "coordinator": COORDINATOR_FORMAL_OPERATIONS,
    "modeling": (*MODELING_OPERATIONS, *DIRECT_MODELING_OPERATIONS),
    "protocol": UNIFIED_PROTOCOL_OPERATIONS,
    "acceptance": ACCEPTANCE_OPERATIONS,
}

# R3.0-011: the competency-question role owns exactly one Runner-private
# capability.  It is registered here so the dispatcher can validate it, while
# only a run that selected ``competency_question_acceptance`` assembles an
# endpoint that advertises it (no production role ever sees this operation).
COMPETENCY_QUESTION_ROLE = "competency-question"
CQ_OPERATION = "cq_publish_question_draft"
CQ_OPERATIONS: tuple[str, ...] = (
    CQ_OPERATION, "write_handoff_output", "publish_handoff_material",
    "list_handoff_material", "read_handoff_material",
)
ROLE_OPERATIONS[COMPETENCY_QUESTION_ROLE] = CQ_OPERATIONS


CAPABILITY_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "modeling_submit_model_changes": {
        "type": "object", "properties": {
            "modeling_id": {"type": "string"},
            "request_edits": {
                "type": "array", "minItems": 1,
                "description": "Explicit JSON Patch operations on request_ref only. Correct the "
                    "retained request without regenerating unchanged contents. No implicit repair.",
                "items": {"type": "object", "properties": {
                    "op": {"type": "string", "enum": ["add", "replace", "remove", "move"]},
                    "path": {"type": "string", "description": "JSON Pointer in the request body."},
                    "from": {"type": "string"},
                    "value": {"type": ["string", "number", "boolean", "object", "array", "null"]},
                }, "required": ["op", "path"], "additionalProperties": False},
            },
            "placement_ref": {
                "type": ["object", "null"], "required": ["artifact_ref", "path"],
                "properties": {key: {"type": "string", "minLength": 1} for key in ("artifact_ref", "path")},
                "additionalProperties": False,
                "description": "Copy a confirmed ontology-plan placement_ref from the Host notification; optional for existing unambiguous placement.",
            },
            "request": {"type": "object", "properties": {
                "schema_version": {"type": "string", "enum": ["r4-3-025-model-changes/v1"]},
                "candidate_ref": {"type": ["string", "null"]},
                "changes": {"type": "array", "minItems": 1, "items": {"type": "object"}},
            }, "required": ["schema_version", "candidate_ref", "changes"], "additionalProperties": False},
        }, "required": ["modeling_id"],
        "additionalProperties": False,
    },
    "modeling_inspect_associations": {
        "type": "object", "properties": {
            "modeling_id": {"type": "string"},
            "focus_iris": {"type": "array", "items": {"type": "string"}},
        }, "required": ["modeling_id"], "additionalProperties": False,
    },
    "modeling_finish_changes": {
        "type": "object", "properties": {"modeling_id": {"type": "string"}},
        "required": ["modeling_id"], "additionalProperties": False,
    },
    "modeling_publish_staged_candidate": {
        "type": "object",
        "properties": {"modeling_id": {"type": "string"}},
        "required": ["modeling_id"],
        "additionalProperties": False,
    },
    "protocol_list_platform_artifacts": {
        "type": "object",
        "properties": {"protocol_id": {"type": "string"}},
        "required": ["protocol_id"],
        "additionalProperties": False,
    },
    "protocol_build_acceptance_stage_handoff": {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            # stage_calls is intentionally optional: when omitted, the carrier
            # auto-selects the three canonical final-state observed calls.  When
            # supplied, each stage must still exact-match one observed call.
            "stage_calls": {
                "type": "object",
                "properties": {
                    stage: {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string"},
                            "arguments": {"type": "object"},
                            "artifact_path": {"type": "string"},
                        },
                        "required": ["tool", "arguments", "artifact_path"],
                        "additionalProperties": False,
                    }
                    for stage in ("dry-run", "apply", "readback")
                },
                "required": ["dry-run", "apply", "readback"],
                "additionalProperties": False,
            },
        },
        "required": ["protocol_id"],
        "additionalProperties": False,
    },
    "protocol_build_candidate_receipt": {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "delivery_id": {"type": "string"},
        },
        "required": ["protocol_id", "delivery_id"],
        "additionalProperties": False,
    },
    "protocol_build_candidate_conflict": {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "delivery_id": {"type": "string"},
            "conflict_code": {"type": "string"},
            "conflict_detail": {"type": "string"},
        },
        "required": ["protocol_id", "delivery_id", "conflict_code", "conflict_detail"],
        "additionalProperties": False,
    },
    "protocol_staged_submit_modeling_batch": {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            # ``batch`` mirrors the real submit_modeling_batch envelope
            # (session_id, client_batch_id, ontology_id, idempotency_key,
            # expected_model_revision, items[{command_kind, payload}],
            # mode, lease_token).  value_traces and l3_nodes are Runner-side
            # trace attachments and are never forwarded to the backend.
            "batch": {"type": "object"},
            "value_traces": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "command_index": {"type": "integer", "minimum": 0},
                        "conclusion_id": {"type": "string"},
                        "mapped_property": {"type": "string"},
                    },
                    "required": ["command_index", "conclusion_id"],
                    "additionalProperties": False,
                },
            },
            "l3_nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "command_index": {"type": "integer", "minimum": 0},
                        "entity_id": {"type": "string"},
                        "semantic_value_iri": {"type": "string"},
                    },
                    "required": ["command_index", "entity_id", "semantic_value_iri"],
                    "additionalProperties": False,
                },
            },
            # R3.0-009 adds ``plan_ref`` to the submission arguments, so the
            # advertised schema must not reject a contract-correct 009 request
            # before dispatch.  It stays optional here: the Runner contract
            # still owns the 009 requirement, the run-relative path rule, the
            # plan re-read and the approval checks, and 008B runs submit with
            # no ``plan_ref`` at all.
            "plan_ref": {"type": "string"},
        },
        "required": ["protocol_id", "batch", "value_traces", "l3_nodes"],
        "additionalProperties": False,
    },
    "protocol_execute_approved_plans": {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "mode": {"type": "string", "enum": ["apply_atomic"],
                     "default": "apply_atomic"},
            "plan_refs": {"type": "array", "minItems": 1, "uniqueItems": True,
                          "items": {"type": "string"}},
            "lease_tokens": {"type": "object", "additionalProperties": {"type": "string"}},
            "trace_attachments": {"type": "object", "additionalProperties": {
                "type": "object", "properties": {
                    "value_traces": {"type": "array", "items": {"type": "object"}},
                    "l3_nodes": {"type": "array", "items": {"type": "object"}},
                }, "additionalProperties": False,
            }},
        },
        "required": ["protocol_id", "plan_refs", "lease_tokens"],
        "additionalProperties": False,
    },
    "protocol_inspect_associations": {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "project_id": {"type": "string"},
            "ontology_ids": {"type": "array", "items": {"type": "string"}},
            "read_refs": {"type": "array", "items": {"type": "string"}},
            "final_read_ref": {"type": "string"},
            "semantic_base_iri": {"type": "string"},
            "focus_iris": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["protocol_id", "project_id", "ontology_ids", "read_refs",
                     "final_read_ref", "semantic_base_iri"],
        "additionalProperties": False,
    },
    "protocol_check_plan_coverage": {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "candidate_ref": {"type": "string"},
            "plan_refs": {"type": "array", "items": {"type": "string"}},
            "dispositions": {"type": "array", "items": {
                "type": "object", "properties": {
                    "candidate_item_id": {"type": "string"},
                    "disposition": {"type": "string", "enum": ["unknown", "out_of_scope", "deferred"]},
                    "reason": {"type": "string"},
                }, "required": ["candidate_item_id", "disposition", "reason"],
                "additionalProperties": False,
            }},
        },
        "required": ["protocol_id", "candidate_ref", "plan_refs", "dispositions"],
        "additionalProperties": False,
    },
    "coordinator_ticket_draft": {
        "type": "object",
        "properties": {
            "coordinator_id": {"type": "string"},
            "handoff_delivery_id": {"type": "string"},
            "handoff_json": {"type": "object"},
            "handoff_digest": {"type": "string"},
            "question_id": {"type": "string"},
            "ticket_revision": {"type": "integer", "minimum": 1},
        },
        "required": [
            "coordinator_id",
            "handoff_delivery_id",
            "handoff_json",
            "handoff_digest",
            "question_id",
            "ticket_revision",
        ],
        "additionalProperties": False,
    },
    "coordinator_ticket_draft_from_delivery": {
        "type": "object",
        "properties": {
            "coordinator_id": {"type": "string"},
            "handoff_delivery_id": {"type": "string"},
            "question_id": {"type": "string"},
            "ticket_revision": {"type": "integer", "minimum": 1},
        },
        "required": [
            "coordinator_id",
            "handoff_delivery_id",
            "question_id",
            "ticket_revision",
        ],
        "additionalProperties": False,
    },
    "coordinator_publish_acceptance_ticket": {
        "type": "object",
        "properties": {
            "coordinator_id": {"type": "string"},
            "ticket_json": {"type": "object"},
            "ticket_digest": {"type": "string"},
            "requirement_ref": {"type": "string"},
            "owner_revision": {"type": "string"},
        },
        "required": [
            "coordinator_id",
            "ticket_json",
            "ticket_digest",
            "requirement_ref",
            "owner_revision",
        ],
        "additionalProperties": False,
    },
    "coordinator_get_verdict": {
        "type": "object",
        "properties": {
            "coordinator_id": {"type": "string"},
            "acceptance_round_id": {"type": "string"},
            "verdict_digest": {"type": ["string", "null"]},
        },
        "required": ["coordinator_id", "acceptance_round_id", "verdict_digest"],
        "additionalProperties": False,
    },
    "acceptance_get_ticket": {
        "type": "object",
        "properties": {
            "acceptance_id": {"type": "string"},
            "round_id": {"type": "string"},
        },
        "required": ["acceptance_id", "round_id"],
        "additionalProperties": False,
    },
    "acceptance_child_start": {
        "type": "object",
        "properties": {
            "acceptance_id": {"type": "string"},
            "round_id": {"type": "string"},
            "kind": {"type": "string", "enum": ["source", "platform"]},
            "request_id": {"type": "string"},
            # ticket_digest and attempt are accepted-but-ignored: the Host derives
            # both from the immutable round/ticket state.  Retained as optional
            # properties so a careful caller may pass them as a sanity check, but
            # the schema no longer requires them and the dispatcher never reads them.
            "ticket_digest": {"type": "string"},
            "attempt": {"type": "integer", "enum": [0, 1]},
        },
        "required": ["acceptance_id", "round_id", "kind", "request_id"],
        "additionalProperties": False,
    },
    "acceptance_child_get_report": {
        "type": "object",
        "properties": {
            "acceptance_id": {"type": "string"},
            "round_id": {"type": "string"},
            "child_handle": {"type": "string"},
            "request_id": {"type": "string"},
        },
        "required": ["acceptance_id", "round_id", "child_handle", "request_id"],
        "additionalProperties": False,
    },
    "acceptance_child_recycle": {
        "type": "object",
        "properties": {
            "acceptance_id": {"type": "string"},
            "round_id": {"type": "string"},
            "child_handle": {"type": "string"},
            "completion_ref": {
                "oneOf": [
                    {
                        "title": "terminal-report-digest",
                        "type": "object",
                        "properties": {"terminal_report_digest": {"type": "string"}},
                        "required": ["terminal_report_digest"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "infrastructure-failure-digest",
                        "type": "object",
                        "properties": {"infrastructure_failure_digest": {"type": "string"}},
                        "required": ["infrastructure_failure_digest"],
                        "additionalProperties": False,
                    },
                ]
            },
            "request_id": {"type": "string"},
        },
        "required": ["acceptance_id", "round_id", "child_handle", "completion_ref", "request_id"],
        "additionalProperties": False,
    },
    "acceptance_get_failure_record": {
        "type": "object",
        "properties": {
            "acceptance_id": {"type": "string"},
            "round_id": {"type": "string"},
            "failure_digest": {"type": "string"},
        },
        "required": ["acceptance_id", "round_id", "failure_digest"],
        "additionalProperties": False,
    },
    "build_acceptance_verdict": {
        "type": "object",
        # The Acceptance agent supplies ONLY simple judgment content plus the
        # acceptance/round identifiers.  Every mechanical field (schema_version,
        # ticket-copied bindings, modeling receipts, report digests, failure
        # evidence refs/digests, model state, verdict digest, typed evidence-ref
        # structures, the checks key set, and the CQ id) is Host-derived from
        # the bound ticket, examiner reports, and tracked failures.  Deep
        # validation of these judgment objects lives in the carrier's
        # ``build_acceptance_verdict``/``validate_verdict``; the schema only
        # accepts their top-level shape.
        "properties": {
            "acceptance_id": {"type": "string"},
            "round_id": {"type": "string"},
            "verdict": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED"]},
            "failure_layer": {"type": ["string", "null"]},
            "blocked_reason": {"type": ["string", "null"]},
            "evidence_ref_ids": {
                "type": "array",
                # Evidence REF_IDS, not typed refs and not locators.  Each item
                # is a ref_id string copied verbatim from one of the two
                # Examiner terminal reports (source ``approved-source-...``
                # prefixes, platform reader-chosen ids).  The Host lifts the
                # fully-typed bound ref verbatim from the report it came from
                # and completes page chains by (tool, request_digest) group;
                # the agent never supplies typed-ref digests, paths, page
                # fields, or ticket/state bindings.
                "items": {"type": "string"},
            },
            "checks": {
                # The flat eight-key mapping of CHECK_KEYS to a PASS/FAIL/
                # BLOCKED verdict.  The Host owns the key set and rejects any
                # drift; only the verdict-per-check value is the agent's
                # judgment.
                "type": "object",
            },
            "competency_question_results": {
                "type": "array",
                # Each item carries ONLY {status, answer, evidence_ref_ids}
                # where evidence_ref_ids are ref_id strings (see above).  The
                # Host fills the ticket-bound question id and lifts the typed
                # evidence refs.
                "items": {"type": "object"},
            },
            "recommended_action": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": [
            "acceptance_id",
            "round_id",
            "verdict",
            "failure_layer",
            "blocked_reason",
            "evidence_ref_ids",
            "checks",
            "competency_question_results",
            "recommended_action",
            "summary",
        ],
        "additionalProperties": False,
    },
    "submit_acceptance_result": {
        "type": "object",
        # The Acceptance agent supplies ONLY simple judgment content plus the
        # acceptance/round identifiers and a fresh request_id: evidence ref_ids
        # (strings copied from the examiner reports, not typed refs), the
        # eight-key checks mapping (not the wrapped structure), and CQ
        # status/answer/ref_ids (the Host fills the CQ id).  The Host assembles
        # the 28-field verdict envelope (the same deterministic assembly
        # ``build_acceptance_verdict`` performs), validates it through
        # ``validate_verdict``, and records the receipt internally.  The large
        # ``verdict_json`` never transits the codex CLI tool-result, so it
        # cannot be display-truncated or re-typed by the agent; the agent
        # relays only judgment, never the assembled verdict bytes.  Deep
        # validation of these judgment objects lives in the carrier's
        # ``build_acceptance_verdict``/``validate_verdict``; the schema only
        # accepts their top-level shape.
        "properties": {
            "acceptance_id": {"type": "string"},
            "round_id": {"type": "string"},
            "verdict": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED"]},
            "failure_layer": {"type": ["string", "null"]},
            "blocked_reason": {"type": ["string", "null"]},
            "evidence_ref_ids": {
                "type": "array",
                # Evidence REF_IDS (see build_acceptance_verdict for the
                # ref_id contract).  The Host lifts every typed ref verbatim
                # from the examiner report it came from.
                "items": {"type": "string"},
            },
            "checks": {
                # The flat eight-key CHECK_KEYS -> PASS/FAIL/BLOCKED mapping.
                "type": "object",
            },
            "competency_question_results": {
                "type": "array",
                # Each item carries ONLY {status, answer, evidence_ref_ids
                # (ref_id strings)}; the Host fills the question id.
                "items": {"type": "object"},
            },
            "recommended_action": {"type": "string"},
            "summary": {"type": "string"},
            "request_id": {"type": "string"},
        },
        "required": [
            "acceptance_id",
            "round_id",
            "verdict",
            "failure_layer",
            "blocked_reason",
            "evidence_ref_ids",
            "checks",
            "competency_question_results",
            "recommended_action",
            "summary",
            "request_id",
        ],
        "additionalProperties": False,
    },
    "acceptance_get_verdict": {
        "type": "object",
        "properties": {
            "acceptance_id": {"type": "string"},
            "round_id": {"type": "string"},
            "verdict_digest": {"type": "string"},
        },
        "required": ["acceptance_id", "round_id", "verdict_digest"],
        "additionalProperties": False,
    },
}

# R3.0-011: the competency-question draft publication capability.  The draft
# object's exact fields and its question records are validated mechanically by
# the Runner (``modeling_team.competency_questions``), so the advertised schema
# only fixes the envelope: one ``draft`` object, nothing else.
CAPABILITY_TOOL_SCHEMAS[CQ_OPERATION] = {
    "type": "object",
    "properties": {
        "cq_id": {"type": "string"},
        "draft": {"type": "object", "description": (
            "Formal review uses phase panorama-review or slice-review. Preparation phases "
            "panorama-draft/slice-draft save a private draft only and return preparation_saved; "
            "republish with the returned review_phase before waiting for Host approval."
        )},
        "body_ref": {"type": "object"},
        "material_refs": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["cq_id"],
    "additionalProperties": False,
}


if __package__:
    from .direct_modeling import model_change_item_schema
    from .handoff_materials import HANDOFF_TOOL_SPECS, REF_SCHEMA

    CAPABILITY_TOOL_SCHEMAS["modeling_submit_model_changes"]["properties"]["request"]["properties"]["changes"]["items"] = model_change_item_schema()
    CAPABILITY_TOOL_SCHEMAS["modeling_submit_model_changes"]["properties"]["request_ref"] = {
        **REF_SCHEMA,
        "description": (
            "Complete request JSON published by this Modeling agent to recipient runner using "
            "publish_handoff_material. Supply exactly one of request or request_ref. "
            "Use the returned material_id; path selects a directory's file member. "
            "The program reads the immutable full request without model transcription."
        ),
    }
    CAPABILITY_TOOL_SCHEMAS.update({spec["name"]: spec["inputSchema"] for spec in HANDOFF_TOOL_SPECS})


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {key: _jsonable(child) for key, child in dataclasses.asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _text_content(value: Any) -> list[dict[str, str]]:
    return [{"type": "text", "text": json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)}]


def _matches_schema(value: Any, schema: Mapping[str, Any]) -> bool:
    """Small deterministic validator for the fixed capability input schemas."""

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        return sum(
            1
            for option in one_of
            if isinstance(option, Mapping) and _matches_schema(value, option)
        ) == 1

    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected]
    valid_type = False
    for candidate in types:
        if candidate == "object" and isinstance(value, Mapping):
            valid_type = True
        elif candidate == "string" and isinstance(value, str):
            valid_type = True
        elif candidate == "integer" and isinstance(value, int) and not isinstance(value, bool):
            valid_type = True
        elif candidate == "array" and isinstance(value, (list, tuple)) and not isinstance(value, str):
            valid_type = True
        elif candidate == "boolean" and isinstance(value, bool):
            valid_type = True
        elif candidate == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            valid_type = True
        elif candidate == "null" and value is None:
            valid_type = True
    if not valid_type:
        return False
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        return False
    minimum = schema.get("minimum")
    if isinstance(minimum, (int, float)) and (
        not isinstance(value, (int, float)) or value < minimum
    ):
        return False
    if isinstance(value, (list, tuple)) and not isinstance(value, (str, Mapping)):
        # ``items`` is optional: when omitted any array element is accepted and
        # the owning capability performs the structural validation.  This keeps
        # the schema validator deterministic for the judgment arrays (evidence
        # locators, competency-question results) without duplicating the deep
        # contract checks that live in the carrier.
        items = schema.get("items")
        if isinstance(items, Mapping):
            return all(_matches_schema(item, items) for item in value)
        return True
    if isinstance(value, Mapping):
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        if properties or required:
            if not required.issubset(value):
                return False
            if schema.get("additionalProperties") is False and not set(value).issubset(properties):
                return False
            return all(
                key in properties and _matches_schema(child, properties[key])
                for key, child in value.items()
            )
    return True


class RunnerCapabilityEndpoint:
    """One role-bound, token-authenticated Unix socket endpoint."""

    def __init__(
        self,
        *,
        role: str,
        socket_path: Path,
        token: str,
        dispatch: Callable[[str, str, Mapping[str, Any]], Any],
        operations: tuple[str, ...] | None = None,
        audit_path: Path | None = None,
    ) -> None:
        if role not in ROLE_OPERATIONS:
            raise ValueError("unknown Runner capability role")
        self.role = role
        self.socket_path = socket_path
        self.token = token
        configured = ROLE_OPERATIONS[role] if operations is None else tuple(operations)
        if not configured or not set(configured).issubset(ROLE_OPERATIONS[role]):
            raise ValueError("Runner capability operations are not role-owned")
        self.operations = configured
        self._dispatch = dispatch
        # Runner-private audit sink.  When set, every ``tools/call`` outcome is
        # appended here with the *original* exception type/message so a debugger
        # or independent acceptance reader can see why a capability call failed
        # even when the JSON-RPC response stays opaque (-32001) or carries only
        # a structured diagnostic.  Agent processes never read this file.
        self._audit_path: Path | None = Path(audit_path) if audit_path is not None else None
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def descriptor(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "operations": list(self.operations),
            "token_digest": token_digest(self.token),
            "socket_mode": "0600",
        }

    def start(self) -> None:
        if self._server is not None:
            return
        self.socket_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.socket_path.is_symlink() or self.socket_path.exists():
            raise RuntimeError("Runner capability socket already exists")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            server.listen(8)
        except Exception:
            server.close()
            self.socket_path.unlink(missing_ok=True)
            raise
        self._server = server
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name=f"runner-capability-{self.role}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        server, self._server = self._server, None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)
        self.socket_path.unlink(missing_ok=True)

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        while not self._stop.is_set():
            try:
                connection, _ = server.accept()
            except OSError:
                return
            with connection:
                try:
                    connection.settimeout(10)
                    line = connection.makefile("r", encoding="utf-8").readline(1_048_577)
                    if not line or len(line) > 1_048_576:
                        raise ValueError
                    request = json.loads(line)
                    response = self.handle(request)
                except Exception:
                    response = self._error(None)
                try:
                    connection.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
                except OSError:
                    pass

    def _error(self, request_id: Any) -> dict[str, Any]:
        # The ``-32001`` error is deliberately opaque: unrelated token, schema,
        # and dispatch failures must remain indistinguishable to the caller.
        # A structured diagnostic an Agent must act on (e.g. a stage-handoff
        # ``no_match`` payload) is returned on the success path with
        # ``structuredContent`` ``{ok: False, error: ...}`` from ``handle``;
        # the codex CLI MCP client wrapper strips ``error.data`` when it
        # re-wraps a JSON-RPC error as a flat ``"Mcp error"`` string, so a
        # diagnostic placed on the error path would never reach the Agent.
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32001, "message": "Runner capability request rejected"},
        }

    def _audit(
        self,
        operation: Any,
        ok: bool,
        *,
        error_type: str | None = None,
        error_message: str | None = None,
        diagnostic: Mapping[str, Any] | None = None,
    ) -> None:
        # Runner-private debugging/acceptance trail.  This is NOT the
        # Agent-visible response channel: it records the original exception
        # type/message for every ``tools/call`` outcome so a later debugger or
        # independent reader can recover the exact reason a capability call
        # failed, even when ``handle`` returned an opaque ``-32001`` (which by
        # contract hides token/schema/dispatch failures from the caller).
        if self._audit_path is None:
            return
        record: dict[str, Any] = {
            "role": self.role,
            "operation": operation if isinstance(operation, str) else None,
            "ok": ok,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        if error_type is not None:
            record["error_type"] = error_type
        if error_message is not None:
            record["error_message"] = error_message
        if diagnostic is not None:
            record["diagnostic"] = dict(diagnostic)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        try:
            with _AUDIT_LOCK:
                self._audit_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._audit_path, "a", encoding="utf-8") as handle:
                    handle.write(line)
        except OSError:
            # The audit trail must never break a live capability call.
            return

    def handle(self, request: Any) -> dict[str, Any]:
        activity = getattr(self, "activity", None)
        if activity is not None and isinstance(request, Mapping) and request.get("method") == "tools/call":
            from uuid import uuid4
            name = (request.get("params") or {}).get("name")
            return activity.execute_tool("mcp:" + uuid4().hex, str(name),
                                         lambda: self._handle_request(request))
        return self._handle_request(request)

    def _handle_request(self, request: Any) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            return self._error(None)
        request_id = request.get("id")
        if request.get("token") != self.token:
            return self._error(request_id)
        method = request.get("method")
        if method == "tools/list":
            protocol_descriptions = {
                "modeling_submit_model_changes": (
                    "Submit exactly one of inline request or request_ref for the complete request JSON "
                    "published to runner. Prefer request_ref for an already prepared request; do not "
                    "retype its contents. candidate_ref selects a candidate, not a request document. "
                    "After a static rejection, use correction.request_ref and explicitly selected "
                    "request_edits (add/replace/remove/move) instead of rebuilding the whole request. "
                    "The program compiles, binds real execution context and calls apply_atomic once "
                    "per batch. No command plan, technical identity, dry-run or Protocol approval. "
                    "Optional placement_ref selects one Host-confirmed frozen plan entry for fields-only creation. "
                    "Trust applied receipts; reconcile uncertain original requests."
                ),
                "modeling_inspect_associations": (
                    "Read this run's complete authorized asserted graph with existing governed "
                    "pagination and return deterministic association candidates for business review. "
                    "Preserves partial/forbidden/drift feedback; no write or semantic verdict."
                ),
                "modeling_finish_changes": "Complete owned Build Sessions and release leases before final production handoff.",
                "protocol_execute_approved_plans": (
                    "Execute retained immutable plan_refs with apply_atomic and current-version "
                    "validation inside that apply. Model dry-run execution and translation-proof "
                    "prerequisites are retired. Confirmed applied receipts allow dependency-ordered "
                    "continuation without per-batch full resource comparisons. Resource readback and "
                    "semantic verdict remain not_evaluated; business feedback and final association "
                    "checks use actual governed reads."
                ),
                "protocol_staged_submit_modeling_batch": (
                    "Legacy/manual inline staged batch submission. Unified plans should use "
                    "protocol_execute_approved_plans with apply_atomic, "
                    "to preserve every approved item field without transcription. For a receipted "
                    "applying/recovering Attempt, continue the exact retained original batch "
                    "through this tool with unchanged session, key, payload, version and lease; "
                    "terminal Attempts are not replayed."
                ),
            }
            tools = [
                {
                    "name": operation,
                    "description": protocol_descriptions.get(
                        operation, f"Runner-private {self.role} capability"
                    ),
                    "inputSchema": CAPABILITY_TOOL_SCHEMAS[operation],
                }
                for operation in self.operations
            ]
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}
        if method != "tools/call":
            return self._error(request_id)
        params = request.get("params")
        if not isinstance(params, Mapping):
            return self._error(request_id)
        operation = params.get("name")
        arguments = params.get("arguments", {})
        schema = CAPABILITY_TOOL_SCHEMAS.get(str(operation))
        if operation == "modeling_submit_model_changes" and schema is not None:
            schema = json.loads(json.dumps(schema))
            schema["properties"]["request"]["properties"]["changes"]["items"] = {"type": "object"}
            # Deep input errors need actionable not_written feedback from the owner,
            # rather than the opaque cross-role capability rejection.
            schema["properties"]["request_edits"]["items"] = {"type": "object"}
        if (
            operation not in self.operations
            or schema is None
            or not isinstance(arguments, Mapping)
            or not _matches_schema(arguments, schema)
        ):
            self._audit(operation, False, error_type="schema_or_operation_rejected")
            return self._error(request_id)
        try:
            result = _jsonable(self._dispatch(self.role, str(operation), arguments))
        except Exception as exc:
            # A dispatch may choose to expose a structured diagnostic (e.g. the
            # stage-handoff ``no_match`` payload) by raising with a Mapping
            # ``data`` attribute.  Route it through a *successful* JSON-RPC
            # result with ``structuredContent`` ``{ok: False, error: ...}`` and a
            # readable text block: the codex CLI MCP client wrapper re-wraps a
            # JSON-RPC error as ``"Mcp error: <code>: <message>"`` and strips
            # ``error.data`` along the way, so a diagnostic on the error path
            # never reaches the Agent.  A plain exception (no Mapping ``data``)
            # and every protocol/schema/token rejection keep the opaque
            # ``-32001`` error below so unrelated failures stay indistinguishable.
            payload = getattr(exc, "data", None)
            if not isinstance(payload, Mapping):
                self._audit(
                    operation,
                    False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                return self._error(request_id)
            diagnostic: dict[str, Any] = dict(payload)
            self._audit(
                operation,
                False,
                error_type=type(exc).__name__,
                error_message=str(exc),
                diagnostic=diagnostic,
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "structuredContent": {"ok": False, "error": diagnostic},
                    "content": _text_content({"ok": False, "error": diagnostic}),
                },
            }
        self._audit(operation, True)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"structuredContent": {"ok": True, "data": result}, "content": _text_content(result)},
        }


_CAPABILITY_CONNECT_TIMEOUT_SECONDS = 15.0


def _stdio_request(socket_path: str, token: str, request: Mapping[str, Any]) -> dict[str, Any]:
    payload = {**dict(request), "token": token}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        # Keep endpoint connection and request writes bounded.  A capability
        # may be applying a model change while the response is pending; the
        # native MCP/session budget owns that wait, so a shorter local read
        # timeout would let the apply continue after the caller lost its ID.
        connection.settimeout(_CAPABILITY_CONNECT_TIMEOUT_SECONDS)
        connection.connect(socket_path)
        connection.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        connection.settimeout(None)
        line = connection.makefile("r", encoding="utf-8").readline(1_048_577)
    value = json.loads(line)
    return value if isinstance(value, dict) else {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32001, "message": "Runner capability request rejected"}}


def run_stdio_client(socket_path: str, token_file: Path, *, stdin: Any = None, stdout: Any = None) -> int:
    """Serve MCP JSON-RPC over stdio while forwarding to one private endpoint."""

    import sys

    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except OSError:
        return 2
    if not token:
        return 2
    for line in input_stream:
        request_id: Any = None
        try:
            request = json.loads(line)
            if not isinstance(request, Mapping):
                continue
            method = request.get("method")
            request_id = request.get("id")
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "runner-capability", "version": "1"},
                    },
                }
            elif isinstance(method, str) and method.startswith("notifications/"):
                continue
            else:
                response = _stdio_request(socket_path, token, request)
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()
        except Exception:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32001, "message": "Runner capability request rejected"},
            }
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()
    return 0


ROLE_MATERIAL_TOOL = {
    "name": "read_role_material",
    "description": "Read frozen original role material by manifest ID; follow next_offset until read_complete.",
    "inputSchema": {"type": "object", "properties": {
        "material_id": {"type": "string"}, "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1, "maximum": 16384}},
        "required": ["material_id"], "additionalProperties": False},
}


def read_role_material(manifest: Mapping[str, Any], arguments: Mapping[str, Any]) -> dict:
    """Only frozen IDs resolve to files. Offsets/limits count Unicode characters."""
    if not _matches_schema(arguments, ROLE_MATERIAL_TOOL["inputSchema"]):
        raise ValueError("invalid material arguments; use manifest material_id and bounded offset/limit")
    item = manifest.get(arguments["material_id"])
    if not isinstance(item, dict):
        raise ValueError("material not authorized; use a material_id from this role's manifest")
    path = Path(item["file"])
    if path.is_symlink():
        raise ValueError("material changed; request Host manifest repair")
    payload = path.read_bytes()
    if sha256(payload).hexdigest() != item["sha256"]:
        raise ValueError("material changed; request Host manifest repair")
    content = payload.decode("utf-8")
    offset, limit = arguments.get("offset", 0), arguments.get("limit", 16384)
    if limit > 16384:
        raise ValueError("limit exceeds 16384; follow next_offset to read the remaining original text")
    if offset > len(content):
        raise ValueError("offset exceeds material length; use returned next_offset")
    end = min(len(content), offset + limit)
    return {"material_id": arguments["material_id"], "source": item["source"],
            "sha256": item["sha256"], "text": content[offset:end], "offset": offset,
            "next_offset": end if end < len(content) else None, "read_complete": end == len(content)}


def run_role_materials(manifest_path: Path, *, stdin=None, stdout=None) -> int:
    import sys
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for line in stdin or sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        method = request.get("method")
        result = {}
        if method == "initialize":
            result = {"protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
                      "capabilities": {"tools": {}}, "serverInfo": {"name": "role-materials", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [ROLE_MATERIAL_TOOL]}
        elif method == "tools/call":
            try:
                params = request.get("params", {})
                if params.get("name") != "read_role_material":
                    raise ValueError("tool not authorized")
                value = read_role_material(manifest, params.get("arguments", {}))
                result = {"content": _text_content(value), "structuredContent": value}
            except (OSError, ValueError) as exc:
                result = {"isError": True, "content": _text_content({"error": str(exc)})}
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "error": {
                "code": -32601, "message": "method not available"}}), file=stdout or sys.stdout, flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}),
              file=stdout or sys.stdout, flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Runner-private capability stdio MCP client")
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--socket")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--role-materials", type=Path)
    args = parser.parse_args()
    if args.role_materials:
        return run_role_materials(args.role_materials)
    if not args.stdio or not args.socket or not args.token_file:
        return 2
    return run_stdio_client(args.socket, args.token_file)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ACCEPTANCE_OPERATIONS",
    "CAPABILITY_TOOL_SCHEMAS",
    "COMPETENCY_QUESTION_ROLE",
    "COORDINATOR_OPERATIONS",
    "COORDINATOR_FORMAL_OPERATIONS",
    "CQ_OPERATION",
    "CQ_OPERATIONS",
    "MODELING_OPERATIONS",
    "PROTOCOL_OPERATIONS",
    "ROLE_OPERATIONS",
    "STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION",
    "STAGED_PROTOCOL_OPERATION",
    "STAGED_PROTOCOL_OPERATIONS",
    "STAGED_PROTOCOL_RUN_OPERATIONS",
    "STAGED_UNIFIED_PROTOCOL_OPERATIONS",
    "UNIFIED_PROTOCOL_RUN_OPERATIONS",
    "UNIFIED_PROTOCOL_OPERATIONS",
    "RunnerCapabilityEndpoint",
    "run_stdio_client",
    "token_digest",
]
