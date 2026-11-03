"""Independent R5.0-011 boundary tests; never paid-model quality evidence."""

import json
from contextlib import contextmanager

import pytest

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.execution import CodexInvocation
from ontoweave_modeling.process_evaluation import DIMENSIONS, ProcessEvaluation, satisfaction
from ontoweave_modeling.team import TeamChannel


def stage(workspace, point="cq"):
    ref = workspace.put_reference(
        "independent-stage",
        "candidate",
        {"condition": "acceptance AND signature before payment"},
        0,
    )
    return {
        "point": point,
        "scope": "installation-to-payment",
        "goal": "preserve conjunction",
        "source_ids": ["source"],
        "artifact_refs": [ref],
        "unit_ids": [],
    }


def fixed_report(basis, point="cq"):
    return {
        "binding_digest": basis,
        "dimensions": [
            {
                "dimension": name,
                "status": "scored",
                "score": 3,
                "expectation": "acceptance AND signature before payment",
                "finding": "conjunction retained",
                "evidence": ["source#condition"],
                "gap": "",
                "impact": "none",
                "priority": "none",
            }
            for name in DIMENSIONS[point]
        ],
        "key_gaps": [],
        "unexamined": [],
        "combination_cases": [
            {
                "scenario": "accepted but unsigned",
                "expected": "blocked",
                "actual": "blocked",
                "evidence": ["source#condition"],
            }
        ],
    }


def native(binding, point="cq", malformed=False):
    def invoke(root, purpose, prompt, inputs):
        prompt = json.loads(prompt)
        folder = binding.root / "process-evaluations" / prompt["binding_digest"] / "materials"
        reads = []

        def add(tool, arguments, body):
            reads.append(
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "status": "completed",
                            "tool": tool,
                            "arguments": arguments,
                            "result": {"structuredContent": body},
                        }
                    },
                }
            )

        for mid, entry in prompt["materials"].items():
            text = (folder / entry["path"]).read_text()
            add(
                "read_material",
                {"material_id": mid},
                {
                    "text": text,
                    "offset": 0,
                    "total_characters": len(text),
                    "sha256": entry["sha256"],
                },
            )
        if point == "integration":
            add(
                "query_semantic_context",
                {},
                {
                    "scope": {"ontologies": [{"ontology_id": "ontology", "model_revision": 1}]},
                    "primary_matches": [
                        {
                            "iri": "urn:condition",
                            "ontology_id": "ontology",
                            "data": {"label": "payment allowed"},
                        }
                    ],
                },
            )
        (root / "agent").mkdir(parents=True, exist_ok=True)
        (root / "agent/events.jsonl").write_text("\n".join(json.dumps(e) for e in reads))
        report = fixed_report(prompt["binding_digest"], point)
        if malformed:
            report["dimensions"] = None
        return {"status": "completed", "final_response": json.dumps(report)}

    return invoke


@pytest.mark.parametrize("point", ["cq", "slicing"])
def test_planning_diagnostic_does_not_require_platform(binding, tmp_path, monkeypatch, point):
    class NoPlatform:
        def call(self, action, payload=None):
            raise FrameworkError("platform_scope_not_prepared")

        @contextmanager
        def provider(self, *args):
            yield "http://unused"

    class Agent:
        def __init__(self, *args, **kwargs):
            assert kwargs.get("platform_config") is None
            assert kwargs["allowed_tools"] == ("read_material",)

        def start(self):
            pass

        def run_turn(self, prompt):
            return {"status": "completed", "final_response": "{}"}

        def close(self):
            pass

    monkeypatch.setattr("ontoweave_modeling.codex_agent.CodexAgent", Agent)
    root = tmp_path / "native"
    root.mkdir()
    result = CodexInvocation(
        binding, NoPlatform(), read_only=True, model_revisions={}, materials_only=True
    )(root, "process_evaluation", point, [])
    assert result["status"] == "completed", result


def test_integration_label_only_is_insufficient(binding, workspace):
    class Platform:
        def call(self, action, payload=None):
            assert action == "snapshot"
            return {
                "model_revisions": {"ontology": 1},
                "resource_bindings": {
                    "condition": {"ontology_id": "ontology", "resource_iri": "urn:condition"}
                },
            }

    process = ProcessEvaluation(binding, workspace, Platform())
    process.configure(True)
    record = process.submit(stage(workspace, "integration"))
    result = process.run(record["binding_digest"], invoke=native(binding, "integration"))
    assert result["state"] != "completed" or result.get("satisfaction") != "satisfied", result


def test_malformed_dimensions_is_recoverable_record(binding, workspace):
    process = ProcessEvaluation(binding, workspace)
    process.configure(True)
    record = process.submit(stage(workspace))
    result = process.run(record["binding_digest"], invoke=native(binding, malformed=True))
    assert result["state"] == "failed" and result.get("error")


def test_existing_handoff_material_can_be_submitted(binding, workspace):
    process = ProcessEvaluation(binding, workspace)
    process.configure(True)
    reference = TeamChannel(binding.data, workspace, TaskControl(workspace)).publish(
        "cq-output", text="Approved CQ v1"
    )
    submitted = process.submit({**stage(workspace), "artifact_refs": [reference]})
    assert submitted["state"] == "queued"


def test_late_summary_preserves_production_terminal(binding, workspace):
    process = ProcessEvaluation(binding, workspace)
    process.configure(True)
    record = process.submit(stage(workspace))
    process.summary("failed")
    assert process.run(record["binding_digest"], invoke=native(binding))["state"] == "completed"
    current = workspace.get(process.prefix + "summary")["content"]["report"]
    assert current["production_status"] == "failed" and current["production_complete"] is True


@pytest.mark.parametrize("point", DIMENSIONS)
def test_fixed_source_gap_and_unknown_never_satisfied(point):
    report = fixed_report("frozen", point)
    report["dimensions"][0].update(score=1, gap="signature precondition absent", priority="high")
    assert satisfaction(report) == "gaps"
    report = fixed_report("frozen", point)
    report["dimensions"][0].update(
        status="unverified", score=None, finding="missing historical body"
    )
    assert satisfaction(report) == "unverified"


def test_disable_during_budget_sync_prevents_native_admission(binding, workspace, monkeypatch):
    import ontoweave_modeling.execution as execution

    process = ProcessEvaluation(binding, workspace)
    process.configure(True)
    record = process.submit(stage(workspace))
    calls = []

    def disable_before_admission(*args, **kwargs):
        process.configure(False)

    def unexpected_invoke(*args):
        calls.append("native_started_after_disable")
        return native(binding)(*args)

    monkeypatch.setattr(execution, "synchronize_budget", disable_before_admission)
    result = process.run(record["binding_digest"], invoke=unexpected_invoke)
    assert process.settings()["enabled"] is False
    assert calls == []
    assert result["state"] == "cancelled", result
    assert TaskControl(workspace).view()["active"] == {}
    assert workspace.list_kind("execution") == []
