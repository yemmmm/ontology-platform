"""Host-only HTTP channel for immutable checkpoint platform data."""

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4, uuid5

from .checkpoints import CheckpointError


def platform_data_request(
    base_url: str, admin_key: str, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url}/api/checkpoint-data/{action}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {admin_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("detail", {})
        except (ValueError, AttributeError):
            detail = {}
        code = detail.get("code") if isinstance(detail, dict) else None
        raise CheckpointError(
            code or "checkpoint_data_failed",
            f"platform checkpoint {action} returned HTTP {exc.code}",
            obj="platform_data",
            phase="checkpoint-" + action,
            retryable=action == "capture",
        ) from exc
    except (OSError, ValueError) as exc:
        raise CheckpointError(
            "checkpoint_data_unavailable" if action == "capture" else "fork_result_unknown",
            f"platform checkpoint {action} did not return a confirmed result",
            obj="platform_data",
            phase="checkpoint-" + action,
            retryable=action == "capture",
            retry="inspect platform state before retrying" if action == "fork" else "retry capture",
        ) from exc


def prepare_fork_plan(
    *,
    source_run_root: Path,
    checkpoint_id: str,
    new_run_id: str,
    repository_root: Path,
    readback: Any,
    authorization_reference: str | None,
    fork_reason: str,
):
    """Validate immutable inputs without reading the old chain's mutable tail."""
    from . import checkpoint_recovery as recovery
    from .checkpoints import PLATFORM_DATA_PATH, checkpoints_root, file_digest

    if not fork_reason.strip():
        raise CheckpointError(
            "fork_reason_required", "fork needs an explicit reason", obj="fork_reason"
        )
    new_run_id = recovery.safe_new_run_id(new_run_id)
    manifest = recovery._load_manifest(source_run_root, checkpoint_id)
    recovery._verify_packaged_digests(source_run_root, manifest, checkpoint_id)
    if manifest.get("kind") == recovery.CHECKPOINT_KIND_PRODUCTION_HANDOFF:
        raise CheckpointError(
            "checkpoint_kind_mode_mismatch", "handoff requires acceptance", obj="kind"
        )
    data_ref = manifest.get("platform_data") or {}
    data_path = checkpoints_root(source_run_root) / checkpoint_id / PLATFORM_DATA_PATH
    if not data_ref or not data_path.is_file():
        raise CheckpointError(
            "checkpoint_data_missing", "checkpoint has no saved platform data", obj="platform_data"
        )
    if data_path.is_symlink() or file_digest(data_path) != data_ref.get("digest"):
        raise CheckpointError(
            "artifact_changed", "platform snapshot digest mismatch", obj="platform_data"
        )
    snapshot = json.loads(data_path.read_text())
    bindings = recovery.production_resume_bindings(manifest)
    if not bindings or (
        snapshot["project_id"] != bindings["project_id"]
        or set(snapshot["ontology_ids"]) != set(bindings["ontology_ids"])
    ):
        raise CheckpointError(
            "snapshot_scope_mismatch", "snapshot differs from checkpoint scope", obj="platform_data"
        )
    if (source_run_root.parent / new_run_id).exists():
        raise CheckpointError("resume_new_run_exists", "new run already exists", obj="new_run_id")
    configuration = recovery._require_configuration_identity(manifest)
    profile_path, task_path = recovery._resolve_checkpoint_contracts(
        source_run_root, manifest, repository_root
    )
    writer = recovery.source_writer_report(source_run_root, readback, [])
    if writer["state_json_status"] is None:
        raise CheckpointError(
            "source_active", "source writer state is unavailable", obj="state.json"
        )
    writer["chain_writer_lock"] = recovery.chain_writer_lock_report(
        source_run_root, manifest, source_run_root.parent
    )
    if writer["chain_writer_lock"]["verdict"] == "writer_process_exited":
        writer["verdict"] = "writer_process_exited"
    if not recovery.source_writer_settles_recovery(writer):
        raise CheckpointError(
            "source_active", "stop source writer before forking", obj="source_run_id"
        )
    approvals = recovery.validate_business_approvals(manifest, source_run_root)
    if approvals.get("invalidated"):
        raise CheckpointError(
            "approval_binding_changed", "source approvals are invalid", obj="approvals"
        )
    completed = [
        recovery.CompletedOperation(
            origin_run_id=source_run_root.name,
            **{key: value for key, value in row.items() if key != "batch_complete"},
        )
        for row in snapshot.get("completed_operations", [])
    ]
    reconciliation = {
        "completed": completed,
        "completion_index": {entry.key: entry for entry in completed},
        "completed_client_batches": {
            row["client_batch_id"]: row["batch_id"]
            for row in snapshot.get("completed_operations", [])
            if row["batch_complete"]
        },
        "pending_new_dry_run": [],
        "recoverable_new_batch": [],
        "blocked": [],
        "scope_drift": [],
        "readback_counters": {},
    }
    mappings = recovery.build_plan_mappings(manifest, source_run_root, reconciliation)
    packets = recovery.build_role_packets(
        manifest, reconciliation, mappings, approvals, configuration
    )
    origin = {
        "schema_version": "r3-0-017-fork/v1",
        "source_run_id": source_run_root.name,
        "root_run_id": new_run_id,
        "new_run_id": new_run_id,
        "checkpoint_id": checkpoint_id,
        "checkpoint_digest": recovery.manifest_digest(
            recovery.manifest_path(source_run_root, checkpoint_id)
        ),
        "snapshot_digest": snapshot["digest"],
        "authorization_reference": authorization_reference,
        "fork_reason": fork_reason,
        "source_writer": writer,
        "old_chain_writes": "unchanged; no reconciliation claim",
    }
    imports = {
        "business_approvals": approvals,
        "completed_client_batches": reconciliation["completed_client_batches"],
        "completed_operations": [entry.index_entry() for entry in completed],
        "plan_mappings": mappings,
    }
    target_project_id = uuid4()
    plan = recovery.RecoveryPlan(
        manifest=manifest,
        manifest_digest=origin["checkpoint_digest"],
        source_run_root=source_run_root,
        checkpoint_id=checkpoint_id,
        new_run_id=new_run_id,
        chain_roots=recovery.origin_chain_roots(source_run_root, source_run_root.parent),
        reconciliation=reconciliation,
        approvals=approvals,
        plan_mappings=mappings,
        role_packets=packets,
        inspection={
            "accounting": {"semantic_starts": 1, "kind": "fork"},
            "prep_timing": {},
            "source_writer": writer,
        },
        origin=origin,
        imports=imports,
        profile_path=profile_path,
        task_path=task_path,
        scope={
            "mode": "checkpoint",
            "project_id": str(target_project_id),
            "ontology_ids": [
                str(uuid5(target_project_id, item)) for item in snapshot["ontology_ids"]
            ],
            "root_run_id": new_run_id,
        },
        prep_started_at=0,
        prep_finished_at=0,
    )
    return plan, snapshot
