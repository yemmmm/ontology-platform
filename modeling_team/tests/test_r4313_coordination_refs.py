from __future__ import annotations

import hashlib
import json
import threading
from types import SimpleNamespace

import pytest

from modeling_team.acceptance import CoordinatorPhaseController
from modeling_team.handoff_materials import HandoffMaterials
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker, mcp_response


@pytest.mark.parametrize("mode", ["body-only", "body-explained", "aux-only", "inline"])
def test_coordination_mcp_broker_runner_runtime_and_evidence(tmp_path, mode):
    store = HandoffMaterials(tmp_path / "handoff-materials", "coordination-run")
    store.register_actor("modeling", {}, {"coordinator", "runner"})
    store.register_actor("coordinator", {}, {"modeling", "runner"})
    original = "中文正文" * 10000
    output = store.write_output("modeling", "formal.txt", original)
    publication = store.publish("modeling", "coordinator", output["source_path"])
    ref = {"material_id": publication["material_id"]}
    evidence, received, phase_inputs = [], [], []
    runner = object.__new__(TeamRunner)
    runner.run = SimpleNamespace(handoff_materials=store)
    runner._coordination_runtime_queue = []
    runner._coordination_runtime_lock = threading.Lock()
    runner._formal_coordination_role_ids = lambda: {
        role: role for role in ("coordinator", "modeling", "protocol", "acceptance")
    }
    runner._append_evidence = lambda kind, event: evidence.append((kind, event))
    runner.adapter = SimpleNamespace(
        send_message=lambda actor, delivery: received.append((actor, delivery))
    )
    runner.coordinator_phase = CoordinatorPhaseController()
    runner.coordinator_phase.start()
    runner.coordinator_phase.assign_slice(sender_id="coordinator", objective="bounded slice")
    generation = runner.coordinator_phase.generation

    def phase_callback(*args):
        phase_inputs.append(args)
        return runner._coordination_phase_callback(*args)

    broker = TeamTransportBroker(
        tmp_path / "broker", {("modeling", "coordinator")}, materials=store,
        coordination_phase_callback=phase_callback,
        coordination_event_observer=runner._coordination_transport_event_observer,
    )
    arguments = {
        "recipient_id": "coordinator", "message_kind": "ready_for_acceptance",
        "generation": generation,
    }
    if mode.startswith("body"):
        arguments["body_ref"] = ref
        if mode == "body-explained":
            arguments["text"] = "请读阶段正文"
        formal_text = original
    else:
        arguments["text"] = "阶段辅助材料" if mode == "aux-only" else "普通阶段说明"
        if mode == "aux-only":
            arguments["material_refs"] = [ref]
        formal_text = arguments["text"]

    def call(name, args, actor="modeling"):
        response = mcp_response(
            {"method": "tools/call", "params": {"name": name, "arguments": args}},
            broker=broker, agent_id=actor,
        )
        return json.loads(response["content"][0]["text"])

    response = call("send_coordination", arguments)
    if mode.startswith("body"):
        assert original not in json.dumps(response, ensure_ascii=False)
        assert response["phase_event"]["generation"] == generation
    message = broker.drain_coordination()[0]
    assert message.text == formal_text
    assert phase_inputs[0] == (
        "modeling", "coordinator", "ready_for_acceptance", formal_text, generation,
    )
    assert message.phase_event["text"] == formal_text
    assert message.phase_event["generation"] == generation
    assert not message.terminal and not message.settles and not broker.results
    with pytest.raises(RoutingError, match="coordination phase rejected"):
        call("send_coordination", {**arguments, "generation": generation + 1})
    assert len(evidence) == 1
    runner._drain_coordination_runtime_deliveries()
    assert len(received) == 1
    actor, delivery = received[0]
    assert actor == delivery.recipient_id == "coordinator"
    assert delivery.delivery_id == message.message_id == response["message_id"]
    assert delivery.kind == "coordination-phase"
    formal_payload = json.loads(delivery.text)
    assert formal_payload["text"] == formal_text
    assert formal_payload["generation"] == generation
    assert formal_payload["coordination_message_id"] == message.message_id
    rendered = CodexRuntimeAdapter._delivery_input(delivery)[0]["text"]
    rendered_payload = json.loads(rendered)
    display_payload = json.loads(rendered_payload["text"])
    assert display_payload["coordination_message_id"] == message.message_id
    assert display_payload["generation"] == generation
    assert evidence[0][0] == "coordination"
    event = evidence[0][1]
    assert event["message_id"] == message.message_id
    assert event["text_sha256"] == hashlib.sha256(formal_text.encode()).hexdigest()
    assert "text" not in event["phase_event"]
    assert event["phase_event"]["generation"] == generation
    if mode == "inline":
        assert response["phase_event"] == message.phase_event
        assert delivery.display_text is None and delivery.body_ref is None
        assert delivery.material_refs == ()
        assert "body_ref" not in event and "material_refs" not in event
        assert display_payload == formal_payload
    else:
        assert original not in rendered and len(rendered.encode()) < 2000
        if mode.startswith("body"):
            assert delivery.body_ref == rendered_payload["body_ref"] == event["body_ref"] == ref
            assert display_payload["text"] == (
                arguments.get("text") or "Read the referenced material through read_handoff_material."
            )
        else:
            assert delivery.material_refs == (ref,)
            assert rendered_payload["material_refs"] == event["material_refs"] == [ref]
        listing = call("list_handoff_material", ref, "coordinator")
        assert listing["list_complete"]
        content, offset = [], 0
        while True:
            page = call("read_handoff_material", {**ref, "offset": offset}, "coordinator")
            content.append(page["content"])
            offset = page["next_offset"]
            if page["read_complete"]:
                break
        assert "".join(content) == original
    runner._drain_coordination_runtime_deliveries()
    assert len(received) == 1
