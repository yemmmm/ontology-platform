"""2026-09-14 provider-recovery increment: externally fixable provider errors wait.

Two layers, no charged model calls:

* Runtime layer (real ``CodexRuntimeAdapter`` + a fake App Server over real
  pipes): exhausted SDK retries on rate-limit/quota/balance/outage variants
  park the role in an observable provider wait on its live thread instead of
  the fatal latch; an explicit bound recovery starts a new turn on the same
  thread; malformed identities and non-external variants stay fatal.
* Runner layer (real ``TeamTransportBroker`` + production foreground
  admission): the wait is routed to a healthy Coordinator through the native
  issue contract, resumed after a bound outer resolution, host-recoverable
  when the Coordinator itself is blocked, exempt from the run fallback clock,
  and deferred against cleanup until an explicit stop.
"""

from __future__ import annotations

import json
import os
import threading
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.runtimes.base import RuntimeDispatchReceipt
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent
from modeling_team.tests.test_r30006_live_repair_socket import (
    _ForegroundSink,
    _admit_line,
    _pump,
    _wire_transport,
)
from modeling_team.tests.test_r30009_runner_wiring import _UnifiedRunner
from modeling_team.tests.test_runner import CapturingAdapter

COORDINATOR_ID = "coordinator"
RECOVERY_TEXT = "额度已充值恢复，请继续原任务。"


def _agent(tmp_path: Path, *, agent_id: str = "protocol", active: str = "turn-1") -> _Agent:
    return _Agent(
        agent_id,
        SimpleNamespace(role=agent_id),
        tmp_path / "home",
        tmp_path / "work",
        tmp_path / "skills",
        thread_id=f"thread-{agent_id}",
        active_turn_id=active,
        last_started_turn_id=active,
        state="running",
    )


def _provider_error(
    *, will_retry: bool = False, variant: object, turn_id: str = "turn-1"
) -> dict[str, object]:
    info = variant if isinstance(variant, str) else {variant: {"httpStatusCode": 503}}
    return {
        "method": "error",
        "params": {
            "threadId": "thread-protocol",
            "turnId": turn_id,
            "willRetry": will_retry,
            "error": {
                "message": "provider text must never be retained",
                "codexErrorInfo": info,
            },
        },
    }


# --- Runtime layer: classification into observable waits ------------------------


@pytest.mark.parametrize(
    "variant",
    [
        "rateLimitExceeded",
        "usageLimitExceeded",
        "serverOverloaded",
        "internalServerError",
        "unauthorized",
        "responseStreamConnectionFailed",
    ],
)
def test_recoverable_exhausted_provider_error_waits_instead_of_latching(
    tmp_path: Path, variant: str
) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent

    adapter._notification(agent, _provider_error(will_retry=False, variant=variant))

    assert agent.runtime_failure is None
    assert agent.state == "waiting_provider"
    assert agent.active_turn_id is None
    wait = adapter.provider_wait_status(agent.agent_id)
    assert wait is not None and wait["variant"] == variant
    waits = adapter.consume_provider_waits()
    assert len(waits) == 1 and waits[0][0] == agent.agent_id
    assert adapter.consume_provider_waits() == []
    evidence = (tmp_path / "evidence" / "provider-wait.jsonl").read_text()
    assert "provider text" not in evidence


def test_repeated_exhausted_notifications_deduplicate_one_wait(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent

    adapter._notification(agent, _provider_error(variant="rateLimitExceeded"))
    adapter._notification(agent, _provider_error(variant="rateLimitExceeded"))
    adapter._notification(agent, _provider_error(variant="rateLimitExceeded"))

    waits = adapter.consume_provider_waits()
    assert len(waits) == 1
    wait = adapter.provider_wait_status(agent.agent_id)
    assert wait["notifications"] == 3
    assert wait["epoch"] == 1 and wait["wait_id"] == f"{agent.agent_id}:1"


def test_waiting_state_does_not_arm_the_inactivity_watchdog(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent

    adapter._notification(agent, _provider_error(variant="rateLimitExceeded"))
    agent.last_output_monotonic = time.monotonic() - 10_000.0

    # The watchdog arms only on state=="running" and never while a provider
    # wait is pending; assert the exact guard the watch loop evaluates.
    with agent.state_lock:
        armed = (
            agent.runtime_failure is None
            and agent.provider_wait is None
            and agent.state == "running"
            and agent.last_output_monotonic > 0.0
        )
    assert armed is False
    assert agent.inactivity_failure is None


def test_send_message_is_rejected_while_waiting(tmp_path: Path) -> None:
    from modeling_team.runtimes.codex import CodexRuntimeError, RuntimeDelivery

    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    adapter._notification(agent, _provider_error(variant="rateLimitExceeded"))

    with pytest.raises(CodexRuntimeError, match="provider wait is active"):
        adapter.send_message(
            agent.agent_id,
            RuntimeDelivery(
                sender_id="user/outer", recipient_id=agent.agent_id, kind="outer-user", text="x"
            ),
        )


def test_identity_mismatch_stays_fatal_and_supersedes_the_wait(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    adapter._notification(agent, _provider_error(variant="rateLimitExceeded"))
    wait = adapter.provider_wait_status(agent.agent_id)

    adapter._notification(
        agent, _provider_error(variant="rateLimitExceeded", turn_id="turn-other")
    )

    assert agent.runtime_failure is not None
    assert agent.state == "failed"
    assert adapter.provider_wait_status(agent.agent_id) is None


# --- Runtime layer: fake App Server recovery over real pipes ---------------------


class _FakeAppServer:
    """A minimal JSON-RPC App Server over two real pipes.

    It answers ``turn/start`` with fresh turn identities on the same thread and
    can be switched between healthy and provider-refusing modes; no model is
    contacted.
    """

    def __init__(self) -> None:
        request_read, request_write = os.pipe()
        response_read, response_write = os.pipe()
        self.request = os.fdopen(request_write, "w", buffering=1)
        self._response_write = response_write
        self.stdout = os.fdopen(response_read, "rb", buffering=0)
        self.terminated = False
        self.refuse_turns = False
        # Provider-exhaustion modes: emit an exhausted error notification for
        # ``exhaust_turn_id`` before refusing the request, or after a
        # successful turn start (``exhaust_after_start``).
        self.exhaust_turn_id: str | None = None
        self.exhaust_after_start = False
        self.turns = 0
        self.lines: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, args=(request_read,), daemon=True)
        self._thread.start()

    def _send(self, value: dict) -> None:
        with self._lock:
            os.write(self._response_write, (json.dumps(value) + "\n").encode())

    def _error_notification(self, turn_id: str) -> dict:
        return {
            "method": "error",
            "params": {
                "threadId": "thread-protocol",
                "turnId": turn_id,
                "willRetry": False,
                "error": {
                    "message": "provider text must never be retained",
                    "codexErrorInfo": "rateLimitExceeded",
                },
            },
        }

    def _serve(self, request_read: int) -> None:
        with os.fdopen(request_read, "r", buffering=1) as reader:
            for line in reader:
                if self._stop.is_set():
                    return
                self.lines.append(line.strip())
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    continue
                method = request.get("method")
                if method != "turn/start":
                    continue
                if self.refuse_turns:
                    if self.exhaust_turn_id is not None:
                        self._send(self._error_notification(self.exhaust_turn_id))
                    self._send(
                        {
                            "id": request.get("id"),
                            "error": {"code": -32001, "message": "simulated provider refusal"},
                        }
                    )
                    continue
                with self._lock:
                    self.turns += 1
                    turn_id = f"turn-fake-{self.turns}"
                self._send({"id": request.get("id"), "result": {"turn": {"id": turn_id}}})
                if self.exhaust_after_start:
                    self._send(self._error_notification(turn_id))

    def terminate(self) -> None:
        self.terminated = True

    def close(self) -> None:
        self._stop.set()
        self.request.close()
        self.stdout.close()
        os.close(self._response_write)


def _waiting_agent_with_server(tmp_path: Path, adapter: CodexRuntimeAdapter) -> tuple[_Agent, _FakeAppServer]:
    server = _FakeAppServer()
    agent = _agent(tmp_path)
    agent.process = SimpleNamespace(stdin=server.request, stdout=server.stdout, pid=None, terminate=server.terminate)
    adapter.agents[agent.agent_id] = agent
    adapter._notification(agent, _provider_error(variant="rateLimitExceeded"))
    return agent, server


def test_bound_recovery_starts_a_new_turn_on_the_same_thread(tmp_path: Path) -> None:
    from modeling_team.runtimes.codex import RuntimeDelivery

    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent, server = _waiting_agent_with_server(tmp_path, adapter)
    try:
        receipt = adapter.recover_provider_wait(
            agent.agent_id, RECOVERY_TEXT, sender_id="user/outer"
        )

        assert receipt.mode == "start"
        assert receipt.turn_id and receipt.turn_id != "turn-1"
        assert agent.thread_id == "thread-protocol"
        assert agent.provider_wait is None
        assert agent.state == "running"
        assert server.terminated is False
        evidence = (tmp_path / "evidence" / "provider-wait-recovered.jsonl").read_text()
        assert "额度" not in evidence  # message content retained only as digest
        last_request = json.loads(server.lines[-1])
        assert last_request["method"] == "turn/start"
        assert last_request["params"]["threadId"] == "thread-protocol"
    finally:
        server.close()


def test_stale_wait_binding_is_rejected_and_failure_returns_to_waiting(tmp_path: Path) -> None:
    from modeling_team.runtimes.codex import CodexRuntimeError

    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent, server = _waiting_agent_with_server(tmp_path, adapter)
    try:
        with pytest.raises(CodexRuntimeError, match="stale"):
            adapter.recover_provider_wait(agent.agent_id, RECOVERY_TEXT, wait_id="protocol:99")

        server.refuse_turns = True
        with pytest.raises(CodexRuntimeError):
            adapter.recover_provider_wait(agent.agent_id, RECOVERY_TEXT)

        wait = adapter.provider_wait_status(agent.agent_id)
        assert wait is not None and wait["recovery_failures"] == 1
        assert agent.state == "waiting_provider"
        assert agent.runtime_failure is None
        assert server.terminated is False
        recovered = (tmp_path / "evidence" / "provider-wait-recovery-failed.jsonl").read_text()
        assert '"recovery_failures": 1' in recovered
    finally:
        server.close()


# --- Runner layer: coordinator-judged and host-takeover recovery -----------------


class _ProviderWaitAdapter(CapturingAdapter):
    """Capturing adapter extended with the provider-wait control surface."""

    def __init__(self) -> None:
        super().__init__()
        self.agents = {
            agent_id: SimpleNamespace(
                process=None,
                thread_id=f"thread-{agent_id}",
                active_turn_id=None,
                runtime_failure=None,
                state="idle",
                provider_wait=None,
                package=SimpleNamespace(role=agent_id),
            )
            for agent_id in ("coordinator", "modeling", "protocol")
        }
        self._wait_queue: list[tuple[str, dict]] = []
        self._failure_queue: list[tuple[str, dict]] = []
        self.recoveries: list[tuple[str, str, str | None]] = []
        self.fail_next_recovery = False
        self.reenter_next_recovery = False
        self.stopped = False
        self._turns = 0

    def inject_wait(self, agent_id: str, variant: str = "rateLimitExceeded") -> dict:
        agent = self.agents[agent_id]
        record = {
            "agent_id": agent_id,
            "role": agent_id,
            "wait_id": f"{agent_id}:1",
            "epoch": 1,
            "variant": variant,
            "http_status": None,
            "thread_digest": "digest",
            "state": "waiting",
            "notifications": 1,
            "recovery_failures": 0,
        }
        agent.provider_wait = record
        agent.active_turn_id = None
        agent.state = "waiting_provider"
        self._wait_queue.append((agent_id, dict(record)))
        return record

    def latch(self, agent_id: str) -> None:
        agent = self.agents[agent_id]
        agent.runtime_failure = {"reason": "provider-error-terminal", "role": agent_id}
        agent.state = "failed"
        self._failure_queue.append((agent_id, dict(agent.runtime_failure)))

    def consume_runtime_failures(self):
        queue, self._failure_queue = self._failure_queue[:], []
        return queue

    def consume_provider_waits(self):
        queue, self._wait_queue = self._wait_queue[:], []
        return queue

    def provider_wait_status(self, agent_id):
        wait = self.agents[agent_id].provider_wait
        return dict(wait) if wait is not None else None

    def send_message(self, agent_id, delivery):
        super().send_message(agent_id, delivery)
        if self.agents[agent_id].provider_wait is not None:
            raise RuntimeError("provider wait is active in fake adapter")
        self._turns += 1
        self.agents[agent_id].active_turn_id = f"turn-{self._turns}"
        return RuntimeDispatchReceipt("start", f"turn-{self._turns}")

    def recover_provider_wait(self, agent_id, message, *, wait_id=None, sender_id="user/outer"):
        if self.fail_next_recovery:
            self.fail_next_recovery = False
            self.recoveries.append((agent_id, "failed", wait_id))
            current = self.agents[agent_id].provider_wait
            if current is not None:
                current["recovery_failures"] = int(current.get("recovery_failures", 0)) + 1
            raise RuntimeError("simulated recovery refusal")
        wait = self.agents[agent_id].provider_wait
        if self.reenter_next_recovery:
            # Mirror the runtime's synchronous reentry: the turn dispatch
            # succeeded but the provider reported exhaustion again for it.
            self.reenter_next_recovery = False
            self.recoveries.append((agent_id, "reentered", wait_id))
            wait = dict(wait)
            wait["epoch"] = wait["epoch"] + 1
            wait["wait_id"] = f"{agent_id}:{wait['epoch']}"
            self.agents[agent_id].provider_wait = wait
            self.agents[agent_id].state = "waiting_provider"
            raise RuntimeError(
                "provider is still exhausted after the recovery dispatch; the role "
                "re-entered its provider wait"
            )
        if wait is None:
            raise RuntimeError("agent is not waiting for provider recovery")
        if wait_id is not None and wait_id != wait["wait_id"]:
            raise RuntimeError("provider recovery wait binding is stale")
        self.agents[agent_id].provider_wait = None
        self._turns += 1
        turn = f"turn-{self._turns}"
        self.agents[agent_id].active_turn_id = turn
        self.agents[agent_id].state = "running"
        self.recoveries.append((agent_id, turn, wait_id))
        return RuntimeDispatchReceipt("start", turn)

    def stop(self):
        self.stopped = True


def _runner_with_adapter(tmp_path: Path) -> tuple[_UnifiedRunner, _ProviderWaitAdapter, _ForegroundSink]:
    staged = _UnifiedRunner(tmp_path)
    runner = staged.runner
    adapter = _ProviderWaitAdapter()
    runner.adapter = adapter
    sink = _ForegroundSink()
    staged.prepare()
    _wire_transport(runner)
    return staged, adapter, sink


def test_coordinator_judged_recovery_resumes_the_same_thread(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("protocol")
        output = _pump(runner, sink)
        assert any(entry["type"] == "provider-wait" for entry in output)
        ledger = runner.transport.issue_ledger
        assert ledger.state == "reported"
        issue = ledger.active_issue
        assert issue.category == "runtime_recovery"
        assert issue.reporter_id == "protocol"
        assert issue.thread_id == "thread-protocol"
        assert issue.mutation_state == "confirmed_no_write"
        # The Coordinator received the native issue delivery.
        assert any(
            agent_id == "coordinator" and delivery.kind == "issue"
            for agent_id, delivery in adapter.messages
        )

        # Coordinator pause: no reporter turn is possible or needed.
        pause = _control(runner, "pause", issue.issue_id, issue.control_epoch)
        assert pause["action"] == "pause"
        _pump(runner, sink)
        assert ledger.state == "waiting_owner"
        assert not any(
            agent_id == "protocol" for agent_id, _delivery in adapter.messages
        ) or all(
            delivery.kind == "issue"
            for agent_id, delivery in adapter.messages
            if agent_id == "protocol"
        )

        # The user reports the quota reset through the production outer path.
        accepted = _admit_line(
            runner,
            sink,
            json.dumps(
                {
                    "action": "issue_resolution",
                    "run_id": runner.run.run_id,
                    "issue_id": issue.issue_id,
                    "reporter_id": "protocol",
                    "control_epoch": issue.control_epoch,
                    "resolution_type": "repair_completed",
                    "repair_component": "external_service",
                    "resolution_text": RECOVERY_TEXT,
                },
                ensure_ascii=False,
            ),
        )
        assert accepted is None
        assert ledger.state == "resolution_ready"

        resume = _control(
            runner,
            "resume",
            issue.issue_id,
            issue.control_epoch,
            resolution_type="repair_completed",
            repair_component="external_service",
            resolution_text=RECOVERY_TEXT,
        )
        assert resume["action"] == "resume"
        _pump(runner, sink)
        assert ledger.state == "resolved"
        assert adapter.recoveries and adapter.recoveries[0][0] == "protocol"
        assert adapter.agents["protocol"].thread_id == "thread-protocol"
        assert adapter.provider_wait_status("protocol") is None
        _pump(runner, sink)  # next tick reconciles the runner-side registry
        assert runner._provider_wait_registry() == {}
    finally:
        staged.cleanup()


def test_host_takeover_recovers_without_a_available_coordinator(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.latch("coordinator")
        adapter.inject_wait("protocol", variant="usageLimitExceeded")
        output = _pump(runner, sink)
        # The fatally failed Coordinator defers whole-run cleanup instead of
        # erasing the waiting role; no cooperative issue can be reported
        # through a blocked Coordinator, so the wait stays host-owned.
        takeover = next(entry for entry in output if entry["type"] == "coordinator-unavailable")
        assert takeover["provider_waits"] == ["protocol"]
        ledger = runner.transport.issue_ledger
        assert ledger.active_issue is None
        assert adapter.stopped is False

        output = runner.receive_outer(
            {"action": "recover_provider", "role": "protocol", "text": RECOVERY_TEXT}
        )
        recovery = next(entry for entry in output if entry["type"] == "provider-recovery")
        assert recovery["dispatch_mode"] == "start"
        assert adapter.recoveries and adapter.recoveries[0][0] == "protocol"
        assert adapter.provider_wait_status("protocol") is None
        evidence = (staged.run_root / "evidence" / "provider-wait.jsonl").read_text()
        assert '"event": "host-recovery"' in evidence

        # Recovery requires a pending wait; a replay is a typed rejection.
        with pytest.raises(Exception, match="no pending provider wait"):
            runner.receive_outer(
                {"action": "recover_provider", "role": "protocol", "text": RECOVERY_TEXT}
            )
    finally:
        staged.cleanup()


def test_coordinator_itself_waiting_is_host_recoverable(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("coordinator", variant="serverOverloaded")
        _pump(runner, sink)
        assert runner.transport.issue_ledger.active_issue is None
        output = runner.receive_outer(
            {"action": "recover_provider", "agent_id": "coordinator", "text": RECOVERY_TEXT}
        )
        assert any(entry["type"] == "provider-recovery" for entry in output)
        assert adapter.provider_wait_status("coordinator") is None
    finally:
        staged.cleanup()


def test_failed_recovery_returns_to_waiting_with_backoff(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("protocol")
        _pump(runner, sink)
        ledger = runner.transport.issue_ledger
        issue = ledger.active_issue
        _control(runner, "pause", issue.issue_id, issue.control_epoch)
        _pump(runner, sink)
        _admit_line(runner, sink, _resolution_line(runner.run.run_id, issue))
        adapter.fail_next_recovery = True
        resume = _control(
            runner,
            "resume",
            issue.issue_id,
            issue.control_epoch,
            resolution_type="repair_completed",
            repair_component="external_service",
            resolution_text=RECOVERY_TEXT,
        )
        output = _pump(runner, sink)
        assert any(
            entry.get("reason_code") == "provider_recovery_retry" for entry in output
        )
        # The wait is restored and observable; nothing was rebound.
        assert adapter.provider_wait_status("protocol") is not None
        assert ledger.state != "rebind_required"
        assert adapter.recoveries == [("protocol", "failed", "protocol:1")]

        # An immediate retry is spaced by the backoff window, not polled.  The
        # failed control was requeued, so the next drain defers it.
        deferred = _pump(runner, sink)
        assert any(
            entry.get("reason_code") == "provider_recovery_backoff" for entry in deferred
        )
        assert len(adapter.recoveries) == 1

        # After the window, the same bound recovery succeeds.
        runner._provider_recovery_retry_not_before = 0.0
        _pump(runner, sink)
        assert ledger.state == "resolved"
        assert adapter.recoveries[-1][0] == "protocol"
        assert adapter.provider_wait_status("protocol") is None
    finally:
        staged.cleanup()


def test_multiple_waiting_roles_keep_every_problem(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("protocol")
        adapter.inject_wait("modeling")
        _pump(runner, sink)
        ledger = runner.transport.issue_ledger
        # One active issue at a time; both waits stay in the registry.
        assert set(runner._provider_wait_registry()) == {"protocol", "modeling"}
        assert ledger.active_issue is not None
        first_reporter = ledger.active_issue.reporter_id
        assert first_reporter in {"modeling", "protocol"}

        # Recover the reported role via the host path; the other wait must not
        # be lost and becomes the next reported issue.
        output = runner.receive_outer(
            {"action": "recover_provider", "role": first_reporter, "text": RECOVERY_TEXT}
        )
        assert any(entry["type"] == "provider-recovery" for entry in output)
        remaining = set(runner._provider_wait_registry())
        assert remaining == {"protocol", "modeling"} - {first_reporter}
        _pump(runner, sink)
        # The recovered role's issue settled; the remaining wait becomes the
        # next reported problem instead of being lost.
        ledger = runner.transport.issue_ledger
        assert ledger.active_issue is not None
        assert ledger.active_issue.reporter_id in remaining
        assert runner._provider_wait_registry().keys() == remaining
    finally:
        staged.cleanup()


def test_provider_wait_time_is_excluded_from_the_run_fallback_clock(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.latch("coordinator")  # keep the issue channel out of the picture
        adapter.inject_wait("protocol")
        clock = {"now": 1.0}
        runner.monotonic_clock = lambda: clock["now"]
        runner._run_fallback_timeout_seconds = 60.0
        runner._run_fallback_started = 0.0
        runner._issue_pending_elapsed = 0.0
        runner._issue_pending_started = None
        runner._cq_wait_windows = SimpleNamespace(
            elapsed=lambda now: 0.0, evidence=lambda now: [], has_open_window=False
        )

        # The first pump settles into the host-takeover deferral; the wait is
        # observed and its exclusion clock starts on the next tick.
        _pump(runner, sink)
        _pump(runner, sink)
        assert runner._provider_wait_started is not None
        assert "protocol" in runner._provider_wait_registry()

        # 1060 waiting seconds later the run fallback must not fire: waiting
        # time is excluded, so active time is still ~1 second.
        clock["now"] = 1061.0
        _pump(runner, sink)

        # Without the exclusion the same wall-clock position is far past the
        # 60-second timeout, proving the exclusion is what held it back.
        runner._provider_wait_elapsed = 0.0
        runner._provider_wait_started = None
        with pytest.raises(Exception, match="run fallback timeout"):
            runner._check_run_fallback_timeout()
    finally:
        staged.cleanup()


def test_cleanup_defers_while_waiting_and_explicit_stop_proceeds(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.latch("coordinator")
        adapter.inject_wait("protocol")
        _pump(runner, sink)

        paused = runner.cleanup()
        assert paused["status"] == "paused" and paused["cleanup_deferred"] is True
        assert adapter.stopped is False
        assert staged.run_root.is_dir()

        output = runner.receive_outer({"action": "stop"})
        assert output[-1]["type"] == "stopped"
        assert adapter.stopped is True
    finally:
        staged.cleanup()


def test_unknown_write_gate_stays_closed_during_provider_recovery(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        # An unreconciled staged write forces the unknown mutation state.
        runner._staged_resolution_blocker = lambda: "staged_unreconciled_batch"  # type: ignore[method-assign]
        adapter.inject_wait("protocol")
        _pump(runner, sink)
        ledger = runner.transport.issue_ledger
        assert ledger.active_issue.mutation_state == "unknown"

        issue = ledger.active_issue
        _control(runner, "pause", issue.issue_id, issue.control_epoch)
        _pump(runner, sink)
        rejected = _admit_line(runner, sink, _resolution_line(runner.run.run_id, issue))
        assert rejected is not None
        assert rejected["code"] == "unknown_mutation_requires_reconciliation"
        assert ledger.state == "waiting_owner"

        # Host direct recovery can start the next turn, but it never unlocks
        # the write gate or silently settles the gated issue.
        output = runner.receive_outer(
            {"action": "recover_provider", "role": "protocol", "text": RECOVERY_TEXT}
        )
        assert any(entry["type"] == "provider-recovery" for entry in output)
        assert runner._staged_resolution_blocker() == "staged_unreconciled_batch"
        evidence = (staged.run_root / "evidence" / "provider-wait.jsonl").read_text()
        assert '"event": "issue-settlement-skipped"' in evidence
    finally:
        staged.cleanup()


# --- Runtime layer: terminal/race boundaries around the wait ---------------------


def _turn_completed(turn_id: str) -> dict[str, object]:
    return {"method": "turn/completed", "params": {"turn": {"id": turn_id}}}


def test_late_abandoned_terminal_while_waiting_is_consumed_safely(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    adapter._notification(agent, _provider_error(variant="rateLimitExceeded"))

    # The abandoned turn's own late terminal and an unattributable one are both
    # ignored while parked: the wait owns the state, nothing latches.
    adapter._notification(agent, _turn_completed("turn-1"))
    adapter._notification(agent, _turn_completed("turn-other"))
    adapter._notification(agent, {"method": "turn/completed", "params": {}})
    assert agent.runtime_failure is None
    assert agent.state == "waiting_provider"
    assert agent.provider_wait is not None


def test_late_abandoned_terminal_after_recovery_does_not_kill_the_thread(
    tmp_path: Path,
) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent, server = _waiting_agent_with_server(tmp_path, adapter)
    try:
        receipt = adapter.recover_provider_wait(agent.agent_id, RECOVERY_TEXT)
        new_turn = receipt.turn_id
        assert agent.state == "running" and agent.active_turn_id == new_turn

        # The SDK's late terminal for the turn abandoned into the wait arrives
        # after the recovered turn already started: consume it, never latch.
        adapter._notification(agent, _turn_completed("turn-1"))
        assert agent.runtime_failure is None
        assert agent.active_turn_id == new_turn
        assert "turn-1" not in agent.abandoned_turn_ids

        # A genuinely wrong identity while the recovered turn is active stays
        # fatal (identity damage is not recoverable).
        adapter._notification(agent, _turn_completed("turn-zz"))
        assert agent.runtime_failure is not None
    finally:
        server.close()


def test_recovered_turn_terminal_completes_normally(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent, server = _waiting_agent_with_server(tmp_path, adapter)
    try:
        receipt = adapter.recover_provider_wait(agent.agent_id, RECOVERY_TEXT)
        adapter._notification(agent, _turn_completed("turn-1"))
        adapter._notification(agent, _turn_completed(receipt.turn_id))
        assert agent.state == "idle"
        assert agent.runtime_failure is None
    finally:
        server.close()


def test_inactivity_timeout_rechecks_the_wait_at_the_latch_decision(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    adapter._notification(agent, _provider_error(variant="rateLimitExceeded"))
    agent.last_output_monotonic = time.monotonic() - 10_000.0

    # Direct call (the watchdog's unlocked precheck can race a concurrent wait
    # entry): the lock-level decision must still refuse to latch.
    adapter._on_inactivity_timeout(agent, 60.0)
    assert agent.runtime_failure is None
    assert agent.inactivity_failure is None
    assert agent.state == "waiting_provider"


def test_failed_recovery_preserves_a_freshly_observed_epoch(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent, server = _waiting_agent_with_server(tmp_path, adapter)
    try:
        # The stream re-enters waiting with a NEW epoch (notification for the
        # abandoned turn) while the recovery dispatch itself fails.
        server.refuse_turns = True
        server.exhaust_turn_id = "turn-1"
        with pytest.raises(Exception):
            adapter.recover_provider_wait(agent.agent_id, RECOVERY_TEXT)

        wait = adapter.provider_wait_status(agent.agent_id)
        assert wait is not None
        assert wait["epoch"] == 2 and wait["wait_id"] == f"{agent.agent_id}:2"
        assert wait["recovery_failures"] == 1
        assert agent.state == "waiting_provider"
        assert agent.runtime_failure is None
        recovered = (tmp_path / "evidence" / "provider-wait-recovery-failed.jsonl").read_text()
        assert '"wait_restored": false' in recovered
    finally:
        server.close()


def test_synchronous_reentry_raises_instead_of_claiming_recovery(tmp_path: Path) -> None:
    from modeling_team.runtimes.codex import CodexRuntimeError

    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent, server = _waiting_agent_with_server(tmp_path, adapter)
    try:
        # The server accepts the recovery turn and immediately reports the
        # provider exhausted again for that new turn.
        server.exhaust_after_start = True
        with pytest.raises(CodexRuntimeError, match="re-entered its provider wait"):
            adapter.recover_provider_wait(agent.agent_id, RECOVERY_TEXT)

        wait = adapter.provider_wait_status(agent.agent_id)
        assert wait is not None and wait["epoch"] == 2
        assert agent.state == "waiting_provider"
        assert agent.runtime_failure is None
        reentered = (tmp_path / "evidence" / "provider-wait-recovery-reentered.jsonl").read_text()
        assert '"dispatch_mode": "start"' in reentered
        assert not (tmp_path / "evidence" / "provider-wait-recovered.jsonl").exists()
    finally:
        server.close()


def test_closed_process_is_visibly_unavailable_not_eternally_recoverable(
    tmp_path: Path,
) -> None:
    from modeling_team.runtimes.codex import CodexRuntimeError

    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent, server = _waiting_agent_with_server(tmp_path, adapter)
    try:
        agent.process = None
        with pytest.raises(CodexRuntimeError, match="app-server is unavailable"):
            adapter.recover_provider_wait(agent.agent_id, RECOVERY_TEXT)
        wait = adapter.provider_wait_status(agent.agent_id)
        assert wait is not None and wait["state"] == "unavailable"
        assert agent.runtime_failure is None
    finally:
        server.close()


def test_startup_exhaustion_is_an_observable_wait_not_an_abort(tmp_path: Path) -> None:
    from modeling_team.runtimes.codex import CodexRuntimeError, RuntimeDelivery

    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    server = _FakeAppServer()
    server.exhaust_after_start = True
    agent = _agent(tmp_path)
    agent.process = SimpleNamespace(stdin=server.request, stdout=server.stdout, pid=None, terminate=server.terminate)
    agent.active_turn_id = None
    adapter.agents[agent.agent_id] = agent
    try:
        receipt = adapter.send_message(
            agent.agent_id,
            RuntimeDelivery(sender_id="coordinator", recipient_id=agent.agent_id, kind="team", text="initial task"),
        )
        assert receipt.mode == "start"
        adapter.receive_messages()
        wait = adapter.provider_wait_status(agent.agent_id)
        assert wait is not None and wait["variant"] == "rateLimitExceeded"
        assert agent.runtime_failure is None
        with pytest.raises(CodexRuntimeError, match="provider wait is active"):
            adapter.send_message(
                agent.agent_id,
                RuntimeDelivery(sender_id="coordinator", recipient_id=agent.agent_id, kind="team", text="again"),
            )
    finally:
        server.close()


@pytest.mark.parametrize(
    "info,expected_status",
    [
        ("usageLimitExceeded", None),
        ({"responseStreamConnectionFailed": {"httpStatusCode": 402}}, 402),
    ],
)
def test_balance_exhaustion_encodings_wait_with_sanitized_status(
    tmp_path: Path, info: object, expected_status: int | None
) -> None:
    """Insufficient balance is classified from its actual app-server encodings."""

    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    adapter.agents[agent.agent_id] = agent

    variant = info if isinstance(info, str) else next(iter(info))
    if isinstance(info, dict):
        notification = _provider_error(variant="rateLimitExceeded")
        notification["params"]["error"]["codexErrorInfo"] = info
    else:
        notification = _provider_error(variant=info)
    adapter._notification(agent, notification)
    wait = adapter.provider_wait_status(agent.agent_id)
    assert wait is not None
    assert wait["variant"] == variant
    assert wait["http_status"] == expected_status
    assert agent.state == "waiting_provider"
    evidence = (tmp_path / "evidence" / "provider-wait.jsonl").read_text()
    assert "provider text" not in evidence
    if expected_status is not None:
        assert f'"http_status": {expected_status}' in evidence


# --- Runner layer: status, takeover, deferral of necessary messages --------------


def test_status_action_exposes_pending_waits_with_ownership(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("protocol")
        adapter.inject_wait("coordinator", variant="usageLimitExceeded")
        output = runner.receive_outer({"action": "status"})
        record = next(entry for entry in output if entry["type"] == "provider-wait-status")
        waits = {wait["agent_id"]: wait for wait in record["waits"]}
        assert set(waits) == {"protocol", "coordinator"}
        for agent_id, wait in waits.items():
            assert wait["wait_id"] == f"{agent_id}:1" and wait["epoch"] == 1
            assert wait["recovery_route"] == "host"
            assert wait["action"] == "recover_provider"
        assert waits["protocol"]["variant"] == "rateLimitExceeded"
        assert waits["coordinator"]["variant"] == "usageLimitExceeded"
    finally:
        staged.cleanup()


def test_coordinator_takeover_keeps_recovered_roles_alive(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.latch("coordinator")
        adapter.inject_wait("protocol")
        output = _pump(runner, sink)
        takeover = next(entry for entry in output if entry["type"] == "coordinator-unavailable")
        assert takeover["host_action"] == "recover_provider"
        assert takeover["provider_waits"] == ["protocol"]
        assert "not a complete-team recovery" in takeover["note"]
        # The Coordinator stays dead; the run and the waiting role survive.
        assert adapter.agents["coordinator"].runtime_failure is not None
        assert adapter.stopped is False
        assert staged.run_root.is_dir()
        assert runner.transport.issue_ledger.active_issue is None

        output = runner.receive_outer(
            {"action": "recover_provider", "role": "protocol", "text": RECOVERY_TEXT}
        )
        assert any(entry["type"] == "provider-recovery" for entry in output)
        assert adapter.agents["protocol"].state == "running"

        # The deferred Coordinator failure must NOT auto-clean the just
        # recovered surviving role: several drains keep it alive on its new
        # turn with no terminal cleanup.
        for _ in range(3):
            tick = _pump(runner, sink)
            assert not any(entry["type"] == "runtime-failure" for entry in tick)
        assert adapter.stopped is False
        assert adapter.provider_wait_status("protocol") is None
        assert staged.run_root.is_dir()

        # Explicit stop ends the takeover and cleans, recording the retained
        # Coordinator failure.
        stopped = runner.receive_outer({"action": "stop"})
        assert stopped[-1]["type"] == "stopped"
        assert adapter.stopped is True
        evidence = (staged.run_root / "evidence" / "runtime-failure.jsonl").read_text()
        assert "coordinator-takeover-stopped" in evidence
        assert runner._deferred_runtime_failures is None
    finally:
        staged.cleanup()


def test_host_recovery_settles_issue_from_coordinator_pause_state(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("protocol")
        _pump(runner, sink)
        ledger = runner.transport.issue_ledger
        issue = ledger.active_issue
        # Native coordinator control path (transport tool surface).
        pause = _control(runner, "pause", issue.issue_id, issue.control_epoch)
        assert pause["action"] == "pause"
        _pump(runner, sink)
        assert ledger.state == "waiting_owner"

        # The Coordinator cannot advance the resume; host direct recovery must
        # settle the paused issue instead of leaving the run stuck.
        output = runner.receive_outer(
            {"action": "recover_provider", "role": "protocol", "text": RECOVERY_TEXT}
        )
        assert any(entry["type"] == "provider-recovery" for entry in output)
        assert ledger.state == "resolved"
        assert adapter.provider_wait_status("protocol") is None
    finally:
        staged.cleanup()


def test_issue_resolution_delivery_defers_when_coordinator_waits(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("protocol")
        _pump(runner, sink)
        ledger = runner.transport.issue_ledger
        issue = ledger.active_issue
        _control(runner, "pause", issue.issue_id, issue.control_epoch)
        _pump(runner, sink)
        # The Coordinator parks in its own provider wait after pausing.
        adapter.inject_wait("coordinator")

        rejected = _admit_line(runner, sink, _resolution_line(runner.run.run_id, issue))
        assert rejected is not None
        assert rejected["code"] == "coordinator_waiting_provider"
        # The resolution itself persisted; the run stays alive and actionable.
        assert ledger.state == "resolution_ready"
        assert adapter.stopped is False
        evidence = (staged.run_root / "evidence" / "issue-resolution.jsonl").read_text()
        assert "coordinator-delivery-deferred" in evidence
    finally:
        staged.cleanup()


# --- Foreground CLI/FIFO surface -------------------------------------------------


def test_foreground_event_loop_recovers_and_survives_invalid_recover_lines(
    tmp_path: Path,
) -> None:
    from io import StringIO

    from modeling_team.__main__ import _foreground_event_loop

    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("protocol")
        _pump(runner, sink)

        lines = StringIO(
            "\n".join(
                [
                    json.dumps(
                        {"action": "recover_provider", "role": "protocol", "text": RECOVERY_TEXT},
                        ensure_ascii=False,
                    ),
                    json.dumps({"action": "recover_provider", "role": "protocol", "text": ""}),
                    json.dumps({"action": "stop"}),
                ]
            )
            + "\n"
        )
        emitted: list[list[dict]] = []
        reads = {"count": 0}

        def select_fn(*_args):
            reads["count"] += 1
            return ([lines], [], []) if reads["count"] <= 3 else ([], [], [])

        _foreground_event_loop(runner, lines, lambda entries: emitted.extend(entries), select_fn=select_fn)

        flat = list(emitted)
        assert any(
            entry.get("type") == "provider-recovery" and entry.get("dispatch_mode") == "start"
            for entry in flat
        )
        # The invalid recovery line is a typed, nonfatal rejection and the run
        # is not cleaned up by it.
        assert any(entry.get("type") == "outer-input-rejected" for entry in flat)
        assert any(entry.get("type") == "stopped" for entry in flat)
        assert adapter.recoveries and adapter.recoveries[0][0] == "protocol"
        assert adapter.stopped is True
    finally:
        staged.cleanup()


# --- Final-review blockers: stale/failed recovery never tears down the foreground ---


def _run_foreground_lines(runner, lines_text: str, readable_polls: int) -> list[dict]:
    from io import StringIO

    from modeling_team.__main__ import _foreground_event_loop

    lines = StringIO(lines_text)
    emitted: list[dict] = []
    reads = {"count": 0}

    def select_fn(*_args):
        reads["count"] += 1
        return ([lines], [], []) if reads["count"] <= readable_polls else ([], [], [])

    _foreground_event_loop(
        runner, lines, lambda entries: emitted.extend(entries), select_fn=select_fn
    )
    return list(emitted)


def test_foreground_survives_stale_wait_id_then_recovers(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("protocol")
        _pump(runner, sink)
        flat = _run_foreground_lines(
            runner,
            "\n".join(
                [
                    json.dumps(
                        {
                            "action": "recover_provider",
                            "role": "protocol",
                            "wait_id": "protocol:99",
                            "text": RECOVERY_TEXT,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "action": "recover_provider",
                            "role": "protocol",
                            "wait_id": "protocol:1",
                            "text": RECOVERY_TEXT,
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps({"action": "stop"}),
                ]
            )
            + "\n",
            readable_polls=3,
        )
        rejections = [entry for entry in flat if entry.get("type") == "outer-input-rejected"]
        assert rejections and rejections[0]["code"] == "provider_recovery_failed"
        assert "stale" in rejections[0]["detail"]
        # The stale attempt did not consume the wait; the bound retry works.
        assert any(
            entry.get("type") == "provider-recovery" and entry.get("dispatch_mode") == "start"
            for entry in flat
        )
        assert adapter.recoveries and adapter.recoveries[0][0] == "protocol"
        assert any(entry.get("type") == "stopped" for entry in flat)
    finally:
        staged.cleanup()


def test_foreground_survives_dispatch_failure_then_status_and_stop(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.latch("coordinator")
        adapter.inject_wait("protocol")
        _pump(runner, sink)
        adapter.fail_next_recovery = True
        flat = _run_foreground_lines(
            runner,
            "\n".join(
                [
                    json.dumps(
                        {"action": "recover_provider", "role": "protocol", "text": RECOVERY_TEXT},
                        ensure_ascii=False,
                    ),
                    json.dumps({"action": "status"}),
                    json.dumps({"action": "stop"}),
                ]
            )
            + "\n",
            readable_polls=4,
        )
        rejections = [entry for entry in flat if entry.get("type") == "outer-input-rejected"]
        assert rejections and rejections[0]["code"] == "provider_recovery_failed"
        # The failed dispatch left the wait restored and observable via status;
        # the run survived until the explicit stop.
        status = next(entry for entry in flat if entry.get("type") == "provider-wait-status")
        assert status["waits"][0]["agent_id"] == "protocol"
        assert status["waits"][0]["recovery_failures"] == 1
        assert any(entry.get("type") == "stopped" for entry in flat)
        assert adapter.recoveries == [("protocol", "failed", None)]
    finally:
        staged.cleanup()


def test_outer_reentry_recovery_is_a_typed_rejection_without_settlement(
    tmp_path: Path,
) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        adapter.inject_wait("protocol")
        _pump(runner, sink)
        ledger = runner.transport.issue_ledger
        adapter.reenter_next_recovery = True
        with pytest.raises(Exception, match="provider recovery failed") as raised:
            runner.receive_outer(
                {"action": "recover_provider", "role": "protocol", "text": RECOVERY_TEXT}
            )
        assert getattr(raised.value, "code", None) == "provider_recovery_failed"
        # The wait is active again with a new epoch; no recovery was claimed,
        # no issue settled, no RUNNING state.
        wait = adapter.provider_wait_status("protocol")
        assert wait is not None and wait["epoch"] == 2
        assert ledger.state != "resolved"
        assert not any(
            entry["type"] == "provider-recovery"
            for entry in runner.receive_outer({"action": "status"})
        )
        assert (staged.run_root / "evidence" / "provider-wait.jsonl").exists()
    finally:
        staged.cleanup()


# --- helpers ---------------------------------------------------------------------


def _control(runner, action: str, issue_id: str, epoch: int, **extra) -> dict:
    from modeling_team.transport_mcp import mcp_response

    arguments = {
        "issue_id": issue_id,
        "reporter_id": "protocol",
        "action": action,
        "control_epoch": epoch,
        **extra,
    }
    response = mcp_response(
        {"method": "tools/call", "params": {"name": "issue_control", "arguments": arguments}},
        broker=runner.transport,
        agent_id=COORDINATOR_ID,
    )
    return json.loads(response["content"][0]["text"])


def _resolution_line(run_id: str, issue) -> str:
    return json.dumps(
        {
            "action": "issue_resolution",
            "run_id": run_id,
            "issue_id": issue.issue_id,
            "reporter_id": issue.reporter_id,
            "control_epoch": issue.control_epoch,
            "resolution_type": "repair_completed",
            "repair_component": "external_service",
            "resolution_text": RECOVERY_TEXT,
        },
        ensure_ascii=False,
    )
