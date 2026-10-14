"""2026-09-17 abort-park fix: an upstream fuse is a backoff, not a run kill.

Three layers, no charged model calls:

* Proxy (real loopback session + a scripted upstream): transient 429/5xx
  rejections and dropped transports retry inside the same client request with
  bounded backoff; success resets the consecutive-failure counter and only an
  exhausted budget counts exactly one failure.
* Runtime: a latched provider-session failure parks the roles riding the
  failed loopback session in observable provider waits instead of queueing a
  terminal runtime failure, and ``recover_provider_wait`` rebuilds a dead
  session instead of assuming it is alive.
* Runner (production foreground admission): the park is WAITING_OWNER with
  ``provider_waits`` visible and the control FIFO alive, cleanup never runs on
  the failure path, recovery continues the same run, and only an explicit
  ``stop`` cleans up.
"""

from __future__ import annotations

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.deepseek_provider_proxy import (
    RESPONSES_UPSTREAM_FAILURE,
    RESPONSES_UPSTREAM_MAX_ATTEMPTS,
    ResponsesProviderSession,
)
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.tests.test_provider_wait_recovery import (
    RECOVERY_TEXT,
    _FakeAppServer,
    _agent,
    _pump,
    _runner_with_adapter,
)


# --- Proxy layer: bounded in-request backoff -------------------------------------


class _ScriptedUpstream(BaseHTTPRequestHandler):
    """Return the next scripted status, then a final status forever."""

    protocol_version = "HTTP/1.1"
    statuses: list[tuple[int, str | None]] = []
    drops_before_response = 0
    lock = threading.Lock()

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        with self.lock:
            if _ScriptedUpstream.drops_before_response > 0:
                _ScriptedUpstream.drops_before_response -= 1
                # Simulate a transport drop: close without any HTTP response.
                self.close_connection = True
                try:
                    self.connection.close()
                except OSError:
                    pass
                return
            status, retry_after = (
                _ScriptedUpstream.statuses.pop(0)
                if _ScriptedUpstream.statuses
                else (200, None)
            )
        self.send_response(status)
        if retry_after is not None:
            self.send_header("Retry-After", retry_after)
        body = (
            b"{}"
            if 200 <= status < 300
            else b'{"provider":"must-never-reach-the-client"}'
        )
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture()
def scripted_upstream():
    _ScriptedUpstream.statuses = []
    _ScriptedUpstream.drops_before_response = 0
    server = HTTPServer(("127.0.0.1", 0), _ScriptedUpstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _session(upstream: HTTPServer, *, threshold: int) -> ResponsesProviderSession:
    # Zero backoff keeps the bounded retry observable without sleeping the
    # suite; the ladder itself is covered by the delay unit test below.
    session = ResponsesProviderSession(
        b"file-only-sentinel",
        upstream_url=f"http://127.0.0.1:{upstream.server_port}/responses",
        upstream_failure_threshold=threshold,
        max_upstream_attempts=3,
        retry_backoff_seconds=(0.0, 0.0, 0.0),
    )
    session.start()
    return session


def _post(session: ResponsesProviderSession) -> http.client.HTTPResponse:
    port = int(session.base_url.rsplit(":", 1)[1])
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(
        "POST", "/responses", body=b"{}", headers={"Content-Type": "application/json"}
    )
    return connection.getresponse()


def test_upstream_429s_are_absorbed_and_success_resets_the_counter(
    scripted_upstream,
) -> None:
    failures: list[str] = []
    session = _session(scripted_upstream, threshold=1)
    session.on_failure = failures.append
    _ScriptedUpstream.statuses = [(429, "0"), (429, "0"), (200, None)]
    try:
        response = _post(session)
        assert response.status == 200
        assert response.read() == b"{}"
    finally:
        session.stop()
    # Two transient rejections were absorbed inside one client request; the
    # consecutive-failure counter never advanced, let alone signaled.
    assert session.snapshot()["upstream_retries"] == 2
    assert session.snapshot()["upstream_errors"] == 0
    assert session._consecutive_upstream_failures == 0
    assert failures == []


def test_exhausted_retries_count_exactly_one_consecutive_failure(
    scripted_upstream,
) -> None:
    failures: list[str] = []
    session = _session(scripted_upstream, threshold=2)
    session.on_failure = failures.append
    _ScriptedUpstream.statuses = [(429, None)] * 8
    try:
        response = _post(session)
        assert response.status == 429
        assert response.read() == b""  # provider body is discarded, never relayed
        assert session._consecutive_upstream_failures == 1
        assert failures == []

        response = _post(session)
        assert response.status == 429
        response.read()
    finally:
        session.stop()
    # The threshold semantics are unchanged: the signal fires once at the
    # second consecutive exhausted request, not once per retried attempt.
    assert session.snapshot()["upstream_errors"] == 2
    assert session.snapshot()["upstream_retries"] == 2 * (session.max_upstream_attempts - 1)
    assert failures == [RESPONSES_UPSTREAM_FAILURE]
    assert session._consecutive_upstream_failures == 0


def test_dropped_transport_is_retried_inside_the_same_request(scripted_upstream) -> None:
    session = _session(scripted_upstream, threshold=1)
    _ScriptedUpstream.drops_before_response = 1
    try:
        response = _post(session)
        assert response.status == 200
        assert response.read() == b"{}"
    finally:
        session.stop()
    assert session.snapshot()["upstream_retries"] == 1
    assert session.snapshot()["upstream_errors"] == 0


def test_retry_delay_respects_retry_after_with_a_hard_ceiling() -> None:
    session = ResponsesProviderSession(
        b"file-only-sentinel",
        retry_backoff_seconds=(2.0, 4.0, 8.0),
        retry_after_ceiling_seconds=60.0,
    )
    try:
        assert session.upstream_retry_delay(1, "5") == 5.0
        # A provider cannot extend the backoff past the ceiling.
        assert session.upstream_retry_delay(1, "3600") == 60.0
        assert session.upstream_retry_delay(1, "-3") == 0.0
        # Non-numeric (or absent) Retry-After falls back to the ladder.
        assert session.upstream_retry_delay(1, "soon") == 2.0
        assert session.upstream_retry_delay(2, None) == 4.0
        # Out-of-range attempt indices stay bounded, never raise.
        assert session.upstream_retry_delay(99, None) == 8.0
    finally:
        session.stop()


def test_default_fuse_budget_is_three_attempts() -> None:
    session = ResponsesProviderSession(b"file-only-sentinel")
    try:
        assert RESPONSES_UPSTREAM_MAX_ATTEMPTS == 3
        assert session.max_upstream_attempts == 3
    finally:
        session.stop()


# --- Runtime layer: park instead of latch, rebuild dead sessions -----------------


def test_provider_session_failure_parks_session_roles_instead_of_latching(
    tmp_path: Path,
) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    session_role = _agent(tmp_path, agent_id="protocol")
    session_role.provider_id = "deepseek-direct"
    builtin_role = _agent(tmp_path, agent_id="coordinator")
    builtin_role.provider_id = None
    adapter.agents[session_role.agent_id] = session_role
    adapter.agents[builtin_role.agent_id] = builtin_role

    adapter._on_provider_session_failure("provider-upstream-failed")
    # A continuously dead listener re-signals on every receive tick: the park
    # is one episode, not a per-tick evidence stream.
    adapter._on_provider_session_failure("provider-upstream-failed")

    assert session_role.runtime_failure is None
    assert session_role.state == "waiting_provider"
    assert builtin_role.provider_wait is None
    assert builtin_role.state == "running"
    assert adapter.consume_runtime_failures() == []
    wait = adapter.provider_wait_status("protocol")
    assert wait is not None
    assert wait["variant"] == "provider-upstream-failed"
    assert wait["reason_code"] == "provider-upstream-failed"
    assert adapter.consume_provider_waits() == [("protocol", wait)]
    evidence = (tmp_path / "evidence" / "provider-wait.jsonl").read_text()
    assert '"reason_code": "provider-upstream-failed"' in evidence
    assert '"agent_id": "protocol"' in evidence


def test_recovery_rebuilds_a_dead_provider_session(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    server = _FakeAppServer()
    agent = _agent(tmp_path)
    agent.provider_id = "deepseek-direct"
    agent.process = SimpleNamespace(
        stdin=server.request, stdout=server.stdout, pid=None, terminate=server.terminate
    )
    adapter.agents[agent.agent_id] = agent
    adapter._enter_provider_wait(
        agent,
        {
            "source": "provider-session",
            "reason": "provider-upstream-failed",
            "variant": "provider-upstream-failed",
        },
    )
    rebuilds: list[dict[str, bool]] = []
    listening = [False]

    def restart() -> dict[str, bool]:
        rebuilds.append({"deepseek-direct": True})
        listening[0] = True
        return {"deepseek-direct": True}

    adapter._provider_sessions = SimpleNamespace(
        started=lambda: True,
        listening=lambda: listening[0],
        restart_dead_sessions=restart,
    )
    try:
        receipt = adapter.recover_provider_wait(agent.agent_id, RECOVERY_TEXT)
        assert receipt.mode == "start"
        assert rebuilds == [{"deepseek-direct": True}]
        assert agent.provider_wait is None
        assert agent.state == "running"
        # The episode latch is re-armed: a later failure can park again.
        assert adapter._provider_session_failure_parked is False
        evidence = (tmp_path / "evidence" / "provider-session-rebuilt.jsonl").read_text()
        assert "deepseek-direct" in evidence
    finally:
        server.close()


def test_unrebuildable_session_keeps_the_wait_recoverable(tmp_path: Path) -> None:
    from modeling_team.runtimes.codex import CodexRuntimeError

    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    adapter._run_root = tmp_path
    agent = _agent(tmp_path)
    agent.provider_id = "deepseek-direct"
    adapter.agents[agent.agent_id] = agent
    adapter._enter_provider_wait(
        agent,
        {
            "source": "provider-session",
            "reason": "provider-upstream-failed",
            "variant": "provider-upstream-failed",
        },
    )
    adapter._provider_sessions = SimpleNamespace(
        started=lambda: True,
        listening=lambda: False,
        restart_dead_sessions=lambda: {"deepseek-direct": False},
    )

    with pytest.raises(CodexRuntimeError, match="rebuild"):
        adapter.recover_provider_wait(agent.agent_id, RECOVERY_TEXT)

    # The typed rejection leaves the wait pending and never escalates to the
    # fatal latch: the host can retry after remediating the session.
    assert adapter.provider_wait_status(agent.agent_id) is not None
    assert agent.runtime_failure is None
    assert adapter.consume_runtime_failures() == []
    evidence = (tmp_path / "evidence" / "provider-wait-recovery-failed.jsonl").read_text()
    assert "provider-session-unrebuildable" in evidence


# --- Runner layer: WAITING_OWNER without cleanup until an explicit stop ----------


def test_provider_session_park_waits_for_owner_without_cleanup(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        for agent_id in ("coordinator", "protocol"):
            record = adapter.inject_wait(agent_id, variant="provider-upstream-failed")
            record["reason_code"] = "provider-upstream-failed"
            # inject_wait snapshots the record into the wait queue before the
            # enrichment above; refresh that queued copy to match.
            adapter._wait_queue[-1] = (agent_id, dict(record))

        output = _pump(runner, sink)
        waits = [entry for entry in output if entry["type"] == "provider-wait"]
        assert waits and all(entry["recoverable"] is True for entry in waits)
        assert all(
            entry["reason_code"] == "provider-upstream-failed" for entry in waits
        )

        state = json.loads((staged.run_root / "state.json").read_text())
        assert state["state"] == "WAITING_OWNER"
        assert state["host_action"] == "recover_provider"
        assert {item["agent_id"] for item in state["provider_waits"]} == {
            "coordinator",
            "protocol",
        }

        # No terminal settlement happened: no runtime-failure evidence, no
        # cleanup, the control FIFO still answers outer lines.
        assert not (staged.run_root / "evidence" / "runtime-failure.jsonl").exists()
        assert adapter.stopped is False
        assert staged.run_root.is_dir()
        assert runner._runtime_failure_finalized is False
        assert any(entry["type"] == "provider-wait-status" for entry in _pump(runner, sink))

        result = runner.receive_outer(
            {"action": "recover_provider", "role": "protocol", "text": RECOVERY_TEXT}
        )
        assert any(entry["type"] == "provider-recovery" for entry in result)
        # The Coordinator is still parked: the run stays owner-owned until the
        # last wait is recovered.
        state = json.loads((staged.run_root / "state.json").read_text())
        assert state["state"] == "WAITING_OWNER"
        assert {item["agent_id"] for item in state["provider_waits"]} == {"coordinator"}

        runner.receive_outer(
            {"action": "recover_provider", "role": "coordinator", "text": RECOVERY_TEXT}
        )
        state = json.loads((staged.run_root / "state.json").read_text())
        assert state["state"] == "RUNNING"

        # The same run continues on the next tick, cleanup-free.
        _pump(runner, sink)
        assert adapter.stopped is False
    finally:
        staged.cleanup()


def test_provider_session_park_cleans_up_only_on_explicit_stop(tmp_path: Path) -> None:
    staged, adapter, sink = _runner_with_adapter(tmp_path)
    runner = staged.runner
    try:
        record = adapter.inject_wait("protocol", variant="provider-upstream-failed")
        record["reason_code"] = "provider-upstream-failed"
        _pump(runner, sink)

        # A cleanup attempted behind the host's back is deferred while the
        # wait survives; the run stays observable.
        paused = runner.cleanup()
        assert paused["status"] == "paused" and paused["cleanup_deferred"] is True
        assert adapter.stopped is False
        assert staged.run_root.is_dir()

        output = runner.receive_outer({"action": "stop"})
        assert output[-1]["type"] == "stopped"
        assert adapter.stopped is True
    finally:
        staged.cleanup()
