"""Explicit, retained source revisions and selective work re-entry within one run."""

from datetime import UTC, datetime
from pathlib import Path

from .contracts import FrameworkError, TaskBinding, _check_sources, digest, safe_id, write_json
from .control import TaskControl


class SourceRevisions:
    def __init__(self, binding, repository):
        self.binding, self.repository = binding, repository
        self.control = TaskControl(repository)

    def stage(self, change, materials):
        """Accept a Host source package immediately; activate only at a settled boundary."""
        identity = safe_id(change["change_id"])
        manifest = _check_sources(materials)
        record_id = self.binding.identity + ":source-change:" + identity
        request_digest = digest({"change": change, "manifest": manifest})
        prior = self.repository.get(record_id)
        if prior:
            if prior["content"]["request_digest"] != request_digest:
                raise FrameworkError("source_change_identity_conflict")
            return prior["content"]
        changed = [
            key
            for key in sorted(self.binding.data["source_manifest"].keys() | manifest.keys())
            if self.binding.data["source_manifest"].get(key) != manifest.get(key)
        ]
        plan = self.repository.get(self.binding.identity + ":work-plan")
        units = (
            plan["content"]["units"]
            if plan
            else {
                u["unit_id"]: {**u, "parent_id": u.get("parent_id", "modeling")}
                for u in self.binding.data.get("work_units", [])
            }
        )
        known = {key for key, unit in units.items() if unit.get("status", "active") == "active"}
        requested = change.get("affected_units", sorted(known))
        if not set(requested).issubset(known):
            raise FrameworkError("work_unit_not_found", available_ids=sorted(known))
        from .work_plan import WorkPlan

        affected = sorted(
            {u for key in requested for u in WorkPlan.ancestors({"units": units}, key)}
            - {"modeling"}
        )
        content = {
            "change_id": identity,
            "request_digest": request_digest,
            "manifest": manifest,
            "changed_materials": changed,
            "affected_units": affected,
            "reason": change["reason"],
            "evaluation": change.get("evaluation", self.binding.data["evaluation"]),
        }
        destination = self.binding.root / "source-revisions" / identity / "materials"
        for entry in manifest.values():
            target = destination / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes((Path(materials) / entry["path"]).read_bytes())
        write_json(destination / "manifest.json", manifest)
        content.update(status="queued", queued_at=datetime.now(UTC).isoformat())
        self.repository.put_reference(record_id, "source_change", content, 0)
        return content

    def activate(self):
        """Resume queued source changes without replacing old materials, receipts or model IDs."""
        if self.control.view()["active"]:
            return self.binding
        changes = sorted(
            self.repository.list_kind("source_change"), key=lambda r: r["content"]["queued_at"]
        )
        for row in changes:
            change = row["content"]
            if change["status"] != "queued":
                continue
            current = self.repository.get(self.binding.identity + ":work")
            if current and current["content"]["status"] == "uncertain":
                return self.binding
            previous = self.binding.data
            plan = self.repository.get(self.binding.identity + ":work-plan")
            data = {
                **previous,
                "cycle_id": change["change_id"],
                "source_directory": "source-revisions/" + change["change_id"] + "/materials",
                "source_manifest": change["manifest"],
                "source_manifest_digest": digest(change["manifest"]),
                "evaluation": change["evaluation"],
            }
            if plan:
                data["work_units"] = [
                    u for u in plan["content"]["units"].values() if u["status"] == "active"
                ]
            for version in (previous, data):
                write_json(
                    self.binding.root / "binding-versions" / (digest(version) + ".json"),
                    {"digest": digest(version), "binding": version},
                )
            write_json(
                self.binding.root / "binding.json", {"digest": digest(data), "binding": data}
            )
            self.binding = TaskBinding.load(self.binding.root)
            selected = [self.binding] + [
                self.binding.for_unit(unit) for unit in change["affected_units"]
            ]
            for binding in selected:
                work_id = binding.identity + ":work"
                work = self.repository.get(work_id)
                if not work or work["content"].get("source_change_id") == change["change_id"]:
                    continue
                state = {
                    **work["content"],
                    "activity": "model",
                    "status": "ready",
                    "round": work["content"]["round"] + 1,
                    "refresh_baseline": True,
                    "semantic_acceptance": "unverified",
                    "source_change_id": change["change_id"],
                    "issue": {
                        "code": "source_changed",
                        "changed_materials": change["changed_materials"],
                        "reason": change["reason"],
                        "instruction": "Review the explicit source revision against the actual model. "
                        "Reuse unchanged valid results; do not recreate existing definitions. "
                        "A withdrawn source is not proof its former business statement is false.",
                    },
                }
                self.repository.put_reference(work_id, "work_unit", state, work["revision"])
            self.repository.put_reference(
                row["object_id"],
                "source_change",
                {**change, "status": "activated"},
                row["revision"],
            )
        return self.binding
