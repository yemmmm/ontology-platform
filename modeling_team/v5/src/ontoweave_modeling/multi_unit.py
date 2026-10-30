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
            prior = self.repository.get(flow.work_id)
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
                    }
                )
            self.flows[binding.actor] = flow
        self.parent = self.flows["modeling"]
        self.children = [f for actor, f in self.flows.items() if actor != "modeling"]

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
        self.bridge.call("read_config", {"role": "modeling"})
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
                    for actor, flow in self.flows.items():
                        state = states[actor]
                        phase = state.get("resume_activity", "model")
                        incoming = {m["id"] for m in flow.human.pending(phase)}
                        marker = (flow.binding.data.get("work_generation", 0), frozenset(incoming))
                        if (
                            actor in busy
                            or seen.get(actor) == marker
                            or state["status"] == "handoff_ready"
                        ):
                            continue
                        if state["status"] in {"proposal_ready", "waiting_input"} and not incoming:
                            continue
                        unit = next(
                            (u for u in self.binding.data["work_units"] if u["unit_id"] == actor),
                            {},
                        )
                        dependencies = unit.get("dependencies", [])
                        children = flow.binding.direct_units
                        if (
                            children
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
