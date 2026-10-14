"""Deterministic A1–A7 engineering counterexamples; no provider calls."""

import copy
import hashlib
import json

import pytest

from modeling_team.usage_report import ScopeError, build_report, render_markdown, write_report

START = "2026-10-14T00:00:00+00:00"
STAMP = "2026-10-14T01:00:00+00:00"
END = "2026-10-15T00:00:00+00:00"
IDENTITY = dict(
    task_ref="task-a",
    provider="provider-a",
    account_ref="account-a",
    key_ref="key-A",
    requested_model="model-a",
    actual_model="model-a",
    requested_effort="high",
    effective_effort="high",
    role="delivery",
    phase="supervision",
    session_id="session-a",
    run_id="run-a",
    operation_id="operation-a",
    round=1,
    thread_id="thread-a",
    usage_definition_ref="provider-usage-definition",
)


def usage(i=100, c=60, o=20, r=5):
    return dict(input_tokens=i, cached_input_tokens=c, output_tokens=o, reasoning_output_tokens=r)


def receipt(rid="r1", **extra):
    return dict(response_id=rid, timestamp=STAMP, usage=usage(), **extra)


def scope(tmp_path, records=None):
    path = tmp_path / "receipts.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in (records or [receipt()])))
    return dict(
        schema_version="model-usage-scope/v1",
        task_ref="task-a",
        inventory_complete=True,
        task_window=dict(start=START, end=END, timezone="UTC", start_source="authorization"),
        sources=[dict(id="s1", root=str(tmp_path), path=path.name, kind="receipts")],
        bindings=[dict(source_id="s1", evidence_ref="session-receipt", **IDENTITY)],
        layer_coverage=[dict(role="delivery", status="observed")],
    )


def add_source(s, tmp_path, sid, records, kind="receipts", **binding):
    path = tmp_path / f"{sid}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    s["sources"].append(dict(id=sid, root=str(tmp_path), path=path.name, kind=kind))
    s["bindings"].append(dict(source_id=sid, evidence_ref="binding", **{**IDENTITY, **binding}))
    return path


def tokens(report):
    return report["task_usage"]["tokens"]


def bill(s, **extra):
    s["billing_scope"] = dict(
        provider="provider-a",
        account_ref="account-a",
        key_ref="key-A",
        model="model-a",
        start=START,
        end=END,
        timezone="UTC",
        time_basis="usage_completion",
        source_ref="vendor-export",
        key_binding_evidence_ref="console-key-filter",
        definition_ref="provider-usage-definition",
        inventory_complete=True,
        vendor_usage=usage(),
        **extra,
    )


def test_response_copy_and_conflict_keep_safe_fields(tmp_path):
    s = scope(tmp_path)
    add_source(s, tmp_path, "copy", [receipt()])
    report = build_report(s)
    assert tokens(report)["input_tokens"] == 100
    assert len(report["responses"]) == 1
    assert len(report["responses"][0]["sources"]) == 2
    add_source(s, tmp_path, "conflict", [{**receipt(), "usage": usage(i=110)}])
    report = build_report(s)
    assert tokens(report)["input_tokens"] is None
    assert tokens(report)["output_tokens"] == 20
    assert report["usage_status"] == "partial"
    assert any(x["code"] == "response_usage_conflict" for x in report["limitations"])


def test_no_response_id_needs_real_unique_request_proof(tmp_path):
    s = scope(tmp_path, [receipt(None, request_id="req")])
    assert tokens(build_report(s))["input_tokens"] is None
    p = tmp_path / "receipts.jsonl"
    p.write_text(
        json.dumps(receipt(None, request_id="req", unique_request_evidence_ref="wire-id")) + "\n"
    )
    assert tokens(build_report(s))["input_tokens"] == 100


def test_partial_fields_do_not_become_zero_or_wrong_cache_ratio(tmp_path):
    s = scope(
        tmp_path,
        [
            receipt(),
            dict(response_id="r2", timestamp=STAMP, usage=dict(input_tokens=900, output_tokens=10)),
        ],
    )
    r = build_report(s)
    assert tokens(r)["input_tokens"] == 1000
    assert tokens(r)["cached_input_tokens"] == 60
    assert tokens(r)["cache_rate"] == 0.6
    assert r["task_usage"]["cache_rate_input_coverage"] == 100
    assert r["usage_status"] == "partial"


@pytest.mark.parametrize("bad", [-1, 1.5, True, "42"])
def test_invalid_numbers_keep_known_subtotals(tmp_path, bad):
    s = scope(tmp_path, [{**receipt(), "usage": {**usage(), "input_tokens": bad}}])
    r = build_report(s)
    assert tokens(r)["input_tokens"] is None
    assert tokens(r)["output_tokens"] == 20
    assert r["limitations"][0]["code"] == "invalid_usage"


def test_subset_checks_and_zero_input(tmp_path):
    s = scope(tmp_path, [{**receipt(), "usage": usage(0, 0, 0, 0)}])
    assert tokens(build_report(s))["cache_rate"] is None
    (tmp_path / "receipts.jsonl").write_text(
        json.dumps({**receipt(), "usage": usage(10, 11, 2, 3)}) + "\n"
    )
    r = build_report(s)
    assert tokens(r)["cached_input_tokens"] is None
    assert tokens(r)["reasoning_output_tokens"] is None


def test_broken_lines_byte_ranges_and_frozen_prefix(tmp_path):
    s = scope(tmp_path)
    path = tmp_path / "receipts.jsonl"
    original = path.read_bytes()
    path.write_bytes(original + b'broken\n{"truncated":')
    r = build_report(s)
    assert tokens(r)["input_tokens"] == 100
    assert {x["code"] for x in r["limitations"]} >= {"invalid_json_line", "truncated_line"}
    assert r["limitations"][0]["source"]["byte_offset"] == len(original)
    s["sources"][0]["byte_length"] = len(original)
    r = build_report(s)
    assert r["sources"][0]["sha256"] == hashlib.sha256(original).hexdigest()
    path.write_bytes(path.read_bytes() + b"more")
    assert build_report(s) == r


def test_cumulative_resume_difference_and_partial_rollout_not_added(tmp_path):
    s = scope(tmp_path, [{**receipt(), "usage": usage(500, 300, 100, 20)}])
    segment = dict(
        id="segment-1",
        evidence_ref="start-end-receipts",
        start=START,
        end=END,
        baseline=usage(1000, 600, 200, 40),
        includes_response_ids=["r1"],
    )
    add_source(
        s,
        tmp_path,
        "total",
        [
            dict(
                timestamp=STAMP,
                source_mode="thread_cumulative",
                thread_id="thread-a",
                usage=usage(1800, 1000, 350, 80),
            )
        ],
        cumulative_segment=segment,
    )
    r = build_report(s)
    assert tokens(r)["input_tokens"] == 800
    assert r["cost_units"][0]["unitemized_residual"]["input_tokens"] == 300
    assert r["responses"][0]["usage"]["input_tokens"] == 500
    assert tokens(build_report(s))["input_tokens"] == 800
    del s["bindings"][1]["cumulative_segment"]["includes_response_ids"]
    assert tokens(build_report(s))["input_tokens"] == 500
    assert any(x["code"] == "cumulative_overlap_unproven" for x in build_report(s)["limitations"])


def test_cumulative_reset_and_no_baseline_are_unknown(tmp_path):
    s = scope(tmp_path)
    segment = dict(
        id="s",
        evidence_ref="baseline",
        start=START,
        end=END,
        baseline=usage(1000, 600, 200, 40),
        includes_response_ids=["r1"],
    )
    add_source(
        s,
        tmp_path,
        "total",
        [
            dict(
                timestamp=STAMP,
                source_mode="thread_cumulative",
                thread_id="thread-a",
                usage=usage(900, 650, 250, 50),
            )
        ],
        cumulative_segment=segment,
    )
    r = build_report(s)
    assert tokens(r)["input_tokens"] is None
    assert any(x["code"] == "cumulative_reset" for x in r["limitations"])
    s["bindings"][1].pop("cumulative_segment")
    r = build_report(s)
    assert tokens(r)["input_tokens"] == 100
    assert len(r["observed_thread_totals"]) == 1


def test_rollout_compaction_only_real_id_is_subset(tmp_path):
    s = scope(tmp_path)
    add_source(
        s,
        tmp_path,
        "rollout",
        [
            dict(type="session_meta", payload=dict(id="thread-a")),
            dict(
                type="token_usage_record",
                timestamp=STAMP,
                payload=dict(response_id="r1", usage=usage()),
            ),
            dict(type="compacted", payload=dict(compaction_response_id="r1")),
            dict(type="compacted", payload={}),
        ],
        "rollout",
    )
    r = build_report(s)
    assert tokens(r)["input_tokens"] == 100
    assert r["compaction_subset"]["tokens"]["input_tokens"] == 100
    assert r["compaction_subset"]["additive"] is False
    assert any(x["code"] == "compaction_binding_unknown" for x in r["limitations"])


def test_other_task_shared_thread_and_unallocated_not_guessed(tmp_path):
    s = scope(tmp_path)
    add_source(s, tmp_path, "other", [receipt("r2")], task_ref="other-task", role="judge")
    add_source(s, tmp_path, "unknown", [receipt("r3")], task_ref=None, role=None)
    bill(s)
    s["billing_scope"]["vendor_usage"] = usage(300, 180, 60, 15)
    r = build_report(s)
    assert tokens(r)["input_tokens"] == 100
    assert r["billing_window_usage"]["categories"]["other_task"]["tokens"]["input_tokens"] == 100
    assert r["billing_status"] == "MATCHED"
    assert r["reconciliation"]["attribution_status"] == "partial"


@pytest.mark.parametrize("delta", [-10, 0, 10])
def test_billing_signed_difference_and_missing_timezone(tmp_path, delta):
    s = scope(tmp_path)
    bill(s)
    s["billing_scope"]["vendor_usage"]["input_tokens"] += delta
    r = build_report(s)
    assert r["reconciliation"]["tokens"]["input_tokens"]["difference"] == delta
    assert r["billing_status"] == ("MATCHED" if delta == 0 else "MISMATCH")
    s["billing_scope"].pop("timezone")
    r = build_report(s)
    assert r["billing_status"] == "PARTIAL"
    assert r["reconciliation"]["tokens"]["input_tokens"]["raw_difference"] == delta


def test_half_open_window_and_different_time_basis(tmp_path):
    s = scope(tmp_path, [receipt(), {**receipt("boundary"), "timestamp": END}])
    bill(s)
    r = build_report(s)
    assert r["reconciliation"]["tokens"]["input_tokens"]["difference"] == 0
    s["billing_scope"]["time_basis"] = "request_start"
    r = build_report(s)
    assert r["billing_status"] == "PARTIAL"
    assert r["billing_window_usage"]["boundary_unknown"] == 2


def test_prices_are_explicit_versioned_decimal_and_subscription_unknown(tmp_path):
    s = scope(tmp_path)
    assert build_report(s)["cost_estimates"][0]["amount"] is None
    s["price_versions"] = [
        dict(
            provider="provider-a",
            model="model-a",
            source_ref="price-sheet",
            version="2026-10",
            verified_at=START,
            currency="USD",
            unit_tokens=1000,
            start=START,
            end=END,
            definition_ref="input-includes-cache",
            billing_mode="api",
            rates=dict(cached_input_tokens="0.1", uncached_input_tokens="1", output_tokens="2"),
        )
    ]
    cost = build_report(s)["cost_estimates"][0]
    assert cost["amount"] == "0.086"
    s["price_versions"][0]["billing_mode"] = "subscription"
    assert build_report(s)["cost_estimates"][0]["amount"] is None


def timing(rid, start, end, **extra):
    return dict(
        provider="provider-a",
        key_ref="key-A",
        response_id=rid,
        kind="request_completion",
        start=f"2026-10-14T01:00:{start:02d}+00:00",
        end=f"2026-10-14T01:00:{end:02d}+00:00",
        clock_ref="host-utc",
        start_source="wire-send",
        end_source="usage-terminal",
        status="completed",
        binding_evidence_ref="response-request-binding",
        **extra,
    )


def test_throughput_weighted_parallel_and_unknown_not_ttft(tmp_path):
    s = scope(tmp_path, [receipt(), receipt("r2"), receipt("r3")])
    add_source(
        s,
        tmp_path,
        "timing",
        [
            timing("r1", 0, 10),
            timing("r2", 5, 15),
            {**timing("r3", 20, 30), "binding_evidence_ref": None},
        ],
        "timing",
    )
    r = build_report(s)
    metric = r["timing_metrics"]["metrics"][0]
    assert metric["weighted_rate"] == 2
    assert metric["parallel_union_rate"] == pytest.approx(40 / 15)
    assert metric["unknown"] == 1
    assert metric["output_coverage"] == pytest.approx(2 / 3)
    assert r["timing_metrics"]["metrics"][8]["weighted_rate"] is None
    assert r["timing_metrics"]["wall_clock_state"] == "elapsed_to_cutoff"


def test_unknown_layers_and_attempts_do_not_imply_free_calls(tmp_path):
    s = scope(tmp_path)
    s["layer_coverage"] = [
        dict(role="consumer", status="not_invoked", evidence_ref="operation-log"),
        dict(role="scoring", status="unknown", evidence_ref="reranker-invoked"),
    ]
    add_source(
        s,
        tmp_path,
        "attempt",
        [
            dict(
                event="attempt_start",
                request_id="req",
                attempt_index=1,
                start=STAMP,
                status="unfinished",
            )
        ],
        "capture",
    )
    bill(s)
    r = build_report(s)
    assert r["layers"][0]["status"] == "not_invoked"
    assert r["layers"][1]["tokens"]["input_tokens"] is None
    assert tokens(r)["input_tokens"] == 100
    assert r["billing_status"] == "PARTIAL"


def test_shared_response_attribution_conflict_never_selects_one_task(tmp_path):
    s = scope(tmp_path)
    add_source(s, tmp_path, "copy", [receipt()], task_ref="other")
    r = build_report(s)
    assert tokens(r)["input_tokens"] is None
    assert r["unallocated"]["tokens"]["input_tokens"] == 100


def test_reports_repeat_exactly_preserve_old_evidence_and_no_body(tmp_path):
    s = scope(
        tmp_path,
        [receipt(secret="do-not-retain", body="business-body", authorization="secret-key")],
    )
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(s))
    r = write_report(scope_path, tmp_path / "one")
    write_report(scope_path, tmp_path / "two")
    for name in ("report.json", "report.md"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    assert (tmp_path / "one" / "report.md").read_text() == render_markdown(r)
    assert "business-body" not in json.dumps(r)
    with pytest.raises(FileExistsError):
        write_report(scope_path, tmp_path / "one")
    invalid = copy.deepcopy(s)
    invalid["sources"][0]["path"] = "../outside.jsonl"
    with pytest.raises(ScopeError):
        build_report(invalid)


def test_shared_thread_without_slice_is_unallocated(tmp_path):
    s = scope(tmp_path)
    s["bindings"][0]["shared_thread"] = True
    r = build_report(s)
    assert tokens(r)["input_tokens"] is None
    assert r["unallocated"]["tokens"]["input_tokens"] == 100


def test_overlapping_cumulative_segments_cannot_double_count(tmp_path):
    s = scope(tmp_path)
    segment = dict(
        id="segment-1",
        evidence_ref="baseline",
        start=START,
        end=END,
        fresh_zero_baseline=True,
        includes_response_ids=["r1"],
    )
    add_source(
        s,
        tmp_path,
        "c1",
        [
            dict(
                timestamp=STAMP,
                source_mode="thread_cumulative",
                thread_id="thread-a",
                usage=usage(),
            )
        ],
        cumulative_segment=segment,
    )
    add_source(
        s,
        tmp_path,
        "c2",
        [
            dict(
                timestamp=STAMP,
                source_mode="thread_cumulative",
                thread_id="thread-a",
                usage=usage(),
            )
        ],
        cumulative_segment={**segment, "id": "segment-2"},
    )
    r = build_report(s)
    assert tokens(r)["input_tokens"] == 100
    assert any(x["code"] == "cumulative_segments_overlap" for x in r["limitations"])


def test_source_bad_structure_and_missing_source_do_not_drop_safe_values(tmp_path):
    s = scope(tmp_path)
    add_source(
        s, tmp_path, "bad", [dict(method="thread/tokenUsage/updated", params="bad")], "app_server"
    )
    s["sources"].append(dict(id="absent", root=str(tmp_path), path="absent.jsonl", kind="rollout"))
    r = build_report(s)
    assert tokens(r)["input_tokens"] == 100
    assert {x["code"] for x in r["limitations"]} >= {"invalid_source_record", "source_unavailable"}


def test_billing_different_usage_definitions_are_not_comparable(tmp_path):
    s = scope(tmp_path)
    bill(s)
    s["billing_scope"]["definition_ref"] = "input-excludes-cache"
    r = build_report(s)
    assert r["billing_status"] == "PARTIAL"
    assert r["billing_window_usage"]["boundary_unknown"] == 1


def test_request_start_billing_requires_real_time_binding(tmp_path):
    s = scope(
        tmp_path,
        [{**receipt(), "request_started_at": START, "billing_time_evidence_ref": "wire-binding"}],
    )
    bill(s)
    s["billing_scope"]["time_basis"] = "request_start"
    assert build_report(s)["billing_status"] == "MATCHED"


def test_timing_missing_for_known_response_is_counted_unknown(tmp_path):
    r = build_report(scope(tmp_path))
    unknown = r["timing_metrics"]["metrics"][3]
    assert unknown["status"] == "unknown"
    assert unknown["eligible"] == 1
    assert unknown["unknown"] == 1
    assert unknown["weighted_rate"] is None


def test_timing_conflict_does_not_pick_first_sample(tmp_path):
    s = scope(tmp_path)
    add_source(s, tmp_path, "timing", [timing("r1", 0, 10), timing("r1", 0, 20)], "timing")
    r = build_report(s)
    assert r["timing_metrics"]["metrics"][0]["weighted_rate"] is None


def test_billing_amount_and_token_states_are_separate(tmp_path):
    s = scope(tmp_path)
    bill(s)
    s["price_versions"] = [
        dict(
            provider="provider-a",
            model="model-a",
            source_ref="price",
            version="p1",
            verified_at=START,
            currency="USD",
            unit_tokens=100,
            start=START,
            end=END,
            definition_ref="definition",
            billing_mode="api",
            rates=dict(input_tokens="1", output_tokens="2"),
        )
    ]
    s["billing_scope"].update(vendor_amount="1.5", currency="USD")
    r = build_report(s)
    assert r["billing_status"] == "PARTIAL"
    assert r["reconciliation"]["token_status"] == "MATCHED"
    s["billing_scope"].update(amount_rule_ref="no-tax-no-discount-exact", price_version_refs=["p1"])
    r = build_report(s)
    assert r["billing_status"] == "MISMATCH"
    assert r["reconciliation"]["amount"]["difference"] == "0.1"


def test_numeric_billing_match_does_not_close_task_attribution(tmp_path):
    s = scope(tmp_path)
    add_source(s, tmp_path, "copy", [receipt()], task_ref="other-task")
    bill(s)
    r = build_report(s)
    assert r["reconciliation"]["token_status"] == "MATCHED"
    assert r["reconciliation"]["attribution_status"] == "partial"


def test_unbound_known_identity_keeps_usage_unallocated(tmp_path):
    s = scope(tmp_path, [{**receipt(), **IDENTITY}])
    s["bindings"] = []
    r = build_report(s)
    assert tokens(r)["input_tokens"] is None
    assert r["unallocated"]["tokens"]["input_tokens"] == 100


def test_unknown_timezone_and_overlapping_prices_stay_unknown(tmp_path):
    s = scope(tmp_path)
    bill(s)
    s["billing_scope"]["timezone"] = "unknown"
    assert build_report(s)["billing_status"] == "PARTIAL"
    price = dict(
        provider="provider-a",
        model="model-a",
        source_ref="price",
        version="p1",
        verified_at=START,
        currency="USD",
        unit_tokens=100,
        start=START,
        end=END,
        definition_ref="definition",
        billing_mode="api",
        rates=dict(input_tokens="1"),
    )
    s["price_versions"] = [price, {**price, "version": "p2"}]
    assert build_report(s)["cost_estimates"][0]["amount"] is None


def test_vendor_subset_violation_cannot_be_a_verified_mismatch(tmp_path):
    s = scope(tmp_path)
    bill(s)
    s["billing_scope"]["vendor_usage"]["cached_input_tokens"] = 101
    r = build_report(s)
    assert r["billing_status"] == "PARTIAL"
    assert r["reconciliation"]["tokens"]["cached_input_tokens"]["vendor"] is None


def test_report_retains_explicit_binding_and_scope_digest(tmp_path):
    s = scope(tmp_path)
    add_source(s, tmp_path, "copy", [receipt()])
    r = build_report(s)
    assert r["responses"][0]["binding_evidence_refs"] == ["binding", "session-receipt"]
    assert (
        r["scope"]["sha256"]
        == hashlib.sha256(json.dumps(s, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    )
