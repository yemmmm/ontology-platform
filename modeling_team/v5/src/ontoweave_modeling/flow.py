"""One bounded business work unit, with references rather than conversation in checkpoints."""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .acceptance import require_governed_read, successful_reads
from .budget import synchronize_budget
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
from .human_input import HumanInput
from .results import ResultContractError, decode_json_result
from .semantic_workspace import SemanticWorkspace
from .team import TeamChannel
from .unit_checks import check_unit, pending_check_units
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
    resume_activity: str
    human_request_ids: list[str]
    refresh_baseline: bool
    peer_round: int
    peer_next: str
    work_generation: int
    candidate_basis_ref: dict


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
        self.human = HumanInput(binding, repository, self.control)
        self.team = TeamChannel(binding.data, repository, self.control, binding.actor)
        self.work_id = binding.identity + ":work"

    def initialize(self) -> dict:
        binding_ref = self.repository.put_reference(
            self.binding.identity + ":binding:" + digest(self.binding.data),
            "task_binding",
            self.binding.data,
            0,
        )
        prior = self.repository.get(self.work_id)
        if prior:
            if prior["content"]["binding_ref"] != binding_ref:
                original = self.repository.read_reference(prior["content"]["binding_ref"])
                fixed = (
                    "task_ref",
                    "run_id",
                    "models",
                    "profile_sha256",
                    "authorization",
                    "scope",
                    "project_ref",
                    "workspace_ref",
                )
                if any(original.get(key) != self.binding.data.get(key) for key in fixed):
                    raise FrameworkError("binding_changed_or_incompatible")
                return self._save({**prior["content"], "binding_ref": binding_ref})
            return prior["content"]
        return self._save(
            {
                "activity": "prepare",
                "status": "ready",
                "round": 0,
                "binding_ref": binding_ref,
                "semantic_acceptance": "unverified",
                "work_generation": self.binding.data.get("work_generation", 0),
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
        synchronize_budget(self.binding, self.control)
        control = self.control.synchronize()
        if control["mode"] != "running" or not control["budget_open"]:
            raise FrameworkError("task_not_running", control=control["mode"])
        if control["active"].get(unit) != operation_id:
            admitted = self.control.begin_activity(unit, operation_id)
            if not admitted["admitted"]:
                raise FrameworkError("execution_not_admitted", control=admitted)
        result = self.bridge.call(action, payload or {})
        if result.get("project_id"):
            self.repository.put_reference(
                "run:" + self.binding.data["run_id"] + ":project-binding",
                "project_binding",
                {"project_id": result["project_id"]},
                0,
            )
        if self.binding.data.get("semantic_workspace") and "model_revisions" in result:
            from .semantic_workspace import SemanticWorkspace

            SemanticWorkspace(self.repository, self.binding.data).observe_models(
                result["model_revisions"]
            )
        if result.get("status") != "uncertain":
            self.control.finish_turn(unit, operation_id)
        return result

    def _prepare(self, state):
        state = self._fresh(state)
        if state["activity"] != "prepare":
            return state
        baseline = self._host("snapshot" if self.binding.is_child else "prepare_scope", "prepare")
        ref = self.repository.put_reference(
            self.binding.identity + ":baseline", "model_reference", baseline, 0
        )
        return self._save({**state, "activity": "model", "baseline_ref": ref})

    def _pending_children(self):
        plan = self.repository.get("run:" + self.binding.data["run_id"] + ":work-plan")
        if not plan:
            return []
        return [
            unit["unit_id"]
            for unit in plan["content"]["units"].values()
            if unit["parent_id"] == self.binding.actor
            and unit["status"] == "active"
            and (
                not (
                    work := self.repository.get(
                        "run:" + self.binding.data["run_id"] + ":unit:" + unit["unit_id"] + ":work"
                    )
                )
                or work["content"]["status"] != "proposal_ready"
            )
        ]

    def _model(self, state):
        state = self._fresh(state)
        if state["activity"] != "model":
            return state
        if any(self.team.pending(actor) for actor in self.team.peers):
            return self._save(
                {**state, "activity": "collaborate", "peer_next": "model", "status": "ready"}
            )
        if state.get("refresh_baseline"):
            target = self._host("snapshot", f"human-baseline-{state['round']:05d}")
            target_ref = self.repository.put_reference(
                f"{self.binding.identity}:human-baseline:{digest(target)}",
                "model_reference",
                target,
                0,
            )
            state = self._save({**state, "target_ref": target_ref, "refresh_baseline": False})
        local_execution = f"model-{state['round']:05d}"
        if (
            state.get("issue", {}).get("code")
            in {"unresolved_reason_required", "model_changes_required", "work_result_invalid"}
            and state["round"]
        ):
            previous = f"model-{state['round'] - 1:05d}"
            path = (
                self.binding.root
                / "executions"
                / self.binding.execution_id(previous)
                / "result.json"
            )
            if path.exists():
                original = json.loads(path.read_text())
                try:
                    decode_work_result(
                        original["final_response"],
                        self.binding.data["source_manifest"],
                        require_changes=not self.binding.is_child,
                    )
                except FrameworkError:
                    pass
                else:
                    local_execution = previous
        previous_proposal = None
        if state.get("candidate_ref"):
            previous = self.repository.read_reference(state["candidate_ref"])
            if (
                self.binding.data.get("collaboration")
                or self.binding.data.get("work_units")
                or self.binding.data.get("work_management")
            ):
                previous_proposal = {
                    "material_ref": self.team.publish(
                        "previous-" + digest(state["candidate_ref"])[:24],
                        text=json.dumps(previous, ensure_ascii=False),
                    ),
                    "instruction": "Read this exact previous result using read_handoff_material and correct it against feedback. Preserve technical fixes already made; reassess business content against current sources and baseline.",
                }
            else:
                previous_proposal = {"content": previous}
        prompt = {
            "objective": self.binding.data["objective"],
            "previous_proposal": previous_proposal,
            "source_manifest": self.binding.data["source_manifest"],
            "assigned_material_ids": self.binding.data.get("assigned_material_ids", []),
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
            "previous_local_check": self.repository.read_reference(state["local_self_check_ref"])
            if state.get("local_self_check_ref")
            else None,
            "result_schema": WORK_RESULT_SCHEMA,
            "human_context": self.human.context(),
            "team_members": sorted(self.team.members),
            "child_results": [
                {
                    "unit_id": unit["unit_id"],
                    "objective": unit["objective"],
                    "material_ref": row["content"].get("result_material_ref"),
                    "status": row["content"]["status"],
                    "check_material_ref": row["content"].get("check_material_ref"),
                }
                for unit in self.binding.direct_units
                if (
                    row := self.repository.get(
                        self.binding.for_unit(unit["unit_id"]).identity + ":work"
                    )
                )
            ],
            "contract": "Return the existing unified graph and explicit r4-3-025 model changes. "
            "For every create select exactly ONE source: candidate item_id with fields=null, "
            "OR fields with item_id=null. Never set both; do not copy candidate content into fields "
            "while keeping its item_id. Child candidates are attributed proposals, not automatically "
            "valid platform requests; translate their business meaning into the actual attached contract. "
            "If candidate.business_meaning repeats semantic_definition.business_meaning, keep "
            "the same complete string in both; these two slots merge into one output field. "
            "Return exactly one JSON object matching result_schema. Read approved sources with "
            "read_material using source_manifest keys as material_id, not filenames or source paths. "
            "Every source_refs entry must match a read_material read in this native turn; "
            "earlier reads or unchanged source versions do not count for that declaration. "
            "Cite only the exact materials actually read here. "
            "When incorporating ready direct-child meanings, declare needed original-owner "
            "actual-model checks in review_units. They run after application/no_change and "
            "before your overall self-check; only select incorporated, ready direct children. "
            "actual_baseline.resource_refs contains Host-verified existing_resource_ref objects: "
            "copy their artifact_ref and path exactly when referring to an applied resource. "
            "For an existing resource read from the governed model, you may use an existing_resource_ref "
            "with artifact_ref='model-read:<family>:<ontology_id>' and path='/' plus its exact returned IRI. "
            "Families are class-detail, property-list, relation-type-list or entity-detail; the Host "
            "verifies the scoped native read and obtains its actual identity. Never derive a native ID from an IRI. "
            "receipt_item_path is provenance, not a binding-artifact path. The Host resolves these "
            "references; do not try to read artifact_ref with read_mcp_resource or read_material. "
            "Use status proposed when the complete request is ready for Host application; "
            "application is the next program step, not a prerequisite for proposing. Historical "
            "errors or the need for subsequent self-check do not make a ready request recoverable_issue. "
            "Preserve unknowns; never invent business facts. consumed_ids may only contain IDs from "
            "Queued inputs, never material IDs; return [] when that queue is empty. "
            "Execution IDs, platform scope, leases and Batch fields are Host-owned.",
            "placement_contract": "The actual baseline lists authorized ontology_ids. In a multi-Ontology scope, "
            "return ontology_targets mapping each create change_id to its chosen actual authorized ontology_id. "
            "Existing updates can inherit placement from their verified target_ref. "
            "Work units do not determine Ontology placement; never invent or derive ontology IDs.",
            "human_input_contract": "When required business information is missing, return "
            "waiting_input with human_requests containing question, reason and impact. "
            "Questions are persisted and shown directly to the user after this native turn. "
            "Use prior human_context answers as attributed business input, not platform facts. "
            "Acknowledge only supplied Queued input IDs in consumed_ids. Explicitly list a request "
            "in resolved_request_ids only when its consumed non-partial reply actually resolves it. "
            "Partial replies do not resolve a whole request. Preserve other pending questions; "
            "If no actual human questions were supplied, return resolved_request_ids=[]; "
            "proactive technical input IDs belong only in consumed_ids. "
            "resolved_request_ids contains human HITL IDs only. Team work requests use the "
            "resolve_work_request tool and must not be included in this result field. "
            "do not repeat an unchanged pending question. Reassess old replies against the actual baseline.",
        }
        ref = self.executions.run(
            local_execution,
            "modeling",
            json.dumps(prompt),
            self.invoke,
            resume_original=True,
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
                native["final_response"],
                self.binding.data["source_manifest"],
                require_changes=not self.binding.is_child,
            )
            if result["status"] in {"proposed", "no_change"}:
                read_sources = {
                    (args.get("material_id"), data.get("sha256"))
                    for tool, args, data in successful_reads(
                        self.binding.root
                        / "executions"
                        / self.binding.execution_id(local_execution)
                        / "agent/events.jsonl"
                    )
                    if tool == "read_material" and "text" in data
                }
                missing_sources = sorted(
                    {
                        r["material_id"]
                        for r in result["source_refs"]
                        if (r["material_id"], r["sha256"]) not in read_sources
                    }
                )
                if missing_sources:
                    raise FrameworkError("source_read_missing", material_ids=missing_sources)
            if set(result.get("review_units", [])) - {
                unit["unit_id"] for unit in self.binding.direct_units
            }:
                raise FrameworkError("unit_check_scope_forbidden")
            self._confirm_inputs(ref, result)
        except FrameworkError as error:
            return self._save(
                {
                    **state,
                    "round": state["round"] + 1,
                    "execution_ref": ref,
                    "issue": error.as_dict(),
                }
            )
        pending_children = self._pending_children()
        if self.binding.is_child and pending_children and result["status"] == "proposed":
            result = {
                **result,
                "status": "waiting_children",
                "issues": [
                    *result["issues"],
                    "Await direct children: " + ", ".join(pending_children),
                ],
            }
        candidate = self.repository.put_reference(
            f"{self.binding.identity}:candidate:{state['round']}",
            "candidate",
            result,
            0,
        )
        if result["status"] == "waiting_children":
            return self._save(
                {
                    **state,
                    "status": "waiting_children" if pending_children else "ready",
                    "activity": "model",
                    "round": state["round"] + 1,
                    "execution_ref": ref,
                    "candidate_ref": candidate,
                    "issue": {
                        "issues": result["issues"],
                        "instruction": "Integrate ready direct child results or delegate remaining scope; no unfinished direct children remain."
                        if not pending_children
                        else "Await direct child results.",
                    },
                }
            )
        if self.binding.is_child and result["status"] in {"proposed", "no_change"}:
            material = self.team.publish(
                "result-" + digest(candidate)[:24], text=json.dumps(result, ensure_ascii=False)
            )
            self.team.send(
                self.binding.data.get("_parent_actor", "modeling"),
                "Child proposal is ready for parent semantic integration.",
                "result-" + digest(candidate)[:24],
                material_refs=[material],
            )
            return self._save(
                {
                    **state,
                    "status": "proposal_ready",
                    "candidate_ref": candidate,
                    "execution_ref": ref,
                    "result_material_ref": material,
                    "issue": {"issues": result["issues"]},
                }
            )
        if result["status"] == "waiting_input":
            waiting = self._wait_for_human(
                {
                    **state,
                    "candidate_ref": candidate,
                    "execution_ref": ref,
                    "round": state["round"] + 1,
                    "issue": {"issues": result["issues"]},
                },
                "model",
                result,
                ref,
                state.get("target_ref", state["baseline_ref"]),
            )
            if any(self.team.pending(actor) for actor in self.team.peers):
                return self._save(
                    {
                        **waiting,
                        "activity": "collaborate",
                        "status": "ready",
                        "peer_next": "wait_input",
                    }
                )
            return waiting
        if result["status"] == "waiting_peer" or any(
            self.team.pending(actor) for actor in self.team.peers
        ):
            return self._save(
                {
                    **state,
                    "activity": "collaborate",
                    "status": "ready",
                    "round": state["round"] + 1,
                    "candidate_ref": candidate,
                    "execution_ref": ref,
                    "peer_next": "apply" if result["status"] == "proposed" else "model",
                    "issue": {"issues": result["issues"]},
                }
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
                "candidate_basis_ref": state.get("target_ref", state["baseline_ref"]),
                "activity": "apply"
                if result["status"] == "proposed"
                else "self_check"
                if result["status"] == "no_change"
                else "model",
                "status": "ready"
                if result["status"] in {"proposed", "no_change"}
                else result["status"],
                "issue": {"issues": result["issues"]},
            }
        )

    def _collaborate(self, state):
        state = self._fresh(state)
        pending = [actor for actor in self.team.peers if self.team.pending(actor)]
        if not pending:
            next_activity = state.get("peer_next", "model")
            if next_activity == "wait_input":
                return self._save({**state, "activity": "wait_input", "status": "waiting_input"})
            if self.team.pending(self.binding.actor) or self.human.pending(
                "self_check" if next_activity == "self_check" else "model"
            ):
                next_activity = "self_check" if next_activity == "self_check" else "model"
            elif next_activity == "model":
                return self._save({**state, "status": "waiting_peer"})
            return self._save({**state, "activity": next_activity, "status": "ready"})
        actor = pending[0]
        execution_id = f"peer-{actor}-{state.get('peer_round', 0):05d}"
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {"enum": ["ready", "waiting_peer", "recoverable_issue"]},
                "issues": {"type": "array", "items": {"type": "string"}},
                "consumed_ids": WORK_RESULT_SCHEMA["properties"]["consumed_ids"],
            },
            "required": ["status", "issues", "consumed_ids"],
        }
        reuse_result = False
        if state.get("issue", {}).get("code") == "peer_result_needs_correction" and state.get(
            "peer_round"
        ):
            previous_id = f"peer-{actor}-{state['peer_round'] - 1:05d}"
            previous_path = (
                self.binding.root
                / "executions"
                / self.binding.execution_id(previous_id)
                / "result.json"
            )
            if previous_path.exists():
                previous = json.loads(previous_path.read_text())
                try:
                    decode_json_result(previous["final_response"], schema)
                except ResultContractError:
                    pass
                else:
                    execution_id, reuse_result = previous_id, True
        prompt = json.dumps(
            {
                "objective": self.team.peers[actor]["objective"],
                "source_manifest": self.binding.data["source_manifest"],
                "team_members": sorted(self.team.members),
                "actor_id": actor,
                "feedback": state.get("issue"),
                "result_schema": schema,
            }
        )
        manager = ExecutionManager(
            self.repository, self.control, self.binding, unit_id=self.team.unit(actor)
        )
        ref = manager.run(execution_id, "peer:" + actor, prompt, self.invoke, resume_original=True)
        native = self.repository.read_reference(ref)["result"]
        update = {**state, "peer_round": state.get("peer_round", 0) + (not reuse_result)}
        try:
            if native["status"] != "completed":
                raise FrameworkError("peer_turn_failed", layer="runtime/infrastructure")
            result = decode_json_result(native["final_response"], schema)
            if result["status"] == "recoverable_issue":
                return self._save(
                    {
                        **update,
                        "status": "recoverable_issue",
                        "issue": {"code": "peer_runtime_issue", "issues": result["issues"]},
                    }
                )
            manager.confirm_consumption(ref, result["consumed_ids"])
        except (FrameworkError, ResultContractError) as error:
            return self._save(
                {
                    **update,
                    "status": "recoverable_issue",
                    "issue": {
                        "code": "peer_result_needs_correction",
                        "detail": error.as_dict()
                        if isinstance(error, FrameworkError)
                        else str(error),
                    },
                }
            )
        return self._save({**update, "status": "ready", "issue": {"issues": result["issues"]}})

    def _apply(self, state):
        state = self._fresh(state)
        if state["activity"] != "apply":
            return state
        candidate = self.repository.read_reference(state["candidate_ref"])
        operation_id = f"apply-{state['round']:05d}"
        original_operation = self.repository.get(self.binding.identity + ":" + operation_id)
        original_intent = self.binding.root / "host" / "operations" / operation_id / "intent.json"
        active_operation = self.control.view()["active"].get(
            self.binding.data["work_unit_id"] + ":platform"
        )
        if (
            state.get("candidate_basis_ref")
            and not original_operation
            and not original_intent.exists()
            and active_operation != operation_id
        ):
            current = self._host("snapshot", "before-" + operation_id)
            basis = self.repository.read_reference(state["candidate_basis_ref"])
            if current["model_revisions"] != basis["model_revisions"]:
                ref = self.repository.put_reference(
                    self.binding.identity + ":drift:" + operation_id + ":" + digest(current),
                    "model_reference",
                    current,
                    0,
                )
                return self._save(
                    {
                        **state,
                        "activity": "model",
                        "status": "ready",
                        "round": state["round"] + 1,
                        "target_ref": ref,
                        "issue": {
                            "code": "model_baseline_changed",
                            "before": basis["model_revisions"],
                            "after": current["model_revisions"],
                            "instruction": "Read the changed actual model and reassess impact; do not invent its business confirmation history.",
                        },
                    }
                )
        result = self._host(
            "apply",
            operation_id,
            {
                "operation_id": operation_id,
                "candidate": candidate["candidate"],
                "changes": candidate["changes"],
                "ontology_targets": candidate.get("ontology_targets"),
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

    def _review_children(self, state, units):
        try:
            checks = [
                check_unit(self.binding, self.repository, self.bridge, unit) for unit in units
            ]
        except FrameworkError as error:
            if error.code in {"task_not_running", "execution_not_admitted"}:
                raise
            correct_selection = error.code in {"unit_check_not_ready", "unit_check_scope_forbidden"}
            return self._save(
                {
                    **state,
                    "activity": "model" if correct_selection else "self_check",
                    "status": "ready" if correct_selection else "recoverable_issue",
                    "round": state["round"] + int(correct_selection),
                    "issue": error.as_dict(),
                }
            )
        if pending := pending_check_units(checks):
            return self._save(
                {
                    **state,
                    "activity": "model",
                    "status": "work_change_pending",
                    "issue": {"code": "local_self_check_rework", "units": pending},
                }
            )
        return None

    def _self_check(self, state):
        state = self._fresh(state)
        if state["activity"] != "self_check":
            return state
        proposal = self.repository.read_reference(state["candidate_ref"])
        if review := self._review_children(state, proposal.get("review_units", [])):
            return review
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
                "pending_child_units": self._pending_children(),
                "workspace_context": SemanticWorkspace(
                    self.repository, self.binding.data, self.binding.actor
                ).context()
                if self.binding.data.get("semantic_workspace")
                else None,
                "child_self_checks": [
                    {
                        "unit_id": unit["unit_id"],
                        "material_ref": row["content"]["check_material_ref"],
                    }
                    for unit in self.binding.direct_units
                    if (
                        row := self.repository.get(
                            self.binding.for_unit(unit["unit_id"]).identity + ":work"
                        )
                    )
                    and row["content"].get("check_material_ref")
                ],
                "feedback": state.get("issue"),
                "instruction": "Read the actual model with query_semantic_context. Check business meaning "
                "against approved sources; a candidate or successful application is not proof. "
                "Return exactly one JSON object matching result_schema: ready, revise or waiting_input. "
                "Describe needed model corrections in issues for the modeling stage; do not include "
                "a draft change request or additional JSON blocks. Do not invent missing information. "
                "consumed_ids may only contain IDs from Queued inputs, never material IDs; "
                "return [] when that queue is empty. When pending_child_units is nonempty, "
                "check the current safely applied portion and retain unfinished child scope in issues. "
                "Do not repeat a pending child's question as a new parent human request; "
                "if that portion is sound, return ready and the program keeps the task waiting. "
                "Do not invent answers for those children; ready for this portion does not finish the task. "
                "When semantic workspace is enabled, revisit your relevant coverage/open records "
                "after the actual read: update the same record IDs with actual expression destinations "
                "and remaining gaps. Repair invalid references using returned versioned refs, "
                "and explicitly supersede duplicate notes instead of leaving conflicting current copies. "
                "Model completeness does not automatically close unfinished workspace records.",
                "local_review_contract": "When a ready direct child's bounded actual-model check "
                "is needed, name it in review_units. The original unit checks its own proposal "
                "with isolated production context and read tools, not application rights. "
                "Reuse current child_self_checks when applicable; retain your own cross-unit "
                "rules and unallocated scope judgment. This is production self-check, not acceptance.",
                "result_schema": SELF_CHECK_SCHEMA,
                "human_context": self.human.context(),
                "human_input_contract": "Ask missing business facts with human_requests "
                "(question, reason, impact) and waiting_input. Consume actual Queued input IDs; "
                "resolve only explicitly matched, consumed non-partial replies with "
                "resolved_request_ids. Reassess replies against actual target versions; "
                "do not repeat unchanged pending questions or infer unresolved facts.",
            }
        )
        execution_id = f"self-check-{state['round']:05d}-{state.get('check_round', 0):03d}"
        ref = self.executions.run(
            execution_id, "self_check", prompt, self.invoke, resume_original=True
        )
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
                self.binding.root
                / "executions"
                / self.binding.execution_id(execution_id)
                / "agent/events.jsonl",
                target["model_revisions"],
            )
            self._confirm_inputs(ref, result)
            if set(result.get("review_units", [])) - {
                u["unit_id"] for u in self.binding.direct_units
            }:
                raise FrameworkError("unit_check_scope_forbidden")
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
        if result["status"] == "waiting_input":
            waiting = self._wait_for_human(
                {**update, "check_round": state.get("check_round", 0) + 1},
                "self_check",
                result,
                ref,
                target_ref,
            )
            if any(self.team.pending(actor) for actor in self.team.peers):
                return self._save(
                    {
                        **waiting,
                        "activity": "collaborate",
                        "status": "ready",
                        "peer_next": "wait_input",
                    }
                )
            return waiting
        if any(self.team.pending(actor) for actor in self.team.peers):
            return self._save(
                {
                    **update,
                    "activity": "collaborate",
                    "peer_next": "self_check",
                    "check_round": state.get("check_round", 0) + 1,
                    "status": "ready",
                }
            )
        if result["status"] == "revise":
            return self._save({**update, "activity": "model", "round": state["round"] + 1})
        if review := self._review_children({**state, **update}, result.get("review_units", [])):
            return review
        if result["status"] == "ready" and (
            reentry := self._new_inputs_before_handoff({**state, **update})
        ):
            return reentry
        if result["status"] == "ready" and (pending := self._pending_children()):
            return self._save(
                {
                    **update,
                    "activity": "model",
                    "status": "waiting_children",
                    "round": state["round"] + 1,
                    "issue": {
                        "issues": [
                            *result["issues"],
                            "Await unfinished children: " + ", ".join(pending),
                        ]
                    },
                }
            )
        return self._save(
            {
                **update,
                "activity": "handoff" if result["status"] == "ready" else "self_check",
                "status": "ready" if result["status"] == "ready" else "waiting_input",
            }
        )

    def _confirm_inputs(self, execution_ref, result):
        consumed = result["consumed_ids"]
        resolved = result.get("resolved_request_ids", [])
        self.human.validate_resolutions(execution_ref, consumed, resolved)
        self.executions.confirm_consumption(execution_ref, consumed)
        self.human.resolve(execution_ref, consumed, resolved)

    def _wait_for_human(self, state, phase, result, execution_ref, basis_ref):
        self.human.ask(phase, result.get("human_requests", []), basis_ref, execution_ref)
        pending = [
            r["request_id"]
            for r in self.human.requests()
            if r["status"] != "resolved" and r["phase"] == phase
        ]
        return self._save(
            {
                **state,
                "activity": "wait_input",
                "status": "waiting_input",
                "resume_activity": phase,
                "human_request_ids": pending,
            }
        )

    def _wait_input(self, state):
        state = self._fresh(state)
        phase = state["resume_activity"]
        control = self.control.synchronize()
        if control["mode"] != "running" or not control["budget_open"]:
            raise FrameworkError("task_not_running", control=control["mode"])
        while not self.human.pending(phase):
            interrupt(
                {
                    "work_unit_id": self.binding.data["work_unit_id"],
                    "request_ids": state.get("human_request_ids", []),
                }
            )
        return self._save(
            {**state, "activity": phase, "status": "ready", "refresh_baseline": phase == "model"}
        )

    def _new_inputs_before_handoff(self, state):
        pending = self.human.pending("model")
        if not pending:
            return None
        return self._save(
            {
                **state,
                "activity": "model",
                "status": "ready",
                "round": state["round"] + 1,
                "refresh_baseline": True,
                "issue": {
                    "code": "new_inputs_before_handoff",
                    "input_ids": [item["id"] for item in pending],
                    "instruction": "New scoped inputs remain to be assessed before handoff. "
                    "Read them in the next model turn; reuse valid applied work and do not "
                    "equate a safe partial-group check with whole-objective completion.",
                },
            }
        )

    def _handoff(self, state):
        state = self._fresh(state)
        if state["activity"] != "handoff":
            return state
        if reentry := self._new_inputs_before_handoff(state):
            return reentry
        target = self._host("finalize", "finalize")
        if reentry := self._new_inputs_before_handoff(state):
            return reentry
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
            "human_context": self.human.context(),
        }
        ref = self.repository.put_reference(
            self.binding.identity + ":handoff:" + digest(handoff), "handoff", handoff, 0
        )
        return self._save({**state, "handoff_ref": ref, "status": "handoff_ready"})

    def _route(self, state):
        plan = self.repository.get("run:" + self.binding.data["run_id"] + ":work-plan")
        if plan:
            generation = (
                plan["content"]["units"].get(self.binding.actor, {}).get("generation", 0)
                if self.binding.is_child
                else plan["content"]["root_generation"]
            )
            if generation != self.binding.data.get("work_generation", 0):
                self._save({**state, "status": "work_change_pending"})
                return END
        pending = [
            r["content"]
            for r in self.repository.list_kind("source_change")
            if r["content"]["status"] == "queued"
            and (not self.binding.is_child or self.binding.actor in r["content"]["affected_units"])
        ]
        if pending:
            self._save({**state, "status": "source_change_pending"})
            return END
        if state["status"] == "waiting_input":
            return "wait_input"
        return state["activity"] if state["status"] == "ready" else END

    def compile(self, checkpointer):
        builder = StateGraph(FlowState)
        builder.add_node("dispatch", lambda state: self._fresh(state))
        builder.add_edge(START, "dispatch")
        names = ("prepare", "model", "collaborate", "apply", "self_check", "wait_input", "handoff")
        builder.add_conditional_edges("dispatch", self._route, [*names, END])
        for name in names:
            builder.add_node(name, getattr(self, "_" + name))
            builder.add_conditional_edges(name, self._route, [*names, END])
        return builder.compile(checkpointer=checkpointer)

    def advance(self, checkpointer) -> dict:
        state = self.initialize()
        if state["status"] == "handoff_ready":
            return state
        if state["status"] == "proposal_ready":
            if not self.human.pending("model"):
                return state
            state = self._save(
                {**state, "status": "ready", "activity": "model", "round": state["round"] + 1}
            )
        if self.control.synchronize()["mode"] == "stopped":
            return self._save({**state, "status": "stopped"})
        if state["status"] == "waiting_input" and state["activity"] != "wait_input":
            phase = state["activity"]
            state = self._save(
                {
                    **state,
                    "activity": "wait_input",
                    "resume_activity": phase,
                    "round": state["round"] + (phase == "model"),
                    "check_round": state.get("check_round", 0) + (phase == "self_check"),
                }
            )
        if state["activity"] != "wait_input":
            state = self._save({**state, "status": "ready"})
        elif self.control.view()["mode"] == "running":
            state = self._save({**state, "status": "waiting_input"})
        graph = self.compile(checkpointer)
        config = {
            "configurable": {"thread_id": self.binding.thread_id},
            "recursion_limit": 100,
        }
        try:
            snapshot = graph.get_state(config)
            if (
                state["activity"] == "wait_input"
                and snapshot.next
                and not self.human.pending(state["resume_activity"])
            ):
                return state
            interrupted = any(task.interrupts for task in snapshot.tasks)
            value = Command(resume=True) if interrupted else None if snapshot.next else state
            graph.invoke(value, config)
            return self.repository.get(self.work_id)["content"]
        except FrameworkError as error:
            current = self.repository.get(self.work_id)["content"]
            control = self.control.view()
            mode = control.get("mode", "running")
            status = (
                mode
                if error.code in {"task_not_running", "execution_not_admitted"}
                and mode != "running"
                else "blocked"
            )
            if error.code == "task_not_running" and status == "blocked":
                status = "paused"
            if error.code == "execution_not_admitted" and not control["budget_open"]:
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
