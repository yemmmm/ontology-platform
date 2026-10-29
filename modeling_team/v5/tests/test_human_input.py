"""Real PostgreSQL/LangGraph wait and replay; deterministic actors are not semantic proof."""

import json

import pytest
from test_framework_flow import Actor, Platform

from ontoweave_modeling.contracts import FrameworkError, TaskBinding
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.human_input import HumanInput
from ontoweave_modeling.workspace import WorkspaceRepository


class AskingActor(Actor):
    phase = "modeling"

    def __call__(self, root, purpose, prompt, inputs):
        value = super().__call__(root, purpose, prompt, inputs)
        if purpose != self.phase:
            return value
        response = json.loads(value["final_response"])
        replies = [m for m in inputs if m.get("metadata", {}).get("request_id")]
        response["consumed_ids"] = [m["id"] for m in inputs]
        if not replies or replies[-1]["metadata"]["partial"]:
            response.update(status="waiting_input", issues=["The required meaning is incomplete"])
            if purpose == "modeling":
                response.update(candidate=None, changes=None)
            response["human_requests"] = (
                []
                if replies
                else [
                    {
                        "question": "Which business meaning should be used?",
                        "reason": "The source leaves this fact open.",
                        "impact": "The current work unit depends on this answer.",
                    }
                ]
            )
        else:
            response["resolved_request_ids"] = [replies[-1]["metadata"]["request_id"]]
        value["final_response"] = json.dumps(response)
        return value


def test_question_reply_rebuild_resumes_original_work_once(binding, workspace, saver):
    platform = Platform()
    actor = AskingActor(binding, platform)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    waiting = flow.advance(saver)
    assert waiting["status"] == "waiting_input" and not platform.effects
    checkpoint = flow.compile(saver).get_state({"configurable": {"thread_id": "framework-run"}})
    assert any(task.interrupts for task in checkpoint.tasks)
    human = HumanInput(binding, workspace, TaskControl(workspace))
    question = human.requests()[0]
    assert question["basis_ref"] and question["source_revisions"]
    assert WorkUnitFlow(binding, workspace, platform, actor).advance(saver) == waiting
    assert len(actor.calls) == 1
    first = human.submit("Confirmed meaning", "answer-1", request_id=question["request_id"])
    assert human.submit("Confirmed meaning", "answer-1", request_id=question["request_id"]) == first
    rebuilt = WorkUnitFlow(binding, workspace, platform, actor)
    assert rebuilt.advance(saver)["status"] == "handoff_ready"
    assert human.requests()[0]["status"] == "resolved"
    assert len(platform.effects) == 1
    assert len(TaskControl(workspace).view()["messages"]) == 1
    rebuilt.advance(saver)
    assert actor.calls == ["modeling", "modeling", "self_check"]


def test_partial_answer_remains_open_until_matching_full_answer(binding, workspace, saver):
    platform = Platform()
    actor = AskingActor(binding, platform)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    flow.advance(saver)
    human = flow.human
    question = human.requests()[0]["request_id"]
    human.submit("Only part of the meaning", "partial", request_id=question, partial=True)
    assert flow.advance(saver)["status"] == "waiting_input"
    assert human.requests()[0]["status"] == "answer_consumed"
    assert len(human.requests()) == 1 and not platform.effects
    human.submit("Complete confirmed meaning", "full", request_id=question)
    assert (
        WorkUnitFlow(binding, workspace, platform, actor).advance(saver)["status"]
        == "handoff_ready"
    )
    assert len(platform.effects) == 1 and human.requests()[0]["status"] == "resolved"


def test_request_saved_before_wait_checkpoint_does_not_repeat_agent(
    binding, workspace, saver, monkeypatch
):
    platform = Platform()
    actor = AskingActor(binding, platform)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    original = flow._save

    def crash(state):
        if state["activity"] == "wait_input":
            raise RuntimeError("after question commit, before wait checkpoint")
        return original(state)

    monkeypatch.setattr(flow, "_save", crash)
    with pytest.raises(RuntimeError, match="before wait checkpoint"):
        flow.advance(saver)
    rebuilt = WorkUnitFlow(binding, workspace, platform, actor)
    assert rebuilt.advance(saver)["status"] == "waiting_input"
    assert len(actor.calls) == 1 and len(rebuilt.human.requests()) == 1


def test_answer_saved_before_queue_is_recoverable_and_identity_bound(
    binding, workspace, monkeypatch
):
    control = TaskControl(workspace)
    human = HumanInput(binding, workspace, control)
    real_enqueue = control.enqueue
    monkeypatch.setattr(
        control, "enqueue", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("lost"))
    )
    with pytest.raises(RuntimeError):
        human.submit("User input", "message")
    monkeypatch.setattr(control, "enqueue", real_enqueue)
    human.submit("User input", "message")
    human.submit("User input", "message")
    assert len(control.view()["messages"]) == 1
    with pytest.raises(FrameworkError, match="identity_conflict"):
        human.submit("Changed input", "message")


def test_wait_after_application_resumes_self_check_without_reapplying(binding, workspace, saver):
    platform = Platform()
    actor = AskingActor(binding, platform)
    actor.phase = "self_check"
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    assert flow.advance(saver)["status"] == "waiting_input"
    assert len(platform.effects) == 1
    question = flow.human.requests()[0]
    assert question["phase"] == "self_check"
    flow.human.submit("Confirmed", "answer", request_id=question["request_id"])
    assert (
        WorkUnitFlow(binding, workspace, platform, actor).advance(saver)["status"]
        == "handoff_ready"
    )
    assert len(platform.effects) == 1 and actor.calls.count("modeling") == 1


def test_busy_unsolicited_input_waits_for_next_agent_boundary(binding, workspace, saver):
    platform = Platform()
    control = TaskControl(workspace)
    human = HumanInput(binding, workspace, control)
    actor = Actor(binding, platform)

    def invoke(root, purpose, prompt, inputs):
        value = actor(root, purpose, prompt, inputs)
        if purpose == "modeling":
            assert control.view()["active"] and not inputs
            human.submit("A proactive user clarification", "proactive")
            assert control.view()["messages"][0]["status"] == "queued"
        else:
            assert [m["id"] for m in inputs] == ["proactive"]
            result = json.loads(value["final_response"])
            result["consumed_ids"] = ["proactive"]
            value["final_response"] = json.dumps(result)
        return value

    assert (
        WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)["status"]
        == "handoff_ready"
    )
    assert control.view()["messages"][0]["status"] == "consumed"


def test_other_task_cannot_reply_to_question_and_stale_revision_is_explicit(binding, workspace):
    human = HumanInput(binding, workspace, TaskControl(workspace))
    identity = human.ask(
        "model", [{"question": "Open?", "reason": "Missing", "impact": "This unit"}], None, {}
    )[0]
    other = WorkspaceRepository(workspace.connection, workspace.schema, "other-task")
    with pytest.raises(FrameworkError, match="not_found"):
        HumanInput(binding, other, TaskControl(other)).submit("Answer", "a", request_id=identity)
    with pytest.raises(FrameworkError, match="version_changed"):
        human.submit("Answer", "b", request_id=identity, request_revision=2)


def test_resolved_request_ack_is_idempotent_but_unanswered_or_partial_cannot_resolve(
    binding, workspace, saver
):
    platform = Platform()
    actor = AskingActor(binding, platform)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    flow.advance(saver)
    question = flow.human.requests()[0]["request_id"]
    empty_execution = workspace.put_reference("empty-execution", "execution", {"inputs": []}, 0)
    with pytest.raises(FrameworkError, match="human_resolution_unconfirmed"):
        flow.human.validate_resolutions(empty_execution, [], [question])
    partial_execution = workspace.put_reference(
        "partial-execution",
        "execution",
        {"inputs": [{"id": "partial", "metadata": {"request_id": question, "partial": True}}]},
        0,
    )
    with pytest.raises(FrameworkError, match="human_resolution_unconfirmed"):
        flow.human.validate_resolutions(partial_execution, ["partial"], [question])
    flow.human.submit("Confirmed", "full", request_id=question)
    assert flow.advance(saver)["status"] == "handoff_ready"
    flow.human.validate_resolutions(empty_execution, [], [question])


def test_reply_resume_refreshes_baseline_and_keeps_original_question_version(
    binding, workspace, saver, monkeypatch
):
    platform = Platform()
    actor = AskingActor(binding, platform)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    flow.advance(saver)
    original = flow.human.requests()[0]
    call = platform.call
    observed = []

    def changed(action, payload):
        result = call(action, payload)
        if action == "snapshot":
            result["external_baseline_revision"] = "new-version"
        return result

    def invoke(root, purpose, prompt, inputs):
        if purpose == "modeling":
            observed.append(json.loads(prompt)["actual_baseline"])
        return actor(root, purpose, prompt, inputs)

    monkeypatch.setattr(platform, "call", changed)
    flow.human.submit("Confirmed", "answer", request_id=original["request_id"])
    assert (
        WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)["status"]
        == "handoff_ready"
    )
    assert observed[0]["external_baseline_revision"] == "new-version"
    assert flow.human.requests()[0]["request_ref"] == original["request_ref"]


def test_other_run_input_is_not_delivered_or_silently_reused(binding, workspace):
    control = TaskControl(workspace)
    human = HumanInput(binding, workspace, control)
    human.submit("For the original run", "original-message")
    other = TaskBinding(binding.root, {**binding.data, "run_id": "other-run"})
    other_human = HumanInput(other, workspace, control)
    assert not other_human.pending("model") and not other_human.context()["answers"]
    with pytest.raises(FrameworkError, match="identity_conflict"):
        other_human.submit("For the original run", "original-message")
    turn = control.begin_activity(
        "bounded-unit",
        "other-exec",
        deliver_inputs=True,
        input_phase="model",
        input_run_id="other-run",
    )
    assert not turn["inputs"]


def test_cli_questions_reply_text_file_and_unsolicited_input_use_no_agent(
    binding, workspace, tmp_path, monkeypatch, capsys
):
    from ontoweave_modeling import cli

    monkeypatch.setattr(cli, "repository", lambda _: (workspace, {}))
    monkeypatch.setattr(
        cli.HostBridge, "call", lambda *a, **kw: pytest.fail("No Agent/platform call")
    )
    human = HumanInput(binding, workspace, TaskControl(workspace))
    question = human.ask(
        "model", [{"question": "Which name?", "reason": "Missing", "impact": "Unit"}], None, {}
    )[0]
    args = ["--run-dir", str(binding.root)]
    assert cli.main(["questions", *args]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["questions"][0]["request_id"] == question
    text = tmp_path / "answer.txt"
    text.write_text("A multiline\nuser answer\n")
    reply = [
        "reply",
        *args,
        "--request-id",
        question,
        "--request-revision",
        "1",
        "--message-id",
        "cli-answer",
        "--text-file",
        str(text),
    ]
    assert cli.main(reply) == 0
    assert json.loads(capsys.readouterr().out)["result"]["message"]["body"] == text.read_text()
    assert cli.main(reply) == 0
    capsys.readouterr()
    assert cli.main(["input", *args, "--message-id", "proactive", "--text", "Extra fact"]) == 0
    capsys.readouterr()
    assert cli.main(["questions", *args]) == 0
    question_view = json.loads(capsys.readouterr().out)["result"]["questions"][0]
    assert question_view["replies"][0]["body"] == text.read_text()
    assert len(TaskControl(workspace).view()["messages"]) == 2
    control = TaskControl(workspace)
    control.enqueue(
        "host-note",
        "input",
        "Operational context",
        binding.data["work_unit_id"],
        metadata={"source": "host"},
    )
    assert len(human.context()["answers"]) == 2
    control.enqueue("stop", "stop")
    control.synchronize()
    assert cli.main(["input", *args, "--message-id", "after-stop", "--text", "New fact"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "human_input_task_closed"


def test_wait_pause_and_resume_without_reply_does_not_invoke_agent(binding, workspace, saver):
    platform = Platform()
    actor = AskingActor(binding, platform)
    flow = WorkUnitFlow(binding, workspace, platform, actor)
    flow.advance(saver)
    flow.control.enqueue("pause", "pause")
    flow.control.synchronize()
    flow.control.enqueue("resume", "resume")
    flow.control.synchronize()
    assert flow.advance(saver)["status"] == "waiting_input"
    assert actor.calls == ["modeling"]
