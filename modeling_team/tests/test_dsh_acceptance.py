"""R4.3-033: real pinned SDK/MCP/bwrap engineering checks; local provider only."""

import json
import subprocess
import threading
from pathlib import Path

import pytest

from modeling_team.acceptance_runtime import ExaminerRuntimeBlocked
from modeling_team.evaluation_owner import EvaluationOwner
from modeling_team.model_routing import TeamModelProfileError, load_team_model_profile
from modeling_team.runtimes.acceptance import validate_acceptance_profile
from modeling_team.runtimes.dsh_acceptance import DshAcceptanceRuntime
from modeling_team.tests.test_dsh_runtime import LocalMessagesProvider, wait_until
from modeling_team.tests.test_r3011_acceptance_runtime import (
    _batch_packet,
    _questions,
    _examiner_entry,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILE = "dsh-acceptance-deepseek-flash-low"


class ScriptedProvider(LocalMessagesProvider):
    steps = []

    def start(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        owner = self
        self.steps = list(type(self).steps)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append(request)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                def event(kind, **data):
                    self.wfile.write(
                        f"event: {kind}\ndata: {json.dumps({'type': kind, **data})}\n\n".encode()
                    )

                event(
                    "message_start",
                    message={
                        "id": f"reply-{len(owner.requests)}",
                        "type": "message",
                        "role": "assistant",
                        "model": "deepseek-flash",
                        "content": [],
                        "stop_reason": None,
                        "usage": {"input_tokens": 1, "output_tokens": 0},
                    },
                )
                step = owner.steps.pop(0) if owner.steps else None
                if step:
                    name, arguments = step(request) if callable(step) else step
                    event(
                        "content_block_start",
                        index=0,
                        content_block={
                            "type": "tool_use",
                            "id": f"call-{len(owner.requests)}",
                            "name": name,
                            "input": {},
                        },
                    )
                    event(
                        "content_block_delta",
                        index=0,
                        delta={"type": "input_json_delta", "partial_json": json.dumps(arguments)},
                    )
                else:
                    event(
                        "content_block_start", index=0, content_block={"type": "text", "text": ""}
                    )
                    event(
                        "content_block_delta",
                        index=0,
                        delta={"type": "text_delta", "text": "engineering only"},
                    )
                event("content_block_stop", index=0)
                event(
                    "message_delta",
                    delta={
                        "stop_reason": "tool_use" if step else "end_turn",
                        "stop_sequence": None,
                    },
                    usage={"output_tokens": 1},
                )
                event("message_stop")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.base_url


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    from modeling_team.runtimes import dsh_acceptance

    monkeypatch.setattr(
        dsh_acceptance, "preflight_profile_credentials", lambda p: {"deepseek-official": object()}
    )
    monkeypatch.setattr(
        dsh_acceptance, "read_deepseek_credential", lambda b: b"fake-engineering-key"
    )
    adapter = DshAcceptanceRuntime(repository_root=ROOT, provider_factory=ScriptedProvider)
    adapter._run_root = tmp_path
    adapter.bind_acceptance_model_profile(load_team_model_profile(ROOT, PROFILE))
    ScriptedProvider.steps = []
    yield adapter
    if adapter.resource and not adapter.resource.destroyed:
        adapter.resource.destroy()


def options(packet):
    return dict(
        read_key="fake-platform-key",
        platform_forwarder=lambda *args: {"ok": True, "data": {}},
        ontology_ids={key: "graph" for key in packet.payload["authorized_scope"]},
    )


@pytest.mark.parametrize("role", ["platform-examiner", "acceptance"])
def test_actual_isolated_loading_tools_and_process_pause(runtime, role):
    packet = _batch_packet(role=role)
    child = runtime.launch_v3_acceptance_child(
        packet,
        role_instructions="engineering",
        reports=[],
        **(options(packet) if role == "platform-examiner" else {}),
    )
    registered = runtime.transport._provider.usage_bindings[child.agent.session_id]
    assert registered["role"] == role
    assert registered["batch_id"] == packet.batch_id
    assert registered["run_id"] == packet.payload["run_id"]
    assert registered["process_instance"] == child.agent.instance
    assert "operation_id" not in registered  # A batch is not an operation identity.
    tools = {t["name"] for t in runtime.transport._rpc(child.agent, "host/inspect", {})["tools"]}
    assert not any(
        name in " ".join(tools).lower()
        for name in ("shell", "edit_file", "subagent", "start_run", "apply_batch")
    )
    assert any("platform_read_proxy" in t for t in tools) is (role == "platform-examiner")
    assert child.thread_id is None and child.identity["runtime"] == "dsh"
    command = runtime.transport.namespace_command(child.agent)
    code = "import fs from 'node:fs'; console.log(JSON.stringify({repo:fs.existsSync(process.argv[1]),home:fs.existsSync(process.argv[2]),key:process.env.DEEPSEEK_API_KEY,input:fs.readFileSync('/agent/home/input.json','utf8')}));"
    probe = subprocess.run(
        command[: command.index("--") + 1]
        + ["/agent/node", "--input-type=module", "-e", code, str(ROOT), str(Path.home())],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert probe.returncode == 0, probe.stderr
    seen = json.loads(probe.stdout)
    assert not seen["repo"] and not seen["home"] and "key" not in seen
    if role == "platform-examiner":
        assert "answer_points" not in seen["input"] and "approved material" not in seen["input"]
    else:
        assert "approved material" in seen["input"]
    owner = EvaluationOwner(child.evidence_root / "owner")
    try:
        owner.bind(runtime, child)
        identity = child.identity
        for action in ("pause", "resume"):
            owner.receipts[action] = {"action": action, "target_threads": [owner._member_id(child)]}
            owner._dispatch_control(
                child, {"request_id": action, "action": action, "text": "control"}
            )
            assert owner.receipts[action]["status"] == "effective"
            assert child.user_waiting is (action == "pause")
            if action == "pause":
                assert all(p["state"] in {"T", "t"} for p in runtime.transport._group(child.agent))
        assert identity == child.identity
    finally:
        owner.release(child)
        owner.close()
    child.destroy()
    assert not Path(child.spec["private_root"]).exists()
    assert runtime.transport.cleanup_identifiers()["complete"]


def test_real_mcp_read_report_correction_and_retained_followup(runtime):
    packet = _batch_packet(questions=_questions(1))
    entry = _examiner_entry(packet.batch_id, "cq-1")
    entry["evidence_refs"] = ["p0"]
    ScriptedProvider.steps = [
        (
            "mcp__platform_read_proxy__query_semantic_context",
            {"ontology_ids": ["ontology-1"], "query": "engineering"},
        ),
        ("mcp__examiner_report__submit_examiner_report", dict(entry, question_content_version=999)),
        ("mcp__examiner_report__submit_examiner_report", entry),
    ]
    reports, teardown, observed, reads = [], {}, {}, []
    owner = EvaluationOwner(runtime._run_root / "owner")
    try:
        returned = runtime.run_v3_acceptance_child(
            packet,
            role_instructions="engineering",
            reports=reports,
            **options(packet),
            response_persistence=lambda path, doc: reads.append((path, doc)),
            timeout_seconds=15,
            teardown=teardown,
            examiner_observables=observed,
            cooperative_owner=owner,
        )
        assert returned == [entry] == reports
        assert len(reads) == len(observed["receipts"]) == 1
        child = runtime.resource
        assert len(child.report_sink._rejections) == 1
        assert child.report_sink._thread is None and child.task_closed
        assert teardown["consumer_retained"] and teardown["runtime_session_id"]
        assert "thread_id" not in teardown and "model_usage" not in teardown
        provider = runtime.transport._provider
        assert len(provider.requests) == 4
        submitted = json.dumps(provider.requests)
        assert "fake-platform-key" not in submitted and "fake-engineering-key" not in submitted
        child.control({"request_id": "followup", "action": "consult", "text": "只读解释"})
        wait_until(lambda: child.terminal_event)
        assert reports == [entry] and len(provider.requests) == 5
    finally:
        owner.close()
    assert runtime.resource.destroyed
    assert (runtime.resource.evidence_root / "sessions").is_dir()


def test_finished_partial_session_is_technical_incomplete(runtime):
    packet = _batch_packet(questions=_questions(2))
    entry = _examiner_entry(packet.batch_id, "cq-1")
    ScriptedProvider.steps = [("mcp__examiner_report__submit_examiner_report", entry)]
    reports, teardown = [], {}
    with pytest.raises(ExaminerRuntimeBlocked) as error:
        runtime.run_v3_acceptance_child(
            packet,
            role_instructions="engineering",
            reports=reports,
            **options(packet),
            timeout_seconds=10,
            teardown=teardown,
        )
    assert error.value.evidence["reason_code"] == "batch-incomplete"
    assert reports == [entry]
    assert teardown["child_destroyed"] and teardown["socket_root_removed"]


def test_exact_roles_and_no_production_profile_fallback():
    profile = load_team_model_profile(ROOT, PROFILE)
    validate_acceptance_profile("dsh", profile)
    with pytest.raises(TeamModelProfileError, match="binding-missing"):
        validate_acceptance_profile("dsh", load_team_model_profile(ROOT, "dsh-deepseek-flash-low"))
    with pytest.raises(TeamModelProfileError, match="unsupported-runtime-provider"):
        validate_acceptance_profile("codex", profile)
    with pytest.raises(TeamModelProfileError, match="service_tier"):
        validate_acceptance_profile("dsh", profile, service_tier="fast")


def test_native_judge_requires_real_frozen_read_receipt_and_separate_session(runtime):
    from modeling_team.tests.test_v43_judge_references import reference_packet, arguments, verdict

    packet = reference_packet(1)
    entry = verdict(packet, "cq-1")
    ScriptedProvider.steps = [
        ("mcp__examiner_report__submit_examiner_report", entry),
        ("mcp__examiner_report__read_frozen_evidence", arguments(packet)),
        ("mcp__examiner_report__submit_examiner_report", entry),
    ]
    reports, teardown = [], {}
    runtime.run_v3_acceptance_child(
        packet,
        role_instructions="engineering",
        reports=reports,
        timeout_seconds=15,
        teardown=teardown,
    )
    child = runtime.resource
    assert reports == [entry]
    assert len(child.report_sink._rejections) == 1
    assert len(child.report_sink.batch_contract.source_read_receipts) == 1
    assert "platform_read_proxy" not in json.dumps(child.agent.expected_tools)
    assert teardown["child_destroyed"]
    old_identity = child.identity
    # Another group is a fresh private process/session, with no stale messages.
    ScriptedProvider.steps = [
        ("mcp__examiner_report__read_frozen_evidence", arguments(packet)),
        ("mcp__examiner_report__submit_examiner_report", entry),
    ]
    runtime.run_v3_acceptance_child(
        packet, role_instructions="engineering", reports=[], timeout_seconds=15
    )
    assert runtime.resource.identity != old_identity


def test_late_bound_member_is_frozen_before_any_prompt(runtime):
    child = runtime.launch_v3_acceptance_child(
        _batch_packet(), role_instructions="engineering", reports=[], **options(_batch_packet())
    )
    owner = EvaluationOwner(runtime._run_root / "owner")
    owner.pending_pause = "p"
    owner._flow_message = {"request_id": "p", "action": "pause", "text": "wait"}
    owner.receipts["p"] = {"action": "pause", "status": "owner_waiting"}
    try:
        owner.bind(runtime, child)
        assert child.user_waiting and owner.receipts["p"]["status"] == "effective"
        assert runtime.transport._provider.requests == []
        assert child.agent.dispatches == {}
        owner.receipts["r"] = {"action": "resume", "target_threads": [owner._member_id(child)]}
        owner._dispatch_control(child, {"request_id": "r", "action": "resume", "text": "go"})
        assert owner.pending_pause is None
    finally:
        owner.release(child)
        owner.close()


def test_active_pause_keeps_owner_online_and_resumes_original_session(runtime):
    packet = _batch_packet(questions=_questions(1))
    entry = _examiner_entry(packet.batch_id, "cq-1")
    provider_entered, provider_release = threading.Event(), threading.Event()

    def held_report(request):
        provider_entered.set()
        assert provider_release.wait(10)
        return "mcp__examiner_report__submit_examiner_report", entry

    ScriptedProvider.steps = [held_report]
    owner = EvaluationOwner(runtime._run_root / "owner")
    failures = []

    def controller():
        try:
            assert provider_entered.wait(10)
            for action in ("pause", "resume"):
                with (owner.root / "input.fifo").open("w") as fifo:
                    fifo.write(
                        json.dumps(
                            {"request_id": action, "action": action, "text": "engineering control"}
                        )
                        + "\n"
                    )
                wait_until(lambda: owner.receipts.get(action, {}).get("status") == "effective")
                if action == "pause":
                    assert runtime.resource.user_waiting
                    assert runtime.resource.submitted_reports == []
                    assert runtime.resource.agent.projection.activity is not None
                    provider_release.set()
        except BaseException as exc:
            failures.append(exc)
            provider_release.set()

    thread = threading.Thread(target=controller)
    thread.start()
    reports = []
    try:
        runtime.run_v3_acceptance_child(
            packet,
            role_instructions="engineering",
            reports=reports,
            **options(packet),
            timeout_seconds=15,
            cooperative_owner=owner,
        )
        thread.join(5)
        assert not thread.is_alive() and not failures
        assert reports == [entry]
        pause = next(iter(owner.receipts["pause"]["member_results"].values()))
        resume = next(iter(owner.receipts["resume"]["member_results"].values()))
        assert pause["runtime_session_id"] == resume["runtime_session_id"]
        assert pause["process_instance"] == resume["process_instance"]
    finally:
        provider_release.set()
        thread.join(5)
        owner.close()


def test_sink_acceptance_survives_lost_response_and_close_wins_over_late_report(runtime):
    import socket

    packet = _batch_packet(questions=_questions(1))
    reports = []
    child = runtime.launch_v3_acceptance_child(
        packet, role_instructions="engineering", reports=reports, **options(packet)
    )
    entry = _examiner_entry(packet.batch_id, "cq-1")
    # Submit and disconnect without reading the receipt. The Host must keep the
    # accepted set instead of replaying this report or inferring failure from EOF.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(child.report_sink.socket_path))
        client.sendall(json.dumps({"token": child.report_sink.token, "report": entry}).encode())
    wait_until(lambda: child.report_sink.batch_contract.is_complete)
    assert reports == [entry]
    child.close_reports()
    with pytest.raises(ValueError, match="closed"):
        child.accept(dict(entry, answer="late replacement"))
    child.destroy()
    assert reports == [entry]
