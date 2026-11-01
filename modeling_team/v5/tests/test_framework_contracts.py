"""Frozen inputs and references are contracts, not semantic quality judgments."""

import json
import subprocess
from pathlib import Path

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


def test_frozen_method_reuses_multiview_business_guidance_and_semantics(task_file, tmp_path):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    instructions = binding.data["instructions"]
    root = Path(__file__).resolve().parents[3]
    skill = (root / "modeling_team/skills/ontology-modeling/SKILL.md").read_text()
    for heading, following in (
        ("## Read approved business inputs", "## Resolve consequential gaps"),
        ("## Design a coherent scenario", "## Coordinate viewpoints and shared changes"),
        ("## Coordinate viewpoints and shared changes", "### Report current progress"),
    ):
        section = skill.split(heading, 1)[1].split(following, 1)[0].strip()
        assert section in instructions
    contract = json.loads(
        instructions.split("Technical representation contracts (not business sources):\n", 1)[1]
    )
    semantics = json.loads(
        (root / "modeling_team/references/r4-0-012-modeling-contract.json").read_text()
    )
    for name in (
        "reusable_action_semantics",
        "process_binding_semantics",
        "business_rule_semantics",
        "interface_mapping",
    ):
        assert contract[name] == semantics[name]
    assert "root work unit carries the integration responsibility" in instructions
    assert TaskBinding.load(binding.root).data["instructions"] == instructions


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
    assert "owl:NamedIndividual" in contract["semantic_level"]
    assert "Class/relation_type" in contract["semantic_level"]


def test_new_binding_includes_neutral_candidate_shape_without_legacy_workflow(task_file, tmp_path):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    raw = binding.data["instructions"].split(
        "Technical representation contracts (not business sources):\n", 1
    )[1]
    contract = json.loads(raw)
    candidate = contract["candidate"]
    assert candidate["fields"] == [
        "schema_version",
        "scenario_id",
        "candidate_id",
        "revision",
        "items",
        "explicit_unknowns",
    ]
    assert candidate["item_fields"] == [
        "item_id",
        "item_kind",
        "business_meaning",
        "value",
        "relation_endpoints",
        "slice_ids",
        "shared_scope",
        "unknowns",
    ]
    assert "semantic_definition" in candidate["item_optional_fields"]
    assert "metric_definition" in candidate["item_kinds"]
    metric = contract["metric_definition_payload"]
    assert {"name", "grain", "time_field", "aggregation", "denominator_rule"} <= set(
        metric["required"]
    )
    assert "metric_id" not in metric["fields"]
    assert metric["fields"]["time_field"]["format"] == "absolute-rdf-iri"
    assert "stage3_slot" not in contract
    assert "approvals" not in contract


def test_new_binding_exposes_complete_relational_mapping_payloads(task_file, tmp_path):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    raw = binding.data["instructions"].split(
        "Technical representation contracts (not business sources):\n", 1
    )[1]
    contract = json.loads(raw)
    table = contract["table_mapping_payload"]
    assert {"name", "table_name", "column_mappings", "schema_source"} <= set(table["required"])
    assert table["exactly_one_required"] == ["mapped_class_iri", "mapped_definition_iri"]
    assert "table_mapping_id" not in table["fields"]
    assert table["fields"]["mapping_definition"]["items"] == (
        "relational_mapping_structures.mapping_definition.table_mapping"
    )
    join = contract["join_mapping_payload"]
    assert {"relation_type_iri", "join_direction", "join_path", "schema_source"} <= set(
        join["required"]
    )
    assert "join_mapping_id" not in join["fields"]
    assert join["fields"]["mapping_definition"]["items"] == (
        "relational_mapping_structures.mapping_definition.join_mapping"
    )
    structures = contract["relational_mapping_structures"]
    assert "column_mappings[*].property_iri" in structures["reference_inputs"]["paths"]
    assert (
        "mapping_definition.identifiers[*].property_iri" in structures["reference_inputs"]["paths"]
    )
    assert "join_path[*].from_mapping_iri" in structures["reference_inputs"]["paths"]
    assert (
        "mapping_definition.step_semantics[*].condition_rule_iri"
        in structures["reference_inputs"]["paths"]
    )
    assert structures["column_mapping"]["required"] == ["column"]
    assert structures["column_mapping"]["role"] == ["value", "business_key"]
    assert structures["join_step"]["table_form_fields"] == [
        "from_table",
        "to_table",
        "from_columns",
        "to_columns",
    ]
    assert "field_meanings" in structures["mapping_definition"]["table_mapping"]["fields"]
    assert "step_semantics" in structures["mapping_definition"]["join_mapping"]["fields"]


def test_mapping_input_reference_shapes_and_example_are_executable(task_file, tmp_path):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    contract = json.loads(
        binding.data["instructions"].split(
            "Technical representation contracts (not business sources):\n", 1
        )[1]
    )
    for kind, names in {
        "table_mapping": ("mapped_class_iri", "mapped_definition_iri"),
        "join_mapping": ("relation_type_iri",),
    }.items():
        for name in names:
            field = contract[kind + "_payload"]["fields"][name]
            assert field["type"] == "object"
            assert field["compiled_format"] == "absolute-rdf-iri"
            assert field["exactly_one_required"] == ["definition_ref", "existing_resource_ref"]
    example = contract["relational_request_example"]
    column = example["candidate"]["items"][0]["value"]["column_mappings"][0]
    assert "existing_resource_ref" in column["property_iri"]
    assert {x["item_id"] for x in example["candidate"]["items"]} == {
        x["item_id"] for x in example["changes"]["changes"]
    }
    assert all(x["fields"] is None for x in example["changes"]["changes"])
    repo = Path(__file__).resolve().parents[3]
    backend_python = repo / "backend/.venv/bin/python"
    if not backend_python.exists():
        pytest.skip("canonical candidate validator requires the existing backend environment")
    result = subprocess.run(
        [
            str(backend_python),
            "-c",
            (
                "import json,sys; "
                "from modeling_team.direct_modeling import compile_model_changes; "
                "example=json.load(sys.stdin); "
                "example['changes']['candidate_ref']='candidate.json'; "
                "batches,_=compile_model_changes(example['changes'], candidate=example['candidate'], "
                "ontology_by_item={x['item_id']:'ontology-1' for x in example['candidate']['items']}, "
                "resolve_binding=lambda ref: {'ontology_id':'ontology-1', "
                "'resource_iri':'https://example.test'+ref['path'], 'resource_id':ref['path']}); "
                "assert batches[0]['items'][0]['payload']['column_mappings'][0]['property_iri'] "
                "== 'https://example.test/actual-property'"
            ),
        ],
        check=False,
        input=json.dumps(example),
        text=True,
        capture_output=True,
        cwd=repo,
    )
    assert result.returncode == 0, result.stdout + result.stderr


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


@pytest.mark.parametrize("target", ["work", "record"])
def test_source_digest_feedback_allows_exact_correction(binding, workspace, target):
    from ontoweave_modeling.semantic_workspace import SemanticWorkspace

    expected = binding.data["source_manifest"]["source"]["sha256"]
    reference = {"material_id": "source", "sha256": "0" * 64}
    space = SemanticWorkspace(workspace, binding.data)

    def submit(ref):
        if target == "record":
            return space.write(
                "source-review", "material_review", "Review", "Source read", source_refs=[ref]
            )
        return decode_work_result(
            json.dumps(
                {
                    "status": "no_change",
                    "candidate": None,
                    "changes": None,
                    "source_refs": [ref],
                    "issues": [],
                    "consumed_ids": [],
                }
            ),
            binding.data["source_manifest"],
        )

    with pytest.raises(FrameworkError) as caught:
        submit(reference)
    assert caught.value.code == "source_reference_mismatch"
    assert caught.value.detail["expected_sha256"] == expected
    assert caught.value.detail["actual_sha256"] == "0" * 64
    assert reference["sha256"] == "0" * 64
    assert submit({"material_id": "source", "sha256": expected})
