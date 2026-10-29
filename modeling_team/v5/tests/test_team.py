import asyncio
import json
from contextlib import contextmanager

import pytest
from test_framework_flow import Actor, Platform

from ontoweave_modeling.contracts import FrameworkError
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.execution import CodexInvocation
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.human_input import HumanInput
from ontoweave_modeling.material_tools import material_server
from ontoweave_modeling.results import ResultContractError
from ontoweave_modeling.team import TeamChannel


@pytest.fixture
def team(binding, workspace):
    binding.data["task_ref"] = workspace.task_ref
    binding.data["collaboration"] = {
        "peers": [{"agent_id": "reviewer", "objective": "Check sources."}]
    }
    control = TaskControl(workspace)
    return [
        TeamChannel(binding.data, workspace, control, actor, binding.root / "materials")
        for actor in ["modeling", "reviewer"]
    ]


def test_busy_queue_material_ranges_and_delegated_request(team):
    a, b = team
    a.control.begin_activity(b.unit("reviewer"), "busy")
    ref = a.publish("source-copy", source_material_id="source")
    with pytest.raises(FrameworkError, match="handoff_material_forbidden"):
        b.read(ref)
    message = a.send(
        "reviewer",
        "Read only the needed section.",
        "review-1",
        [ref],
        {"summary": "check source", "blocking": True},
    )
    assert message["status"] == "queued"
    assert (
        a.send(
            "reviewer",
            message["body"],
            "review-1",
            [ref],
            {"summary": "check source", "blocking": True},
        )
        == message
    )
    assert a.control.begin_activity(b.unit("reviewer"), "other")["admitted"] is False
    a.control.finish_turn(b.unit("reviewer"), "busy")
    admitted = a.control.begin_activity(
        b.unit("reviewer"),
        "next",
        deliver_inputs=True,
        input_phase="model",
        input_run_id=a.task["run_id"],
    )
    assert [m["id"] for m in admitted["inputs"]] == [message["id"]]
    chunk = b.read(ref, 3, 8)
    assert len(chunk["text"]) == 8 and chunk["next_offset"] == 11
    assert "text" not in admitted["inputs"][0]["metadata"]["material_refs"][0]
    assert a.board()["agents"][0]["requests"][0]["delivery_status"] == "delivered"
    assert all(m["metadata"]["source"] == "agent" for m in admitted["inputs"])


def test_cards_history_authorship_and_reply_do_not_resolve(team):
    a, b = team
    a.update_card({"current_work": "first"})
    a.update_card({"current_work": "second"}, 1)
    assert a.board("modeling", 1)["agents"][0]["card"]["content"]["current_work"] == "first"
    assert a.update_card({"current_work": "stale"}, 0)["code"] == "version_conflict"
    with pytest.raises(FrameworkError, match="invalid_work_card"):
        a.update_card({"author": "reviewer"})
    message = a.send("reviewer", "check", "request", work_request={"summary": "check"})
    b.send("modeling", "done", "reply", reply_to=message["id"])
    assert a.board("modeling")["agents"][0]["requests"][0]["resolution"] is None
    with pytest.raises(FrameworkError, match="work_request_resolution_forbidden"):
        b.resolve_request(message["id"], "satisfied")
    a.resolve_request(message["id"], "satisfied")
    assert a.board("reviewer")["agents"][0]["requests"][0]["resolution"]["status"] == "satisfied"


def test_material_old_version_kept_and_cross_run_denied(team):
    a, b = team
    first = a.publish("note", text="old text")
    a.send("reviewer", "read", "one", [first])
    second = a.publish("note", text="new text", expected_revision=1)
    assert b.read(first)["text"] == "old text"
    assert b.read({"object_id": first["object_id"], "revision": 1})["text"] == "old text"
    with pytest.raises(FrameworkError, match="handoff_material_changed_or_missing"):
        b.read({**first, "digest": "wrong"})
    with pytest.raises(FrameworkError, match="handoff_material_forbidden"):
        b.read(second)
    other = TeamChannel({**a.task, "run_id": "other-run"}, a.repository, a.control, "reviewer")
    with pytest.raises(FrameworkError, match="handoff_material_changed_or_missing"):
        other.read(first)
    with pytest.raises(FrameworkError, match="team_recipient_not_found"):
        a.send("acceptance", "hidden", "forbidden")
    with pytest.raises(FrameworkError, match="team_message_identity_conflict"):
        a.send("reviewer", "changed", "one")


def test_opaque_ids_are_not_file_paths_and_own_author_is_redundant(team):
    a, b = team
    ref = a.publish("source:revision/opaque", text="approved interpretation")
    msg = a.send("reviewer", "check", "run:opaque:message/1", [ref])
    assert b.read(ref)["text"] == "approved interpretation"
    reply = b.send("modeling", "done", "run:opaque:message/2", reply_to=msg["id"])
    assert reply["metadata"]["author"] == "reviewer"
    result = b.update_card({"author": "reviewer", "current_work": "done"})
    assert result["object"]["content"]["author"] == "reviewer"
    assert b.update_card({"current_work": "next", "expected_revision": 1})["status"] == "recorded"


def test_team_tools_loaded_through_real_mcp(team, binding, workspace, tmp_path):
    a, _ = team
    config = tmp_path / "team.json"
    config.write_text(
        json.dumps(
            {
                "task": a.task,
                "connection": workspace.connection,
                "schema": workspace.schema,
                "actor": "modeling",
            }
        )
    )
    server = material_server(binding.root / "materials", team_config=config)
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {
        "send_team_message",
        "publish_handoff_material",
        "read_handoff_material",
        "update_work_card",
        "get_work_board",
        "resolve_work_request",
    } <= names
    asyncio.run(server.call_tool("update_work_card", {"card": {"current_work": "MCP"}}))
    assert a.board("modeling")["agents"][0]["card"]["content"]["current_work"] == "MCP"


def test_two_members_exchange_and_rebuild_does_not_replay_application(
    team, binding, workspace, saver
):
    a, b = team
    platform = Platform()
    fallback = Actor(binding, platform)
    calls = []

    def invoke(root, purpose, prompt, inputs):
        calls.append(purpose)
        if purpose.startswith("peer:"):
            assert len(inputs) == 1
            assert b.read(inputs[0]["metadata"]["material_refs"][0], 0, 8)["text"]
            b.send(
                "modeling", "Use only the supplied meaning.", "response", reply_to=inputs[0]["id"]
            )
            folder = root / "agent"
            folder.mkdir()
            (folder / "events.jsonl").write_text("")
            return {
                "status": "completed",
                "thread_id": "peer-thread",
                "turn_id": root.name,
                "final_response": json.dumps(
                    {"status": "ready", "issues": [], "consumed_ids": [m["id"] for m in inputs]}
                ),
            }
        value = fallback(root, purpose, prompt, inputs)
        response = json.loads(value["final_response"])
        if purpose == "modeling" and not inputs:
            ref = a.publish("source", source_material_id="source")
            a.send("reviewer", "Check needed source.", "question", [ref])
            response.update(
                status="waiting_peer", candidate=None, changes=None, issues=["Await peer"]
            )
        response["consumed_ids"] = [m["id"] for m in inputs]
        value["final_response"] = json.dumps(response)
        return value

    flow = WorkUnitFlow(binding, workspace, platform, invoke)
    state = flow.advance(saver)
    assert state["status"] == "handoff_ready"
    assert calls == ["modeling", "peer:reviewer", "modeling", "self_check"]
    assert len(platform.effects) == 1
    assert all(m["status"] == "consumed" for m in a.messages())
    assert WorkUnitFlow(binding, workspace, platform, invoke).advance(saver) == state
    assert len(calls) == 4 and len(platform.effects) == 1


def test_waiting_peer_without_message_does_not_poll(team, binding, workspace, saver):
    platform = Platform()
    actor = Actor(binding, platform)

    def invoke(root, purpose, prompt, inputs):
        value = actor(root, purpose, prompt, inputs)
        response = json.loads(value["final_response"])
        response.update(status="waiting_peer", changes=None, issues=["Waiting for peer"])
        value["final_response"] = json.dumps(response)
        return value

    state = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert state["status"] == "waiting_peer"
    WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert actor.calls == ["modeling"] and not platform.effects


def test_targeted_technical_repair_wakes_peer_without_publishing_host_note_on_board(team):
    a, b = team
    a.control.enqueue(
        "repair",
        "input",
        "Technical repair only",
        b.unit("reviewer"),
        metadata={"source": "host", "run_id": a.task["run_id"], "phase": "model"},
    )
    assert [m["id"] for m in b.pending("reviewer")] == ["repair"]
    assert not b.messages()


def test_team_request_cannot_be_reported_as_resolved_human_question(team, binding, workspace):
    a, _ = team
    msg = a.send("reviewer", "check", "request", work_request={"summary": "check"})
    ref = workspace.put_reference("peer-execution", "execution", {"inputs": [msg]}, 0)
    human = HumanInput(binding, workspace, a.control)
    with pytest.raises(FrameworkError, match="human_resolution_unconfirmed") as error:
        human.validate_resolutions(ref, [msg["id"]], [msg["id"]])
    assert error.value.detail["allowed_human_request_ids"] == []


def test_peer_dispatch_keeps_simultaneous_human_question(team, binding, workspace, saver):
    a, b = team
    platform = Platform()
    fallback = Actor(binding, platform)

    def invoke(root, purpose, prompt, inputs):
        value = fallback(root, purpose, prompt, inputs)
        response = json.loads(value["final_response"])
        response["consumed_ids"] = [m["id"] for m in inputs]
        if purpose == "modeling":
            context = json.loads(prompt)["human_context"]
            if not context["requests"]:
                a.send("reviewer", "do independent source check", "check")
            response.update(
                status="waiting_input",
                changes=None,
                issues=["Need human meaning"],
                human_requests=[]
                if context["requests"]
                else [
                    {
                        "question": "Which meaning?",
                        "reason": "Unknown source fact",
                        "impact": "Current concept",
                    }
                ],
            )
        else:
            b.send(
                "modeling",
                "Source check only; human fact still unknown",
                "reply",
                reply_to=inputs[0]["id"],
            )
        value["final_response"] = json.dumps(response)
        return value

    state = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    questions = HumanInput(binding, workspace, a.control).requests()
    assert state["status"] == "waiting_input" and not platform.effects
    assert len(questions) == 1 and questions[0]["status"] == "awaiting_answer"
    assert fallback.calls == ["modeling", "peer:reviewer", "modeling"]


def test_reparse_original_peer_receipt_after_format_fix_does_not_rerun_actor(
    team, binding, workspace, saver, monkeypatch
):
    import ontoweave_modeling.flow as module

    a, b = team
    platform = Platform()
    fallback = Actor(binding, platform)
    a.send("reviewer", "Please check source", "initial")

    def invoke(root, purpose, prompt, inputs):
        value = fallback(root, purpose, prompt, inputs)
        response = json.loads(value["final_response"])
        response["consumed_ids"] = [m["id"] for m in inputs]
        if purpose.startswith("peer:"):
            b.send("modeling", "Checked", "reply", reply_to=inputs[0]["id"])
            value["final_response"] = "Completed peer review.\n" + json.dumps(response)
        else:
            value["final_response"] = json.dumps(response)
        return value

    real_decode = module.decode_json_result

    def old_decode(message, schema):
        if message.startswith("Completed peer review."):
            raise ResultContractError("result_json_missing_or_ambiguous")
        return real_decode(message, schema)

    with monkeypatch.context() as patch:
        patch.setattr(module, "decode_json_result", old_decode)
        state = WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)
    assert state["status"] == "recoverable_issue" and fallback.calls == ["peer:reviewer"]
    assert (
        WorkUnitFlow(binding, workspace, platform, invoke).advance(saver)["status"]
        == "handoff_ready"
    )
    assert (
        fallback.calls == ["peer:reviewer", "modeling", "self_check"] and len(platform.effects) == 1
    )


def test_actual_invocation_team_mcp_resolves_host_outside_namespace(
    team, binding, workspace, tmp_path, monkeypatch
):
    from openai_codex.generated.v2_all import McpServerToolCallResponse

    from ontoweave_modeling.codex_agent import CodexAgent

    (binding.root / "private-runtime.json").write_text(
        json.dumps({"connection": workspace.connection, "workspace_schema": workspace.schema})
    )
    config = tmp_path / "platform.json"
    config.write_text("{}")

    class Bridge:
        def call(self, operation, payload):
            return {"config_ref": str(config)}

        @contextmanager
        def provider(self, *args):
            yield "http://127.0.0.1:9"

    class Probe(CodexAgent):
        def run_turn(self, prompt):
            result = self.client.request(
                "mcpServer/tool/call",
                {
                    "threadId": self.thread_id,
                    "server": "workspace",
                    "tool": "update_work_card",
                    "arguments": {"card": {"current_work": "real isolated MCP"}},
                },
                response_model=McpServerToolCallResponse,
            )
            assert not result.is_error, result.content
            published = self.client.request(
                "mcpServer/tool/call",
                {
                    "threadId": self.thread_id,
                    "server": "workspace",
                    "tool": "publish_handoff_material",
                    "arguments": {"material_id": "probe", "source_material_id": "source"},
                },
                response_model=McpServerToolCallResponse,
            )
            assert not published.is_error, published.content
            ref = json.loads(published.content[0]["text"])
            read = self.client.request(
                "mcpServer/tool/call",
                {
                    "threadId": self.thread_id,
                    "server": "workspace",
                    "tool": "read_handoff_material",
                    "arguments": {
                        "reference": {"object_id": ref["object_id"], "revision": ref["revision"]},
                        "limit": 8,
                    },
                },
                response_model=McpServerToolCallResponse,
            )
            assert not read.is_error, read.content
            assert len(json.loads(read.content[0]["text"])["text"]) == 8
            return {"status": "completed"}

    monkeypatch.setattr("ontoweave_modeling.codex_agent.CodexAgent", Probe)
    root = tmp_path / "execution"
    root.mkdir()
    CodexInvocation(binding, Bridge())(root, "modeling", "No inference", [])
    a, _ = team
    assert (
        a.board("modeling")["agents"][0]["card"]["content"]["current_work"] == "real isolated MCP"
    )
