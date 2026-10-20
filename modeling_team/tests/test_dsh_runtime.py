"""Real pinned DSH/bwrap loading and process control, with no external model calls."""

import hashlib
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.contracts import load_multi_slice_team_configuration
from modeling_team.deepseek_provider_proxy import preflight_deepseek_credential
from modeling_team.model_routing import load_team_model_profile
from modeling_team.runtimes.dsh import DshRuntimeAdapter
from modeling_team.transport_mcp import TeamTransportBroker
from modeling_team.capability_mcp import (
    RunnerCapabilityEndpoint,
    DIRECT_MODELING_OPERATIONS,
    CQ_OPERATION,
)
from modeling_team.modeling_readonly import ModelingReadProxy

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def local_roster(tmp_path):
    config = load_multi_slice_team_configuration(
        ROOT / "modeling_team/profiles/r4-3-026-minimal-installation-chain-dsh.yaml",
        ROOT / "modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml",
        root=ROOT,
    )
    key = tmp_path / "fake.key"
    key.write_text("DEEPSEEK_API_KEY=test-only-not-a-real-provider-key\n")
    key.chmod(0o600)
    root = tmp_path / "run"
    for agent in config.profile.agents:
        folder = root / "sources" / agent.package.role
        folder.mkdir(parents=True)
        for source in config.task.role_sources:
            if agent.package.role in source.roles:
                dest = folder / source.relative_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source.path, dest)
    broker = TeamTransportBroker(root / "transport/broker", set(config.profile.communication))
    broker.start([agent.agent_id for agent in config.profile.agents])
    sockets = tempfile.TemporaryDirectory(prefix="r4331-sockets-")
    endpoints = {}
    capability_calls = []

    def dispatch(role, operation, args):
        value = {"role": role, "operation": operation, "arguments": dict(args)}
        capability_calls.append(value)
        return value

    for role, operations in [
        ("modeling", DIRECT_MODELING_OPERATIONS),
        ("competency-question", (CQ_OPERATION,)),
    ]:
        token = Path(sockets.name) / f"{role}.token"
        token.write_text("test-only-" + role)
        endpoint = RunnerCapabilityEndpoint(
            role=role,
            socket_path=Path(sockets.name) / f"{role}.sock",
            token=token.read_text(),
            operations=operations,
            dispatch=dispatch,
        )
        endpoint.start()
        endpoints[role] = endpoint
    carrier = SimpleNamespace(
        capability_descriptors={role: endpoint.descriptor for role, endpoint in endpoints.items()},
        capability_token_path=lambda role: Path(sockets.name) / f"{role}.token",
        capability_socket_path=lambda role: endpoints[role].socket_path,
    )
    read_proxy = ModelingReadProxy(
        socket_path=Path(sockets.name) / "read.sock",
        token="read-test-token",
        read_key="test-only-not-platform-key",
        project_id="test-project",
        ontology_id="test-ontology",
        forward=lambda tool, args, key: {"ok": True, "data": {}},
    )
    read_proxy.start()
    run = SimpleNamespace(
        root=root,
        run_id="engineering-only",
        formal_contract=None,
        configuration=config,
        acceptance=carrier,
        capability_calls=capability_calls,
        modeling_read_proxy=read_proxy,
        transport_root=broker.root,
        team_model_profile=load_team_model_profile(ROOT, "dsh-deepseek-flash-low"),
        provider_credential_bindings={"deepseek-official": preflight_deepseek_credential(key)},
    )
    adapter = DshRuntimeAdapter(repository_root=ROOT)
    try:
        yield adapter, run, broker
    finally:
        adapter.stop()
        broker.stop()
        for endpoint in endpoints.values():
            endpoint.stop()
        read_proxy.destroy()
        sockets.cleanup()


def test_real_isolated_roster_loads_exact_tools_and_freezes_all_processes(local_roster):
    adapter, run, broker = local_roster
    identities = adapter.start_roster(run, run.configuration.profile.agents)
    assert len(identities) == 3
    assert all(identity.runtime == "dsh" for identity in identities)
    visibility = adapter.probe_role_visibility(run)
    assert set(visibility) == {"coordinator", "modeling", "competency-question"}
    for configured in run.configuration.profile.agents:
        actor = adapter.agents[configured.agent_id]
        package = configured.package
        assert package.package_id == package.role
        manifest = actor.material_manifest
        loaded = {entry["source"]: entry["sha256"] for entry in manifest.values()}
        instruction = package.instructions_path.relative_to(ROOT).as_posix()
        assert loaded[instruction] == hashlib.sha256(package.instructions_path.read_bytes()).hexdigest()
        for skill in package.required_skills:
            assert loaded[f"/skills/{skill.parent.name}/SKILL.md"] == hashlib.sha256(
                skill.read_bytes()
            ).hexdigest()
        assert not any("minimal-chain-modeling" in name for name in loaded)
        if configured.agent_id != "competency-question":
            assert not any("cq-private" in name for name in loaded)
    for actor in ("coordinator", "modeling"):
        tools = {tool["name"] for server, tool in adapter.agents[actor].expected_tools if server == "team_transport"}
        assert {"update_work_card", "get_work_board", "resolve_work_request"} <= tools
        assert (adapter.agents[actor].base / "home/work_board.py").read_bytes() == (ROOT / "modeling_team/work_board.py").read_bytes()
    cq_tools = {tool["name"] for server, tool in adapter.agents["competency-question"].expected_tools if server == "team_transport"}
    assert not {"update_work_card", "get_work_board", "resolve_work_request"} & cq_tools
    before = [adapter.runtime_identity(key) for key in adapter.agents]
    groups = adapter.pause()
    assert all(len(group) >= 3 for group in groups.values())
    assert all(item["state"] in {"T", "t"} for group in groups.values() for item in group)
    adapter.resume()
    assert before == [adapter.runtime_identity(key) for key in adapter.agents]
    adapter.pause()
    adapter.stop()
    assert adapter.cleanup_identifiers()["complete"]
    assert all(agent.process.poll() is not None for agent in adapter.agents.values())
    baseline = (run.root / "evidence/dsh-baseline.jsonl").read_text()
    assert "test-only-not-a-real-provider-key" not in baseline


def test_nonformal_roster_ignores_inactive_coordinator_capability(local_roster):
    from modeling_team.capability_mcp import COORDINATOR_OPERATIONS

    adapter, run, broker = local_roster
    # The real carrier retains this formal-only descriptor, while the minimal
    # chain Runner starts only the Modeling and CQ endpoints.
    run.acceptance.capability_descriptors["coordinator"] = {
        "operations": list(COORDINATOR_OPERATIONS),
    }
    socket_root = run.acceptance.capability_token_path("modeling").parent
    (socket_root / "coordinator.token").write_text("test-only-coordinator")
    run.acceptance.capability_socket_path = lambda role: socket_root / f"{role}.sock"
    identities = adapter.start_roster(run, run.configuration.profile.agents)
    assert len(identities) == 3
    assert all(
        server != "runner_capability"
        for server, tool in adapter.agents["coordinator"].expected_tools
    )
    assert adapter.probe_role_visibility(run)["modeling"]


class LocalMessagesProvider:
    """Real HTTP/SSE to the pinned Harness, wholly deterministic and offline."""

    def __init__(self, credential, **kwargs):
        self.proxy_token = "engineering-only-proxy-token"
        self.requests = []
        self.input_tokens = 1
        self.usage_bindings = {}
        self.tool_calls = True
        self.tool_name = "mcp__role_materials__read_role_material"
        self.tool_arguments = {"material_id": "material-1", "limit": 30}
        self.fail = False
        self.failure_status = 402
        self.failure_body = {'type': 'error', 'error': {'type': 'billing_error', 'message': 'HTTP 402'}}
        self.invalid_tool_json = False
        self.hold = None
        self.server = None
        self.thread = None

    def register_usage_session(self, session_id, context, *, evidence_ref):
        self.usage_bindings[session_id] = {**context, "evidence_ref": evidence_ref}

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def start(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append(request)
                if owner.hold is not None:
                    owner.hold.wait(10)
                if owner.fail:
                    self.send_response(owner.failure_status)
                    self.end_headers()
                    self.wfile.write(json.dumps(owner.failure_body).encode())
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                def event(kind, data):
                    self.wfile.write(
                        f"event: {kind}\ndata: {json.dumps({'type': kind, **data})}\n\n".encode()
                    )

                event(
                    "message_start",
                    {
                        "message": {
                            "id": "msg_test",
                            "type": "message",
                            "role": "assistant",
                            "model": "deepseek-flash",
                            "content": [],
                            "stop_reason": None,
                            "usage": {"input_tokens": owner.input_tokens, "output_tokens": 0},
                        }
                    },
                )
                if owner.tool_calls and len(owner.requests) == 1:
                    event(
                        "content_block_start",
                        {
                            "index": 0,
                            "content_block": {
                                "type": "tool_use",
                                "id": "tool_test",
                                "name": owner.tool_name,
                                "input": {},
                            },
                        },
                    )
                    event(
                        "content_block_delta",
                        {
                            "index": 0,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": '{bad-json' if owner.invalid_tool_json else json.dumps(owner.tool_arguments),
                            },
                        },
                    )
                    reason = "tool_use"
                else:
                    event(
                        "content_block_start",
                        {"index": 0, "content_block": {"type": "text", "text": ""}},
                    )
                    event(
                        "content_block_delta",
                        {"index": 0, "delta": {"type": "text_delta", "text": "engineering reply"}},
                    )
                    reason = "end_turn"
                event("content_block_stop", {"index": 0})
                event(
                    "message_delta",
                    {
                        "delta": {"stop_reason": reason, "stop_sequence": None},
                        "usage": {"output_tokens": 1},
                    },
                )
                event("message_stop", {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.base_url

    def stop(self):
        if self.hold:
            self.hold.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(2)
            self.server = None
        return True


def wait_until(predicate, timeout=10):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.03)
    raise AssertionError("timed out waiting for original DSH event")


def test_real_enqueue_tool_result_and_settled_are_separate_from_business_report(local_roster):
    import json
    from modeling_team.runtimes.base import RuntimeDelivery

    adapter, run, broker = local_roster
    adapter.provider_factory = LocalMessagesProvider
    adapter.start_roster(run, run.configuration.profile.agents)
    assert set(adapter._provider.usage_bindings) == {a.session_id for a in adapter.agents.values()}
    for agent in adapter.agents.values():
        registered = adapter._provider.usage_bindings[agent.session_id]
        assert registered["role"] == agent.package.role
        assert registered["process_instance"] == agent.instance
        assert registered["run_id"] == run.run_id
    receipt = adapter.send_message(
        "modeling", RuntimeDelivery("coordinator", "modeling", "peer", "engineering task")
    )
    assert receipt.mode == "enqueue" and receipt.turn_id is None
    wait_until(lambda: adapter.dispatch_status("modeling")[0]["state"] == "settled")
    statuses = adapter.dispatch_status("modeling")
    assert statuses[0]["message_id"] == receipt.message_id
    assert statuses[0]["claimed_seq"] < statuses[0]["turn_end_seq"]
    assert adapter.wait_settled(["modeling"], 0.1)
    assert broker.results == {}  # ordinary reply and idle do not accept a business TaskResult
    assert any(message.text == "engineering reply" for message in adapter.receive_messages())
    requests = adapter._provider.requests
    assert len(requests) == 2
    assert requests[0]["model"] == "deepseek-flash"
    actual_names = {tool["name"] for tool in requests[0]["tools"]}
    expected_names = {
        adapter._public_name(server, tool["name"])
        for server, tool in adapter.agents["modeling"].expected_tools
    }
    assert actual_names == expected_names
    assert any("material-1" in json.dumps(message) for message in requests[1]["messages"])
    assert not adapter.terminal_report_blocked("modeling")


def test_active_pause_blocks_dispatch_keeps_host_receipts_and_resumes_original_session(
    local_roster,
):
    import threading
    from modeling_team.runtimes.base import RuntimeDelivery
    from modeling_team.runtimes.dsh import DshRuntimeError

    adapter, run, broker = local_roster
    adapter.provider_factory = LocalMessagesProvider
    adapter.start_roster(run, run.configuration.profile.agents)
    provider = adapter._provider
    provider.tool_calls = False
    provider.hold = threading.Event()
    receipt = adapter.send_message(
        "modeling", RuntimeDelivery("coordinator", "modeling", "peer", "engineering pause")
    )
    wait_until(lambda: len(provider.requests) == 1)
    second = adapter.send_message(
        "modeling", RuntimeDelivery("coordinator", "modeling", "peer", "busy queued input")
    )
    assert adapter.dispatch_status("modeling")[1]["state"] == "queued"
    identity = adapter.runtime_identity("modeling")
    groups = adapter.pause()
    assert all(item["state"] in {"T", "t"} for values in groups.values() for item in values)
    with pytest.raises(DshRuntimeError, match="dispatch-closed"):
        adapter.send_message("modeling", RuntimeDelivery("coordinator", "modeling", "peer", "late"))
    # The Host completes the response while the actual role process tree stays stopped.
    provider.hold.set()
    assert adapter.dispatch_status("modeling")[0]["state"] == "claimed"
    assert len(provider.requests) == 1
    adapter.resume()
    wait_until(
        lambda: all(item["state"] == "settled" for item in adapter.dispatch_status("modeling"))
    )
    after = adapter.runtime_identity("modeling")
    assert (
        after.runtime_identity == identity.runtime_identity
        and after.process_instance == identity.process_instance
    )
    assert len(provider.requests) == 2
    assert receipt.message_id == adapter.dispatch_status("modeling")[0]["message_id"]
    assert second.message_id == adapter.dispatch_status("modeling")[1]["message_id"]


def test_provider_wait_recovery_is_submitted_then_effective_in_same_session(local_roster):
    from modeling_team.runtimes.base import RuntimeDelivery
    from modeling_team.runtimes.dsh import DshRuntimeError

    adapter, run, broker = local_roster
    adapter.provider_factory = LocalMessagesProvider
    adapter.start_roster(run, run.configuration.profile.agents)
    provider = adapter._provider
    provider.fail = True
    provider.tool_calls = False
    adapter.send_message(
        "modeling", RuntimeDelivery("coordinator", "modeling", "peer", "engineering failure")
    )
    wait_until(lambda: adapter.provider_wait_status("modeling") is not None)
    wait_until(lambda: adapter.agents["modeling"].projection.activity is None)
    pending = adapter.provider_wait_status("modeling")
    identity = adapter.runtime_identity("modeling")
    assert pending["state"] == "waiting"
    assert len(provider.requests) == 1  # no automatic replay, including interrupted streams
    with pytest.raises(DshRuntimeError, match="wait_id changed"):
        adapter.recover_provider_wait("modeling", "recovered", wait_id="stale")
    adapter.pause()
    with pytest.raises(DshRuntimeError, match="pause/stop takes precedence"):
        adapter.recover_provider_wait("modeling", "recovered", wait_id=pending["wait_id"])
    adapter.resume()
    failed_recovery = adapter.recover_provider_wait(
        "modeling", "still failing", wait_id=pending["wait_id"]
    )
    assert failed_recovery.mode == "enqueue"
    wait_until(lambda: len(provider.requests) == 2)
    wait_until(lambda: adapter.wait_settled(["modeling"], 0.1))
    wait_until(lambda: adapter.provider_wait_status("modeling") is not None)
    pending = adapter.provider_wait_status("modeling")
    assert pending["variant"] == "QUOTA" and pending["http_status"] == 402
    repaired = []
    provider.refresh_credential = lambda credential: repaired.append(bytes(credential))
    run.provider_credential_bindings["deepseek-official"].path.write_text(
        "DEEPSEEK_API_KEY=repaired-test-key\n"
    )
    provider.fail = False
    receipt = adapter.recover_provider_wait(
        "modeling", "external issue fixed", wait_id=pending["wait_id"]
    )
    assert receipt.mode == "enqueue"
    wait_until(lambda: adapter.provider_wait_status("modeling") is None)
    assert adapter.runtime_identity("modeling").runtime_identity == identity.runtime_identity
    wait_until(lambda: adapter.wait_settled(["modeling"], 0.1))
    assert len(provider.requests) == 3
    assert repaired == [b"repaired-test-key"]


def test_terminal_report_accepts_live_claimed_turn_but_blocks_pending_and_late_inputs(local_roster):
    from modeling_team.runtimes.base import RuntimeDispatchReceipt
    from modeling_team.transport_mcp import RoutingError

    adapter, run, broker = local_roster
    adapter.provider_factory = LocalMessagesProvider
    adapter.start_roster(run, run.configuration.profile.agents)
    broker.terminal_commit = adapter.commit_terminal
    agent = adapter.agents["modeling"]
    agent.projection.append(
        {
            "seq": 0,
            "type": "agent/inbox/spliced",
            "data": {"target": "next-turn", "start": 0, "inserted": [{"id": "m"}]},
        }
    )
    agent.dispatches["host-test"] = RuntimeDispatchReceipt(
        "enqueue", None, "dsh", "host-test", agent.session_id, "m"
    )
    with pytest.raises(RoutingError, match="unconsumed"):
        broker.report("modeling", "completed", "premature")
    agent.projection.append({"seq": 1, "type": "turn/start", "data": {"turn": 1}})
    agent.projection.append(
        {
            "seq": 2,
            "type": "agent/inbox/spliced",
            "data": {"target": "next-turn", "start": 0, "removedCount": 1, "inserted": []},
        }
    )
    assert (
        broker.report("modeling", "completed", "valid report inside active turn").status
        == "completed"
    )
    with pytest.raises(RoutingError, match="terminal"):
        broker.send("coordinator", "modeling", "late input")


def test_explicit_restore_keeps_durable_session_and_sends_no_new_prompt(local_roster):
    import os
    import signal
    from modeling_team.runtimes.base import RuntimeDelivery
    from modeling_team.runtimes.dsh import DshRuntimeError

    adapter, run, broker = local_roster
    adapter.provider_factory = LocalMessagesProvider
    adapter.start_roster(run, run.configuration.profile.agents)
    adapter._provider.tool_calls = False
    adapter.send_message(
        "modeling",
        RuntimeDelivery("coordinator", "modeling", "peer", "engineering persisted history"),
    )
    wait_until(lambda: adapter.wait_settled(["modeling"], 0.1))
    agent = adapter.agents["modeling"]
    adapter._rpc(agent, "host/checkpoint", {"sessionId": agent.session_id})
    before = adapter.runtime_identity("modeling")
    calls = len(adapter._provider.requests)
    os.killpg(agent.process.pid, signal.SIGKILL)
    agent.process.wait(3)
    agent.pump.join(3)
    with pytest.raises(DshRuntimeError, match="reconciled writes"):
        adapter.restore_session("modeling")
    adapter.restore_session("modeling", writes_reconciled=True)
    after = adapter.runtime_identity("modeling")
    assert (
        before.runtime_identity == after.runtime_identity
        and before.process_instance != after.process_instance
    )
    assert len(adapter._provider.requests) == calls
    assert adapter._rpc(agent, "host/inspect", {})["tools"]


def test_direct_modeling_mcp_keeps_original_arguments_and_structured_result(local_roster):
    import json
    from modeling_team.runtimes.base import RuntimeDelivery

    adapter, run, broker = local_roster
    adapter.provider_factory = LocalMessagesProvider
    adapter.start_roster(run, run.configuration.profile.agents)
    provider = adapter._provider
    provider.tool_name = "mcp__runner_capability__modeling_submit_model_changes"
    provider.tool_arguments = {
        "modeling_id": "modeling",
        "request": {
            "schema_version": "r4-3-025-model-changes/v1",
            "candidate_ref": None,
            "changes": [
                {"change_id": "engineering-fixture", "intent": "synthetic-no-platform-write"}
            ],
        },
    }
    adapter.send_message(
        "modeling", RuntimeDelivery("coordinator", "modeling", "peer", "engineering bridge")
    )
    wait_until(lambda: adapter.wait_settled(["modeling"], 0.1))
    assert len(run.capability_calls) == 1
    call = run.capability_calls[0]
    assert call["role"] == "modeling" and call["operation"] == "modeling_submit_model_changes"
    assert call["arguments"] == provider.tool_arguments
    assert len(provider.requests) == 2
    assert "synthetic-no-platform-write" in json.dumps(provider.requests[1]["messages"])
    original_events = (run.root / "evidence/dsh-wire.jsonl").read_text()
    assert "structuredContent" in original_events and "engineering-fixture" in original_events
    assert broker.results == {}


def test_startup_configuration_can_be_corrected_without_replacing_an_admitted_session(local_roster):
    from modeling_team.runtimes.dsh import DshRuntimeError

    adapter, run, broker = local_roster
    original = adapter._check_tools
    adapter._check_tools = lambda role, inspection: original(role, {**inspection, "tools": []})
    with pytest.raises(DshRuntimeError, match="missing=") as failure:
        adapter.start_roster(run, run.configuration.profile.agents)
    assert failure.value.category == "platform-contract"
    first_base = adapter.agents["coordinator"].base
    assert (first_base / "stderr.log").exists()
    assert adapter.cleanup_identifiers()["complete"]
    assert all(
        adapter.provider_wait_status(agent.agent_id) is None
        for agent in run.configuration.profile.agents
    )
    adapter._check_tools = original
    identities = adapter.start_roster(run, run.configuration.profile.agents)
    assert len(identities) == 3
    assert adapter.agents["coordinator"].base != first_base
    assert (first_base / "stderr.log").exists()
    assert all(not agent.dispatches for agent in adapter.agents.values())
    with pytest.raises(DshRuntimeError, match="still owns role processes"):
        adapter.start_roster(run, run.configuration.profile.agents)


def _wire_run_materials(run, broker):
    from modeling_team.runner import TeamRunner

    runner = TeamRunner.__new__(TeamRunner)
    runner.run = run
    runner._competency_questions = True
    runner._multi_slice_workflow = True
    runner._staged_decisions = True
    runner._unified_graph = True
    (run.root / 'scenario-map').mkdir(exist_ok=True)
    (run.root / 'competency-questions/public').mkdir(parents=True, exist_ok=True)
    runner._prepare_handoff_materials()
    broker.materials = run.handoff_materials
    return runner


def test_real_dsh_coordinator_tool_transfers_original_artifact_without_host_copy(local_roster):
    from hashlib import sha256
    from modeling_team.runtimes.base import RuntimeDelivery

    adapter, run, broker = local_roster
    _wire_run_materials(run, broker)
    adapter.provider_factory = LocalMessagesProvider
    adapter.start_roster(run, run.configuration.profile.agents)
    provider = adapter._provider
    provider.tool_name = 'mcp__team_transport__write_handoff_output'
    content = '{\n "scenario_id": "工程原字节"\n}\n'
    provider.tool_arguments = {'relative_path': 'scenario-map/scenario-map.json', 'content': content}
    adapter.send_message('coordinator', RuntimeDelivery('runner', 'coordinator', 'task', 'fixture'))
    wait_until(lambda: adapter.wait_settled(['coordinator'], 0.1))
    assert (run.root / 'scenario-map/scenario-map.json').read_bytes() == content.encode()
    receipt = run.handoff_materials.artifacts['coordinator:scenario-map/scenario-map.json']
    assert receipt['state'] == 'received' and receipt['sha256'] == sha256(content.encode()).hexdigest()
    assert len(provider.requests) == 2
    assert 'runner_receipt' in __import__('json').dumps(provider.requests[1]['messages'])
    # The regular Runner reader sees those same bytes; semantic validation is unchanged.
    from modeling_team.scenario_map import load_scenario_map
    assert load_scenario_map(run.root / 'scenario-map/scenario-map.json')['scenario_id'] == '工程原字节'


def test_real_dsh_public_reference_is_read_and_native_consumption_is_separate(local_roster):
    import json

    adapter, run, broker = local_roster
    _wire_run_materials(run, broker)
    adapter.provider_factory = LocalMessagesProvider
    adapter.start_roster(run, run.configuration.profile.agents)
    store = run.handoff_materials
    path = run.root / 'competency-questions/public/public-projection-0001.json'
    path.write_text('{"questions":[{"question":"公开工程问题"}]}')
    store.queue_public_input(path, ['modeling'], 'public-digest',
                             freeze={'batch_id': 'batch-real-fixture', 'snapshot_digest': 'frozen'})
    # Resolve the immutable reference before the native message is sent.
    adapter.pause()
    store.flush_public_inputs(adapter)
    record = next(iter(store.public_inputs.values()))
    assert record['state'] == 'pending' and 'error' in record
    provider = adapter._provider
    provider.tool_name = 'mcp__team_transport__read_handoff_material'
    provider.tool_arguments = record['material_ref']
    adapter.resume()
    store.flush_public_inputs(adapter)
    wait_until(lambda: adapter.wait_settled(['modeling'], 0.1))
    store.flush_public_inputs(adapter)
    record = next(iter(store.public_inputs.values()))
    assert record['state'] == 'settled'
    status = adapter.dispatch_status('modeling')[0]
    assert status['queued_seq'] < status['claimed_seq'] < status['turn_end_seq']
    assert '公开工程问题' in json.dumps(provider.requests[1]['messages'], ensure_ascii=False)
    assert len(provider.requests) == 2
    store.flush_public_inputs(adapter)
    assert len(provider.requests) == 2
    assert broker.results == {}  # Read/settled are not semantic acceptance.


def test_public_dispatch_lost_reply_late_reconciliation_and_cancel_use_original_identity(local_roster):
    from modeling_team.runtimes.base import RuntimeDelivery
    from modeling_team.runtimes.dsh import DshRuntimeError

    adapter, run, broker = local_roster
    adapter.start_roster(run, run.configuration.profile.agents)
    agent = adapter.agents['modeling']
    original_rpc = adapter._rpc
    calls = []
    def lost_reply(target, method, params, **kwargs):
        calls.append(params)
        error = DshRuntimeError('fixture response lost')
        error.request_id = 999
        raise error
    adapter._rpc = lost_reply
    delivery = RuntimeDelivery('runner/competency-questions', 'modeling', 'cq-public-input',
                               'public-version-one', delivery_id='stable-public-id')
    with pytest.raises(DshRuntimeError):
        adapter.send_message('modeling', delivery)
    with pytest.raises(DshRuntimeError, match='delivery-unknown'):
        adapter.send_message('modeling', delivery)
    assert len(calls) == 1
    adapter._reconcile_enqueue(agent, {'id': 999, 'result': {'messageId': 'late-message'}})
    receipt = adapter.send_message('modeling', delivery)
    assert receipt.message_id == 'late-message' and len(calls) == 1
    with pytest.raises(DshRuntimeError, match='binding-changed'):
        adapter.send_message('modeling', __import__('dataclasses').replace(delivery, text='changed'))
    # Native cancellation proves this inbox message was never claimed.
    seq = agent.projection.next_seq
    agent.projection.append({'seq': seq, 'type': 'agent/inbox/spliced', 'data': {
        'target': 'next-turn', 'start': 0, 'inserted': [{'id': 'late-message'}]}})
    agent.projection.append({'seq': seq + 1, 'type': 'agent/inbox/spliced', 'data': {
        'target': 'next-turn', 'start': 0, 'removedCount': 1, 'inserted': [], 'outcome': 'canceled'}})
    # It may be resent only after cancellation; the delivery identity stays fixed.
    adapter._rpc = lambda *args, **kwargs: {'messageId': 'replacement-message'}
    second = adapter.send_message('modeling', delivery)
    assert second.message_id == 'replacement-message' and second.dispatch_id != receipt.dispatch_id
    adapter._rpc = original_rpc
