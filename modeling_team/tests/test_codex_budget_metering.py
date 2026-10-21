"""Regression cases for the first real Codex amount-budget run."""

import json
from io import StringIO
from types import SimpleNamespace

import pytest

from modeling_team.runtimes.budget import RuntimeBudget
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent
from modeling_team.close_statistics import ActivityRecorder
from modeling_team.task_budget import TaskBudget
from modeling_team.usage_capture import NumericReceiptWriter
from modeling_team.tests.test_task_budget import _runtime_binding, make_budget


START = "2026-10-20T00:00:00+00:00"
END = "2026-10-20T00:00:01+00:00"
LATE = "2026-10-20T00:00:20+00:00"


def test_recorder_thread_switch_keeps_prior_usage_and_late_old_notifications(tmp_path, monkeypatch):
    stamp = [START]
    monkeypatch.setattr("modeling_team.close_statistics.utc_now", lambda: stamp[0])
    monkeypatch.setattr("modeling_team.usage_capture.utc_now", lambda: stamp[0])
    budget = make_budget(tmp_path)
    path = tmp_path / "usage-events.jsonl"
    context = {"runtime": "codex", "agent_id": "delivery", "role": "delivery",
               "process_instance": "process-a", "provider": "route-a",
               "actual_model": "model-a", "key_ref": "key-a"}
    recorder = ActivityRecorder(
        tmp_path / "run", context, fresh_session=True,
        usage_sources=[{"path": path, "kind": "capture"}], budget=budget,
        budget_owner_id="delivery-a", budget_binding=context,
    )
    writer = NumericReceiptWriter(path, context)
    recorder.bind("thread-a")
    proxy = tmp_path / "provider-attempts.jsonl"
    RuntimeBudget(tmp_path, "delivery-a", budget, context, "codex").register_source(
        proxy, "capture", shared=True, capture_session_id="capture-a"
    )

    def write(thread, amount):
        writer({"event": "thread_usage", "thread_id": thread, "runtime_session_id": thread,
                "total": {"input_tokens": amount, "cached_input_tokens": 0,
                          "cache_write_tokens": 0, "output_tokens": amount // 10,
                          "reasoning_output_tokens": 0}})

    stamp[0] = END
    write("thread-a", 100)
    assert budget.tick(now=END)["charged_estimate"] == "0.00028"
    stamp[0] = "2026-10-20T00:00:02+00:00"
    recorder.bind("thread-b")
    recorder.bind("thread-b")  # repeated binding is not another cumulative segment
    write("thread-b", 200)
    stamp[0] = "2026-10-20T00:00:03+00:00"
    write("thread-a", 150)  # a queued old-thread notification arrives after switching
    rows = []
    for index in range(3):
        base = {"proxy_session_id": "proxy-a", "request_id": f"request-{index}",
                "attempt_index": 1, "session_id": "capture-a", "provider": "route-a",
                "requested_model": "model-a", "key_ref": "key-a"}
        rows.extend([
            {**base, "event": "attempt_start", "start": START, "status": "unfinished"},
            {**base, "event": "attempt_end", "end": END, "status": "completed"},
        ])
    proxy.write_text("".join(json.dumps(row) + "\n" for row in rows))
    state = budget.tick(now=LATE)
    assert state["charged_estimate"] == "0.00098"
    assert not state["coverage"]["issues"]
    assert not state["pause_reasons"]
    numeric = [s for s in state["sources"].values()
               if s["kind"] == "capture" and not s["metadata"].get("shared")]
    assert {s["binding"]["thread_id"] for s in numeric} == {"thread-a", "thread-b"}
    assert len(numeric) == 2
    recorder.exit(0)
    assert TaskBudget(budget.ref).tick(now=LATE)["charged_estimate"] == "0.00098"


def setup_native(tmp_path):
    budget = make_budget(tmp_path)
    _, _, writer, binding = _runtime_binding(tmp_path)
    binding["cumulative_segment"] = {
        "id": "thread-a", "evidence_ref": str(writer.path),
        "fresh_zero_baseline": True, "start": START,
        "end": "9999-12-31T23:59:59.999999+00:00",
    }
    member = RuntimeBudget(tmp_path, "owner-a", budget, binding, "codex")
    member.register_source(writer.path, "capture")
    proxy = tmp_path / "proxy.jsonl"
    member.register_source(proxy, "capture", shared=True, capture_session_id="capture-a")
    return budget, writer, proxy


def snapshot(writer, count, stamp):
    writer({
        "event": "thread_usage", "thread_id": "thread-a", "turn_id": "turn-a",
        "received_at": stamp,
        "total": {
            "input_tokens": count, "cached_input_tokens": 0,
            "cache_write_tokens": 0, "output_tokens": count // 10,
            "reasoning_output_tokens": 0,
        },
    })


def proxy_rows(path, *, status="completed", key="key-a"):
    base = {
        "proxy_session_id": "proxy-a", "request_id": "request-a", "attempt_index": 1,
        "session_id": "capture-a", "provider": "route-a", "requested_model": "model-a",
        "key_ref": key,
    }
    path.write_text("\n".join(json.dumps(row) for row in (
        {**base, "event": "attempt_start", "start": START, "status": "unfinished"},
        {**base, "event": "attempt_end", "end": END, "status": status},
    )) + "\n")


def test_cumulative_snapshots_keep_file_order_after_persisted_map_reload(tmp_path):
    budget, writer, _ = setup_native(tmp_path)
    for count, stamp in ((100, END), (200, "2026-10-20T00:00:02+00:00"),
                         (300, "2026-10-20T00:00:03+00:00")):
        snapshot(writer, count, stamp)
    budget.tick(now=LATE)
    # Durable maps are keyed by a digest, not append order.
    with budget._locked():
        state = budget._load_state()
        rows = sorted(state["_records"].items(), key=lambda pair: pair[1]["sources"][0]["byte_offset"])
        state["_records"] = dict((rows[0], rows[2], rows[1]))
        budget._refresh_summary(state, now=LATE)
    assert state["charged_estimate"] == "0.00084"
    assert not state["coverage"]["issues"]


def test_real_cumulative_reset_stays_visible(tmp_path):
    budget, writer, _ = setup_native(tmp_path)
    snapshot(writer, 300, END)
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    state = budget.tick(now=LATE)
    assert any(issue["code"] == "cumulative_reset" for issue in state["coverage"]["issues"])
    assert any(r["reason"] == "metering_error" for r in state["pause_reasons"])


def test_successful_transport_uses_bound_native_metering_without_double_charge(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy)
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    state = budget.tick(now=LATE)
    assert state["charged_estimate"] == "0.00028"
    assert state["pending_settlement"] == 0
    assert not state["pause_reasons"]
    attempt = next(iter(budget._load_state()["_attempts"].values()))
    assert not attempt["has_usage"]  # no invented per-request receipt
    assert attempt["native_coverage"]["additive"] is False


def test_shared_capture_keeps_earlier_member_native_coverage(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy)
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    # Concurrent Consumers share one file; the last source registration is not
    # the identity of every row. Native coverage still binds the row's session.
    RuntimeBudget(tmp_path, "owner-b", budget, {}, "codex").register_source(
        proxy, "capture", shared=True, capture_session_id="capture-b"
    )
    state = budget.tick(now=LATE)
    assert state["charged_estimate"] == "0.00028"
    assert not state["coverage"]["issues"]
    assert not state["pause_reasons"]


def test_shared_capture_cannot_borrow_another_sessions_native_usage(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    RuntimeBudget(tmp_path, "owner-b", budget, {}, "codex").register_source(
        proxy, "capture", shared=True, capture_session_id="capture-b"
    )
    proxy_rows(proxy)
    proxy.write_text(proxy.read_text().replace("capture-a", "capture-b"))
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    state = budget.tick(now=LATE)
    assert any(issue["code"] == "metering_error" for issue in state["coverage"]["issues"])


def test_shared_capture_admits_all_registered_sessions_and_excludes_others(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    RuntimeBudget(tmp_path, "owner-b", budget, {}, "codex").register_source(
        proxy, "capture", shared=True, capture_session_id="capture-b"
    )
    proxy_rows(proxy)
    rows = proxy.read_text()
    proxy.write_text(rows + rows.replace("capture-a", "foreign-capture").replace("request-a", "foreign"))
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    state = budget.tick(now=LATE)
    attempts = list(budget._load_state()["_attempts"].values())
    assert len(attempts) == 1 and attempts[0]["session_id"] == "capture-a"
    assert attempts[0]["native_coverage"]["additive"] is False
    assert state["charged_estimate"] == "0.00028"
    assert not state["coverage"]["issues"]


def test_native_thread_segments_share_file_without_cross_attribution(tmp_path, monkeypatch):
    budget, writer, _ = setup_native(tmp_path)
    source_id, source = next((key, row) for key, row in budget.show()["sources"].items()
                             if not row["metadata"].get("shared"))
    boundary = "2026-10-20T00:00:03+00:00"
    binding = source["binding"]
    budget.register_source(source_id, writer.path, "capture", {
        **binding, "cumulative_segment": {**binding["cumulative_segment"], "end": boundary},
    })
    budget.register_source("native-thread-b", writer.path, "capture", {
        **binding, "thread_id": "thread-b", "runtime_session_id": "thread-b",
        "cumulative_segment": {**binding["cumulative_segment"], "id": "thread-b", "start": boundary},
    }, runtime="codex", native_capture_session_id="capture-b")
    monkeypatch.setattr("modeling_team.usage_capture.utc_now", lambda: "2026-10-20T00:00:02+00:00")
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    monkeypatch.setattr("modeling_team.usage_capture.utc_now", lambda: "2026-10-20T00:00:04+00:00")
    writer({"event": "thread_usage", "thread_id": "thread-b", "turn_id": "turn-b",
            "runtime_session_id": "thread-b",
            "received_at": "2026-10-20T00:00:04+00:00", "total": {
                "input_tokens": 100, "cached_input_tokens": 0, "cache_write_tokens": 0,
                "output_tokens": 10, "reasoning_output_tokens": 0}})
    state = budget.tick(now=LATE)
    assert state["charged_estimate"] == "0.00056"
    assert not state["coverage"]["issues"]


@pytest.mark.parametrize("status", ["client_disconnected", "stream_error", "transport_error"])
def test_failed_transport_without_numeric_basis_stays_paused(tmp_path, status):
    budget, _, proxy = setup_native(tmp_path)
    proxy_rows(proxy, status=status)
    state = budget.tick(now=LATE)
    assert any(r["reason"] == "metering_error" for r in state["pause_reasons"])


@pytest.mark.parametrize("key", ["other-key", None])
def test_unrelated_native_credential_cannot_cover_proxy(tmp_path, key):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy, key=key)
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    assert any(r["reason"] == "metering_error" for r in budget.tick(now=LATE)["pause_reasons"])


def test_missing_native_numbers_still_pause_successful_transport(tmp_path):
    budget, _, proxy = setup_native(tmp_path)
    proxy_rows(proxy)
    assert any(r["reason"] == "metering_error" for r in budget.tick(now=LATE)["pause_reasons"])


def test_unmatched_transport_is_provisional_and_late_native_replaces_it(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy)
    rows = proxy.read_text()
    proxy.write_text(rows + rows.replace('request-a', 'request-b'))
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    first = budget.tick(now=LATE)
    assert first["provisional_amount"] == "0.00056"
    assert first["charged_estimate"] == "0.00084"
    assert not first["coverage"]["issues"]
    snapshot(writer, 200, "2026-10-20T00:00:03+00:00")
    final = budget.tick(now=LATE)
    assert final["provisional_amount"] == "0"
    assert final["charged_estimate"] == "0.00056"
    assert not final["coverage"]["issues"]


def test_duplicate_native_notification_does_not_hide_missing_usage(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy)
    rows = proxy.read_text()
    proxy.write_text(rows + rows.replace('request-a', 'request-b'))
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    snapshot(writer, 100, "2026-10-20T00:00:03+00:00")
    state = budget.tick(now=LATE)
    assert state["provisional_amount"] == "0.00056"
    assert state["charged_estimate"] == "0.00084"


def test_host_estimate_covers_exact_ended_attempt_and_real_usage_replaces_it(tmp_path):
    from modeling_team.task_budget import BudgetError
    budget, writer, proxy = setup_native(tmp_path)
    for source_id, source in budget.show()["sources"].items():
        if not source["metadata"].get("shared"):
            budget.register_source(source_id, source["path"], source["kind"], source["binding"],
                                   native_capture_session_id="another-capture")
    proxy_rows(proxy, status="client_disconnected")
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    budget.tick(now=LATE)
    arguments = dict(
        proxy_session_id="proxy-a", request_id="request-a", attempt_index=1,
        usage_estimate={"input_tokens": 200, "output_tokens": 20},
        evidence_reference="host-private:numeric-comparison", basis="conservative-comparison",
    )
    with pytest.raises(BudgetError):
        budget.record_attempt_estimate(**{**arguments, "proxy_session_id": "wrong-proxy"})
    state = budget.record_attempt_estimate(**arguments)
    assert state["charged_estimate"] == "0.00084"
    assert state["provisional_amount"] == "0.00056"
    assert not state["coverage"]["issues"]
    assert budget.record_attempt_estimate(**arguments)["charged_estimate"] == "0.00084"
    with proxy.open("a") as stream:
        stream.write(json.dumps({
            "event": "response_usage", "proxy_session_id": "proxy-a", "request_id": "request-a",
            "attempt_index": 1, "response_id": "actual-failed-response", "session_id": "capture-a",
            "provider": "route-a", "key_ref": "key-a", "actual_model": "model-a",
            "status": "completed", "usage": {"input_tokens": 100, "cached_input_tokens": 0,
            "output_tokens": 10},
        }) + "\n")
    final = budget.tick(now=LATE)
    assert final["charged_estimate"] == "0.00056"
    assert final["provisional_amount"] == "0"


def test_native_cancellation_gets_explicit_provisional_cost_without_faking_usage(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy, status="client_disconnected")
    rows = proxy.read_text()
    proxy.write_text(rows + rows.replace('request-a', 'request-b'))
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    state = budget.tick(now=LATE)
    assert state["provisional_amount"] == "0.00056"
    assert not state["coverage"]["issues"]
    attempt = next(iter(budget._load_state()["_attempts"].values()))
    assert attempt["status"] == "client_disconnected" and not attempt["has_usage"]


def native_activity(budget, tmp_path, *, ended=False, session="thread-a"):
    path = tmp_path / "native-activity.jsonl"
    binding = {"runtime": "codex", "runtime_session_id": session,
               "provider": "route-a", "actual_model": "model-a", "key_ref": "key-a"}
    budget.register_source("native-activity", path, "activity", binding, runtime="codex")
    rows = [{"event": "llm_start", "call_id": "native-turn-a", "turn_id": "turn-a",
             "recorded_at": START}]
    if ended:
        rows.append({"event": "llm_end", "call_id": "native-turn-a", "turn_id": "turn-a",
                     "recorded_at": "2026-10-20T00:00:19+00:00", "status": "completed"})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_transport_waits_for_its_active_native_turn_without_missing_usage_pause(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy)
    native_activity(budget, tmp_path)
    state = budget.tick(now=LATE)
    assert not state["pause_reasons"]
    assert state["pending_settlement"] >= 1
    assert state["inflight_count"] >= 1
    snapshot(writer, 100, LATE)
    assert not budget.tick(now=LATE)["pause_reasons"]


@pytest.mark.parametrize("first_turn,notification_first", [(False, False), (False, True),
                                                          (True, True)])
def test_turn_dispatch_precedes_proxy_even_when_start_notice_arrives_late(
    tmp_path, monkeypatch, first_turn, notification_first,
):
    # A provider request can finish before the first native usage notification.
    # Its turn must start at dispatch, not at the later local acknowledgement.
    stamp = [START]
    monkeypatch.setattr("modeling_team.close_statistics.utc_now", lambda: stamp[0])
    monkeypatch.setattr("modeling_team.close_statistics.clock_stamp", lambda: {
        "clock_ref": "dispatch-clock", "monotonic_ns": 100 if stamp[0] == START else 200,
    })
    budget, _, proxy = setup_native(tmp_path)
    binding = {"runtime": "codex", "runtime_session_id": "thread-a",
               "provider": "route-a", "actual_model": "model-a", "key_ref": "key-a"}
    recorder = ActivityRecorder(tmp_path / "runtime", binding)
    budget.register_source("native-activity", recorder.path, "activity", binding, runtime="codex")

    class Input(StringIO):
        def flush(self):
            proxy_rows(proxy)
            stamp[0] = "2026-10-20T00:00:00.010756+00:00"

    agent = _Agent("modeling", None, tmp_path, tmp_path, tmp_path,
                   process=SimpleNamespace(stdin=Input(), stdout=StringIO()),
                   thread_id="thread-a", activity=recorder,
                   auth_barrier_pending=first_turn, credential_mode="provider_proxy")
    adapter = CodexRuntimeAdapter(repository_root=tmp_path, use_bwrap=False)
    frames = []
    if notification_first:
        frames.append({"method": "turn/started", "params": {"turn": {"id": "turn-a"}}})
    frames.append({"id": 1, "result": {"turn": {"id": "turn-a"}}})
    replies = iter(json.dumps(frame) for frame in frames)
    monkeypatch.setattr(adapter, "_read_output_line", lambda *_: next(replies))
    monkeypatch.setattr(adapter, "_drain_agent_output_locked", lambda *_: None)

    reply = adapter._rpc(agent, "turn/start", {"threadId": "thread-a", "input": []})
    adapter._activity_turn_start(agent, reply["turn"]["id"])
    state = budget.tick(now=LATE)
    assert not state["pause_reasons"]
    assert not state["coverage"]["issues"]
    assert state["pending_settlement"] >= 1
    rows = [json.loads(line) for line in recorder.path.read_text().splitlines()]
    starts = [row for row in rows if row["event"] == "llm_start"]
    assert len(starts) == 1 and starts[0]["recorded_at"] == START
    assert starts[0]["clock_ref"] == "dispatch-clock"
    assert starts[0]["monotonic_ns"] == 100

    # The original protection still starts its grace at actual turn completion.
    stamp[0] = "2026-10-20T00:00:19+00:00"
    adapter._activity_turn_end(agent, "turn-a", "completed")
    assert not budget.tick(now=LATE)["pause_reasons"]
    late = budget.tick(now="2026-10-20T00:00:30+00:00")
    assert any(row["reason"] == "metering_error" for row in late["pause_reasons"])


def test_transport_missing_usage_grace_starts_when_native_turn_ends(tmp_path):
    budget, _, proxy = setup_native(tmp_path)
    proxy_rows(proxy)
    native_activity(budget, tmp_path, ended=True)
    assert not budget.tick(now=LATE)["pause_reasons"]
    state = budget.tick(now="2026-10-20T00:00:30+00:00")
    assert any(row["reason"] == "metering_error" for row in state["pause_reasons"])


@pytest.mark.parametrize("session,status", [("other-thread", "completed"),
                                           ("thread-a", "transport_error")])
def test_native_turn_cannot_hide_foreign_or_failed_transport(tmp_path, session, status):
    budget, _, proxy = setup_native(tmp_path)
    proxy_rows(proxy, status=status)
    native_activity(budget, tmp_path, session=session)
    assert any(row["reason"] == "metering_error" for row in budget.tick(now=LATE)["pause_reasons"])
