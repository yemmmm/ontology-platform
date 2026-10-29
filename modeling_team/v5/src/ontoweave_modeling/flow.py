"""One bounded business work unit, with references rather than conversation in checkpoints."""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

from .acceptance import require_governed_read, successful_reads
from .contracts import (
    SELF_CHECK_SCHEMA,
    WORK_RESULT_SCHEMA,
    FrameworkError,
    TaskBinding,
    decode_work_result,
    digest,
)
from .control import TaskControl
from .execution import ExecutionManager
from .results import ResultContractError, decode_json_result
from .workspace import WorkspaceRepository


class FlowState(TypedDict, total=False):
    activity: str
    status: str
    round: int
    check_round: int
    binding_ref: dict
    baseline_ref: dict
    execution_ref: dict
    candidate_ref: dict
    operation_ref: dict
    target_ref: dict
    self_check_ref: dict
    handoff_ref: dict
    issue: dict
    semantic_acceptance: str


class WorkUnitFlow:
    def __init__(self, binding: TaskBinding, repository: WorkspaceRepository, bridge, invoke):
        self.binding, self.repository, self.bridge, self.invoke = (
            binding,
            repository,
            bridge,
            invoke,
        )
        self.control = TaskControl(repository)
        self.executions = ExecutionManager(repository, self.control, binding)
        self.work_id = binding.identity + ":work"

    def initialize(self) -> dict:
        binding_ref = self.repository.put_reference(
            self.binding.identity + ":binding",
            "task_binding",
            self.binding.data,
            0,
        )
        prior = self.repository.get(self.work_id)
        if prior:
            if prior["content"]["binding_ref"] != binding_ref:
                raise FrameworkError("binding_changed_or_incompatible")
            return prior["content"]
        return self._save(
            {
                "activity": "prepare",
                "status": "ready",
                "round": 0,
                "binding_ref": binding_ref,
                "semantic_acceptance": "unverified",
            }
        )

    def _save(self, state: dict) -> dict:
        prior = self.repository.get(self.work_id)
        self.repository.put_reference(
            self.work_id, "work_unit", state, prior["revision"] if prior else 0
        )
        return state

    def _fresh(self, state: dict) -> dict:
        # A business record may have committed before its graph checkpoint.
        row = self.repository.get(self.work_id)
        return row["content"] if row else state

    def _host(self, action: str, operation_id: str, payload=None) -> dict:
        unit = self.binding.data["work_unit_id"] + ":platform"
        control = self.control.synchronize()
        if control["mode"] != "running" or not control["budget_open"]:
            raise FrameworkError("task_not_running", control=control["mode"])
        if control["active"].get(unit) != operation_id:
            admitted = self.control.begin_activity(unit, operation_id)
            if not admitted["admitted"]:
                raise FrameworkError("execution_not_admitted", control=admitted)
        result = self.bridge.call(action, payload or {})
        if result.get("status") != "uncertain":
            self.control.finish_turn(unit, operation_id)
        return result

    def _prepare(self, state):
        state = self._fresh(state)
        if state["activity"] != "prepare":
            return state
        baseline = self._host("prepare_scope", "prepare")
        ref = self.repository.put_reference(
            self.binding.identity + ":baseline", "model_reference", baseline, 0
        )
        return self._save({**state, "activity": "model", "baseline_ref": ref})

    def _model(self, state):
        state = self._fresh(state)
        if state["activity"] != "model":
            return state
        prompt = {
            "objective": self.binding.data["objective"],
            "source_manifest": self.binding.data["source_manifest"],
            "actual_baseline": self.repository.read_reference(
                state.get("target_ref", state["baseline_ref"])
            ),
            "feedback": (
                {
                    **state["issue"],
                    "actual": self.repository.read_reference(state["issue"]["operation_ref"]),
                }
                if state.get("issue", {}).get("operation_ref")
                else state.get("issue")
            ),
            "result_schema": WORK_RESULT_SCHEMA,
            "contract": "Return the existing unified graph and explicit r4-3-025 model changes. "
            "Return exactly one JSON object matching result_schema. Read approved sources with "
            "read_material using source_manifest keys as material_id, not filenames or source paths. "
            "actual_baseline.resource_refs contains Host-verified existing_resource_ref objects: "
            "copy their artifact_ref and path exactly when referring to an applied resource. "
            "receipt_item_path is provenance, not a binding-artifact path. The Host resolves these "
            "references; do not try to read artifact_ref with read_mcp_resource or read_material. "
            "Use status proposed when the complete request is ready for Host application; "
            "application is the next program step, not a prerequisite for proposing. Historical "
            "errors or the need for subsequent self-check do not make a ready request recoverable_issue. "
            "Preserve unknowns; never invent business facts. consumed_ids may only contain IDs from "
            "Queued inputs, never material IDs; return [] when that queue is empty. "
            "Execution IDs, platform scope, leases and Batch fields are Host-owned.",
        }
        ref = self.executions.run(
            f"model-{state['round']:05d}", "modeling", json.dumps(prompt), self.invoke
        )
        native = self.repository.read_reference(ref)["result"]
        if native["status"] != "completed":
            return self._save(
                {
                    **state,
                    "status": "recoverable_issue",
                    "round": state["round"] + 1,
                    "issue": {"code": "native_turn_failed", "execution_ref": ref},
                }
            )
        try:
            result = decode_work_result(
                native["final_response"], self.binding.data["source_manifest"]
            )
            if result["status"] == "proposed":
                read_sources = {
                    (args.get("material_id"), data.get("sha256"))
                    for tool, args, data in successful_reads(
                        self.binding.root
                        / "executions"
                        / f"model-{state['round']:05d}"
                        / "agent/events.jsonl"
                    )
                    if tool == "read_material" and "text" in data
                }
                if any(
                    (r["material_id"], r["sha256"]) not in read_sources
                    for r in result["source_refs"]
                ):
                    raise FrameworkError("source_read_missing")
            self.executions.confirm_consumption(ref, result["consumed_ids"])
        except FrameworkError as error:
            return self._save(
                {
                    **state,
                    "round": state["round"] + 1,
                    "execution_ref": ref,
                    "issue": error.as_dict(),
                }
            )
        candidate = self.repository.put_reference(
            f"{self.binding.identity}:candidate:{state['round']}",
            "candidate",
            result,
            0,
        )
        if result["status"] == "recoverable_issue":
            return self._save(
                {
                    **state,
                    "round": state["round"] + 1,
                    "execution_ref": ref,
                    "candidate_ref": candidate,
                    "issue": {"issues": result["issues"]},
                }
            )
        return self._save(
            {
                **state,
                "execution_ref": ref,
                "candidate_ref": candidate,
                "activity": "apply" if result["status"] == "proposed" else "model",
                "status": "ready" if result["status"] == "proposed" else result["status"],
                "issue": {"issues": result["issues"]},
            }
        )

    def _apply(self, state):
        state = self._fresh(state)
        if state["activity"] != "apply":
            return state
        candidate = self.repository.read_reference(state["candidate_ref"])
        operation_id = f"apply-{state['round']:05d}"
        result = self._host(
            "apply",
            operation_id,
            {
                "operation_id": operation_id,
                "candidate": candidate["candidate"],
                "changes": candidate["changes"],
            },
        )
        previous = self.repository.get(self.binding.identity + ":" + operation_id)
        ref = self.repository.put_reference(
            self.binding.identity + ":" + operation_id,
            "application_reference",
            result,
            previous["revision"] if previous else 0,
        )
        if result.get("status") == "uncertain":
            return self._save({**state, "operation_ref": ref, "status": "uncertain"})
        if result.get("status") != "completed":
            target = self._host("snapshot", "snapshot-" + operation_id)
            target_ref = self.repository.put_reference(
                f"{self.binding.identity}:correction-baseline:{state['round']}",
                "model_reference",
                target,
                0,
            )
            return self._save(
                {
                    **state,
                    "activity": "model",
                    "round": state["round"] + 1,
                    "operation_ref": ref,
                    "target_ref": target_ref,
                    "issue": {"code": "application_needs_correction", "operation_ref": ref},
                }
            )
        return self._save({**state, "activity": "self_check", "operation_ref": ref})

    def _self_check(self, state):
        state = self._fresh(state)
        if state["activity"] != "self_check":
            return state
        target = self._host("snapshot", f"snapshot-{state['round']:05d}")
        target_ref = self.repository.put_reference(
            f"{self.binding.identity}:target:{state['round']}:{digest(target)}",
            "model_reference",
            target,
            0,
        )
        prompt = json.dumps(
            {
                "objective": self.binding.data["objective"],
                "actual_target": target,
                "source_manifest": self.binding.data["source_manifest"],
                "feedback": state.get("issue"),
                "instruction": "Read the actual model with query_semantic_context. Check business meaning "
                "against approved sources; a candidate or successful application is not proof. "
                "Return exactly one JSON object matching result_schema: ready, revise or waiting_input. "
                "Describe needed model corrections in issues for the modeling stage; do not include "
                "a draft change request or additional JSON blocks. Do not invent missing information. "
                "consumed_ids may only contain IDs from Queued inputs, never material IDs; "
                "return [] when that queue is empty.",
                "result_schema": SELF_CHECK_SCHEMA,
            }
        )
        execution_id = f"self-check-{state['round']:05d}-{state.get('check_round', 0):03d}"
        ref = self.executions.run(execution_id, "self_check", prompt, self.invoke)
        native = self.repository.read_reference(ref)["result"]
        if native["status"] != "completed":
            return self._save(
                {
                    **state,
                    "status": "recoverable_issue",
                    "check_round": state.get("check_round", 0) + 1,
                    "issue": {"code": "self_check_turn_failed", "execution_ref": ref},
                }
            )
        try:
            result = decode_json_result(native["final_response"], SELF_CHECK_SCHEMA)
            require_governed_read(
                self.binding.root / "executions" / execution_id / "agent/events.jsonl",
                target["model_revisions"],
            )
            self.executions.confirm_consumption(ref, result["consumed_ids"])
        except (ResultContractError, FrameworkError) as error:
            return self._save(
                {
                    **state,
                    "check_round": state.get("check_round", 0) + 1,
                    "issue": {"code": "self_check_needs_correction", "detail": str(error)},
                }
            )
        check_ref = self.repository.put_reference(
            f"{self.binding.identity}:self-check:{state['round']}:{state.get('check_round', 0)}",
            "self_check",
            {
                "result": result,
                "execution_ref": ref,
                "target_ref": target_ref,
            },
            0,
        )
        update = {
            **state,
            "target_ref": target_ref,
            "self_check_ref": check_ref,
            "issue": {"issues": result["issues"]},
        }
        if result["status"] == "revise":
            return self._save({**update, "activity": "model", "round": state["round"] + 1})
        return self._save(
            {
                **update,
                "activity": "handoff" if result["status"] == "ready" else "self_check",
                "status": "ready" if result["status"] == "ready" else "waiting_input",
            }
        )

    def _handoff(self, state):
        state = self._fresh(state)
        if state["activity"] != "handoff":
            return state
        target = self._host("finalize", "finalize")
        if (
            target["model_revisions"]
            != self.repository.read_reference(state["target_ref"])["model_revisions"]
        ):
            raise FrameworkError("frozen_target_changed")
        handoff = {
            "schema_version": "ontoweave-handoff/v1",
            "target": target,
            "binding_digest": digest(self.binding.data),
            "source_manifest_digest": self.binding.data["source_manifest_digest"],
            "source_revisions": {
                key: value["sha256"] for key, value in self.binding.data["source_manifest"].items()
            },
            "evaluation": self.binding.data["evaluation"],
            "semantic_acceptance": "unverified",
        }
        ref = self.repository.put_reference(
            self.binding.identity + ":handoff", "handoff", handoff, 0
        )
        return self._save({**state, "handoff_ref": ref, "status": "handoff_ready"})

    @staticmethod
    def _route(state):
        return state["activity"] if state["status"] == "ready" else END

    def compile(self, checkpointer):
        builder = StateGraph(FlowState)
        builder.add_node("dispatch", lambda state: self._fresh(state))
        builder.add_edge(START, "dispatch")
        names = ("prepare", "model", "apply", "self_check", "handoff")
        builder.add_conditional_edges("dispatch", self._route, [*names, END])
        for name in names:
            builder.add_node(name, getattr(self, "_" + name))
            builder.add_conditional_edges(name, self._route, [*names, END])
        return builder.compile(checkpointer=checkpointer)

    def advance(self, checkpointer) -> dict:
        state = self.initialize()
        if state["status"] in {"handoff_ready", "waiting_input"}:
            return state
        if self.control.synchronize()["mode"] == "stopped":
            return self._save({**state, "status": "stopped"})
        state = self._save({**state, "status": "ready"})
        graph = self.compile(checkpointer)
        config = {
            "configurable": {"thread_id": self.binding.data["run_id"]},
            "recursion_limit": 100,
        }
        try:
            graph.invoke(None if graph.get_state(config).next else state, config)
            return self.repository.get(self.work_id)["content"]
        except FrameworkError as error:
            current = self.repository.get(self.work_id)["content"]
            mode = self.control.view().get("mode", "running")
            status = (
                mode
                if error.code in {"task_not_running", "execution_not_admitted"}
                and mode != "running"
                else "blocked"
            )
            if error.code == "task_not_running" and status == "blocked":
                status = "paused"
            issue = (
                current["issue"]
                if status in {"paused", "stopped"} and current.get("issue")
                else error.as_dict()
            )
            return self._save({**current, "status": status, "issue": issue})
        except GraphRecursionError:
            current = self.repository.get(self.work_id)["content"]
            return self._save(
                {
                    **current,
                    "status": "recoverable_issue",
                    "issue": {"code": "graph_runtime_limit", "recoverable": True},
                }
            )
