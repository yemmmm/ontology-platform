"""Professional results on the existing WorkUnitFlow and work-plan checkpoint path."""

from __future__ import annotations

import json

from .acceptance import require_governed_read, successful_reads
from .contracts import FrameworkError, decode_work_result, digest
from .results import ResultContractError, decode_json_result
from .role_team import ROLE_KINDS, compose_integration, qualified_id, result_schema
from .work_plan import WorkPlan


def _events(flow, execution_id):
    return (
        flow.binding.root
        / "executions"
        / flow.binding.execution_id(execution_id)
        / "agent/events.jsonl"
    )


def _read_materials(events, references):
    """Consumption requires complete observed reads of the exact delivered version."""
    reads = list(successful_reads(events))
    for reference in references:
        ranges, total = [], None
        for tool, _, data in reads:
            if tool != "read_handoff_material" or data.get("reference") != reference:
                continue
            start = data.get("offset", 0)
            total = data.get("total_characters")
            ranges.append((start, start + len(data.get("text", ""))))
        end = 0
        for start, stop in sorted(ranges):
            if start > end:
                break
            end = max(end, stop)
        if total is None or end < total:
            raise FrameworkError(
                "role_material_not_consumed",
                reference=reference,
                read_characters=end,
                total_characters=total,
            )


def _basis(flow, baseline, plan):
    binding = flow.binding
    unit = plan["units"].get(binding.actor, {})
    return {
        "source_manifest_digest": binding.data["source_manifest_digest"],
        "scope_ref": unit.get("scope_ref")
        if binding.is_child
        else plan.get("scope_refs", {}).get(binding.actor),
        "cq_ref": plan.get("public_cq_ref"),
        "shared_refs": unit.get("shared_refs", []),
        "model_revisions": baseline["model_revisions"],
        "consumed_refs": [],
    }


def _publish(flow, result_ref, envelope, artifact):
    text = json.dumps(
        {"result_ref": result_ref, "result": envelope, "artifact": artifact}, ensure_ascii=False
    )
    material = flow.team.publish("role-result-" + digest(result_ref)[:24], text=text)
    parent = flow.binding.data.get("_parent_actor", flow.binding.root_actor)
    if parent != flow.binding.actor:
        flow.team.send(
            parent,
            "Professional result; read the precise material before consuming.",
            "role-result-" + digest(result_ref)[:24],
            material_refs=[material],
        )
    return material


def _install_scope(flow, artifact, artifact_ref, material):
    binding = flow.binding
    manager = WorkPlan(binding.data, flow.repository, binding.actor)

    def update(plan):
        root = binding.actor
        assigned = set()
        for assignment in artifact["assignments"]:
            identity = assignment["unit_id"]
            if identity in {
                binding.root_actor,
                "acceptance",
                binding.data["work_unit_id"],
            }:
                raise FrameworkError("work_unit_identity_conflict", unit_id=identity)
            if identity in assigned:
                raise FrameworkError("work_unit_identity_conflict", unit_id=identity)
            assigned.add(identity)
            if set(assignment["material_ids"]) - binding.data["source_manifest"].keys():
                raise FrameworkError("material_forbidden", unit_id=identity)
            prior = plan["units"].get(identity)
            if prior and (prior["role_id"] != assignment["role_id"] or prior["parent_id"] != root):
                raise FrameworkError(
                    "work_owner_forbidden",
                    unit_id=identity,
                    expected={"role_id": prior["role_id"], "parent_id": prior["parent_id"]},
                    received={"role_id": assignment["role_id"], "parent_id": root},
                    instruction="Reuse the existing role and parent; do not reassign its identity.",
                )
            requested = {
                **assignment,
                "parent_id": root,
                "actor_id": identity,
                "work_kind": ROLE_KINDS[assignment["role_id"]],
                "work_phase": "plan"
                if assignment["role_id"] == "coordinator"
                else "propose"
                if assignment["role_id"] == "modeling"
                else "produce",
                "status": "active",
            }
            semantic_change = not prior or any(prior.get(k) != v for k, v in requested.items())
            generation = prior.get("generation", 0) + int(semantic_change) if prior else 0
            plan["units"][identity] = {
                **(prior or {}),
                **requested,
                "generation": generation,
                "scope_ref": artifact_ref if semantic_change else prior["scope_ref"],
            }
        for shared in artifact["shared_definitions"]:
            owner = plan["units"].get(shared["maintainer_unit_id"])
            if not owner or owner["role_id"] != "modeling":
                raise FrameworkError(
                    "shared_maintainer_missing", definition_id=shared["definition_id"]
                )
            if set(shared["user_unit_ids"]) - plan["units"].keys():
                raise FrameworkError("shared_user_missing", definition_id=shared["definition_id"])
        previous_ref = plan.get("scope_refs", {}).get(root)
        previous_shared = (
            flow.repository.read_reference(previous_ref).get("shared_definitions", [])
            if previous_ref
            else []
        )
        if previous_shared != artifact["shared_definitions"]:
            affected = {
                identity
                for shared in [*previous_shared, *artifact["shared_definitions"]]
                for identity in [shared["maintainer_unit_id"], *shared["user_unit_ids"]]
            }
            for identity in affected & plan["units"].keys():
                unit = plan["units"][identity]
                if unit.get("scope_ref") != artifact_ref:
                    unit.update(generation=unit["generation"] + 1, scope_ref=artifact_ref)
                unit["shared_refs"] = (
                    [artifact_ref]
                    if any(
                        identity in [s["maintainer_unit_id"], *s["user_unit_ids"]]
                        for s in artifact["shared_definitions"]
                    )
                    else []
                )
        intake = plan["units"].get("modeler")
        if (
            root == binding.root_actor
            and "modeler" not in assigned
            and intake
            and intake.get("work_phase") == "source_intake"
        ):
            # Keep its original analysis/results; only the provisional assignment retires.
            from .control import TaskControl

            if "modeler" in TaskControl(flow.repository).view()["active"]:
                intake["retire_after_intake"] = True
            else:
                intake["status"] = "retired"
        plan.setdefault("scope_refs", {})[root] = artifact_ref
        plan.setdefault("scope_materials", {})[root] = material
        # Public production reviews the new scope, rather than being replaced by the root.
        cq = plan["units"]["cq-public"]
        primary_scope = plan["scope_refs"].get(binding.root_actor, cq.get("scope_ref"))
        # Nested plans still refresh panorama coverage even when the root scope is unchanged.
        # An explicit CQ assignment above has already advanced this exact scope once.
        if "cq-public" not in assigned or cq.get("scope_ref") != primary_scope:
            cq.update(
                scope_ref=primary_scope, generation=cq["generation"] + 1, work_phase="produce"
            )
        return assigned

    assigned = manager.change(update)
    for identity in {"cq-public", *assigned}:
        flow.team.send(
            identity,
            "Exact scope assignment; reuse applicable source intake and retain unknowns.",
            "scope-" + digest([artifact_ref, identity])[:24],
            material_refs=[material],
        )
        intake_work = flow.repository.get("run:" + binding.data["run_id"] + ":unit:modeler:work")
        if intake_work and intake_work["content"].get("intake_material_ref"):
            ref = intake_work["content"]["intake_material_ref"]
            # The intake author delivered this material to the Coordinator; forward unchanged.
            flow.team.send(
                identity,
                "Retained source intake; reassess only assignment differences.",
                "intake-" + digest([ref, identity])[:24],
                material_refs=[ref],
            )


def _refresh_cq(flow, artifact_ref, material, artifact, phase):
    manager = WorkPlan(flow.binding.data, flow.repository, flow.binding.actor)
    prior = manager.row()["content"].get("public_cq_ref")
    if flow.binding.actor != "cq-public":
        # A recursive public-CQ subtask owns its own result, never the canonical set.
        return
    changed = not prior or flow.repository.read_reference(prior) != artifact

    def update(plan):
        plan.update(public_cq_ref=artifact_ref, public_cq_material_ref=material)
        if phase == "review":
            basis = flow.repository.read_reference(
                flow.repository.get(flow.work_id)["content"]["role_result_ref"]
            )["basis"]
            plan["public_cq_model_revisions"] = basis["model_revisions"]
            plan["public_cq_review_basis"] = {
                "cq_ref": artifact_ref,
                "model_revisions": basis["model_revisions"],
                "source_manifest_digest": basis["source_manifest_digest"],
            }

    manager.change(update)
    # A proof refresh with unchanged public semantics must not trigger team-wide rework.
    if not changed:
        return
    plan = manager.row()["content"]
    for unit in plan["units"].values():
        if (
            unit["status"] != "active"
            or unit["role_id"] != "modeling"
            or unit.get("work_phase") == "source_intake"
        ):
            continue
        flow.team.send(
            unit["unit_id"],
            "New exact public CQ version; determine its effect within your scope.",
            "cq-" + digest([artifact_ref, unit["unit_id"]])[:24],
            material_refs=[material],
        )


def _validate_public_cq(flow, result, plan):
    artifact = result["artifact"]
    questions = artifact["questions"]
    ids = [q["cq_id"] for q in questions]
    dispositions = artifact["reused_ids"] + artifact["revised_ids"] + artifact["new_ids"]
    if (
        len(set(ids)) != len(ids)
        or len(set(dispositions)) != len(dispositions)
        or set(dispositions) != set(ids)
    ):
        raise FrameworkError("public_cq_identity_or_disposition_invalid")
    prior = (
        flow.repository.read_reference(plan["public_cq_ref"])
        if plan.get("public_cq_ref")
        else {"questions": []}
    )
    confirmed = [q for q in prior["questions"] if q["criteria_status"] == "confirmed"]
    from .custom_cq import public_goal_questions

    seeds = public_goal_questions(flow.binding.materials, flow.binding.data["source_manifest"])
    for question in questions:
        if any(ref not in result["source_refs"] for ref in question["source_refs"]):
            raise FrameworkError("public_cq_source_not_consumed", cq_id=question["cq_id"])
        if question["criteria_status"] != "confirmed" or question in confirmed:
            continue
        seed = seeds.get(question["cq_id"], {})
        definition = seed.get("cq_definition", {})
        if (
            seed.get("question") == question["question"]
            and definition.get("criteria_status") == "confirmed"
            and question["reference_answer"] == definition.get("reference_answer")
            and question["answer_author"] == definition.get("answer_author")
        ):
            continue
        authorized = False
        execution = flow.repository.read_reference(result["_execution_ref"])
        for answer in execution["inputs"]:
            metadata = answer.get("metadata", {})
            request_id = metadata.get("request_id")
            request = flow.repository.get(request_id) if request_id else None
            if (
                answer["id"] in result["consumed_ids"]
                and request_id in result.get("resolved_request_ids", [])
                and metadata.get("source") == "user"
                and not metadata.get("partial")
                and request
                and request["content"]["question"] == question["question"]
                and question["reference_answer"] == answer["body"]
                and question["answer_author"] == metadata.get("author")
            ):
                authorized = True
                break
        if not authorized:
            raise FrameworkError(
                "public_cq_confirmation_basis_required",
                cq_id=question["cq_id"],
                instruction="Preserve exact confirmed seed/human evidence, or retain draft/unknown; self-authored answers are not confirmation.",
            )


def model(flow, state):
    binding, repository = flow.binding, flow.repository
    manager = WorkPlan(binding.data, repository, binding.actor)
    plan = manager.row()["content"]
    phase = state.get(
        "role_phase",
        binding.data.get("work_phase", "plan" if binding.role == "coordinator" else "propose"),
    )
    if state.get("issue", {}).get("code") == "source_changed" and binding.role == "coordinator":
        phase = "plan"
    if binding.role == "coordinator" and phase == "integrate":
        children = [
            u
            for u in plan["units"].values()
            if u["parent_id"] == binding.actor
            and u["status"] == "active"
            and u["role_id"] in {"modeling", "coordinator"}
        ]
        ready = [
            u
            for u in children
            if (r := repository.get(binding.for_unit(u["unit_id"]).identity + ":work"))
            and r["content"]["status"] == "proposal_ready"
        ]
        if not ready:
            return flow._save({**state, "status": "waiting_children", "role_phase": phase})
    local_execution = f"role-{state['round']:05d}"
    previous_execution = repository.get(
        binding.identity + ":execution:" + binding.execution_id(local_execution)
    )
    previous_prompt = (
        json.loads(previous_execution["content"]["prompt"]) if previous_execution else None
    )
    baseline = (
        previous_prompt["actual_baseline"]
        if previous_prompt
        else flow._host("snapshot", "role-baseline-" + str(state["round"]))
    )
    baseline_ref = repository.put_reference(
        binding.identity + ":role-baseline:" + digest(baseline), "model_reference", baseline, 0
    )
    expected_basis = previous_prompt["basis"] if previous_prompt else _basis(flow, baseline, plan)
    child_results = []
    for unit in plan["units"].values():
        row = repository.get("run:" + binding.data["run_id"] + ":unit:" + unit["unit_id"] + ":work")
        child_results.append(
            {
                **{
                    k: unit.get(k)
                    for k in (
                        "unit_id",
                        "role_id",
                        "work_kind",
                        "work_phase",
                        "generation",
                        "scope_ref",
                        "status",
                    )
                },
                "work": row["content"] if row else None,
            }
        )
    prompt = {
        "objective": binding.data["objective"],
        "actor_id": binding.actor,
        "role_id": binding.role,
        "work_kind": binding.work_kind,
        "phase": phase,
        "source_manifest": binding.data["source_manifest"],
        "assigned_material_ids": binding.data.get("assigned_material_ids", []),
        "actual_baseline": baseline,
        "basis": expected_basis,
        "scope_materials": plan.get("scope_materials", {}),
        "public_cq_material_ref": plan.get("public_cq_material_ref"),
        "child_results": child_results,
        "human_context": flow.human.context(),
        "previous_result_material_ref": state.get("rejected_result_material_ref")
        or state.get("result_material_ref"),
        "feedback": state.get("issue"),
        "result_schema": result_schema(binding, phase),
        "contract": "Return one professional result. Authorship is program-bound. Echo the exact actual basis used. "
        "consumed_refs names only exact handoff materials completely read using read_handoff_material this turn. "
        "source_refs names actual approved source reads this turn, not filenames or inferred truth. "
        "An integration selects exact owner result_ref/candidate_ref/changes_ref from retained role result envelopes, "
        "never writes their semantic body. Defer unready scope with its original owner. Original Modelers check every "
        "selected contribution after application; public CQ is separate. Existing baseline resource_refs are exact "
        "existing_resource_ref objects; preserve artifact_ref and path without guessing native IDs. "
        "Use human_requests for real business decisions; consume only delivered queue IDs. "
        "If a previous rejected result is provided, read its exact material and correct the "
        "reported technical fields; retain valid business content. It is not an accepted artifact. "
        "For semantic revisions use reopen_work_unit for affected original owners, preserving unaffected siblings.",
    }
    if previous_prompt:
        prompt = previous_prompt
    purpose = "source_intake" if phase == "source_intake" else binding.work_kind
    execution_ref = flow.executions.run(
        local_execution, purpose, json.dumps(prompt), flow.invoke, resume_original=True
    )
    native = repository.read_reference(execution_ref)["result"]
    try:
        if native["status"] != "completed":
            raise FrameworkError(
                "native_turn_failed", layer="runtime/infrastructure", execution_ref=execution_ref
            )
        result = decode_json_result(native["final_response"], prompt["result_schema"])
        if (
            binding.role == "coordinator"
            and phase == "plan"
            and result["status"] == "waiting_children"
            and result["artifact"] is not None
        ):
            # A complete explicit plan must be installed before its children can run.
            # All source, basis and ownership checks below still apply.
            result["status"] = "proposed"
        basis = result["basis"]
        for field, code in (
            ("source_manifest_digest", "role_source_basis_changed"),
            ("scope_ref", "role_scope_basis_changed"),
            ("model_revisions", "role_model_basis_changed"),
            ("shared_refs", "role_shared_basis_changed"),
            ("cq_ref", "role_cq_basis_changed"),
        ):
            if basis[field] != expected_basis[field] and not (
                field == "cq_ref" and basis[field] is None
            ):
                raise FrameworkError(
                    code,
                    field="basis." + field,
                    expected=expected_basis[field],
                    received=basis[field],
                    instruction="Echo this turn's input basis value exactly, including null. "
                    "New plans and contributions belong in artifact, not the input basis. "
                    "List only fully read handoff materials in consumed_refs.",
                )
        _read_materials(_events(flow, local_execution), basis["consumed_refs"])
        if result["status"] in {"proposed", "no_change"}:
            if not result["artifact"] or not result["source_refs"]:
                raise FrameworkError("role_artifact_or_sources_missing")
            reads = {
                (args.get("material_id"), data.get("sha256"))
                for tool, args, data in successful_reads(_events(flow, local_execution))
                if tool == "read_material" and "text" in data
            }
            for ref in result["source_refs"]:
                entry = binding.data["source_manifest"].get(ref["material_id"])
                if not entry or entry["sha256"] != ref["sha256"]:
                    raise FrameworkError(
                        "source_reference_mismatch", material_id=ref["material_id"]
                    )
                if (ref["material_id"], ref["sha256"]) not in reads:
                    raise FrameworkError(
                        "source_read_missing",
                        material_id=ref["material_id"],
                        instruction="Read this approved material with read_material in this turn "
                        "before listing it in source_refs; follow next_offset for remaining pages. "
                        "Reuse the retained business analysis, but do not claim a prior turn's read.",
                    )
            if binding.role == "modeling" and phase != "source_intake":
                decode_work_result(
                    json.dumps({**result, **result["artifact"]}), binding.data["source_manifest"]
                )
            if binding.role == "competency-question" and phase == "review":
                require_governed_read(_events(flow, local_execution), baseline["model_revisions"])
            if binding.role == "competency-question":
                _validate_public_cq(flow, {**result, "_execution_ref": execution_ref}, plan)
        flow._confirm_inputs(execution_ref, result)
    except (FrameworkError, ResultContractError) as error:
        rejected_material = None
        if native["status"] == "completed" and native.get("final_response"):
            rejected_material = flow.team.publish(
                "rejected-" + local_execution, text=native["final_response"]
            )
        return flow._save(
            {
                **state,
                "status": "recoverable_issue",
                "round": state["round"] + 1,
                "execution_ref": execution_ref,
                "rejected_result_material_ref": rejected_material,
                "issue": error.as_dict()
                if isinstance(error, FrameworkError)
                else {
                    "code": "role_result_invalid",
                    "layer": "platform-contract",
                    "recoverable": True,
                    "detail": str(error),
                },
            }
        )
    artifact = result["artifact"]
    identity = (
        binding.identity + f":role-result:{binding.data.get('work_generation', 0)}:{state['round']}"
    )
    artifact_ref = (
        repository.put_reference(
            binding.identity + ":role-artifact:" + digest(artifact), "role_artifact", artifact, 0
        )
        if artifact
        else None
    )
    envelope = {
        **{k: result[k] for k in ("schema_version", "status", "basis", "source_refs", "issues")},
        "role_id": binding.role,
        "actor_id": binding.actor,
        "unit_id": binding.data.get("_unit_id", binding.data["work_unit_id"]),
        "generation": binding.data.get("work_generation", 0),
        "work_kind": binding.work_kind,
        "phase": phase,
        "execution_ref": execution_ref,
        "artifact_ref": artifact_ref,
        "candidate_ref": None,
        "changes_ref": None,
    }
    if binding.role == "modeling" and phase != "source_intake" and artifact:
        for name, kind in (("candidate", "model_candidate"), ("changes", "model_changes")):
            if artifact[name] is not None:
                envelope[name + "_ref"] = repository.put_reference(
                    identity + ":" + name, kind, artifact[name], 0
                )
        envelope["qualified_change_ids"] = {
            change["change_id"]: qualified_id(binding.actor, identity, change["change_id"], "c")
            for change in (artifact.get("changes") or {}).get("changes", [])
        }
    result_ref = repository.put_reference(identity, "role_work_result", envelope, 0)
    material = _publish(flow, result_ref, envelope, artifact)
    update = {
        **state,
        "rejected_result_material_ref": None,
        "execution_ref": execution_ref,
        "role_result_ref": result_ref,
        "result_material_ref": material,
        "role_phase": phase,
        "round": state["round"] + 1,
        "target_ref": baseline_ref,
        "issue": {"issues": result["issues"]},
    }
    if phase == "source_intake":
        update["intake_material_ref"] = material
        for unit in current_units(repository, binding):
            if unit["role_id"] == "modeling" and unit["unit_id"] != binding.actor:
                flow.team.send(
                    unit["unit_id"],
                    "Retained actual source intake; reuse applicable propositions and unknowns.",
                    "intake-" + digest([result_ref, unit["unit_id"]])[:24],
                    material_refs=[material],
                )
    current = manager.row()["content"]
    generation = (
        current["units"].get(binding.actor, {}).get("generation", 0)
        if binding.is_child
        else current["root_generation"]
    )
    if generation != binding.data.get("work_generation", 0):
        return flow._save({**update, "status": "work_change_pending"})
    if result["status"] == "waiting_input":
        return flow._wait_for_human(update, "model", result, execution_ref, baseline_ref)
    if result["status"] not in {"proposed", "no_change"}:
        return flow._save({**update, "status": result["status"]})
    try:
        if phase == "source_intake":
            return flow._save(
                {**update, "status": "proposal_ready", "intake_material_ref": material}
            )
        if binding.role == "coordinator" and phase == "plan":
            _install_scope(flow, artifact, artifact_ref, material)
            return flow._save({**update, "status": "waiting_children", "role_phase": "integrate"})
        if binding.role == "competency-question":
            flow._save({**update, "status": "proposal_ready"})
            _refresh_cq(flow, artifact_ref, material, artifact, phase)
            return repository.get(flow.work_id)["content"]
        if binding.role == "modeling":
            proposal = {**result, **artifact}
            candidate_ref = repository.put_reference(
                identity + ":proposal", "candidate", proposal, 0
            )
            return flow._save(
                {
                    **update,
                    "status": "proposal_ready",
                    "candidate_ref": candidate_ref,
                    "candidate_basis_ref": baseline_ref,
                }
            )
        composed = compose_integration(binding, repository, artifact, result["basis"])
        if binding.is_child:
            # Intermediate Coordinators forward authored references, never become Modeler authors.
            return flow._save(
                {**update, "status": "proposal_ready", "integration_plan_ref": artifact_ref}
            )
        candidate_ref = repository.put_reference(
            identity + ":composition", "candidate", composed, 0
        )
        return flow._save(
            {
                **update,
                "activity": "apply" if composed["status"] == "proposed" else "self_check",
                "status": "ready",
                "candidate_ref": candidate_ref,
                "candidate_basis_ref": baseline_ref,
                "integration_plan_ref": artifact_ref,
            }
        )
    except FrameworkError as error:
        owner = error.detail.get("owner_work_id")
        if owner and error.code in {
            "contribution_model_basis_changed",
            "contribution_scope_changed",
            "contribution_source_changed",
            "model_contribution_invalid",
        }:
            flow.team.send(
                owner,
                "Reassess this exact contribution against its changed basis: "
                + json.dumps(error.as_dict()),
                "basis-" + digest([result_ref, owner])[:24],
                material_refs=[material],
            )
            manager.reopen(owner, error.code)
        return flow._save({**update, "status": "recoverable_issue", "issue": error.as_dict()})


def application_receipts(flow, state):
    """Deliver the actual receipt with the persisted original-owner/ID map."""
    if not state.get("operation_ref") or not state.get("integration_plan_ref"):
        return
    receipt = flow.repository.read_reference(state["operation_ref"])
    if receipt.get("status") != "completed":
        return
    candidate = flow.repository.read_reference(state["candidate_ref"])
    identity = flow.binding.identity + ":role-application:" + digest(state["operation_ref"])
    if flow.repository.get(identity):
        return
    target = flow.bridge.call("snapshot", {})
    material = flow.team.publish(
        "receipt-" + digest(state["operation_ref"])[:24],
        text=json.dumps(
            {
                "operation_ref": state["operation_ref"],
                "receipt": receipt,
                "target": target,
                "integration_plan_ref": state["integration_plan_ref"],
                "origins": candidate["origins"],
            },
            ensure_ascii=False,
        ),
    )
    manager = WorkPlan(flow.binding.data, flow.repository)
    plan = manager.row()["content"]
    for owner in {o["owner_work_id"] for o in candidate["origins"].values()}:
        flow.control.enqueue(
            flow.team.prefix + "receipt-" + digest([state["operation_ref"], owner])[:24],
            "input",
            "Actual receipt and original contribution/ID mapping; check your governed scope.",
            owner,
            metadata={
                "source": "agent",
                "author": flow.binding.actor,
                "phase": "self_check",
                "run_id": flow.binding.data["run_id"],
                "material_refs": [material],
            },
        )
    cq = plan["units"]["cq-public"]

    def update(current):
        selected = current["units"]["cq-public"]
        if current.get("cq_application_ref") != state["operation_ref"]:
            selected.update(generation=selected["generation"] + 1, work_phase="review")
            current["cq_application_ref"] = state["operation_ref"]

    manager.change(update)
    flow.team.send(
        cq["unit_id"],
        "Refresh public CQ support/unknowns using this actual governed revision.",
        "receipt-cq-" + digest(state["operation_ref"])[:24],
        material_refs=[material],
    )
    flow.repository.put_reference(
        identity,
        "role_application",
        {
            "operation_ref": state["operation_ref"],
            "integration_plan_ref": state["integration_plan_ref"],
            "contribution_refs": candidate["contribution_refs"],
            "origins": candidate["origins"],
            "target": target,
            "material_ref": material,
        },
        0,
    )


def application_failure(flow, state):
    receipt = flow.repository.read_reference(state["operation_ref"])
    if receipt.get("status") != "not_written":
        return
    candidate = flow.repository.read_reference(state["candidate_ref"])
    material = flow.team.publish(
        "application-error-" + digest(state["operation_ref"])[:24],
        text=json.dumps(
            {
                "operation_ref": state["operation_ref"],
                "receipt": receipt,
                "origins": candidate["origins"],
            },
            ensure_ascii=False,
        ),
    )
    failed = {
        identity
        for error in receipt.get("errors", [])
        for identity in (
            [error["change_id"]] if error.get("change_id") else error.get("change_ids", [])
        )
    }
    owners = {
        origin["owner_work_id"]
        for identity, origin in candidate["origins"].items()
        if not failed or identity in failed
    }
    manager = WorkPlan(flow.binding.data, flow.repository)
    for owner in owners:
        flow.team.send(
            owner,
            "The Host confirmed not_written. Correct your own contribution; preserve semantic meaning and actual receipts.",
            "not-written-" + digest([state["operation_ref"], owner])[:24],
            material_refs=[material],
        )
        manager.reopen(
            owner, "application_needs_correction: " + state["operation_ref"]["object_id"]
        )


def before_self_check(flow, state):
    application_receipts(flow, state)
    plan = WorkPlan(flow.binding.data, flow.repository).row()["content"]
    target = flow.bridge.call("snapshot", {})
    if plan.get("public_cq_review_basis") != {
        "cq_ref": plan.get("public_cq_ref"),
        "model_revisions": target["model_revisions"],
        "source_manifest_digest": flow.binding.data["source_manifest_digest"],
    }:
        cq_work = flow.repository.get("run:" + flow.binding.data["run_id"] + ":unit:cq-public:work")
        if (
            cq_work
            and cq_work["content"].get("status") == "proposal_ready"
            and cq_work["content"].get("work_generation", 0)
            == plan["units"]["cq-public"]["generation"]
        ):
            # no_change still requires the specialist's actual current support review.
            def update(current):
                cq = current["units"]["cq-public"]
                cq.update(generation=cq["generation"] + 1, work_phase="review")

            WorkPlan(flow.binding.data, flow.repository).change(update)
        return flow._save(
            {
                **state,
                "status": "waiting_children",
                "issue": {"code": "public_cq_readback_pending", "owner_work_id": "cq-public"},
            }
        )
    return None


def current_units(repository, binding):
    plan = repository.get("run:" + binding.data["run_id"] + ":work-plan")["content"]
    return [unit for unit in plan["units"].values() if unit["status"] == "active"]


def pending_units(flow, plan):
    pending = []
    applications = flow.repository.list_kind("role_application")
    work = flow.repository.get(flow.work_id)["content"]
    current = (
        flow.repository.read_reference(work["candidate_ref"]) if work.get("candidate_ref") else {}
    )
    for unit in plan["units"].values():
        if unit["status"] != "active" or unit.get("work_phase") == "source_intake":
            continue
        if unit["parent_id"] != flow.binding.actor and flow.binding.is_child:
            continue
        identity = "run:" + flow.binding.data["run_id"] + ":unit:" + unit["unit_id"] + ":work"
        row = flow.repository.get(identity)
        state = row["content"] if row else {}
        if (
            state.get("status") != "proposal_ready"
            or state.get("work_generation", 0) != unit["generation"]
        ):
            pending.append(unit["unit_id"])
            continue
        if unit["role_id"] != "modeling":
            continue
        ref = state.get("role_result_ref")
        if not ref:
            pending.append(unit["unit_id"])
            continue
        result = flow.repository.read_reference(ref)
        request = (
            flow.repository.read_reference(result["changes_ref"])
            if result.get("changes_ref")
            else {"changes": []}
        )
        needed = {change["change_id"] for change in request["changes"]}
        applied = {
            origin["change_id"]
            for application in applications
            for origin in application["content"]["origins"].values()
            if origin.get("result_ref") == ref and "change_id" in origin
        }
        if needed - applied or (not needed and ref not in current.get("contribution_refs", [])):
            pending.append(unit["unit_id"])
    return pending
