"""Custom goals use retained source changes and cannot turn missing criteria into PASS."""

import hashlib
import json

import pytest

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.revisions import SourceRevisions


def snapshot(*, ready=False):
    row = {
        "cq_id": "project-q1",
        "content_revision": 2,
        "question": "各凭证的调用数？",
        "cq_definition": {
            "kind": "custom",
            "criteria_status": "confirmed" if ready else "draft",
            "source_refs": ["source"],
            "acceptance_criteria": ["按凭证统计成功新调用"],
        },
        "criteria_ready": ready,
        "active": True,
        "visibility": "public",
    }

    def encode(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()

    row["content_digest"] = hashlib.sha256(encode(row)).hexdigest()
    value = {
        "schema_version": "ontoweave-cq-snapshot/v1",
        "project_id": "project",
        "questions": [row],
    }
    sha = hashlib.sha256(encode(value)).hexdigest()
    return {**value, "snapshot_id": "cq-" + sha[:24], "sha256": sha}


def test_busy_cq_revision_queues_then_preserves_original_materials(binding, workspace):
    from ontoweave_modeling.custom_cq import CustomCQ

    original = (binding.materials / "source.md").read_bytes()
    control = TaskControl(workspace)
    control.begin_turn("bounded-unit", "native-original")
    cq = CustomCQ(binding, workspace)
    staged = cq.stage(snapshot())
    assert staged["status"] == "queued"
    assert SourceRevisions(binding, workspace).activate().data == binding.data
    assert (binding.materials / "source.md").read_bytes() == original
    control.finish_turn("bounded-unit", "native-original")
    revised = SourceRevisions(binding, workspace).activate()
    assert "cq-goals" in revised.data["source_manifest"]
    assert revised.data["source_manifest"]["cq-goals"]["material_type"] == "competency_goal"
    assert (revised.materials / "source.md").read_bytes() == original
    assert (binding.materials / "source.md").read_bytes() == original
    assert CustomCQ(revised, workspace).stage(snapshot()) is None


def test_cq_snapshot_tampering_is_recoverable_before_any_material_write(binding, workspace):
    from ontoweave_modeling.custom_cq import CustomCQ

    data = snapshot()
    data["questions"][0]["question"] = "偷偷替换题干"
    with pytest.raises(FrameworkError, match="cq_snapshot_digest_mismatch"):
        CustomCQ(binding, workspace).stage(data)
    assert not workspace.list_kind("source_change")


def test_frozen_cq_keeps_stable_identity_and_unready_cases(binding, workspace):
    from ontoweave_modeling.custom_cq import freeze_cases

    freeze = freeze_cases(snapshot(), binding.data["source_manifest"])
    assert len(freeze["questions"]) == 1
    case = freeze["questions"][0]
    assert (case["index"], case["cq_id"], case["content_revision"]) == (1, "project-q1", 2)
    assert case["criteria_ready"] is False
    ready = freeze_cases(snapshot(ready=True), binding.data["source_manifest"])
    assert (
        ready["questions"][0]["source_bindings"]["source"]
        == (binding.data["source_manifest"]["source"]["sha256"])
    )


def test_custom_report_requires_frozen_identity_and_cannot_pass_draft_criteria():
    from ontoweave_modeling.custom_cq import validate_cases

    data = snapshot()
    report = {
        "verdict": "PASS",
        "cases": [
            {
                "index": 1,
                "cq_id": "project-q1",
                "content_revision": 2,
                "content_digest": data["questions"][0]["content_digest"],
                "passed": True,
                "outcome": "pass",
                "answerability": "supported",
                "sql_readiness": "supported",
                "sql_execution": "not_run",
            }
        ],
    }
    with pytest.raises(FrameworkError, match="cq_unready_criteria_cannot_pass"):
        validate_cases(report, data["questions"])
    report["verdict"] = "PARTIAL"
    report["cases"][0].update(
        passed=False,
        outcome="question-answer-review",
        answerability="unverified",
        sql_readiness="unverified",
    )
    result = validate_cases(report, data["questions"])
    assert result[0]["outcome"] == "question-answer-review"
    assert "actual_answer" not in result[0] and "reason" not in result[0]
    report["cases"][0]["cq_id"] = "other-question"
    with pytest.raises(FrameworkError, match="cq_case_binding_mismatch"):
        validate_cases(report, data["questions"])


def test_ready_report_does_not_claim_sql_execution_without_execution_evidence():
    from ontoweave_modeling.custom_cq import validate_cases

    data = snapshot(ready=True)
    case = data["questions"][0]
    report = {
        "verdict": "PASS",
        "cases": [
            {
                "index": 1,
                "cq_id": case["cq_id"],
                "content_revision": 2,
                "content_digest": case["content_digest"],
                "passed": True,
                "outcome": "pass",
                "answerability": "supported",
                "sql_readiness": "supported",
                "sql_execution": "pass",
            }
        ],
    }
    with pytest.raises(FrameworkError, match="cq_sql_execution_not_available"):
        validate_cases(report, data["questions"])


def test_new_goals_arriving_during_native_turn_stop_old_candidate_before_apply(
    task_file,
    tmp_path,
    workspace,
    saver,
):
    from test_framework_flow import Actor, Platform, tool_event
    from ontoweave_modeling.contracts import TaskBinding
    from ontoweave_modeling.custom_cq import CustomCQ
    from ontoweave_modeling.flow import WorkUnitFlow

    task = json.loads(task_file.read_text())
    task.update(project_ref="project", custom_cq=True)
    task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(task_file, tmp_path / "cq-run")

    class ProjectPlatform(Platform):
        current = snapshot()

        def call(self, action, payload=None):
            return self.current if action == "cq_snapshot" else super().call(action, payload or {})

    platform = ProjectPlatform()
    CustomCQ(binding, workspace).sync(platform)
    binding = SourceRevisions(binding, workspace).activate()

    def actor(root, purpose, prompt, inputs):
        result = Actor(binding, platform)(root, purpose, prompt, inputs)
        if purpose == "modeling":
            manifest = binding.data["source_manifest"]["cq-goals"]
            path = root / "agent/events.jsonl"
            with path.open("a") as stream:
                stream.write(
                    json.dumps(
                        tool_event(
                            "read_material",
                            {
                                "text": (binding.materials / manifest["path"]).read_text(),
                                "sha256": manifest["sha256"],
                            },
                            {"material_id": "cq-goals"},
                        )
                    )
                    + "\n"
                )
            platform.current = snapshot(ready=True)
        return result

    result = WorkUnitFlow(binding, workspace, platform, actor).advance(saver)
    assert result["status"] == "source_change_pending"
    assert not platform.effects
    assert len(workspace.list_kind("source_change")) == 2
    after = SourceRevisions(binding, workspace).activate()
    assert after.data["cycle_id"] == platform.current["snapshot_id"]
    assert (binding.materials / "custom-cq-goals.json").exists()


def test_frozen_batch_includes_all_cross_unit_goals_without_duplicating_question(
    binding, workspace, tmp_path
):
    from ontoweave_modeling.custom_cq import CustomCQ

    binding.data["work_units"] = [{"unit_id": "keys"}, {"unit_id": "calls"}]
    package = tmp_path / "cq-evaluation"
    evaluation = CustomCQ(binding, workspace).evaluation_package(snapshot(), package)
    questions = json.loads((package / "frozen-custom-questions.json").read_text())["questions"]
    assert evaluation["case_count"] == 1
    assert questions[0]["cq_id"] == "project-q1"
    assert questions[0]["criteria_ready"] is False
    assert evaluation["custom_cq"][0]["content_revision"] == 2


def test_cq_evaluate_cli_uses_readonly_context_and_reuses_its_original_freeze(
    binding,
    workspace,
    monkeypatch,
):
    from test_framework_flow import tool_event
    from ontoweave_modeling import cli

    handoff = {
        "target": {"model_revisions": {"ontology": 3}},
        "evaluation": binding.data["evaluation"],
        "source_revisions": {
            key: entry["sha256"] for key, entry in binding.data["source_manifest"].items()
        },
    }
    ref = workspace.put_reference("test-handoff", "handoff", handoff, 0)
    workspace.put_reference(
        binding.identity + ":work",
        "work_unit",
        {
            "status": "handoff_ready",
            "handoff_ref": ref,
        },
        0,
    )

    class Platform:
        current = snapshot()
        fetched = 0
        published = []

        def call(self, action, payload=None):
            if action == "cq_snapshot":
                self.fetched += 1
                return self.current
            if action == "cq_results":
                self.published.append(payload)
                return {"recorded": ["project-q1"], "skipped_stale": []}
            assert action == "snapshot"
            return handoff["target"]

    class IndependentReader:
        def __init__(self, _binding, _bridge, *, materials, **_kwargs):
            self.materials = materials

        def __call__(self, root, purpose, prompt, inputs):
            assert purpose == "acceptance" and not inputs
            parsed = json.loads(prompt)
            frozen = parsed["custom_cq_cases"]
            assert len(frozen) == 1 and not frozen[0]["criteria_ready"]
            events = []
            manifest = json.loads((self.materials / "manifest.json").read_text())
            for material_id, entry in manifest.items():
                events.append(
                    tool_event(
                        "read_material",
                        {
                            "text": (self.materials / entry["path"]).read_text(),
                            "sha256": entry["sha256"],
                        },
                        {"material_id": material_id},
                    )
                )
            events.append(
                tool_event(
                    "query_semantic_context",
                    {
                        "scope": {"ontologies": [{"ontology_id": "ontology", "model_revision": 3}]},
                    },
                )
            )
            (root / "agent").mkdir()
            (root / "agent/events.jsonl").write_text("\n".join(map(json.dumps, events)))
            question = frozen[0]
            report = {
                "verdict": "PARTIAL",
                "freeze_id": parsed["evaluation"]["freeze_id"],
                "model_revisions": {"ontology": 3},
                "cases": [
                    {
                        "index": 1,
                        "passed": False,
                        "actual_answer": "PRIVATE_ACTUAL",
                        "reason": "PRIVATE_REASON",
                        "evidence_iris": [],
                        **{
                            key: question[key]
                            for key in ("cq_id", "content_revision", "content_digest")
                        },
                        "outcome": "question-answer-review",
                        "answerability": "unverified",
                        "sql_readiness": "unverified",
                        "sql_execution": "not_run",
                    }
                ],
            }
            return {"status": "completed", "final_response": json.dumps(report)}

    platform = Platform()
    monkeypatch.setattr(cli, "HostBridge", lambda root: platform)
    monkeypatch.setattr(cli, "repository", lambda selected: (workspace, {}))
    monkeypatch.setattr(cli, "CodexInvocation", IndependentReader)
    args = cli.parser().parse_args(
        ["cq-evaluate", "--run-dir", str(binding.root), "--evaluation-id", "cq-regression"]
    )
    before = workspace.get(binding.identity + ":work")
    public = cli.dispatch(args)
    assert public["verdict"] == "PARTIAL" and public["total"] == 1
    assert public["custom_cq"][0]["sql_execution"] == "not_run"
    assert "PRIVATE" not in json.dumps(public)
    assert workspace.get(binding.identity + ":work") == before
    original = (binding.root / "cq-evaluation-inputs/cq-regression/scope.json").read_bytes()
    platform.current = snapshot(ready=True)
    assert cli.dispatch(args)["cq_snapshot_id"] == public["cq_snapshot_id"]
    assert platform.fetched == 1
    assert (binding.root / "cq-evaluation-inputs/cq-regression/scope.json").read_bytes() == original
    args.question_id = ["other-question"]
    with pytest.raises(FrameworkError, match="cq_evaluation_selection_changed"):
        cli.dispatch(args)


def test_task_subset_is_explicit_and_stopped_sync_never_reopens_work(
    task_file, tmp_path, workspace, monkeypatch
):
    from ontoweave_modeling import cli
    from ontoweave_modeling.contracts import TaskBinding

    task = json.loads(task_file.read_text())
    task["cq_question_ids"] = ["project-q1"]
    task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(task_file, tmp_path / "subset-run")
    assert binding.data["custom_cq"] is True
    assert binding.data["cq_question_ids"] == ["project-q1"]
    TaskControl(workspace).enqueue("stop-test", "stop")
    monkeypatch.setattr(cli, "repository", lambda selected: (workspace, {}))

    class NoCalls:
        def call(self, *args, **kwargs):
            pytest.fail("A stopped CQ sync must not call the platform or reopen work")

    monkeypatch.setattr(cli, "HostBridge", lambda root: NoCalls())
    args = cli.parser().parse_args(["cq-sync", "--run-dir", str(binding.root)])
    assert cli.dispatch(args) == {"status": "task_stopped", "queued": False}
    assert not workspace.list_kind("source_change")
