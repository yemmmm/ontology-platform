"""Early static validation for staged v5 Modeler changes."""

import json

import pytest
import yaml
from jsonschema import validate
from modeling_team.direct_modeling import (
    compile_model_changes,
    model_change_item_schema,
    validate_model_change_request,
)

from ontoweave_modeling.contracts import FrameworkError, TaskBinding
from ontoweave_modeling.role_artifacts import submit_role_artifact
from ontoweave_modeling.role_team import result_schema


def _item(item_id, item_kind, value):
    return {
        "item_id": item_id,
        "item_kind": item_kind,
        "business_meaning": "An approved business object.",
        "value": value,
        "relation_endpoints": None,
        "slice_ids": ["slice-1"],
        "shared_scope": None,
        "unknowns": [],
    }


def _candidate(items):
    return {
        "schema_version": "r3-0-009-unified-graph/v2",
        "scenario_id": "scenario-1",
        "candidate_id": "candidate-1",
        "revision": 1,
        "items": items,
        "explicit_unknowns": [],
    }


def _relation_candidate():
    return _candidate(
        [
            _item("source", "entity", {"label": "Source"}),
            _item("target", "entity", {"label": "Target"}),
            _item(
                "predicate",
                "property",
                {"name": "links to", "predicate_kind": "relation"},
            ),
            {
                **_item(
                    "link",
                    "relation",
                    {"predicate": {"definition_ref": "predicate"}},
                ),
                "relation_endpoints": {"from_item_id": "source", "to_item_id": "target"},
            },
        ]
    )


@pytest.fixture
def professional_model_binding(task_file, tmp_path):
    task = json.loads(task_file.read_text())
    task["team_contract"] = "role-team/v1"
    task["unit_concurrency"] = 1
    task_file.write_text(json.dumps(task))
    profile_path = task_file.parent / "profile.yaml"
    profile = yaml.safe_load(profile_path.read_text())
    for role in ("coordinator", "competency-question"):
        profile["roles"][role] = dict(profile["roles"]["modeling"])
    profile_path.write_text(yaml.safe_dump(profile))
    return TaskBinding.prepare(task_file, tmp_path / "professional-run").for_unit("modeler")


def _request(changes, *, candidate_ref=None):
    return {
        "schema_version": "r4-3-025-model-changes/v1",
        "candidate_ref": candidate_ref,
        "changes": changes,
    }


def _change(*, item_id, fields):
    return {
        "change_id": "create-item",
        "action": "create",
        "resource_kind": "entity",
        "item_id": item_id,
        "target_ref": None,
        "fields": fields,
    }


def test_preflight_catches_ambiguous_candidate_create_before_host_binding():
    candidate = _candidate([_item("item-1", "entity", {"name": "Approved entity"})])
    errors = validate_model_change_request(
        _request([_change(item_id="item-1", fields={})]),
        candidate=candidate,
        allow_unbound_candidate_ref=True,
    )

    assert [error["code"] for error in errors] == ["change_source_ambiguous"]
    assert errors[0]["change_id"] == "create-item"
    assert errors[0]["path"] == "/changes/0/item_id"


def test_modeler_guidance_reuses_supported_value_and_semantic_fields(
    professional_model_binding,
):
    schema = result_schema(professional_model_binding, "propose", guidance=True)
    item = schema["properties"]["artifact"]["anyOf"][0]["properties"]["candidate"]["properties"][
        "items"
    ]["items"]
    supported = model_change_item_schema()["properties"]["fields"]

    assert item["properties"]["value"]["type"] == "object"
    assert all(
        item["properties"]["value"]["properties"][key] == value
        for key, value in supported["properties"].items()
    )
    assert "predicate" in item["properties"]["value"]["properties"]
    assert item["properties"]["value"]["additionalProperties"] is True
    assert "entity" not in item["properties"]["value"]["properties"]
    assert "iri_local" not in item["properties"]["value"]["properties"]

    semantic = item["properties"]["semantic_definition"]
    assert "business_meaning" in semantic["properties"]
    assert "name" not in semantic["properties"]
    assert "notes" not in semantic["properties"]


def test_modeler_guidance_accepts_neutral_relation_value_and_endpoints(
    professional_model_binding,
):
    candidate = _relation_candidate()
    batches, _ = compile_model_changes(
        _request(
            [
                {
                    "change_id": f"create-{item['item_id']}",
                    "action": "create",
                    "resource_kind": item["item_kind"],
                    "item_id": item["item_id"],
                    "target_ref": None,
                    "fields": None,
                }
                for item in candidate["items"]
            ],
            candidate_ref="candidate.json",
        ),
        candidate=candidate,
        ontology_by_item={item["item_id"]: "ontology-1" for item in candidate["items"]},
        resolve_binding=lambda _ref: None,
    )
    relation = next(item for item in batches[0]["items"] if item["client_item_id"] == "link")
    assert relation["command_kind"] == "create_relation"
    assert relation["payload"] == {
        "source_entity_iri": {
            "item_ref": {"client_item_id": "source", "output": "resource_iri"}
        },
        "relation_type_iri": {
            "item_ref": {"client_item_id": "predicate", "output": "resource_iri"}
        },
        "target_entity_iri": {
            "item_ref": {"client_item_id": "target", "output": "resource_iri"}
        },
    }

    schema = result_schema(professional_model_binding, "propose", guidance=True)
    artifact_schema = schema["properties"]["artifact"]["anyOf"][0]
    artifact = {
        "candidate": candidate,
        "changes": None,
        "ontology_targets": {},
        "review_units": [],
        "shared_conflicts": [],
        "public_cq_disposition": "Draft goals reviewed; support remains unverified.",
    }

    validate(instance=artifact, schema=artifact_schema)

    value = artifact_schema["properties"]["candidate"]["properties"]["items"]["items"][
        "properties"
    ]["value"]
    assert "predicate" in value["properties"]
    assert "relation_endpoints" in artifact_schema["properties"]["candidate"]["properties"][
        "items"
    ]["items"]["properties"]


def test_preflight_keeps_fields_only_creation_valid_without_candidate_ref():
    errors = validate_model_change_request(
        _request(
            [
                {
                    "change_id": "create-class",
                    "action": "create",
                    "resource_kind": "class",
                    "item_id": None,
                    "target_ref": None,
                    "fields": {"name": "Approved class"},
                }
            ]
        ),
        candidate=None,
        allow_unbound_candidate_ref=True,
    )

    assert errors == []


def test_submit_role_artifact_returns_static_change_errors_before_staging(
    professional_model_binding, workspace
):
    binding = professional_model_binding
    artifact = {
        "candidate": _candidate([_item("item-1", "entity", {"name": "Approved entity"})]),
        "changes": _request([_change(item_id="item-1", fields={})]),
        "ontology_targets": {},
        "review_units": [],
        "shared_conflicts": [],
        "public_cq_disposition": "Draft goals reviewed; support remains unverified.",
    }

    with pytest.raises(FrameworkError) as caught:
        submit_role_artifact(
            binding,
            workspace,
            {"execution_id": "execution-1", "phase": "propose", "basis": {}},
            artifact,
        )

    assert caught.value.code == "model_changes_invalid"
    assert caught.value.detail["errors"][0]["code"] == "change_source_ambiguous"
    assert not workspace.list_kind("role_submission")
