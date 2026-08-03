"""Independent real Protocol/receipt P2a driver (no Runner or semantic start).

This command owns one disposable ``PlatformScope`` and one Protocol Agent.  It
delivers a generated-IRI v2 candidate over the real Team Transport socket and
lets Protocol perform the production dry-run/apply, read, pagination, and
native-verifier path.  The command never imports ``TeamRunner`` or
``StartLedger`` and never writes the tester-owned P2a PASS file.

The compact local fixture in :mod:`modeling_team.p2a_fixture` remains useful
for deterministic unit coverage.  This driver is the executable seam an
independent tester runs against the real app server; its run-local evidence is
the only output it owns.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import (
    ProfileAgent,
    SAFE_PROTOCOL_TOOLS,
    TaskSource,
    TeamConfiguration,
    TeamProfile,
    TeamTask,
    digest_file,
    load_profile,
    repository_root,
)
from .matrix_artifact import MATRIX_RELATIVE, MatrixArtifactError, load_matrix
from .p2a_batch_plan import (
    ASSERTION_CLIENT_ITEM_IDS,
    P2ABatchPlanError,
    P2A_CANDIDATE_DELIVERY_ID,
    P2A_CANDIDATE_DIGEST,
    P2A_CANDIDATE_REVISION,
    P2A_SEMANTIC_DIGEST,
    RDF_TYPE,
    XSD_STRING,
    verify_p2a_dry_run_evidence_projection,
)
from .platform_scope import PlatformScope, PlatformScopeError
from .proof_v2 import ProofV2Error, validate_candidate_item_evidence_map
from .p2_protocol_driver import (
    PROTOCOL_ID,
    _DriverRun,
    _Evidence,
    _bootstrap_helpers,
    _cleanup_scope,
    _remove_runtime_artifacts,
    _runtime_delivery,
)
from .runtimes.codex import CodexRuntimeError
from .runtimes.base import RuntimeDelivery
from .runtimes.p2a_codex import (
    NATIVE_VERIFIER_MAX_CALLS,
    OVERLAY_CONTRACT_RELATIVE,
    P2ACodexRuntimeAdapter,
)
from .transport_mcp import Delivery, TeamTransportBroker


CONTRACT_RELATIVE_PATH = Path("modeling_team/references/p2a-protocol-driver-contract.json")
SYNTHETIC_MODELING_ID = "p2a-synthetic-modeling"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
P2A_SCHEMA = "p2a-protocol-driver/v1"
_CANDIDATE_MAP_RELATIVE = Path("evidence/candidate-item-evidence-map.json")
_NATIVE_VERIFIER_EVENTS_RELATIVE = Path("evidence/native-verifier-events.jsonl")
_NATIVE_VERIFIER_ATTEMPT_EVENTS_RELATIVE = Path(
    "evidence/native-verifier-attempt-events.jsonl"
)
_BATCH_INVENTORY_LIMIT = 100
_IDLE_FLUSH_GRACE_SECONDS = 1.0
_MAX_CONTINUATIONS = 1
_CORRECTABLE_FAILURE_LAYERS = frozenset({"argument_contract", "proof_validation"})
_CONTINUATION_TEXT = (
    "Continue the same P2a Protocol task in this same thread and run. Inspect the "
    "native-verifier tool error visible in the preceding turn. Correct only the proof input; "
    "if needed, perform additional read-only platform reads. Call the native verifier again. "
    "Do not repeat dry_run or apply_atomic, submit any platform write, change the candidate or "
    "modeling semantics, create a Project, Ontology, or scope, or report to Team Transport unless "
    "the native verifier returns complete=true. The total native-verifier call budget across the "
    "original turn and this continuation is three."
)
_PROOF_V2_ASSET = {
    "source_path": "modeling_team/proof_v2.py",
    "staged_path": "runtime-assets/protocol/proof_v2.py",
    "mount_path": "/opt/proof_v2.py",
    "mode": "0600",
    "parent_mode": "0700",
    "sha256": "b053f01cfd389f3541fa89702134db899770b5b5276c57f3048131176868c593",
}

_CONTRACT_FIELDS = {
    "schema_version",
    "command",
    "argv",
    "required_stages",
    "forbidden_evidence",
    "candidate_sender_id",
    "protocol_agent_id",
    "scope_mode",
    "protocol_tools",
    "runtime_contract",
    "max_runtime_seconds",
    "evidence_mode",
    "cleanup_policy",
}
_REQUIRED_STAGES = [
    "driver_started",
    "matrix_validated",
    "protocol_roster_started",
    "candidate_delivered",
    "candidate_receipt",
    "dry_run_observed",
    "apply_observed",
    "postapply_evidence_observed",
    "retrieval_observed",
    "native_verifier_completed",
    "protocol_report_accepted",
    "protocol_runtime_cleanup",
    "scope_cleanup_first_stage",
    "scope_deleted",
    "scope_cleanup_second_stage",
    "driver_stopped",
]
_FORBIDDEN_EVIDENCE = [
    "teamrunner",
    "start_ledger",
    "semantic_start",
    "terminal-result-handoff",
    "ack_terminal_handoff",
    "p2a-pass",
]
_RUNTIME_CONTRACT = {
    "adapter": "P2ACodexRuntimeAdapter.start_roster",
    "broker": "TeamTransportBroker",
    "stdio": True,
    "private_bwrap": True,
    "app_server": True,
    "native_mcp": [
        "team_transport",
        "ontology_platform",
        "protocol_mechanics",
        "p2a_protocol_overlay",
    ],
    "protocol_retrieval_mcp": {
        "server": "protocol_mechanics",
        "command": "/usr/bin/python3",
        "args": ["/opt/protocol-retrieval-mcp.py"],
        "runtime_run_id_env": "PROTOCOL_RUNTIME_RUN_ID",
        "runtime_context_path": "/opt/mechanics-contract.json",
        "tools": [
            "build_candidate_receipt",
            "verify_scoped_retrieval_fallback",
            "write_candidate_item_evidence_map",
        ],
    },
    "idle_flush_grace_seconds": _IDLE_FLUSH_GRACE_SECONDS,
    "bounded_correction": {
        "adapter_method": "send_message",
        "max_continuations": _MAX_CONTINUATIONS,
        "max_native_verifier_calls": NATIVE_VERIFIER_MAX_CALLS,
        "same_agent_thread_run": True,
        "lease_policy": "exact_identity_and_original_expiry_no_renew",
        "credential_expiry": "explicit_null_when_unsupported",
    },
    "proof_v2_asset": _PROOF_V2_ASSET,
    "p2a_overlay": {
        "contract_path": OVERLAY_CONTRACT_RELATIVE.as_posix(),
        "server": "p2a_protocol_overlay",
        "command": "/usr/bin/python3",
        "args": ["/opt/p2a_protocol_overlay_mcp.py"],
        "task_id": "p2a-protocol-production",
        "tools": [
            "build_p2a_batch_plan",
            "verify_p2a_dry_run_evidence_projection",
        ],
    },
}
_CLEANUP_POLICY = {
    "scope_mode": "create",
    "max_owned_ephemeral_scopes": 1,
    "delete_requires_first_stage": True,
    "admin_revoke_in_finally": True,
    "no_direct_db_delete": True,
    "no_new_deletion_key": True,
}


class P2AProtocolDriverError(RuntimeError):
    """A fail-closed real P2a driver error."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def load_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise P2AProtocolDriverError("P2a driver contract is unreadable") from exc
    if not isinstance(value, dict) or set(value) != _CONTRACT_FIELDS:
        raise P2AProtocolDriverError("P2a driver contract fields drifted")
    if value.get("schema_version") != P2A_SCHEMA:
        raise P2AProtocolDriverError("P2a driver contract schema drifted")
    if value.get("command") != "uv" or value.get("argv") != [
        "run",
        "--project",
        "backend",
        "python",
        "-m",
        "modeling_team.p2a_protocol_driver",
        "--contract",
        CONTRACT_RELATIVE_PATH.as_posix(),
    ]:
        raise P2AProtocolDriverError("P2a driver command drifted")
    if value.get("required_stages") != _REQUIRED_STAGES or value.get("forbidden_evidence") != _FORBIDDEN_EVIDENCE:
        raise P2AProtocolDriverError("P2a driver lifecycle/provenance drifted")
    if value.get("candidate_sender_id") != SYNTHETIC_MODELING_ID or value.get("protocol_agent_id") != PROTOCOL_ID:
        raise P2AProtocolDriverError("P2a driver roster drifted")
    if value.get("scope_mode") != "create" or value.get("runtime_contract") != _RUNTIME_CONTRACT:
        raise P2AProtocolDriverError("P2a driver scope/runtime contract drifted")
    tools = value.get("protocol_tools")
    if (
        not isinstance(tools, list)
        or not tools
        or len(set(tools)) != len(tools)
        or any(tool not in SAFE_PROTOCOL_TOOLS for tool in tools)
        or "submit_modeling_batch" not in tools
        or "query_semantic_context" not in tools
        or "run_semantic_reasoning" not in tools
    ):
        raise P2AProtocolDriverError("P2a Protocol tool contract is invalid")
    maximum = value.get("max_runtime_seconds")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 1800:
        raise P2AProtocolDriverError("P2a runtime bound is invalid")
    if value.get("evidence_mode") != "append_only_run_local" or value.get("cleanup_policy") != _CLEANUP_POLICY:
        raise P2AProtocolDriverError("P2a evidence/cleanup policy is invalid")
    return value


def _build_configuration(root: Path, contract: dict[str, Any]) -> TeamConfiguration:
    profile = load_profile(root / "modeling_team/profiles/base-three-agent.yaml", root=root)
    package = next((agent.package for agent in profile.agents if agent.package.role == "protocol"), None)
    if package is None:
        raise P2AProtocolDriverError("Protocol package is unavailable")
    protocol_agent = ProfileAgent(PROTOCOL_ID, package)
    single_profile = TeamProfile("p2a-protocol-production", profile.runtime, (protocol_agent,), frozenset(), {})
    source = root / "modeling_team/references/modeling-batch-item-contract.json"
    if not source.is_file() or source.is_symlink():
        raise P2AProtocolDriverError("Protocol mechanics reference is unavailable")
    role_source = TaskSource(source, source.relative_to(root), "protocol", frozenset({"protocol"}))
    task = TeamTask(
        "p2a-protocol-production",
        "",
        (source,),
        ("candidate receipt", "dry_run", "apply_atomic", "native v2 verifier", "Protocol terminal result"),
        schema_version=2,
        role_sources=(role_source,),
        protocol_tools=tuple(contract["protocol_tools"]),
        retain_nonempty=False,
        semantic_start_evidence=(),
    )
    return TeamConfiguration(single_profile, task)


def _stage_run(run: _DriverRun, root: Path, matrix: dict[str, Any], contract: dict[str, Any]) -> None:
    (run.root / "evidence").mkdir(parents=True, mode=0o700, exist_ok=True)
    source_root = run.root / "sources" / "protocol"
    source_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    source = root / "modeling_team/references/modeling-batch-item-contract.json"
    target = source_root / source.relative_to(root)
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    target.write_bytes(source.read_bytes())
    baseline = {
        "files": {
            "p2a_protocol_driver": digest_file(root / "modeling_team/p2a_protocol_driver.py"),
            "p2a_protocol_driver_contract": digest_file(root / CONTRACT_RELATIVE_PATH),
            "proof_matrix_artifact": digest_file(root / MATRIX_RELATIVE),
            "proof_v2": digest_file(root / _PROOF_V2_ASSET["source_path"]),
            "protocol_retrieval_mcp": digest_file(root / "modeling_team/protocol_retrieval_mcp.py"),
            "protocol_retrieval_verifier": digest_file(root / "modeling_team/protocol_mechanics.py"),
            "p2a_batch_plan": digest_file(root / "modeling_team/p2a_batch_plan.py"),
            "p2a_protocol_overlay_mcp": digest_file(
                root / "modeling_team/p2a_protocol_overlay_mcp.py"
            ),
            "p2a_overlay_contract": digest_file(root / OVERLAY_CONTRACT_RELATIVE),
            "p2a_codex_runtime": digest_file(root / "modeling_team/runtimes/p2a_codex.py"),
        },
        "matrix_digest": matrix["matrix_digest"],
        "source_candidate_digest": matrix["source_candidate_digest"],
    }
    if baseline["files"]["proof_v2"] != contract["runtime_contract"]["proof_v2_asset"]["sha256"]:
        raise P2AProtocolDriverError("P2a proof_v2 runtime asset drifts from contract")
    (run.root / "baseline-manifest.json").write_text(
        json.dumps(baseline, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _promote_candidate_item_evidence_map(
    run_root: Path,
    runtime_work: Path,
    candidate: dict[str, Any],
    run_id: str,
) -> tuple[dict[str, Any], str]:
    """Validate the Protocol-owned map and promote one immutable safe copy."""
    source = runtime_work / _CANDIDATE_MAP_RELATIVE
    try:
        work_root = runtime_work.resolve(strict=True)
        work_stat = os.lstat(runtime_work)
        if (
            stat.S_ISLNK(work_stat.st_mode)
            or not stat.S_ISDIR(work_stat.st_mode)
            or work_stat.st_uid != os.getuid()
        ):
            raise P2AProtocolDriverError("candidate evidence map work root is invalid")
        source_parent = source.parent.resolve(strict=True)
        source_parent.relative_to(work_root)
        source_stat = os.lstat(source)
        if (
            stat.S_ISLNK(source_stat.st_mode)
            or not stat.S_ISREG(source_stat.st_mode)
            or source_stat.st_uid != os.getuid()
        ):
            raise P2AProtocolDriverError("candidate evidence map source metadata is invalid")
        raw = source.read_bytes()
    except P2AProtocolDriverError:
        raise
    except (OSError, ValueError) as exc:
        raise P2AProtocolDriverError("candidate evidence map is unavailable") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
        validated = validate_candidate_item_evidence_map(
            candidate,
            value,
            expected_run_id=run_id,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ProofV2Error, TypeError, ValueError) as exc:
        raise P2AProtocolDriverError("candidate evidence map is invalid") from exc
    target = run_root / _CANDIDATE_MAP_RELATIVE
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    canonical = json.dumps(
        validated,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
    except FileExistsError as exc:
        raise P2AProtocolDriverError("candidate evidence map was promoted more than once") from exc
    except OSError as exc:
        raise P2AProtocolDriverError("candidate evidence map promotion failed") from exc
    try:
        offset = 0
        while offset < len(canonical):
            offset += os.write(descriptor, canonical[offset:])
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
    except OSError as exc:
        raise P2AProtocolDriverError("candidate evidence map promotion failed") from exc
    finally:
        os.close(descriptor)
    digest = hashlib.sha256(canonical).hexdigest()
    return validated, digest


def _authorized_get(scope: PlatformScope, path: str) -> Any:
    """Use the existing scope-owned admin request helper for readback only."""
    if not scope.admin_key or scope.request is None:
        raise P2AProtocolDriverError("authorized batch readback is unavailable")
    status, value = scope.request("GET", path, None, scope.admin_key)
    if status != 200:
        raise P2AProtocolDriverError(f"authorized batch readback failed ({status})")
    return value


def _batch_safe_snapshot(detail: dict[str, Any]) -> dict[str, Any]:
    attempts = detail.get("attempts")
    safe_attempts: list[dict[str, Any]] = []
    for attempt in attempts if isinstance(attempts, list) else []:
        if not isinstance(attempt, dict):
            continue
        plan = attempt.get("operation_plan")
        plan_evidence = plan.get("evidence") if isinstance(plan, dict) else None
        safe_attempts.append(
            {
                "attempt_id": attempt.get("attempt_id"),
                "mode": attempt.get("mode"),
                "attempt_status": attempt.get("attempt_status"),
                "operation_plan_evidence_sha256": _canonical_digest(plan_evidence)
                if isinstance(plan_evidence, list)
                else None,
                "operation_plan_evidence_count": len(plan_evidence)
                if isinstance(plan_evidence, list)
                else 0,
                "finding_codes": sorted(
                    str(finding.get("code"))
                    for finding in attempt.get("findings", [])
                    if isinstance(finding, dict) and isinstance(finding.get("code"), str)
                ),
            }
        )
    return {
        "batch_id": detail.get("batch_id"),
        "ontology_id": detail.get("ontology_id"),
        "build_session_id": detail.get("build_session_id"),
        "client_item_ids": sorted(
            str(item.get("client_item_id"))
            for item in detail.get("items", [])
            if isinstance(item, dict) and isinstance(item.get("client_item_id"), str)
        ),
        "attempts": safe_attempts,
    }


def _observe_authoritative_dry_run(
    scope: PlatformScope,
    candidate: dict[str, Any],
    evidence_map: dict[str, Any],
) -> dict[str, Any] | None:
    """Read inventory plus two candidate details and prove their exact stability."""
    if not scope.ontology_id:
        raise P2AProtocolDriverError("ontology is unavailable for dry-run readback")
    inventory_path = (
        f"/api/ontologies/{scope.ontology_id}/modeling-batches"
        f"?limit={_BATCH_INVENTORY_LIMIT}"
    )
    inventory = _authorized_get(scope, inventory_path)
    if not isinstance(inventory, dict) or not isinstance(inventory.get("batches"), list):
        raise P2AProtocolDriverError("batch inventory response is invalid")
    batches = inventory["batches"]
    if inventory.get("next_cursor") is not None:
        raise P2AProtocolDriverError("batch inventory is incomplete")
    if not batches:
        return None
    batch_ids = [
        item.get("batch_id")
        for item in batches
        if isinstance(item, dict) and isinstance(item.get("batch_id"), str)
    ]
    if len(batch_ids) != len(batches) or len(set(batch_ids)) != len(batch_ids):
        raise P2AProtocolDriverError("batch inventory IDs are invalid")
    details: list[dict[str, Any]] = []
    for batch_id in batch_ids:
        detail = _authorized_get(scope, f"/api/modeling-batches/{batch_id}")
        if not isinstance(detail, dict) or detail.get("batch_id") != batch_id:
            raise P2AProtocolDriverError("batch detail identity drifted")
        details.append(detail)
    detail_ids = [detail.get("batch_id") for detail in details]
    if set(detail_ids) != set(batch_ids) or len(detail_ids) != len(set(detail_ids)):
        raise P2AProtocolDriverError("batch inventory/details do not match")
    expected_item_ids = {
        row.get("client_item_id")
        for row in evidence_map.get("rows", [])
        if isinstance(row, dict) and isinstance(row.get("client_item_id"), str)
    }
    if not expected_item_ids:
        raise P2AProtocolDriverError("candidate evidence map has no client items")
    for detail in details:
        if detail.get("ontology_id") != scope.ontology_id:
            raise P2AProtocolDriverError("batch detail ontology drifted")
        item_ids = {
            item.get("client_item_id")
            for item in detail.get("items", [])
            if isinstance(item, dict) and isinstance(item.get("client_item_id"), str)
        }
        if item_ids != expected_item_ids:
            continue
        attempts = detail.get("attempts")
        if not isinstance(attempts, list):
            raise P2AProtocolDriverError("candidate batch attempts are invalid")
        for attempt in attempts:
            if not isinstance(attempt, dict) or attempt.get("mode") != "dry_run":
                continue
            if attempt.get("attempt_status") != "validated":
                continue
            findings = attempt.get("findings")
            if isinstance(findings, list) and any(
                isinstance(finding, dict) and finding.get("code") == "missing_evidence"
                for finding in findings
            ):
                raise P2AProtocolDriverError("candidate dry-run reports missing evidence")
            plan = attempt.get("operation_plan")
            plan_rows = plan.get("evidence") if isinstance(plan, dict) else None
            if not isinstance(plan_rows, list):
                raise P2AProtocolDriverError("candidate dry-run Evidence plan is unavailable")
            second_detail = _authorized_get(
                scope,
                f"/api/modeling-batches/{detail['batch_id']}",
            )
            if (
                not isinstance(second_detail, dict)
                or second_detail.get("batch_id") != detail.get("batch_id")
            ):
                raise P2AProtocolDriverError("second candidate batch detail identity drifted")
            try:
                verified = verify_p2a_dry_run_evidence_projection(
                    candidate,
                    evidence_map,
                    detail,
                    detail,
                    second_detail,
                    expected_run_id=evidence_map["run_id"],
                )
            except (P2ABatchPlanError, ProofV2Error, TypeError, ValueError) as exc:
                raise P2AProtocolDriverError("candidate dry-run Evidence plan mismatches map") from exc
            return {
                "inventory_sha256": _canonical_digest(inventory),
                "inventory_batch_ids": sorted(batch_ids),
                "detail_snapshots": [_batch_safe_snapshot(detail) for detail in details],
                "candidate_batch_id": detail.get("batch_id"),
                "dry_run_attempt_id": attempt.get("attempt_id"),
                "plan_rows": verified["plan_rows"],
                "plan_sha256": verified["plan_sha256"],
                "dedupe_by_inline_identity": verified["dedupe_by_inline_identity"],
                "second_detail_sha256": _canonical_digest(second_detail),
            }
    return None


def _read_native_verifier_events(run_root: Path) -> list[dict[str, Any]]:
    path = run_root / _NATIVE_VERIFIER_EVENTS_RELATIVE
    if not path.is_file() or path.is_symlink():
        return []
    completion_fields = {
        "role",
        "tool",
        "status",
        "complete",
        "proof_arguments_sha256",
        "result_envelope_sha256",
        "category",
        "recorded_at_ns",
    }
    failure_fields = {
        "error_code",
        "failure_layer",
        "error_message_sha256",
        "top_level_exact",
        "types_valid",
        "mode_create",
    }
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise P2AProtocolDriverError("native verifier events are unreadable") from exc
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise P2AProtocolDriverError("native verifier event is malformed") from exc
        if not isinstance(event, dict) or frozenset(event) not in {
            frozenset(completion_fields),
            frozenset(failure_fields),
        }:
            raise P2AProtocolDriverError("native verifier event fields drifted")
        if set(event) == completion_fields:
            if (
                event.get("role") != "protocol"
                or event.get("tool") != "verify_scoped_retrieval_fallback"
                or event.get("status") not in {"accepted", "rejected"}
                or not isinstance(event.get("complete"), bool)
                or not isinstance(event.get("proof_arguments_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", event["proof_arguments_sha256"])
                or not isinstance(event.get("result_envelope_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", event["result_envelope_sha256"])
                or not isinstance(event.get("category"), str)
                or isinstance(event.get("recorded_at_ns"), bool)
                or not isinstance(event.get("recorded_at_ns"), int)
            ):
                raise P2AProtocolDriverError("native verifier event is invalid")
        elif (
            isinstance(event.get("error_code"), bool)
            or not isinstance(event.get("error_code"), int)
            or event.get("failure_layer")
            not in {"argument_contract", "proof_validation", "transport"}
            or not isinstance(event.get("error_message_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", event["error_message_sha256"])
            or any(
                not isinstance(event.get(field), bool)
                for field in ("top_level_exact", "types_valid", "mode_create")
            )
        ):
            raise P2AProtocolDriverError("native verifier event is invalid")
        events.append(event)
    return events


def _read_native_verifier_attempt_events(run_root: Path) -> list[dict[str, Any]]:
    path = run_root / _NATIVE_VERIFIER_ATTEMPT_EVENTS_RELATIVE
    if not path.is_file() or path.is_symlink():
        return []
    expected_fields = {"event", "native_call_count", "action", "created_at_ns"}
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise P2AProtocolDriverError("native verifier attempt events are unreadable") from exc
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise P2AProtocolDriverError("native verifier attempt event is malformed") from exc
        if not isinstance(event, dict) or set(event) != expected_fields:
            raise P2AProtocolDriverError("native verifier attempt event fields drifted")
        if (
            event.get("event") != "native_verifier_approval"
            or event.get("action") not in {"accept", "decline"}
            or isinstance(event.get("native_call_count"), bool)
            or not isinstance(event.get("native_call_count"), int)
            or not 0 <= event["native_call_count"] <= NATIVE_VERIFIER_MAX_CALLS
            or isinstance(event.get("created_at_ns"), bool)
            or not isinstance(event.get("created_at_ns"), int)
            or event["created_at_ns"] <= 0
        ):
            raise P2AProtocolDriverError("native verifier attempt event is invalid")
        events.append(event)
    accepted_counts = [event["native_call_count"] for event in events if event["action"] == "accept"]
    if accepted_counts != list(range(1, len(accepted_counts) + 1)):
        raise P2AProtocolDriverError("native verifier attempt count drifted")
    if any(
        event["action"] == "decline"
        and event["native_call_count"] != NATIVE_VERIFIER_MAX_CALLS
        for event in events
    ):
        raise P2AProtocolDriverError("native verifier decline count drifted")
    return events


def _future_expiry(value: Any, *, now: datetime | None = None) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        return False
    return parsed.astimezone(timezone.utc) > (now or datetime.now(timezone.utc))


def _read_continuation_baseline(
    scope: PlatformScope,
    run: _DriverRun,
    agent: Any,
    batch_snapshot: dict[str, Any],
    applied_snapshot: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    project_id = scope.project_id
    ontology_id = scope.ontology_id
    credential_id = scope.protocol_key_id
    if (
        not isinstance(project_id, str)
        or not project_id
        or not isinstance(ontology_id, str)
        or not ontology_id
        or not isinstance(credential_id, str)
        or not credential_id
        or not isinstance(scope.protocol_key, str)
        or not scope.protocol_key
        or run.protocol_key != scope.protocol_key
        or not isinstance(agent.thread_id, str)
        or not agent.thread_id
    ):
        raise P2AProtocolDriverError("continuation identity baseline is unavailable")
    batch_id = batch_snapshot.get("candidate_batch_id")
    dry_run_attempt_id = batch_snapshot.get("dry_run_attempt_id")
    apply_attempt_id = applied_snapshot.get("apply_attempt_id")
    if not all(
        isinstance(value, str) and value
        for value in (batch_id, dry_run_attempt_id, apply_attempt_id)
    ):
        raise P2AProtocolDriverError("continuation batch baseline is unavailable")
    batch_detail = _authorized_get(scope, f"/api/modeling-batches/{batch_id}")
    if (
        not isinstance(batch_detail, dict)
        or batch_detail.get("batch_id") != batch_id
        or batch_detail.get("ontology_id") != ontology_id
        or _canonical_digest(batch_detail) != applied_snapshot.get("detail_sha256")
    ):
        raise P2AProtocolDriverError("continuation batch baseline drifted")
    build_session_id = batch_detail.get("build_session_id")
    attempts = batch_detail.get("attempts")
    if not isinstance(build_session_id, str) or not build_session_id or not isinstance(attempts, list):
        raise P2AProtocolDriverError("continuation Build Session baseline is unavailable")
    attempt_identity = [
        (attempt.get("attempt_id"), attempt.get("mode"), attempt.get("attempt_status"))
        for attempt in attempts
        if isinstance(attempt, dict)
    ]
    if attempt_identity != [
        (dry_run_attempt_id, "dry_run", "validated"),
        (apply_attempt_id, "apply_atomic", "applied"),
    ]:
        raise P2AProtocolDriverError("continuation attempt baseline drifted")
    session_detail = _authorized_get(scope, f"/api/build-sessions/{build_session_id}")
    session = session_detail.get("session") if isinstance(session_detail, dict) else None
    leases = session_detail.get("leases") if isinstance(session_detail, dict) else None
    if (
        not isinstance(session, dict)
        or session.get("id") != build_session_id
        or session.get("project_id") != project_id
        or session.get("status") != "active"
        or not isinstance(session.get("revision"), int)
        or isinstance(session.get("revision"), bool)
        or not isinstance(leases, list)
    ):
        raise P2AProtocolDriverError("continuation Build Session baseline is invalid")
    matching_leases = [
        lease
        for lease in leases
        if isinstance(lease, dict)
        and lease.get("ontology_id") == ontology_id
        and lease.get("build_session_id") == build_session_id
    ]
    if len(matching_leases) != 1:
        raise P2AProtocolDriverError("continuation Lease identity is ambiguous")
    lease = matching_leases[0]
    if (
        lease.get("state") != "active"
        or lease.get("lease_revision") != 1
        or lease.get("renewed_at") is not None
        or not _future_expiry(lease.get("expires_at"), now=now)
    ):
        raise P2AProtocolDriverError("continuation Lease is not valid")
    credential = _authorized_get(scope, f"/api/api-keys/{credential_id}")
    if (
        not isinstance(credential, dict)
        or credential.get("id") != credential_id
        or credential.get("project_id") != project_id
        or credential.get("scopes") != ["model"]
        or not isinstance(credential.get("created_at"), str)
        or credential.get("revoked_at") is not None
        or credential.get("expires_at") is not None
    ):
        raise P2AProtocolDriverError("continuation credential is not valid")
    workspace = _authorized_get(scope, f"/api/ontologies/{ontology_id}/workspace-context")
    modeling = _authorized_get(scope, f"/api/ontologies/{ontology_id}/modeling-context")
    modeling_workspace = modeling.get("workspace") if isinstance(modeling, dict) else None
    if (
        not isinstance(workspace, dict)
        or workspace.get("state") != "ready"
        or not isinstance(workspace.get("workspace_version"), str)
        or not isinstance(modeling, dict)
        or modeling.get("project", {}).get("id") != project_id
        or modeling.get("ontology", {}).get("id") != ontology_id
        or not isinstance(modeling_workspace, dict)
        or modeling_workspace.get("state") != "ready"
        or modeling_workspace.get("workspace_version") != workspace["workspace_version"]
    ):
        raise P2AProtocolDriverError("continuation workspace baseline is invalid")
    return {
        "run_id": run.run_id,
        "agent_id": agent.agent_id,
        "thread_id": agent.thread_id,
        "project_id": project_id,
        "ontology_id": ontology_id,
        "build_session_id": build_session_id,
        "session_revision": session["revision"],
        "lease_identity": [build_session_id, ontology_id],
        "lease_revision": lease["lease_revision"],
        "lease_state": lease["state"],
        "lease_expires_at": lease["expires_at"],
        "lease_renewed_at": lease.get("renewed_at"),
        "credential_id": credential_id,
        "credential_project_id": credential["project_id"],
        "credential_scopes": credential["scopes"],
        "credential_created_at": credential["created_at"],
        "credential_revoked_at": credential["revoked_at"],
        "credential_expiry_present": "expires_at" in credential,
        "credential_expires_at": None,
        "credential_secret_sha256": hashlib.sha256(scope.protocol_key.encode("utf-8")).hexdigest(),
        "batch_id": batch_id,
        "dry_run_attempt_id": dry_run_attempt_id,
        "apply_attempt_id": apply_attempt_id,
        "batch_snapshot": _batch_safe_snapshot(batch_detail),
        "workspace_state": workspace["state"],
        "workspace_version": workspace["workspace_version"],
    }


def _continuation_eligible(
    *,
    receipt_seen: bool,
    map_seen: bool,
    dry_run_seen: bool,
    apply_seen: bool,
    postapply_seen: bool,
    retrieval_seen: bool,
    failure_layer: str | None,
    verifier_seen: bool,
    broker_seen: bool,
    agent_state: str,
    active_turn_id: str | None,
    continuation_count: int,
    native_call_count: int,
) -> bool:
    return (
        receipt_seen
        and map_seen
        and dry_run_seen
        and apply_seen
        and postapply_seen
        and retrieval_seen
        and failure_layer in _CORRECTABLE_FAILURE_LAYERS
        and not verifier_seen
        and not broker_seen
        and agent_state == "idle"
        and active_turn_id is None
        and continuation_count == 0
        and 0 < native_call_count < NATIVE_VERIFIER_MAX_CALLS
    )


def _continuation_delivery(run_id: str) -> RuntimeDelivery:
    return RuntimeDelivery(
        sender_id="p2a-host",
        recipient_id=PROTOCOL_ID,
        kind="p2a-native-correction",
        text=_CONTINUATION_TEXT,
        delivery_id=f"{run_id}-native-continuation-1",
        expects_reply=False,
        reply_to_delivery_id=None,
    )


def _continuation_evidence_payload(
    *,
    continuation_index: int,
    native_call_count: int,
    failure_layer: str | None,
    baseline_match: bool,
    created_at_ns: int | None = None,
) -> dict[str, Any]:
    timestamp = time.time_ns() if created_at_ns is None else created_at_ns
    if (
        isinstance(continuation_index, bool)
        or continuation_index not in {0, 1}
        or isinstance(native_call_count, bool)
        or not isinstance(native_call_count, int)
        or not 0 <= native_call_count <= NATIVE_VERIFIER_MAX_CALLS
        or failure_layer not in {*_CORRECTABLE_FAILURE_LAYERS, "transport", None}
        or not isinstance(baseline_match, bool)
        or isinstance(timestamp, bool)
        or not isinstance(timestamp, int)
        or timestamp <= 0
    ):
        raise P2AProtocolDriverError("continuation evidence payload is invalid")
    return {
        "continuation_index": continuation_index,
        "native_call_count": native_call_count,
        "failure_layer": failure_layer,
        "baseline_match": baseline_match,
        "created_at_ns": timestamp,
    }


def _observe_postapply_same_evidence_ids(
    scope: PlatformScope,
    dry_run_snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Require applied item results to retain the dry-run dedupe IDs exactly."""
    batch_id = dry_run_snapshot.get("candidate_batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise P2AProtocolDriverError("dry-run candidate batch identity is unavailable")
    expected: dict[str, set[str]] = {}
    for row in dry_run_snapshot.get("plan_rows", []):
        if not isinstance(row, dict):
            raise P2AProtocolDriverError("dry-run plan row is invalid")
        client_item_id = row.get("client_item_id")
        reference_id = row.get("dedupe_identity")
        if not isinstance(client_item_id, str) or not isinstance(reference_id, str):
            raise P2AProtocolDriverError("dry-run Evidence identity is invalid")
        expected.setdefault(client_item_id, set()).add(reference_id)
    if set(expected) != set(ASSERTION_CLIENT_ITEM_IDS.values()):
        raise P2AProtocolDriverError("dry-run Evidence item set drifts")
    detail = _authorized_get(scope, f"/api/modeling-batches/{batch_id}")
    if not isinstance(detail, dict) or detail.get("batch_id") != batch_id:
        raise P2AProtocolDriverError("post-apply batch detail identity drifts")
    attempts = detail.get("attempts")
    if not isinstance(attempts, list):
        raise P2AProtocolDriverError("post-apply batch attempts are invalid")
    applied = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict)
        and attempt.get("mode") == "apply_atomic"
        and attempt.get("attempt_status") == "applied"
    ]
    if not applied:
        return None
    if len(applied) != 1:
        raise P2AProtocolDriverError("post-apply attempt identity is ambiguous")
    results = applied[0].get("items")
    if not isinstance(results, list):
        raise P2AProtocolDriverError("post-apply item results are invalid")
    actual: dict[str, set[str]] = {}
    for result in results:
        if not isinstance(result, dict):
            raise P2AProtocolDriverError("post-apply item result is invalid")
        client_item_id = result.get("client_item_id")
        references = result.get("evidence_reference_ids")
        if (
            not isinstance(client_item_id, str)
            or not isinstance(references, list)
            or any(not isinstance(value, str) or not value for value in references)
        ):
            raise P2AProtocolDriverError("post-apply Evidence result is invalid")
        if client_item_id in actual:
            raise P2AProtocolDriverError("post-apply client item result is duplicated")
        actual[client_item_id] = set(references)
    if actual != expected:
        raise P2AProtocolDriverError(
            "post-apply EvidenceReference IDs drift from dry-run dedupe identities"
        )
    return {
        "batch_id": batch_id,
        "apply_attempt_id": applied[0].get("attempt_id"),
        "bindings": [
            {
                "client_item_id": client_item_id,
                "evidence_reference_ids": sorted(reference_ids),
            }
            for client_item_id, reference_ids in sorted(actual.items())
        ],
        "detail_sha256": _canonical_digest(detail),
    }


def _idle_stage_error(
    *,
    agent_state: str,
    terminal_present: bool,
    idle_since: float,
    now: float,
    stages: dict[str, bool],
    turn_started: bool = True,
    retrieval_seen: bool | None = None,
) -> str | None:
    """Return a bounded stage failure after a started turn goes idle.

    ``retrieval_seen`` remains an ignored compatibility argument for older
    unit callers; retrieval is now one ordinary stage rather than a precondition
    for checking the whole sequence.
    """
    if not turn_started or agent_state != "idle" or terminal_present:
        return None
    if now - idle_since < _IDLE_FLUSH_GRACE_SECONDS:
        return None
    missing = [name for name, present in stages.items() if not present]
    if not missing:
        return None
    return "P2a Protocol turn completed idle before stages: " + ", ".join(missing)


def _generated_candidate(matrix: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    for assertion_id in ASSERTION_CLIENT_ITEM_IDS:
        row = next(
            (item for item in matrix["rows"] if item["assertion_id"] == assertion_id),
            None,
        )
        if row is None:
            raise P2AProtocolDriverError(
                f"matrix lacks frozen P2a assertion {assertion_id}"
            )
        selected.append(row)
    terms = {
        "r23002-a008": {
            "subject": "p2a:generated-subject",
            "predicate": "urn:p2a:publicationStatus",
            "object": "published",
            "object_kind": "literal",
            "object_datatype": XSD_STRING,
            "object_language": None,
        },
        "r23002-a009": {
            "subject": "p2a:generated-subject",
            "predicate": "urn:p2a:hasOutput",
            "object": "urn:p2a:output",
            "object_kind": "resource",
            "object_datatype": None,
            "object_language": None,
        },
        "r23002-a004": {
            "subject": "urn:p2a:workflow",
            "predicate": "urn:p2a:hasVersion",
            "object": "p2a:generated-subject",
            "object_kind": "resource",
            "object_datatype": None,
            "object_language": None,
        },
        "r23002-a001": {
            "subject": "p2a:generated-subject",
            "predicate": RDF_TYPE,
            "object": "urn:p2a:FixtureResource",
            "object_kind": "resource",
            "object_datatype": None,
            "object_language": None,
        },
    }
    items = []
    for row in selected:
        assertion_id = row["assertion_id"]
        items.append(
            {
                "assertion_id": assertion_id,
                "graph_role": "asserted_data",
                **terms[assertion_id],
                "evidence_citations": row["approved_citations"],
            }
        )
    items.sort(key=_canonical_bytes)
    semantic = _canonical_digest({"schema_version": "candidate-required-assertions/v2", "statements": items})
    binding = {
        "schema_version": "candidate-required-assertions/v2",
        "candidate_revision": P2A_CANDIDATE_REVISION,
        "delivery_id": P2A_CANDIDATE_DELIVERY_ID,
        "reply_chain": [P2A_CANDIDATE_DELIVERY_ID],
        "semantic_digest": semantic,
    }
    candidate = {
        **binding,
        "candidate_digest": _canonical_digest(binding),
        "items": items,
    }
    if (
        candidate["semantic_digest"] != P2A_SEMANTIC_DIGEST
        or candidate["candidate_digest"] != P2A_CANDIDATE_DIGEST
    ):
        raise P2AProtocolDriverError("frozen P2a candidate semantic content drifts")
    return candidate, selected


def _task_text(run: _DriverRun, candidate: dict[str, Any], matrix: dict[str, Any]) -> str:
    context = run.protocol_context or {}
    return (
        "Independent P2a Protocol-only production fixture for exact task "
        "p2a-protocol-production. It owns no TeamRunner or semantic-start budget. The Host has supplied "
        "the scope context below, but you personally own every ontology-platform MCP call and must never "
        "ask the P2a overlay to obtain context or perform platform operations. Execute this order exactly. "
        "(1) Call protocol_mechanics/build_candidate_receipt with only the delivered immutable candidate; "
        "send its exact four-field accepted receipt once through Team Transport, bound to the candidate "
        "delivery. (2) Call protocol_mechanics/write_candidate_item_evidence_map once with the candidate and "
        "the exact bindings r23002-a008=p2a-01-literal-a008, "
        "r23002-a009=p2a-02-resource-a009, r23002-a004=p2a-03-relation-a004, and "
        "r23002-a001=p2a-04-vocabulary-a001. (3) Call "
        "p2a_protocol_overlay/build_p2a_batch_plan once with that candidate, retained map, and exact receipt; "
        "use its exact four-item output without adding, deleting, reordering, or editing fields. "
        "(4) Personally run the ordered Build Session lifecycle with configured ontology-platform tools: "
        "create with initial checkpoint omitted/null, save initial checkpoint, acquire lease, and submit "
        "one dry_run. Retain the formal submit receipt R0, then perform two authorized get_modeling_batch "
        "detail reads R1 and R2. Call p2a_protocol_overlay/verify_p2a_dry_run_evidence_projection with "
        "candidate/map/R0/R1/R2; proceed only when the exact item set, 4-to-3 projection, global "
        "inline-identity/dedupe bijection, and canonical R0=R1=R2 stability pass. (5) Submit apply_atomic "
        "with the exact same four items, then read the applied detail and call the same overlay verifier "
        "with postapply_evidence_bindings so every EvidenceReference ID back-references the same dry-run "
        "dedupe ID for its client item. (6) Personally read formal batch/workspace/Evidence/lineage data, "
        "run validation and reasoning, and consume every independent match/context page. The live "
        "publicationStatus write is the plain literal published. The candidate's full XSD string IRI is "
        "proof normalization only and is never a typed-write claim. (7) Call "
        "protocol_mechanics/verify_scoped_retrieval_fallback with exactly the v2 15-field proof envelope, "
        "actual generated IRIs, evidence_bindings, statement_lineage, and pagination. If its visible tool "
        "error is argument-contract or proof-validation only, inspect that error and correct only the proof "
        "input, optionally making additional read-only platform reads; across all turns you may call this "
        "native verifier at most three times. Never repeat dry_run or apply_atomic, write again, change "
        "semantics, or create another scope. Report terminal once only after complete=true. No PASS artifact "
        "is yours to write. Matrix digest=%s. Scope context=%s. "
        "Candidate=%s"
        % (
            matrix["matrix_digest"],
            json.dumps(context, ensure_ascii=False, sort_keys=True),
            json.dumps(candidate, ensure_ascii=False, sort_keys=True),
        )
    )


def _validate_candidate_receipt(reply: Delivery, candidate: dict[str, Any], delivery_id: str) -> None:
    if (
        reply.sender_id != PROTOCOL_ID
        or reply.recipient_id != SYNTHETIC_MODELING_ID
        or reply.reply_to_delivery_id != delivery_id
        or not isinstance(reply.delivery_id, str)
        or not reply.delivery_id
        or not isinstance(reply.text, str)
        or not reply.text
        or len(reply.text) > 4096
    ):
        raise P2AProtocolDriverError("P2a candidate receipt envelope is invalid")
    try:
        value = json.loads(reply.text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise P2AProtocolDriverError("P2a candidate receipt is not JSON") from exc
    if not isinstance(value, dict) or set(value) != {"status", "candidate_revision", "semantic_digest", "candidate_digest"}:
        raise P2AProtocolDriverError("P2a candidate receipt fields are invalid")
    if (
        value.get("status") != "accepted"
        or value.get("candidate_revision") != candidate["candidate_revision"]
        or value.get("semantic_digest") != candidate["semantic_digest"]
        or value.get("candidate_digest") != candidate["candidate_digest"]
    ):
        raise P2AProtocolDriverError("P2a candidate receipt binding drifted")


def run_driver(
    *,
    contract_path: Path,
    root: Path | None = None,
    run_id: str,
    base_url: str = "http://127.0.0.1:8001",
    evidence_path: Path | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    repository = (root or repository_root()).resolve()
    if not RUN_ID_RE.fullmatch(run_id):
        raise P2AProtocolDriverError("unsafe P2a run ID")
    maximum = float(contract["max_runtime_seconds"])
    if timeout is not None:
        maximum = min(maximum, max(1.0, float(timeout)))
    run_root = repository / "workspaces" / "p2a-protocol-runs" / run_id
    if run_root.exists():
        raise P2AProtocolDriverError("P2a run directory already exists")
    try:
        matrix = load_matrix(repository)
    except MatrixArtifactError as exc:
        raise P2AProtocolDriverError("P2a proof matrix is invalid") from exc
    candidate, selected_rows = _generated_candidate(matrix)
    run = _DriverRun(run_id, run_root, _build_configuration(repository, contract), {"mode": "create"})
    if evidence_path is not None:
        try:
            evidence_path.resolve().relative_to(run_root.resolve())
        except ValueError as exc:
            raise P2AProtocolDriverError("P2a evidence must remain run-local") from exc
    evidence = _Evidence(evidence_path or run_root / "evidence" / "p2a-protocol-driver.jsonl", _FORBIDDEN_EVIDENCE)
    scope: PlatformScope | None = None
    broker: TeamTransportBroker | None = None
    adapter: P2ACodexRuntimeAdapter | None = None
    started = time.monotonic()
    receipt_seen = False
    retrieval_seen = False
    verifier_seen = False
    write_seen = False
    dry_run_seen = False
    postapply_seen = False
    evidence_map: dict[str, Any] | None = None
    evidence_map_digest: str | None = None
    batch_snapshot: dict[str, Any] | None = None
    applied_snapshot: dict[str, Any] | None = None
    native_event_count = 0
    native_attempt_event_count = 0
    native_call_count = 0
    latest_failure_layer: str | None = None
    continuation_count = 0
    continuation_baseline: dict[str, Any] | None = None
    last_continuation_policy_check = 0.0
    last_batch_observation = 0.0
    last_postapply_observation = 0.0
    idle_since: float | None = None
    protocol_turn_started = False
    terminal_result: dict[str, Any] | None = None
    guard_calls: list[dict[str, Any]] = []
    try:
        run_root.mkdir(parents=True, mode=0o700)
        _stage_run(run, repository, matrix, contract)
        evidence.append("driver_started", run_id=run_id, scope_mode="create")
        evidence.append(
            "matrix_validated",
            matrix_path=MATRIX_RELATIVE.as_posix(),
            matrix_digest=matrix["matrix_digest"],
            row_count=len(matrix["rows"]),
            representative_assertion_ids=[row["assertion_id"] for row in selected_rows],
        )
        create_admin, revoke_admin = _bootstrap_helpers(repository)
        scope = PlatformScope(base_url, run_id, create_admin, revoke_admin)
        scope.prepare({"mode": "create"})
        scope.retain_nonempty = False
        run.protocol_key = scope.protocol_key
        run.protocol_context = scope.read_protocol_context()
        if not run.protocol_key or not run.protocol_context:
            raise P2AProtocolDriverError("P2a Protocol scope credentials/context unavailable")
        adapter = P2ACodexRuntimeAdapter(repository_root=repository)

        def terminal_guard(agent_id: str, already_synchronized: bool = False) -> bool:
            if adapter is None:
                return True
            blocked = adapter.terminal_report_blocked(agent_id, already_synchronized)
            guard_calls.append({"agent_id": agent_id, "blocked": blocked is True})
            return blocked

        broker = TeamTransportBroker(
            run_root / "transport" / "broker",
            {(SYNTHETIC_MODELING_ID, PROTOCOL_ID), (PROTOCOL_ID, SYNTHETIC_MODELING_ID)},
            terminal_report_guard=terminal_guard,
        )
        broker.start([PROTOCOL_ID])
        run.transport_root = broker.root
        (run_root / "transport-root").write_text(str(broker.root), encoding="utf-8")
        identities = adapter.start_roster(run, list(run.configuration.profile.agents))
        if [item.agent_id for item in identities] != [PROTOCOL_ID]:
            raise P2AProtocolDriverError("P2a Protocol roster drifted")
        evidence.append("protocol_roster_started", agent_id=PROTOCOL_ID)
        adapter.start_task(
            PROTOCOL_ID,
            _task_text(run, candidate, matrix),
            [str(path) for path in run.configuration.profile.agents[0].package.required_skills],
            [PROTOCOL_ID],
        )
        protocol_turn_started = True
        delivery = broker.send(
            SYNTHETIC_MODELING_ID,
            PROTOCOL_ID,
            json.dumps(
                {"candidate": candidate, "matrix_digest": matrix["matrix_digest"]},
                ensure_ascii=False,
                sort_keys=True,
            ),
            expects_reply=True,
        )
        claimed = broker.drain_for(delivery_id=delivery.delivery_id)
        if claimed != [delivery]:
            raise P2AProtocolDriverError("P2a candidate queue ownership drifted")
        adapter.send_message(PROTOCOL_ID, _runtime_delivery(delivery))
        broker.ack_delivery(delivery.delivery_id)
        evidence.append("candidate_delivered", delivery_id=delivery.delivery_id, candidate_digest=candidate["candidate_digest"])
        deadline = time.monotonic() + maximum
        while time.monotonic() < deadline:
            adapter.receive_messages()
            for reply in broker.drain_for(sender_id=PROTOCOL_ID, recipient_id=SYNTHETIC_MODELING_ID):
                if receipt_seen:
                    raise P2AProtocolDriverError("duplicate P2a candidate receipt")
                _validate_candidate_receipt(reply, candidate, delivery.delivery_id)
                receipt_seen = True
                broker.ack_delivery(reply.delivery_id)
                evidence.append("candidate_receipt", delivery_id=reply.delivery_id, reply_to_delivery_id=reply.reply_to_delivery_id)
            agent = adapter.agents.get(PROTOCOL_ID)
            if agent is not None:
                map_source = agent.work / _CANDIDATE_MAP_RELATIVE
                if evidence_map is None and map_source.is_file():
                    evidence_map, evidence_map_digest = _promote_candidate_item_evidence_map(
                        run_root,
                        agent.work,
                        candidate,
                        run_id,
                    )
                    evidence.append(
                        "candidate_item_evidence_map_promoted",
                        path=_CANDIDATE_MAP_RELATIVE.as_posix(),
                        sha256=evidence_map_digest,
                        map_digest=evidence_map["map_digest"],
                        row_count=len(evidence_map["rows"]),
                    )
                now = time.monotonic()
                if evidence_map is not None and not dry_run_seen and now - last_batch_observation >= 0.5:
                    last_batch_observation = now
                    batch_snapshot = _observe_authoritative_dry_run(
                        scope,
                        candidate,
                        evidence_map,
                    )
                    if batch_snapshot is not None:
                        dry_run_seen = True
                        evidence.append(
                            "batch_history_snapshot",
                            inventory_sha256=batch_snapshot["inventory_sha256"],
                            inventory_batch_ids=batch_snapshot["inventory_batch_ids"],
                            detail_snapshots=batch_snapshot["detail_snapshots"],
                        )
                        evidence.append(
                            "dry_run_observed",
                            batch_id=batch_snapshot["candidate_batch_id"],
                            attempt_id=batch_snapshot["dry_run_attempt_id"],
                            plan_sha256=batch_snapshot["plan_sha256"],
                            map_digest=evidence_map["map_digest"],
                        )
                if (
                    batch_snapshot is not None
                    and not postapply_seen
                    and now - last_postapply_observation >= 0.5
                ):
                    last_postapply_observation = now
                    applied_snapshot = _observe_postapply_same_evidence_ids(
                        scope,
                        batch_snapshot,
                    )
                    if applied_snapshot is not None:
                        write_seen = True
                        postapply_seen = True
                        evidence.append(
                            "apply_observed",
                            batch_id=applied_snapshot["batch_id"],
                            attempt_id=applied_snapshot["apply_attempt_id"],
                        )
                        evidence.append(
                            "postapply_evidence_observed",
                            batch_id=applied_snapshot["batch_id"],
                            bindings=applied_snapshot["bindings"],
                            detail_sha256=applied_snapshot["detail_sha256"],
                        )
                if not retrieval_seen and getattr(agent, "retrieval_episode", 0) >= 1:
                    retrieval_seen = True
                    evidence.append("retrieval_observed", episode=agent.retrieval_episode)
                events = _read_native_verifier_events(run_root)
                if len(events) < native_event_count:
                    raise P2AProtocolDriverError("native verifier event history regressed")
                for event in events[native_event_count:]:
                    if "failure_layer" in event:
                        latest_failure_layer = event["failure_layer"]
                        evidence.append("native_verifier_failed", **event)
                    elif event["status"] == "accepted" and event["complete"] is True:
                        verifier_seen = True
                        evidence.append(
                            "native_verifier_completed",
                            status=event["status"],
                            complete=event["complete"],
                            proof_arguments_sha256=event["proof_arguments_sha256"],
                            result_envelope_sha256=event["result_envelope_sha256"],
                            category=event["category"],
                        )
                native_event_count = len(events)
                attempt_events = _read_native_verifier_attempt_events(run_root)
                if len(attempt_events) < native_attempt_event_count:
                    raise P2AProtocolDriverError("native verifier attempt history regressed")
                for event in attempt_events[native_attempt_event_count:]:
                    if event["action"] == "accept":
                        native_call_count = event["native_call_count"]
                    else:
                        evidence.append(
                            "protocol_correction_terminal",
                            **_continuation_evidence_payload(
                                continuation_index=continuation_count,
                                native_call_count=event["native_call_count"],
                                failure_layer=latest_failure_layer,
                                baseline_match=continuation_baseline is not None,
                            ),
                        )
                        raise P2AProtocolDriverError("native verifier call budget exhausted")
                native_attempt_event_count = len(attempt_events)
                if (
                    latest_failure_layer is not None
                    and latest_failure_layer not in _CORRECTABLE_FAILURE_LAYERS
                    and not verifier_seen
                ):
                    raise P2AProtocolDriverError("native verifier failure is not correctable")
                if (
                    continuation_count == 1
                    and continuation_baseline is not None
                    and now - last_continuation_policy_check >= 0.5
                ):
                    last_continuation_policy_check = now
                    try:
                        current_baseline = _read_continuation_baseline(
                            scope,
                            run,
                            agent,
                            batch_snapshot,
                            applied_snapshot,
                        )
                    except P2AProtocolDriverError:
                        evidence.append(
                            "protocol_continuation_policy_violation",
                            **_continuation_evidence_payload(
                                continuation_index=continuation_count,
                                native_call_count=native_call_count,
                                failure_layer=latest_failure_layer,
                                baseline_match=False,
                            ),
                        )
                        raise
                    if current_baseline != continuation_baseline:
                        evidence.append(
                            "protocol_continuation_policy_violation",
                            **_continuation_evidence_payload(
                                continuation_index=continuation_count,
                                native_call_count=native_call_count,
                                failure_layer=latest_failure_layer,
                                baseline_match=False,
                            ),
                        )
                        raise P2AProtocolDriverError("continuation resource baseline drifted")
                if getattr(agent, "state", "") == "failed":
                    raise P2AProtocolDriverError("P2a Protocol app-server entered failed state")
                if (
                    getattr(agent, "state", "") == "idle"
                    and protocol_turn_started
                    and terminal_result is None
                    and not broker.results
                ):
                    if idle_since is None:
                        idle_since = now
                    else:
                        idle_elapsed = now - idle_since >= _IDLE_FLUSH_GRACE_SECONDS
                        eligible = _continuation_eligible(
                            receipt_seen=receipt_seen,
                            map_seen=evidence_map is not None,
                            dry_run_seen=dry_run_seen,
                            apply_seen=write_seen,
                            postapply_seen=postapply_seen,
                            retrieval_seen=retrieval_seen,
                            failure_layer=latest_failure_layer,
                            verifier_seen=verifier_seen,
                            broker_seen=bool(broker.results),
                            agent_state=agent.state,
                            active_turn_id=getattr(agent, "active_turn_id", None),
                            continuation_count=continuation_count,
                            native_call_count=native_call_count,
                        )
                        if idle_elapsed and eligible:
                            if batch_snapshot is None or applied_snapshot is None:
                                raise P2AProtocolDriverError(
                                    "continuation write baseline is unavailable"
                                )
                            frozen = _read_continuation_baseline(
                                scope,
                                run,
                                agent,
                                batch_snapshot,
                                applied_snapshot,
                            )
                            current = _read_continuation_baseline(
                                scope,
                                run,
                                agent,
                                batch_snapshot,
                                applied_snapshot,
                            )
                            if current != frozen:
                                evidence.append(
                                    "protocol_correction_terminal",
                                    **_continuation_evidence_payload(
                                        continuation_index=continuation_count,
                                        native_call_count=native_call_count,
                                        failure_layer=latest_failure_layer,
                                        baseline_match=False,
                                    ),
                                )
                                raise P2AProtocolDriverError(
                                    "continuation resource baseline drifted"
                                )
                            original_thread_id = agent.thread_id
                            adapter.send_message(PROTOCOL_ID, _continuation_delivery(run_id))
                            if agent.thread_id != original_thread_id:
                                raise P2AProtocolDriverError(
                                    "continuation Runtime thread identity drifted"
                                )
                            continuation_baseline = frozen
                            continuation_count = 1
                            last_continuation_policy_check = now
                            evidence.append(
                                "protocol_continuation_started",
                                **_continuation_evidence_payload(
                                    continuation_index=continuation_count,
                                    native_call_count=native_call_count,
                                    failure_layer=latest_failure_layer,
                                    baseline_match=True,
                                ),
                            )
                            idle_since = None
                            continue
                        if idle_elapsed and continuation_count == 1:
                            evidence.append(
                                "protocol_correction_terminal",
                                **_continuation_evidence_payload(
                                    continuation_index=continuation_count,
                                    native_call_count=native_call_count,
                                    failure_layer=latest_failure_layer,
                                    baseline_match=continuation_baseline is not None,
                                ),
                            )
                            raise P2AProtocolDriverError(
                                "P2a Protocol continuation completed idle without success"
                            )
                        if idle_elapsed and native_call_count >= NATIVE_VERIFIER_MAX_CALLS:
                            raise P2AProtocolDriverError("native verifier call budget exhausted")
                        idle_error = _idle_stage_error(
                            agent_state=agent.state,
                            terminal_present=bool(broker.results),
                            idle_since=idle_since,
                            now=now,
                            stages={
                                "candidate_receipt": receipt_seen,
                                "candidate_item_evidence_map_promoted": evidence_map is not None,
                                "dry_run_observed": dry_run_seen,
                                "apply_observed": write_seen,
                                "postapply_evidence_observed": postapply_seen,
                                "retrieval_observed": retrieval_seen,
                                "native_verifier_completed": verifier_seen,
                                "protocol_report_accepted": bool(broker.results),
                            },
                            turn_started=protocol_turn_started,
                        )
                        if idle_error is not None:
                            raise P2AProtocolDriverError(idle_error)
                else:
                    idle_since = None
            if broker.results:
                result = broker.results[next(iter(broker.results))]
                terminal_result = {"agent_id": result.agent_id, "status": result.status}
                break
            time.sleep(0.05)
        # A real runtime may publish the map or the last Batch receipt in the
        # same flush that transitions its turn to idle.  Perform one final
        # authoritative readback before declaring the stage missing.
        agent = adapter.agents.get(PROTOCOL_ID) if adapter is not None else None
        if agent is not None and evidence_map is None and (agent.work / _CANDIDATE_MAP_RELATIVE).is_file():
            evidence_map, evidence_map_digest = _promote_candidate_item_evidence_map(
                run_root,
                agent.work,
                candidate,
                run_id,
            )
            evidence.append(
                "candidate_item_evidence_map_promoted",
                path=_CANDIDATE_MAP_RELATIVE.as_posix(),
                sha256=evidence_map_digest,
                map_digest=evidence_map["map_digest"],
                row_count=len(evidence_map["rows"]),
            )
        if evidence_map is None:
            raise P2AProtocolDriverError("candidate evidence map was not promoted")
        if evidence_map is not None and not dry_run_seen:
            batch_snapshot = _observe_authoritative_dry_run(
                scope,
                candidate,
                evidence_map,
            )
            if batch_snapshot is not None:
                dry_run_seen = True
                evidence.append(
                    "batch_history_snapshot",
                    inventory_sha256=batch_snapshot["inventory_sha256"],
                    inventory_batch_ids=batch_snapshot["inventory_batch_ids"],
                    detail_snapshots=batch_snapshot["detail_snapshots"],
                )
                evidence.append(
                    "dry_run_observed",
                    batch_id=batch_snapshot["candidate_batch_id"],
                    attempt_id=batch_snapshot["dry_run_attempt_id"],
                    plan_sha256=batch_snapshot["plan_sha256"],
                    map_digest=evidence_map["map_digest"],
                )
        if batch_snapshot is not None and not postapply_seen:
            applied_snapshot = _observe_postapply_same_evidence_ids(scope, batch_snapshot)
            if applied_snapshot is not None:
                write_seen = True
                postapply_seen = True
                evidence.append(
                    "apply_observed",
                    batch_id=applied_snapshot["batch_id"],
                    attempt_id=applied_snapshot["apply_attempt_id"],
                )
                evidence.append(
                    "postapply_evidence_observed",
                    batch_id=applied_snapshot["batch_id"],
                    bindings=applied_snapshot["bindings"],
                    detail_sha256=applied_snapshot["detail_sha256"],
                )
        if adapter is not None:
            events = _read_native_verifier_events(run_root)
            for event in events[native_event_count:]:
                if "failure_layer" in event:
                    evidence.append("native_verifier_failed", **event)
                elif event["status"] == "accepted" and event["complete"] is True:
                    verifier_seen = True
                    evidence.append(
                        "native_verifier_completed",
                        status=event["status"],
                        complete=event["complete"],
                        proof_arguments_sha256=event["proof_arguments_sha256"],
                        result_envelope_sha256=event["result_envelope_sha256"],
                        category=event["category"],
                    )
        missing = [
            name
            for name, present in (
                ("candidate_receipt", receipt_seen),
                ("dry_run_observed", dry_run_seen),
                ("apply_observed", write_seen),
                ("postapply_evidence_observed", postapply_seen),
                ("retrieval_observed", retrieval_seen),
                ("native_verifier_completed", verifier_seen),
            )
            if not present
        ]
        if missing:
            raise P2AProtocolDriverError(
                "P2a Protocol sequence did not complete before timeout: " + ", ".join(missing)
            )
        if terminal_result is None or terminal_result["agent_id"] != PROTOCOL_ID:
            raise P2AProtocolDriverError("P2a Protocol terminal report was not accepted")
        evidence.append(
            "protocol_report_accepted",
            status=terminal_result["status"],
            terminal_guard_calls=guard_calls,
        )
    except P2AProtocolDriverError:
        raise
    except (CodexRuntimeError, PlatformScopeError, OSError, ValueError) as exc:
        raise P2AProtocolDriverError("P2a Protocol production path failed") from exc
    finally:
        cleanup_errors: list[str] = []
        if adapter is not None:
            try:
                adapter.stop()
            except Exception as exc:  # pragma: no cover - defensive closeout
                cleanup_errors.append(type(exc).__name__)
        if broker is not None:
            try:
                broker.stop()
            except Exception as exc:  # pragma: no cover - defensive closeout
                cleanup_errors.append(type(exc).__name__)
        if adapter is not None:
            try:
                _remove_runtime_artifacts(run_root)
            except OSError as exc:  # pragma: no cover - defensive closeout
                cleanup_errors.append(type(exc).__name__)
            try:
                evidence.append("protocol_runtime_cleanup", credentials_destroyed=True, cleanup_error=cleanup_errors[-1] if cleanup_errors else None)
            except P2AProtocolDriverError:
                cleanup_errors.append("evidence")
        if scope is not None:
            try:
                _cleanup_scope(scope, evidence)
            except (P2AProtocolDriverError, PlatformScopeError, OSError) as exc:
                cleanup_errors.append(type(exc).__name__)
        if run_root.exists():
            try:
                evidence.append("driver_stopped", elapsed_seconds=round(time.monotonic() - started, 3), cleanup_errors=cleanup_errors)
            except P2AProtocolDriverError:
                pass
        if cleanup_errors:
            raise P2AProtocolDriverError("P2a Protocol cleanup did not complete")
    if terminal_result is None:
        raise P2AProtocolDriverError("P2a Protocol driver finished without terminal result")
    return {
        "run_id": run_id,
        "matrix_path": MATRIX_RELATIVE.as_posix(),
        "matrix_digest": matrix["matrix_digest"],
        "source_candidate_digest": matrix["source_candidate_digest"],
        "candidate_digest": candidate["candidate_digest"],
        "representative_assertion_ids": [row["assertion_id"] for row in selected_rows],
        "terminal_result": terminal_result,
        "semantic_start_written": False,
        "pass_artifact_written": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run independent real P2a Protocol fixture")
    parser.add_argument("--contract", type=Path, default=CONTRACT_RELATIVE_PATH)
    parser.add_argument("--root", type=Path, default=repository_root())
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--timeout", type=float, default=None)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run_driver(
                contract_path=args.contract,
                root=args.root,
                run_id=args.run_id,
                base_url=args.base_url,
                timeout=args.timeout,
            ),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["CONTRACT_RELATIVE_PATH", "P2AProtocolDriverError", "load_contract", "run_driver"]
