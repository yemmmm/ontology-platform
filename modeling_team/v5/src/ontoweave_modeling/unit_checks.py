"""Bounded production read-back by the original work unit; never independent acceptance."""

import json

from .acceptance import require_governed_read, successful_reads
from .contracts import SELF_CHECK_SCHEMA, FrameworkError, digest, write_json
from .control import TaskControl
from .execution import CodexInvocation, ExecutionManager
from .human_input import HumanInput
from .results import ResultContractError, decode_json_result
from .semantic_workspace import SemanticWorkspace
from .team import TeamChannel
from .work_plan import WorkPlan


def pending_check_units(checks):
    return [
        check["unit_id"]
        for check in checks
        if check.get("status") == "work_change_pending" or check["result"]["status"] != "ready"
    ]


def check_unit(binding, repository, bridge, unit_id, *, invoke=None, invoke_factory=None):
    current_binding = WorkPlan(binding.data, repository).binding(binding)
    if unit_id not in {u["unit_id"] for u in current_binding.data["work_units"]}:
        raise FrameworkError("work_unit_not_found", unit_id=unit_id)
    selected = current_binding.for_unit(unit_id)
    if selected.role_team and selected.role == "competency-question":
        raise FrameworkError("public_cq_review_required", unit_id=unit_id)
    work_id = selected.identity + ":work"
    row = repository.get(work_id)
    if (
        not row
        or row["content"].get("status") != "proposal_ready"
        or not (
            row["content"].get("candidate_ref")
            or (
                selected.role_team
                and selected.role == "coordinator"
                and row["content"].get("integration_plan_ref")
            )
        )
        or row["content"].get("work_generation", 0) != selected.data.get("work_generation", 0)
    ):
        raise FrameworkError("unit_check_not_ready", unit_id=unit_id)
    work = row["content"]
    if selected.role_team and selected.role == "coordinator":
        integration = repository.read_reference(work["integration_plan_ref"])
        proposal = {
            "integration_plan": integration,
            "scope_ref": selected.data.get("scope_ref"),
            "review_units": integration["check_units"],
        }
    else:
        proposal = repository.read_reference(work["candidate_ref"])
    # This unit is always checked below; only its direct children need recursion.
    requested = [child for child in proposal.get("review_units", []) if child != unit_id]
    if set(requested) - {unit["unit_id"] for unit in selected.direct_units}:
        raise FrameworkError("unit_check_scope_forbidden", unit_id=unit_id)
    child_checks = [
        check_unit(
            current_binding, repository, bridge, child, invoke=invoke, invoke_factory=invoke_factory
        )
        for child in requested
    ]
    if pending := pending_check_units(child_checks):
        return {
            "unit_id": unit_id,
            "status": "work_change_pending",
            "pending_units": pending,
            "child_checks": child_checks,
        }
    target = bridge.call("snapshot")
    basis = {
        "candidate_ref": work.get("candidate_ref"),
        "source_manifest_digest": selected.data["source_manifest_digest"],
        "work_generation": selected.data.get("work_generation", 0),
        "model_revisions": target["model_revisions"],
    }
    if selected.role_team:
        plan = WorkPlan(binding.data, repository).row()["content"]
        basis.update(
            role_result_ref=work.get("role_result_ref"),
            integration_plan_ref=work.get("integration_plan_ref"),
            scope_ref=selected.data.get("scope_ref"),
            public_cq_ref=plan.get("public_cq_ref"),
        )
    if child_checks:
        basis["child_check_refs"] = {
            child: repository.get(current_binding.for_unit(child).identity + ":work")["content"][
                "local_self_check_ref"
            ]
            for child in requested
        }
    identity = selected.identity + ":unit-check:" + digest(basis)
    prior = repository.get(identity)
    if prior:
        return prior["content"]
    directory = binding.root / "unit-checks" / unit_id / digest(basis)
    attempt_path = directory / "attempt.json"
    attempt = json.loads(attempt_path.read_text()) if attempt_path.exists() else {"index": 0}
    workspace_context = None
    if selected.data.get("semantic_workspace"):
        workspace = SemanticWorkspace(repository, selected.data, selected.actor)
        workspace.observe_models(target["model_revisions"])
        workspace_context = workspace.context()
    prompt = {
        "objective": selected.data["objective"],
        "source_manifest": selected.data["source_manifest"],
        "assigned_material_ids": selected.data.get("assigned_material_ids", []),
        "own_proposal": proposal,
        "child_self_checks": [
            {key: check[key] for key in ("unit_id", "result", "governed_read_material_ref")}
            for check in child_checks
        ],
        "human_context": HumanInput(selected, repository, TaskControl(repository)).context(),
        "actual_target": {
            **{k: target[k] for k in ("project_id", "ontology_ids", "model_revisions")},
            "resource_bindings": target.get("resource_bindings", {}),
        },
        "workspace_context": workspace_context,
        **(
            {
                "public_cq_material_ref": plan.get("public_cq_material_ref"),
                "professional_role": selected.role,
            }
            if selected.role_team
            else {}
        ),
        "instruction": "Production self-check for your bounded unit, not independent acceptance. "
        "Read the original sources and actual governed model, expand exact resources as needed. "
        "actual_target.resource_bindings provides actual applied resource locators for exact "
        "read_model_resource calls when recall is incomplete or degraded. These locators "
        "are navigation, not proof of business meaning; still read the actual resource. "
        "Check your proposed meaning, expressions, conditions and unknowns. Do not apply changes "
        "or assess unrelated child details. Return ready, revise or waiting_input with precise "
        "issues; a candidate is not actual model evidence. This return is not whole-task PASS. "
        "Judge the complete source-grounded meaning, not whether parent integration preserved "
        "your candidate's shape or created one resource per proposition. Supported semantic "
        "definitions may carry a calculation rule without a dedicated metric mapping resource. "
        "Still verify actual relationships and resource semantic level; an individual does not "
        "replace a general concept when the source supplies no instances. "
        "consumed_ids contains only this turn's Queued inputs[].id; return [] for an empty "
        "queue. Historical answers and own_proposal.consumed_ids are retained evidence, not "
        "inputs delivered again in this turn. "
        "When workspace_context is supplied, inspect your existing relevant records first. "
        "After the governed read, refresh those same coverage/definition/open records and states "
        "from the actual expressions; do not add a parallel completion note and leave old fault "
        "or pending records current. Supersede genuinely obsolete records explicitly. "
        "Keep real unknowns or missing expressions accurate; do not mark all records complete "
        "merely because the model check is ready. Recheck final dependency freshness.",
        "result_schema": {
            **SELF_CHECK_SCHEMA,
            "properties": {
                k: v for k, v in SELF_CHECK_SCHEMA["properties"].items() if k != "review_units"
            },
        },
        "contract_feedback": attempt.get("error"),
    }
    execution_id = "unit-check-" + digest(basis)[:20] + f"-{attempt['index']:03d}"
    manager = ExecutionManager(repository, TaskControl(repository), selected)
    ref = manager.run(
        execution_id,
        "self_check",
        json.dumps(prompt),
        invoke
        or (
            invoke_factory(selected)
            if invoke_factory
            else CodexInvocation(selected, bridge, model_revisions=target["model_revisions"])
        ),
        resume_original=True,
    )
    native = repository.read_reference(ref)["result"]
    try:
        if native["status"] != "completed":
            raise FrameworkError(
                "unit_check_turn_failed",
                layer="runtime/infrastructure",
                native_error=native.get("error"),
                execution_ref=ref,
            )
        result = decode_json_result(native["final_response"], SELF_CHECK_SCHEMA)
        events = (
            binding.root / "executions" / selected.execution_id(execution_id) / "agent/events.jsonl"
        )
        require_governed_read(events, target["model_revisions"])
        manager.confirm_consumption(ref, result["consumed_ids"])
        if bridge.call("snapshot")["model_revisions"] != target["model_revisions"]:
            raise FrameworkError("frozen_target_changed")
    except (ResultContractError, FrameworkError) as error:
        write_json(
            attempt_path,
            {
                "index": attempt["index"] + 1,
                "error": error.as_dict() if isinstance(error, FrameworkError) else str(error),
                "execution_ref": ref,
            },
        )
        raise FrameworkError(
            "unit_check_needs_correction",
            layer=error.layer if isinstance(error, FrameworkError) else "platform-contract",
            detail=str(error),
            cause=error.as_dict() if isinstance(error, FrameworkError) else str(error),
        ) from error
    channel = TeamChannel(selected.data, repository, TaskControl(repository), selected.actor)
    reads = [
        {"tool": tool, "arguments": arguments, "data": data}
        for tool, arguments, data in successful_reads(events)
        if tool in {"query_semantic_context", "read_model_resource"}
    ]
    read_ref = channel.publish(
        "check-reads-" + digest(basis)[:24], text=json.dumps(reads, ensure_ascii=False)
    )
    proof = {
        "unit_id": unit_id,
        "basis": basis,
        "result": result,
        "execution_ref": ref,
        "governed_read_material_ref": read_ref,
    }
    proof_ref = repository.put_reference(identity, "unit_self_check", proof, 0)
    material = channel.publish(
        "check-" + digest(basis)[:24], text=json.dumps(proof, ensure_ascii=False)
    )
    current = repository.get(work_id)
    repository.put_reference(
        work_id,
        "work_unit",
        {
            **current["content"],
            "local_self_check_ref": proof_ref,
            "check_material_ref": material,
        },
        current["revision"],
    )
    if result["status"] != "ready":
        WorkPlan(binding.data, repository).reopen(
            unit_id, "Local actual-model self-check: " + "; ".join(result["issues"])
        )
    # Host-produced evidence can be delivered after handoff, without starting another turn.
    # Keep the ordinary Agent send/closed-task guard and material read permissions unchanged.
    parent = selected.data.get("_parent_actor", "modeling")
    channel.control.enqueue(
        channel.prefix + selected.actor + ":host-check-" + digest(basis)[:24],
        "input",
        "Bounded production self-check result; exact governed reads are available by range. "
        "This is not independent acceptance.",
        channel.unit(parent),
        metadata={
            "source": "agent",
            "author": selected.actor,
            "phase": "self_check",
            "recipient": parent,
            "run_id": selected.data["run_id"],
            "material_refs": [material, read_ref],
        },
    )
    return proof
