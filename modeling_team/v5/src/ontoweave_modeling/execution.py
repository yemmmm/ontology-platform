"""Durable native invocation identity and recovery of completed original results."""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .budget import synchronize_budget
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
        execution_id = self.binding.execution_id(execution_id)
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
            synchronize_budget(
                self.binding,
                self.control,
                role="acceptance" if purpose == "acceptance" else "modeling",
            )
            admission = self.control.begin_activity(
                self.unit_id,
                execution_id,
                deliver_inputs=purpose not in {"acceptance", "overview"},
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
        attempts_path = root / "provider-usage.jsonl"
        attempts = (
            (json.loads(line) for line in attempts_path.read_text().splitlines())
            if attempts_path.exists()
            else ()
        )
        limited = next((attempt for attempt in attempts if attempt.get("http_status") == 429), None)
        if limited:
            # This user-authorized run must stop at provider allowance exhaustion.
            # HTTP 429 alone does not prove the provider's exact window or reset time.
            write_json(
                self.binding.root / "provider-limit.json",
                {
                    "execution_id": execution_id,
                    "http_status": 429,
                    "request_id": limited.get("request_id"),
                    "window_attribution": "unknown",
                    "action": "pause_at_natural_boundary; Host must inspect before another call",
                },
            )
            self.control.enqueue(
                "provider-limit:" + execution_id,
                "pause",
                metadata={"source": "provider", "code": "provider_limit"},
            )
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
        reference = self.repository.put_reference(
            record_id,
            "execution",
            {
                **current["content"],
                "state": "finished",
                "result": result,
            },
            current["revision"],
        )
        synchronize_budget(self.binding, self.control)
        return reference

    def confirm_consumption(self, execution_ref: dict, consumed_ids: list[str]) -> None:
        execution = self.repository.read_reference(execution_ref)
        delivered = {item["id"] for item in execution["inputs"]}
        if not set(consumed_ids).issubset(delivered):
            raise FrameworkError(
                "input_consumption_mismatch",
                allowed_ids=sorted(delivered),
                unexpected_ids=sorted(set(consumed_ids) - delivered),
            )
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
        read_only: bool = False,
        resume_from: Path | None = None,
    ):
        self.binding, self.bridge = binding, bridge
        self.materials = materials or binding.materials
        self.instructions = instructions or binding.data["instructions"]
        self.model_revisions = model_revisions
        self.read_only = read_only
        self.resume_from = resume_from

    def __call__(self, root: Path, purpose: str, prompt: str, inputs: list) -> dict:
        from .codex_agent import CodexAgent
        from .memory import MEMORY_TOOLS
        from .semantic_workspace import WORKSPACE_TOOLS
        from .team import TEAM_TOOLS
        from .work_plan import WORK_TOOLS

        role = "acceptance" if purpose == "acceptance" else "modeling"
        tools = ("read_material", "query_semantic_context", "read_model_resource")
        team_config = None
        instructions = self.instructions
        if (
            role == "modeling"
            and not self.read_only
            and (
                self.binding.data.get("collaboration")
                or self.binding.data.get("shared_memory")
                or self.binding.data.get("work_units")
                or self.binding.data.get("work_management")
                or self.binding.data.get("semantic_workspace")
            )
        ):
            if (
                self.binding.data.get("collaboration")
                or self.binding.data.get("work_units")
                or self.binding.data.get("work_management")
            ):
                tools += TEAM_TOOLS
            if self.binding.data.get("work_units") or self.binding.data.get("work_management"):
                tools += WORK_TOOLS
            if self.binding.data.get("shared_memory"):
                tools += MEMORY_TOOLS
            if self.binding.data.get("semantic_workspace"):
                tools += WORKSPACE_TOOLS
            private = json.loads((self.binding.root / "private-runtime.json").read_text())
            connection = dict(private["connection"])
            # Reuse the verified P0 workspace route: resolve before entering the namespace.
            connection.setdefault("hostaddr", socket.gethostbyname(connection["host"]))
            team_config = root / "team-private.json"
            team_config.write_text(
                json.dumps(
                    {
                        "task": self.binding.data,
                        "connection": connection,
                        "schema": private["workspace_schema"],
                        "actor": purpose.removeprefix("peer:")
                        if purpose.startswith("peer:")
                        else self.binding.actor,
                    }
                )
            )
            if (
                self.binding.data.get("collaboration")
                or self.binding.data.get("work_units")
                or self.binding.data.get("work_management")
            ):
                instructions += (
                    "\nUse team tools for signed work cards, peer messages and frozen materials. "
                    "Queued is not read. Ordinary text and material refs are separate. "
                    "Read received materials with read_handoff_material only as needed; "
                    "peer analysis is attributed interpretation, not a new approved business fact. "
                    "Update your card at meaningful changes, not every tool call. "
                    "To await a peer, return waiting_peer; never ask the human to forward peer messages."
                    " On a persistent infrastructure tool error, end this turn with recoverable_issue "
                    "and the exact blocker; repeated identical tool retries cannot repair Host infrastructure."
                )
            if self.binding.data.get("work_units") or self.binding.data.get("work_management"):
                instructions += (
                    " Use delegate_work to create bounded direct children only when useful. "
                    "They may delegate further. Keep unallocated scope and overall rules in your own work. "
                    "After delegation return waiting_children with null candidate/changes; "
                    "on reentry use get_work_tree and read direct child results as needed. "
                    "get_work_tree shows only one parent's direct children; use parent_id to "
                    "inspect another level. A unit absent from this page may exist below a child. "
                    "Only the root applies; child proposals are not final acceptance. "
                    "Use reopen_work_unit for explicit rework; ordinary notifications do not require "
                    "recreating a finished proposal."
                )
            if self.binding.is_child and purpose == "modeling":
                instructions += (
                    " You own this child work unit only. Return its source-grounded proposed "
                    "business candidate for the parent to integrate; changes may be null because "
                    "you do not apply. candidate may hold bounded propositions/definitions. "
                    "The program will publish your complete "
                    "result as a versioned handoff material. Do not claim application or full-task "
                    "completion. Ask missing business input using the supplied HITL result contract."
                )
            if purpose.startswith("peer:"):
                instructions = (
                    "You are a bounded production peer, not an independent evaluator. "
                    "Use the objective, approved sources and actual queued messages. "
                    "Use team tools to maintain your own card, read received frozen materials by range, "
                    "and send an attributed result to the requester, using reply_to. "
                    "Do not apply models or invent business facts. Return exactly the supplied peer "
                    "result schema, not a modeling change object. consumed_ids contains only "
                    "Queued inputs[].id; never material_refs[].object_id or outgoing message IDs. "
                    "read_material uses source_manifest keys as material_id, never a source_ref. "
                    "Your card accepts current_work, scope, next_steps, waiting_note, result_refs; "
                    "omit author and agent_id because the tool binds identity. "
                    "Only the request originator resolves it; the recipient sends a reply instead. "
                    "If a persistent infrastructure/tool-contract problem prevents progress, return "
                    "recoverable_issue with exact issues, preserving unconsumed inputs for repair. "
                    "No required accept/confirm handshake."
                )
            if self.binding.data.get("shared_memory"):
                instructions += (
                    " Shared task business memory is enabled. Use write_memory for judgments, "
                    "decisions and open items (entry_id, kind, title, body, source_refs). "
                    "For an unknown entry ID use search_memory by text, then read_memory for "
                    "the complete record. To update use the read revision as top-level "
                    "expected_revision. A conflict returns actual content for your merge; "
                    "preserve valid prior conditions and exceptions. These are attributed "
                    "business notes, not an applied model or new human approval."
                )
            if self.binding.data.get("semantic_workspace"):
                instructions += (
                    " Use get_modeling_context at a new context to locate persistent records. "
                    "Use write_semantic_record for complete propositions, interpretations, identity/reuse "
                    "decisions, definitions, coverage, open items and summaries. Keep source refs and "
                    "exact depends_on references; keep review, cognition, expression, work and applicability "
                    "separate. Application and independent acceptance are Host observations, not note states. "
                    "Summaries navigate to originals; stale/needs_review content is not current confirmation. "
                    "Freshness checks declared dependencies only; after a shared meaning changes, "
                    "search relevant semantic users too, including current notes with an omitted dependency. "
                    "get_modeling_context reports the actual bound project_ref; use scope=project for "
                    "shared project records when available, otherwise scope=task. "
                    "Preserve conditions, exceptions, negation, modality and unknowns, including unallocated scope. "
                    "When the actual existing model already satisfies the source, return no_change with null "
                    "candidate/changes and source_refs; the program still performs actual governed self-check."
                )
        if purpose == "self_check":
            scope = (
                "this original child's assigned scope"
                if self.binding.is_child
                else "the complete root objective"
            )
            instructions += (
                f" You are checking {scope} against actual applied evidence now, not proposing. "
                "Return only the supplied self-check result with ready, revise or waiting_input; "
                "never proposed, candidate or changes. Necessary edits belong in issues with revise "
                "for the next modeling stage. Queued authoring guidance does not change this phase. "
                "This is production read-back, not independent acceptance."
            )
        native_requested = False
        try:
            read_payload = {"role": role}
            if self.model_revisions is not None:
                read_payload["model_revisions"] = self.model_revisions
            read_config = self.bridge.call("read_config", read_payload)["config_ref"]
            if self.resume_from is not None:
                usage_path = self.resume_from.parent / "usage.jsonl"
                samples = usage_path.read_text().splitlines() if usage_path.exists() else []
                if samples:
                    sample = json.loads(samples[-1])["params"]
                    write_json(
                        root / "native-usage-baseline.json",
                        {
                            "thread_id": sample["threadId"],
                            "total": sample["tokenUsage"]["total"],
                            "source_execution": self.resume_from.parent.name,
                            "evidence_ref": str(usage_path),
                        },
                    )
                elif self.binding.data["authorization"]["mode"] == "amount":
                    raise FrameworkError("resume_usage_baseline_missing")
            if self.binding.data["authorization"]["mode"] == "amount":
                (root / "budget-native-usage.jsonl").touch(exist_ok=True)
            with self.bridge.provider(root.name, role, tools) as url:

                def observe(method, params):
                    if method == "thread/tokenUsage/updated":
                        with (root / "usage.jsonl").open("a") as stream:
                            stream.write(json.dumps({"method": method, "params": params}) + "\n")
                        if self.binding.data["authorization"]["mode"] == "amount":
                            with (root / "budget-native-usage.jsonl").open("a") as stream:
                                stream.write(
                                    json.dumps(
                                        {
                                            "event": "thread_usage",
                                            "thread_id": params["threadId"],
                                            "runtime_session_id": params["threadId"],
                                            "turn_id": params["turnId"],
                                            "total": params["tokenUsage"]["total"],
                                            "received_at": datetime.now(UTC).isoformat(),
                                        }
                                    )
                                    + "\n"
                                )

                resume_options = {"resume_from": self.resume_from} if self.resume_from else {}
                agent = CodexAgent(
                    root / "agent",
                    self.binding.model(role),
                    provider_base_url=url,
                    materials=self.materials,
                    platform_config=Path(read_config),
                    team_config=team_config,
                    instructions=instructions,
                    on_event=observe,
                    allowed_tools=tools,
                    **resume_options,
                )
                try:
                    if self.resume_from:
                        agent.start(resume=True)
                    else:
                        agent.start()
                    native_requested = True
                    return agent.run_turn(prompt + "\nQueued inputs: " + json.dumps(inputs))
                finally:
                    agent.close()
        except Exception as error:
            if native_requested:
                raise
            result = {
                "status": "failed",
                "thread_id": None,
                "turn_id": None,
                "native_start_requested": False,
                "normal_pause": False,
                "error": {
                    "code": "native_dispatch_failed",
                    "layer": "runtime/infrastructure",
                    "cause": error.as_dict()
                    if isinstance(error, FrameworkError)
                    else {"type": type(error).__name__},
                },
                "final_response": "",
            }
            write_json(root / "result.json", result)
            return result
