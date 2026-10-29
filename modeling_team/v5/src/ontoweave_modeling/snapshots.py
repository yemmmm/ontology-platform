"""Named, Host-private observation snapshots for comparing workflow experiments."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from psycopg import sql

from .contracts import FrameworkError, digest, write_json


class RunSnapshots:
    def __init__(self, binding=None, repository=None, *, root=None):
        self.binding, self.repository = binding, repository
        self.root = (Path(root) if root is not None else binding.root) / "snapshots"

    def save(self, name, graph, bridge):
        config = {"configurable": {"thread_id": self.binding.data["run_id"]}}
        state = graph.get_state(config)
        with self.repository.connect() as connection:
            rows = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE task_ref=%s ORDER BY object_id").format(
                    self.repository.table("business_objects")
                ),
                (self.repository.task_ref,),
            ).fetchall()
        objects, executions = [], []
        for row in rows:
            record = {
                **self.repository.view(row),
                "digest": digest(row["content"]),
                "updated_at": row["updated_at"].isoformat(),
            }
            if row["kind"] == "execution":
                # Original prompt/events stay in the run's execution store, not every snapshot.
                executions.append({k: record[k] for k in ["object_id", "revision", "digest"]})
            else:
                objects.append(record)
        work = next(
            (r["content"] for r in objects if r["object_id"] == self.binding.identity + ":work"), {}
        )
        model = None
        model_error = None
        reference = work.get("target_ref", work.get("baseline_ref"))
        if reference:
            model = self.repository.read_reference(reference)
            try:
                model = bridge.call("snapshot", {})
            except FrameworkError as error:
                model_error = error.as_dict()
        source_hashes = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        }
        snapshot = {
            "schema_version": "ontoweave-run-snapshot/v1",
            "snapshot_id": uuid.uuid4().hex,
            "name": name,
            "saved_at": datetime.now(UTC).isoformat(),
            "task_ref": self.binding.data["task_ref"],
            "run_id": self.binding.data["run_id"],
            "binding_digest": digest(self.binding.data),
            "source_hashes": source_hashes,
            "workflow": {
                "checkpoint_config": state.config,
                "values": state.values,
                "next": list(state.next),
            },
            "objects": objects,
            "execution_refs": executions,
            "model_context": model,
            "model_read_error": model_error,
            "capture_note": "Components are read observations with their own versions; "
            "this is not a cross-store transaction or a model rollback.",
        }
        self.root.mkdir(mode=0o700, exist_ok=True)
        path = self.root / (snapshot["snapshot_id"] + ".json")
        write_json(path, snapshot)
        path.chmod(0o600)
        return {
            "snapshot_id": snapshot["snapshot_id"],
            "name": name,
            "path": str(path),
            "object_count": len(objects),
            "model_read_error": model_error,
        }

    def list(self):
        return [
            {
                "snapshot_id": d["snapshot_id"],
                "name": d["name"],
                "saved_at": d["saved_at"],
                "object_count": len(d["objects"]),
            }
            for d in self._all()
        ]

    def _all(self):
        return sorted(
            (json.loads(p.read_text()) for p in self.root.glob("*.json")),
            key=lambda d: d["saved_at"],
        )

    def read(self, identity):
        found = [d for d in self._all() if identity in {d["snapshot_id"], d["name"]}]
        if not found:
            raise FrameworkError("snapshot_not_found", snapshot=identity)
        return found[-1]

    def diff(self, before, after):
        a, b = self.read(before), self.read(after)
        left = {r["object_id"]: r for r in a["objects"]}
        right = {r["object_id"]: r for r in b["objects"]}
        changes = []
        for identity in sorted(left.keys() | right.keys()):
            old, new = left.get(identity), right.get(identity)
            if old and new and old["digest"] == new["digest"]:
                continue
            fields = sorted(
                k
                for k in (
                    (old or {}).get("content", {}).keys() | (new or {}).get("content", {}).keys()
                )
                if (old or {}).get("content", {}).get(k) != (new or {}).get("content", {}).get(k)
            )
            changes.append(
                {
                    "object_id": identity,
                    "kind": (new or old)["kind"],
                    "before_revision": old["revision"] if old else None,
                    "after_revision": new["revision"] if new else None,
                    "changed_fields": fields,
                }
            )
        return {
            "before": a["snapshot_id"],
            "after": b["snapshot_id"],
            "changes": changes,
            "workflow_changed": a["workflow"] != b["workflow"],
            "before_model_revisions": (a["model_context"] or {}).get("model_revisions"),
            "after_model_revisions": (b["model_context"] or {}).get("model_revisions"),
        }
