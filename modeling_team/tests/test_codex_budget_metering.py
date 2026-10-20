"""Regression cases for the first real Codex amount-budget run."""

import json

import pytest

from modeling_team.runtimes.budget import RuntimeBudget
from modeling_team.tests.test_task_budget import _runtime_binding, make_budget


START = "2026-10-20T00:00:00+00:00"
END = "2026-10-20T00:00:01+00:00"
LATE = "2026-10-20T00:00:20+00:00"


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


@pytest.mark.parametrize("status", ["client_disconnected", "stream_error", "transport_error"])
def test_failed_transport_without_its_own_usage_is_not_hidden_by_native_usage(tmp_path, status):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy, status=status)
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    assert any(r["reason"] == "metering_error" for r in budget.tick(now=LATE)["pause_reasons"])


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


def test_one_native_sample_cannot_cover_multiple_successful_requests(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy)
    rows = proxy.read_text()
    proxy.write_text(rows + rows.replace('request-a', 'request-b'))
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    assert any(r["reason"] == "metering_error" for r in budget.tick(now=LATE)["pause_reasons"])


def test_duplicate_native_notification_does_not_hide_missing_usage(tmp_path):
    budget, writer, proxy = setup_native(tmp_path)
    proxy_rows(proxy)
    rows = proxy.read_text()
    proxy.write_text(rows + rows.replace('request-a', 'request-b'))
    snapshot(writer, 100, "2026-10-20T00:00:02+00:00")
    snapshot(writer, 100, "2026-10-20T00:00:03+00:00")
    assert any(r["reason"] == "metering_error" for r in budget.tick(now=LATE)["pause_reasons"])
