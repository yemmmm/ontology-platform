"""Bounded production read-back by the original work unit; never independent acceptance."""

import json

from .acceptance import require_governed_read
from .contracts import SELF_CHECK_SCHEMA, FrameworkError, digest, write_json
from .control import TaskControl
from .execution import CodexInvocation, ExecutionManager
from .human_input import HumanInput
from .results import ResultContractError, decode_json_result
from .team import TeamChannel
from .work_plan import WorkPlan


def check_unit(binding, repository, bridge, unit_id, *, invoke=None):
    current_binding = WorkPlan(binding.data, repository).binding(binding)
    if unit_id not in {u["unit_id"] for u in current_binding.data["work_units"]}:
        raise FrameworkError("work_unit_not_found", unit_id=unit_id)
    selected = current_binding.for_unit(unit_id)
    work_id = selected.identity + ":work"
    row = repository.get(work_id)
    if (
        not row
        or row["content"].get("status") != "proposal_ready"
        or not row["content"].get("candidate_ref")
        or row["content"].get("work_generation", 0) != selected.data.get("work_generation", 0)
    ):
        raise FrameworkError("unit_check_not_ready", unit_id=unit_id)
    work = row["content"]
    target = bridge.call("snapshot")
    basis = {
        "candidate_ref": work.get("candidate_ref"),
        "source_manifest_digest": selected.data["source_manifest_digest"],
        "work_generation": selected.data.get("work_generation", 0),
        "model_revisions": target["model_revisions"],
    }
    identity = selected.identity + ":unit-check:" + digest(basis)
    prior = repository.get(identity)
    if prior:
        return prior["content"]
    directory = binding.root / "unit-checks" / unit_id / digest(basis)
    attempt_path = directory / "attempt.json"
    attempt = json.loads(attempt_path.read_text()) if attempt_path.exists() else {"index": 0}
    prompt = {
        "objective": selected.data["objective"],
        "source_manifest": selected.data["source_manifest"],
        "assigned_material_ids": selected.data.get("assigned_material_ids", []),
        "own_proposal": repository.read_reference(work["candidate_ref"]),
        "human_context": HumanInput(selected, repository, TaskControl(repository)).context(),
        "actual_target": {k: target[k] for k in ("project_id", "ontology_ids", "model_revisions")},
        "instruction": "Production self-check for your bounded unit, not independent acceptance. "
        "Read the original sources and actual governed model, expand exact resources as needed. "
        "Check your proposed meaning, expressions, conditions and unknowns. Do not apply changes "
        "or assess unrelated child details. Return ready, revise or waiting_input with precise "
        "issues; a candidate is not actual model evidence. This return is not whole-task PASS. "
        "consumed_ids contains only this turn's Queued inputs[].id; return [] for an empty "
        "queue. Historical answers and own_proposal.consumed_ids are retained evidence, not "
        "inputs delivered again in this turn.",
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
        invoke or CodexInvocation(selected, bridge, model_revisions=target["model_revisions"]),
        resume_original=True,
    )
    native = repository.read_reference(ref)["result"]
    try:
        if native["status"] != "completed":
            raise FrameworkError("unit_check_turn_failed", layer="runtime/infrastructure")
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
        raise FrameworkError("unit_check_needs_correction", detail=str(error)) from error
    proof = {"unit_id": unit_id, "basis": basis, "result": result, "execution_ref": ref}
    proof_ref = repository.put_reference(identity, "unit_self_check", proof, 0)
    material = TeamChannel(
        selected.data, repository, TaskControl(repository), selected.actor
    ).publish("check-" + digest(basis)[:24], text=json.dumps(proof, ensure_ascii=False))
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
    return proof
