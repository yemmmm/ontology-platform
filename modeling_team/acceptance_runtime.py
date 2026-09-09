"""Private runtime helpers for the R2.3-005 Examiner children.

The Runner owns this module.  It deliberately has no semantic authority: the platform
proxy validates a frozen ticket envelope before forwarding to the host-owned canonical
MCP server.  ``ScopedReadProxy`` can still be constructed without a forwarder by
explicit deterministic offline tests; formal Runner children always bind the concrete
``McpReadForwarder`` created by the platform read-key lifecycle.
"""

from __future__ import annotations

import hashlib
import asyncio
import base64
from copy import deepcopy
import json
import os
import queue
import re
import socket
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

from .competency_questions import (
    CQ_BATCH_PACKET_SCHEMA,
    CQ_BATCH_REPORT_SCHEMA,
    validate_acceptance_verdict,
    validate_evidence_bundle,
    validate_examiner_report,
    validate_model_binding,
)


class ChildRuntimeError(RuntimeError):
    """A private child/proxy contract failed closed."""


class _ProxyScopeDenied(Exception):
    """Internal: one proxy call is refused before any forward (code-carrying)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ExaminerRuntimeBlocked(ChildRuntimeError):
    """A typed, fail-closed Examiner stop which must not be retried by asking another role."""

    def __init__(self, reason: str, *, role: str | None = None, evidence: Mapping[str, Any] | None = None):
        if not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._/-]{0,79}", reason):
            raise ValueError("Examiner blocked reason is invalid")
        self.reason = reason
        self.role = role
        self.evidence = dict(evidence or {})
        super().__init__(f"BLOCKED/{reason}")

    def __str__(self) -> str:
        return _blocked_detail(self)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ExaminerBlocked/v1",
            "status": "BLOCKED",
            "blocked_reason": self.reason,
            "role": self.role,
            "evidence": dict(self.evidence),
        }


def _packet_json_default(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__bytes_base64__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, MappingProxyType):
        return dict(value)
    raise TypeError(f"unsupported packet value: {type(value).__name__}")


def _packet_canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_packet_json_default,
    ).encode("utf-8")


def _packet_digest(value: Any) -> str:
    return hashlib.sha256(_packet_canonical(value)).hexdigest()


def _packet_tokens(value: Any) -> int:
    """Deterministic provider-neutral estimate used for recomputable accounting."""

    return max(1, (len(_packet_canonical(value)) + 3) // 4)


def _packet_measurement_payload(kind: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Project role-packet accounting without raw source bytes or platform responses."""

    measured = dict(payload)
    if kind == "source" and isinstance(measured.get("approved_sources"), (list, tuple)):
        measured["approved_sources"] = [
            {
                "path": item.get("path"),
                "sha256": item.get("sha256"),
            }
            for item in measured["approved_sources"]
            if isinstance(item, Mapping)
        ]
    if kind == "acceptance":
        # Acceptance receives typed reports and their digests, not raw platform
        # responses; count the report envelope as task context and leave evidence
        # response accounting to the Platform metrics object.
        measured.pop("platform_response", None)
    return measured


def _freeze_packet(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_packet(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_packet(child) for child in value)
    if isinstance(value, tuple):
        return tuple(_freeze_packet(child) for child in value)
    return value


def _unfreeze_packet(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _unfreeze_packet(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_unfreeze_packet(child) for child in value]
    return value


def _require_packet_keys(value: Mapping[str, Any], keys: Iterable[str], label: str) -> None:
    if set(value) != set(keys):
        raise ExaminerRuntimeBlocked("acceptance-input", evidence={"packet": label})


@dataclass(frozen=True)
class ExaminerRolePacket:
    """Immutable, digest-bound Host input for one fresh Examiner instance."""

    kind: str
    payload: Mapping[str, Any]
    canonical_digest: str
    field_inventory: tuple[str, ...]
    token_breakdown: Mapping[str, int]
    schema_version: str = "ExaminerRolePacket/v1"

    @classmethod
    def build(cls, kind: str, payload: Mapping[str, Any]) -> "ExaminerRolePacket":
        if kind not in {"source", "platform", "acceptance"}:
            raise ChildRuntimeError("Examiner packet kind is invalid")
        if not isinstance(payload, Mapping):
            raise ChildRuntimeError("Examiner packet payload is invalid")
        normalized = dict(payload)
        expected = {
            "source": {
                "question", "ordinal", "count", "approved_sources", "source_bundle_digest", "report_schema"
            },
            "platform": {
                "question", "ordinal", "count", "model_state", "platform_read_scope",
                "proxy_capability", "request_schema", "report_schema", "ticket_binding",
                "allowed_read_tools"
            },
            "acceptance": {
                "question", "ticket_binding", "ordinal", "count", "source_report", "platform_report",
                "source_report_digest", "platform_report_digest", "verdict_schema",
                "source_evidence_ref_ids", "platform_evidence_ref_ids",
            },
        }[kind]
        _require_packet_keys(normalized, expected, f"{kind} Examiner packet")
        ordinal, count = normalized.get("ordinal"), normalized.get("count")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
            raise ExaminerRuntimeBlocked("acceptance-input", role=kind)
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0 or ordinal > count:
            raise ExaminerRuntimeBlocked("acceptance-input", role=kind)
        question = normalized.get("question")
        if not isinstance(question, str) or not question:
            raise ExaminerRuntimeBlocked("acceptance-input", role=kind)
        if kind == "source":
            sources = normalized["approved_sources"]
            if not isinstance(sources, (list, tuple)) or not sources:
                raise ExaminerRuntimeBlocked("source-missing", role="source")
            if not isinstance(normalized.get("report_schema"), Mapping):
                raise ExaminerRuntimeBlocked("acceptance-input", role="source")
            for source in sources:
                if not isinstance(source, Mapping) or set(source) != {"path", "sha256", "bytes"}:
                    raise ExaminerRuntimeBlocked("source-missing", role="source")
                path, digest, content = source["path"], source["sha256"], source["bytes"]
                if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                    raise ExaminerRuntimeBlocked("source-missing", role="source")
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ExaminerRuntimeBlocked("source-missing", role="source")
                if not isinstance(content, bytes) or hashlib.sha256(content).hexdigest() != digest:
                    raise ExaminerRuntimeBlocked("source-missing", role="source")
                try:
                    content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ExaminerRuntimeBlocked("source-missing", role="source") from exc
            manifest = [{"path": item["path"], "sha256": item["sha256"]} for item in sources]
            if (
                not isinstance(normalized["source_bundle_digest"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", normalized["source_bundle_digest"])
                or normalized["source_bundle_digest"] != _packet_digest(manifest)
            ):
                raise ExaminerRuntimeBlocked("source-missing", role="source")
        elif kind == "platform":
            for field in (
                "model_state", "platform_read_scope", "proxy_capability", "request_schema",
                "ticket_binding",
            ):
                if not isinstance(normalized[field], Mapping):
                    raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            if not normalized["proxy_capability"].get("capability_id"):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            state = normalized["model_state"]
            scope = normalized["platform_read_scope"]
            if (
                not isinstance(state.get("workspace_version"), str)
                or not state.get("workspace_version")
                or not isinstance(state.get("state_digest"), str)
                or re.fullmatch(r"[0-9a-f]{64}", state["state_digest"]) is None
                or any(not isinstance(scope.get(field), str) or not scope.get(field) for field in ("project_id", "ontology_id", "graph_set_id"))
            ):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            ticket_digest = normalized["ticket_binding"].get("ticket_digest")
            if not isinstance(ticket_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", ticket_digest):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            allowed_tools = normalized.get("allowed_read_tools")
            if (
                not isinstance(allowed_tools, (list, tuple))
                or not allowed_tools
                or len(set(allowed_tools)) != len(allowed_tools)
                or any(not isinstance(tool, str) or tool not in PLATFORM_PROXY_READ_TOOLS for tool in allowed_tools)
            ):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            request_schema = normalized["request_schema"]
            schemas = request_schema.get("tools") if isinstance(request_schema.get("tools"), Mapping) else request_schema
            if not isinstance(schemas, Mapping) or set(schemas) != set(allowed_tools):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            exact = examiner_proxy_schemas(allowed_tools)
            if any(_packet_digest(schemas[tool]) != _packet_digest(exact[tool]) for tool in allowed_tools):
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
            if "source" in normalized or "history" in normalized:
                raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
        else:
            for field in ("ticket_binding", "source_report", "platform_report"):
                if not isinstance(normalized[field], Mapping):
                    raise ExaminerRuntimeBlocked(
                        "acceptance-evidence", role="acceptance",
                        evidence={"binding_code": "report-object-invalid", "field": field},
                    )
            for field in ("source_report_digest", "platform_report_digest"):
                if not isinstance(normalized[field], str) or not re.fullmatch(r"[0-9a-f]{64}", normalized[field]):
                    raise ExaminerRuntimeBlocked(
                        "acceptance-evidence", role="acceptance",
                        evidence={"binding_code": "report-digest-invalid", "field": field},
                    )
            try:
                source_report = _validate_report_sink_payload(normalized["source_report"], kind="source")
                platform_report = _validate_report_sink_payload(normalized["platform_report"], kind="platform")
            except ChildRuntimeError as exc:
                raise ExaminerRuntimeBlocked(
                    "acceptance-evidence", role="acceptance",
                    evidence={"binding_code": "report-sink-invalid", "field": "sink-rejected"},
                ) from exc
            if (
                normalized["source_report_digest"] != _packet_digest(source_report)
                or normalized["platform_report_digest"] != _packet_digest(platform_report)
            ):
                raise ExaminerRuntimeBlocked(
                    "acceptance-evidence", role="acceptance",
                    evidence={"binding_code": "report-digest-mismatch"},
                )
            if not isinstance(normalized["ticket_binding"].get("ticket_digest"), str) or re.fullmatch(
                r"[0-9a-f]{64}", normalized["ticket_binding"]["ticket_digest"]
            ) is None:
                raise ExaminerRuntimeBlocked("acceptance-input", role="acceptance")
            if not isinstance(normalized.get("verdict_schema"), Mapping):
                raise ExaminerRuntimeBlocked("acceptance-input", role="acceptance")
            for field in ("source_evidence_ref_ids", "platform_evidence_ref_ids"):
                values = normalized.get(field)
                if (
                    not isinstance(values, (list, tuple))
                    or not values
                    or any(not isinstance(item, str) or not item for item in values)
                    or len(set(values)) != len(values)
                ):
                    raise ExaminerRuntimeBlocked(
                        "acceptance-evidence", role="acceptance",
                        evidence={"binding_code": "evidence-ref-ids-invalid", "field": field},
                    )
            if "approved_sources" in normalized or "platform_response" in normalized or "history" in normalized:
                raise ExaminerRuntimeBlocked("acceptance-input", role="acceptance")
        frozen = _freeze_packet(normalized)
        canonical = _packet_digest(_unfreeze_packet(frozen))
        inventory = tuple(sorted(str(key) for key in normalized))
        measured_payload = _packet_measurement_payload(kind, normalized)
        breakdown = {
            "system_safety_prefix_tokens": 0,
            "host_packet_tokens": _packet_tokens(measured_payload),
            "source_bytes_tokens": (
                sum(_packet_tokens(bytes(item["bytes"])) for item in normalized["approved_sources"])
                if kind == "source" else 0
            ),
            "platform_response_tokens": 0,
            "task_tokens": _packet_tokens({key: normalized[key] for key in inventory if key in {"question", "ticket_binding", "ordinal", "count"}}),
            "evidence_tokens": 0,
        }
        host_packet_limit = 8192 if kind == "acceptance" else 4096
        if breakdown["host_packet_tokens"] > host_packet_limit:
            raise ExaminerRuntimeBlocked(
                "acceptance-input",
                role=kind,
                evidence={"host_packet_tokens": breakdown["host_packet_tokens"]},
            )
        return cls(kind, frozen, canonical, inventory, MappingProxyType(breakdown))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "payload": _unfreeze_packet(self.payload),
            "canonical_digest": self.canonical_digest,
            "field_inventory": list(self.field_inventory),
            "token_breakdown": dict(self.token_breakdown),
        }


def build_source_examiner_packet(**payload: Any) -> ExaminerRolePacket:
    return ExaminerRolePacket.build("source", payload)


def build_platform_examiner_packet(**payload: Any) -> ExaminerRolePacket:
    return ExaminerRolePacket.build("platform", payload)


def build_acceptance_examiner_packet(**payload: Any) -> ExaminerRolePacket:
    return ExaminerRolePacket.build("acceptance", payload)


# --- R3.0-011 v3 hidden-batch acceptance packets ------------------------------
#
# The v3 contract is an explicit, separately versioned branch.  It never
# rewrites ``ExaminerRolePacket/v1``: the legacy per-question
# source/platform/acceptance fields above stay byte-identical, and the branch is
# chosen by packet schema at the dispatch selector (``acceptance_branch_for``),
# never by only changing a prompt or reusing ``validate_ticket``.

CQ_ACCEPTANCE_BRANCH_V3 = "v3-batch"
CQ_ACCEPTANCE_BRANCH_LEGACY = "legacy-r2.3-per-question"
CQ_ACCEPTANCE_PLATFORM_ROLE = "platform-examiner"
CQ_ACCEPTANCE_JUDGE_ROLE = "acceptance"

# A Platform Examiner stays blind: no answer points, no evidence bundle, no
# review binding and no conversation history may enter its batch packet.
_V3_BLIND_FORBIDDEN_FIELDS = frozenset(
    {"answer_points", "evidence_refs", "review_binding", "evidence_bundle", "answers", "history"}
)


def acceptance_branch_for(schema_version: Any) -> str:
    """Return the explicit acceptance branch for a packet schema version."""

    if schema_version == CQ_BATCH_PACKET_SCHEMA:
        return CQ_ACCEPTANCE_BRANCH_V3
    if schema_version == "ExaminerRolePacket/v1":
        return CQ_ACCEPTANCE_BRANCH_LEGACY
    raise ChildRuntimeError("acceptance packet schema_version is unknown")


@dataclass(frozen=True)
class AcceptanceBatchPacket:
    """Immutable, digest-bound Host input for one v3 acceptance session.

    ``role`` is ``platform-examiner`` for the single continuous hidden-batch
    session, or ``acceptance`` for the independent read-only judge session.  A
    Platform Examiner packet carries ordered questions, the bound model states,
    the authorized Ontology scope and read-only tools, and never carries answer
    points or reference evidence; the Acceptance judge packet carries the frozen
    answers, the evidence bundle and the Examiner reports instead.
    """

    role: str
    payload: Mapping[str, Any]
    canonical_digest: str
    batch_id: str
    freeze_digest: str
    field_inventory: tuple[str, ...]
    schema_version: str = CQ_BATCH_PACKET_SCHEMA

    @classmethod
    def build(cls, role: str, payload: Mapping[str, Any]) -> "AcceptanceBatchPacket":
        if role not in {CQ_ACCEPTANCE_PLATFORM_ROLE, CQ_ACCEPTANCE_JUDGE_ROLE}:
            raise ChildRuntimeError("v3 acceptance packet role is invalid")
        if not isinstance(payload, Mapping):
            raise ChildRuntimeError("v3 acceptance packet payload is invalid")
        normalized = dict(payload)
        expected = {
            CQ_ACCEPTANCE_PLATFORM_ROLE: {
                "run_id",
                "batch_id",
                "freeze_digest",
                "questions",
                "authorized_scope",
                "model_binding",
                "authorized_read_tools",
                "report_schema",
                "session",
            },
            CQ_ACCEPTANCE_JUDGE_ROLE: {
                "run_id",
                "batch_id",
                "freeze_digest",
                "questions",
                "model_binding_digest",
                "evidence_bundle",
                "examiner_reports",
                "verdict_schema",
            },
        }[role]
        if set(normalized) != expected:
            raise ChildRuntimeError("v3 acceptance packet fields are invalid")
        for key in ("run_id", "batch_id"):
            if not isinstance(normalized[key], str) or not normalized[key]:
                raise ChildRuntimeError(f"v3 acceptance packet {key} is invalid")
        if not _v3_digest(normalized["freeze_digest"]):
            raise ChildRuntimeError("v3 acceptance packet freeze_digest is invalid")
        question_ids = _v3_batch_questions(normalized["questions"], role=role)
        if role == CQ_ACCEPTANCE_PLATFORM_ROLE:
            scope = normalized["authorized_scope"]
            if not isinstance(scope, list) or not scope or any(
                not isinstance(item, str) or not item for item in scope
            ):
                raise ChildRuntimeError("v3 acceptance packet authorized_scope is invalid")
            if len(set(scope)) != len(scope):
                raise ChildRuntimeError("v3 acceptance packet authorizes an Ontology twice")
            try:
                binding = validate_model_binding(
                    normalized["model_binding"], authorized_ontology_ids=list(scope)
                )
            except ValueError as exc:
                raise ChildRuntimeError(f"v3 acceptance model binding is invalid: {exc}") from exc
            if binding.get("batch_id") != normalized["batch_id"] or binding.get(
                "freeze_digest"
            ) != normalized["freeze_digest"]:
                # The packet seam must enforce the same batch/freeze identity the
                # cq-acceptance CLI checks before it can build a packet
                # (Round 1 F3).
                raise ChildRuntimeError(
                    "v3 acceptance model binding does not match this batch and freeze snapshot"
                )
            bound = sorted(
                entry["ontology_id"] for entry in binding.get("ontologies", [])
            )
            if bound != sorted(scope):
                raise ChildRuntimeError("v3 acceptance model binding does not close the scope")
            tools = normalized["authorized_read_tools"]
            if (
                not isinstance(tools, list)
                or not tools
                or any(tool not in PLATFORM_PROXY_READ_TOOLS for tool in tools)
                or len(set(tools)) != len(tools)
            ):
                raise ChildRuntimeError("v3 acceptance read tools are invalid")
            if not isinstance(normalized["report_schema"], Mapping):
                raise ChildRuntimeError("v3 acceptance report_schema is invalid")
            session = normalized["session"]
            if not isinstance(session, Mapping) or dict(session) != {
                "mode": "single-continuous-batch",
                "ordered": True,
            }:
                raise ChildRuntimeError("v3 acceptance session contract is invalid")
        else:
            if not _v3_digest(normalized["model_binding_digest"]):
                raise ChildRuntimeError("v3 acceptance model_binding_digest is invalid")
            if not isinstance(normalized["verdict_schema"], Mapping):
                raise ChildRuntimeError("v3 acceptance verdict_schema is invalid")
            try:
                bundle = validate_evidence_bundle(normalized["evidence_bundle"])
            except ValueError as exc:
                raise ChildRuntimeError(f"v3 acceptance evidence bundle is invalid: {exc}") from exc
            reports = normalized["examiner_reports"]
            if not isinstance(reports, list):
                raise ChildRuntimeError("v3 acceptance examiner_reports is invalid")
            for report in reports:
                try:
                    validated = validate_examiner_report(report, question_ids=question_ids)
                except ValueError as exc:
                    raise ChildRuntimeError(f"v3 examiner report is invalid: {exc}") from exc
                if validated.get("batch_id") != normalized["batch_id"]:
                    raise ChildRuntimeError("v3 examiner report is bound to another batch")
            normalized["evidence_bundle"] = bundle
        frozen = _freeze_packet(normalized)
        digest = _packet_digest(_unfreeze_packet(frozen))
        return cls(
            role,
            frozen,
            digest,
            str(normalized["batch_id"]),
            str(normalized["freeze_digest"]),
            tuple(sorted(str(key) for key in normalized)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "role": self.role,
            "payload": _unfreeze_packet(self.payload),
            "canonical_digest": self.canonical_digest,
            "batch_id": self.batch_id,
            "freeze_digest": self.freeze_digest,
            "field_inventory": list(self.field_inventory),
        }


def _v3_digest(value: Any) -> bool:
    """Accept a 64-hex digest or the competency-question ``sha256:<hex>`` form."""

    if not isinstance(value, str):
        return False
    candidate = value[len("sha256:") :] if value.startswith("sha256:") else value
    return re.fullmatch(r"[0-9a-f]{64}", candidate) is not None


def _v3_batch_questions(questions: Any, *, role: str) -> list[str]:
    """Validate the ordered batch question list and return its ids."""

    if not isinstance(questions, list) or not questions:
        raise ChildRuntimeError("v3 acceptance batch question list is empty")
    expected = (
        {"question_id", "content_version", "question", "scope"}
        if role == CQ_ACCEPTANCE_PLATFORM_ROLE
        else {
            "question_id",
            "content_version",
            "question",
            "answer_points",
            "evidence_refs",
            "unknown",
            "scope",
        }
    )
    ids: list[str] = []
    for item in questions:
        if not isinstance(item, Mapping) or set(item) != expected:
            raise ChildRuntimeError(f"v3 acceptance batch question fields are invalid for {role}")
        if any(field in item for field in _V3_BLIND_FORBIDDEN_FIELDS) and role == (
            CQ_ACCEPTANCE_PLATFORM_ROLE
        ):
            raise ChildRuntimeError("v3 platform batch packet is not blind")
        question_id = item["question_id"]
        if not isinstance(question_id, str) or not question_id:
            raise ChildRuntimeError("v3 acceptance batch question_id is invalid")
        version = item["content_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ChildRuntimeError("v3 acceptance batch content_version is invalid")
        if not isinstance(item["question"], str) or not item["question"]:
            raise ChildRuntimeError("v3 acceptance batch question text is invalid")
        scope = item["scope"]
        if not isinstance(scope, Mapping) or scope.get("kind") not in {"panorama", "slice"}:
            raise ChildRuntimeError("v3 acceptance batch question scope is invalid")
        slice_ids = scope.get("slice_ids")
        if scope.get("kind") == "slice" and (
            not isinstance(slice_ids, list)
            or not slice_ids
            or any(not isinstance(value, str) or not value for value in slice_ids)
        ):
            raise ChildRuntimeError("v3 acceptance slice question needs slice_ids")
        if scope.get("kind") == "panorama" and slice_ids != []:
            raise ChildRuntimeError("v3 acceptance panorama question must not carry slice_ids")
        if role == CQ_ACCEPTANCE_JUDGE_ROLE:
            if not isinstance(item["answer_points"], list) or not item["answer_points"]:
                raise ChildRuntimeError("v3 judge packet question needs answer points")
            if not isinstance(item["evidence_refs"], list):
                raise ChildRuntimeError("v3 judge packet evidence_refs is invalid")
            if not isinstance(item["unknown"], list):
                raise ChildRuntimeError("v3 judge packet unknown list is invalid")
        ids.append(question_id)
    if len(set(ids)) != len(ids):
        raise ChildRuntimeError("v3 acceptance batch repeats a question_id")
    return ids


def build_platform_batch_packet(**payload: Any) -> AcceptanceBatchPacket:
    """Build the v3 single-continuous-session Platform Examiner batch packet."""

    return AcceptanceBatchPacket.build(CQ_ACCEPTANCE_PLATFORM_ROLE, payload)


def build_acceptance_judge_packet(**payload: Any) -> AcceptanceBatchPacket:
    """Build the v3 independent read-only Acceptance judge packet."""

    return AcceptanceBatchPacket.build(CQ_ACCEPTANCE_JUDGE_ROLE, payload)


def v3_ticket_digest(value: Any) -> str:
    """Normalize a v3 freeze digest to the 64-hex proxy ticket form.

    The frozen snapshot digest is ``sha256:<hex>`` while every proxy binding
    (``_EXAMINER_SCOPE_SCHEMA``/``_safe_digest``) is 64-hex.  The prefix is
    transport presentation, never new identity: the hex body must be present,
    well formed, and identical to the packet digest the batch is bound to.
    """

    if not _v3_digest(value):
        raise ChildRuntimeError("v3 acceptance ticket digest is invalid")
    text = str(value)
    return text[len("sha256:") :] if text.startswith("sha256:") else text


def v3_proxy_scope_entries(
    packet: AcceptanceBatchPacket, graph_set_ids: Mapping[str, Any]
) -> tuple[dict[str, str], ...]:
    """Build the packet-verified proxy scope for one v3 platform session.

    One entry per authorized Ontology, in packet order: project, Ontology, graph
    set and both bound state digests.  Project and state identity are read from
    the packet's own model binding, so a host entry can never widen or re-point
    the authorized scope; ``graph_set_ids`` supplies the default graph set the
    host observed for that Ontology with the same authorized read tools (the
    packet carries the binding, not the platform's graph-set locator).  These
    entries are the only scope a v3 Platform Examiner can read; anything outside
    the list is refused before a forward.
    """

    if not isinstance(packet, AcceptanceBatchPacket) or packet.role != (
        CQ_ACCEPTANCE_PLATFORM_ROLE
    ):
        raise ChildRuntimeError("v3 proxy scope requires a platform batch packet")
    payload = _unfreeze_packet(packet.payload)
    scope = payload.get("authorized_scope")
    if not isinstance(scope, list) or not scope:
        raise ChildRuntimeError("v3 proxy scope requires the packet authorization")
    binding = payload.get("model_binding")
    ontologies = binding.get("ontologies") if isinstance(binding, Mapping) else None
    if not isinstance(ontologies, list) or not ontologies:
        raise ChildRuntimeError("v3 proxy scope requires the packet model binding")
    if not isinstance(graph_set_ids, Mapping):
        raise ChildRuntimeError("v3 proxy scope graph sets are invalid")
    entries: list[dict[str, str]] = []
    for item in ontologies:
        if not isinstance(item, Mapping):
            raise ChildRuntimeError("v3 proxy scope entry is invalid")
        ontology_id = item.get("ontology_id")
        project_id = item.get("project_id")
        workspace = item.get("workspace_state")
        graph = item.get("graph_state")
        state = workspace.get("state_digest") if isinstance(workspace, Mapping) else None
        graph_state = graph.get("state_digest") if isinstance(graph, Mapping) else None
        graph_set_id = graph_set_ids.get(ontology_id) if isinstance(ontology_id, str) else None
        if not all(
            isinstance(field, str) and field
            for field in (ontology_id, project_id, state, graph_state, graph_set_id)
        ):
            raise ChildRuntimeError("v3 proxy scope entry is incomplete")
        if ontology_id not in scope:
            raise ChildRuntimeError("v3 proxy scope entry is outside the packet authorization")
        entries.append(
            {
                "project_id": str(project_id),
                "ontology_id": str(ontology_id),
                "graph_set_id": str(graph_set_id),
                "model_state_digest": str(state),
                "graph_state_digest": str(graph_state),
            }
        )
    return tuple(entries)


class V3BatchReportContract:
    """Sink-time batch binding for one v3 acceptance session (design §3.G4.2).

    The contract is built from the session's own :class:`AcceptanceBatchPacket`,
    so the sink can reject anything the packet never authorized: another batch,
    another freeze, an unknown question, a duplicate submission, or a question
    reported out of packet order.  Per-question field validation is delegated to
    the canonical ``validate_examiner_report``/``validate_acceptance_verdict``
    contracts — this class adds only the batch, order and completeness rules.
    """

    def __init__(self, *, role: str, packet: AcceptanceBatchPacket) -> None:
        if role not in {CQ_ACCEPTANCE_PLATFORM_ROLE, CQ_ACCEPTANCE_JUDGE_ROLE}:
            raise ChildRuntimeError("v3 report sink contract role is invalid")
        if not isinstance(packet, AcceptanceBatchPacket) or packet.role != role:
            raise ChildRuntimeError("v3 report sink contract packet is invalid")
        if acceptance_branch_for(packet.schema_version) != CQ_ACCEPTANCE_BRANCH_V3:
            raise ChildRuntimeError("v3 report sink contract requires the v3 branch")
        self.role = role
        self.packet = packet
        payload = _unfreeze_packet(packet.payload)
        self.batch_id = str(payload["batch_id"])
        self.question_ids = list(_v3_batch_questions(payload["questions"], role=role))
        self.content_versions = {
            str(item["question_id"]): item["content_version"]
            for item in payload["questions"]
        }
        self._reported: list[dict[str, Any]] = []

    @property
    def schema_version(self) -> str:
        return CQ_BATCH_REPORT_SCHEMA

    @property
    def reports(self) -> list[dict[str, Any]]:
        return list(self._reported)

    @property
    def pending_question_ids(self) -> list[str]:
        reported = {str(report["question_id"]) for report in self._reported}
        return [item for item in self.question_ids if item not in reported]

    @property
    def is_complete(self) -> bool:
        return not self.pending_question_ids

    def validate(self, report: Mapping[str, Any]) -> dict[str, Any]:
        """Validate one per-question entry against this batch contract."""

        if not isinstance(report, Mapping):
            raise ChildRuntimeError("v3 acceptance batch report entry is invalid")
        if report.get("schema_version") != CQ_BATCH_REPORT_SCHEMA:
            raise ChildRuntimeError(
                f"v3 acceptance batch report schema must be {CQ_BATCH_REPORT_SCHEMA}"
            )
        if report.get("batch_id") != self.batch_id:
            raise ChildRuntimeError("v3 acceptance batch report is bound to another batch")
        question_id = report.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise ChildRuntimeError("v3 acceptance batch report question_id is invalid")
        reported = {str(item["question_id"]) for item in self._reported}
        if question_id in reported:
            raise ChildRuntimeError(
                f"v3 acceptance batch already carries a report for {question_id}"
            )
        expected = self.question_ids[len(self._reported)]
        if question_id != expected:
            raise ChildRuntimeError(
                f"v3 acceptance batch expects the report for {expected} next; got {question_id}"
            )
        validator = validate_examiner_report if self.role == CQ_ACCEPTANCE_PLATFORM_ROLE else (
            validate_acceptance_verdict
        )
        try:
            validated = validator(report, question_ids=self.question_ids)
        except ValueError as exc:
            raise ChildRuntimeError(f"v3 acceptance batch report is invalid: {exc}") from exc
        if self.role == CQ_ACCEPTANCE_PLATFORM_ROLE and validated.get(
            "question_content_version"
        ) != self.content_versions.get(question_id):
            raise ChildRuntimeError(
                f"v3 acceptance batch report for {question_id} cites another content version"
            )
        return validated

    def record(self, report: Mapping[str, Any]) -> None:
        """Latch one validated entry; completeness only after the last question."""

        if self.is_complete:
            raise ChildRuntimeError("v3 acceptance batch is already complete")
        self._reported.append(dict(report))


@dataclass(frozen=True)
class ExaminerTransportReceipt:
    sender: str
    recipient: str
    status: str
    reason: str
    receipt_digest: str


class ExaminerTransport:
    """Role-private transport that rejects all lateral collaboration before send."""

    def __init__(self, *, owner_id: str):
        if not isinstance(owner_id, str) or not owner_id:
            raise ChildRuntimeError("Examiner transport owner is invalid")
        self.owner_id = owner_id
        self.receipts: list[ExaminerTransportReceipt] = []

    def send(self, *, sender: str, recipient: str, payload: Mapping[str, Any]) -> ExaminerTransportReceipt:
        if recipient != self.owner_id:
            receipt_data = {
                "sender": sender,
                "recipient": recipient,
                "status": "rejected",
                "reason": "collaboration/routing",
                "payload_digest": _packet_digest(payload),
            }
            receipt = ExaminerTransportReceipt(
                sender=str(sender),
                recipient=str(recipient),
                status="rejected",
                reason="collaboration/routing",
                receipt_digest=_packet_digest(receipt_data),
            )
            self.receipts.append(receipt)
            return receipt
        receipt_data = {"sender": sender, "recipient": recipient, "status": "accepted", "payload_digest": _packet_digest(payload)}
        receipt = ExaminerTransportReceipt(str(sender), str(recipient), "accepted", "owner", _packet_digest(receipt_data))
        self.receipts.append(receipt)
        return receipt


_TOKEN_FIELDS = (
    "inputTokens", "cachedInputTokens", "cacheWriteInputTokens", "outputTokens",
    "reasoningOutputTokens", "totalTokens", "modelContextWindow",
)

# Examiner inference-step guardrail (user decision 2026-08-20): one unified
# cap of 30 for every examiner child, with no per-role distinction.  The cap
# bounds runaway children only; it is not an acceptance-quality gate.  Live
# calibration history: 10 (platform-only) was exhausted by the full live
# platform examiner on both attempts in r23009-luna-20260820-start2; 20
# (platform-only) passed that layer in start3; the unified 30 keeps the same
# runaway margin for source/acceptance children without re-introducing
# per-role calibration drift.
_EXAMINER_MAX_INFERENCE_STEPS = 30


@dataclass
class ExaminerRunMetrics:
    """Recomputable per-child metrics for Codex App Server notifications."""

    role: str
    thread_id: str | None = None
    turn_start_count: int = 0
    inference_steps: int = 0
    max_inference_steps: int = _EXAMINER_MAX_INFERENCE_STEPS
    ttft_ms: float | None = None
    terminal_wall_ms: float | None = None
    proxy_time_ms: float = 0.0
    collaboration_rejections: int = 0
    first_turn_input_digest: str | None = None
    first_turn_input_fields: tuple[str, ...] = ()
    inherited_turns: int = 0
    packet_tokens: int = 0
    source_bytes_tokens: int = 0
    platform_response_tokens: int = 0
    terminal_report: bool = False
    blocked: ExaminerRuntimeBlocked | None = None
    _started_monotonic: float = field(default_factory=time.monotonic, repr=False)
    _first_token_monotonic: float | None = field(default=None, repr=False)
    _last_usage: dict[str, int] = field(default_factory=dict, repr=False)
    _increments: list[dict[str, int]] = field(default_factory=list, repr=False)
    _totals: dict[str, int] = field(default_factory=lambda: {name: 0 for name in _TOKEN_FIELDS}, repr=False)
    _first_input_tokens: int | None = field(default=None, repr=False)
    _turn_id: str | None = field(default=None, repr=False)
    _accepted_turn_ids: set[str] = field(default_factory=set, repr=False)
    _allow_continuation_turn: bool = False
    terminal_event: bool = False

    def record_turn_start(self) -> None:
        """Record the Host-issued fresh turn exactly once."""

        if self.turn_start_count == 0:
            self.turn_start_count = 1

    def allow_continuation_turn(self) -> None:
        """Permit one Host-issued mechanical continuation turn to change turn_id.

        The continuation is the Runner's deterministic nudge after the model ends
        its turn without submitting; it is not a new Agent thread or history.
        """

        self._allow_continuation_turn = True

    def bind_thread(self, thread_id: str) -> None:
        if not isinstance(thread_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", thread_id):
            raise ChildRuntimeError("fresh Examiner thread identity is invalid")
        if self.thread_id is not None and self.thread_id != thread_id:
            raise ChildRuntimeError("fresh Examiner thread identity changed")
        self.thread_id = thread_id

    def bind_first_turn_input(self, value: Sequence[Mapping[str, Any]], *, inherited_turns: int = 0, packet: ExaminerRolePacket | None = None) -> None:
        if inherited_turns != 0:
            self.blocked = ExaminerRuntimeBlocked("acceptance-input", role=self.role, evidence={"inherited_turns": inherited_turns})
            raise self.blocked
        fields: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                fields.extend(str(key) for key in sorted(item))
        self.inherited_turns = 0
        self.first_turn_input_fields = tuple(fields)
        self.first_turn_input_digest = _packet_digest(list(value))
        if packet is not None:
            self.packet_tokens = int(packet.token_breakdown.get("host_packet_tokens", 0))
            self.source_bytes_tokens = int(packet.token_breakdown.get("source_bytes_tokens", 0))

    def observe_notification(self, value: Mapping[str, Any]) -> bool:
        if not isinstance(value, Mapping):
            raise ChildRuntimeError("Examiner notification is invalid")
        method = value.get("method")
        params = value.get("params") if isinstance(value.get("params"), Mapping) else {}
        if method in {"turn/started", "turn/start"}:
            self.record_turn_start()
        if method in {
            "item/agentMessage/delta", "item/reasoning/summaryTextDelta", "item/reasoning/textDelta",
            "item/commandExecution/outputDelta", "item/fileChange/outputDelta", "process/outputDelta",
        } and self._first_token_monotonic is None:
            self._first_token_monotonic = time.monotonic()
            self.ttft_ms = (self._first_token_monotonic - self._started_monotonic) * 1000
        if method != "thread/tokenUsage/updated":
            if method in {"turn/completed", "turn/finished"}:
                self.terminal_event = True
                if self.terminal_wall_ms is None:
                    self.terminal_wall_ms = (time.monotonic() - self._started_monotonic) * 1000
            return False
        event_thread_id = params.get("threadId")
        if self.thread_id is not None and event_thread_id is not None and event_thread_id != self.thread_id:
            self.blocked = ExaminerRuntimeBlocked(
                "runtime-metrics", role=self.role, evidence={"thread_id": self.thread_id}
            )
            raise self.blocked
        event_turn_id = params.get("turnId")
        if event_turn_id is not None:
            if not isinstance(event_turn_id, str) or not event_turn_id:
                self.blocked = ExaminerRuntimeBlocked("runtime-metrics", role=self.role)
                raise self.blocked
            if self._turn_id is not None and event_turn_id != self._turn_id:
                if self._allow_continuation_turn and len(self._accepted_turn_ids) < 2:
                    self._accepted_turn_ids.add(event_turn_id)
                    self._turn_id = event_turn_id
                else:
                    self.blocked = ExaminerRuntimeBlocked(
                        "runtime-metrics", role=self.role, evidence={"turn_id": self._turn_id}
                    )
                    raise self.blocked
            else:
                self._accepted_turn_ids.add(event_turn_id)
                self._turn_id = event_turn_id
        usage = params.get("tokenUsage") if isinstance(params.get("tokenUsage"), Mapping) else params.get("token_usage")
        if not isinstance(usage, Mapping):
            return False
        cumulative = usage.get("total") if isinstance(usage.get("total"), Mapping) else usage
        current: dict[str, int] = {}
        for token_name in _TOKEN_FIELDS:
            raw = cumulative.get(token_name)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                # Provider notifications occasionally omit one accounting field,
                # e.g. ``modelContextWindow``.  Normalize it to zero so retained
                # increments always have the complete fixed token-field set.
                current[token_name] = 0
            else:
                current[token_name] = raw
        if not any(current.values()):
            return False
        increments: dict[str, int] = {}
        for token_name, raw in current.items():
            prior = self._last_usage.get(token_name, 0)
            delta = raw - prior
            if delta < 0:
                self.blocked = ExaminerRuntimeBlocked("runtime-metrics", role=self.role, evidence={"field": token_name})
                raise self.blocked
            increments[token_name] = delta
            self._totals[token_name] = raw
        positive = any(value > 0 for key, value in increments.items() if key != "modelContextWindow")
        self._last_usage.update(current)
        if not positive:
            return False
        if self.inference_steps >= self.max_inference_steps:
            # Once the terminal report is recorded, later usage notifications
            # (a model that keeps reasoning after submitting) must not turn a
            # successful submission into a budget failure.  Keep appending those
            # accounting increments without advancing the step counter so the
            # retained totals still equal the sum of increments.
            if self.terminal_report:
                self._increments.append(increments)
                return True
            if self._allow_continuation_turn and self.inference_steps < self.max_inference_steps + 1:
                self.inference_steps += 1
                self._increments.append(increments)
                return True
            self.blocked = ExaminerRuntimeBlocked("runtime-budget", role=self.role, evidence={"steps": self.inference_steps + 1})
            raise self.blocked
        self.inference_steps += 1
        self._increments.append(increments)
        # Bind the first positive inference usage only.  A zero/no-op cumulative
        # notification is not an inference and must not freeze first-input accounting.
        if self._first_input_tokens is None and "inputTokens" in current:
            self._first_input_tokens = current["inputTokens"]
        # Usage notifications are cumulative and normally arrive immediately before
        # turn/completed; TTFT is therefore sourced only from output/delta events.
        return True

    def record_proxy_time(self, elapsed_ms: float) -> None:
        if isinstance(elapsed_ms, (int, float)) and elapsed_ms >= 0:
            self.proxy_time_ms += float(elapsed_ms)

    def record_platform_response(self, response: Mapping[str, Any]) -> None:
        if isinstance(response, Mapping):
            self.platform_response_tokens += _packet_tokens(response)

    def record_collaboration_rejection(self) -> None:
        self.collaboration_rejections += 1

    def record_terminal_report(self, report: Mapping[str, Any]) -> None:
        if not isinstance(report, Mapping) or set(report) != _REPORT_SEMANTIC_FIELDS:
            self.blocked = ExaminerRuntimeBlocked(
                "acceptance-evidence",
                role=self.role,
                evidence={
                    "binding_code": "report-fields-invalid",
                    "report_field_set": ",".join(sorted(report)) if isinstance(report, Mapping) else "",
                },
            )
            raise self.blocked
        self.terminal_report = True
        # The validated typed report is itself the terminal payload.  A provider
        # turn/completed notification may never arrive; record wall time at the
        # report boundary when no terminal event has already supplied it.
        if self.terminal_wall_ms is None:
            self.terminal_wall_ms = (time.monotonic() - self._started_monotonic) * 1000

    def record_terminal_verdict(self, verdict: Mapping[str, Any]) -> None:
        """Record the real Acceptance terminal output; no synthetic report is accepted."""

        required = {"status", "answer", "evidence_ref_ids", "current", "usable", "failure_layer", "blocked_reason"}
        sequence = {"question_ordinal", "question_count", "previous_question_ordinal", "next_question_ordinal", "final"}
        if not isinstance(verdict, Mapping) or not required.issubset(verdict) or set(verdict) - required - sequence:
            self.blocked = ExaminerRuntimeBlocked(
                "acceptance-evidence",
                role=self.role,
                evidence={
                    "binding_code": "verdict-fields-invalid",
                    "verdict_field_set": ",".join(sorted(verdict)) if isinstance(verdict, Mapping) else "",
                },
            )
            raise self.blocked
        if verdict["status"] not in {"PASS", "FAIL", "BLOCKED"}:
            self.blocked = ExaminerRuntimeBlocked(
                "acceptance-evidence",
                role=self.role,
                evidence={"binding_code": "verdict-status-invalid"},
            )
            raise self.blocked
        if not isinstance(verdict["answer"], str) or not verdict["answer"]:
            self.blocked = ExaminerRuntimeBlocked(
                "acceptance-evidence",
                role=self.role,
                evidence={"binding_code": "verdict-answer-invalid"},
            )
            raise self.blocked
        if not isinstance(verdict["evidence_ref_ids"], list) or not all(
            isinstance(item, str) and item for item in verdict["evidence_ref_ids"]
        ):
            self.blocked = ExaminerRuntimeBlocked(
                "acceptance-evidence",
                role=self.role,
                evidence={"binding_code": "verdict-evidence-refs-invalid"},
            )
            raise self.blocked
        if not isinstance(verdict["current"], bool) or not isinstance(verdict["usable"], bool):
            self.blocked = ExaminerRuntimeBlocked(
                "acceptance-evidence",
                role=self.role,
                evidence={"binding_code": "verdict-flags-invalid"},
            )
            raise self.blocked
        self.terminal_report = True
        if self.terminal_wall_ms is None:
            self.terminal_wall_ms = (time.monotonic() - self._started_monotonic) * 1000

    def allow_inference(self) -> None:
        if self.blocked is not None:
            raise self.blocked
        if self.inference_steps >= self.max_inference_steps:
            self.blocked = ExaminerRuntimeBlocked("runtime-budget", role=self.role, evidence={"steps": self.inference_steps})
            raise self.blocked

    @property
    def token_usage_increments(self) -> tuple[Mapping[str, int], ...]:
        return tuple(MappingProxyType(dict(item)) for item in self._increments)

    def as_dict(self) -> dict[str, Any]:
        totals = dict(self._totals)
        return {
            "schema_version": "ExaminerRunMetrics/v1",
            "role": self.role,
            "fresh_thread_id": self.thread_id,
            "fresh_thread": self.thread_id is not None and self.inherited_turns == 0,
            "metrics_complete": bool(
                self.thread_id
                and self.ttft_ms is not None
                and (self.terminal_event or self.terminal_report)
            ),
            "inherited_turns": self.inherited_turns,
            "first_turn_input": {
                "fields": list(self.first_turn_input_fields),
                "digest": self.first_turn_input_digest,
            },
            "turn_start_count": self.turn_start_count,
            "inference_steps": self.inference_steps,
            "token_usage_increments": [dict(item) for item in self._increments],
            "first_input_tokens": self._first_input_tokens or 0,
            "total_tokens": totals.get("totalTokens", 0),
            "cached_input_tokens": totals.get("cachedInputTokens", 0),
            "cache_write_input_tokens": totals.get("cacheWriteInputTokens", 0),
            "output_tokens": totals.get("outputTokens", 0),
            "reasoning_output_tokens": totals.get("reasoningOutputTokens", 0),
            "model_context_window": totals.get("modelContextWindow", 0),
            "token_estimate_algorithm": "canonical_utf8_bytes_div_4_ceil",
            "estimated_task_tokens": self.packet_tokens,
            "estimated_evidence_tokens": self.source_bytes_tokens + self.platform_response_tokens,
            "task_tokens": self.packet_tokens,
            "evidence_tokens": self.source_bytes_tokens + self.platform_response_tokens,
            "ttft_ms": self.ttft_ms,
            "terminal_wall_ms": self.terminal_wall_ms,
            "proxy_time_ms": self.proxy_time_ms,
            "collaboration_rejections": self.collaboration_rejections,
            "terminal_report": self.terminal_report,
            "blocked": self.blocked.as_dict() if self.blocked else None,
        }


def aggregate_ordered_examiner_verdicts(verdicts: Iterable[Mapping[str, Any]], *, count: int | None = None) -> dict[str, Any]:
    rows = [dict(value) for value in verdicts]
    expected = len(rows) if count is None else count
    if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0 or len(rows) != expected:
        raise ChildRuntimeError("ordered Examiner verdict count is invalid")
    def row_ordinal(row: Mapping[str, Any]) -> Any:
        return row.get("question_ordinal", row.get("ordinal"))

    if [row_ordinal(row) for row in rows] != list(range(1, expected + 1)):
        raise ChildRuntimeError("ordered Examiner verdict ordinals are not contiguous")
    statuses = [row.get("status", row.get("verdict")) for row in rows]
    if any(status not in {"PASS", "FAIL", "BLOCKED"} for status in statuses):
        raise ChildRuntimeError("ordered Examiner verdict status is invalid")
    for index, row in enumerate(rows, start=1):
        if row_ordinal(row) != index:
            raise ChildRuntimeError("ordered Examiner verdict ordinal is invalid")
        if row.get("question_count", row.get("count")) != expected:
            raise ChildRuntimeError("ordered Examiner verdict count is invalid")
        if row.get("previous_question_ordinal") != (index - 1 if index > 1 else None):
            raise ChildRuntimeError("ordered Examiner previous ordinal is invalid")
        if row.get("next_question_ordinal") != (index + 1 if index < expected else None):
            raise ChildRuntimeError("ordered Examiner next ordinal is invalid")
        if row.get("final") is not (index == expected):
            raise ChildRuntimeError("ordered Examiner final marker is invalid")
    status = "BLOCKED" if "BLOCKED" in statuses else "FAIL" if "FAIL" in statuses else "PASS"
    return {
        "schema_version": "ExaminerOrderedVerdicts/v1",
        "count": expected,
        "verdicts": rows,
        "status": status,
        "previous": rows[-1].get("previous_question_ordinal"),
        "next": rows[-1].get("next_question_ordinal"),
        "final": True,
    }


class LeanExaminerRuntime:
    """Small opt-in host orchestration seam for fresh Source/Platform/Acceptance roles.

    Executors are intentionally injected: the production Codex adapter can provide a
    process-backed executor, while independent tests use deterministic executors.  Every
    call receives a new packet and metrics object; no prior report is passed to the next CQ.
    """

    def __init__(
        self,
        *,
        source_executor: Callable[[ExaminerRolePacket, ExaminerRunMetrics], Mapping[str, Any]] | None = None,
        platform_executor: Callable[[ExaminerRolePacket, ExaminerRunMetrics], Mapping[str, Any]] | None = None,
        acceptance_executor: Callable[[ExaminerRolePacket, ExaminerRunMetrics], Mapping[str, Any]] | None = None,
        codex_adapter: Any | None = None,
        platform_read_key: str | None = None,
        platform_forwarder: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        child_timeout_seconds: float = 90.0,
        platform_child_timeout_seconds: float | None = None,
        platform_retry_limit: int = 1,
        acceptance_retry_limit: int = 0,
    ):
        if codex_adapter is not None:
            if any(executor is not None for executor in (source_executor, platform_executor, acceptance_executor)):
                raise ChildRuntimeError("Lean Examiner executors cannot mix Codex wiring")
            runner = getattr(codex_adapter, "run_lean_examiner_child", None)
            if not callable(runner):
                raise ChildRuntimeError("Codex Examiner executor is unavailable")

            def run_source(packet: ExaminerRolePacket, metrics: ExaminerRunMetrics) -> Mapping[str, Any]:
                return runner(packet, metrics, timeout_seconds=child_timeout_seconds)

            def run_platform(packet: ExaminerRolePacket, metrics: ExaminerRunMetrics) -> Mapping[str, Any]:
                if not isinstance(platform_read_key, str) or not platform_read_key:
                    raise ExaminerRuntimeBlocked("acceptance-input", role="platform")
                return runner(
                    packet,
                    metrics,
                    read_key=platform_read_key,
                    platform_forwarder=platform_forwarder,
                    timeout_seconds=(
                        platform_child_timeout_seconds
                        if platform_child_timeout_seconds is not None
                        else child_timeout_seconds
                    ),
                )

            def run_acceptance(packet: ExaminerRolePacket, metrics: ExaminerRunMetrics) -> Mapping[str, Any]:
                return runner(packet, metrics, timeout_seconds=child_timeout_seconds)

            source_executor, platform_executor, acceptance_executor = (
                run_source,
                run_platform,
                run_acceptance,
            )
        if not all(callable(executor) for executor in (source_executor, platform_executor, acceptance_executor)):
            raise ChildRuntimeError("Lean Examiner executors are incomplete")
        self.source_executor = source_executor
        self.platform_executor = platform_executor
        self.acceptance_executor = acceptance_executor
        self._platform_retry_limit = max(0, int(platform_retry_limit))
        self._acceptance_retry_limit = max(0, int(acceptance_retry_limit))
        if platform_child_timeout_seconds is not None:
            try:
                platform_child_timeout_seconds = float(platform_child_timeout_seconds)
            except (TypeError, ValueError) as exc:
                raise ChildRuntimeError("platform child timeout is invalid") from exc
            if platform_child_timeout_seconds <= 0:
                raise ChildRuntimeError("platform child timeout is invalid")
        self._platform_child_timeout_seconds = platform_child_timeout_seconds
        self._failure_metrics: tuple[dict[str, Any], ...] = ()

    @property
    def failure_metrics(self) -> tuple[dict[str, Any], ...]:
        """Return copied per-role snapshots captured by the last failed run."""

        return tuple(deepcopy(row) for row in self._failure_metrics)

    def _capture_failure_metrics(
        self,
        metrics: Sequence[ExaminerRunMetrics],
        error: BaseException,
    ) -> None:
        """Retain only recomputable metrics for a failed role stage."""

        snapshots = list(metrics)
        if isinstance(error, ExaminerRuntimeBlocked) and snapshots and snapshots[-1].blocked is None:
            snapshots[-1].blocked = error
        self._failure_metrics = tuple(metric.as_dict() for metric in snapshots)

    def run(self, questions: Sequence[Mapping[str, Any]], *, source_packets: Sequence[Mapping[str, Any]], platform_packets: Sequence[Mapping[str, Any]], ticket_binding: Mapping[str, Any], verdict_schema: Mapping[str, Any], stage: str = "all") -> dict[str, Any]:
        if stage not in {"all", "platform"}:
            raise ChildRuntimeError("Lean Examiner stage is invalid")
        count = len(questions)
        if count <= 0 or len(source_packets) != count or len(platform_packets) != count:
            raise ChildRuntimeError("Lean Examiner question/packet count is invalid")
        self._failure_metrics = ()
        verdicts: list[dict[str, Any]] = []
        metrics: list[dict[str, Any]] = []
        completed_metrics: list[ExaminerRunMetrics] = []
        for ordinal, question in enumerate(questions):
            source_payload = dict(source_packets[ordinal])
            platform_payload = dict(platform_packets[ordinal])
            question_ordinal = ordinal + 1
            source_payload.update(question=question.get("question"), ordinal=question_ordinal, count=count)
            platform_payload.update(
                question=question.get("question"),
                ordinal=question_ordinal,
                count=count,
                ticket_binding=platform_payload.get("ticket_binding", dict(ticket_binding)),
                allowed_read_tools=platform_payload.get("allowed_read_tools", list(PLATFORM_PROXY_READ_TOOLS)),
            )
            source_packet = build_source_examiner_packet(**source_payload)
            platform_packet = build_platform_examiner_packet(**platform_payload)
            if stage == "platform":
                source_report: Mapping[str, Any] = {
                    "answerability": "answerable",
                    "conclusion": "standalone-platform-probe",
                    "evidence": [],
                    "coverage": {"queries_or_sections": [], "complete": True},
                    "gaps": [],
                    "evidence_refs": [{"location": "standalone.md"}],
                }
                source_metrics = ExaminerRunMetrics("source")
                source_evidence_ids: set[str] = set()
            else:
                source_metrics = ExaminerRunMetrics("source")
            if stage == "platform":
                source_metrics.record_terminal_report(source_report)
                source_evidence_ids = set()
            else:
                try:
                    source_metrics.bind_first_turn_input([{"type": "packet", "digest": source_packet.canonical_digest}], packet=source_packet)
                    source_report = self.source_executor(source_packet, source_metrics)
                    source_evidence_ids = _source_report_evidence_ids(source_packet, source_report)
                    source_metrics.record_terminal_report(source_report)
                except BaseException as exc:
                    self._capture_failure_metrics([*completed_metrics, source_metrics], exc)
                    raise
            platform_metrics = ExaminerRunMetrics("platform")
            platform_retry_used = False
            try:
                platform_metrics.bind_first_turn_input([{"type": "packet", "digest": platform_packet.canonical_digest}], packet=platform_packet)
                try:
                    platform_report = self.platform_executor(platform_packet, platform_metrics)
                except ExaminerRuntimeBlocked:
                    # A Platform child that stops generating after the retrieval
                    # wave (DeepSeek provider behavior) is retried once with a
                    # fresh child and fresh metrics; the read key and forwarder
                    # remain Host-owned and unchanged.
                    if not getattr(self, "_platform_retry_limit", 1) or platform_retry_used:
                        raise
                    platform_retry_used = True
                    platform_metrics = ExaminerRunMetrics("platform")
                    platform_metrics.bind_first_turn_input([{"type": "packet", "digest": platform_packet.canonical_digest}], packet=platform_packet)
                    platform_report = self.platform_executor(platform_packet, platform_metrics)
                platform_evidence_ids = _platform_report_ref_ids(platform_report)
                platform_metrics.record_terminal_report(platform_report)
            except BaseException as exc:
                self._capture_failure_metrics([*completed_metrics, source_metrics, platform_metrics], exc)
                raise
            if stage == "platform":
                metrics.extend([source_metrics.as_dict(), platform_metrics.as_dict()])
                completed_metrics.extend([source_metrics, platform_metrics])
                return {
                    "schema_version": "ExaminerOrderedVerdicts/v1",
                    "count": count,
                    "verdicts": [],
                    "status": "PLATFORM-ONLY",
                    "complete": False,
                    "stopped_at": question_ordinal,
                    "next": question_ordinal + 1 if question_ordinal < count else None,
                    "final": question_ordinal == count,
                    "platform_report": dict(platform_report),
                    "metrics": metrics,
                }
            source_digest, platform_digest = _packet_digest(source_report), _packet_digest(platform_report)
            acceptance_metrics = ExaminerRunMetrics("acceptance")
            acceptance_retry_used = False
            try:
                acceptance_packet = build_acceptance_examiner_packet(
                    question=question.get("question"), ticket_binding=dict(ticket_binding), ordinal=question_ordinal, count=count,
                    source_report=dict(source_report), platform_report=dict(platform_report),
                    source_report_digest=source_digest, platform_report_digest=platform_digest,
                    source_evidence_ref_ids=sorted(source_evidence_ids),
                    platform_evidence_ref_ids=sorted(platform_evidence_ids),
                    verdict_schema=dict(verdict_schema),
                )
                acceptance_metrics.bind_first_turn_input([{"type": "packet", "digest": acceptance_packet.canonical_digest}], packet=acceptance_packet)
                try:
                    verdict = dict(self.acceptance_executor(acceptance_packet, acceptance_metrics))
                except ExaminerRuntimeBlocked:
                    # The Acceptance model frequently reasons without calling the
                    # submit tool (DeepSeek behavior).  Retry with a fresh child
                    # and fresh metrics; the packet is immutable and unchanged.
                    if not getattr(self, "_acceptance_retry_limit", 0) or acceptance_retry_used:
                        raise
                    acceptance_retry_used = True
                    acceptance_metrics = ExaminerRunMetrics("acceptance")
                    acceptance_metrics.bind_first_turn_input([{"type": "packet", "digest": acceptance_packet.canonical_digest}], packet=acceptance_packet)
                    verdict = dict(self.acceptance_executor(acceptance_packet, acceptance_metrics))
                _validate_acceptance_evidence_ids(verdict, source_evidence_ids | platform_evidence_ids)
                verdict.setdefault("question_ordinal", question_ordinal)
                verdict.setdefault("question_count", count)
                verdict.setdefault("previous_question_ordinal", question_ordinal - 1 if question_ordinal > 1 else None)
                verdict.setdefault("next_question_ordinal", question_ordinal + 1 if question_ordinal < count else None)
                verdict.setdefault("final", question_ordinal == count)
                acceptance_metrics.record_terminal_verdict(verdict)
            except BaseException as exc:
                self._capture_failure_metrics([*completed_metrics, source_metrics, platform_metrics, acceptance_metrics], exc)
                raise
            verdicts.append(verdict)
            metrics.extend([source_metrics.as_dict(), platform_metrics.as_dict(), acceptance_metrics.as_dict()])
            completed_metrics.extend([source_metrics, platform_metrics, acceptance_metrics])
            if not (
                verdict.get("status", verdict.get("verdict")) == "PASS"
                and verdict.get("current") is True
                and verdict.get("usable") is True
            ):
                return {
                    "schema_version": "ExaminerOrderedVerdicts/v1",
                    "count": count,
                    "verdicts": verdicts,
                    "status": verdict.get("status", verdict.get("verdict")),
                    "complete": False,
                    "stopped_at": question_ordinal,
                    "next": question_ordinal + 1 if question_ordinal < count else None,
                    "final": question_ordinal == count,
                    "metrics": metrics,
                }
        result = aggregate_ordered_examiner_verdicts(verdicts, count=count)
        result["complete"] = True
        result["metrics"] = metrics
        return result


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ChildRuntimeError(f"{field} is invalid")
    return value


def _looks_like_absolute_iri(value: Any) -> bool:
    if not isinstance(value, str) or value != value.strip() or any(
        character.isspace() for character in value
    ):
        return False
    return value.startswith(("http://", "https://", "urn:"))


def _safe_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in value):
        raise ChildRuntimeError(f"{field} is invalid")
    return value


_REPORT_SEMANTIC_FIELDS = frozenset(
    {"answerability", "conclusion", "evidence", "coverage", "gaps", "evidence_refs"}
)
_REPORT_PLATFORM_LOCATOR_FIELDS = frozenset(
    {"ref_id", "tool", "request_digest", "response_digest", "artifact_path", "page"}
)


def _validate_report_sink_payload(
    value: Any, *, kind: str, batch_contract: "V3BatchReportContract | None" = None
) -> dict[str, Any]:
    """Validate the kind-specific child payload before invoking the Host callback.

    ``batch_contract`` selects the explicit v3 batch branch (dispatched by the
    packet schema, never by kind alone): the per-question entry is validated
    against the session's own batch binding.  Without it the legacy R2.3
    per-question contracts below are applied unchanged.
    """

    if batch_contract is not None:
        if kind not in {"platform", "acceptance"}:
            raise ChildRuntimeError("report sink kind is invalid")
        expected_role = CQ_ACCEPTANCE_PLATFORM_ROLE if kind == "platform" else (
            CQ_ACCEPTANCE_JUDGE_ROLE
        )
        if batch_contract.role != expected_role:
            raise ChildRuntimeError("v3 batch report contract does not match the sink kind")
        return batch_contract.validate(value)
    if kind == "acceptance":
        expected = {"status", "answer", "evidence_ref_ids", "current", "usable", "failure_layer", "blocked_reason"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ChildRuntimeError("acceptance verdict fields drift")
        if value["status"] not in {"PASS", "FAIL", "BLOCKED"} or not isinstance(value["answer"], str) or not value["answer"]:
            raise ChildRuntimeError("acceptance verdict is invalid")
        if not isinstance(value["evidence_ref_ids"], list) or any(not isinstance(item, str) or not item for item in value["evidence_ref_ids"]):
            raise ChildRuntimeError("acceptance verdict evidence refs are invalid")
        if not isinstance(value["current"], bool) or not isinstance(value["usable"], bool):
            raise ChildRuntimeError("acceptance verdict flags are invalid")
        if value["status"] == "PASS" and (value["failure_layer"] is not None or value["blocked_reason"] is not None):
            raise ChildRuntimeError("acceptance PASS carries failure fields")
        return dict(value)
    if kind not in {"source", "platform"}:
        raise ChildRuntimeError("report sink kind is invalid")
    if not isinstance(value, Mapping) or set(value) != _REPORT_SEMANTIC_FIELDS:
        raise ChildRuntimeError("report payload fields drift")
    if value["answerability"] not in {"answerable", "insufficient-evidence", "unavailable"}:
        raise ChildRuntimeError("report answerability is invalid")
    if not isinstance(value["conclusion"], str) or not value["conclusion"]:
        raise ChildRuntimeError("report conclusion is invalid")
    if not isinstance(value["evidence"], list) or not isinstance(value["gaps"], list):
        raise ChildRuntimeError("report evidence/gaps are invalid")
    coverage = value["coverage"]
    if (
        not isinstance(coverage, Mapping)
        or set(coverage) != {"queries_or_sections", "complete"}
        or not isinstance(coverage["queries_or_sections"], list)
        or not isinstance(coverage["complete"], bool)
    ):
        raise ChildRuntimeError("report coverage is invalid")
    refs = value["evidence_refs"]
    if not isinstance(refs, list) or not refs:
        raise ChildRuntimeError("report evidence_refs are invalid")
    for ref in refs:
        if not isinstance(ref, Mapping):
            raise ChildRuntimeError("report evidence locator is invalid")
        if kind == "source":
            if set(ref) != {"location"} or not isinstance(ref["location"], str) or not ref["location"]:
                raise ChildRuntimeError("source evidence locator is invalid")
            path = ref["location"].split("#", 1)[0]
            if not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ChildRuntimeError("source evidence locator path is invalid")
        else:
            if set(ref) != _REPORT_PLATFORM_LOCATOR_FIELDS:
                raise ChildRuntimeError("platform evidence locator fields drift")
            if not isinstance(ref["ref_id"], str) or not ref["ref_id"]:
                raise ChildRuntimeError("platform evidence locator ref_id is invalid")
            if not isinstance(ref["tool"], str) or not ref["tool"]:
                raise ChildRuntimeError("platform evidence locator tool is invalid")
            # R2.3-009 examiner diagnosis (2026-08-21): demanding hand-copied
            # 64-hex digests here rejected live Examiner reports for one
            # transcribed character while every locator field is recoverable
            # from the proxy receipt.  Digest transcription is protocol
            # mechanics the tool layer owns: accept any non-empty string and
            # let ``_validate_platform_report_receipts`` stamp the canonical
            # receipt values before the report is delivered.
            for field in ("request_digest", "response_digest"):
                if not isinstance(ref[field], str) or not ref[field]:
                    raise ChildRuntimeError(f"platform evidence locator {field} is invalid")
            path = ref["artifact_path"]
            if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ChildRuntimeError("platform evidence locator path is invalid")
            page = ref["page"]
            if not isinstance(page, Mapping) or set(page) != {
                "ordinal", "input_cursor", "output_cursor", "has_more", "sequence_complete"
            }:
                raise ChildRuntimeError("platform evidence locator page is invalid")
            if not isinstance(page["ordinal"], int) or page["ordinal"] < 0:
                raise ChildRuntimeError("platform evidence locator page ordinal is invalid")
            if not isinstance(page["input_cursor"], (str, type(None))) or not isinstance(
                page["output_cursor"], (str, type(None))
            ):
                raise ChildRuntimeError("platform evidence locator page cursors are invalid")
            if not isinstance(page["has_more"], bool) or not isinstance(
                page["sequence_complete"], bool
            ):
                raise ChildRuntimeError("platform evidence locator page flags are invalid")
            if page["has_more"] and page["sequence_complete"]:
                raise ChildRuntimeError("platform evidence locator page is incomplete and complete")
    return dict(value)


def _source_report_evidence_ids(packet: ExaminerRolePacket, report: Mapping[str, Any]) -> set[str]:
    """Bind Source report locations to this packet's approved manifest."""

    approved: dict[str, str] = {}
    sources = packet.payload.get("approved_sources")
    if not isinstance(sources, (list, tuple)):
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence", role="source",
            evidence={"binding_code": "approved-sources-missing"},
        )
    for source in sources:
        if not isinstance(source, Mapping):
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="source",
                evidence={"binding_code": "approved-source-shape"},
            )
        path, digest = source.get("path"), source.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str) or path in approved:
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="source",
                evidence={"binding_code": "approved-source-invalid"},
            )
        approved[path] = digest
    refs = report.get("evidence_refs") if isinstance(report, Mapping) else None
    if not isinstance(refs, list) or not refs:
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence", role="source",
            evidence={"binding_code": "source-refs-invalid"},
        )
    seen_paths: set[str] = set()
    result: set[str] = set()
    for ref in refs:
        if not isinstance(ref, Mapping) or not isinstance(ref.get("location"), str):
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="source",
                evidence={"binding_code": "source-locator-shape"},
            )
        path = ref["location"].split("#", 1)[0]
        if path not in approved or path in seen_paths:
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="source",
                evidence={"binding_code": "source-path-unauthorized", "path": path},
            )
        seen_paths.add(path)
        result.add(f"source:{_packet_digest({'path': path, 'sha256': approved[path]})}")
    return result


def _platform_report_ref_ids(report: Mapping[str, Any]) -> set[str]:
    """Return only report-local Platform ref IDs after shape validation."""

    refs = report.get("evidence_refs") if isinstance(report, Mapping) else None
    if not isinstance(refs, list) or not refs:
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence", role="platform",
            evidence={"binding_code": "platform-refs-invalid"},
        )
    result: set[str] = set()
    for index, ref in enumerate(refs):
        ref_id = ref.get("ref_id") if isinstance(ref, Mapping) else None
        if not isinstance(ref_id, str) or not ref_id or ref_id in result:
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="platform",
                evidence={"binding_code": "ref-id-invalid", "index": index},
            )
        result.add(ref_id)
    return result


def _ref_id_summary(refs: Any) -> str:
    """Join report-local ref_ids into one safe diagnostic string.

    Only printable safe characters survive; anything else is dropped so the
    summary can never carry secrets, quotes, or control characters.
    """

    if not isinstance(refs, (list, tuple)):
        return ""
    safe = re.compile(r"[^A-Za-z0-9_:\-]")
    parts: list[str] = []
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        ref_id = ref.get("ref_id")
        if not isinstance(ref_id, str) or not ref_id:
            continue
        cleaned = safe.sub("", ref_id)
        if cleaned and len(cleaned) <= 64:
            parts.append(cleaned)
    return ",".join(parts)[:200]


def _ref_tool_summary(refs: Any) -> str:
    """Join report-local locator tool names into one safe diagnostic string."""

    if not isinstance(refs, (list, tuple)):
        return ""
    safe = re.compile(r"[^A-Za-z0-9_:\-]")
    parts: list[str] = []
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        tool = ref.get("tool")
        if not isinstance(tool, str) or not tool:
            continue
        cleaned = safe.sub("", tool)
        if cleaned and len(cleaned) <= 64:
            parts.append(cleaned)
    return ",".join(parts)[:200]


def _receipt_tool_summary(receipts: Any) -> str:
    """Join proxy receipt tool names into one safe diagnostic string."""

    if not isinstance(receipts, (list, tuple)):
        return ""
    safe = re.compile(r"[^A-Za-z0-9_:\-]")
    parts: list[str] = []
    for receipt in receipts:
        tool = getattr(receipt, "tool", None)
        if not isinstance(tool, str) or not tool:
            continue
        cleaned = safe.sub("", tool)
        if cleaned and len(cleaned) <= 64:
            parts.append(cleaned)
    return ",".join(parts)[:200]


def _receipt_ordinal_summary(receipts: Any) -> str:
    """Join proxy receipt ordinals into one safe diagnostic string."""

    if not isinstance(receipts, (list, tuple)):
        return ""
    return ",".join(str(getattr(item, "ordinal", None)) for item in receipts)


def _validate_platform_report_receipts(report: Mapping[str, Any], resource: Any) -> set[str]:
    """Bind every Platform locator to one current-child proxy receipt and page."""

    proxy = getattr(resource, "proxy", None)
    snapshots = getattr(proxy, "receipt_snapshot", None) if proxy is not None else None
    if callable(snapshots):
        snapshots = snapshots()
    if not isinstance(snapshots, (list, tuple)):
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence", role="platform",
            evidence={"binding_code": "receipt-snapshot-invalid"},
        )
    receipts = tuple(snapshots)
    refs = report.get("evidence_refs") if isinstance(report, Mapping) else None
    if not isinstance(refs, list):
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence",
            role="platform",
            evidence={
                "binding_code": "report-refs-invalid",
                "report_ref_count": 0,
                "proxy_receipt_count": len(receipts),
            },
        )
    if not receipts:
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence",
            role="platform",
            evidence={
                "binding_code": "receipts-empty",
                "report_ref_count": len(refs),
                "proxy_receipt_count": 0,
            },
        )
    if len(refs) != len(receipts):
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence",
            role="platform",
            evidence={
                "binding_code": "receipt-count-mismatch",
                "report_ref_count": len(refs),
                "proxy_receipt_count": len(receipts),
                "report_ref_ids": _ref_id_summary(refs),
                "report_ref_tools": _ref_tool_summary(refs),
                "proxy_receipt_ordinals": _receipt_ordinal_summary(receipts),
                "proxy_receipt_tools": _receipt_tool_summary(receipts),
            },
        )
    result: set[str] = set()
    previous_ref: Mapping[str, Any] | None = None
    previous_page: Mapping[str, Any] | None = None
    for index, ref in enumerate(refs):
        if not isinstance(ref, Mapping):
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="platform",
                evidence={"binding_code": "locator-shape", "index": index},
            )
        receipt = receipts[index]
        if getattr(receipt, "ordinal", None) != index:
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="platform",
                evidence={"binding_code": "ordinal-mismatch", "index": index},
            )
        # R2.3-009 examiner diagnosis (2026-08-21): the child had every digest
        # available yet still mis-transcribed one of 64-hex characters, and the
        # whole acceptance round died on that typo.  The locator's position is
        # already pinned by count + ordinal + tool, so the remaining fields are
        # deterministic receipt data: match on ``tool`` only and stamp the
        # canonical ``request_digest``/``response_digest``/``artifact_path``
        # from the receipt onto the delivered report in place.
        if ref.get("tool") != getattr(receipt, "tool", None):
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="platform",
                evidence={"binding_code": "locator-key-mismatch", "index": index},
            )
        if isinstance(ref, dict):
            ref["request_digest"] = receipt.request_digest
            ref["response_digest"] = receipt.response_digest
            ref["artifact_path"] = receipt.artifact_path
            # R2.3-009 start21 (2026-08-22): the page chain is the second piece
            # of deterministic receipt data the child was asked to transcribe,
            # and hand-built page objects were the rejection that burned the
            # round to the child-timeout watchdog.  The proxy derived each
            # page from the live cursors at call time; stamp it in place too.
            stamped_page = getattr(receipt, "page", None)
            if isinstance(stamped_page, Mapping) and stamped_page:
                ref["page"] = dict(stamped_page)
        page = ref.get("page")
        if (
            not isinstance(page, Mapping)
            or not isinstance(page.get("ordinal"), int)
            or page.get("ordinal") < 0
            or not isinstance(page.get("input_cursor"), (str, type(None)))
            or not isinstance(page.get("output_cursor"), (str, type(None)))
            or not isinstance(page.get("has_more"), bool)
            or not isinstance(page.get("sequence_complete"), bool)
        ):
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="platform",
                evidence={"binding_code": "page-shape", "index": index},
            )
        if page["ordinal"] == 0:
            if page["input_cursor"] is not None or (previous_page is not None and previous_page.get("has_more")):
                raise ExaminerRuntimeBlocked(
                    "acceptance-evidence", role="platform",
                    evidence={"binding_code": "page-first-invalid", "index": index},
                )
        else:
            if (
                previous_ref is None
                or previous_page is None
                or previous_page.get("has_more") is not True
                or ref.get("tool") != previous_ref.get("tool")
                or page["ordinal"] != previous_page.get("ordinal", -1) + 1
                or page["input_cursor"] != previous_page.get("output_cursor")
            ):
                raise ExaminerRuntimeBlocked(
                    "acceptance-evidence", role="platform",
                    evidence={"binding_code": "page-sequence-invalid", "index": index},
                )
        if page["has_more"]:
            if page["sequence_complete"] or not isinstance(page["output_cursor"], str) or not page["output_cursor"]:
                raise ExaminerRuntimeBlocked(
                    "acceptance-evidence", role="platform",
                    evidence={"binding_code": "page-has-more-invalid", "index": index},
                )
            if index == len(refs) - 1:
                raise ExaminerRuntimeBlocked(
                    "acceptance-evidence", role="platform",
                    evidence={"binding_code": "page-truncated-locator", "index": index},
                )
        elif page["sequence_complete"] is not True or page["output_cursor"] is not None:
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="platform",
                evidence={"binding_code": "page-final-invalid", "index": index},
            )
        ref_id = ref.get("ref_id")
        if not isinstance(ref_id, str) or not ref_id or ref_id in result:
            raise ExaminerRuntimeBlocked(
                "acceptance-evidence", role="platform",
                evidence={"binding_code": "ref-id-invalid", "index": index},
            )
        result.add(ref_id)
        previous_ref, previous_page = ref, page
    return result


def _validate_acceptance_evidence_ids(verdict: Mapping[str, Any], allowed_ids: set[str]) -> None:
    """Accept only current Source/Platform evidence IDs; PASS must cite one."""

    ids = verdict.get("evidence_ref_ids") if isinstance(verdict, Mapping) else None
    if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence", role="acceptance",
            evidence={"binding_code": "verdict-ref-ids-shape"},
        )
    if len(ids) != len(set(ids)) or any(item not in allowed_ids for item in ids):
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence", role="acceptance",
            evidence={"binding_code": "verdict-ref-ids-not-allowed"},
        )
    if verdict.get("status") == "PASS" and not ids:
        raise ExaminerRuntimeBlocked(
            "acceptance-evidence", role="acceptance",
            evidence={"binding_code": "verdict-pass-without-evidence"},
        )


def _blocked_detail(blocked: ExaminerRuntimeBlocked) -> str:
    """Turn one typed binding rejection into an actionable child-readable message."""

    evidence = blocked.evidence if isinstance(blocked.evidence, Mapping) else {}
    code = evidence.get("binding_code")
    index = evidence.get("index")
    prefix = f"binding_code={code}" if isinstance(code, str) else "binding-rejected"
    location = f" at locator index {index}" if isinstance(index, int) else ""
    details: list[str] = []
    for key in ("report_ref_count", "proxy_receipt_count", "report_ref_ids", "proxy_receipt_ordinals"):
        value = evidence.get(key)
        if isinstance(value, (int, str)) and str(value):
            details.append(f"{key}={value}")
    message = prefix + location
    if details:
        message += " (" + ", ".join(details) + ")"
    return message


def _make_report_validator(kind: str, packet: ExaminerRolePacket, resource: Any | None = None) -> Callable[[Mapping[str, Any]], None] | None:
    """Return a sink-time validator that gives the child precise rejection reasons."""

    if kind == "source":
        def validate_source(report: Mapping[str, Any]) -> None:
            try:
                _source_report_evidence_ids(packet, report)
            except ExaminerRuntimeBlocked as exc:
                raise ExaminerRuntimeBlocked(
                    exc.reason, role="source",
                    evidence=dict(exc.evidence) if isinstance(exc.evidence, Mapping) else {},
                ) from exc
        return validate_source
    if kind == "platform":
        def validate_platform(report: Mapping[str, Any]) -> None:
            if resource is None or getattr(resource, "proxy", None) is None:
                raise ExaminerRuntimeBlocked(
                    "acceptance-evidence", role="platform",
                    evidence={"binding_code": "receipt-snapshot-invalid"},
                )
            try:
                _validate_platform_report_receipts(report, resource)
            except ExaminerRuntimeBlocked as exc:
                raise ExaminerRuntimeBlocked(
                    exc.reason, role="platform",
                    evidence=dict(exc.evidence) if isinstance(exc.evidence, Mapping) else {},
                ) from exc
        return validate_platform
    if kind == "acceptance":
        allowed_ids = set()
        for field in ("source_evidence_ref_ids", "platform_evidence_ref_ids"):
            values = packet.payload.get(field)
            if isinstance(values, (list, tuple)):
                allowed_ids.update(str(value) for value in values)

        def validate_acceptance(verdict: Mapping[str, Any]) -> None:
            try:
                _validate_acceptance_evidence_ids(verdict, allowed_ids)
            except ExaminerRuntimeBlocked as exc:
                raise ExaminerRuntimeBlocked(
                    exc.reason, role="acceptance",
                    evidence=dict(exc.evidence) if isinstance(exc.evidence, Mapping) else {},
                ) from exc
        return validate_acceptance
    return None


def _private_dir(path: Path, *, create: bool = False) -> None:
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise ChildRuntimeError("private runtime directory is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
    ):
        raise ChildRuntimeError("private runtime directory is not 0700")


def _write_private(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.is_symlink() or path.exists():
        raise ChildRuntimeError("private runtime artifact already exists")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _copy_private(source: Path, target: Path, mode: int) -> None:
    """Copy one trusted regular file into a private tree without following links."""
    try:
        metadata = os.lstat(source)
    except OSError as exc:
        raise ChildRuntimeError("private source is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ChildRuntimeError("private source is invalid")
    _private_dir(target.parent)
    descriptor = -1
    try:
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ChildRuntimeError("private source is invalid")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            payload = stream.read()
    except OSError as exc:
        raise ChildRuntimeError("private source is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    _write_private(target, payload, mode)


# R2.3-006 Platform Examiner consumes only the generic semantic query interface.
# It must not read modeling-context, build-session, read-model, or projection
# internals; those are modeling/Producer concerns, not consumer retrieval.  The
# full read-tool catalog below remains shared with R2.3-005; the R2.3-006
# operation narrows the child to semantic query only.
PLATFORM_PROXY_READ_TOOLS: tuple[str, ...] = (
    "check_platform_health",
    "get_project_build_context",
    "get_build_session",
    "get_modeling_context",
    "get_ontology_workspace_context",
    "get_ontology_read_model",
    "get_entity_statement_context",
    "get_semantic_read_model",
    "query_semantic_context",
    "semantic_sparql_query",
    "describe_semantic_graph_set",
    "list_semantic_derived_pointers",
    "inspect_semantic_projection_status",
    "list_evidence_references",
    "get_evidence_reference",
    "get_ontology_lineage",
    "inspect_semantic_statement_provenance",
    "get_semantic_reasoning_run",
    "get_semantic_validation_run",
    "list_semantic_reasoning_runs",
    "list_semantic_validation_runs",
)


# The R2.3-006 wrapper schema is deliberately represented as a small JSON-Schema
# subset.  It is frozen here rather than inferred from a backend response: unknown,
# missing, and wrong-type arguments therefore fail before a forwarder is queued.
_EXAMINER_SCOPE_SCHEMA: dict[str, Any] = {
    "project_id": {"type": "string"},
    "ontology_id": {"type": "string"},
    "graph_set_id": {"type": "string"},
    "ticket_digest": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
    "model_state_digest": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
}
_EXAMINER_TOOL_FIELDS: dict[str, dict[str, dict[str, Any]]] = {
    "check_platform_health": {},
    "get_project_build_context": {
        "recent_session_limit": {"type": "integer", "minimum": 0},
        "recent_session_cursor": {"type": "integer", "minimum": 0},
    },
    "get_build_session": {
        "session_id": {"type": "string"},
        "checkpoint_limit": {"type": "integer", "minimum": 1},
        "checkpoint_cursor": {"type": ["integer", "null"], "minimum": 0},
    },
    "get_modeling_context": {},
    "get_ontology_workspace_context": {},
    "get_ontology_read_model": {
        "model_name": {"type": "string", "enum": ["classes", "entities", "facts", "rules"]},
        "include": {"type": "string", "enum": ["asserted"]},
        "allow_stale_derived": {"type": "boolean", "const": False},
        "field_set": {"type": "string", "enum": ["summary", "full"]},
        "limit": {"type": "integer", "minimum": 1},
        "entity_iri": {"type": "string"}, "class_iri": {"type": "string"},
        "kind": {"type": "string"}, "q": {"type": "string"},
    },
    "get_entity_statement_context": {"entity_iri": {"type": "string"}},
    "get_semantic_read_model": {
        "model_name": {"type": "string"},
        "include": {"type": "string"},
        "allow_stale_derived": {"type": "boolean"},
        "limit": {"type": "integer", "minimum": 1},
    },
    "query_semantic_context": {
        "scope_mode": {"type": "string", "const": "ontologies"},
        "query": {"type": ["string", "null"]}, "queries": {"type": ["array", "null"], "items": {"type": "string"}},
        "ontology_ids": {"type": "array", "items": {"type": "string"}},
        "resource_types": {"type": ["array", "null"], "items": {"type": "string"}},
        "assertion_types": {"type": ["array", "null"], "items": {"type": "string"}}, "search_mode": {"type": "string"},
        "depth": {"type": "integer", "minimum": 1, "maximum": 1},
        "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        "context_limit": {"type": "integer", "minimum": 0, "maximum": 3},
        "match_cursor": {"type": "string"}, "context_cursor": {"type": "string"},
        "context_detail": {"type": "string", "enum": ["full", "compact"]},
    },
    "semantic_sparql_query": {
        "scope_mode": {"type": "string", "const": "ontologies"}, "query": {"type": "string"},
        "ontology_ids": {"type": "array", "items": {"type": "string"}}, "timeout_seconds": {"type": ["number", "null"]},
        "result_limit": {"type": ["integer", "null"], "minimum": 1},
    },
    "describe_semantic_graph_set": {},
    "list_semantic_derived_pointers": {
        "result_kind": {"type": "string"}, "status": {"type": "string"},
    },
    "inspect_semantic_projection_status": {},
    "list_evidence_references": {
        "search": {"type": "string"}, "limit": {"type": "integer", "minimum": 1},
        "offset": {"type": "integer", "minimum": 0},
    },
    "get_evidence_reference": {"reference_id": {"type": "string"}},
    "get_ontology_lineage": {
        "target_type": {"type": "string"}, "target_id": {"type": "string"},
        "include_history": {"type": "boolean"}, "max_depth": {"type": "integer", "minimum": 1},
        "limit": {"type": "integer", "minimum": 1},
    },
    "inspect_semantic_statement_provenance": {
        "statement_iri": {"type": "string"}, "include": {"type": "string"},
    },
    "get_semantic_reasoning_run": {"reasoning_run_id": {"type": "string"}},
    "get_semantic_validation_run": {"validation_run_id": {"type": "string"}},
    "list_semantic_reasoning_runs": {
        "limit": {"type": "integer", "minimum": 1}, "offset": {"type": "integer", "minimum": 0},
        "kind": {"type": "string"},
    },
    "list_semantic_validation_runs": {
        "limit": {"type": "integer", "minimum": 1}, "offset": {"type": "integer", "minimum": 0},
        "kind": {"type": "string"},
    },
}


def examiner_proxy_schemas(tools: Iterable[str] = PLATFORM_PROXY_READ_TOOLS) -> dict[str, dict[str, Any]]:
    """Return detached exact schemas for the requested read-tool inventory."""

    schemas: dict[str, dict[str, Any]] = {}
    for tool in tools:
        if tool not in PLATFORM_PROXY_READ_TOOLS:
            raise ChildRuntimeError("Examiner proxy schema contains a non-read tool")
        properties = {**_EXAMINER_SCOPE_SCHEMA, **_EXAMINER_TOOL_FIELDS.get(tool, {})}
        required = list(_EXAMINER_SCOPE_SCHEMA)
        required.extend({
            "get_project_build_context": [],
            "get_build_session": ["session_id"],
            "get_modeling_context": [],
            "get_ontology_workspace_context": [],
            "get_ontology_read_model": ["model_name"],
            "get_entity_statement_context": ["entity_iri"],
            "get_semantic_read_model": ["model_name"],
            "query_semantic_context": ["scope_mode", "ontology_ids"],
            "semantic_sparql_query": ["scope_mode", "query", "ontology_ids"],
            "describe_semantic_graph_set": [],
            "list_semantic_derived_pointers": [],
            "inspect_semantic_projection_status": [],
            "list_evidence_references": [],
            "get_evidence_reference": ["reference_id"],
            "get_ontology_lineage": ["target_type", "target_id"],
            "inspect_semantic_statement_provenance": ["statement_iri"],
            "get_semantic_reasoning_run": ["reasoning_run_id"],
            "get_semantic_validation_run": ["validation_run_id"],
            "list_semantic_reasoning_runs": [],
            "list_semantic_validation_runs": [],
        }.get(tool, []))
        schema: dict[str, Any] = {
            "type": "object",
            "properties": json.loads(json.dumps(properties)),
            "required": required,
            "additionalProperties": False,
        }
        if tool == "query_semantic_context":
            schema["anyOf"] = [{"required": ["query"]}, {"required": ["queries"]}]
        schemas[tool] = schema
    return schemas


# A v3 Platform Examiner reads a packet-authorized Ontology list, so the
# per-Ontology scope fields stop being caller-required: the proxy resolves them
# from the selected authorized entries.  ``project_id`` and ``ticket_digest``
# stay caller-visible because one read is still exactly one project and one
# frozen batch (design §3.G4.1).
_V3_PER_ONTOLOGY_SCOPE_FIELDS = ("ontology_id", "graph_set_id", "model_state_digest")


def v3_examiner_proxy_schemas(
    tools: Iterable[str] = PLATFORM_PROXY_READ_TOOLS,
) -> dict[str, dict[str, Any]]:
    """Return detached exact schemas for a v3 multi-Ontology read scope."""

    schemas = examiner_proxy_schemas(tools)
    for schema in schemas.values():
        schema["required"] = [
            key for key in schema["required"] if key not in _V3_PER_ONTOLOGY_SCOPE_FIELDS
        ]
        # Bound state digests come from the platform rather than from child
        # digest transcription, so the schema keeps only the string shape; the
        # proxy itself rejects a value that contradicts the selected entry.
        schema["properties"]["model_state_digest"] = {"type": "string", "minLength": 1}
    return schemas


def _schema_type_matches(value: Any, expected: str | Sequence[str]) -> bool:
    if isinstance(expected, (list, tuple)):
        return any(_schema_type_matches(value, item) for item in expected)
    if expected == "null":
        return value is None
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, Mapping)
    return False


def validate_examiner_proxy_arguments(tool: str, arguments: Mapping[str, Any], schema: Mapping[str, Any], *, scope: Mapping[str, str]) -> dict[str, Any]:
    """Validate one exact proxy call without invoking a forwarder/backend."""

    if not isinstance(arguments, Mapping) or not isinstance(schema, Mapping):
        raise ChildRuntimeError("Examiner proxy arguments/schema are invalid")
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or schema.get("additionalProperties") is not False:
        raise ChildRuntimeError("Examiner proxy schema must be closed")
    required = schema.get("required", ())
    if not isinstance(required, list) or set(arguments) - set(properties) or set(required) - set(arguments):
        raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any(
        isinstance(branch, Mapping) and isinstance(branch.get("required"), list)
        and set(branch["required"]).issubset(arguments)
        for branch in any_of
    ) is False:
        raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
    for key, rule in properties.items():
        if key not in arguments or not isinstance(rule, Mapping):
            continue
        value = arguments[key]
        if "const" in rule and value != rule["const"]:
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        if "enum" in rule and value not in rule["enum"]:
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        if not _schema_type_matches(value, rule.get("type", "")):
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        item_schema = rule.get("items")
        if isinstance(item_schema, Mapping) and isinstance(value, list):
            for item in value:
                if not _schema_type_matches(item, item_schema.get("type", "")):
                    raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        if isinstance(value, (int, float)) and "minimum" in rule and value < rule["minimum"]:
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        if isinstance(value, (int, float)) and "maximum" in rule and value > rule["maximum"]:
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        pattern = rule.get("pattern")
        if isinstance(pattern, str) and (not isinstance(value, str) or re.fullmatch(pattern, value) is None):
            raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
    for key, value in scope.items():
        if key in required and arguments.get(key) != value:
            raise ChildRuntimeError(f"exact scope rejected for {tool}")
    if tool == "query_semantic_context" and (
        ("query" in arguments and "queries" in arguments)
        or ("query" not in arguments and "queries" not in arguments)
    ):
        raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
    if tool == "query_semantic_context":
        # The consumer needs modeled facts, not ontology scaffolding: default the
        # resource filter to instance/relation/fact/rule so concept noise and
        # unrelated class matches stay out of the context.  A caller-supplied
        # filter must remain within that consumer set.
        allowed_types = {"instance", "relation", "fact", "rule"}
        caller_types = arguments.get("resource_types")
        if caller_types is not None:
            if not isinstance(caller_types, list) or not caller_types or any(
                not isinstance(item, str) or item not in allowed_types for item in caller_types
            ):
                raise ChildRuntimeError(f"exact argument schema rejected for {tool}")
        else:
            arguments = {**arguments, "resource_types": sorted(allowed_types)}
        # Mechanical small-retrieval defaults.  The prompt prefers small pages,
        # but a missing optional field must not silently fall back to the broad
        # backend defaults (limit 20 / context_limit 100).  The consumer can
        # still opt in to related context explicitly with ``context_limit=3``.
        arguments = {**arguments}
        arguments.setdefault("depth", 1)
        arguments.setdefault("limit", 10)
        if _looks_like_absolute_iri(arguments.get("query")):
            # Exact-anchor navigation needs the direct neighborhood; a zero
            # context page would return only the node label/types.
            arguments.setdefault("context_limit", 3)
        else:
            arguments.setdefault("context_limit", 0)
    return dict(arguments)


@dataclass(frozen=True)
class ProxyReceipt:
    # This is a child-visible virtual identity, never the host AF_UNIX path.  Host paths
    # are runtime-only and must not enter child-config or durable cleanup evidence.
    socket_identity: str
    token_digest: str
    project_id: str
    ontology_id: str
    graph_set_id: str
    ticket_digest: str
    allowed_tools: tuple[str, ...]
    config_digest: str


@dataclass(frozen=True)
class ProxyCallReceipt:
    """Sanitized receipt for one successful scoped read.

    The receipt intentionally contains no key, token, raw response, socket path, or
    host filesystem location.  ``artifact_path`` is a Runner-relative retained
    evidence name and is safe for the child to echo in its typed report reference.
    """

    ordinal: int
    project_id: str
    ontology_id: str
    graph_set_id: str
    ticket_digest: str
    model_state_digest: str
    tool: str
    request_digest: str
    response_digest: str
    artifact_path: str
    # Deterministic pagination tuple for this one call, derived by the proxy
    # from the exact cursor arguments and the platform's truncated/next-cursor
    # markers (R2.3-009 start21: asking the child to transcribe it by hand was
    # the rejection cause).  Empty for receipts recorded before this field.
    page: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class V3ProxyCallReceipt(ProxyCallReceipt):
    """v3-only receipt extension: the multi-Ontology scope actually selected.

    The legacy receipt keeps its exact historical field set -- the Runner's
    platform receipt validator checks that exact set and must keep accepting
    old single-Ontology receipts.  This subclass is instantiated only by the
    v3 branch of ``ScopedReadProxy.handle``, so the extra field never reaches a
    legacy consumer.
    """

    # v3 multi-Ontology scope actually selected for this call (project, Ontology,
    # graph set and both bound state digests per entry).  The legacy
    # single-Ontology proxy receipt fields already carry that scope.
    ontologies: tuple[Mapping[str, str], ...] = ()


def _proxy_page_for_call(
    previous_page: Mapping[str, Any] | None,
    arguments: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive the report locator page tuple for one forwarded read.

    The proxy is the only party that saw the exact request cursors and the
    platform's own ``truncated``/``next_*_cursor`` markers, so the receipt
    records the page chain deterministically instead of asking the Examiner
    child to transcribe it.
    """

    input_cursor = arguments.get("match_cursor") or arguments.get("context_cursor") or None
    has_more = False
    output_cursor: str | None = None
    for page_key, next_key in (
        ("matches_page", "next_match_cursor"),
        ("context_page", "next_context_cursor"),
    ):
        marker = result.get(page_key) if isinstance(result, Mapping) else None
        if isinstance(marker, Mapping) and bool(marker.get("truncated")):
            has_more = True
            if output_cursor is None:
                nxt = marker.get(next_key)
                if isinstance(nxt, str) and nxt:
                    output_cursor = nxt
    if not has_more and bool(result.get("truncated")):
        has_more = True
        nxt = result.get("next_cursor")
        if isinstance(nxt, str) and nxt:
            output_cursor = nxt
    if (
        isinstance(previous_page, Mapping)
        and previous_page.get("has_more") is True
        and input_cursor is not None
        and input_cursor == previous_page.get("output_cursor")
    ):
        ordinal = int(previous_page["ordinal"]) + 1
    else:
        ordinal = 0
    return {
        "ordinal": ordinal,
        "input_cursor": input_cursor,
        "output_cursor": output_cursor if has_more else None,
        "has_more": has_more,
        "sequence_complete": not has_more,
    }


class ScopedReadProxy:
    """A Runner-owned, ticket-bound AF_UNIX read proxy.

    ``read_key`` is intentionally retained only in this object.  It is never written to
    the child home, environment, config, receipt, or proxy response.  The optional
    ``forward`` callback is the only place an integration may attach a real platform
    read; leaving it unset gives deterministic tests a safe offline proxy.
    """

    def __init__(
        self,
        *,
        socket_path: Path,
        token: str,
        read_key: str,
        project_id: str | None = None,
        ontology_id: str | None = None,
        graph_set_id: str | None = None,
        ticket_digest: str,
        model_state_digest: str | None = None,
        allowed_tools: list[str] | tuple[str, ...],
        forward: Callable[[str, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        acceptance_round_id: str | None = None,
        child_handle_digest: str | None = None,
        exact_schemas: Mapping[str, Mapping[str, Any]] | None = None,
        authorized_ontologies: Sequence[Mapping[str, Any]] | None = None,
    ) -> None:
        self.socket_path = socket_path
        self.token = token
        self._read_key: str | None = read_key
        self.authorized_ontologies: tuple[dict[str, str], ...] = ()
        if authorized_ontologies is not None:
            # v3 multi-Ontology branch (design §3.G4.1): the packet-authorized
            # Ontology list replaces the single frozen scope.  Per-entry state
            # digests are platform bindings rather than child transcriptions, so
            # they are non-empty strings instead of 64-hex, and the ticket keeps
            # the frozen ``sha256:<hex>`` digest normalization.
            entries: list[dict[str, str]] = []
            for item in authorized_ontologies:
                if not isinstance(item, Mapping):
                    raise ChildRuntimeError("v3 proxy Ontology scope entry is invalid")
                entry = {
                    "project_id": _safe_id(item.get("project_id"), "project_id"),
                    "ontology_id": _safe_id(item.get("ontology_id"), "ontology_id"),
                    "graph_set_id": _safe_id(item.get("graph_set_id"), "graph_set_id"),
                    "model_state_digest": str(item.get("model_state_digest") or ""),
                    "graph_state_digest": str(item.get("graph_state_digest") or ""),
                }
                if not entry["model_state_digest"] or not entry["graph_state_digest"]:
                    raise ChildRuntimeError("v3 proxy Ontology scope entry is incomplete")
                entries.append(entry)
            if not entries or len({entry["ontology_id"] for entry in entries}) != len(entries):
                raise ChildRuntimeError("v3 proxy Ontology scope is invalid")
            self.authorized_ontologies = tuple(entries)
            primary = self.authorized_ontologies[0]
            self.project_id = primary["project_id"]
            self.ontology_id = primary["ontology_id"]
            self.graph_set_id = primary["graph_set_id"]
            self.model_state_digest = primary["model_state_digest"]
            self.ticket_digest = v3_ticket_digest(ticket_digest)
        else:
            self.project_id = _safe_id(project_id, "project_id")
            self.ontology_id = _safe_id(ontology_id, "ontology_id")
            self.graph_set_id = _safe_id(graph_set_id, "graph_set_id")
            self.ticket_digest = _safe_digest(ticket_digest, "ticket_digest")
            self.model_state_digest = _safe_digest(model_state_digest, "model_state_digest")
        normalized = tuple(str(tool) for tool in allowed_tools)
        if (
            not normalized
            or len(set(normalized)) != len(normalized)
            or any(tool not in PLATFORM_PROXY_READ_TOOLS for tool in normalized)
        ):
            raise ChildRuntimeError("platform proxy allowlist is not read-only")
        self.allowed_tools = normalized
        self.exact_schemas = (
            {str(tool): json.loads(json.dumps(schema)) for tool, schema in exact_schemas.items()}
            if exact_schemas is not None
            else None
        )
        if self.exact_schemas is not None and set(self.exact_schemas) != set(self.allowed_tools):
            raise ChildRuntimeError("Examiner proxy exact schema inventory is incomplete")
        self._forward = forward
        self.acceptance_round_id = (
            _safe_id(acceptance_round_id, "acceptance_round_id")
            if acceptance_round_id is not None
            else "offline-round"
        )
        self.child_handle_digest = (
            _safe_digest(child_handle_digest, "child_handle_digest")
            if child_handle_digest is not None
            else "0" * 64
        )
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self.requests: list[dict[str, Any]] = []
        self._call_receipts: list[ProxyCallReceipt] = []
        self.post_revoke_denials = 0
        self.backend_calls = 0
        self.schema_rejections = 0

    @property
    def active(self) -> bool:
        with self._lock:
            return self._read_key is not None

    @property
    def token_digest(self) -> str:
        return hashlib.sha256(self.token.encode("utf-8")).hexdigest()

    @property
    def receipt(self) -> ProxyReceipt:
        config = {
            "server": "platform_read_proxy",
            "scope": {
                "project_id": self.project_id,
                "ontology_id": self.ontology_id,
                "graph_set_id": self.graph_set_id,
            },
            "ticket_digest": self.ticket_digest,
            "model_state_digest": self.model_state_digest,
            "allowed_tools": list(self.allowed_tools),
        }
        return ProxyReceipt(
            socket_identity="/agent/home/platform-proxy.sock",
            token_digest=self.token_digest,
            project_id=self.project_id,
            ontology_id=self.ontology_id,
            graph_set_id=self.graph_set_id,
            ticket_digest=self.ticket_digest,
            allowed_tools=self.allowed_tools,
            config_digest=_digest(config),
        )

    @property
    def receipt_snapshot(self) -> tuple[ProxyCallReceipt, ...]:
        """Return immutable sanitized receipts for successful calls only."""

        with self._lock:
            return tuple(self._call_receipts)

    def start(self) -> ProxyReceipt:
        with self._lock:
            if self._server is not None:
                return self.receipt
            self.socket_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if self.socket_path.exists() or self.socket_path.is_symlink():
                raise ChildRuntimeError("platform proxy socket already exists")
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
            self._thread = threading.Thread(target=self._serve, name="acceptance-read-proxy", daemon=True)
            self._thread.start()
            return self.receipt

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        server.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(2.0)
                try:
                    raw = b""
                    while b"\n" not in raw and len(raw) < 128 * 1024:
                        block = conn.recv(8192)
                        if not block:
                            break
                        raw += block
                    request = json.loads(raw.split(b"\n", 1)[0].decode("utf-8")) if raw else {}
                    response = self.handle(request)
                except Exception as exc:
                    response = {"ok": False, "error": "proxy-request-invalid", "code": type(exc).__name__}
                try:
                    conn.sendall(_canonical(response) + b"\n")
                except OSError:
                    pass

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise ChildRuntimeError("proxy request is invalid")
        with self._lock:
            if self._read_key is None:
                self.post_revoke_denials += 1
                return {"ok": False, "error": "read-key-revoked", "code": "read-key-revoked"}
            if request.get("token") != self.token:
                return {"ok": False, "error": "proxy-token-invalid", "code": "proxy-token-invalid"}
            operation = request.get("operation")
            if operation == "tools/list":
                # Legacy consumers read the bare name list; the v3 read bridge
                # forwards the exact per-tool schemas so the child sees the
                # argument shape the proxy actually enforces instead of a
                # generic object.
                schemas = [
                    {
                        "name": tool,
                        "description": "ticket-bound read-only platform query",
                        "inputSchema": self.exact_schemas[tool],
                    }
                    for tool in self.allowed_tools
                    if isinstance(self.exact_schemas, dict)
                    and isinstance(self.exact_schemas.get(tool), dict)
                ]
                return {
                    "ok": True,
                    "tools": list(self.allowed_tools),
                    "schemas": schemas or None,
                }
            if operation != "tools/call":
                return {"ok": False, "error": "proxy-operation-denied", "code": "proxy-operation-denied"}
            tool = request.get("tool")
            arguments = request.get("arguments")
            if not isinstance(tool, str) or tool not in self.allowed_tools:
                return {"ok": False, "error": "read-tool-denied", "code": "read-tool-denied"}
            if not isinstance(arguments, Mapping):
                self.schema_rejections += 1
                return {"ok": False, "error": "read-arguments-invalid", "code": "read-arguments-invalid", "backend_calls": 0}
            if self.authorized_ontologies:
                # v3 multi-Ontology branch: scope resolution, injection and the
                # exact-schema check all happen in one place; the legacy frozen
                # single-Ontology block below is not applied at all.
                try:
                    arguments, selected = self._v3_scope_arguments(tool, arguments)
                except _ProxyScopeDenied as denied:
                    if denied.code == "read-arguments-schema":
                        self.schema_rejections += 1
                    return {
                        "ok": False,
                        "error": denied.code,
                        "code": denied.code,
                        "backend_calls": 0,
                    }
                request_digest = _digest({"tool": tool, "arguments": dict(arguments)})
                self.requests.append(
                    {
                        "tool": tool,
                        "request_digest": request_digest,
                        "ontology_ids": [
                            entry["ontology_id"]
                            for entry in selected
                        ],
                    }
                )
                if self._forward is None:
                    return {
                        "ok": False,
                        "error": "platform-forwarding-unconfigured",
                        "code": "platform-forwarding-unconfigured",
                    }
                try:
                    self.backend_calls += 1
                    result = dict(self._forward(tool, arguments, self._read_key))
                except Exception:
                    return {
                        "ok": False,
                        "error": "platform-forward-failed",
                        "code": "platform-forward-failed",
                        "backend_calls": self.backend_calls,
                    }
                response_digest = _digest(result)
                artifact_path = (
                    f"acceptance/{self.acceptance_round_id}/platform-read/"
                    f"{self.child_handle_digest}/{len(self._call_receipts)}.json"
                )
                previous_page = self._call_receipts[-1].page if self._call_receipts else None
                page = _proxy_page_for_call(previous_page, arguments, result)
                self._call_receipts.append(
                    V3ProxyCallReceipt(
                        ordinal=len(self._call_receipts),
                        project_id=str(arguments["project_id"]),
                        ontology_id=str(arguments.get("ontology_id", "")),
                        graph_set_id=str(arguments.get("graph_set_id", "")),
                        ticket_digest=self.ticket_digest,
                        model_state_digest=str(arguments.get("model_state_digest", "")),
                        tool=tool,
                        request_digest=request_digest,
                        response_digest=response_digest,
                        artifact_path=artifact_path,
                        page=page,
                        ontologies=tuple(dict(entry) for entry in selected),
                    )
                )
                return {
                    "ok": True,
                    "result": result,
                    "request_digest": request_digest,
                    "response_digest": response_digest,
                    "artifact_path": artifact_path,
                    "call_ordinal": len(self._call_receipts) - 1,
                    "call_total": len(self._call_receipts),
                }
            required = {
                "project_id": self.project_id,
                "ontology_id": self.ontology_id,
                "graph_set_id": self.graph_set_id,
                "ticket_digest": self.ticket_digest,
                "model_state_digest": self.model_state_digest,
            }
            # R2.3-009 examiner diagnosis (2026-08-21): live evidence showed the
            # Examiner child's projected input carries no ticket_digest or
            # model_state_digest and its instructions never name the five frozen
            # bindings, so demanding the model repeat them denied every real
            # platform read (start8/9 left zero forwarded reads).  Scope binding
            # is protocol mechanics the tool layer owns: inject the frozen scope
            # here and reject only a call that explicitly contradicts it.
            if any(
                key in arguments and arguments[key] != value
                for key, value in required.items()
            ):
                return {"ok": False, "error": "read-scope-denied", "code": "read-scope-denied", "backend_calls": 0}
            arguments = {**required, **arguments}
            if (
                self.exact_schemas is not None
                and tool in {"query_semantic_context", "semantic_sparql_query"}
                and arguments.get("ontology_ids") not in (None, [self.ontology_id])
            ):
                return {
                    "ok": False,
                    "error": "read-scope-denied",
                    "code": "read-scope-denied",
                    "backend_calls": 0,
                }
            if (
                self.exact_schemas is not None
                and tool in {"query_semantic_context", "semantic_sparql_query"}
                and arguments.get("ontology_ids") is None
            ):
                arguments = {**arguments, "ontology_ids": [self.ontology_id]}
            # ``scope_mode`` is equally mechanical: the proxy is ontology-bound,
            # so the only legal value is the one frozen here.  A caller-supplied
            # value still flows through the exact-schema const check.
            if (
                tool in {"query_semantic_context", "semantic_sparql_query"}
                and arguments.get("scope_mode") is None
            ):
                arguments = {**arguments, "scope_mode": "ontologies"}
            if self.exact_schemas is not None:
                try:
                    arguments = validate_examiner_proxy_arguments(
                        tool, arguments, self.exact_schemas[tool], scope=required
                    )
                except ChildRuntimeError:
                    self.schema_rejections += 1
                    return {
                        "ok": False,
                        "error": "read-arguments-schema",
                        "code": "read-arguments-schema",
                        "backend_calls": 0,
                    }
            request_digest = _digest({"tool": tool, "arguments": dict(arguments)})
            self.requests.append({"tool": tool, "request_digest": request_digest})
            if self._forward is None:
                return {"ok": False, "error": "platform-forwarding-unconfigured", "code": "platform-forwarding-unconfigured"}
            try:
                self.backend_calls += 1
                result = dict(self._forward(tool, arguments, self._read_key))
            except Exception:
                return {"ok": False, "error": "platform-forward-failed", "code": "platform-forward-failed", "backend_calls": self.backend_calls}
            response_digest = _digest(result)
            artifact_path = (
                f"acceptance/{self.acceptance_round_id}/platform-read/"
                f"{self.child_handle_digest}/{len(self._call_receipts)}.json"
            )
            previous_page = self._call_receipts[-1].page if self._call_receipts else None
            page = _proxy_page_for_call(previous_page, arguments, result)
            self._call_receipts.append(
                ProxyCallReceipt(
                    ordinal=len(self._call_receipts),
                    project_id=self.project_id,
                    ontology_id=self.ontology_id,
                    graph_set_id=self.graph_set_id,
                    ticket_digest=self.ticket_digest,
                    model_state_digest=self.model_state_digest,
                    tool=tool,
                    request_digest=request_digest,
                    response_digest=response_digest,
                    artifact_path=artifact_path,
                    page=page,
                )
            )
            call_total = len(self._call_receipts)
            return {
                "ok": True,
                "result": result,
                "request_digest": request_digest,
                "response_digest": response_digest,
                "artifact_path": artifact_path,
                "call_ordinal": len(self._call_receipts) - 1,
                "call_total": call_total,
            }

    def revoke(self) -> dict[str, Any]:
        with self._lock:
            self._read_key = None
            return {"status": "revoked", "post_revoke_denials": self.post_revoke_denials}

    def _v3_scope_arguments(
        self, tool: str, arguments: Mapping[str, Any]
    ) -> tuple[dict[str, Any], tuple[dict[str, str], ...]]:
        """Resolve one v3 call's authorized Ontology selection and inject its scope.

        The selection is ``ontology_ids`` (query tools), else ``ontology_id``,
        else the packet's first authorized Ontology.  Every selected Ontology
        must be authorized and one call stays inside one project (the canonical
        read tools take a single ``project_id`` plus an Ontology list).

        The per-call scope values are Host-owned: they are resolved from the
        selected authorized entry, not transcribed by the child.  A caller (or
        the bridge's advisory env scope, which projects the first authorized
        Ontology) can therefore never widen the selection — its value is
        replaced by the selected entry's binding, and for a multi-Ontology
        selection the per-Ontology hint fields are dropped instead of matched.
        Only the frozen batch ticket is a strict caller check, because a wrong
        ticket is a batch-identity error rather than a scope hint.
        """

        authorized = {entry["ontology_id"]: entry for entry in self.authorized_ontologies}
        requested = arguments.get("ontology_ids")
        if requested is None:
            single = arguments.get("ontology_id")
            requested = [single] if isinstance(single, str) and single else None
        if requested is None or requested == []:
            requested = [self.authorized_ontologies[0]["ontology_id"]]
        if not isinstance(requested, list) or any(
            not isinstance(item, str) or not item for item in requested
        ):
            raise _ProxyScopeDenied("read-arguments-invalid")
        if len(set(requested)) != len(requested) or any(item not in authorized for item in requested):
            raise _ProxyScopeDenied("read-scope-denied")
        selected = tuple(dict(authorized[item]) for item in requested)
        if len({entry["project_id"] for entry in selected}) != 1:
            # One read is one project: a cross-project selection is refused
            # instead of being silently narrowed to one project.
            raise _ProxyScopeDenied("read-scope-denied")
        schema = self.exact_schemas.get(tool) if self.exact_schemas is not None else None
        selectable = schema is not None and "ontology_ids" in schema.get("properties", {})
        if len(selected) > 1 and not selectable:
            raise _ProxyScopeDenied("read-scope-denied")
        primary = selected[0]
        injected: dict[str, Any] = {
            "project_id": primary["project_id"],
            "ticket_digest": self.ticket_digest,
        }
        hints: dict[str, Any] = dict(arguments)
        if len(selected) == 1:
            injected.update(
                {
                    "ontology_id": primary["ontology_id"],
                    "graph_set_id": primary["graph_set_id"],
                    "model_state_digest": primary["model_state_digest"],
                }
            )
        else:
            # Per-Ontology bindings cannot be a single value for a multi-Ontology
            # read.  A hint that projects one Ontology's values -- the legacy
            # bridge's primary-entry env, for instance -- is irrelevant here
            # rather than contradictory, so it is dropped: the forwarded read
            # stays bound by the strictly authorized ``ontology_ids`` selection
            # resolved above, and the receipt records each selected entry.
            for key in ("ontology_id", "graph_set_id", "model_state_digest"):
                hints.pop(key, None)
        if "ticket_digest" in arguments and arguments["ticket_digest"] != self.ticket_digest:
            raise _ProxyScopeDenied("read-scope-denied")
        # Host-owned scope always wins over a caller hint (see docstring).
        scoped = {**hints, **injected}
        if tool in {"query_semantic_context", "semantic_sparql_query"}:
            scoped["ontology_ids"] = list(requested)
            if scoped.get("scope_mode") is None:
                scoped["scope_mode"] = "ontologies"
        if schema is not None:
            try:
                scoped = validate_examiner_proxy_arguments(tool, scoped, schema, scope=injected)
            except ChildRuntimeError as exc:
                raise _ProxyScopeDenied("read-arguments-schema") from exc
        return scoped, selected

    def stop(self) -> None:
        self._stop.set()
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.close()
            finally:
                self.socket_path.unlink(missing_ok=True)
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)

    def destroy(self) -> None:
        self.revoke()
        self.stop()


@dataclass
class _ForwardRequest:
    tool: str
    arguments: Mapping[str, Any]
    result: Any = None
    error: BaseException | None = None
    complete: threading.Event = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.complete = threading.Event()


class McpReadForwarder:
    """Host-side synchronous facade over the canonical backend MCP server.

    The forwarder owns the only subprocess environment containing the temporary read
    key.  Its environment is allowlisted and its child-facing API is restricted to the
    ticket's read tools.  Calls are serialized through one MCP ``ClientSession`` so
    pagination cursors and result envelopes remain byte-for-byte typed values rather
    than being reimplemented by the Runner.
    """

    _SCOPED_ENVELOPE_FIELDS = frozenset(
        {"ticket_digest", "model_state_digest"}
    )

    def __init__(
        self,
        *,
        repository_root: Path,
        read_key: str,
        expected_tools: list[str] | tuple[str, ...],
        command: str | None = None,
        args: list[str] | None = None,
        process_env: Mapping[str, str] | None = None,
        client_factory: Callable[..., Any] | None = None,
        exact_schemas: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        if not isinstance(read_key, str) or not read_key:
            raise ChildRuntimeError("forwarder read key is unavailable")
        normalized = tuple(str(tool) for tool in expected_tools)
        if not normalized or len(set(normalized)) != len(normalized):
            raise ChildRuntimeError("forwarder tool inventory is invalid")
        if any(tool not in PLATFORM_PROXY_READ_TOOLS for tool in normalized):
            raise ChildRuntimeError("forwarder tool inventory is not read-only")
        self.repository_root = repository_root.resolve()
        self.read_key = read_key
        self.expected_tools = normalized
        self.command = command or str(self.repository_root / "backend" / ".venv" / "bin" / "python")
        self.args = list(args or ["-m", "app.mcp.server"])
        backend_root = self.repository_root / "backend"
        # Never inherit the caller's environment wholesale: especially do not leak a
        # broader API key, proxy, plugin, or Codex credential into the canonical server.
        allowlisted = {
            "ONTOLOGY_MCP_API_KEY": read_key,
            "PYTHONPATH": str(backend_root),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(backend_root),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        if process_env:
            for name in ("DATABASE_URL", "OXIGRAPH_URL", "EMBEDDING_BASE_URL", "EMBEDDING_MODEL"):
                value = process_env.get(name)
                if isinstance(value, str) and value:
                    allowlisted[name] = value
        self.process_env = allowlisted
        self.client_factory = client_factory
        self.exact_schemas = (
            {str(tool): json.loads(json.dumps(schema)) for tool, schema in exact_schemas.items()}
            if exact_schemas is not None
            else None
        )
        self.backend_calls = 0
        self.schema_rejections = 0
        self._queue: queue.Queue[_ForwardRequest | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._startup_error: BaseException | None = None
        self._tool_schemas: dict[str, Mapping[str, Any]] = {}
        self._inventory_digest: str | None = None

    @property
    def inventory_digest(self) -> str | None:
        return self._inventory_digest

    @property
    def active(self) -> bool:
        return self._thread is not None and not self._stopped.is_set()

    def start(self, *, timeout: float = 20.0) -> "McpReadForwarder":
        if self._thread is not None:
            if self._startup_error is not None:
                raise ChildRuntimeError("canonical MCP forwarder failed to start") from self._startup_error
            return self
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run, name="acceptance-mcp-forwarder", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=max(0.1, timeout)):
            self.stop()
            raise ChildRuntimeError("canonical MCP forwarder startup timed out")
        if self._startup_error is not None:
            error = self._startup_error
            self.stop()
            raise ChildRuntimeError("canonical MCP forwarder startup failed") from error
        return self

    def _run(self) -> None:
        try:
            asyncio.run(self._session_loop())
        except BaseException as exc:  # surfaced to start()/forward() without leaking text
            self._startup_error = exc
            self._ready.set()
            while True:
                request = self._queue.get()
                if request is None:
                    return
                request.error = ChildRuntimeError("canonical MCP forwarder is unavailable")
                request.complete.set()

    async def _session_loop(self) -> None:
        # Imports are deferred so deterministic offline tests do not need to start the
        # backend or initialize its dependency graph.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        parameters = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=dict(self.process_env),
            cwd=str(self.repository_root / "backend"),
        )
        factory = self.client_factory or stdio_client
        async with factory(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listed = await session.list_tools()
                tools = getattr(listed, "tools", ())
                inventory: dict[str, Mapping[str, Any]] = {}
                for tool in tools if isinstance(tools, (list, tuple)) else ():
                    name = getattr(tool, "name", None)
                    if isinstance(name, str):
                        schema = getattr(tool, "inputSchema", None)
                        inventory[name] = schema if isinstance(schema, Mapping) else {}
                # The canonical server may expose additional write tools.  We require
                # every frozen read wrapper to exist and expose only the exact ticket
                # inventory through this proxy; no extra tool can cross the boundary.
                missing = set(self.expected_tools) - set(inventory)
                if missing:
                    raise ChildRuntimeError("canonical MCP read tool inventory is incomplete")
                self._tool_schemas = {name: inventory[name] for name in self.expected_tools}
                self._inventory_digest = _digest(
                    {"canonical_tools": sorted(inventory), "ticket_tools": list(self.expected_tools)}
                )
                self._ready.set()
                while not self._stopped.is_set():
                    request = await asyncio.to_thread(self._queue.get)
                    if request is None:
                        return
                    try:
                        schema = self._tool_schemas.get(request.tool)
                        if schema is None:
                            raise ChildRuntimeError("forwarder tool is outside ticket inventory")
                        arguments = dict(request.arguments)
                        exact = self.exact_schemas.get(request.tool) if self.exact_schemas is not None else None
                        if exact is not None:
                            scope = {
                                key: arguments[key]
                                for key in ("project_id", "ontology_id", "graph_set_id", "ticket_digest", "model_state_digest")
                                if key in arguments
                            }
                            arguments = validate_examiner_proxy_arguments(
                                request.tool, arguments, exact, scope=scope
                            )
                        properties = schema.get("properties") if isinstance(schema, Mapping) else None
                        # The wrapper validates the complete ticket envelope first;
                        # this explicit projection then removes only wrapper control
                        # fields not accepted by the canonical backend tool.
                        if isinstance(properties, Mapping):
                            arguments = {
                                key: value for key, value in arguments.items() if key in properties
                            }
                        self.backend_calls += 1
                        result = await session.call_tool(request.tool, arguments)
                        request.result = self._decode_result(result)
                    except BaseException as exc:
                        if isinstance(exc, ChildRuntimeError) and "schema" in str(exc):
                            self.schema_rejections += 1
                        request.error = exc
                    finally:
                        request.complete.set()

    @staticmethod
    def _decode_result(result: Any) -> Mapping[str, Any]:
        if bool(getattr(result, "isError", False)):
            raise ChildRuntimeError("canonical MCP read tool returned an error")
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, Mapping):
            return dict(structured)
        content = getattr(result, "content", ())
        for item in content if isinstance(content, (list, tuple)) else ():
            text = getattr(item, "text", None)
            if not isinstance(text, str):
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, Mapping):
                return dict(value)
            return {"value": value}
        raise ChildRuntimeError("canonical MCP read tool returned no typed data")

    def forward(self, tool: str, arguments: Mapping[str, Any], read_key: str) -> Mapping[str, Any]:
        if read_key != self.read_key or not self.active:
            raise ChildRuntimeError("forwarder read key is unavailable")
        request = _ForwardRequest(tool=tool, arguments=dict(arguments))
        self._queue.put(request)
        if not request.complete.wait(timeout=30):
            raise ChildRuntimeError("canonical MCP read tool timed out")
        if request.error is not None:
            raise ChildRuntimeError("canonical MCP read tool failed") from request.error
        if not isinstance(request.result, Mapping):
            raise ChildRuntimeError("canonical MCP read result is not typed")
        return dict(request.result)

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._queue.put(None)
            self._thread.join(timeout=2)
        self._thread = None
        self.read_key = ""
        self.process_env.pop("ONTOLOGY_MCP_API_KEY", None)


class ReportSinkServer:
    """Write-only private child report endpoint; never Team Transport.

    The sink runs the full kind-specific binding validation at submit time so a
    rejected report returns a detailed, actionable reason to the child.  The child
    may correct and resubmit within a bounded attempt budget; once accepted, no
    further submissions are honored.
    """

    def __init__(
        self,
        socket_path: Path,
        token: str,
        submit: Callable[[Mapping[str, Any]], Any],
        kind: str | None = None,
        validator: Callable[[Mapping[str, Any]], None] | None = None,
        max_attempts: int = 3,
        batch_contract: V3BatchReportContract | None = None,
    ):
        self.socket_path = socket_path
        self.token = token
        self._submit = submit
        if kind is not None and kind not in {"source", "platform", "acceptance"}:
            raise ChildRuntimeError("report sink kind is invalid")
        self.kind = kind
        self.validator = validator
        if batch_contract is not None:
            # The v3 batch branch is selected by the packet schema, so it is only
            # legal for the two v3 session kinds and only for the matching role.
            if kind not in {"platform", "acceptance"}:
                raise ChildRuntimeError("v3 batch report sink kind is invalid")
            expected_role = CQ_ACCEPTANCE_PLATFORM_ROLE if kind == "platform" else (
                CQ_ACCEPTANCE_JUDGE_ROLE
            )
            if batch_contract.role != expected_role:
                raise ChildRuntimeError("v3 batch report contract does not match the sink kind")
        self.batch_contract = batch_contract
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise ChildRuntimeError("report sink attempt budget is invalid")
        self.max_attempts = max_attempts
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._submitted = False
        self._rejections: list[str] = []

    def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            raise ChildRuntimeError("report sink socket already exists")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            server.listen(2)
        except Exception:
            server.close()
            self.socket_path.unlink(missing_ok=True)
            raise
        server.settimeout(0.2)
        self._server = server
        self._thread = threading.Thread(target=self._serve, name="acceptance-report-sink", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        while not self._stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    data = conn.recv(128 * 1024)
                    request = json.loads(data.decode("utf-8")) if data else {}
                    if not isinstance(request, Mapping):
                        response = {"ok": False, "code": "report-invalid"}
                    elif request.get("token") != self.token:
                        response = {"ok": False, "code": "report-token-invalid"}
                    elif self._submitted:
                        response = {"ok": False, "code": "report-already-submitted"}
                    elif (
                        len(self._rejections) >= self.max_attempts
                        and self.batch_contract is None
                    ):
                        # Legacy single-report budget only: a rejected report ends
                        # the round there.  The v3 batch branch stays recoverable
                        # (AGENTS.md: format/parameter/incomplete artifacts must
                        # never become a code-local irrecoverable gate) — its
                        # correction feedback stays typed and the session
                        # deadline is the only bound on total attempts.
                        response = {
                            "ok": False,
                            "code": "report-attempts-exceeded",
                            "detail": (
                                "report rejected "
                                + str(self.max_attempts)
                                + " times; no further resubmission is allowed"
                            ),
                            "attempts_remaining": 0,
                        }
                    elif not isinstance(request.get("report"), Mapping):
                        response = {"ok": False, "code": "report-invalid"}
                    else:
                        report = request["report"]
                        try:
                            if self.batch_contract is not None:
                                # v3 branch: one per-question entry, validated and
                                # latched against the session's batch contract.  The
                                # entry is recorded only after the Host accepted it,
                                # so a failed submit still leaves the question open
                                # for a bounded resubmission.
                                report = _validate_report_sink_payload(
                                    report,
                                    kind=self.kind,
                                    batch_contract=self.batch_contract,
                                )
                            elif self.kind is not None:
                                report = _validate_report_sink_payload(report, kind=self.kind)
                            if self.validator is not None:
                                self.validator(report)
                        except (ChildRuntimeError, ExaminerRuntimeBlocked) as exc:
                            detail = str(exc)
                            self._rejections.append(detail)
                            attempts_remaining = max(0, self.max_attempts - len(self._rejections))
                            response = {
                                "ok": False,
                                "code": "report-binding-rejected",
                                "detail": detail,
                                "attempts_remaining": attempts_remaining,
                            }
                        except Exception as exc:
                            # Preserve the validator's own reason (exception
                            # type plus message) instead of a bare
                            # "report-rejected": start11 of R2.3-009 lost the
                            # real rejection cause for two examiner reports
                            # this way, leaving the failure undiagnosable.
                            detail = f"{type(exc).__name__}: {exc}".strip()
                            self._rejections.append(detail)
                            attempts_remaining = max(0, self.max_attempts - len(self._rejections))
                            response = {
                                "ok": False,
                                "code": "report-rejected",
                                "detail": detail,
                                "attempts_remaining": attempts_remaining,
                            }
                        else:
                            try:
                                self._submit(report)
                            except Exception as exc:
                                # The submit callback runs the full Host
                                # binding (handle lookup, envelope validation,
                                # receipt binding, persistence); any failure
                                # there used to escape to the outer handler
                                # and answer with a bare "report-rejected".
                                # start13 of R2.3-009 lost the real cause of
                                # three consecutive examiner reports that way
                                # (start11 lost two through the twin path
                                # fixed above), so surface it here with the
                                # same detail and attempts accounting.
                                detail = f"{type(exc).__name__}: {exc}".strip()
                                self._rejections.append(detail)
                                attempts_remaining = max(
                                    0, self.max_attempts - len(self._rejections)
                                )
                                response = {
                                    "ok": False,
                                    "code": "report-submit-rejected",
                                    "detail": detail,
                                    "attempts_remaining": attempts_remaining,
                                }
                            else:
                                if self.batch_contract is not None:
                                    self.batch_contract.record(report)
                                    complete = self.batch_contract.is_complete
                                    # A batch session stays open until its last
                                    # question is reported; only then is the sink
                                    # latched and the child told it is done.
                                    self._submitted = complete
                                    response = {
                                        "ok": True,
                                        "question_id": str(report["question_id"]),
                                        "reports_remaining": len(
                                            self.batch_contract.pending_question_ids
                                        ),
                                        "batch_complete": complete,
                                    }
                                else:
                                    self._submitted = True
                                    response = {"ok": True}
                    conn.sendall(_canonical(response))
                except Exception:
                    try:
                        conn.sendall(_canonical({"ok": False, "code": "report-rejected"}))
                    except OSError:
                        pass

    def stop(self) -> None:
        self._stop.set()
        server = self._server
        self._server = None
        if server is not None:
            server.close()
        self.socket_path.unlink(missing_ok=True)
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)


def child_config_digest(config: Mapping[str, Any]) -> str:
    """Compute a public config binding without retaining secrets."""
    return _digest(config)


def prepare_child_tree(
    *,
    private_root: Path,
    source_bytes: Mapping[str, bytes] | None = None,
    host_auth: Path | None = None,
    instructions: bytes = b"",
    skill_name: str,
    skill_bytes: bytes,
) -> dict[str, Path]:
    """Create the private child home/work/skills tree with strict modes."""
    _private_dir(private_root)
    home, work, skills = private_root / "home", private_root / "work", private_root / "skills"
    for path in (home, work, skills):
        _private_dir(path, create=True)
    if host_auth is not None:
        _copy_private(host_auth, home / "auth.json", 0o600)
    _write_private(home / "instructions.md", instructions, 0o400)
    skill_dir = skills / skill_name
    _private_dir(skill_dir, create=True)
    _write_private(skill_dir / "SKILL.md", skill_bytes, 0o444)
    if source_bytes:
        for relative, payload in source_bytes.items():
            target = home / "sources" / relative
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ChildRuntimeError("source path escapes child home")
            _write_private(target, payload, 0o400)
    return {"home": home, "work": work, "skills": skills}


__all__ = [
    "ChildRuntimeError",
    "ExaminerRuntimeBlocked",
    "ExaminerRolePacket",
    "ExaminerTransportReceipt",
    "ExaminerTransport",
    "ExaminerRunMetrics",
    "LeanExaminerRuntime",
    "aggregate_ordered_examiner_verdicts",
    "build_source_examiner_packet",
    "build_platform_examiner_packet",
    "build_acceptance_examiner_packet",
    "AcceptanceBatchPacket",
    "acceptance_branch_for",
    "build_platform_batch_packet",
    "build_acceptance_judge_packet",
    "CQ_ACCEPTANCE_BRANCH_V3",
    "CQ_ACCEPTANCE_BRANCH_LEGACY",
    "CQ_ACCEPTANCE_PLATFORM_ROLE",
    "CQ_ACCEPTANCE_JUDGE_ROLE",
    "V3BatchReportContract",
    "v3_proxy_scope_entries",
    "v3_ticket_digest",
    "v3_examiner_proxy_schemas",
    "examiner_proxy_schemas",
    "validate_examiner_proxy_arguments",
    "PLATFORM_PROXY_READ_TOOLS",
    "ProxyReceipt",
    "ScopedReadProxy",
    "McpReadForwarder",
    "ReportSinkServer",
    "child_config_digest",
    "prepare_child_tree",
]
