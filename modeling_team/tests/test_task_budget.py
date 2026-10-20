"""R4.4-002 numeric budget and persistence checks; no upstream provider calls."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from modeling_team.close_statistics import ActivityRecorder
from modeling_team.task_budget import BudgetError, TaskBudget, bind_budget, budget_for
import modeling_team.task_budget as task_budget_module
from modeling_team.usage_capture import NumericReceiptWriter
from modeling_team.usage_report import estimate_budget_cost, estimate_tail_bound
from modeling_team.runtimes.dsh import DshRuntimeAdapter


def price(**extra):
    return {
        "provider": "route-a",
        "actual_model": "model-a",
        "cached_input_per_million": "0.2",
        "uncached_input_per_million": "2",
        "output_per_million": "8",
        **extra,
    }


def event(response_id="response-1", **extra):
    return {
        "event": "response_usage",
        "response_id": response_id,
        "provider": "route-a",
        "key_ref": "key-a",
        "actual_model": "model-a",
        "usage": {
            "input_tokens": 1_100_000,
            "cached_input_tokens": 1_000_000,
            "output_tokens": 10_000,
        },
        "status": "completed",
        **extra,
    }


def make_budget(tmp_path, amount="10"):
    return TaskBudget.create(
        tmp_path / "origin" / "cost-budget",
        {
            "budget_id": "budget-a",
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": amount,
            "prices": [price()],
        },
    )


def _runtime_binding(tmp_path):
    context = {
        "runtime": "codex",
        "agent_id": "delivery",
        "role": "delivery",
        "task_ref": "task-a",
        "provider": "route-a",
        "requested_model": "model-a",
        "runtime_session_id": "thread-a",
        "process_instance": "process-a",
    }
    recorder = ActivityRecorder(tmp_path / "run", context)
    usage_path = tmp_path / "run" / "provider-usage.jsonl"
    writer = NumericReceiptWriter(
        usage_path,
        {**context, "actual_model": "model-a", "key_ref": "key-a"},
    )
    binding = {
        "task_ref": "task-a",
        "provider": "route-a",
        "actual_model": "model-a",
        "key_ref": "key-a",
        "runtime": "codex",
        "runtime_session_id": "thread-a",
        "process_instance": "process-a",
    }
    return recorder, usage_path, writer, binding


def test_activity_recorder_and_numeric_writer_share_one_budget_attempt(tmp_path):
    budget = make_budget(tmp_path)
    recorder, usage_path, writer, binding = _runtime_binding(tmp_path)
    budget.register_source("activity", recorder.path, "activity", binding)
    budget.register_source("usage", usage_path, "capture", binding)
    recorder.emit("llm_start", call_id="call-1")
    inflight = budget.tick(now="2026-10-20T00:00:00+00:00")
    assert inflight["inflight_count"] == 1
    writer({
        "event": "response_usage",
        "request_id": "call-1",
        "response_id": "response-1",
        "actual_model": "model-a",
        "status": "completed",
        "raw_usage": {"input_tokens": 1_100_000, "output_tokens": 10_000},
        "present_fields": ["input_tokens", "output_tokens"],
        "usage_complete": True,
    })
    recorder.emit("llm_end", call_id="call-1", status="completed")
    settled = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert settled["inflight_count"] == 0
    assert settled["pending_settlement"] == 0
    assert settled["coverage"]["units"] == 1
    assert settled["charged_estimate"] == "2.28"
    attempts = json.loads(budget.state_path.read_text(encoding="utf-8"))["_attempts"]
    assert len(attempts) == 1
    assert next(iter(attempts.values()))["has_usage"] is True


def test_activity_end_without_numeric_usage_enters_grace_then_metering_error(tmp_path):
    budget = make_budget(tmp_path)
    recorder, _, _, binding = _runtime_binding(tmp_path)
    budget.register_source("activity", recorder.path, "activity", binding)
    recorder.emit("llm_start", call_id="missing-usage")
    recorder.emit("llm_end", call_id="missing-usage", status="completed")
    observed = datetime.now(timezone.utc)
    pending = budget.tick(now=observed)
    assert pending["pending_settlement"] == 1
    assert "metering_error" not in pending["pause_reasons"]
    late = budget.tick(now=observed + timedelta(seconds=11))
    assert any(
        item.get("reason") == "metering_error" if isinstance(item, dict) else item == "metering_error"
        for item in late["pause_reasons"]
    )


def test_thread_cumulative_snapshot_closes_matching_activity_turn(tmp_path):
    budget = make_budget(tmp_path)
    recorder, _, writer, binding = _runtime_binding(tmp_path)
    budget.register_source("activity", recorder.path, "activity", binding)
    # This is the turn-start contract supplied by the runtime.  A cumulative
    # snapshot is chargeable only after the runtime has published its fresh
    # zero baseline and the source evidence reference.
    cumulative_binding = {
        **binding,
        "cumulative_segment": {
            "id": "thread-a",
            "evidence_ref": str(writer.path),
            "baseline": {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_output_tokens": 0,
                "output_tokens": 0,
            },
            "fresh_zero_baseline": True,
            "start": "2000-01-01T00:00:00+00:00",
            "end": "9999-12-31T23:59:59.999999+00:00",
        },
    }
    budget.register_source("usage", writer.path, "capture", cumulative_binding)
    recorder.emit("llm_start", call_id="thread-a:turn-1", turn_id="turn-1")
    writer({
        "event": "thread_usage",
        "thread_id": "thread-a",
        "turn_id": "turn-1",
        "total": {
            "input_tokens": 1_100_000,
            "cached_input_tokens": 1_000_000,
            "reasoning_output_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": 10_000,
        },
    })
    recorder.emit("llm_end", call_id="thread-a:turn-1", turn_id="turn-1", status="completed")

    state = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert state["charged_estimate"] == "0.48"
    assert state["pending_settlement"] == 0
    assert state["inflight_count"] == 0
    assert "metering_error" not in state["pause_reasons"]


def _write_actual_dsh_native_event(tmp_path, *, usage=True, seq=7, step=1):
    runtime = DshRuntimeAdapter(repository_root=tmp_path)
    runtime._run = SimpleNamespace(root=tmp_path)
    runtime._record(
        "native-role",
        {
            "agent_id": "dsh-owner",
            "session_id": "dsh-session",
            "process_instance": "dsh-process",
            "frame": {
                "method": "session.event",
                "params": {
                    "sessionId": "dsh-session",
                    "event": {
                        "type": "assistant/message",
                        "timestamp": "2026-10-20T12:00:00+00:00",
                            "seq": seq,
                        "data": {
                            "turn": 2,
                                "step": step,
                            **({
                                "usage": {
                                    "inputTokens": 900_000,
                                    "cacheReadTokens": 100_000,
                                    "cacheWriteTokens": 0,
                                    "outputTokens": 10_000,
                                    "reasoningTokens": 0,
                                }
                            } if usage else {}),
                        },
                    },
                },
            },
        },
    )
    return tmp_path / "evidence" / "dsh-native-role.jsonl"


def _register_actual_dsh_sources(budget, tmp_path, native_path):
    binding = {
        "provider": "route-a",
        "actual_model": "model-a",
        "key_ref": "key-a",
        "runtime": "dsh",
        "runtime_session_id": "dsh-session",
        "process_instance": "dsh-process",
        "role": "delivery",
        "usage_definition_ref": "dsh:fixture",
    }
    budget.bind_owner("dsh-owner", role="delivery", runtime="dsh")
    budget.register_source(
        "dsh-native-source", native_path, "dsh_native", binding=binding, owner_id="dsh-owner"
    )
    provider_path = tmp_path / "evidence" / "dsh-provider.jsonl"
    writer = NumericReceiptWriter(
        provider_path,
        {
            "runtime": "dsh",
            "runtime_session_id": "dsh-session",
            "process_instance": "dsh-process",
            "provider": "route-a",
            "key_ref": "key-a",
            "requested_model": "model-a",
        },
    )
    writer({
        "event": "attempt_start",
        "request_id": "reqUUID-actual",
        "status": "unfinished",
        "start": "2026-10-20T12:00:00+00:00",
    })
    writer({
        "event": "attempt_end",
        "request_id": "reqUUID-actual",
        "status": "completed",
        "end": "2026-10-20T12:00:01+00:00",
    })
    budget.register_source(
        "dsh-provider-source",
        provider_path,
        "dsh_capture",
        binding={
            "provider": "route-a",
            "actual_model": "model-a",
            "key_ref": "key-a",
            "runtime": "dsh",
            "runtime_session_id": "dsh-session",
            "process_instance": "dsh-process",
        },
    )


def test_actual_dsh_handler_native_usage_satisfies_duplicate_proxy_lifecycle(tmp_path):
    budget = make_budget(tmp_path)
    native_path = _write_actual_dsh_native_event(tmp_path, usage=True)
    _register_actual_dsh_sources(budget, tmp_path, native_path)

    state = budget.tick(now="2026-10-20T12:00:02+00:00")
    assert state["charged_estimate"] == "1.9"
    assert state["pending_settlement"] == 0
    assert state["inflight_count"] == 0
    assert "metering_error" not in state["pause_reasons"]


def test_actual_dsh_handler_native_missing_usage_enters_grace(tmp_path):
    budget = make_budget(tmp_path)
    native_path = _write_actual_dsh_native_event(tmp_path, usage=False)
    _register_actual_dsh_sources(budget, tmp_path, native_path)

    pending = budget.tick(now="2026-10-20T12:00:02+00:00")
    assert pending["pending_settlement"] == 1
    assert "metering_error" not in pending["pause_reasons"]
    late = budget.tick(now="2026-10-20T12:00:13+00:00")
    assert any(
        item.get("reason") == "metering_error" if isinstance(item, dict) else item == "metering_error"
        for item in late["pause_reasons"]
    )


def test_native_steps_do_not_share_usage_identity(tmp_path):
    budget = make_budget(tmp_path)
    native_path = _write_actual_dsh_native_event(tmp_path, usage=True, seq=7, step=1)
    _write_actual_dsh_native_event(tmp_path, usage=False, seq=8, step=2)
    binding = {
        "provider": "route-a",
        "actual_model": "model-a",
        "key_ref": "key-a",
        "runtime": "dsh",
        "runtime_session_id": "dsh-session",
        "process_instance": "dsh-process",
    }
    budget.register_source("dsh-native-steps", native_path, "dsh_native", binding)

    pending = budget.tick(now="2026-10-20T12:00:02+00:00")
    assert pending["charged_estimate"] == "1.9"
    assert pending["pending_settlement"] == 1
    late = budget.tick(now="2026-10-20T12:00:13+00:00")
    assert any(
        item.get("reason") == "metering_error"
        if isinstance(item, dict)
        else item == "metering_error"
        for item in late["pause_reasons"]
    )


def test_native_primary_is_scoped_and_does_not_hide_other_runtime_or_session(tmp_path):
    budget = make_budget(tmp_path)
    native_path = _write_actual_dsh_native_event(tmp_path, usage=True)
    _register_actual_dsh_sources(budget, tmp_path, native_path)
    observed = datetime.now(timezone.utc)

    other_dsh_path = tmp_path / "evidence" / "other-dsh-provider.jsonl"
    other_dsh_writer = NumericReceiptWriter(
        other_dsh_path,
        {
            "runtime": "dsh",
            "runtime_session_id": "other-dsh-session",
            "process_instance": "other-dsh-process",
            "provider": "route-a",
            "key_ref": "key-a",
            "requested_model": "model-a",
        },
    )
    other_dsh_writer({
        "event": "attempt_start",
        "request_id": "other-dsh-request",
        "proxy_session_id": "other-dsh-proxy",
        "attempt_index": 1,
        "status": "unfinished",
        "start": observed.isoformat(),
    })
    other_dsh_writer({
        "event": "attempt_end",
        "request_id": "other-dsh-request",
        "proxy_session_id": "other-dsh-proxy",
        "attempt_index": 1,
        "status": "completed",
        "end": (observed + timedelta(seconds=1)).isoformat(),
    })
    budget.register_source(
        "other-dsh-provider",
        other_dsh_path,
        "dsh_capture",
        binding={
            "runtime": "dsh",
            "runtime_session_id": "other-dsh-session",
            "process_instance": "other-dsh-process",
            "provider": "route-a",
            "actual_model": "model-a",
            "key_ref": "key-a",
        },
    )

    codex_root = tmp_path / "codex"
    recorder, _, _, binding = _runtime_binding(codex_root)
    budget.register_source("codex-activity", recorder.path, "activity", binding)
    recorder.emit("llm_start", call_id="codex-missing", turn_id="turn-1")
    recorder.emit("llm_end", call_id="codex-missing", turn_id="turn-1", status="completed")

    pending = budget.tick(now=observed + timedelta(seconds=2))
    assert pending["charged_estimate"] == "1.9"
    assert pending["pending_settlement"] == 2
    late = budget.tick(now=observed + timedelta(seconds=13))
    assert any(
        item.get("reason") == "metering_error"
        if isinstance(item, dict)
        else item == "metering_error"
        for item in late["pause_reasons"]
    )


def test_proxy_retry_not_admitted_does_not_close_prior_unmetered_attempt(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "proxy-retries.jsonl"
    request = {
        "request_id": "same-request",
        "proxy_session_id": "proxy-session",
        "provider": "route-a",
        "actual_model": "model-a",
    }
    rows = [
        {
            **request,
            "event": "attempt_start",
            "attempt_index": 1,
            "status": "unfinished",
            "start": "2026-10-20T00:00:00+00:00",
        },
        {
            **request,
            "event": "attempt_end",
            "attempt_index": 1,
            "status": "completed",
            "end": "2026-10-20T00:00:01+00:00",
        },
        {
            **request,
            "event": "attempt_end",
            "attempt_index": 2,
            "status": "not_admitted",
            "end": "2026-10-20T00:00:02+00:00",
        },
    ]
    source.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    budget.register_source(
        "proxy-retries",
        source,
        "capture",
        {
            "runtime": "codex",
            "runtime_session_id": "proxy-thread",
            "provider": "route-a",
            "actual_model": "model-a",
            "key_ref": "key-a",
        },
    )

    pending = budget.tick(now="2026-10-20T00:00:02+00:00")
    assert pending["pending_settlement"] == 1
    late = budget.tick(now="2026-10-20T00:00:12+00:00")
    assert any(
        item.get("reason") == "metering_error"
        if isinstance(item, dict)
        else item == "metering_error"
        for item in late["pause_reasons"]
    )
    attempts = json.loads(budget.state_path.read_text(encoding="utf-8"))["_attempts"]
    assert len(attempts) == 1
    assert next(iter(attempts.values()))["status"] == "completed"


def test_not_admitted_attempt_end_is_not_a_paid_or_missing_attempt(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "proxy-attempts.jsonl"
    source.write_text(
        json.dumps({
            "event": "attempt_end",
            "request_id": "blocked-before-upstream",
            "provider": "route-a",
            "actual_model": "model-a",
            "status": "not_admitted",
            "received_at": "2026-10-20T00:00:00+00:00",
        }) + "\n",
        encoding="utf-8",
    )
    budget.register_source(
        "proxy-attempts",
        source,
        "capture",
        {"provider": "route-a", "actual_model": "model-a"},
    )

    observed = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert observed["inflight_count"] == 0
    assert observed["pending_settlement"] == 0
    assert observed["coverage"]["units"] == 0
    assert observed["pause_reasons"] == []
    assert json.loads(budget.state_path.read_text(encoding="utf-8"))["_attempts"] == {}

    after_grace = budget.tick(now="2026-10-20T00:00:12+00:00")
    assert after_grace["pending_settlement"] == 0
    assert after_grace["inflight_count"] == 0
    assert after_grace["pause_reasons"] == []


def test_not_admitted_end_closes_any_preexisting_activity_without_missing_usage(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "proxy-attempts.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {
                    "event": "attempt_start",
                    "request_id": "blocked-after-boundary",
                    "status": "unfinished",
                    "received_at": "2026-10-20T00:00:00+00:00",
                },
                {
                    "event": "attempt_end",
                    "request_id": "blocked-after-boundary",
                    "status": "not_admitted",
                    "received_at": "2026-10-20T00:00:01+00:00",
                },
            )
        ) + "\n",
        encoding="utf-8",
    )
    budget.register_source("proxy-attempts", source, "capture", {})

    state = budget.tick(now="2026-10-20T00:00:02+00:00")
    assert state["inflight_count"] == 0
    assert state["pending_settlement"] == 0
    assert state["pause_reasons"] == []
    attempts = json.loads(budget.state_path.read_text(encoding="utf-8"))["_attempts"]
    assert next(iter(attempts.values()))["status"] == "not_admitted"

    late = budget.tick(now="2026-10-20T00:00:13+00:00")
    assert late["pending_settlement"] == 0
    assert late["inflight_count"] == 0
    assert late["pause_reasons"] == []


def test_three_bucket_decimal_estimate_and_delivery_projection_is_scoped(tmp_path):
    budget = make_budget(tmp_path)
    budget.bind_owner("private-owner", role="judge")
    source = tmp_path / "usage.jsonl"
    source.write_text(json.dumps(event(role="production", actual_model="model-a")) + "\n", encoding="utf-8")
    budget.register_source("receipts", source, "receipts", {"owner_id": "private-owner"})

    state = budget.tick(now="2026-10-20T00:00:00+00:00")

    assert state["priced_amount"] == "0.48"
    assert state["charged_estimate"] == "0.48"
    assert state["remaining_estimate"] == "9.52"
    delivery = budget.show("delivery")
    assert "owners" not in delivery
    assert "sources" not in delivery
    assert "units" not in delivery
    assert "pause_reason_details" not in delivery
    assert delivery["charged_estimate"] == "0.48"
    assert state["coverage"]["by_role"]["production"]["known_amount"] == "0.48"
    assert state["coverage"]["by_model"]["model-a"]["known_amount"] == "0.48"


def test_source_replacement_and_restart_do_not_double_charge(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "usage.jsonl"
    source.write_text(json.dumps(event()) + "\n", encoding="utf-8")
    budget.register_source("receipts", source, "receipts", {})
    first = budget.tick(now="2026-10-20T00:00:00+00:00")
    assert first["charged_estimate"] == "0.48"

    # A late copy with the same identity is a replacement/copy, not a second call.
    source.write_text(json.dumps(event()) + json.dumps(event()) + "\n", encoding="utf-8")
    second = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert second["charged_estimate"] == "0.48"

    restarted = TaskBudget(budget.ref)
    assert restarted.show()["charged_estimate"] == "0.48"
    assert restarted.show()["sources"]["receipts"]["cursor"] == source.stat().st_size


def test_shared_source_session_slice_does_not_cross_charge_other_session(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "shared-provider.jsonl"
    source.write_text(
        json.dumps(event("owned", session_id="session-a", task_ref="task-a"))
        + "\n"
        + json.dumps(event("other", session_id="session-b", task_ref="task-b"))
        + "\n",
        encoding="utf-8",
    )
    budget.register_source(
        "shared",
        source,
        "capture",
        {"task_ref": "task-a", "provider": "route-a", "actual_model": "model-a"},
        capture_session_id="session-a",
    )
    state = budget.tick(now="2026-10-20T00:00:00+00:00")
    assert state["charged_estimate"] == "0.48"
    assert state["coverage"]["units"] == 1
    assert not any(issue["code"] == "binding_identity_conflict" for issue in state["coverage"]["issues"])


def test_explicit_row_binding_conflict_is_unpriced_and_pauses(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "wrong-task.jsonl"
    source.write_text(json.dumps(event(task_ref="other-task")) + "\n", encoding="utf-8")
    budget.register_source(
        "receipts",
        source,
        "receipts",
        {"task_ref": "task-a", "provider": "route-a", "actual_model": "model-a"},
    )
    state = budget.tick(now="2026-10-20T00:00:00+00:00")
    assert state["charged_estimate"] == "0"
    assert any(issue["code"] == "binding_identity_conflict" for issue in state["coverage"]["issues"])
    assert any(
        item.get("reason") == "metering_error" if isinstance(item, dict) else item == "metering_error"
        for item in state["pause_reasons"]
    )


def test_partial_response_is_replaced_by_final_usage_with_same_identity(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "usage.jsonl"
    partial = event(
        usage={
            "input_tokens": 1_100_000,
            "cached_input_tokens": None,
            "output_tokens": 10_000,
        },
        status="unfinished",
        usage_complete=False,
    )
    source.write_text(json.dumps(partial) + "\n", encoding="utf-8")
    budget.register_source("receipts", source, "receipts", {})
    first = budget.tick(now="2026-10-20T00:00:00+00:00")
    assert first["provisional_amount"] == "2.28"

    final = event(
        usage={
            "input_tokens": 1_100_000,
            "cached_input_tokens": 1_000_000,
            "output_tokens": 10_000,
        },
        status="completed",
        usage_complete=True,
    )
    with source.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(final) + "\n")
    state = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert state["priced_amount"] == "0.48"
    assert state["provisional_amount"] == "0"
    raw = json.loads(budget.state_path.read_text(encoding="utf-8"))
    assert not any("_conflict_variants" in row for row in raw["_records"].values())


def test_final_response_conflict_keeps_prior_charge_and_shared_locator(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "usage.jsonl"
    source.write_text(json.dumps(event()) + "\n", encoding="utf-8")
    budget.register_source("receipts", source, "receipts", {})
    assert budget.tick(now="2026-10-20T00:00:00+00:00")["charged_estimate"] == "0.48"

    conflicting = event(
        usage={
            "input_tokens": 1_100_000,
            "cached_input_tokens": 1_000_000,
            "output_tokens": 20_000,
        },
    )
    with source.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(conflicting) + "\n")
    state = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert state["charged_estimate"] == "0.48"
    assert any(item["code"] == "response_usage_conflict" for item in state["coverage"]["issues"])
    assert any(
        item.get("reason") == "metering_error" if isinstance(item, dict) else item == "metering_error"
        for item in state["pause_reasons"]
    )
    raw = json.loads(budget.state_path.read_text(encoding="utf-8"))
    variants = next(iter(raw["_records"].values()))["_conflict_variants"]
    assert len(variants) == 2
    assert {len(row["sources"]) for row in variants} == {1}


def test_event_suffix_replay_reloads_amount_without_replaying_source_cursor(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "usage.jsonl"
    source.write_text(json.dumps(event()) + "\n", encoding="utf-8")
    budget.register_source("receipts", source, "receipts", {})
    budget.tick()
    checkpoint = json.loads(budget.state_path.read_text(encoding="utf-8"))
    with source.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event("response-2")) + "\n")
    expected = budget.tick()["charged_estimate"]

    # Simulate a crash after the append-only event but before state.json.
    budget.state_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    restarted = TaskBudget(budget.ref)
    replayed = restarted.show()
    assert replayed["charged_estimate"] == expected
    assert replayed["sources"]["receipts"]["cursor"] == checkpoint["sources"]["receipts"]["cursor"]
    assert restarted.tick()["charged_estimate"] == expected


def test_multi_tick_crash_replay_keeps_checkpoint_until_source_catchup(tmp_path, monkeypatch):
    monkeypatch.setattr(task_budget_module, "MAX_TICK_RECORDS", 1)
    budget = make_budget(tmp_path)
    source = tmp_path / "usage.jsonl"
    source.write_text(json.dumps(event("response-1")) + "\n", encoding="utf-8")
    budget.register_source("receipts", source, "receipts", {})
    budget.tick(now="2026-10-20T00:00:00+00:00")
    checkpoint = json.loads(budget.state_path.read_text(encoding="utf-8"))
    for index in range(2, 5):
        with source.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event(f"response-{index}")) + "\n")
        budget.tick(now=f"2026-10-20T00:00:0{index}+00:00")
    expected = budget.show()["charged_estimate"]
    assert expected == "1.92"

    # The state checkpoint predates three committed tick events.  Replaying
    # their metadata gives the last safe subtotal, while source token history
    # still has to catch up from the old cursor over multiple bounded ticks.
    budget.state_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    restarted = TaskBudget(budget.ref)
    assert restarted.show()["charged_estimate"] == expected
    first = restarted.tick(now="2026-10-20T00:00:20+00:00")
    first_raw = json.loads(budget.state_path.read_text(encoding="utf-8"))
    assert first["charged_estimate"] == expected
    assert first_raw.get("_replay_targets")
    second = restarted.tick(now="2026-10-20T00:00:21+00:00")
    assert second["charged_estimate"] == expected
    final = restarted.tick(now="2026-10-20T00:00:22+00:00")
    final_raw = json.loads(budget.state_path.read_text(encoding="utf-8"))
    assert final["charged_estimate"] == expected
    assert final["coverage"]["units"] == 4
    assert "_replay_targets" not in final_raw


def test_corrupt_event_suffix_is_typed_and_partial_tail_is_recoverable(tmp_path):
    budget = make_budget(tmp_path)
    budget.bind_owner("owner")
    state = json.loads(budget.state_path.read_text(encoding="utf-8"))
    # Force the next read to include the malformed middle row.
    state["event_offset"] = 0
    state["event_seq"] = 0
    budget.state_path.write_text(json.dumps(state), encoding="utf-8")
    with budget.events_path.open("a", encoding="utf-8") as stream:
        stream.write('{"not-json"\n')
    fault = TaskBudget(budget.ref).show()
    assert fault["admission_open"] is False
    assert "metering_error" in fault["pause_reasons"]
    assert any(issue["reason"] == "event_ledger_corrupt" for issue in fault["coverage"]["issues"])

    # A real partial final event is ignored and removed before the next append.
    budget.events_path.write_text("", encoding="utf-8")
    budget.state_path.write_text(json.dumps(budget._initial_state(budget._auth())), encoding="utf-8")
    budget.events_path.write_bytes(b'{"partial":')
    assert TaskBudget(budget.ref).show()["event_seq"] == 0
    TaskBudget(budget.ref).request_pause("user_paused")
    assert TaskBudget(budget.ref).show()["pause_reasons"] == ["user_paused"]


def test_tick_uses_one_global_budget_and_rotates_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(task_budget_module, "MAX_TICK_BYTES", 2000)
    monkeypatch.setattr(task_budget_module, "MAX_TICK_RECORDS", 3)
    budget = make_budget(tmp_path)
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    payload = json.dumps(event()) + "\n"
    first.write_text(payload * 8, encoding="utf-8")
    second.write_text(payload.replace("response-1", "response-2") * 8, encoding="utf-8")
    budget.register_source("first", first, "receipts", {})
    budget.register_source("second", second, "receipts", {})
    budget.tick(now="2026-10-20T00:00:00+00:00")
    state = budget.show()
    consumed = state["sources"]["first"]["cursor"] + state["sources"]["second"]["cursor"]
    assert consumed <= 2000
    assert state["sources"]["first"]["cursor"] > 0
    assert state["sources"]["second"]["cursor"] == 0
    rotated = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert rotated["sources"]["second"]["cursor"] > 0


def test_backlog_persists_as_metering_error_after_ten_seconds(tmp_path, monkeypatch):
    monkeypatch.setattr(task_budget_module, "MAX_TICK_BYTES", 600)
    monkeypatch.setattr(task_budget_module, "MAX_TICK_RECORDS", 3)
    budget = make_budget(tmp_path)
    source = tmp_path / "large.jsonl"
    source.write_text((json.dumps(event()) + "\n") * 12, encoding="utf-8")
    budget.register_source("large", source, "receipts", {})
    first = budget.tick(now="2026-10-20T00:00:00+00:00")
    assert first["sources"]["large"]["backlog_since"] == "2026-10-20T00:00:00+00:00"
    late = budget.tick(now="2026-10-20T00:00:11+00:00")
    assert any(
        item.get("reason") == "metering_error" if isinstance(item, dict) else item == "metering_error"
        for item in late["pause_reasons"]
    )


def test_cumulative_usage_without_baseline_pauses_instead_of_counting_fresh_zero(tmp_path):
    budget = make_budget(tmp_path)
    source = tmp_path / "thread.jsonl"
    source.write_text(
        json.dumps(
            {
                "event": "thread_usage",
                "provider": "route-a",
                "key_ref": "key-a",
                "actual_model": "model-a",
                "runtime": "codex",
                "runtime_session_id": "thread-a",
                "timestamp": "2026-10-20T00:00:00+00:00",
                "total": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 10},
                "status": "completed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    budget.register_source("thread", source, "receipts", {})
    state = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert state["charged_estimate"] == "0"
    assert any(
        item.get("reason") == "metering_error" if isinstance(item, dict) else item == "metering_error"
        for item in state["pause_reasons"]
    )
    assert any(item["code"] == "cumulative_baseline_unproven" for item in state["coverage"]["issues"])


def test_closed_empty_source_is_known_zero_and_missing_source_pauses_after_grace(tmp_path):
    budget = make_budget(tmp_path)
    empty = tmp_path / "closed-empty.jsonl"
    empty.write_text("", encoding="utf-8")
    budget.register_source("closed", empty, "receipts", {}, closed=True)
    closed = budget.tick()
    assert closed["coverage"]["status"] == "complete"
    assert closed["coverage"]["known_zero_sources"] == 1
    assert closed["charged_estimate"] == "0"
    assert "metering_error" not in closed["pause_reasons"]

    missing = tmp_path / "missing.jsonl"
    budget.register_source("missing", missing, "receipts", {})
    first = budget.tick()
    assert "metering_error" not in first["pause_reasons"]
    heartbeat = datetime.fromisoformat(first["sources"]["missing"]["registered_at"])
    late = budget.tick(now=heartbeat + timedelta(seconds=11))
    assert any(
        item.get("reason") == "metering_error" if isinstance(item, dict) else item == "metering_error"
        for item in late["pause_reasons"]
    )


def test_exhaustion_has_stable_epoch_and_requires_explicit_continue(tmp_path):
    budget = make_budget(tmp_path, amount="0")
    with pytest.raises(BudgetError) as error:
        budget.require_available(operation="production")
    assert error.value.code == "budget_exhausted"
    first = budget.request_pause("budget_exhausted")
    second = budget.request_pause("budget_exhausted")
    assert first["pause_epoch"] == second["pause_epoch"]
    assert first["pause_reasons"] == second["pause_reasons"]
    with pytest.raises(BudgetError) as error:
        budget.require_available(operation="production")
    assert error.value.code == "budget_exhausted"

    budget.add({"delta_amount": "1", "authorization_id": "auth-2", "authorization_reference": "user-2"})
    # Additional funds do not silently clear the existing pause.
    with pytest.raises(BudgetError) as error:
        budget.require_available(operation="production")
    assert error.value.code == "budget_exhausted"
    continued = budget.continue_authorized("continue-1")
    assert continued["admission_open"] is True
    assert continued["pause_epoch"] == first["pause_epoch"] + 1


def test_host_binding_is_private_file_and_does_not_need_session_json(tmp_path):
    budget = make_budget(tmp_path)
    session_root = tmp_path / "new-session"
    bound = bind_budget(session_root, budget.ref, "delivery-owner", kind="delivery", run_id="run-1")
    resolved = budget_for(session_root)
    assert bound.ref == budget.ref
    assert resolved is not None
    assert resolved.ref == budget.ref
    assert resolved.show("host")["owners"]["delivery-owner"]["run_id"] == "run-1"


def test_invalid_operation_is_recoverable_and_price_can_be_zero(tmp_path):
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": "1",
            "prices": [price(cached_input_per_million="0")],
        },
    )
    with pytest.raises(BudgetError) as error:
        budget.require_available(operation="unregistered-runtime-action")
    assert error.value.code == "budget_operation_not_allowed"
    receipt = budget.require_available(operation="production", binding={"provider": "route-a", "actual_model": "model-a"})
    assert receipt["ok"] is True


def test_unbound_admission_does_not_require_every_price_snapshot(tmp_path):
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "budget_id": "multi-price",
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": "10",
            "prices": [price(), {"provider": "route-b", "actual_model": "model-b"}],
        },
    )
    assert budget.require_available(operation="production")["ok"] is True
    with pytest.raises(BudgetError) as error:
        budget.require_available(
            operation="production",
            binding={"provider": "route-b", "actual_model": "model-b"},
        )
    assert error.value.code == "budget_price_missing"


def test_binding_ref_is_immutable_and_metadata_is_supplemental(tmp_path):
    first = make_budget(tmp_path, amount="2")
    second = TaskBudget.create(
        tmp_path / "other",
        {"task_ref": "other", "authorization_reference": "user-2", "amount": "2", "prices": [price()]},
    )
    root = tmp_path / "session"
    bind_budget(root, first.ref, "owner-a", role="delivery", run_id="run-1")
    bind_budget(root, first.ref, "owner-b", phase="resume")
    binding = json.loads((root / "task-budget-binding.json").read_text(encoding="utf-8"))
    assert binding["budget_ref"] == str(first.ref)
    assert binding["metadata"]["role"] == "delivery"
    assert binding["metadata"]["phase"] == "resume"
    assert set(binding["owner_ids"]) == {"owner-a", "owner-b"}
    with pytest.raises(BudgetError) as error:
        bind_budget(root, second.ref, "owner-c")
    assert error.value.code == "budget_binding_conflict"


def test_control_turn_is_once_per_id_and_receipts_do_not_regress(tmp_path):
    budget = make_budget(tmp_path)
    first = budget.require_available(control_id="pause:0")
    assert first["ok"] is True
    with pytest.raises(BudgetError) as error:
        budget.require_available(control_id="pause:0")
    assert error.value.code == "control_turn_already_consumed"

    # The grant lives in the event/state ledger, so a fresh object cannot
    # reopen the same control turn after a process restart.
    restarted = TaskBudget(budget.ref)
    with pytest.raises(BudgetError) as error:
        restarted.require_available(control_id="pause:0")
    assert error.value.code == "control_turn_already_consumed"

    budget.record_control("owner", 0, "effective")
    unchanged = budget.record_control("owner", 0, "instruction_delivered")
    assert unchanged["status"] == "control_receipt_unchanged"
    budget.request_pause("budget_exhausted")
    next_epoch = budget.require_available(control_id="pause:0")
    assert next_epoch["ok"] is True
    assert next_epoch["pause_epoch"] == 1
    stale = budget.record_control("owner", 0, "effective")
    assert stale["status"] == "stale_control"


def test_monitor_lease_is_single_owner_and_heartbeat_is_durable(tmp_path):
    budget = make_budget(tmp_path)
    budget._claim_monitor("monitor-a")
    with pytest.raises(BudgetError) as error:
        budget._claim_monitor("monitor-b")
    assert error.value.code == "budget_monitor_owned"
    budget.tick(now="2026-10-20T00:00:00+00:00", monitor_id="monitor-a")
    monitor = budget.show()["monitor"]
    assert monitor["owner_id"] == "monitor-a"
    assert monitor["status"] == "active"


def test_monitor_stop_releases_lease_for_same_process_resume(tmp_path):
    budget = make_budget(tmp_path)
    monitor = budget.start_monitor(interval=0.01)
    monitor.stop(timeout=1)
    released = budget.show()["monitor"]
    assert released["owner_id"] is None
    assert released["status"] == "stopped"
    resumed = budget.start_monitor(interval=0.01)
    resumed.stop(timeout=1)


def test_create_retry_is_idempotent_even_when_created_at_would_change(tmp_path):
    ref = tmp_path / "budget"
    first = TaskBudget.create(
        ref,
        {
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": "1",
            "prices": [price()],
        },
    )
    second = TaskBudget.create(
        ref,
        {
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": "1",
            "prices": [price()],
        },
    )
    assert second.ref == first.ref
    assert second.show()["event_seq"] == 0


def test_add_and_continue_digest_and_metering_recovery(tmp_path):
    budget = make_budget(tmp_path, amount="0")
    resumed = budget.add({
        "delta_amount": "1",
        "authorization_id": "auth-continue",
        "authorization_reference": "user-ref",
        "continue_authorized": True,
    })
    assert resumed["admission_open"] is True
    assert budget.add({
        "delta_amount": "1",
        "authorization_id": "auth-continue",
        "authorization_reference": "user-ref",
        "continue_authorized": True,
    })["authorized_amount"] == "1"
    budget.register_source("missing", tmp_path / "does-not-exist.jsonl", "receipts", {})
    budget.tick()
    with pytest.raises(BudgetError) as error:
        budget.request_pause("metering_error")
        budget.continue_authorized("resume-without-fix", clear_reasons=["metering_error"])
    assert error.value.code == "metering_error"


def test_tail_bound_requires_credible_limits_and_uses_incremental_components():
    bounded = estimate_tail_bound(
        prices=[price()],
        limits={
            "inflight": [{"input_max_tokens": 5000, "output_max_tokens": 1250}],
            "control_delay": [{"input_max_tokens": 5000, "output_max_tokens": 1250}],
            "control_turns": [
                {"input_max_tokens": 5000, "output_max_tokens": 1250},
                {"input_max_tokens": 5000, "output_max_tokens": 1250},
            ],
        },
    )
    assert bounded["status"] == "bounded"
    assert bounded["amount"] == "0.08"
    unknown = estimate_tail_bound(prices=[price()], limits={"inflight": [{}]})
    assert unknown["status"] == "unknown"
    assert unknown["amount"] is None


def test_coverage_gaps_and_out_of_scope_are_explicit(tmp_path):
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": "1",
            "prices": [price()],
            "coverage_gaps": ["host-usage-not-wired"],
        },
    )
    state = budget.show()
    assert state["coverage_gaps"] == ["host-usage-not-wired"]
    scopes = {item["scope"]: item for item in state["out_of_scope"]}
    assert scopes["host"] == {
        "scope": "host", "status": "unknown", "amount": None,
        "deducted": False, "currency": "CNY",
    }
    assert scopes["unwired_auxiliary"]["deducted"] is False
    assert scopes["unwired_auxiliary"]["status"] == "unknown"


def test_budget_price_unit_is_fixed_to_one_million_tokens(tmp_path):
    with pytest.raises(BudgetError) as error:
        TaskBudget.create(
            tmp_path / "budget",
            {
                "task_ref": "task-a",
                "authorization_reference": "user-1",
                "amount": "1",
                "prices": [price(unit_tokens=1000)],
            },
        )
    assert error.value.code == "budget_config_invalid"
    assert error.value.details["field"] == "unit_tokens"


@pytest.mark.parametrize("field", ["provider", "actual_model"])
def test_budget_price_requires_exact_provider_and_model_selector(tmp_path, field):
    config_price = price()
    config_price.pop(field)
    with pytest.raises(BudgetError) as error:
        TaskBudget.create(
            tmp_path / field,
            {
                "task_ref": "task-a",
                "authorization_reference": "user-1",
                "amount": "1",
                "prices": [config_price],
            },
        )
    assert error.value.code == "budget_config_invalid"
    assert field in error.value.details["field"]


def test_allowed_bindings_derive_from_prices_and_allow_missing_price_then_add(tmp_path):
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": "1",
            "prices": [price()],
        },
    )
    assert budget.show()["allowed_bindings"] == [
        {"provider": "route-a", "actual_model": "model-a"}
    ]
    with pytest.raises(BudgetError) as error:
        budget.add({
            "delta_amount": "0",
            "authorization_id": "price-other",
            "authorization_reference": "user-2",
            "prices": [price(actual_model="model-b", version="v2")],
        })
    assert error.value.code == "budget_binding_not_allowed"

    missing = TaskBudget.create(
        tmp_path / "missing",
        {
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": "1",
            "allowed_bindings": [{"provider": "route-a", "actual_model": "model-a"}],
        },
    )
    with pytest.raises(BudgetError) as error:
        missing.require_available(binding={"provider": "route-a", "actual_model": "model-a"})
    assert error.value.code == "budget_price_missing"
    missing.add({
        "delta_amount": "0",
        "authorization_id": "price-a",
        "authorization_reference": "user-2",
        "prices": [price()],
    })
    assert missing.require_available(binding={"provider": "route-a", "actual_model": "model-a"})["ok"]


def test_new_price_version_does_not_reprice_already_used_binding(tmp_path):
    budget = make_budget(tmp_path, amount="10")
    source = tmp_path / "usage.jsonl"
    source.write_text(json.dumps(event()) + "\n", encoding="utf-8")
    budget.register_source("receipts", source, "receipts", {})
    assert budget.tick()["charged_estimate"] == "0.48"
    budget.add({
        "delta_amount": "0",
        "authorization_id": "price-v2",
        "authorization_reference": "user-v2",
        "prices": [price(version="v2", cached_input_per_million="1", uncached_input_per_million="1", output_per_million="1")],
    })
    assert budget.show()["charged_estimate"] == "0.48"
    with source.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event("response-2")) + "\n")
    after = budget.tick()
    # The first unit remains on v1 (0.48); only the new unit uses v2 (1.11).
    assert after["charged_estimate"] == "1.59"


def test_budget_decimal_estimate_keeps_large_token_and_tiny_price_precision():
    tokens = 10**32 + 7
    rate = "0.0000000000000000000000000000000003"
    record = {
        "usage": {
            "input_tokens": tokens,
            "cached_input_tokens": 0,
            "output_tokens": tokens,
        }
    }
    estimate = estimate_budget_cost(
        record,
        {
            "currency": "CNY",
            "unit_tokens": 1_000_000,
            "rates": {
                "cached_input_tokens": rate,
                "uncached_input_tokens": rate,
                "output_tokens": rate,
            },
        },
    )
    from decimal import Decimal, localcontext

    with localcontext() as context:
        context.prec = 100
        expected = (Decimal(tokens) * Decimal(rate) * 2) / Decimal(1_000_000)
    assert estimate["status"] == "usage_priced"
    assert Decimal(str(estimate["amount"])) == expected


def test_budget_projection_accumulates_long_decimal_rates_without_rounding(tmp_path):
    tokens = 10**32 + 7
    rate = "0.0000000000000000000000000000000003"
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": "0.000003",
            "prices": [
                price(
                    cached_input_per_million=rate,
                    uncached_input_per_million=rate,
                    output_per_million=rate,
                )
            ],
        },
    )
    source = tmp_path / "usage.jsonl"
    rows = [
        event(
            f"response-{index}",
            role="production",
            usage={
                "input_tokens": tokens,
                "cached_input_tokens": 0,
                "output_tokens": tokens,
            },
        )
        for index in range(40)
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    budget.register_source("receipts", source, "receipts", {})
    state = budget.tick(now="2026-10-20T00:00:00+00:00")
    from decimal import Decimal, localcontext

    with localcontext() as context:
        context.prec = 140
        expected = sum(
            (Decimal(tokens) * Decimal(rate) * 2) / Decimal(1_000_000)
            for _ in rows
        )
    assert Decimal(state["charged_estimate"]) == expected
    assert Decimal(state["coverage"]["by_role"]["production"]["known_amount"]) == expected


def test_budget_add_preserves_long_decimal_authorization(tmp_path):
    budget = make_budget(tmp_path, amount="1")
    delta = "0." + "0" * 30 + "1"
    state = budget.add({
        "delta_amount": delta,
        "authorization_id": "auth-long",
        "authorization_reference": "user-long",
    })
    assert state["authorized_amount"] == "1.0000000000000000000000000000001"
