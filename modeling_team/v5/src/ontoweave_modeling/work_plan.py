"""A versioned work tree: Agents own decomposition; the scheduler executes ready work."""

import json

from .contracts import FrameworkError, TaskBinding, safe_id

WORK_TOOLS = ("delegate_work", "get_work_tree", "reopen_work_unit", "update_work_unit")


class WorkPlan:
    def __init__(self, task, repository, actor=None):
        self.task, self.repository = task, repository
        self.root_actor = (
            "coordinator" if task.get("team_contract") == "role-team/v1" else "modeling"
        )
        self.actor = actor or self.root_actor
        self.identity = "run:" + task["run_id"] + ":work-plan"

    def row(self):
        row = self.repository.get(self.identity)
        if row:
            return row
        units = {
            u["unit_id"]: {
                **u,
                "parent_id": u.get("parent_id", self.root_actor),
                "dependencies": u.get("dependencies", []),
                "generation": 0,
                "status": "active",
            }
            for u in self.task.get("work_units", [])
        }
        content = {"units": units, "root_generation": 0, "root_actor": self.root_actor}
        if self.root_actor == "coordinator":
            from .role_team import validate_units

            validate_units(content, self.task)
        self.repository.put_reference(self.identity, "work_plan", content, 0)
        return self.repository.get(self.identity)

    def change(self, update):
        while True:
            row = self.row()
            content = row["content"]
            result = update(content)
            if self.root_actor == "coordinator":
                from .role_team import validate_units

                validate_units(content, self.task)
            saved = self.repository.put(self.identity, "work_plan", content, row["revision"])
            if saved.get("code") == "version_conflict":
                continue
            if saved.get("status") != "recorded":
                raise FrameworkError(saved["code"], actual=saved)
            return result

    def delegate(
        self,
        unit_id,
        objective,
        instructions="",
        dependencies=None,
        material_ids=None,
        role_id=None,
        work_kind=None,
        scope_ref=None,
    ):
        safe_id(unit_id)
        if unit_id in {"modeling", "acceptance", self.root_actor, self.task["work_unit_id"]}:
            raise FrameworkError("work_unit_identity_conflict")
        if not objective.strip():
            raise FrameworkError("work_unit_objective_required")
        requested = {
            "unit_id": unit_id,
            "parent_id": self.actor,
            "objective": objective,
            "instructions": instructions,
            "dependencies": dependencies or [],
            "material_ids": material_ids or [],
        }
        if self.root_actor == "coordinator":
            from .role_team import ROLE_KINDS

            current = self.row()["content"]["units"].get(self.actor, {})
            actor_role = current.get("role_id", "coordinator")
            role_id = role_id or (actor_role if actor_role != "coordinator" else None)
            if role_id not in ROLE_KINDS:
                raise FrameworkError("work_role_required", unit_id=unit_id)
            if actor_role != "coordinator" and role_id != actor_role:
                raise FrameworkError("work_role_forbidden", role_id=role_id)
            parent_materials = current.get("material_ids", [])
            if parent_materials and set(requested["material_ids"]) - set(parent_materials):
                raise FrameworkError("material_forbidden", unit_id=unit_id)
            requested.update(
                role_id=role_id,
                actor_id=unit_id,
                work_kind=work_kind or ROLE_KINDS[role_id],
                scope_ref=scope_ref or current.get("scope_ref"),
                work_phase="plan"
                if role_id == "coordinator"
                else "propose"
                if role_id == "modeling"
                else "produce",
            )
        unknown = set(requested["material_ids"]) - self.task["source_manifest"].keys()
        if unknown:
            raise FrameworkError("material_not_found", material_ids=sorted(unknown))

        def update(plan):
            prior = plan["units"].get(unit_id)
            if prior:
                if any(
                    prior.get(key, [] if key in {"dependencies", "material_ids"} else "") != value
                    for key, value in requested.items()
                ):
                    raise FrameworkError("work_unit_exists", actual=prior)
                return prior
            plan["units"][unit_id] = {**requested, "generation": 0, "status": "active"}
            return plan["units"][unit_id]

        return self.change(update)

    @staticmethod
    def ancestors(plan, unit_id):
        found = []
        root = plan.get("root_actor", "modeling")
        while unit_id != root:
            if unit_id in found:
                raise FrameworkError("work_tree_cycle", unit_id=unit_id)
            found.append(unit_id)
            if unit_id not in plan["units"]:
                raise FrameworkError("work_unit_not_found", unit_id=unit_id)
            unit_id = plan["units"][unit_id]["parent_id"]
        return [*found, root]

    def _can_manage(self, plan, unit_id):
        if self.root_actor != "coordinator" or self.actor == self.root_actor:
            return
        if self.actor not in self.ancestors(plan, unit_id):
            raise FrameworkError("work_owner_forbidden", unit_id=unit_id)

    def reopen(self, unit_id, reason):
        def update(plan):
            self._can_manage(plan, unit_id)
            for identity in self.ancestors(plan, unit_id):
                if identity == self.root_actor:
                    plan["root_generation"] += 1
                    plan["root_reentry_reason"] = reason
                else:
                    unit = plan["units"][identity]
                    unit.update(
                        generation=unit["generation"] + 1, status="active", reentry_reason=reason
                    )
            return {"status": "reentry_requested", "unit_id": unit_id, "reason": reason}

        return self.change(update)

    def update(self, unit_id, objective=None, dependencies=None, status=None, reason=""):
        def update(plan):
            if unit_id not in plan["units"]:
                raise FrameworkError("work_unit_not_found", unit_id=unit_id)
            unit = plan["units"][unit_id]
            self._can_manage(plan, unit_id)
            if self.root_actor == "coordinator" and status == "retired":
                from .control import TaskControl

                if unit_id in TaskControl(self.repository).view()["active"]:
                    raise FrameworkError("work_execution_reconciliation_required", unit_id=unit_id)
            if objective is not None:
                unit["objective"] = objective
            if dependencies is not None:
                unit["dependencies"] = dependencies
            if status is not None:
                if status not in {"active", "retired"}:
                    raise FrameworkError("work_unit_status_invalid")
                unit["status"] = status
            unit.update(updated_by=self.actor, update_reason=reason)
            return unit

        return self.change(update)

    def binding(self, original):
        plan = self.row()["content"]
        if self.root_actor == "coordinator" and any(
            u.get("retire_after_intake") for u in plan["units"].values()
        ):
            from .control import TaskControl

            active = TaskControl(self.repository).view()["active"]
            retired = [
                identity
                for identity, unit in plan["units"].items()
                if unit.get("retire_after_intake")
                and identity not in active
                and (
                    work := self.repository.get(
                        "run:" + self.task["run_id"] + ":unit:" + identity + ":work"
                    )
                )
                and work["content"].get("intake_material_ref")
            ]
            if retired:

                def retire(current):
                    for identity in retired:
                        current["units"][identity].update(
                            status="retired", retire_after_intake=False
                        )

                self.change(retire)
                plan = self.row()["content"]
        return TaskBinding(
            original.root,
            {
                **original.data,
                "work_units": [u for u in plan["units"].values() if u["status"] == "active"],
                "work_generation": plan["root_generation"],
            },
        )

    def tree(self, parent_id=None, offset=0, limit=20):
        row = self.row()
        units = []
        children = [
            u
            for u in row["content"]["units"].values()
            if u["parent_id"] == (parent_id or self.actor)
        ]
        for unit in children[offset : offset + limit]:
            work = self.repository.get(
                "run:" + self.task["run_id"] + ":unit:" + unit["unit_id"] + ":work"
            )
            units.append(
                {
                    **unit,
                    "work": work["content"] if work else None,
                    "child_count": sum(
                        u["parent_id"] == unit["unit_id"] for u in row["content"]["units"].values()
                    ),
                    "expand": {"parent_id": unit["unit_id"]},
                }
            )
        return {
            "team_contract": self.task.get("team_contract", "single-modeler/v1"),
            "root_actor": self.root_actor,
            "revision": row["revision"],
            "units": units,
            "root_generation": row["content"]["root_generation"],
            "parent_id": parent_id or self.actor,
            "total": len(children),
            "next_offset": offset + limit if offset + limit < len(children) else None,
            "coverage": "direct_children_only",
            "instruction": "Absence on this page does not mean a unit is absent from the tree; expand a child's parent_id to inspect its direct children.",
        }


def register_work_tools(server, plan):
    from mcp.server.fastmcp.exceptions import ToolError

    def call(method, *args):
        try:
            return method(*args)
        except FrameworkError as error:
            raise ToolError(json.dumps(error.as_dict())) from error

    @server.tool()
    def delegate_work(
        unit_id: str,
        objective: str,
        instructions: str = "",
        dependencies: list[str] | None = None,
        material_ids: list[str] | None = None,
        role_id: str | None = None,
        work_kind: str | None = None,
        scope_ref: dict | None = None,
    ) -> dict:
        """Create a direct child with a bounded objective and source IDs. It may delegate further.
        Dependencies name sibling/other work units. Return waiting_children after delegating;
        only the root applies. Repeating an identical definition reuses the unit."""
        return call(
            plan.delegate,
            unit_id,
            objective,
            instructions,
            dependencies,
            material_ids,
            role_id,
            work_kind,
            scope_ref,
        )

    @server.tool()
    def get_work_tree(parent_id: str | None = None, offset: int = 0, limit: int = 20) -> dict:
        """Read hierarchy, dependencies, retained results and unresolved scope; completion is not acceptance."""
        return plan.tree(parent_id, offset, limit)

    @server.tool()
    def reopen_work_unit(unit_id: str, reason: str) -> dict:
        """Request selective rework of a unit and its ancestors at natural boundaries; siblings are retained."""
        return call(plan.reopen, unit_id, reason)

    @server.tool()
    def update_work_unit(
        unit_id: str,
        objective: str | None = None,
        dependencies: list[str] | None = None,
        status: str | None = None,
        reason: str = "",
    ) -> dict:
        """Adjust scope/dependencies or retire a unit; retirement does not prove its scope is delivered.
        Use reopen_work_unit when a finished result must change."""
        return call(plan.update, unit_id, objective, dependencies, status, reason)
