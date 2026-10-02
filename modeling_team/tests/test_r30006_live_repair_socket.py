"""R3.0-006 live repair/resume: real local HTTP and AF_UNIX fault chains.

Two bounded sequences exercise production boundaries only -- the run's own
``RunnerCapabilityEndpoint`` AF_UNIX capability entry, the real
``TeamTransportBroker`` (``report_issue`` and Coordinator-only
``issue_control``), the production foreground admission path
(``modeling_team.__main__._handle_foreground_message``, the shared stdin/FIFO
boundary) and the real staged write classification:

* known no-write: a loopback HTTP write dependency answers a real 503 before
  any write, is repaired in place, and the same run/thread/candidate
  submission then succeeds with the verbatim original request after a
  Coordinator pause, a bound short outer resolution and a same-thread resume
  on a new turn (test plan §3.1-§3.4).
* write followed by no response: a real AF_UNIX endpoint consumes the batch
  bytes and never replies, so the intent is durably ``unknown`` and the staged
  gate stays closed; neither the bound short repair nor the legacy five-field
  reconciliation string unlocks it, and no second submission is forwarded
  (test plan §3 "写后无响应" sequence).

The temporary local dependency clients are the only new machinery here.  They
mirror the production classification contract of
``staged_batch_write_forwarder.forward_staged_modeling_batch`` (definite
pre-write rejection vs unknown-after-dispatch) over real sockets instead of
spawning the canonical stdio MCP child, because no platform service, semantic
start or LLM role run is authorized in this round.  The Runtime adapter is a
mechanical ``CapturingAdapter`` subclass: it records deliveries, exposes real
thread identities and returns production ``RuntimeDispatchReceipt`` values.
This file proves the Runner/Transport/foreground live-repair contracts; it
does not prove R3.0-006 semantic E2E.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from modeling_team import __main__ as foreground
from modeling_team.runtimes.base import RuntimeDispatchReceipt
from modeling_team.staged_batch_write_forwarder import WRITE_TOOL
from modeling_team.staged_decisions import (
    StagedBatchForwardError,
    StagedBatchForwardUnknown,
    staged_decision_artifact_paths,
)
from modeling_team.tests.test_r30002_runner_wiring import _gate_state
from modeling_team.tests.test_r30009_plan_ref_capability_schema import (
    PLAN_REF,
    _call,
    _protocol_capability,
)
from modeling_team.tests.test_r30009_runner_wiring import (
    _batch_items,
    _open_platform_gate_unified,
    _unified_args,
    _UnifiedRunner,
)
from modeling_team.tests.test_runner import CapturingAdapter
from modeling_team.transport_mcp import TeamTransportBroker, mcp_response

REPORTER_ID = "protocol"
COORDINATOR_ID = "coordinator"
REPORTER_THREAD = "thread-r30006-protocol"
REPAIR_TEXT = "接口已经修复完成，请继续原失败步骤。"


# --- the temporary local write dependencies -----------------------------------


class _LocalWriteDependency:
    """A real loopback HTTP write dependency with a controllable health.

    While unhealthy it answers 503 *before* performing any write; its own
    request/write logs are the evidence that the first attempt wrote nothing.
    ``repair`` flips the same listening socket to a healthy 200 without moving
    the endpoint, which is what a local service restart means here.
    """

    def __init__(self) -> None:
        self.healthy = False
        self.requests: list[bytes] = []
        self.writes: list[bytes] = []
        dependency = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server API name
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                dependency.requests.append(body)
                if not dependency.healthy:
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                dependency.writes.append(body)
                payload = json.dumps(
                    {"ok": True, "data": {"batch_id": "batch-r30006-1"}},
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:  # keep test output pristine
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="r30006-write-dependency", daemon=True
        )
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def repair(self) -> None:
        self.healthy = True

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


class _LoopbackHttpForwarder:
    """The temporary dependency client: one real HTTP POST per staged batch.

    Classification mirrors the production forwarder contract: a connection
    failure or a pre-write refusal is definite (``StagedBatchForwardError``),
    while a dispatched call that yields no usable batch identity stays unknown
    (``StagedBatchForwardUnknown``).
    """

    def __init__(self, dependency: _LocalWriteDependency, timeout: float = 5.0) -> None:
        self._dependency = dependency
        self._timeout = timeout
        self.batches: list[dict] = []

    def __call__(self, batch) -> dict:
        self.batches.append(json.loads(json.dumps(batch)))
        payload = json.dumps(batch, ensure_ascii=False, sort_keys=True).encode("utf-8")
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1", self._dependency.port, timeout=self._timeout
            )
            try:
                connection.request(
                    "POST",
                    "/modeling-batches",
                    body=payload,
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                body = response.read()
            finally:
                connection.close()
        except OSError as exc:
            raise StagedBatchForwardError(
                f"{WRITE_TOOL} could not be reached and nothing was written: {exc}"
            ) from exc
        if response.status != 200:
            raise StagedBatchForwardError(
                f"{WRITE_TOOL} was rejected before any write (http {response.status})"
            )
        envelope = json.loads(body.decode("utf-8"))
        data = envelope.get("data") if isinstance(envelope, dict) else None
        if envelope.get("ok") is not True or not isinstance(data, dict) or not data.get("batch_id"):
            raise StagedBatchForwardUnknown(
                f"{WRITE_TOOL} did not return a usable reply after dispatch"
            )
        return dict(data)


class _SilentSocketDependency:
    """A real AF_UNIX write dependency that reads the batch and never replies.

    The fault is the socket contract itself: the request bytes are delivered
    to a live endpoint and no response ever arrives, which is exactly the
    durable write-followed-by-no-response shape.
    """

    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path
        self.request_bodies: list[bytes] = []
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        socket_path.unlink(missing_ok=True)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(socket_path))
        self._server.listen(4)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="r30006-silent-write", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        self._server.settimeout(0.2)
        while not self._stop.is_set():
            try:
                connection, _ = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                try:
                    connection.settimeout(2.0)
                    with connection.makefile("rb") as reader:
                        body = reader.readline(1_048_577)
                    if body:
                        self.request_bodies.append(body)
                except OSError:
                    return
                # Deliberately no reply, ever.
                self._stop.wait(30)

    def stop(self) -> None:
        self._stop.set()
        self._server.close()
        self._thread.join(timeout=2)
        self.socket_path.unlink(missing_ok=True)


class _UnixNoResponseForwarder:
    """Dispatch one real AF_UNIX write and observe that no reply ever comes."""

    def __init__(self, dependency: _SilentSocketDependency, timeout: float = 1.0) -> None:
        self._dependency = dependency
        self._timeout = timeout
        self.batches: list[dict] = []

    def __call__(self, batch) -> dict:
        self.batches.append(json.loads(json.dumps(batch)))
        request = (json.dumps(batch, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        dispatched = False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self._timeout)
                client.connect(str(self._dependency.socket_path))
                client.sendall(request)
                dispatched = True
                reply = client.makefile("rb").readline(1_048_577)
        except OSError as exc:
            if not dispatched:
                raise StagedBatchForwardError(
                    f"{WRITE_TOOL} could not be reached and nothing was written: {exc}"
                ) from exc
            raise StagedBatchForwardUnknown(
                f"{WRITE_TOOL} did not return a usable reply after dispatch: {exc}"
            ) from exc
        raise StagedBatchForwardUnknown(
            f"{WRITE_TOOL} did not return a usable reply after dispatch: "
            f"{len(reply)} bytes without a batch identity"
        )


# --- mechanical instrumentation of the Runtime boundary ------------------------


class _LiveIssueAdapter(CapturingAdapter):
    """Record deliveries with real thread/turn identities; no LLM role run.

    ``send_message`` opens the reporter turn and returns the production
    ``RuntimeDispatchReceipt("start", ...)`` the resume contract requires;
    the test closes the turn afterwards to model the reporter finishing, the
    same observable a real App Server thread produces.
    """

    def __init__(self) -> None:
        super().__init__()
        self.turns = 0
        self.agents = {
            agent_id: SimpleNamespace(
                process=None,
                thread_id=f"thread-r30006-{agent_id}",
                active_turn_id=None,
            )
            for agent_id in ("coordinator", "modeling", "protocol")
        }

    def send_message(self, agent_id, delivery):
        self.messages.append((agent_id, delivery))
        self.turns += 1
        receipt = RuntimeDispatchReceipt("start", f"turn-r30006-{self.turns}")
        agent = self.agents.get(agent_id)
        if agent is not None:
            agent.active_turn_id = receipt.turn_id
        return receipt

    def finish_turn(self, agent_id: str) -> None:
        self.agents[agent_id].active_turn_id = None

    def receive_messages(self):
        # No agent turns are modelled here: the drain must reflect only the
        # real issue-path output, never a canned agent reply.
        return []


class _ForegroundSink:
    """Collect exactly what the production foreground path would print."""

    def __init__(self) -> None:
        self.outputs: list[dict] = []
        self.rejections: list[dict] = []

    def emit_and_observe(self, output) -> None:
        self.outputs.extend(output)

    def emit_outer_input_rejection(self, detail=None) -> None:
        payload = dict(foreground._OUTER_INPUT_REJECTION)
        if detail is not None:
            payload.update(detail)
        self.rejections.append(payload)


# --- shared helpers ------------------------------------------------------------


def _wire_transport(runner) -> None:
    """Wire the real Team Transport the way ``TeamRunner.start`` does.

    ``start`` builds this exact Broker -- same run-local root, frozen Profile
    permission set, terminal dependency graph and issue-escalation switches --
    before any Agent process exists, and a prepared-only runner never reaches
    that line because no roster may start here.  The fixture performs the
    identical non-formal staged wiring so ``report_issue``/``issue_control``
    and the Runner issue event queue are the production pair.
    """

    role_agents = {
        agent.package.role: agent.agent_id
        for agent in runner.run.configuration.profile.agents
    }
    event_lock = threading.Lock()

    def issue_event_callback(event: dict) -> None:
        with runner._issue_event_lock:
            runner._issue_event_queue.append(deepcopy(event))

    def transport_event_observer(event: dict) -> None:
        with event_lock:
            runner._append_team_transport_event(event)

    runner.transport = TeamTransportBroker(
        runner.run.root / "transport" / "broker",
        set(runner.run.configuration.profile.communication),
        terminal_dependencies={
            role_agents["protocol"]: {role_agents["modeling"]},
            role_agents["coordinator"]: {
                role_agents["modeling"],
                role_agents["protocol"],
            },
        },
        modeling_agent_id=role_agents["modeling"],
        coordinator_agent_id=role_agents["coordinator"],
        terminal_report_guard=runner._terminal_report_guard,
        transport_event_observer=transport_event_observer,
        issue_escalation_enabled=True,
        issue_event_callback=issue_event_callback,
    )


def _paths(staged) -> dict:
    return staged_decision_artifact_paths(staged.run_root, unified=True)


def _intent(staged, ordinal: int = 1) -> dict:
    path = _paths(staged)["intents_dir"] / f"intent-{ordinal}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _receipt_names(staged) -> list[str]:
    receipts = _paths(staged)["receipts_dir"]
    return sorted(path.name for path in receipts.iterdir()) if receipts.exists() else []


def _identity(staged) -> dict[str, bytes]:
    """The live identity bytes that must survive the repair window unchanged."""
    paths = _paths(staged)
    return {
        name: path.read_bytes()
        for name, path in (
            ("candidate", paths["candidates_dir"] / "cand-1-r2.json"),
            ("plan", paths["materialization_plans_dir"] / "plan-1-r1.json"),
            ("approvals", paths["approvals"]),
            ("slot", paths["stage3_slot"]),
        )
    }


def _evidence(staged, name: str) -> list[dict]:
    path = staged.run_root / "evidence" / f"{name}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ledger(runner):
    accessor = runner.transport.issue_ledger
    return accessor() if callable(accessor) else accessor


def _transport_call(runner, agent_id: str, name: str, arguments: dict) -> dict:
    response = mcp_response(
        {"method": "tools/call", "params": {"name": name, "arguments": arguments}},
        broker=runner.transport,
        agent_id=agent_id,
    )
    return json.loads(response["content"][0]["text"])


def _report_issue(runner, *, mutation_state: str, error: str) -> dict:
    return _transport_call(
        runner,
        REPORTER_ID,
        "report_issue",
        {
            "category": "platform_repair",
            "summary": "本地写依赖不可用，原提交失败",
            "failing_operation": "protocol_staged_submit_modeling_batch",
            "error": error,
            "mutation_state": mutation_state,
            "requested_action": "pause",
        },
    )


def _issue_control(runner, action: str, issue_id: str, epoch: int, **extra) -> dict:
    arguments = {
        "issue_id": issue_id,
        "reporter_id": REPORTER_ID,
        "action": action,
        "control_epoch": epoch,
        **extra,
    }
    return _transport_call(runner, COORDINATOR_ID, "issue_control", arguments)


def _pump(runner, sink: _ForegroundSink) -> list[dict]:
    """Admit one real foreground status line: the boundary that drains output."""

    before = len(sink.outputs)
    foreground._handle_foreground_message(
        runner,
        json.dumps({"action": "status"}),
        sink.emit_and_observe,
        sink.emit_outer_input_rejection,
    )
    return sink.outputs[before:]


def _admit_line(runner, sink: _ForegroundSink, line: str) -> dict | None:
    """One outer line through the production admission path; last rejection."""

    before = len(sink.rejections)
    foreground._handle_foreground_message(
        runner, line, sink.emit_and_observe, sink.emit_outer_input_rejection
    )
    return sink.rejections[-1] if len(sink.rejections) > before else None


def _short_resolution_line(run_id: str, issue_id: str, epoch: int, *, with_run_id: bool = True) -> str:
    message = {
        "action": "issue_resolution",
        "issue_id": issue_id,
        "reporter_id": REPORTER_ID,
        "control_epoch": epoch,
        "resolution_type": "repair_completed",
        "repair_component": "external_service",
        "resolution_text": REPAIR_TEXT,
    }
    if with_run_id:
        message["run_id"] = run_id
    return json.dumps(message, ensure_ascii=False)


def _legacy_resolution_line(issue_id: str, epoch: int) -> str:
    return json.dumps(
        {
            "action": "issue_resolution",
            "issue_id": issue_id,
            "reporter_id": REPORTER_ID,
            "control_epoch": epoch,
            "resolution_type": "repair_completed",
            "repair_component": "external_service",
            "before_digest": "sha256:" + "1" * 64,
            "after_digest": "sha256:" + "2" * 64,
            "verification_reference": "repair-ticket-r30006",
            "mutation_reconciliation": "reconciled",
        },
        ensure_ascii=False,
    )


def _issue_report_delivery_count(runner, kind: str) -> int:
    return sum(1 for _agent, delivery in runner.adapter.messages if delivery.kind == kind)


# --- sequence 1: known no-write 503, repair, same-thread resume ----------------


def test_known_no_write_503_repairs_and_resumes_the_same_run_and_thread(tmp_path):
    dependency = _LocalWriteDependency()
    forwarder = _LoopbackHttpForwarder(dependency)
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    runner = staged.runner
    runner.adapter = _LiveIssueAdapter()
    sink = _ForegroundSink()
    try:
        staged.prepare()
        _wire_transport(runner)
        assert runner.transport.coordinator_agent_id == COORDINATOR_ID
        assert runner.transport.issue_escalation_enabled is True
        _open_platform_gate_unified(staged)
        identity_before = _identity(staged)
        starts_before = len(runner.adapter.started)
        messages_before = len(runner.adapter.messages)
        arguments = _unified_args(_batch_items(), PLAN_REF)

        with _protocol_capability(staged) as endpoint:
            # 1) the original operation fails at the real dependency: 503, no write.
            failed = _call(endpoint, arguments)
            structured = failed["result"]["structuredContent"]
            assert structured["ok"] is False, structured
            assert structured["error"]["reason_code"] == "staged_batch_forward_failed"
            # The 503 is a definite pre-write refusal: recorded as a closed
            # ``rejected`` intent (closed position, not an unsettled write)
            # while the same key stays retryable after the repair.
            assert _intent(staged)["status"] == "rejected"
            assert _receipt_names(staged) == []
            assert runner._staged_gate_killed is False
            assert len(dependency.requests) == 1
            assert dependency.writes == []
            first_request = dependency.requests[0]

            # 2) the responsible role reports the issue over the real transport.
            report = _report_issue(
                runner,
                mutation_state="confirmed_no_write",
                error="本地写依赖返回 503，未执行写入",
            )
            issue_id = report["issue_id"]
            assert issue_id == "issue-1"
            assert report["mutation_state"] == "confirmed_no_write"
            assert _ledger(runner).state == "reported"
            _pump(runner, sink)
            assert _issue_report_delivery_count(runner, "issue") == 1
            active = _ledger(runner).active_issue
            assert active.thread_id == REPORTER_THREAD
            assert active.category == "platform_repair"
            epoch = active.control_epoch

            # 3) the short repair cannot land before the Coordinator pause.
            early = _admit_line(
                runner, sink, _short_resolution_line(runner.run.run_id, issue_id, epoch)
            )
            assert early is not None and early["code"] == "invalid_outer_input"
            assert _ledger(runner).state == "reported"

            # 4) the Coordinator pauses cooperatively; the reporter turn finishes.
            control = _issue_control(runner, "pause", issue_id, epoch)
            assert control["action"] == "pause" and control["control_epoch"] == epoch
            pause_output = _pump(runner, sink)
            # The pause drain surfaces the escalated issue and the control ack.
            assert [entry["type"] for entry in pause_output] == ["issue", "issue-control"]
            assert _ledger(runner).state == "waiting_repair"
            pause_turn = runner.adapter.agents[REPORTER_ID].active_turn_id
            runner.adapter.finish_turn(REPORTER_ID)

            # 5) the repair window preserves the whole live identity.
            assert _identity(staged) == identity_before
            assert _ledger(runner).active_issue.issue_id == issue_id
            assert len(runner.adapter.started) == starts_before
            control_evidence = _evidence(staged, "issue-control")
            assert [record.get("action") for record in control_evidence] == ["pause"]
            assert all("event" not in record for record in control_evidence)

            # 6) a malformed outer line is rejected alone; nothing else moves.
            deliveries_before = list(runner.adapter.messages)
            malformed = _admit_line(runner, sink, '{"action": "issue_resolu')
            assert malformed is not None and malformed["code"] == "invalid_outer_input"
            assert list(runner.adapter.messages) == deliveries_before
            assert _ledger(runner).state == "waiting_repair"

            # 7) the local dependency is repaired on the same listening socket.
            dependency.repair()

            # 8) the bound short resolution crosses the production foreground path.
            # #31 (auth021): the resolution settles the ledger itself and the
            # admission pump dispatches the resume control inline — the exact
            # control a correct Coordinator would have issued — so the idle
            # reporter is woken within this admission, not on a later
            # Coordinator-issued resume.
            before = len(sink.outputs)
            accepted = _admit_line(
                runner, sink, _short_resolution_line(runner.run.run_id, issue_id, epoch)
            )
            assert accepted is None
            assert _ledger(runner).state == "resolved"
            assert any(
                entry["type"] == "issue-control" for entry in sink.outputs[before:]
            )
            assert [
                record["resolution_type"] for record in _evidence(staged, "issue-resolution")
            ] == ["repair_completed"]

            # 9) the settlement dispatched the resume: same thread, new turn.
            controls = _evidence(staged, "issue-control")
            assert [record["action"] for record in controls] == ["pause", "resume"]
            assert {record["before_thread_id"] for record in controls} == {REPORTER_THREAD}
            assert {record["after_thread_id"] for record in controls} == {REPORTER_THREAD}
            assert {record["dispatch_mode"] for record in controls} == {"start"}
            assert controls[1]["after_turn_id"] != controls[0]["after_turn_id"]
            assert controls[1]["after_turn_id"] != pause_turn
            assert _issue_report_delivery_count(runner, "issue-control") == 2

            # A Coordinator resume racing the settlement is a typed rejection.
            try:
                _issue_control(
                    runner,
                    "resume",
                    issue_id,
                    epoch,
                    resolution_type="repair_completed",
                    repair_component="external_service",
                    resolution_text=REPAIR_TEXT,
                )
            except Exception as exc:
                assert "issue resume requires persisted resolution" in str(exc)
            else:
                raise AssertionError("racing coordinator resume must be rejected")

            # 10) the original operation succeeds with the verbatim request.
            recovered = _call(endpoint, arguments)
            recovered_structured = recovered["result"]["structuredContent"]
            assert recovered_structured["ok"] is True, recovered_structured
            assert _intent(staged)["status"] == "receipted"
            assert _receipt_names(staged) == ["receipt-1.json"]
            assert len(dependency.requests) == 2
            assert dependency.requests[1] == first_request
            assert dependency.writes == [first_request]
            assert forwarder.batches[0] == forwarder.batches[1]

        # conservation: same run, no second start, no cleanup, artifacts intact.
        assert _identity(staged) == identity_before
        assert len(runner.adapter.started) == starts_before
        assert len(runner.adapter.messages) > messages_before
        assert staged.run_root.is_dir()
        assert _evidence(staged, "issue-report")[0]["issue_id"] == issue_id
    finally:
        dependency.stop()
        staged.cleanup()


# --- sequence 2: write followed by no response stays rejected -----------------


def test_socket_write_without_response_keeps_the_unknown_intent_rejected(tmp_path):
    dependency = _SilentSocketDependency(tmp_path / "write-dependency.sock")
    forwarder = _UnixNoResponseForwarder(dependency)
    staged = _UnifiedRunner(tmp_path, forwarder=forwarder)
    runner = staged.runner
    runner.adapter = _LiveIssueAdapter()
    sink = _ForegroundSink()
    try:
        staged.prepare()
        _wire_transport(runner)
        _open_platform_gate_unified(staged)
        starts_before = len(runner.adapter.started)
        arguments = _unified_args(_batch_items(), PLAN_REF)

        with _protocol_capability(staged) as endpoint:
            # 1) the write is dispatched and the endpoint never answers.
            failed = _call(endpoint, arguments)
            structured = failed["result"]["structuredContent"]
            assert structured["ok"] is False, structured
            assert structured["error"]["reason_code"] == "staged_batch_forward_unknown"
            assert _intent(staged)["status"] == "unknown"
            assert _receipt_names(staged) == []
            assert runner._staged_gate_killed is True
            assert _gate_state(staged.run_root)["reason_code"] == "staged_unreconciled_batch"
            assert any(
                record.get("event") == "kill-switch" for record in _evidence(staged, "staged-decisions")
            )
            assert len(dependency.request_bodies) == 1
            dispatched_request = dependency.request_bodies[0]

            # 2) the issue is still reportable and pausable over the real transport.
            report = _report_issue(
                runner,
                mutation_state="confirmed_no_write",
                error="本地写依赖已接收写请求但无响应",
            )
            issue_id = report["issue_id"]
            _pump(runner, sink)
            assert _ledger(runner).state == "reported"
            _issue_control(runner, "pause", issue_id, report["control_epoch"])
            _pump(runner, sink)
            assert _ledger(runner).state == "waiting_repair"
            runner.adapter.finish_turn(REPORTER_ID)
            intent_before = (_paths(staged)["intents_dir"] / "intent-1.json").read_bytes()

            # 3) the user's bound short repair cannot unlock a durable unknown.
            short = _admit_line(
                runner,
                sink,
                _short_resolution_line(runner.run.run_id, issue_id, report["control_epoch"]),
            )
            assert short is not None
            assert short["type"] == "outer-input-rejected"
            assert short["code"] == "unknown_mutation_requires_reconciliation"
            assert _ledger(runner).state == "waiting_repair"

            # 4) the legacy five-field reconciliation string is equally rejected.
            legacy = _admit_line(runner, sink, _legacy_resolution_line(issue_id, report["control_epoch"]))
            assert legacy is not None and legacy["code"] == "unknown_mutation_requires_reconciliation"
            assert _ledger(runner).state == "waiting_repair"

            # 5) no second mutation: the same submission is refused unforwarded.
            #    The closed shared gate intervenes at the entry; the durable
            #    unknown-intent reason lives on the gate state and the latch.
            blocked = _call(endpoint, arguments)
            blocked_structured = blocked["result"]["structuredContent"]
            assert blocked_structured["ok"] is False, blocked_structured
            assert (
                blocked_structured["error"]["reason_code"] == "staged_gate_closed"
            ), blocked_structured
            assert len(dependency.request_bodies) == 1
            assert dependency.request_bodies[0] == dispatched_request
            assert (_paths(staged)["intents_dir"] / "intent-1.json").read_bytes() == intent_before
            assert _receipt_names(staged) == []
            assert _intent(staged)["status"] == "unknown"
            assert _gate_state(staged.run_root)["reason_code"] == "staged_unreconciled_batch"

        # the issue stays pending and the run keeps every artifact it had.
        assert _ledger(runner).state == "waiting_repair"
        assert _ledger(runner).active_issue.issue_id == issue_id
        assert _ledger(runner).active_issue.thread_id == REPORTER_THREAD
        assert len(runner.adapter.started) == starts_before
        assert staged.run_root.is_dir()
    finally:
        dependency.stop()
        staged.cleanup()
