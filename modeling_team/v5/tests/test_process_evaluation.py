import json

import pytest

from ontoweave_modeling.contracts import FrameworkError, TaskBinding
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.process_evaluation import (
    DIMENSIONS,
    ProcessEvaluation,
    satisfaction,
    validate_report,
)


def submission(workspace, point="cq", units=None):
    ref = workspace.put_reference("stage-cq", "semantic_record", {"body": "Approved questions"}, 0)
    return {
        "point": point,
        "scope": "whole goal",
        "goal": "source-grounded",
        "unit_ids": units or [],
        "source_ids": ["source"],
        "artifact_refs": [ref],
    }


def report(basis, point="cq", score=3):
    return {
        "binding_digest": basis,
        "dimensions": [
            {
                "dimension": d,
                "status": "scored",
                "score": score,
                "expectation": "source condition",
                "finding": "preserved",
                "evidence": ["source:0"],
                "gap": "",
                "impact": "none",
                "priority": "none",
            }
            for d in DIMENSIONS[point]
        ],
        "combination_cases": [],
        "unexamined": [],
        "key_gaps": [],
    }


def actor(binding, calls, *, score=3, unknown=False):
    def invoke(root, purpose, prompt, inputs):
        assert purpose == "process_evaluation" and inputs == []
        calls.append(root)
        if unknown:
            raise FrameworkError("unknown_native", layer="runtime/infrastructure")
        prompt = json.loads(prompt)
        events = root / "agent/events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        folder = binding.root / "process-evaluations" / prompt["binding_digest"] / "materials"
        reads = []
        for mid, m in prompt["materials"].items():
            text = (folder / m["path"]).read_text()
            reads.append(
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "type": "mcpToolCall",
                            "status": "completed",
                            "tool": "read_material",
                            "arguments": {"material_id": mid},
                            "result": {
                                "structuredContent": {
                                    "sha256": m["sha256"],
                                    "offset": 0,
                                    "text": text,
                                    "total_characters": len(text),
                                }
                            },
                        }
                    },
                }
            )
        events.write_text("\n".join(json.dumps(r) for r in reads))
        return {
            "status": "completed",
            "final_response": json.dumps(report(prompt["binding_digest"], score=score)),
        }

    return invoke


def test_task_configuration_default_and_validation(task_file, tmp_path):
    task = json.loads(task_file.read_text())
    task["process_evaluation"] = {"enabled": True, "points": ["cq"]}
    task_file.write_text(json.dumps(task))
    assert TaskBinding.prepare(task_file, tmp_path / "enabled").data["process_evaluation"][
        "enabled"
    ]
    task["process_evaluation"]["points"] = ["invalid"]
    task_file.write_text(json.dumps(task))
    with pytest.raises(FrameworkError, match="process_evaluation_point_invalid"):
        TaskBinding.prepare(task_file, tmp_path / "invalid")


def test_disabled_no_capture_or_call(binding, workspace):
    process = ProcessEvaluation(binding, workspace)
    assert process.submit({"point": "cq"})["state"] == "disabled"
    assert process.records() == [] and not process.root.exists()


@pytest.mark.parametrize("units", [[], ["modeling"], ["modeling", "bounded-unit"]])
def test_submission_replay_versions_and_switch(binding, workspace, units):
    process = ProcessEvaluation(binding, workspace)
    process.configure(True)
    s = submission(workspace, units=units)
    first = process.submit(s)
    assert first == process.submit(s)
    assert len(process.records()) == 1
    process.configure(False)
    assert process.records()[0]["content"]["state"] == "cancelled"
    process = ProcessEvaluation(binding, workspace)
    process.configure(True)
    assert process.submit(s)["state"] == "cancelled"
    new = process.submit({**s, "reevaluation_id": "explicit-2"})
    assert new["state"] == "queued" and len(process.records()) == 2
    assert process.records()[0]["content"].get("superseded_by") or process.records()[1][
        "content"
    ].get("superseded_by")


def test_completed_replay_and_late_summary(binding, workspace):
    p = ProcessEvaluation(binding, workspace)
    p.configure(True)
    record = p.submit(submission(workspace))
    first = p.summary("failed")
    calls = []
    result = p.run(record["binding_digest"], invoke=actor(binding, calls))
    assert result["state"] == "completed" and result["satisfaction"] == "satisfied"
    assert p.run(record["binding_digest"], invoke=actor(binding, calls)) == result
    assert len(calls) == 1
    late = p.summary("failed")
    assert late["version"] > first["version"]
    assert (p.root / "summary-0001.json").exists()
    assert p.summary("paused")["report"]["production_complete"] is False
    assert len(late["report"]["stages"]) == 3


def test_drift_cannot_use_current_source(binding, workspace):
    p = ProcessEvaluation(binding, workspace)
    p.configure(True)
    record = p.submit(submission(workspace))
    (binding.materials / "source.md").write_text("Changed")
    calls = []
    result = p.run(record["binding_digest"], invoke=actor(binding, calls))
    assert result["state"] == "failed" and not calls
    assert result["error"]["code"] == "process_source_version_unavailable"


def test_unknown_inflight_reconciles_original_identity(binding, workspace):
    p = ProcessEvaluation(binding, workspace)
    p.configure(True)
    record = p.submit(submission(workspace))
    calls = []
    assert (
        p.run(record["binding_digest"], invoke=actor(binding, calls, unknown=True))["state"]
        == "running"
    )
    assert p.run(record["binding_digest"], invoke=actor(binding, calls))["state"] == "running"
    assert len(calls) == 1
    p.configure(False)
    assert TaskControl(workspace).view()["active"]


def test_task_stop_and_budget_reject_without_production_restart(binding, workspace):
    p = ProcessEvaluation(binding, workspace)
    p.configure(True)
    record = p.submit(submission(workspace))
    control = TaskControl(workspace)
    control.enqueue("stop", "stop")
    calls = []
    result = p.run(record["binding_digest"], invoke=actor(binding, calls))
    assert result["state"] == "failed" and not calls
    assert control.view()["mode"] == "stopped"


def test_integration_missing_actual_keeps_unverified(binding, workspace):
    p = ProcessEvaluation(binding, workspace)
    p.configure(True)
    record = p.submit(submission(workspace, "integration"))
    assert record["state"] == "unverified" and "actual_model_not_reached" in record["reason"]


def test_private_artifacts_forbidden(binding, workspace):
    p = ProcessEvaluation(binding, workspace)
    p.configure(True)
    s = submission(workspace)
    s["artifact_refs"] = [
        workspace.put_reference("private", "process_evaluation", {"answer": "secret"}, 0)
    ]
    with pytest.raises(FrameworkError, match="process_artifact_forbidden"):
        p.submit(s)


@pytest.mark.parametrize("point", DIMENSIONS)
@pytest.mark.parametrize(
    "score,expected", [(0, "gaps"), (1, "gaps"), (2, "gaps"), (3, "satisfied"), (4, "satisfied")]
)
def test_score_anchors_and_gaps(point, score, expected):
    r = report("basis", point, score)
    if point == "integration":
        r["combination_cases"] = [
            {
                "scenario": "missing upstream condition",
                "expected": "block",
                "actual": "block",
                "evidence": ["source"],
            }
        ]
    validate_report(r, point, "basis")
    assert satisfaction(r) == expected
    r["key_gaps"] = ["missing overall constraint"]
    assert satisfaction(r) == "gaps"
    r["key_gaps"] = []
    r["dimensions"][0].update(status="unverified", score=None)
    assert satisfaction(r) == ("unverified" if score >= 3 else "gaps")
    r["dimensions"][0]["score"] = 3
    with pytest.raises(FrameworkError, match="process_unknown_must_not_score"):
        validate_report(r, point, "basis")


def test_queued_budget_pause_blocks_without_call(binding, workspace):
    p = ProcessEvaluation(binding, workspace)
    p.configure(True)
    record = p.submit(submission(workspace))
    TaskControl(workspace).enqueue("budget-pause", "budget_pause")
    calls = []
    result = p.run(record["binding_digest"], invoke=actor(binding, calls))
    assert result["state"] == "failed" and not calls
    assert TaskControl(workspace).view()["budget_open"] is False


def test_fixed_artifact_version_and_saved_source_survive_drift(binding, workspace):
    p = ProcessEvaluation(binding, workspace)
    p.configure(True)
    s = submission(workspace)
    record = p.submit(s)
    folder, _ = p._materials(record)
    workspace.put_reference("stage-cq", "semantic_record", {"body": "Different later questions"}, 1)
    (binding.materials / "source.md").write_text("Later changed source")
    assert "Approved questions" in (folder / "stage-artifact-0.json").read_text()
    calls = []
    assert p.run(record["binding_digest"], invoke=actor(binding, calls))["state"] == "completed"


def test_integration_reads_actual_body_and_combination(binding, workspace):
    class Bridge:
        def call(self, action, payload=None):
            return {"model_revisions": {"ontology": 1}, "resource_bindings": {}}

    p = ProcessEvaluation(binding, workspace, Bridge())
    p.configure(True)
    record = p.submit(submission(workspace, "integration"))

    def invoke(root, purpose, prompt, inputs):
        actor(binding, [])(root, purpose, prompt, inputs)
        event = {
            "method": "item/completed",
            "params": {
                "item": {
                    "status": "completed",
                    "tool": "query_semantic_context",
                    "arguments": {},
                    "result": {
                        "structuredContent": {
                            "scope": {
                                "ontologies": [{"ontology_id": "ontology", "model_revision": 1}]
                            },
                            "primary_matches": [
                                {
                                    "iri": "urn:rule",
                                    "ontology_id": "ontology",
                                    "data": {
                                        "semantic_definition": "Accept AND sign before settlement"
                                    },
                                }
                            ],
                        }
                    },
                }
            },
        }
        with (root / "agent/events.jsonl").open("a") as stream:
            stream.write("\n" + json.dumps(event))
        r = report(record["binding_digest"], "integration")
        r["combination_cases"] = [
            {
                "scenario": "Accepted without signature",
                "expected": "blocked",
                "actual": "blocked",
                "evidence": ["urn:rule"],
            }
        ]
        return {"status": "completed", "final_response": json.dumps(r)}

    result = p.run(record["binding_digest"], invoke=invoke)
    assert result["state"] == "completed" and result["satisfaction"] == "satisfied"


def test_summary_uses_original_budget_units_and_preserves_unknown(binding, workspace, tmp_path):
    from ontoweave_modeling.contracts import digest

    p = ProcessEvaluation(binding, workspace)
    budget = tmp_path / "budget"
    budget.mkdir()
    binding.data["authorization"] = {"mode": "amount", "budget_ref": str(budget)}
    execution = "test-process-execution"
    directory = binding.root / "executions" / execution
    source_prefix = "v5-" + digest(str(directory))[:24]
    workspace.put_reference(
        "test-execution",
        "execution",
        {
            "intent": {"execution_id": execution, "purpose": "process_evaluation"},
            "state": "finished",
        },
        0,
    )
    assert p.summary()["report"]["usage"][0]["cost"] is None
    (budget / "state.json").write_text(
        json.dumps(
            {
                "units": {
                    "one": {"amount": "0.12", "source": {"source_id": source_prefix + "-upstream"}},
                    "host": {"amount": "2.00", "source": {"source_id": "external-host"}},
                }
            }
        )
    )
    assert p.summary()["report"]["usage"][0]["cost"] == "0.12"
