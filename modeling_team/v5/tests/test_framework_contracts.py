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
    with pytest.raises(FileExistsError):
        TaskBinding.prepare(task_file, root)


def test_unsupported_authorization_never_creates_run(task_file, tmp_path):
    task = json.loads(task_file.read_text())
    task["authorization"]["mode"] = "amount"
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


def test_versioned_references_do_not_follow_current_business_revision(workspace):
    original = workspace.put_reference("candidate", "candidate", {"text": "first"}, 0)
    workspace.put_reference("candidate", "candidate", {"text": "second"}, 1)
    assert workspace.read_reference(original)["text"] == "first"
    assert workspace.get("candidate")["revision"] == 2
    wrong = {**original, "digest": "0" * 64}
    with pytest.raises(FrameworkError, match="record_digest_mismatch"):
        workspace.read_reference(wrong)
