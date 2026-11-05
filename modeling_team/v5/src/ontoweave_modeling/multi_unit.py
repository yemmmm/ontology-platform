"""Independent work-tree checkpoints, ready dependencies, and root-owned application."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from .execution import CodexInvocation
from .flow import WorkUnitFlow
from .work_plan import WorkPlan


class MultiUnitFlow:
    def __init__(self, binding, repository, bridge, checkpoint_schema, invoke_factory=None):
        self.original, self.repository, self.bridge = binding, repository, bridge
        self.checkpoint_schema = checkpoint_schema
        self.invoke_factory = invoke_factory or (lambda selected: CodexInvocation(selected, bridge))
        self.check_invoke_factory = invoke_factory
        self.plan = WorkPlan(binding.data, repository)
        self.refresh()

    def refresh(self, busy=None):
        self.binding = self.plan.binding(self.original)
        selected = [self.binding] + [
            self.binding.for_unit(u["unit_id"]) for u in self.binding.data["work_units"]
        ]
        self.flows = {}
        active = WorkUnitFlow(self.binding, self.repository, self.bridge, None).control.view()[
            "active"
        ]
        for binding in selected:
            flow = WorkUnitFlow(binding, self.repository, self.bridge, self.invoke_factory(binding))
            flow.check_invoke_factory = self.check_invoke_factory
            prior = self.repository.get(flow.work_id)
            if prior and (
                prior["content"].get("status") == "uncertain"
                or (
                    binding.role_team
                    and binding.data["work_unit_id"] in active
                    and binding.actor not in (busy or set())
                )
            ):
                # Reconcile the original application before activating a newer generation.
                from .contracts import TaskBinding

                binding = TaskBinding(
                    binding.root, self.repository.read_reference(prior["content"]["binding_ref"])
                )
                flow = WorkUnitFlow(
                    binding, self.repository, self.bridge, self.invoke_factory(binding)
                )
                flow.check_invoke_factory = self.check_invoke_factory
            unit_active = (
                binding.actor in (busy or set())
                or binding.data["work_unit_id"] in active
                or binding.data["work_unit_id"] + ":platform" in active
            )
            state = prior["content"] if prior and unit_active else flow.initialize()
            generation = binding.data.get("work_generation", 0)
            if state.get("work_generation", 0) != generation and not unit_active:
                flow._save(
                    {
                        **state,
                        "status": "ready",
                        "activity": "model",
                        "round": state["round"] + 1,
                        "work_generation": generation,
                        "refresh_baseline": True,
                        "semantic_acceptance": "unverified",
                        "issue": {
                            "code": "work_reentry",
                            "instruction": "Reassess only this scope and direct child changes against the actual model; reuse valid siblings.",
                        },
                        **(
                            {
                                "role_phase": binding.data.get("work_phase", "integrate"),
                                "role_id": binding.role,
                                "actor_id": binding.actor,
                                "work_kind": binding.work_kind,
                            }
                            if binding.role_team
                            else {}
                        ),
                    }
                )
            self.flows[binding.actor] = flow
        self.parent = self.flows[self.binding.root_actor]
        self.children = [f for actor, f in self.flows.items() if actor != self.binding.root_actor]

    def initialize(self):
        self.refresh()
        return self.repository.get(self.parent.work_id)["content"]

    def states(self):
        return {
            child.binding.actor: self.repository.get(child.work_id)["content"]
            for child in self.children
        }

    def advance(self):
        state = self.initialize()
        if state["status"] == "handoff_ready":
            return {"work": state, "units": self.states()}
        if state["activity"] == "prepare":
            self.parent._prepare(state)
        self.bridge.call("read_config", {"role": self.binding.role})
        with self.repository.checkpointer(self.checkpoint_schema):
            pass

        def advance_unit(flow):
            with self.repository.checkpointer(self.checkpoint_schema) as saver:
                return flow.advance(saver)

        with ThreadPoolExecutor(max_workers=self.binding.data.get("unit_concurrency", 2)) as pool:
            running, seen = {}, {}
            while True:
                self.refresh(busy=set(running.values()))
                states = {
                    actor: self.repository.get(flow.work_id)["content"]
                    for actor, flow in self.flows.items()
                }
                control = self.parent.control.synchronize()
                if control["mode"] == "running" and control["budget_open"]:
                    busy = set(running.values())
                    entries = list(self.flows.items())
                    if self.binding.role_team:
                        entries.sort(
                            key=lambda item: (
                                item[1].binding.data.get("work_phase") != "source_intake"
                            )
                        )
                    for actor, flow in entries:
                        state = states[actor]
                        active_native = control["active"].get(flow.binding.data["work_unit_id"])
                        expected_native = flow.binding.execution_id(
                            f"role-{state['round']:05d}"
                            if state["activity"] == "model"
                            else f"self-check-{state['round']:05d}-{state.get('check_round', 0):03d}"
                        )
                        reconcile_native = (
                            flow.binding.role_team and active_native == expected_native
                        )
                        active_platform = control["active"].get(
                            flow.binding.data["work_unit_id"] + ":platform"
                        )
                        reconcile_apply = (
                            state["activity"] == "apply"
                            and active_platform == f"apply-{state['round']:05d}"
                        )
                        phase = state.get("resume_activity", "model")
                        incoming = {m["id"] for m in flow.human.pending(phase)}
                        marker = (flow.binding.data.get("work_generation", 0), frozenset(incoming))
                        if (
                            actor in busy
                            or (active_native and not reconcile_native)
                            or (
                                active_platform
                                and state["status"] != "uncertain"
                                and not reconcile_apply
                            )
                            or seen.get(actor) == marker
                            or state["status"] == "handoff_ready"
                        ):
                            continue
                        if len(running) >= self.binding.data.get("unit_concurrency", 2):
                            break
                        if state["status"] in {"proposal_ready", "waiting_input"} and not incoming:
                            continue
                        unit = next(
                            (u for u in self.binding.data["work_units"] if u["unit_id"] == actor),
                            {},
                        )
                        dependencies = unit.get("dependencies", [])
                        children = flow.binding.direct_units
                        if (
                            not self.binding.role_team
                            and children
                            and not incoming
                            and (
                                state["status"] == "waiting_children"
                                or not any(
                                    states.get(u["unit_id"], {}).get("status") == "proposal_ready"
                                    for u in children
                                )
                            )
                        ):
                            continue
                        answered_wait = state["status"] == "waiting_input" and incoming
                        generations = {
                            u["unit_id"]: u.get("generation", 0)
                            for u in self.binding.data["work_units"]
                        }
                        if not answered_wait and any(
                            states.get(dep, {}).get("status") != "proposal_ready"
                            or states.get(dep, {}).get("work_generation", 0) != generations.get(dep)
                            for dep in dependencies
                        ):
                            continue
                        seen[actor] = marker
                        running[pool.submit(advance_unit, flow)] = actor
                if not running:
                    break
                completed, _ = wait(running, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in completed:
                    future.result()
                    del running[future]
        state = self.repository.get(self.parent.work_id)["content"]
        if state["status"] not in {
            "handoff_ready",
            "waiting_input",
            "blocked",
            "recoverable_issue",
            "source_change_pending",
            "uncertain",
        }:
            control = self.parent.control.synchronize()
            state = self.parent._save(
                {
                    **state,
                    "status": "waiting_children"
                    if control["mode"] == "running" and control["budget_open"]
                    else "stopped"
                    if control["mode"] == "stopped"
                    else "paused",
                }
            )
        return {"work": state, "units": self.states()}
