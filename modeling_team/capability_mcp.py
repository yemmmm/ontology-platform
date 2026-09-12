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
# R3.0-008B/#17: the staged run's second projection.  A staged batch materializes
# items whose lineage is scored at the terminal retrieval gate, and the
# owner-authorized evidence that has to back those items can only be attached
# through the platform's ``associate_evidence_reference``.  Without this
# projection the gate is constructively unsatisfiable for any run that
# materializes before the owner answers (auth010 start4, item e80f85b1), so the
# capability is staged-run-exclusive exactly like the submission operation.
STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION = "protocol_staged_associate_evidence"
STAGED_PROTOCOL_RUN_OPERATIONS: tuple[str, ...] = (
    STAGED_PROTOCOL_OPERATION,
    STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION,
)
STAGED_PROTOCOL_OPERATIONS: tuple[str, ...] = (*PROTOCOL_OPERATIONS, *STAGED_PROTOCOL_RUN_OPERATIONS)
MODELING_OPERATIONS: tuple[str, ...] = ("modeling_publish_staged_candidate",)
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
    "modeling": MODELING_OPERATIONS,
    "protocol": STAGED_PROTOCOL_OPERATIONS,
    "acceptance": ACCEPTANCE_OPERATIONS,
}

# R3.0-011: the competency-question role owns exactly one Runner-private
# capability.  It is registered here so the dispatcher can validate it, while
# only a run that selected ``competency_question_acceptance`` assembles an
# endpoint that advertises it (no production role ever sees this operation).
COMPETENCY_QUESTION_ROLE = "competency-question"
CQ_OPERATION = "cq_publish_question_draft"
CQ_OPERATIONS: tuple[str, ...] = (CQ_OPERATION,)
ROLE_OPERATIONS[COMPETENCY_QUESTION_ROLE] = CQ_OPERATIONS


CAPABILITY_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
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
            # auto-selects the five canonical final-state observed calls.  When
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
                    for stage in ("dry-run", "apply", "readback", "validation", "reasoning")
                },
                "required": ["dry-run", "apply", "readback", "validation", "reasoning"],
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
            # expected_workspace_version, items[{command_kind, payload}],
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
    "protocol_staged_associate_evidence": {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            # ``association`` mirrors the real ``associate_evidence_reference``
            # parameters one for one (project_id, ontology_id, target_type,
            # target_id, evidence_reference_ids, evidence[{document_name,
            # excerpt}], graph_set_id, client_item_id, edit_audit_id).  The
            # platform tool's own ``actor`` parameter is deliberately NOT part
            # of this envelope: the platform derives the actor from the Runner's
            # protocol credential, so a role can never name one.
            "association": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "ontology_id": {"type": "string"},
                    "target_type": {"type": "string"},
                    "target_id": {"type": "string"},
                    "evidence_reference_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "document_name": {"type": "string"},
                                "excerpt": {"type": "string"},
                            },
                            "required": ["document_name", "excerpt"],
                            "additionalProperties": False,
                        },
                    },
                    "graph_set_id": {"type": "string"},
                    "client_item_id": {"type": "string"},
                    "edit_audit_id": {"type": "string"},
                },
                "required": ["project_id", "ontology_id", "target_type", "target_id"],
                "additionalProperties": False,
            },
        },
        "required": ["protocol_id", "association"],
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
        "draft": {"type": "object"},
    },
    "required": ["cq_id", "draft"],
    "additionalProperties": False,
}


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
        if not isinstance(request, Mapping):
            return self._error(None)
        request_id = request.get("id")
        if request.get("token") != self.token:
            return self._error(request_id)
        method = request.get("method")
        if method == "tools/list":
            tools = [
                {
                    "name": operation,
                    "description": f"Runner-private {self.role} capability",
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


def _stdio_request(socket_path: str, token: str, request: Mapping[str, Any]) -> dict[str, Any]:
    payload = {**dict(request), "token": token}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(15)
        connection.connect(socket_path)
        connection.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
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
                "id": None,
                "error": {"code": -32001, "message": "Runner capability request rejected"},
            }
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Runner-private capability stdio MCP client")
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--socket", required=True)
    parser.add_argument("--token-file", required=True, type=Path)
    args = parser.parse_args()
    if not args.stdio:
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
    "RunnerCapabilityEndpoint",
    "run_stdio_client",
    "token_digest",
]
