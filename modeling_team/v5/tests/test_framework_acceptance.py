"""Report mechanics may reject a false PASS, but never assign the semantic verdict."""

import hashlib
import json

import pytest

from ontoweave_modeling.acceptance import validate_report
from ontoweave_modeling.contracts import FrameworkError


@pytest.fixture
def frozen_report(tmp_path):
    handoff = {
        "target": {"model_revisions": {"ontology": 3}},
        "evaluation": {"freeze_id": "freeze", "sha256": "a" * 64, "case_count": 1},
        "source_revisions": {"source": "b" * 64},
    }
    report = {
        "verdict": "PASS",
        "freeze_id": "freeze",
        "model_revisions": {"ontology": 3},
        "cases": [
            {
                "index": 1,
                "passed": True,
                "actual_answer": "Actual governed answer",
                "reason": "Independently assessed",
                "evidence_iris": ["urn:actual:resource"],
            }
        ],
    }
    events = []
    for material_id, sha in [("frozen-questions", "a" * 64), ("source", "b" * 64)]:
        events.append(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "tool": "read_material",
                        "status": "completed",
                        "arguments": {"material_id": material_id},
                        "result": {
                            "structuredContent": {"text": "authorized content", "sha256": sha}
                        },
                    }
                },
            }
        )
    events.append(
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "tool": "query_semantic_context",
                    "status": "completed",
                    "result": {
                        "structuredContent": {
                            "ok": True,
                            "scope": {
                                "ontologies": [{"ontology_id": "ontology", "model_revision": 3}]
                            },
                        }
                    },
                }
            },
        }
    )
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(map(json.dumps, events)))
    return report, handoff, path, events


def test_valid_report_public_projection_contains_no_hidden_answers(frozen_report):
    report, handoff, path, _ = frozen_report
    public = validate_report(report, handoff, path)
    assert public["verdict"] == "PASS" and public["total"] == 1
    assert "actual_answer" not in json.dumps(public) and "reason" not in json.dumps(public)


def test_actual_rest_governed_response_needs_no_synthetic_ok_field(frozen_report):
    report, handoff, path, events = frozen_report
    data = events[-1]["params"]["item"]["result"]["structuredContent"]
    data.pop("ok")
    data["result_status"] = "complete"
    path.write_text("\n".join(map(json.dumps, events)))
    assert validate_report(report, handoff, path)["verdict"] == "PASS"


@pytest.mark.parametrize(
    "defect", ["missing_case", "wrong_revision", "failed_case", "wrong_freeze"]
)
def test_false_binding_or_coverage_does_not_publish_pass(frozen_report, defect):
    report, handoff, path, _ = frozen_report
    if defect == "missing_case":
        report["cases"] = []
    elif defect == "wrong_revision":
        report["model_revisions"] = {"ontology": 4}
    elif defect == "failed_case":
        report["cases"][0]["passed"] = False
    else:
        report["freeze_id"] = "different-freeze"
    with pytest.raises(FrameworkError):
        validate_report(report, handoff, path)


@pytest.mark.parametrize(
    "defect", ["tool_error", "wrong_revision", "failed_envelope", "missing_source"]
)
def test_tool_completion_is_not_successful_governed_or_source_read(frozen_report, defect):
    report, handoff, path, events = frozen_report
    item = events[-1]["params"]["item"]
    if defect == "tool_error":
        item["error"] = {"message": "Forbidden"}
    elif defect == "wrong_revision":
        item["result"]["structuredContent"]["scope"]["ontologies"][0]["model_revision"] = 4
    elif defect == "failed_envelope":
        item["result"]["structuredContent"]["ok"] = False
    else:
        events.pop(1)
    path.write_text("\n".join(map(json.dumps, events)))
    with pytest.raises(FrameworkError):
        validate_report(report, handoff, path)


def test_evaluation_format_retry_preserves_freeze_and_does_not_advance_production(
    task_file,
    tmp_path,
    workspace,
    monkeypatch,
):
    from ontoweave_modeling import cli
    from ontoweave_modeling.contracts import TaskBinding, write_json
    from ontoweave_modeling.control import TaskControl

    questions = b'{"cases":["first", "second"]}'
    question_sha = hashlib.sha256(questions).hexdigest()
    task = json.loads(task_file.read_text())
    task["evaluation"]["sha256"] = question_sha
    task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    source = binding.data["source_manifest"]["source"]
    handoff = {
        "target": {"model_revisions": {"ontology": 3}},
        "evaluation": binding.data["evaluation"],
        "source_revisions": {"source": source["sha256"]},
    }
    ref = workspace.put_reference(binding.identity + ":handoff", "handoff", handoff, 0)
    work = {"status": "handoff_ready", "handoff_ref": ref}
    workspace.put_reference(binding.identity + ":work", "work_unit", work, 0)
    package = tmp_path / "independent-inputs"
    package.mkdir()
    (package / "source.md").write_bytes((binding.root / "materials/source.md").read_bytes())
    (package / "questions.json").write_bytes(questions)
    write_json(
        package / "manifest.json",
        {
            "source": source,
            "frozen-questions": {
                "path": "questions.json",
                "source_ref": "independent-freeze",
                "sha256": question_sha,
            },
        },
    )
    calls = []

    class IndependentActor:
        def __init__(self, binding, bridge, **kwargs):
            assert kwargs["materials"] != binding.root / "materials"
            assert kwargs["model_revisions"] == {"ontology": 3}

        def __call__(self, root, purpose, prompt, inputs):
            calls.append(root.name)
            assert purpose == "acceptance" and not inputs
            folder = root / "agent"
            folder.mkdir()
            events = []
            for material_id, sha in [
                ("source", source["sha256"]),
                ("frozen-questions", question_sha),
            ]:
                events.append(
                    {
                        "method": "item/completed",
                        "params": {
                            "item": {
                                "tool": "read_material",
                                "status": "completed",
                                "arguments": {"material_id": material_id},
                                "result": {
                                    "structuredContent": {"text": "test content", "sha256": sha}
                                },
                            }
                        },
                    }
                )
            events.append(
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "tool": "query_semantic_context",
                            "status": "completed",
                            "result": {
                                "structuredContent": {
                                    "ok": True,
                                    "scope": {
                                        "ontologies": [
                                            {"ontology_id": "ontology", "model_revision": 3}
                                        ]
                                    },
                                }
                            },
                        }
                    },
                }
            )
            (folder / "events.jsonl").write_text("\n".join(map(json.dumps, events)))
            report = {
                "verdict": "PASS",
                "freeze_id": task["evaluation"]["freeze_id"],
                "model_revisions": {"ontology": 3},
                "cases": [
                    {
                        "index": index,
                        "passed": True,
                        "actual_answer": "Test answer",
                        "reason": "Test-only judgment",
                        "evidence_iris": ["urn:test"],
                    }
                    for index in (1, 2)
                ],
            }
            return {
                "status": "completed",
                "final_response": "bad JSON" if len(calls) == 1 else json.dumps(report),
            }

    class Platform:
        def call(self, action):
            assert action == "snapshot"
            return {"model_revisions": {"ontology": 3}}

    monkeypatch.setattr(cli, "CodexInvocation", IndependentActor)
    TaskControl(workspace).enqueue("production-input", "input", "Pending production correction")
    with pytest.raises(FrameworkError, match="evaluation_report_needs_correction"):
        cli.evaluate(binding, workspace, Platform(), package, "evaluation-1")
    assert (
        cli.evaluate(binding, workspace, Platform(), package, "evaluation-1")["verdict"] == "PASS"
    )
    cli.evaluate(binding, workspace, Platform(), package, "evaluation-1")
    assert len(calls) == 2 and calls[0] != calls[1]
    assert workspace.get(binding.identity + ":work")["content"] == work
    control = TaskControl(workspace).view()
    assert not control["active"] and control["messages"][0]["status"] == "queued"
