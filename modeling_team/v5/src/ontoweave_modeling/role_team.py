"""The concrete role-team/v1 contract, frozen inputs and deterministic integration.

This extends the existing work tree; it is not a second runner or a semantic judge.
"""

from __future__ import annotations

import copy
from pathlib import Path

from .contracts import (
    HUMAN_REQUESTS_SCHEMA,
    RESOLVED_REQUESTS_SCHEMA,
    WORK_RESULT_SCHEMA,
    FrameworkError,
    digest,
    safe_id,
    validate_schema,
)

TEAM_CONTRACT = "role-team/v1"
ROLE_KINDS = {
    "coordinator": "coordination",
    "competency-question": "cq_public",
    "modeling": "slice_modeling",
}


def object_schema(properties, required=None):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties) if required is None else required,
    }


STR = {"type": "string", "minLength": 1}
STRINGS = {"type": "array", "items": STR}
REF = object_schema(
    {"object_id": STR, "revision": {"type": "integer", "minimum": 1}, "digest": STR}
)
NULL_REF = {"anyOf": [REF, {"type": "null"}]}
REFS = {"type": "array", "items": REF}
SOURCE_REFS = WORK_RESULT_SCHEMA["properties"]["source_refs"]
BASIS = object_schema(
    {
        "source_manifest_digest": STR,
        "scope_ref": NULL_REF,
        "cq_ref": NULL_REF,
        "shared_refs": REFS,
        "model_revisions": {"type": "object", "additionalProperties": {"type": "integer"}},
        "consumed_refs": REFS,
    }
)
ASSIGNMENT = object_schema(
    {
        "unit_id": STR,
        "role_id": {"enum": list(ROLE_KINDS)},
        "objective": STR,
        "material_ids": STRINGS,
        "dependencies": STRINGS,
        "instructions": {"type": "string"},
        "scope_id": STR,
    }
)
SCOPE_PLAN = object_schema(
    {
        "schema_version": {"const": "scope-plan/v1"},
        "scope": STR,
        "assignments": {"type": "array", "items": ASSIGNMENT},
        "shared_definitions": {
            "type": "array",
            "items": object_schema(
                {
                    "definition_id": STR,
                    "maintainer_unit_id": STR,
                    "user_unit_ids": STRINGS,
                    "decision": STR,
                }
            ),
        },
        "unassigned": STRINGS,
        "confirmation_points": STRINGS,
        "integration_obligations": STRINGS,
    }
)
PUBLIC_CQ = object_schema(
    {
        "schema_version": {"const": "public-cq-set/v1"},
        "questions": {
            "type": "array",
            "items": object_schema(
                {
                    "cq_id": STR,
                    "question": STR,
                    "coverage_kind": {"enum": ["panorama", "slice", "cross_slice"]},
                    "scope_ids": STRINGS,
                    "source_refs": SOURCE_REFS,
                    "reference_answer": {"type": ["string", "null"]},
                    "criteria_status": {"enum": ["draft", "confirmed", "unknown"]},
                    "answer_author": {"type": ["string", "null"]},
                }
            ),
        },
        "reused_ids": STRINGS,
        "revised_ids": STRINGS,
        "new_ids": STRINGS,
        "unknowns": STRINGS,
        "coverage_gaps": STRINGS,
    }
)
PUBLIC_CQ["properties"]["model_support"] = {
    "type": "array",
    "items": object_schema(
        {
            "cq_id": STR,
            "status": {"enum": ["supported", "conditional", "unsupported", "unverified"]},
            "evidence": STRINGS,
        }
    ),
}
INTAKE = object_schema(
    {
        "schema_version": {"const": "source-intake/v1"},
        "propositions": {"type": "array", "minItems": 1, "items": STR},
        "unknowns": STRINGS,
    }
)
# Decode the professional envelope without collapsing canonical candidate issues
# into a first-error JSON-schema message. The role boundary then reuses the full
# pure candidate validator; representation compilation still belongs to the Host.
MODEL_CANDIDATE = {
    "type": ["object", "null"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": STR,
                    "item_kind": STR,
                    "relation_endpoints": {"type": ["object", "null"]},
                },
                "required": ["item_id", "item_kind"],
            },
        },
        "explicit_unknowns": {"type": "array"},
    },
    "required": ["items"],
}
MODEL_CHANGES = {
    "type": ["object", "null"],
    "properties": {
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "change_id": STR,
                    "action": {"enum": ["create", "update", "delete"]},
                    "resource_kind": STR,
                    "item_id": {"type": ["string", "null"]},
                    "fields": {"type": ["object", "null"]},
                },
                "required": ["change_id", "action", "resource_kind"],
            },
        },
    },
    "required": ["changes"],
}
CONTRIBUTION = object_schema(
    {
        "candidate": MODEL_CANDIDATE,
        "changes": MODEL_CHANGES,
        "ontology_targets": WORK_RESULT_SCHEMA["properties"]["ontology_targets"],
        "review_units": STRINGS,
        "shared_conflicts": STRINGS,
        "public_cq_disposition": STR,
    }
)
INTEGRATION = object_schema(
    {
        "schema_version": {"const": "integration-plan/v1"},
        "plan_id": STR,
        "contributions": {
            "type": "array",
            "items": object_schema(
                {
                    "owner_work_id": STR,
                    "generation": {"type": "integer", "minimum": 0},
                    "result_ref": REF,
                    "candidate_ref": NULL_REF,
                    "changes_ref": NULL_REF,
                    "selected_change_ids": STRINGS,
                }
            ),
        },
        "shared_decision_refs": REFS,
        "deferred": {
            "type": "array",
            "items": object_schema(
                {
                    "owner_work_id": STR,
                    "reason": STR,
                    "depends_on": STRINGS,
                }
            ),
        },
        "ontology_targets": {"type": "object", "additionalProperties": STR},
        "check_units": STRINGS,
    }
)
# Recursive Coordinator plans retain their leaf authors; these are plan references,
# never candidates authored by the Coordinator.
INTEGRATION["properties"]["coordination_refs"] = REFS


def result_schema(binding, phase):
    artifact = (
        INTAKE
        if phase == "source_intake"
        else SCOPE_PLAN
        if binding.role == "coordinator" and phase == "plan"
        else INTEGRATION
        if binding.role == "coordinator"
        else PUBLIC_CQ
        if binding.role == "competency-question"
        else CONTRIBUTION
    )
    return object_schema(
        {
            "schema_version": {"const": "role-work-result/v1"},
            "status": {
                "enum": [
                    "proposed",
                    "no_change",
                    "waiting_input",
                    "waiting_children",
                    "waiting_peer",
                    "recoverable_issue",
                ]
            },
            "basis": BASIS,
            "artifact": {"anyOf": [artifact, {"type": "null"}]},
            "artifact_ref": NULL_REF,
            "source_refs": SOURCE_REFS,
            "issues": STRINGS,
            "consumed_ids": WORK_RESULT_SCHEMA["properties"]["consumed_ids"],
            "human_requests": HUMAN_REQUESTS_SCHEMA,
            "resolved_request_ids": RESOLVED_REQUESTS_SCHEMA,
        },
        ["schema_version", "status", "basis", "artifact", "source_refs", "issues", "consumed_ids"],
    )


def freeze_team(data, task_instructions):
    from .contracts import modeling_instructions

    if data.get("collaboration"):
        raise FrameworkError(
            "role_team_peer_contract_unsupported",
            instruction="Use typed work_units for production responsibilities.",
        )
    data.update(work_management=True, semantic_workspace=True)
    packages = {}
    directory = Path(__file__).resolve().parents[2] / "instructions"
    technical = modeling_instructions(task_instructions).split(
        "Technical representation contracts (not business sources):", 1
    )[1]
    for role, filename in (
        ("coordinator", "coordinator.md"),
        ("competency-question", "competency-question.md"),
        ("modeling", "modeler.md"),
    ):
        path = directory / filename
        if not path.is_file():
            raise FrameworkError("role_package_missing", role_id=role, path=str(path))
        instructions = path.read_text() + "\n\nTask-specific instructions:\n" + task_instructions
        if role == "modeling":
            instructions += (
                "\n\nTechnical representation contracts (not business sources):" + technical
            )
        package = {
            "version": TEAM_CONTRACT,
            "instructions": instructions,
            "tools": list(production_tools(data, role)),
        }
        packages[role] = {**package, "sha256": digest(package)}
    units = data.get("work_units", [])
    for unit in units:
        if unit.get("role_id") not in ROLE_KINDS:
            raise FrameworkError("work_role_required", unit_id=unit["unit_id"])
        unit.setdefault("work_kind", ROLE_KINDS[unit["role_id"]])
        unit.setdefault("actor_id", unit["unit_id"])
        unit.setdefault("parent_id", "coordinator")
    if {u["unit_id"] for u in units} & {"coordinator", "cq-public", "modeler"}:
        raise FrameworkError("work_unit_identity_conflict")
    units = [
        {
            "unit_id": "modeler",
            "actor_id": "modeler",
            "role_id": "modeling",
            "work_kind": "slice_modeling",
            "work_phase": "source_intake",
            "parent_id": "coordinator",
            "objective": data["objective"],
            "material_ids": list(data["source_manifest"]),
            "dependencies": [],
        },
        {
            "unit_id": "cq-public",
            "actor_id": "cq-public",
            "role_id": "competency-question",
            "work_kind": "cq_public",
            "work_phase": "produce",
            "parent_id": "coordinator",
            "objective": "Review/reuse and maintain the public competency questions for: "
            + data["objective"],
            "material_ids": list(data["source_manifest"]),
            "dependencies": [],
        },
        *units,
    ]
    data.update(
        role_packages=packages,
        work_units=units,
        work_management=True,
        semantic_workspace=True,
        role_id="coordinator",
        actor_id="coordinator",
        work_kind="coordination",
        task_instructions=task_instructions,
        instructions=packages["coordinator"]["instructions"],
    )
    for unit in units:
        if set(unit.get("material_ids", [])) - data["source_manifest"].keys():
            raise FrameworkError("material_forbidden", unit_id=unit["unit_id"])
    validate_units({"units": {u["unit_id"]: u for u in units}, "root_actor": "coordinator"}, data)


def production_tools(task, role):
    from .semantic_workspace import WORKSPACE_TOOLS
    from .team import TEAM_TOOLS
    from .work_plan import WORK_TOOLS

    if role not in ROLE_KINDS:
        raise FrameworkError("role_not_allowed", role_id=role)
    if task.get("role_packages"):
        return tuple(task["role_packages"][role]["tools"])
    tools = ("read_material", "query_semantic_context", "read_model_resource") + TEAM_TOOLS
    tools += WORK_TOOLS
    if task.get("semantic_workspace"):
        tools += WORKSPACE_TOOLS
    return tools


def validate_units(plan, task):
    """Validate actionable routing/dependency errors, never a semantic slice decision."""
    root = "coordinator"
    units = plan["units"]
    for unit_id, unit in units.items():
        safe_id(unit_id)
        role = unit.get("role_id")
        if (
            role not in ROLE_KINDS
            or unit.get("work_kind") != ROLE_KINDS[role]
            or unit.get("actor_id", unit_id) != unit_id
        ):
            raise FrameworkError("work_role_invalid", unit_id=unit_id)
        if unit["parent_id"] != root and unit["parent_id"] not in units:
            raise FrameworkError("work_parent_missing", unit_id=unit_id)
        missing = set(unit.get("dependencies", [])) - units.keys()
        if missing:
            raise FrameworkError(
                "work_dependency_missing", unit_id=unit_id, missing=sorted(missing)
            )
    for edge in ("dependencies", "parent_id"):

        def visit(identity, stack, edge=edge):
            if identity == root:
                return
            if identity in stack:
                raise FrameworkError(
                    "work_dependency_cycle" if edge == "dependencies" else "work_tree_cycle",
                    cycle=[*stack, identity],
                )
            unit = units[identity]
            following = unit.get(edge, []) if edge == "dependencies" else [unit[edge]]
            for dependency in following:
                visit(dependency, [*stack, identity])

        for unit_id in units:
            visit(unit_id, [])


def qualified_id(owner, result_object_id, local_id, kind):
    return kind + "-" + digest([owner, result_object_id, local_id])[:32]


def target_changes_conflict(left, right):
    if (
        left["action"] == right["action"] == "update"
        and isinstance(left.get("fields"), dict)
        and isinstance(right.get("fields"), dict)
    ):
        return any(
            left["fields"][key] != right["fields"][key]
            for key in left["fields"].keys() & right["fields"].keys()
        )
    return True


# Only the current compiler's declared reference slots carry technical local IDs.
# Semantic definitions, literal property values, physical identifiers and arbitrary
# business JSON are copied unchanged, even if a key happens to say definition_ref.
MAPPING_REFS = {
    "external_field_iri",
    "target_iri",
    "import_run_iri",
    "mapped_class_iri",
    "mapped_definition_iri",
    "relation_type_iri",
    "property_iri",
    "table_mapping_iri",
    "semantic_value",
    "time_field",
    "measure_property_iri",
    "from_mapping_iri",
    "to_mapping_iri",
    "conversion_rule_iri",
    "condition_rule_iri",
    "base_mapping_iri",
    "join_mapping_iris",
    "conversion_rule_iris",
    "target_resource_type_iri",
    "grain",
    "mapped_class",
    "mapped_class_ref",
    "mapped_definition",
    "mapped_definition_ref",
    "relation_type",
    "relation_type_ref",
    "property_ref",
    "table_mapping_ref",
    "semantic_value_ref",
    "time_field_ref",
    "measure_property_ref",
}
MAPPING_CONTEXTS = {
    "column_mappings": {"property_iri"},
    "join_path": {"from_mapping_iri", "to_mapping_iri"},
    "filters": {"field"},
    "mapping_definition": MAPPING_REFS,
    "identifiers": {"property_iri", "table_mapping_iri"},
    "property_bindings": {"property_iri", "table_mapping_iri"},
    "field_meanings": {"conversion_rule_iri"},
    "step_semantics": {"condition_rule_iri"},
    "contexts": {"base_mapping_iri", "join_mapping_iris", "conversion_rule_iris"},
    "counted_identity": {"table_mapping_iri"},
}


def _rewrite_fields(value, kind, rewrite_ref, context="root"):
    if isinstance(value, list):
        return [_rewrite_fields(child, kind, rewrite_ref, context) for child in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    fields = (
        {
            "entity": {"class_iri_or_legacy_id", "class_iris"},
            "property": {"object_class_id"},
            "relation": {"predicate"},
            "class": {"parent_class_ids"},
            "relation_type": {"source_class_id", "target_class_id"},
            "fact": {"new_object_value"} if value.get("new_object_is_iri") else set(),
        }.get(kind, MAPPING_REFS)
        if context == "root"
        else MAPPING_CONTEXTS[context]
    )
    result = copy.deepcopy(value)
    for key, child in value.items():
        if key in fields:
            result[key] = rewrite_ref(child)
        elif (
            context == "root"
            and kind == "entity"
            and key == "properties"
            and isinstance(child, list)
        ):
            result[key] = [
                {**entry, "property_ref": rewrite_ref(entry["property_ref"])}
                if isinstance(entry, dict) and "property_ref" in entry
                else entry
                for entry in child
            ]
        elif key in MAPPING_CONTEXTS and (
            context in {"root", "mapping_definition"}
            or (context == "contexts" and key in {"property_bindings", "counted_identity"})
        ):
            result[key] = _rewrite_fields(child, kind, rewrite_ref, key)
    return result


def _expand_coordination(binding, repository, plan, basis, ancestors=()):
    """Flatten fixed nested decisions while preserving each level's read/check duty."""
    from .work_plan import WorkPlan

    validate_schema(plan, INTEGRATION)
    work_plan = WorkPlan(binding.data, repository).row()["content"]
    expanded = copy.deepcopy(plan)
    consumed = list(basis["consumed_refs"])
    direct_owners = {c["owner_work_id"] for c in plan["contributions"]}
    coordination_owners, references = set(), []
    for reference in plan.get("coordination_refs", []):
        result = repository.read_reference(reference)
        owner = result["actor_id"]
        unit = work_plan["units"].get(owner, {})
        work = repository.get("run:" + binding.data["run_id"] + ":unit:" + owner + ":work")
        if (
            owner in ancestors
            or unit.get("role_id") != "coordinator"
            or result["role_id"] != "coordinator"
            or result.get("phase") != "integrate"
            or unit.get("generation") != result["generation"]
            or not work
            or work["content"].get("status") != "proposal_ready"
            or work["content"].get("role_result_ref") != reference
        ):
            raise FrameworkError("coordination_contribution_invalid", owner_work_id=owner)
        if result["basis"]["model_revisions"] != basis["model_revisions"]:
            raise FrameworkError("contribution_model_basis_changed", owner_work_id=owner)
        material = work["content"].get("result_material_ref")
        if material and material not in basis["consumed_refs"]:
            raise FrameworkError(
                "contribution_not_consumed", owner_work_id=owner, material_ref=material
            )
        nested_plan = repository.read_reference(result["artifact_ref"])
        nested, nested_basis, nested_refs = _expand_coordination(
            binding, repository, nested_plan, result["basis"], (*ancestors, owner)
        )
        coordination_owners.add(owner)
        references.extend([reference, *nested_refs])
        expanded["contributions"].extend(nested["contributions"])
        expanded["deferred"].extend(nested["deferred"])
        for identity, target in nested["ontology_targets"].items():
            if (
                identity in expanded["ontology_targets"]
                and expanded["ontology_targets"][identity] != target
            ):
                raise FrameworkError("integration_placement_conflict", change_id=identity)
            expanded["ontology_targets"][identity] = target
        consumed.extend(ref for ref in nested_basis["consumed_refs"] if ref not in consumed)
    required = direct_owners | coordination_owners
    if set(plan["check_units"]) != required:
        raise FrameworkError(
            "original_owner_check_missing",
            owner_work_ids=sorted(required),
            requested_check_units=plan["check_units"],
            instruction="check_units must name exactly the selected original owners. "
            "A Modeling no_change result still needs its exact contribution selection "
            "and selected_change_ids=[]. Copy its actual candidate_ref/changes_ref, "
            "including null only when the retained result has null references. "
            "Public CQ is separate, not a null Modeling contribution.",
        )
    expanded["check_units"] = list(
        dict.fromkeys(c["owner_work_id"] for c in expanded["contributions"])
    )
    return expanded, {**basis, "consumed_refs": consumed}, references


def compose_integration(binding, repository, plan, basis):
    """Select exact authored contributions; rewrite only contract-defined local IDs."""
    validate_schema(plan, INTEGRATION)
    from .work_plan import WorkPlan

    binding = WorkPlan(binding.data, repository).binding(binding)
    original_plan = plan
    plan, basis, coordination_refs = _expand_coordination(binding, repository, plan, basis)
    work_plan = repository.get("run:" + binding.data["run_id"] + ":work-plan")["content"]
    checked_coordinators = {repository.read_reference(ref)["actor_id"] for ref in coordination_refs}
    for contribution in plan["contributions"]:
        lineage = WorkPlan.ancestors(work_plan, contribution["owner_work_id"])
        if binding.actor not in lineage:
            raise FrameworkError(
                "contribution_scope_forbidden", owner_work_id=contribution["owner_work_id"]
            )
        for ancestor in lineage[1 : lineage.index(binding.actor)]:
            if (
                work_plan["units"][ancestor]["role_id"] == "coordinator"
                and ancestor not in checked_coordinators
            ):
                raise FrameworkError("coordination_check_missing", owner_work_id=ancestor)
    items, changes, origins, placements, source_refs, owners, conflicts = [], [], {}, {}, [], [], {}
    candidate_meta = None
    selected_results = []
    seen_changes = set()
    for contribution in plan["contributions"]:
        owner = contribution["owner_work_id"]
        unit = work_plan["units"].get(owner)
        if not unit or unit["role_id"] != "modeling":
            raise FrameworkError("contribution_owner_invalid", owner_work_id=owner)
        result = repository.read_reference(contribution["result_ref"])
        work = repository.get(binding.for_unit(owner).identity + ":work")
        if (
            result["role_id"] != "modeling"
            or result["actor_id"] != owner
            or result["generation"] != unit["generation"]
            or contribution["generation"] != unit["generation"]
            or not work
            or work["content"].get("role_result_ref") != contribution["result_ref"]
            or work["content"].get("status") != "proposal_ready"
            or result["status"] not in {"proposed", "no_change"}
        ):
            raise FrameworkError("contribution_stale_or_wrong_owner", owner_work_id=owner)
        material = work["content"].get("result_material_ref")
        if material and material not in basis["consumed_refs"]:
            raise FrameworkError(
                "contribution_not_consumed", owner_work_id=owner, material_ref=material
            )
        if (
            result["candidate_ref"] != contribution["candidate_ref"]
            or result["changes_ref"] != contribution["changes_ref"]
        ):
            raise FrameworkError("contribution_reference_mismatch", owner_work_id=owner)
        if result["basis"]["model_revisions"] != basis["model_revisions"]:
            raise FrameworkError(
                "contribution_model_basis_changed",
                owner_work_id=owner,
                result_ref=contribution["result_ref"],
            )
        if result["basis"]["scope_ref"] != unit.get("scope_ref", basis["scope_ref"]):
            raise FrameworkError("contribution_scope_changed", owner_work_id=owner)
        for source in result["source_refs"]:
            current_source = binding.data["source_manifest"].get(source["material_id"])
            if not current_source or current_source["sha256"] != source["sha256"]:
                raise FrameworkError(
                    "contribution_source_changed",
                    owner_work_id=owner,
                    material_id=source["material_id"],
                )
        artifact = repository.read_reference(result["artifact_ref"])
        if artifact["shared_conflicts"]:
            raise FrameworkError(
                "contribution_shared_conflict",
                owner_work_id=owner,
                conflicts=artifact["shared_conflicts"],
            )
        raw_candidate = (
            repository.read_reference(result["candidate_ref"]) if result["candidate_ref"] else None
        )
        raw_changes = (
            repository.read_reference(result["changes_ref"]) if result["changes_ref"] else None
        )
        for name, value, schema in (
            ("candidate", raw_candidate, MODEL_CANDIDATE),
            ("changes", raw_changes, MODEL_CHANGES),
        ):
            try:
                validate_schema(value, schema)
            except FrameworkError as error:
                raise FrameworkError(
                    "model_contribution_invalid",
                    owner_work_id=owner,
                    path=[name, *error.detail["path"]],
                    result_ref=contribution["result_ref"],
                ) from error
        if raw_changes is None:
            if contribution["selected_change_ids"]:
                raise FrameworkError("contribution_change_missing", owner_work_id=owner)
            raw_changes = {"changes": []}
        source_changes = {c["change_id"]: c for c in raw_changes["changes"]}
        if len(source_changes) != len(raw_changes["changes"]):
            raise FrameworkError("candidate_change_id_collision", owner_work_id=owner)
        selected = contribution["selected_change_ids"]
        if len(set(selected)) != len(selected) or set(selected) - source_changes.keys():
            raise FrameworkError("contribution_change_missing", owner_work_id=owner)
        for local in selected:
            identity = (
                contribution["result_ref"]["object_id"],
                contribution["result_ref"]["revision"],
                local,
            )
            if identity in seen_changes:
                raise FrameworkError(
                    "contribution_selected_twice", owner_work_id=owner, change_id=local
                )
            seen_changes.add(identity)
        for applied in repository.list_kind("role_application"):
            for original in applied["content"]["origins"].values():
                if (
                    original.get("result_ref") == contribution["result_ref"]
                    or original.get("artifact_ref") == result["artifact_ref"]
                ) and original.get("change_id") in selected:
                    raise FrameworkError(
                        "contribution_already_applied",
                        owner_work_id=owner,
                        change_id=original["change_id"],
                        operation_ref=applied["content"]["operation_ref"],
                    )
        object_id = contribution["result_ref"]["object_id"]
        raw_items = raw_candidate["items"] if raw_candidate else []
        item_ids = [item["item_id"] for item in raw_items]
        if len(set(item_ids)) != len(item_ids):
            raise FrameworkError("candidate_item_id_collision", owner_work_id=owner)
        aliases = {local: qualified_id(owner, object_id, local, "i") for local in item_ids}
        needed = {source_changes[c].get("item_id") for c in selected} - {None}
        if needed - aliases.keys():
            raise FrameworkError("candidate_item_missing", owner_work_id=owner)

        def rewrite(value, *, needed=needed, owner=owner, aliases=aliases):
            if isinstance(value, list):
                return [rewrite(v) for v in value]
            if isinstance(value, dict):
                if set(value) == {"definition_ref"}:
                    ref = value["definition_ref"]
                    if ref not in needed:
                        raise FrameworkError(
                            "integration_reference_not_closed",
                            owner_work_id=owner,
                            definition_ref=ref,
                        )
                    return {**value, "definition_ref": aliases[ref]}
                return copy.deepcopy(value)
            return value

        if raw_candidate:
            if candidate_meta is None:
                candidate_meta = {
                    k: copy.deepcopy(v) for k, v in raw_candidate.items() if k != "items"
                }
            for item in raw_items:
                if item["item_id"] in needed:
                    mapped = copy.deepcopy(item)
                    mapped["item_id"] = aliases[item["item_id"]]
                    mapped["value"] = _rewrite_fields(item.get("value"), item["item_kind"], rewrite)
                    if item.get("relation_endpoints") is not None:
                        for key in ("from_item_id", "to_item_id"):
                            local = item["relation_endpoints"].get(key)
                            if isinstance(local, str):
                                if local not in needed:
                                    raise FrameworkError(
                                        "integration_reference_not_closed",
                                        owner_work_id=owner,
                                        item_id=local,
                                    )
                                mapped["relation_endpoints"][key] = aliases[local]
                            else:
                                mapped["relation_endpoints"][key] = rewrite(local)
                    items.append(mapped)
                    origins[mapped["item_id"]] = {
                        "owner_work_id": owner,
                        "result_ref": contribution["result_ref"],
                        "item_id": item["item_id"],
                    }
        for local in selected:
            original = source_changes[local]
            change = copy.deepcopy(original)
            change["fields"] = _rewrite_fields(
                original.get("fields"), original["resource_kind"], rewrite
            )
            change["change_id"] = qualified_id(owner, object_id, local, "c")
            if original.get("item_id"):
                change["item_id"] = aliases[original["item_id"]]
            if original.get("target_ref") is not None:
                identity = digest(original["target_ref"])
                for other_owner, other_change in conflicts.get(identity, []):
                    if target_changes_conflict(other_change, original):
                        raise FrameworkError(
                            "shared_target_conflict",
                            owners=[other_owner, owner],
                            target_ref=original["target_ref"],
                        )
                conflicts.setdefault(identity, []).append((owner, original))
            changes.append(change)
            origins[change["change_id"]] = {
                "owner_work_id": owner,
                "generation": contribution["generation"],
                "result_ref": contribution["result_ref"],
                "artifact_ref": result["artifact_ref"],
                "change_id": local,
            }
            placement = (artifact.get("ontology_targets") or {}).get(local)
            chosen = plan["ontology_targets"].get(change["change_id"], placement)
            if placement and chosen != placement:
                raise FrameworkError(
                    "integration_placement_conflict", owner_work_id=owner, change_id=local
                )
            if chosen:
                placements[change["change_id"]] = chosen
        source_refs.extend(r for r in result["source_refs"] if r not in source_refs)
        owners.append(owner)
        selected_results.append(contribution["result_ref"])
    if set(owners) - set(plan["check_units"]):
        raise FrameworkError(
            "original_owner_check_missing",
            owner_work_ids=sorted(set(owners) - set(plan["check_units"])),
        )
    if set(plan["check_units"]) - set(owners):
        raise FrameworkError("unit_check_scope_forbidden")
    if unknown := set(plan["ontology_targets"]) - {c["change_id"] for c in changes}:
        raise FrameworkError(
            "integration_placement_unknown",
            unknown_change_ids=sorted(unknown),
            instruction="Use the exact program-returned qualified_change_ids. "
            "With one authorized Ontology, ontology_targets={} uses the existing Host default; "
            "do not retranscribe qualified IDs merely to repeat that placement.",
        )
    candidate = (
        {**candidate_meta, "candidate_id": "integrated-" + digest(plan)[:24], "items": items}
        if candidate_meta
        else None
    )
    if candidate:
        candidate["explicit_unknowns"] = [
            copy.deepcopy(unknown)
            for c in plan["contributions"]
            if c["candidate_ref"]
            for unknown in repository.read_reference(c["candidate_ref"]).get(
                "explicit_unknowns", []
            )
        ]
    return {
        "status": "proposed" if changes else "no_change",
        "candidate": candidate,
        "changes": {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": changes,
        }
        if changes
        else None,
        "ontology_targets": placements or None,
        "source_refs": source_refs,
        "issues": [d["reason"] for d in plan["deferred"]],
        "consumed_ids": [],
        "review_units": original_plan["check_units"],
        "contribution_refs": selected_results,
        "origins": origins,
        "coordination_result_refs": coordination_refs,
    }
