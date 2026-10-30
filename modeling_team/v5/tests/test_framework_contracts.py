"""Frozen inputs and references are contracts, not semantic quality judgments."""

import json

import pytest

from ontoweave_modeling.contracts import FrameworkError, TaskBinding, decode_work_result


def test_frozen_binding_keeps_material_and_model_after_original_changes(task_file, tmp_path):
    root = tmp_path / "run"
    binding = TaskBinding.prepare(task_file, root)
    source = task_file.parent / "sources" / "source.md"
    source.write_text("changed original")
    assert TaskBinding.load(root).data == binding.data
    assert (root / "materials" / "source.md").read_text().startswith("A source")
    assert binding.model("modeling").model == "glm-5.3-flash"
    assert "S0/S1" in binding.data["instructions"]
    assert (
        "Technical representation contracts (not business sources):" in binding.data["instructions"]
    )
    assert "Preserve conditions and unknowns." in binding.data["instructions"]
    with pytest.raises(FileExistsError):
        TaskBinding.prepare(task_file, root)


def test_unsupported_authorization_never_creates_run(task_file, tmp_path):
    task = json.loads(task_file.read_text())
    task["authorization"]["mode"] = "unsupported"
    task_file.write_text(json.dumps(task))
    with pytest.raises(FrameworkError, match="authorization_mode_not_implemented"):
        TaskBinding.prepare(task_file, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_changed_snapshot_is_not_silently_resumed(task_file, tmp_path):
    root = tmp_path / "run"
    TaskBinding.prepare(task_file, root)
    (root / "materials" / "source.md").write_text("tampered snapshot")
    with pytest.raises(FrameworkError, match="source_revision_changed"):
        TaskBinding.load(root)


def test_unsupported_provider_is_rejected_before_resource_preparation(task_file, tmp_path):
    profile = task_file.parent / "profile.yaml"
    profile.write_text(profile.read_text().replace("glm-direct", "unimplemented-provider"))
    with pytest.raises(FrameworkError, match="provider_route_not_implemented"):
        TaskBinding.prepare(task_file, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_result_errors_are_recoverable_and_unknown_is_not_a_proposal():
    value = {
        "status": "waiting_input",
        "candidate": None,
        "changes": None,
        "source_refs": [],
        "issues": ["Business meaning is unspecified"],
        "consumed_ids": [],
    }
    assert decode_work_result(json.dumps(value), {}) == value
    value["status"] = "proposed"
    with pytest.raises(FrameworkError, match="model_changes_required") as caught:
        decode_work_result(json.dumps(value), {})
    assert caught.value.recoverable


def test_healthy_peer_wait_does_not_need_an_invented_issue():
    value = {
        "status": "waiting_peer",
        "candidate": None,
        "changes": None,
        "source_refs": [],
        "issues": [],
        "consumed_ids": [],
    }
    assert decode_work_result(json.dumps(value), {}) == value
    value["status"] = "recoverable_issue"
    with pytest.raises(FrameworkError, match="unresolved_reason_required"):
        decode_work_result(json.dumps(value), {})


def test_new_binding_includes_executable_fields_only_request_grammar(task_file, tmp_path):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    raw = binding.data["instructions"].split(
        "Technical representation contracts (not business sources):\n", 1
    )[1]
    contract = json.loads(raw)
    request = contract["request_example"]
    assert set(request) == {"schema_version", "candidate_ref", "changes"}
    assert request["schema_version"] == "r4-3-025-model-changes/v1"
    assert request["changes"][0]["fields"]["name"]
    assert contract["relation_request_example"]["changes"][0]["fields"]["source_class_id"]


def test_wrong_request_envelope_returns_actionable_correction():
    value = {
        "status": "proposed",
        "candidate": None,
        "changes": {"request_id": "r4-3-025-model-changes/v1", "changes": []},
        "source_refs": [{"material_id": "source", "sha256": "a" * 64}],
        "issues": [],
        "consumed_ids": [],
    }
    with pytest.raises(FrameworkError, match="model_changes_required") as caught:
        decode_work_result(json.dumps(value), {"source": {"sha256": "a" * 64}})
    assert caught.value.detail["path"] == "/changes/schema_version"
    assert caught.value.detail["expected"] == "r4-3-025-model-changes/v1"
    assert "candidate_ref" in caught.value.detail["instruction"]


def test_structured_human_question_already_contains_its_reason():
    value = {
        "status": "waiting_input",
        "candidate": None,
        "changes": None,
        "source_refs": [],
        "issues": [],
        "consumed_ids": [],
        "human_requests": [
            {"question": "Which name?", "reason": "Name is unresolved", "impact": "This concept"}
        ],
    }
    assert decode_work_result(json.dumps(value), {}) == value


def test_child_proposal_does_not_need_root_application_fields():
    source = {"source": {"sha256": "a" * 64}}
    value = {
        "status": "proposed",
        "candidate": {"propositions": ["A condition"]},
        "changes": None,
        "source_refs": [{"material_id": "source", "sha256": "a" * 64}],
        "issues": [],
        "consumed_ids": [],
        "waiting_note": "Extra diagnostic text is retained",
    }
    assert decode_work_result(json.dumps(value), source, require_changes=False) == value
    with pytest.raises(FrameworkError, match="model_changes_required"):
        decode_work_result(json.dumps(value), source)


def test_versioned_references_do_not_follow_current_business_revision(workspace):
    original = workspace.put_reference("candidate", "candidate", {"text": "first"}, 0)
    workspace.put_reference("candidate", "candidate", {"text": "second"}, 1)
    assert workspace.read_reference(original)["text"] == "first"
    assert workspace.get("candidate")["revision"] == 2
    wrong = {**original, "digest": "0" * 64}
    with pytest.raises(FrameworkError, match="record_digest_mismatch"):
        workspace.read_reference(wrong)
