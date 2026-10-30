"""Explicit data fork plus attributed business continuation; never rewind an applied source model."""

import fcntl
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from .contracts import FrameworkError, TaskBinding, _check_sources, write_json
from .control import TaskControl
from .snapshots import RunSnapshots
from .workspace import WorkspaceRepository


class SnapshotFork:
    def __init__(self, binding, repository, bridge):
        self.binding, self.repository, self.bridge = binding, repository, bridge

    def create(
        self,
        snapshot_id,
        destination,
        run_id,
        reason,
        authorization_reference,
        archive_source=False,
    ):
        if not archive_source:
            raise FrameworkError(
                "archive_source_acknowledgment_required",
                instruction="The reused platform fork archives every source Ontology; explicitly select archive-source.",
            )
        destination = Path(destination).resolve()
        request = {
            "source_run": self.binding.data["run_id"],
            "snapshot": snapshot_id,
            "run_id": run_id,
            "reason": reason,
            "authorization_reference": authorization_reference,
        }
        pending_path = destination / "fork-pending.json"
        pending = json.loads(pending_path.read_text()) if pending_path.exists() else None
        if pending:
            if pending["request"] != request:
                raise FrameworkError("fork_identity_conflict")
            if pending["status"] == "ready":
                return {
                    "status": "prepared",
                    "run_dir": str(destination),
                    "target": pending["result"],
                    "replayed": True,
                }
            if pending["status"] in {"requesting", "unknown"}:
                raise FrameworkError(
                    "fork_result_unknown",
                    target_project_id=pending["target_project_id"],
                    instruction="Read back this exact preallocated target before retrying; no replacement project was created.",
                )
        frozen = RunSnapshots(root=self.binding.root).read(
            pending["snapshot_id"] if pending else snapshot_id
        )
        reference = frozen.get("platform_data")
        if not reference:
            raise FrameworkError(
                "snapshot_platform_data_missing",
                instruction="Save with include-platform; ordinary observation snapshots remain valid for viewing.",
            )
        data_path = self.binding.root / "snapshots" / reference["path"]
        if hashlib.sha256(data_path.read_bytes()).hexdigest() != reference["sha256"]:
            raise FrameworkError("snapshot_platform_data_changed")
        data = json.loads(data_path.read_text())
        if data["project_id"] != frozen["model_context"]["project_id"]:
            raise FrameworkError("snapshot_scope_mismatch")
        old = frozen["binding"]
        original = TaskBinding(self.binding.root, old)
        if _check_sources(original.materials) != old["source_manifest"]:
            raise FrameworkError("snapshot_sources_changed")
        config = json.loads((self.binding.root / "private-runtime.json").read_text())
        with (self.binding.root / "run.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise FrameworkError(
                    "source_run_active",
                    instruction="Pause and let its native activity settle first.",
                ) from error
            control = TaskControl(self.repository)
            if control.view()["active"]:
                raise FrameworkError("source_activity_unsettled")
            if pending is None:
                target_id = str(uuid4())
                inputs = destination.parent / (destination.name + "-fork-inputs")
                inputs.mkdir(mode=0o700)
                task = {
                    key: old[key]
                    for key in (
                        "schema_version",
                        "task_ref",
                        "work_unit_id",
                        "objective",
                        "instructions",
                        "evaluation",
                    )
                }
                task.update(
                    run_id=run_id,
                    materials=str(original.materials),
                    model_profile=str(self.binding.root / "model-profile.yaml"),
                    authorization={**old["authorization"], "reference": authorization_reference},
                    workspace_ref=old["task_ref"] + ":fork:" + run_id,
                    scope={
                        "mode": "existing",
                        "base_url": old["scope"]["base_url"],
                        "project_id": target_id,
                        "ontology_ids": [
                            str(uuid5(UUID(target_id), oid)) for oid in data["ontology_ids"]
                        ],
                        "fork_created_by_run": run_id,
                    },
                )
                task["objective"] = (
                    "Continue from captured actual model and attributed business records. Reuse valid existing definitions; return no_change if the actual model already satisfies the sources. Historical workflow states and acceptance are not inherited proof. "
                    + task["objective"]
                )
                for key in (
                    "work_units",
                    "work_management",
                    "semantic_workspace",
                    "shared_memory",
                    "unit_concurrency",
                ):
                    if key in old:
                        task[key] = old[key]
                task["project_ref"] = target_id
                write_json(inputs / "task.json", task)
                new = TaskBinding.prepare(inputs / "task.json", destination)
                write_json(destination / "private-runtime.json", config)
                pending = {
                    "status": "prepared",
                    "request": request,
                    "target_project_id": target_id,
                    "snapshot_digest": reference["digest"],
                    "snapshot_id": frozen["snapshot_id"],
                    "source_model": frozen["model_context"],
                    "accounting": {
                        "kind": "fork",
                        "semantic_start": "pending real model invocation",
                        "budget_ref": old["authorization"].get("budget_ref"),
                    },
                }
                write_json(pending_path, pending)
            else:
                new = TaskBinding.load(destination)
            if pending["status"] == "prepared":
                control.enqueue(
                    "fork-stop:" + run_id, "stop", metadata={"source": "host", "reason": reason}
                )
                control.synchronize()
                cleanup_path = self.binding.root / "host/cleanup.json"
                cleanup = (
                    json.loads(cleanup_path.read_text())
                    if cleanup_path.exists()
                    else self.bridge.call("cleanup", {})
                )
                if not cleanup.get("aggregate_keys_non_active"):
                    raise FrameworkError("source_keys_not_sealed", receipt=cleanup)
                pending.update(status="requesting", source_cleanup=cleanup)
                write_json(pending_path, pending)
                try:
                    result = self.bridge.call(
                        "fork_data",
                        {
                            "snapshot": data,
                            "name": run_id,
                            "target_project_id": pending["target_project_id"],
                        },
                    )
                    if result["data"]["project_id"] != new.data["scope"]["project_id"] or set(
                        result["data"]["ontology_ids"]
                    ) != set(new.data["scope"]["ontology_ids"]):
                        raise FrameworkError("fork_target_mismatch")
                except Exception:
                    pending["status"] = "unknown"
                    write_json(pending_path, pending)
                    raise
                pending.update(
                    status="copied",
                    result=result["data"],
                    fork_credential=result["credential"],
                    resource_bindings=result.get("resource_bindings", {}),
                )
                write_json(pending_path, pending)
            # These are captured native identities, not applications made by
            # this new run. Keep their provenance and use the existing resolver.
            write_json(
                destination / "host/applied-bindings.json", pending.get("resource_bindings", {})
            )
            target = WorkspaceRepository(
                config["connection"], config["workspace_schema"], new.data["workspace_ref"]
            )
            target.setup()
            project = (
                WorkspaceRepository(
                    config["connection"],
                    config["workspace_schema"],
                    "project:" + new.data["project_ref"],
                )
                if new.data.get("project_ref")
                else None
            )
            imported = []
            for repository, rows in [
                (target, frozen["objects"]),
                (project, frozen.get("project_objects", [])),
            ]:
                if repository is None:
                    continue
                for row in rows:
                    if row["kind"] not in {"semantic_record", "shared_memory"}:
                        continue
                    content = {
                        **row["content"],
                        "origin_snapshot": {
                            "run_id": old["run_id"],
                            "snapshot_id": frozen["snapshot_id"],
                            "object_id": row["object_id"],
                            "revision": row["revision"],
                        },
                        "invalidation": {
                            "reason": "fork context requires recheck against actual target model"
                        },
                    }
                    if row["kind"] == "semantic_record":
                        content["states"] = {
                            **content.get("states", {}),
                            "applicability": "needs_review",
                        }
                    else:
                        content["applicability"] = "needs_review"
                    imported.append(
                        repository.put_reference(row["object_id"], row["kind"], content, 0)
                    )
            pending.update(status="ready", imported_refs=imported)
            write_json(pending_path, pending)
        return {
            "status": "prepared",
            "run_dir": str(destination),
            "target": pending["result"],
            "imported_count": len(imported),
            "source_disposition": "archived",
            "new_native_context": True,
        }
