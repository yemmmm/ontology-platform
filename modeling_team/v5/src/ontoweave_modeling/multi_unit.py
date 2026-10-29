"""Independent child checkpoints, followed by a parent-owned model application."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from .execution import CodexInvocation
from .flow import WorkUnitFlow


class MultiUnitFlow:
    def __init__(self, binding, repository, bridge, checkpoint_schema, invoke_factory=None):
        self.binding, self.repository, self.bridge = binding, repository, bridge
        self.checkpoint_schema = checkpoint_schema
        self.invoke_factory = invoke_factory or (lambda selected: CodexInvocation(selected, bridge))
        self.parent = WorkUnitFlow(binding, repository, bridge, self.invoke_factory(binding))
        self.children = [
            WorkUnitFlow(selected, repository, bridge, self.invoke_factory(selected))
            for unit in binding.data["work_units"]
            if (selected := binding.for_unit(unit["unit_id"]))
        ]

    def initialize(self):
        state = self.parent.initialize()
        for child in self.children:
            child.initialize()
        return state

    def states(self):
        return {
            child.binding.data["work_unit_id"]: self.repository.get(child.work_id)["content"]
            for child in self.children
        }

    def advance(self):
        state = self.initialize()
        if state["status"] == "handoff_ready":
            return {"work": state, "units": self.states()}
        if state["activity"] == "prepare":
            state = self.parent._prepare(state)
        # Shared scope/read key and checkpointer DDL are prepared once, before concurrent children.
        self.bridge.call("read_config", {"role": "modeling"})
        with self.repository.checkpointer(self.checkpoint_schema):
            pass

        def advance_child(child):
            with self.repository.checkpointer(self.checkpoint_schema) as saver:
                return child.advance(saver)

        states = self.states()
        pending = [
            child
            for child in self.children
            if states[child.binding.data["work_unit_id"]]["status"] != "proposal_ready"
            or child.human.pending("model")
        ]
        with ThreadPoolExecutor(max_workers=self.binding.data.get("unit_concurrency", 2)) as pool:
            seen_inputs = {child.binding.actor: set() for child in self.children}

            def submit(child):
                phase = self.repository.get(child.work_id)["content"].get(
                    "resume_activity", "model"
                )
                seen_inputs[child.binding.actor].update(m["id"] for m in child.human.pending(phase))
                return pool.submit(advance_child, child)

            running = {submit(child): child for child in pending}
            while running:
                completed, _ = wait(running, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in completed:
                    future.result()
                    del running[future]
                control = self.parent.control.view()
                if control.get("mode") == "running" and control.get("budget_open", True):
                    active_units = {child.binding.actor for child in running.values()}
                    for child in self.children:
                        phase = self.repository.get(child.work_id)["content"].get(
                            "resume_activity", "model"
                        )
                        incoming = {m["id"] for m in child.human.pending(phase)}
                        if (
                            child.binding.actor not in active_units
                            and incoming - seen_inputs[child.binding.actor]
                        ):
                            running[submit(child)] = child
        states = self.states()
        if all(unit["status"] == "proposal_ready" for unit in states.values()):
            with self.repository.checkpointer(self.checkpoint_schema) as saver:
                state = self.parent.advance(saver)
        else:
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
        return {"work": state, "units": states}
