"""Technical metadata alignment preserves approved reads and semantic payloads."""

import json
from copy import deepcopy

import pytest
from modeling_team.direct_modeling import validate_model_change_request
from test_role_team_flow import RoleActors, RolePlatform
from test_role_team_flow import role_binding as role_binding  # noqa: PLC0414

from ontoweave_modeling import role_candidates
from ontoweave_modeling.contracts import FrameworkError, decode_work_result
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.role_artifacts import submit_role_artifact
from ontoweave_modeling.work_plan import WorkPlan


def _changes():
    return {
        "request_id": "copied-technical-id",
        "changes": [
            {
                "change_id": "create-one",
                "action": "create",
                "resource_kind": "class",
                "item_id": None,
                "target_ref": None,
                "fields": {"name": "Approved condition", "description": "AND exception"},
            }
        ],
    }


def _artifact(changes):
    return {
        "candidate": None,
        "changes": changes,
        "ontology_targets": None,
        "review_units": [],
        "shared_conflicts": [],
        "public_cq_disposition": "Unverified public goal",
    }


def test_changes_alignment_copies_only_technical_metadata():
    original = _changes()
    untouched = deepcopy(original)
    normalized = role_candidates.normalize_model_changes(original)
    assert original == untouched
    assert normalized is not original
    assert normalized == {
        "schema_version": "r4-3-025-model-changes/v1",
        "candidate_ref": None,
        "changes": original["changes"],
    }
    assert normalized["changes"] is not original["changes"]
    assert (
        validate_model_change_request(normalized, candidate=None, allow_unbound_candidate_ref=True)
        == []
    )
    assert validate_model_change_request(
        original, candidate=None, allow_unbound_candidate_ref=True
    )  # The direct public validator still rejects the original request.


@pytest.mark.parametrize("value", [None, [], ["invalid-change-shape"]])
def test_changes_alignment_preserves_non_objects(value):
    assert role_candidates.normalize_model_changes(value) == value


@pytest.mark.parametrize("extra", [{"schema_version": "wrong/v1"}, {"unknown_field": True}])
def test_changes_alignment_does_not_repair_wrong_versions_or_unknown_fields(extra):
    original = {**_changes(), **extra}
    normalized = role_candidates.normalize_model_changes(original)
    assert all(normalized[key] == value for key, value in extra.items())
    assert validate_model_change_request(
        normalized, candidate=None, allow_unbound_candidate_ref=True
    )


@pytest.mark.parametrize("extra", [{}, {"schema_version": "wrong/v1"}, {"unknown_field": True}])
def test_staged_modeler_aligns_metadata_and_preserves_strict_validation(
    role_binding, workspace, extra
):
    binding = role_binding.for_unit("modeler")
    artifact = _artifact({**_changes(), **extra})
    original = deepcopy(artifact)
    context = {"execution_id": "metadata-test", "phase": "propose", "basis": {}}
    if extra:
        with pytest.raises(FrameworkError) as caught:
            submit_role_artifact(binding, workspace, context, artifact)
        assert caught.value.code == "model_changes_invalid"
        assert not workspace.list_kind("role_submission")
    else:
        staged = submit_role_artifact(binding, workspace, context, artifact)
        stored = workspace.read_reference(staged["artifact_ref"])
        assert stored["changes"] == {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": original["changes"]["changes"],
        }
        assert stored["public_cq_disposition"] == original["public_cq_disposition"]
    assert artifact == original


@pytest.mark.parametrize("wrong_version", [False, True])
def test_inline_modeler_aligns_changes_without_rewriting_native_result(
    role_binding, workspace, saver, wrong_version
):
    platform = RolePlatform()
    actors = RoleActors(role_binding, workspace, platform)
    parent = WorkUnitFlow(role_binding, workspace, platform, actors.factory(role_binding))
    assert parent.advance(saver)["status"] == "waiting_children"
    binding = WorkPlan(role_binding.data, workspace).binding(role_binding).for_unit("modeler")
    base = actors.factory(binding)
    originals = []

    def invoke(root, purpose, text, inputs):
        native = base(root, purpose, text, inputs)
        result = json.loads(native["final_response"])
        result["artifact"]["changes"] = _changes()
        if wrong_version:
            result["artifact"]["changes"]["schema_version"] = "wrong/v1"
        native["final_response"] = json.dumps(result)
        originals.append(native["final_response"])
        return native

    result = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    if wrong_version:
        assert result["status"] == "recoverable_issue", result
        assert result["issue"]["code"] == "model_changes_required"
    else:
        assert result["status"] == "proposal_ready", result
        envelope = workspace.read_reference(result["role_result_ref"])
        changes = workspace.read_reference(envelope["changes_ref"])
        assert changes == {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": _changes()["changes"],
        }
    assert (
        workspace.read_reference(result["execution_ref"])["result"]["final_response"]
        == originals[0]
    )
    assert not platform.effects


@pytest.mark.parametrize("proof", ["approved", "unread", "wrong_version", "unknown_id"])
def test_source_alignment_requires_approved_manifest_identity_and_actual_version_read(
    role_binding, workspace, saver, proof
):
    platform = RolePlatform()
    base = RoleActors(role_binding, workspace, platform).factory(role_binding)
    originals = []
    observed = []

    def invoke(root, purpose, text, inputs):
        native = base(root, purpose, text, inputs)
        result = json.loads(native["final_response"])
        result["source_refs"][0]["sha256"] = "b" * 64
        if proof == "unknown_id":
            result["source_refs"][0]["material_id"] = "unapproved"
        path = root / "agent/events.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()]
        if proof == "unread":
            events = []
        elif proof == "wrong_version":
            events[0]["params"]["item"]["result"]["structuredContent"]["sha256"] = "b" * 64
        path.write_text("".join(json.dumps(event) + "\n" for event in events))
        observed.append((path, path.read_text()))
        native["final_response"] = json.dumps(result)
        originals.append(native["final_response"])
        return native

    result = WorkUnitFlow(role_binding, workspace, platform, invoke).advance(saver)
    if proof == "approved":
        assert result["status"] == "waiting_children", result
        envelope = workspace.read_reference(result["role_result_ref"])
        assert envelope["source_refs"] == [
            {
                "material_id": "source",
                "sha256": role_binding.data["source_manifest"]["source"]["sha256"],
            }
        ]
    else:
        assert result["status"] == "recoverable_issue", result
        assert result["issue"]["code"] == (
            "source_reference_mismatch" if proof == "unknown_id" else "source_read_missing"
        )
    assert (
        workspace.read_reference(result["execution_ref"])["result"]["final_response"]
        == originals[0]
    )
    assert observed[0][0].read_text() == observed[0][1]
    assert not platform.effects


@pytest.mark.parametrize("complete", [False, True])
def test_source_alignment_reuses_only_complete_admitted_old_reads(
    role_binding, workspace, saver, complete
):
    platform = RolePlatform()
    base = RoleActors(role_binding, workspace, platform).factory(role_binding)
    calls = []

    def invoke(root, purpose, text, inputs):
        native = base(root, purpose, text, inputs)
        result = json.loads(native["final_response"])
        path = root / "agent/events.jsonl"
        calls.append(root)
        if len(calls) == 1:
            result["source_refs"] = []
            if not complete:
                events = [json.loads(line) for line in path.read_text().splitlines()]
                events[0]["params"]["item"]["result"]["structuredContent"]["total_characters"] = 999
                path.write_text("".join(json.dumps(event) + "\n" for event in events))
        else:
            assert json.loads(text)["reusable_read_execution_refs"]
            path.write_text("")
            result["source_refs"][0]["sha256"] = "b" * 64
        native["final_response"] = json.dumps(result)
        return native

    flow = WorkUnitFlow(role_binding, workspace, platform, invoke)
    assert flow.advance(saver)["status"] == "recoverable_issue"
    result = flow.advance(saver)
    if complete:
        assert result["status"] == "waiting_children", result
    else:
        assert result["status"] == "recoverable_issue", result
        assert result["issue"]["code"] == "source_read_missing"
    assert not platform.effects


def test_public_decoder_keeps_strict_source_sha_validation():
    request = {
        "status": "proposed",
        **_artifact({**_changes(), "schema_version": "r4-3-025-model-changes/v1"}),
        "source_refs": [{"material_id": "source", "sha256": "b" * 64}],
        "issues": [],
        "consumed_ids": [],
    }
    with pytest.raises(FrameworkError) as caught:
        decode_work_result(json.dumps(request), {"source": {"sha256": "a" * 64}})
    assert caught.value.code == "source_reference_mismatch"
