from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent


def _make_adapter(tmp_path: Path) -> CodexRuntimeAdapter:
    adapter = CodexRuntimeAdapter(repository_root=tmp_path)
    # ``_run_root`` is normally set by ``start_roster``; point it at the test root so
    # ``_append_runtime_evidence`` writes instead of early-returning.
    adapter._run_root = tmp_path
    return adapter


def _make_agent(tmp_path: Path, agent_id: str = "protocol", role: str = "protocol") -> _Agent:
    return _Agent(
        agent_id,
        SimpleNamespace(role=role),
        tmp_path / "home",
        tmp_path / "work",
        tmp_path / "skills",
    )


def test_notification_refreshes_last_output_monotonic(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    with agent.state_lock:
        agent.last_output_monotonic = 0.0
    before = time.monotonic()
    adapter._notification(agent, {"method": "item/agentMessage/delta", "params": {}})
    with agent.state_lock:
        assert agent.last_output_monotonic >= before


def test_on_inactivity_timeout_latches_failure_and_state(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    with agent.state_lock:
        agent.last_output_monotonic = time.monotonic() - 400.0
    adapter._on_inactivity_timeout(agent, 300.0)
    assert agent.state == "failed"
    assert agent.inactivity_failure is not None
    assert agent.inactivity_failure["reason"] == "llm-inactivity-timeout"
    assert agent.inactivity_failure["role"] == "protocol"
    failures = adapter.consume_inactivity_failures()
    assert len(failures) == 1
    assert failures[0][0] == agent.agent_id
    assert failures[0][1]["reason"] == "llm-inactivity-timeout"


def test_on_inactivity_timeout_is_idempotent(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    with agent.state_lock:
        agent.last_output_monotonic = time.monotonic() - 400.0
    adapter._on_inactivity_timeout(agent, 300.0)
    # A repeated trigger (e.g. a racing watchdog tick) must not re-latch or double-record.
    adapter._on_inactivity_timeout(agent, 300.0)
    failures = adapter.consume_inactivity_failures()
    assert len(failures) == 1


def test_watchdog_fires_after_inactivity(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    adapter._inactivity_timeout_seconds = 0.1
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    with agent.state_lock:
        agent.last_output_monotonic = time.monotonic() - 1.0
    adapter._start_inactivity_watchdog(agent)
    try:
        failures: list = []
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            failures = adapter.consume_inactivity_failures()
            if failures:
                break
            time.sleep(0.02)
        assert failures, "inactivity watchdog did not fire within 2s"
        assert failures[0][1]["reason"] == "llm-inactivity-timeout"
        assert agent.state == "failed"
    finally:
        agent.inactivity_watchdog_stop.set()


def test_watchdog_does_not_fire_when_active(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    adapter._inactivity_timeout_seconds = 0.1
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    with agent.state_lock:
        agent.last_output_monotonic = time.monotonic()
    adapter._start_inactivity_watchdog(agent)
    keep_alive_stop = threading.Event()

    def keep_alive() -> None:
        # Simulate a steady stream of App Server notifications resetting the clock.
        while not keep_alive_stop.wait(0.02):
            with agent.state_lock:
                agent.last_output_monotonic = time.monotonic()

    refresher = threading.Thread(target=keep_alive, daemon=True)
    refresher.start()
    try:
        time.sleep(0.35)
        assert adapter.consume_inactivity_failures() == []
        assert agent.state == "running"
    finally:
        keep_alive_stop.set()
        agent.inactivity_watchdog_stop.set()


def test_watchdog_skips_non_running_state(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    adapter._inactivity_timeout_seconds = 0.1
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "idle"
    with agent.state_lock:
        agent.last_output_monotonic = time.monotonic() - 1.0
    adapter._start_inactivity_watchdog(agent)
    try:
        time.sleep(0.3)
        assert adapter.consume_inactivity_failures() == []
        assert agent.state == "idle"
    finally:
        agent.inactivity_watchdog_stop.set()
