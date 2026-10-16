"""API graph authoring/approval contracts; fixtures do not prove real API semantics."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.acceptance_runtime import (
    v3_examiner_proxy_schemas,
    validate_examiner_proxy_arguments,
)
from modeling_team.contracts import load_multi_slice_team_configuration
from modeling_team.protocol_mechanics import (
    build_candidate_receipt,
    build_unified_resource_binding_receipt,
    translate_candidate_to_batches,
)
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.staged_decisions import (
    build_approval_projection,
    candidate_item_digest,
    canonical_json_digest,
    projection_digest,
    validate_unified_candidate,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "modeling_team/references/r4-0-011-api-mapping-contract.json"


def candidate():
    return json.loads(CONTRACT.read_text())["neutral_example"]


def unified_candidate():
    return json.loads(CONTRACT.read_text())["unified_example"]


def unified_plan(value, *, semantic_base_iri=None):
    """Protocol-authored materialization using the existing complete approved values."""
    neutral = dict(
        candidate_kind="platform-neutral-candidate-v3",
        candidate_revision=value["revision"],
        scope=value["scenario_id"],
        constraints=[],
        items=[],
    )
    for row in value["items"]:
        semantic = deepcopy(row["value"])
        for field in (
            "semantic_definition",
            "parameter_definition",
            "action_definition",
        ):
            if field in row:
                semantic[field] = deepcopy(row[field])
        neutral["items"].append(
            dict(
                item_id=row["item_id"],
                item_kind="predicate"
                if row["item_kind"] == "property"
                else row["item_kind"],
                semantic=semantic,
            )
        )
    return translate_candidate_to_batches(neutral, semantic_base_iri=semantic_base_iri)


def commands(plan):
    return [item for batch in plan["batches"] for item in batch["items"]]


def test_active_roles_mount_interface_contract():
    refs = ROOT / "modeling_team/references"
    authoring, role = [
        json.loads((refs / name).read_text())
        for name in (
            "platform-neutral-candidate-authoring.json",
            "r4-0-012-modeling-contract.json",
        )
    ]
    assert authoring["interface_mapping"] == role["interface_mapping"]
    config = load_multi_slice_team_configuration(
        ROOT / "modeling_team/profiles/r3-0-011-competency-question.yaml",
        ROOT / "modeling_team/tasks/r4-0-012-tracing-suspension.yaml",
    )
    runner = TeamRunner(repository_root=ROOT, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(
        configuration=config, protocol_context=None, gate_binding=None
    )
    runner._competency_questions = True
    for name in ("coordinator", "modeling", "protocol"):
        source = next(
            s
            for s in config.task.role_sources
            if s.path == CONTRACT and name in s.roles
        )
        assert (
            f"/agent/home/sources/{source.relative_path.as_posix()}"
            in runner._task_text(name)
        )
        package = next(a.package for a in config.profile.agents if a.agent_id == name)
        assert CONTRACT.name in package.instructions_path.read_text()


def test_active_consumer_operation_read_matches_actual_v3_schema_and_current_defaults():
    _, instructions, _ = CodexRuntimeAdapter._child_package_assets(
        "platform", ROOT, v3_batch=True
    )
    assert instructions == (
        ROOT / "modeling_team/agent-packages/v3-acceptance-batch/platform-examiner.md"
    )
    scope = {"project_id": "example-project", "ticket_digest": "a" * 64}
    arguments = {
        **scope, "scope_mode": "ontologies", "ontology_ids": ["example-ontology"],
        "query": "https://example.org/operation/example",
        "resource_types": ["operation"], "context_detail": "full",
    }
    schema = v3_examiner_proxy_schemas(["query_semantic_context"])[
        "query_semantic_context"
    ]
    normalized = validate_examiner_proxy_arguments(
        "query_semantic_context", arguments, schema, scope=scope
    )
    assert normalized["resource_types"] == ["operation"]
    assert normalized["context_detail"] == "full"
    assert normalized["ontology_ids"] == ["example-ontology"]
    # Omitted filters now retain all current kinds, matching the backend;
    # explicit Operation selection remains usable in the same authorized scope.
    omitted = {key: value for key, value in arguments.items() if key != "resource_types"}
    defaulted = validate_examiner_proxy_arguments(
        "query_semantic_context", omitted, schema, scope=scope
    )
    assert "operation" in defaulted["resource_types"]


@pytest.mark.parametrize("form", ["neutral", "unified"])
def test_complete_candidates_and_approval_preserve_fields_edges_and_unknowns(form):
    if form == "neutral":
        value = candidate()
        assert build_candidate_receipt(value)["status"] == "accepted"
        plan = translate_candidate_to_batches(value)
    else:
        value = unified_candidate()
        assert validate_unified_candidate(value) == ()
        plan = unified_plan(value)
    assert not plan["conflicts"]
    items = commands(plan)
    payloads = {i["client_item_id"]: i["payload"] for i in items}
    assert payloads["path-id"]["parameter_definition"]["direction"] == "input"
    assert payloads["task-id"]["parameter_definition"]["direction"] == "output"
    assert payloads["items"]["parameter_definition"]["cardinality"] == "collection"
    assert (
        "completion"
        not in payloads["accepted"]["semantic_definition"]["business_meaning"]
    )
    assert (
        "not a catalog object"
        in payloads["accepted"]["semantic_definition"]["business_meaning"]
    )
    assert payloads["unknown-body"]["properties"]["bodyStatus"] == "unknown"
    assert payloads["no-body"]["properties"]["bodyStatus"] == "none"
    if form == "neutral":
        assert payloads["binding"]["properties"]["bindingId"] == "reserve-v2"
    projection = build_approval_projection(
        task_id="r4-0-012-tracing-suspension",
        scenario_id="catalog",
        session_id="fixture",
        client_batch_id="approved-api",
        ontology_id="owned-fixture",
        candidate_id="api",
        candidate_revision=1,
        candidate_digest=canonical_json_digest(value),
        items=items,
        decision_bindings=[],
        identity_bindings=[],
    )
    assert [i["payload"] for i in projection["items"]] == [i["payload"] for i in items]
    changed = deepcopy(projection)
    next(i for i in changed["items"] if i["client_item_id"] == "path-id")["payload"][
        "parameter_definition"
    ]["required"] = False
    assert projection_digest(changed) != projection_digest(projection)
    assert "definition_ref" not in json.dumps(items)


def test_reference_error_is_located_and_repairable():
    value = candidate()
    edge = next(i for i in value["items"] if i["item_kind"] == "relation")
    edge["semantic"]["object"] = {"definition_ref": "missing"}
    errors = translate_candidate_to_batches(value)["conflicts"]
    assert errors[0]["item_id"] == edge["item_id"]
    assert errors[0]["code"] == "unbound_definition_reference"
    assert not translate_candidate_to_batches(candidate())["conflicts"]
    unified = unified_candidate()
    next(i for i in unified["items"] if i["item_kind"] == "relation")["value"][
        "object"
    ] = {"definition_ref": "missing"}
    assert (
        validate_unified_candidate(unified)[0].reason_code
        == "missing_candidate_reference"
    )


def test_wrong_business_position_is_not_a_platform_structure_error():
    value = candidate()
    edge = next(
        i
        for i in value["items"]
        if i["item_kind"] == "relation"
        and i["semantic"]["subject"] == {"definition_ref": "map-call-original"}
        and i["semantic"]["predicate"] == "forParameter"
    )
    old = candidate_item_digest(edge)
    edge["semantic"]["object"] = {"definition_ref": "replacement"}
    assert not translate_candidate_to_batches(value)["conflicts"]
    assert candidate_item_digest(edge) != old
    # A structurally valid but wrong object binding needs semantic review, never a PASS claim.


@pytest.mark.parametrize("kind", ["operation", "table_mapping"])
def test_existing_resource_binding_reuses_actual_kind_with_current_namespace(kind):
    value = dict(
        candidate_kind="platform-neutral-candidate-v3",
        candidate_revision=1,
        scope="existing catalog",
        constraints=[],
        items=[
            dict(
                item_id="p",
                item_kind="predicate",
                semantic={"predicate": "linked", "predicate_kind": "relation"},
            ),
            dict(
                item_id="ref",
                item_kind="existing_resource_ref",
                semantic={"semantic_id": "existing", "resource_kind": kind},
            ),
            dict(
                item_id="edge",
                item_kind="relation",
                semantic={
                    "subject": {
                        "existing_resource_ref": {
                            "semantic_id": "existing",
                            "resource_kind": kind,
                        }
                    },
                    "predicate": "linked",
                    "object": {
                        "existing_resource_ref": {
                            "semantic_id": "existing",
                            "resource_kind": kind,
                        }
                    },
                },
            ),
        ],
    )
    iri = "https://governed.test/" + kind + "/existing"
    receipt = build_unified_resource_binding_receipt(
        value,
        {
            "resources": [
                {
                    "semantic_id": "existing",
                    "resource_kind": kind,
                    "resource_iri": iri,
                    "read_evidence": {"source": "governed"},
                    "project_id": "p",
                    "ontology_id": "o",
                    "model_revision": 1,
                }
            ]
        },
        project_id="p",
        ontology_id="o",
        model_revision=1,
    )
    plan = translate_candidate_to_batches(
        value,
        existing_binding_receipt=receipt,
        requirement_id="R4.0-010",
        semantic_base_iri="https://current.test/semantic/",
    )
    assert not plan["conflicts"]
    assert receipt["bindings"][0]["resource_kind"] == kind
    relation = next(i for i in commands(plan) if i["command_kind"] == "create_relation")
    assert relation["payload"]["source_entity_iri"] == iri
    assert relation["payload"]["target_entity_iri"] == iri
