"""DSH wiring onto the existing run-scoped immutable handoff store."""

from __future__ import annotations

import json
import os
import threading
from hashlib import sha256
from pathlib import Path

from .handoff_materials import HandoffMaterials, MaterialError, _no_links, _relative
from .runtimes.base import RuntimeDelivery
from .scenario_map import scenario_map_artifact_paths


class DshRunMaterials(HandoffMaterials):
    def __init__(self, root: Path, scope_id: str, coordinators: set[str]):
        super().__init__(root, scope_id)
        self.coordinators = coordinators
        self.targets = {
            p.relative_to(root.parent).as_posix()
            for p in scenario_map_artifact_paths(root.parent).values()
        }
        self.journal = root.parent / "evidence/dsh-handoff.jsonl"
        self.lock = threading.RLock()
        self.artifacts = {}
        self.artifact_versions = {}
        self.public_inputs = {}
        if self.journal.exists():
            for line in self.journal.read_text().splitlines():
                record = json.loads(line)
                if record["run_id"] != scope_id:
                    raise MaterialError(
                        "material_binding_changed", "handoff journal belongs to another run"
                    )
                self._collection(record)[record["handoff_id"]] = record
                if record["kind"] == "artifact":
                    self.artifact_versions[(record["handoff_id"], record["sha256"])] = record

    def _collection(self, record):
        return self.artifacts if record["kind"] == "artifact" else self.public_inputs

    def _save(self, record):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with self.journal.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._collection(record)[record["handoff_id"]] = dict(record)
        if record["kind"] == "artifact":
            self.artifact_versions[(record["handoff_id"], record["sha256"])] = dict(record)

    def write_output(self, actor_id, relative_path, content):
        relative = _relative(relative_path).as_posix()
        if not relative.startswith("scenario-map/"):
            return super().write_output(actor_id, relative, content)
        if actor_id not in self.coordinators:
            raise MaterialError(
                "material_forbidden",
                "only the bound Coordinator can deliver scenario-map artifacts",
            )
        if relative not in self.targets:
            raise MaterialError(
                "material_path_invalid", "use an existing scenario-map artifact filename"
            )
        with self.lock:
            if not isinstance(content, str):
                raise MaterialError("material_media_unsupported", "output must be UTF-8 text")
            data = content.encode("utf-8")
            digest = sha256(data).hexdigest()
            key = actor_id + ":" + relative
            previous = self.artifacts.get(key)
            if (
                previous
                and previous["sha256"] != digest
                and (key, digest) in self.artifact_versions
            ):
                error = MaterialError(
                    "material_version_stale",
                    f"{relative}: historical version superseded; current material_id="
                    f"{previous['material_ref']['material_id']}; read that receipt's original bytes",
                )
                error.data["current_material_ref"] = previous["material_ref"]
                error.data["original_material_ref"] = self.artifact_versions[(key, digest)][
                    "material_ref"
                ]
                raise error
            result = super().write_output(actor_id, relative, content)
            try:
                replaced = None
                if previous is not None and previous["sha256"] == digest:
                    record = dict(previous)
                    # Recheck the original immutable version and its current grants.
                    try:
                        if self.resolve("runner", record["material_ref"]).encode("utf-8") != data:
                            raise MaterialError(
                                "material_digest_mismatch", "original artifact bytes changed"
                            )
                    except MaterialError as exc:
                        if exc.code not in {
                            "material_source_unavailable",
                            "material_digest_mismatch",
                        }:
                            raise
                        replaced = {
                            "replaces_material_ref": record["material_ref"],
                            "replaced_error": exc.code,
                        }
                if previous is None or previous["sha256"] != digest or replaced:
                    publication = self.publish(actor_id, "runner", result["source_path"])
                    record = {
                        "kind": "artifact",
                        "handoff_id": key,
                        "run_id": self.scope_id,
                        "actor_id": actor_id,
                        "source_path": result["source_path"],
                        "target": relative,
                        "sha256": digest,
                        "state": "pending",
                        "material_ref": {"material_id": publication["material_id"]},
                    }
                    record.update(replaced or {})
                    self._save(record)
                target = self.root.parent / relative
                _no_links(target)
                if record["state"] == "received":
                    if target.exists() and (not target.is_file() or target.read_bytes() != data):
                        raise MaterialError(
                            "material_target_changed",
                            "received target changed; reconcile it before retrying this version",
                        )
                    if target.is_file():
                        return {**result, "runner_receipt": record}
                if target.is_file() and target.read_bytes() == data:
                    record.update(state="received")
                    self._save(record)
                    return {**result, "runner_receipt": record}
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                temporary = target.with_suffix(".handoff-tmp")
                _no_links(temporary)
                temporary.write_bytes(data)
                temporary.chmod(0o600)
                temporary.replace(target)
                record.update(state="received")
                record.pop("error", None)
                self._save(record)
                return {**result, "runner_receipt": record}
            except OSError as exc:
                raise MaterialError(
                    "material_target_unavailable",
                    f"{relative}: {exc}; retry the same write after correcting the target",
                ) from exc

    def queue_public_input(self, path, recipients, projection_digest, *, freeze=None):
        """Called only after the Runner wrote its authorized public projection."""
        with self.lock:
            version = path.relative_to(self.root.parent).as_posix()
            for recipient in recipients:
                key = (
                    "cq-public-"
                    + sha256(f"{self.scope_id}:{recipient}:{version}".encode()).hexdigest()
                )
                if key in self.public_inputs:
                    continue
                notice = {
                    "run_id": self.scope_id,
                    "version": version,
                    "projection_digest": projection_digest,
                }
                if freeze is not None:
                    notice["freeze"] = dict(freeze)
                self._save(
                    {
                        "kind": "public-input",
                        "handoff_id": key,
                        "run_id": self.scope_id,
                        "recipient_id": recipient,
                        "version": version,
                        "notice": notice,
                        "state": "pending",
                    }
                )

    def flush_public_inputs(self, adapter):
        with self.lock:
            for original in list(self.public_inputs.values()):
                record = dict(original)
                try:
                    if record.get("dispatch_id"):
                        statuses = adapter.dispatch_status(record["recipient_id"])
                        status = next(
                            (s for s in statuses if s["dispatch_id"] == record["dispatch_id"]), None
                        )
                        state = status["state"] if status else "unknown"
                        record["state"] = state
                        if state not in {"failed", "canceled"}:
                            if record != original:
                                self._save(record)
                            continue
                    if "material_ref" not in record:
                        path = self.root.parent / record["version"]
                        publication = self.publish("runner", record["recipient_id"], str(path))
                        record["material_ref"] = {"material_id": publication["material_id"]}
                        self._save(record)
                    notice = {**record["notice"], "material_ref": record["material_ref"]}
                    delivery = RuntimeDelivery(
                        "runner/competency-questions",
                        record["recipient_id"],
                        "cq-public-input",
                        json.dumps(notice, ensure_ascii=False, sort_keys=True),
                        delivery_id=record["handoff_id"],
                        material_refs=(record["material_ref"],),
                    )
                    receipt = adapter.send_message(record["recipient_id"], delivery)
                    record.update(state="queued", dispatch_id=receipt.dispatch_id)
                    record.pop("error", None)
                except Exception as exc:
                    # Dispatch exceptions carry the original identity even if the RPC reply was lost.
                    if getattr(exc, "dispatch_id", None):
                        record["dispatch_id"] = exc.dispatch_id
                        record["state"] = "unknown"
                    record["error"] = str(exc)
                if record != original:
                    self._save(record)
