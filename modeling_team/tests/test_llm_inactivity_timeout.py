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


def _record_retryable_stream_disconnect(adapter: CodexRuntimeAdapter, agent: _Agent) -> None:
    """Feed one real-shaped retryable provider error notification for the turn."""
    agent.thread_id = "thread-1"
    agent.active_turn_id = "turn-1"
    agent.last_started_turn_id = "turn-1"
    adapter._notification(
        agent,
        {
            "method": "error",
            "params": {
                "error": {
                    "message": "upstream stream disconnected",
                    "codexErrorInfo": {
                        "responseStreamDisconnected": {"httpStatusCode": None}
                    },
                },
                "willRetry": True,
                "threadId": "thread-1",
                "turnId": "turn-1",
            },
        },
    )


def test_retryable_provider_error_is_remembered_per_turn(tmp_path: Path) -> None:
    # #32 (auth021): a ``willRetry=true`` external error is observable evidence
    # but must not itself latch or park — only the wedged-stream silence after
    # it converts the watchdog timeout into a park.
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    _record_retryable_stream_disconnect(adapter, agent)
    with agent.state_lock:
        assert agent.turn_provider_error is not None
        assert agent.turn_provider_error["variant"] == "responseStreamDisconnected"
        assert agent.turn_provider_error["will_retry"] is True
    assert agent.provider_wait is None
    assert agent.runtime_failure is None
    assert adapter.consume_inactivity_failures() == []
    assert adapter.consume_provider_waits() == []


def test_inactivity_timeout_parks_after_retryable_provider_error(tmp_path: Path) -> None:
    # #32 (auth021 start1): the SDK promised a retry that never concluded; the
    # stream then hung silently for 21 minutes and the watchdog killed the run
    # fatally.  Silence after a recorded retryable external error is the
    # wedged-stream signature: park in a provider wait for host
    # ``recover_provider`` instead of the fatal latch.
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    _record_retryable_stream_disconnect(adapter, agent)
    with agent.state_lock:
        agent.last_output_monotonic = time.monotonic() - 400.0
    adapter._on_inactivity_timeout(agent, 300.0)
    assert agent.state == "waiting_provider"
    assert agent.provider_wait is not None
    assert agent.provider_wait["variant"] == "responseStreamDisconnected"
    assert (
        agent.provider_wait["reason_code"]
        == "llm-inactivity-timeout-after-retryable-provider-error"
    )
    assert agent.inactivity_failure is None
    assert agent.runtime_failure is None
    assert adapter.consume_inactivity_failures() == []
    waits = adapter.consume_provider_waits()
    assert len(waits) == 1
    assert waits[0][0] == agent.agent_id
    assert waits[0][1]["variant"] == "responseStreamDisconnected"
    # A repeated watchdog tick must not duplicate the wait or queue it twice.
    adapter._on_inactivity_timeout(agent, 300.0)
    assert adapter.consume_provider_waits() == []
    assert agent.provider_wait["notifications"] == 1


def test_new_turn_clears_remembered_provider_error(tmp_path: Path) -> None:
    # The memory is turn-scoped: once a new turn starts (the recovered path),
    # a later silent hang is a plain hang again and keeps the fatal latch.
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    _record_retryable_stream_disconnect(adapter, agent)
    assert agent.turn_provider_error is not None

    def fake_rpc(agent_value, method, payload):
        assert method == "turn/start"
        return {"turn": {"id": "turn-2"}}

    adapter._rpc = fake_rpc  # type: ignore[method-assign]
    agent.first_turn_input = [{"type": "text", "text": "next turn"}]
    adapter.start_task(agent.agent_id, "next turn", [], ["a", "b"])
    with agent.state_lock:
        assert agent.turn_provider_error is None
        assert agent.last_started_turn_id == "turn-2"
        assert agent.state == "running"
    with agent.state_lock:
        agent.last_output_monotonic = time.monotonic() - 400.0
    adapter._on_inactivity_timeout(agent, 300.0)
    assert agent.state == "failed"
    assert agent.inactivity_failure is not None
    assert agent.inactivity_failure["reason"] == "llm-inactivity-timeout"
    assert agent.provider_wait is None
    assert adapter.consume_provider_waits() == []


# --- native sleep lifecycle (auth01 start3) -------------------------------------
#
# The real 2026-10-03 failure: the last observable notification was
# ``item/started`` for the supported native ``sleep`` item (id
# ``call_e7tO3gAM4TOXNe0hrIHkMnjv``, durationMs 43200000) with no corresponding
# ``item/completed`` for 20 minutes; the turn is still ``running`` inside the
# sleep wait, so the inactivity watchdog latched a false
# ``llm-inactivity-timeout``.  A supported sleep wait is not LLM inactivity:
# its observable started -> completed lifecycle pauses the watchdog, and the
# matching completion restarts the clock.  Only observable native sleep items
# count; unknown notifications and mismatched lifecycles never extend anything.


def _sleep_item(item_id: str = "call_sleep_1", *, duration_ms: int = 43_200_000) -> dict:
    """One App Server sleep item; real item keys are id/type/durationMs."""

    return {"type": "sleep", "id": item_id, "durationMs": duration_ms}


def _sleep_params(
    item_id: str = "call_sleep_1",
    *,
    turn_id: str | None = None,
    thread_id: str | None = None,
) -> dict:
    """Real sleep notification params: item/startedAtMs plus explicit identities."""

    params: dict = {"item": _sleep_item(item_id), "startedAtMs": 1_790_980_205_004}
    if turn_id is not None:
        params["turnId"] = turn_id
    if thread_id is not None:
        params["threadId"] = thread_id
    return params


def _age_clock(agent: _Agent, seconds: float = 400.0) -> None:
    with agent.state_lock:
        agent.last_output_monotonic = time.monotonic() - seconds


def _failures_within(adapter: CodexRuntimeAdapter, seconds: float) -> list:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        failures = adapter.consume_inactivity_failures()
        if failures:
            return failures
        time.sleep(0.02)
    return []


def test_watchdog_pauses_during_native_sleep_and_rearms_after_completion(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    adapter._inactivity_timeout_seconds = 0.1
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    adapter._notification(agent, {"method": "item/started", "params": _sleep_params()})
    # The sleep has already been waiting 400s of LLM silence; without the pause
    # the watchdog latches here (the real start3 false failure).
    _age_clock(agent)
    adapter._start_inactivity_watchdog(agent)
    try:
        time.sleep(0.35)
        assert adapter.consume_inactivity_failures() == []
        assert agent.state == "running"
        assert agent.runtime_failure is None

        # The observable completed lifecycle closes the pause and restarts the clock.
        adapter._notification(agent, {"method": "item/completed", "params": {"item": _sleep_item()}})
        with agent.state_lock:
            assert agent.active_sleep_item_ids == set()
            assert agent.last_output_monotonic >= time.monotonic() - 0.5

        # Silence after the sleep is a real model stall again: the watchdog
        # must re-arm on the restarted clock (not exit at the pause).
        _age_clock(agent)
        failures = _failures_within(adapter, 2.0)
        assert failures, "the watchdog did not re-arm after the sleep completed"
        assert failures[0][1]["reason"] == "llm-inactivity-timeout"
        assert agent.state == "failed"
    finally:
        agent.inactivity_watchdog_stop.set()


def test_watchdog_does_not_pause_on_arbitrary_items_or_unidentified_sleeps(tmp_path: Path) -> None:
    # Only a well-formed native sleep item (type sleep plus a non-empty string
    # id) may pause the watchdog; anything else stays a real silence.
    for item in (
        {"type": "commandExecution", "id": "call_tool_1"},
        {"type": "sleep"},
        {"type": "sleep", "id": ""},
        {"type": "sleep", "id": 5},
    ):
        adapter = _make_adapter(tmp_path)
        adapter._inactivity_timeout_seconds = 0.1
        agent = _make_agent(tmp_path)
        adapter.agents[agent.agent_id] = agent
        agent.state = "running"
        adapter._notification(agent, {"method": "item/started", "params": {"item": item}})
        _age_clock(agent)
        adapter._start_inactivity_watchdog(agent)
        try:
            failures = _failures_within(adapter, 2.0)
            assert failures, f"the watchdog stayed paused for {item!r}"
            assert failures[0][1]["reason"] == "llm-inactivity-timeout"
        finally:
            agent.inactivity_watchdog_stop.set()


def test_mismatched_sleep_completion_neither_creates_nor_clears_a_pause(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    # A completion with no matching start never opens a pause.
    adapter._notification(
        agent, {"method": "item/completed", "params": {"item": _sleep_item("call_other")}}
    )
    with agent.state_lock:
        assert agent.active_sleep_item_ids == set()
    # A genuine pause only closes on its own lifecycle event.
    adapter._notification(
        agent, {"method": "item/started", "params": {"item": _sleep_item("call_sleep_a")}}
    )
    adapter._notification(
        agent, {"method": "item/completed", "params": {"item": _sleep_item("call_sleep_b")}}
    )
    with agent.state_lock:
        assert agent.active_sleep_item_ids == {"call_sleep_a"}
    adapter._notification(
        agent, {"method": "item/completed", "params": {"item": _sleep_item("call_sleep_a")}}
    )
    with agent.state_lock:
        assert agent.active_sleep_item_ids == set()


def test_unknown_notification_methods_neither_refresh_nor_pause(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    with agent.state_lock:
        agent.last_output_monotonic = 0.0
    adapter._notification(agent, {"method": "status/updated", "params": {"item": _sleep_item()}})
    with agent.state_lock:
        assert agent.last_output_monotonic == 0.0
        assert agent.active_sleep_item_ids == set()


def test_turn_boundaries_clear_a_stale_sleep_pause(tmp_path: Path) -> None:
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    agent.active_turn_id = "turn-1"
    agent.last_started_turn_id = "turn-1"
    adapter._notification(agent, {"method": "item/started", "params": {"item": _sleep_item()}})
    with agent.state_lock:
        assert agent.active_sleep_item_ids == {"call_sleep_1"}
    # A turn terminal that arrives without the sleep completion still ends the
    # wait: the pause never outlives its turn.
    adapter._notification(agent, {"method": "turn/completed", "params": {"turn": {"id": "turn-1"}}})
    with agent.state_lock:
        assert agent.active_sleep_item_ids == set()
    # A stale item from the finished turn cannot pause the next one either.
    adapter._notification(agent, {"method": "item/started", "params": {"item": _sleep_item()}})
    adapter._notification(agent, {"method": "turn/started", "params": {"turn": {"id": "turn-2"}}})
    with agent.state_lock:
        assert agent.active_sleep_item_ids == set()
    adapter._notification(agent, {"method": "item/started", "params": {"item": _sleep_item()}})
    adapter._notification(agent, {"method": "turn/failed", "params": {"turn": {"id": "turn-2"}}})
    with agent.state_lock:
        assert agent.active_sleep_item_ids == set()


def test_latch_rechecks_deadline_sleep_and_state_under_the_lock(tmp_path: Path) -> None:
    # The watchdog precheck runs outside the state lock; the latch decision
    # must re-verify the same facts under it, and the watch loop must survive
    # an aborted latch instead of exiting with the protection disarmed.
    # (a) activity arrived after the precheck.
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    _age_clock(agent)
    adapter._notification(
        agent,
        {"method": "item/agentMessage/delta", "params": {"itemId": "item-1", "delta": "x"}},
    )
    assert adapter._on_inactivity_timeout(agent, 300.0) is False
    assert agent.state == "running"
    assert agent.runtime_failure is None
    assert adapter.consume_inactivity_failures() == []

    # (b) a native sleep started after the precheck.
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    adapter._notification(agent, {"method": "item/started", "params": {"item": _sleep_item()}})
    _age_clock(agent)
    assert adapter._on_inactivity_timeout(agent, 300.0) is False
    assert agent.state == "running"
    assert agent.runtime_failure is None
    assert adapter.consume_inactivity_failures() == []

    # (c) the turn ended after the precheck.
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    agent.active_turn_id, agent.last_started_turn_id = "turn-1", "turn-1"
    adapter._notification(agent, {"method": "turn/completed", "params": {"turn": {"id": "turn-1"}}})
    _age_clock(agent)
    assert adapter._on_inactivity_timeout(agent, 300.0) is False
    assert agent.state == "idle"
    assert adapter.consume_inactivity_failures() == []


def test_final_latch_race_a_sleep_started_before_the_latch_cannot_be_killed(
    tmp_path: Path,
) -> None:
    # Host-review boundary: the eligibility re-check and the fatal latch were two
    # separate ``state_lock`` acquisitions.  A native sleep started by the reader
    # thread in that gap was accepted as a pause and then still killed by the
    # latch.  They must serialize: either the sleep is visible to the latch
    # decision (no kill), or the latch wins before the sleep exists — never both.
    adapter = _make_adapter(tmp_path)
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    agent.active_turn_id = "turn-1"
    agent.last_started_turn_id = "turn-1"
    agent.thread_id = "thread-1"
    _age_clock(agent, 400.0)

    original_latch = adapter._latch_runtime_failure
    reader_done = threading.Event()
    observed: dict[str, bool] = {}

    def race_latch(agent_arg: _Agent, detail, **kwargs):
        def start_sleep() -> None:
            adapter._notification(
                agent_arg,
                {
                    "method": "item/started",
                    "params": _sleep_params(
                        "call_race", turn_id="turn-1", thread_id="thread-1"
                    ),
                },
            )
            reader_done.set()

        reader = threading.Thread(target=start_sleep, daemon=True)
        reader.start()
        reader_done.wait(0.4)
        observed["sleep_visible_before_latch"] = reader_done.is_set()
        result = original_latch(agent_arg, detail, **kwargs)
        observed["latched"] = agent_arg.runtime_failure is not None
        return result

    adapter._latch_runtime_failure = race_latch  # type: ignore[method-assign]
    try:
        assert adapter._on_inactivity_timeout(agent, 300.0) is True
    finally:
        adapter._latch_runtime_failure = original_latch  # type: ignore[method-assign]
    # Both at once is the bug: the sleep was accepted as a pause and the role
    # was still killed as if the sleep had never been observed.
    assert not (observed["sleep_visible_before_latch"] and observed["latched"])
    # Under serialization the latch wins this ordering: the late sleep start is
    # dropped by the already-failed guard instead of pausing a dead role.
    assert observed["latched"] is True
    assert agent.state == "failed"
    assert adapter.consume_inactivity_failures() != []


def test_stale_sleep_notifications_never_pause_the_active_turn(tmp_path: Path) -> None:
    # Real notification shape (host-verified): params carry
    # item/startedAtMs/threadId/turnId; item carries id/type/durationMs.  A sleep
    # bound to a prior turn or thread must not pause the active turn's watchdog.
    for stale in (
        {"turn_id": "turn-old", "thread_id": "thread-1"},
        {"turn_id": "turn-1", "thread_id": "thread-old"},
    ):
        adapter = _make_adapter(tmp_path)
        adapter._inactivity_timeout_seconds = 0.1
        agent = _make_agent(tmp_path)
        adapter.agents[agent.agent_id] = agent
        agent.state = "running"
        agent.active_turn_id = "turn-1"
        agent.last_started_turn_id = "turn-1"
        agent.thread_id = "thread-1"
        adapter._notification(
            agent,
            {"method": "item/started", "params": _sleep_params("call_stale", **stale)},
        )
        with agent.state_lock:
            assert agent.active_sleep_item_ids == set()
        _age_clock(agent)
        adapter._start_inactivity_watchdog(agent)
        try:
            failures = _failures_within(adapter, 2.0)
            assert failures, f"a stale sleep paused the watchdog: {stale!r}"
            assert failures[0][1]["reason"] == "llm-inactivity-timeout"
        finally:
            agent.inactivity_watchdog_stop.set()


def test_sleep_for_the_active_turn_and_thread_still_pauses(tmp_path: Path) -> None:
    # Guard against over-rejection: ownership must accept the sleep that belongs
    # to the currently active turn/thread (and identity-less notifications).
    adapter = _make_adapter(tmp_path)
    adapter._inactivity_timeout_seconds = 0.1
    agent = _make_agent(tmp_path)
    adapter.agents[agent.agent_id] = agent
    agent.state = "running"
    agent.active_turn_id = "turn-1"
    agent.last_started_turn_id = "turn-1"
    agent.thread_id = "thread-1"
    adapter._notification(
        agent,
        {
            "method": "item/started",
            "params": _sleep_params("call_own", turn_id="turn-1", thread_id="thread-1"),
        },
    )
    with agent.state_lock:
        assert agent.active_sleep_item_ids == {"call_own"}
    _age_clock(agent)
    adapter._start_inactivity_watchdog(agent)
    try:
        time.sleep(0.35)
        assert adapter.consume_inactivity_failures() == []
        assert agent.state == "running"
    finally:
        agent.inactivity_watchdog_stop.set()
