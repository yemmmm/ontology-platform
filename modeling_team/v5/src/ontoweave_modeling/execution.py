"""Durable native invocation identity and recovery of completed original results."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

from .contracts import FrameworkError, TaskBinding, digest, safe_id, write_json
from .control import TaskControl
from .workspace import WorkspaceRepository


def completed_native_result(events_path: Path) -> dict | None:
    """Only a terminal turn event proves completion; a dead process does not."""
    if not events_path.exists():
        return None
    messages, thread, turn, final = [], None, None, None
    for line in events_path.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # A truncated final line is not completion proof.
            continue
        method, params = event["method"], event["params"]
        if method == "turn/started":
            thread, turn = params["threadId"], params["turn"]["id"]
            messages, final = [], None
        elif method == "item/completed" and params.get("item", {}).get("type") == "agentMessage":
            messages.append(params["item"]["text"])
        elif method == "turn/completed" and params["turn"]["id"] == turn:
            final = {
                "thread_id": thread,
                "turn_id": turn,
                "status": params["turn"]["status"],
                "error": params["turn"].get("error"),
                "final_response": "\n".join(messages),
            }
    return final


class ExecutionManager:
    def __init__(
        self,
        repository: WorkspaceRepository,
        control: TaskControl,
        binding: TaskBinding,
        *,
        unit_id: str | None = None,
    ):
        self.repository, self.control, self.binding = repository, control, binding
        self.unit_id = unit_id or binding.data["work_unit_id"]

    def run(
        self,
        execution_id: str,
        purpose: str,
        prompt: str,
        invoke: Callable,
        *,
        resume_original: bool = False,
    ) -> dict:
        safe_id(execution_id)
        root = self.binding.root / "executions" / execution_id
        record_id = f"{self.binding.identity}:execution:{execution_id}"
        intent = {"purpose": purpose, "prompt_digest": digest(prompt), "execution_id": execution_id}
        prior = self.repository.get(record_id)
        if prior and resume_original and prior["content"]["intent"]["purpose"] == purpose:
            prompt = prior["content"].get("prompt", prompt)
            intent["prompt_digest"] = digest(prompt)
        if prior and prior["content"]["intent"] != intent:
            raise FrameworkError("execution_intent_conflict")
        if prior:
            receipt_path = root / "result.json"
            result = (
                json.loads(receipt_path.read_text())
                if receipt_path.exists()
                else completed_native_result(root / "agent" / "events.jsonl")
            )
            if result is None:
                raise FrameworkError(
                    "reconciliation_required",
                    layer="runtime/infrastructure",
                    execution_id=execution_id,
                )
        else:
            admission = self.control.begin_activity(
                self.unit_id,
                execution_id,
                deliver_inputs=purpose != "acceptance",
                input_phase="self_check" if purpose == "self_check" else "model",
                input_run_id=self.binding.data["run_id"],
            )
            if not admission["admitted"]:
                raise FrameworkError("execution_not_admitted", control=admission)
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.repository.put_reference(
                record_id,
                "execution",
                {
                    "intent": intent,
                    "prompt": prompt,
                    "state": "dispatching",
                    "owner_pid": os.getpid(),
                    "inputs": admission["inputs"],
                },
                0,
            )
            # Once dispatching is durable, an exception preserves active/unknown state.
            result = invoke(root, purpose, prompt, admission["inputs"])
        if result.get("status") not in {"completed", "failed", "interrupted"}:
            raise FrameworkError("native_result_not_terminal", layer="runtime/infrastructure")
        write_json(root / "result.json", result)
        active = self.control.view()["active"]
        if active.get(self.unit_id) == execution_id:
            # Consumption is confirmed separately, after the purpose-specific schema is valid.
            self.control.finish_turn(self.unit_id, execution_id)
        current = self.repository.get(record_id)
        if current["content"]["state"] == "finished":
            return {
                "object_id": record_id,
                "revision": current["revision"],
                "digest": digest(current["content"]),
            }
        return self.repository.put_reference(
            record_id,
            "execution",
            {
                **current["content"],
                "state": "finished",
                "result": result,
            },
            current["revision"],
        )

    def confirm_consumption(self, execution_ref: dict, consumed_ids: list[str]) -> None:
        execution = self.repository.read_reference(execution_ref)
        delivered = {item["id"] for item in execution["inputs"]}
        if not set(consumed_ids).issubset(delivered):
            raise FrameworkError("input_consumption_mismatch")
        if not consumed_ids:
            return

        def change(state):
            for message in state["messages"]:
                if message["id"] not in consumed_ids:
                    continue
                if message.get("execution_id") != execution["intent"]["execution_id"] or message[
                    "status"
                ] not in {"delivered", "consumed"}:
                    raise FrameworkError("input_consumption_mismatch")
                message["status"] = "consumed"

        self.control._change(change)


class CodexInvocation:
    """Concrete Codex/tool loop; graph and budget decisions stay with the Host."""

    def __init__(
        self,
        binding: TaskBinding,
        bridge,
        *,
        materials: Path | None = None,
        instructions: str | None = None,
        model_revisions: dict | None = None,
    ):
        self.binding, self.bridge = binding, bridge
        self.materials = materials or binding.root / "materials"
        self.instructions = instructions or binding.data["instructions"]
        self.model_revisions = model_revisions

    def __call__(self, root: Path, purpose: str, prompt: str, inputs: list) -> dict:
        from .codex_agent import CodexAgent

        role = "acceptance" if purpose == "acceptance" else "modeling"
        tools = ("read_material", "query_semantic_context")
        read_payload = {"role": role}
        if self.model_revisions is not None:
            read_payload["model_revisions"] = self.model_revisions
        read_config = self.bridge.call("read_config", read_payload)["config_ref"]
        with self.bridge.provider(root.name, role, tools) as url:

            def observe(method, params):
                if method == "thread/tokenUsage/updated":
                    with (root / "usage.jsonl").open("a") as stream:
                        stream.write(json.dumps({"method": method, "params": params}) + "\n")

            agent = CodexAgent(
                root / "agent",
                self.binding.model(role),
                provider_base_url=url,
                materials=self.materials,
                platform_config=Path(read_config),
                instructions=self.instructions,
                on_event=observe,
                allowed_tools=tools,
            )
            try:
                agent.start()
                return agent.run_turn(prompt + "\nQueued inputs: " + json.dumps(inputs))
            finally:
                agent.close()
