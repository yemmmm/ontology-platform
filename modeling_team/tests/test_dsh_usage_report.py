"""034 provider/native/Codex accounting, binding and price counterexamples."""

import json

import pytest

from modeling_team.dsh_usage import DSH_SEMANTICS
from modeling_team.usage_report import build_report, write_report
from modeling_team.tests.test_usage_report import scope, add_source, START, STAMP, END, bill

RAW = dict(
    input_tokens=40,
    cache_read_input_tokens=60,
    cache_creation_input_tokens=5,
    output_tokens=20,
    reasoning_tokens=3,
)
NATIVE = dict(
    inputTokens=40, cacheReadTokens=60, cacheWriteTokens=5, outputTokens=20, reasoningTokens=3
)


def provider(request="request-1", response="response-1", session="native-1", **extra):
    return dict(
        event="response_usage",
        runtime="dsh",
        runtime_session_id=session,
        provider="provider-a",
        key_ref="key-A",
        usage_definition_ref="provider-usage-definition",
        response_id=response,
        request_id=request,
        end=STAMP,
        start=START,
        status="completed",
        actual_model="model-a",
        usage_complete=True,
        binding_evidence_ref="host-registration",
        usage_semantics=DSH_SEMANTICS,
        raw_usage=RAW,
        purpose="assistant",
        **extra,
    )


def dsh_scope(tmp_path, rows=None):
    s = scope(tmp_path)
    s["sources"].clear()
    s["bindings"].clear()
    add_source(
        s,
        tmp_path,
        "dsh",
        rows or [provider()],
        kind="dsh_capture",
        thread_id=None,
        runtime="dsh",
        runtime_session_id="native-1",
    )
    return s


def native(seq, kind="assistant/message", usage=None, turn=1, step=1):
    return dict(
        type=kind,
        seq=seq,
        timestamp=STAMP,
        data=dict(
            turn=turn,
            step=step,
            usage=NATIVE if usage is None else usage,
            message={"text": "PRIVATE-BODY"},
        ),
    )


def add_native(s, tmp_path, rows, sid="native", session="native-1"):
    add_source(
        s,
        tmp_path,
        sid,
        rows,
        kind="dsh_native",
        thread_id=None,
        runtime="dsh",
        runtime_session_id=session,
    )
    s["sources"][-1]["runtime_session_id"] = session


def test_exclusive_buckets_copy_conflict_mixed_runtime_and_compression(tmp_path):
    rows = [provider(), provider("compact", "compact-response")]
    rows[1]["purpose"] = "compaction"
    rows[1]["status"] = "stream_error"
    rows[1]["usage_complete"] = False
    s = dsh_scope(tmp_path, rows)
    add_source(
        s,
        tmp_path,
        "copy",
        [provider()],
        kind="dsh_capture",
        thread_id=None,
        runtime="dsh",
        runtime_session_id="native-1",
    )
    add_source(
        s,
        tmp_path,
        "codex",
        [
            dict(
                response_id="codex-response",
                timestamp=STAMP,
                usage=dict(
                    input_tokens=100,
                    cached_input_tokens=60,
                    output_tokens=20,
                    reasoning_output_tokens=3,
                ),
            )
        ],
    )
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] == 310
    assert len(report["responses"]) == 3
    assert report["compaction_subset"]["tokens"]["input_tokens"] == 105
    assert report["compaction_subset"]["additive"] is False
    assert {row["identity"]["runtime"] for row in report["task_usage"]["groups"]} == {
        "dsh",
        "codex",
    }
    assert report["usage_status"] == "partial"


def test_native_replacement_retry_copies_and_provider_precedence(tmp_path):
    s = dsh_scope(tmp_path)
    events = [
        native(1, "assistant/attempt", {**NATIVE, "outputTokens": 7}),
        native(2),
        native(3, "llm/retry-started"),
        native(4),
        native(5, "compaction/summary"),
    ]
    add_native(s, tmp_path, events)
    add_native(s, tmp_path, events, sid="copy")
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] == 105
    check = report["dsh_native_comparisons"][0]
    assert check["native_assistant_usage"]["tokens"]["output_tokens"] == 40
    assert check["difference"]["output_tokens"] == -20
    assert "PRIVATE-BODY" not in json.dumps(report)
    # Without provider originals, ordinary retry and successful summary are a partial subtotal.
    s["sources"] = [row for row in s["sources"] if row["id"] != "dsh"]
    s["bindings"] = [row for row in s["bindings"] if row["source_id"] != "dsh"]
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] == 315
    assert report["compaction_subset"]["tokens"]["input_tokens"] == 105
    assert report["usage_status"] == "partial"
    bill(s)
    assert build_report(s)["billing_status"] == "PARTIAL"


@pytest.mark.parametrize(
    "missing", ["cache_creation_input_tokens", "input_tokens", "cache_read_input_tokens"]
)
def test_missing_input_bucket_does_not_derive_total(tmp_path, missing):
    s = dsh_scope(tmp_path, [provider()])
    path = tmp_path / "dsh.jsonl"
    value = json.loads(path.read_text())
    value["raw_usage"].pop(missing)
    path.write_text(json.dumps(value) + "\n")
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] is None
    assert report["usage_status"] == "partial"


def test_native_sessions_and_process_resume_never_share_history(tmp_path):
    s = dsh_scope(tmp_path)
    s["sources"].clear()
    s["bindings"].clear()
    # Same session across process generations and file copies counts once.
    add_native(s, tmp_path, [native(1)], sid="old")
    add_native(s, tmp_path, [native(1)], sid="restored")
    add_native(s, tmp_path, [native(1)], sid="new", session="native-2")
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] == 210
    assert len(report["dsh_native_comparisons"]) == 2
    assert all(row.get("thread_id") is None for row in report["cost_units"])


def test_shared_proxy_missing_binding_and_identity_conflict(tmp_path):
    s = dsh_scope(tmp_path, [provider(), provider("r2", "s2", session="unknown")])
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] == 105
    assert report["unallocated"]["tokens"]["input_tokens"] == 105
    s["bindings"][0]["usage_definition_ref"] = None
    path = tmp_path / "dsh.jsonl"
    path.write_text(
        "".join(json.dumps({**row, "usage_definition_ref": None}) + "\n" for row in [provider()])
    )
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] is None
    assert any(row["code"] == "dsh_definition_unknown" for row in report["limitations"])


def test_no_response_id_needs_real_registration_and_request_evidence(tmp_path):
    s = dsh_scope(tmp_path, [provider(response=None)])
    assert build_report(s)["task_usage"]["tokens"]["input_tokens"] == 105
    value = provider(response=None)
    value["binding_evidence_ref"] = None
    (tmp_path / "dsh.jsonl").write_text(json.dumps(value) + "\n")
    report = build_report(s)
    assert report["task_usage"]["cost_units"] == 0
    assert len(report["ambiguous_responses"]) == 1


def test_separate_cache_write_price_never_bills_twice_and_no_default_price(tmp_path):
    s = dsh_scope(tmp_path)
    assert build_report(s)["cost_estimates"][0]["amount"] is None
    s["price_versions"] = [
        dict(
            provider="provider-a",
            model="model-a",
            version="v1",
            source_ref="explicit-import",
            verified_at=STAMP,
            currency="USD",
            unit_tokens=1,
            start=START,
            end=END,
            definition_ref="provider-usage-definition",
            billing_mode="api",
            rates=dict(
                uncached_input_tokens="1",
                cached_input_tokens="0.1",
                cache_write_tokens="2",
                output_tokens="1",
            ),
        )
    ]
    cost = build_report(s)["cost_estimates"][0]
    assert cost["amount"] == "76.0"  # U40 + R6 + W10 + O20
    assert cost["charge_tokens"]["uncached_input_tokens"] == 40
    del s["price_versions"][0]["rates"]["cache_write_tokens"]
    assert build_report(s)["cost_estimates"][0]["amount"] == "71.0"  # U+W45 + R6 + O20


def test_same_response_numeric_conflict_and_definition_conflict_are_partial(tmp_path):
    s = dsh_scope(tmp_path, [provider(), {**provider(), "raw_usage": {**RAW, "input_tokens": 41}}])
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] is None
    assert report["task_usage"]["tokens"]["output_tokens"] == 20
    assert report["usage_status"] == "partial"


def test_native_seq_conflict_is_not_arbitrarily_selected(tmp_path):
    s = dsh_scope(tmp_path)
    s["sources"].clear()
    s["bindings"].clear()
    add_native(s, tmp_path, [native(1), native(1, usage={**NATIVE, "inputTokens": 41})])
    report = build_report(s)
    assert report["task_usage"]["cost_units"] == 0
    assert any(row["code"] == "dsh_native_seq_conflict" for row in report["limitations"])


def test_explicit_dsh_cumulative_delta_baseline_and_nonadditive_provider(tmp_path):
    s = dsh_scope(tmp_path)
    projection = dict(
        source_mode="dsh_assistant_cumulative",
        runtime="dsh",
        runtime_session_id="native-1",
        timestamp=STAMP,
        usage_semantics=DSH_SEMANTICS,
        raw_usage={
            **{key: value for key, value in NATIVE.items() if key != "inputTokens"},
            "uncachedInputTokens": 140,
        },
        actual_model="model-a",
    )
    add_source(
        s,
        tmp_path,
        "projection",
        [projection],
        kind="receipts",
        thread_id=None,
        runtime="dsh",
        runtime_session_id="native-1",
        cumulative_segment=dict(
            id="delta",
            evidence_ref="explicit-frozen-projection",
            start=START,
            end=END,
            baseline=dict(
                input_tokens=100,
                cached_input_tokens=0,
                cache_write_tokens=0,
                output_tokens=0,
                reasoning_output_tokens=0,
            ),
        ),
    )
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] == 105
    comparison = report["dsh_native_comparisons"][0]
    assert comparison["native_cumulative_delta"]["input_tokens"] == 105
    assert comparison["additive"] is False
    s["sources"] = [r for r in s["sources"] if r["id"] == "projection"]
    s["bindings"] = [r for r in s["bindings"] if r["source_id"] == "projection"]
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] == 105
    assert report["usage_status"] == "partial"
    del s["bindings"][0]["cumulative_segment"]
    report = build_report(s)
    assert report["task_usage"]["tokens"]["input_tokens"] is None
    assert len(report["observed_thread_totals"]) == 1


def test_numeric_native_wire_timestamp_stream_usage_and_report_repeatability(tmp_path):
    s = dsh_scope(tmp_path)
    wrapper = dict(
        process_instance="process-1",
        frame=dict(
            method="session.event",
            params=dict(
                sessionId="native-1",
                event=dict(
                    type="assistant/attempt",
                    seq=1,
                    time=1791939600000,
                    data=dict(
                        turn=1,
                        step=1,
                        stream=[
                            dict(type="chunk", time=1, chunk=dict(type="usage", usage=NATIVE)),
                            dict(type="text-chunks", texts=["PRIVATE-BODY"]),
                        ],
                    ),
                ),
            ),
        ),
    )
    add_native(s, tmp_path, [wrapper])
    source = tmp_path / "scope.json"
    source.write_text(json.dumps(s))
    original = (tmp_path / "native.jsonl").read_bytes()
    first = tmp_path / "report-1"
    second = tmp_path / "report-2"
    write_report(source, first)
    write_report(source, second)
    assert (first / "report.json").read_bytes() == (second / "report.json").read_bytes()
    assert (first / "report.md").read_bytes() == (second / "report.md").read_bytes()
    assert (tmp_path / "native.jsonl").read_bytes() == original
    assert "PRIVATE-BODY" not in (first / "report.json").read_text()
    assert "DSH native reconciliation" in (first / "report.md").read_text()


def test_unfinished_attempt_is_not_free_or_counted_twice(tmp_path):
    s = dsh_scope(tmp_path)
    path = tmp_path / "dsh.jsonl"
    with path.open("a") as output:
        for event_kind in ("attempt_start", "attempt_end"):
            output.write(
                json.dumps(
                    dict(
                        event=event_kind,
                        provider="provider-a",
                        key_ref="key-A",
                        runtime="dsh",
                        runtime_session_id="native-1",
                        request_id="no-usage",
                    )
                )
                + "\n"
            )
    report = build_report(s)
    assert report["dsh_unknown_attempts"] == 1
    assert report["usage_status"] == "partial"
    assert report["task_usage"]["tokens"]["input_tokens"] == 105


def test_capture_request_timing_never_invents_generation_timing(tmp_path):
    s = dsh_scope(tmp_path, [provider(headers_at="2026-10-14T00:30:00Z", clock_ref="host-utc")])
    report = build_report(s)
    timing = report["timing_metrics"]["metrics"]
    assert (
        next(r for r in timing if r["kind"] == "request_completion" and r["status"] == "completed")[
            "used"
        ]
        == 1
    )
    assert (
        next(r for r in timing if r["kind"] == "after_headers" and r["status"] == "completed")[
            "used"
        ]
        == 1
    )
    assert all(r["used"] == 0 for r in timing if r["kind"] == "generation")


@pytest.mark.parametrize("raw", [None, [], "PRIVATE-BODY", True])
def test_malformed_raw_usage_keeps_attempt_and_safe_unknown(tmp_path, raw):
    value = provider()
    value["raw_usage"] = raw
    s = dsh_scope(tmp_path, [value])
    report = build_report(s)
    assert len(report["responses"]) == 1
    assert report["task_usage"]["tokens"]["input_tokens"] is None
    assert report["usage_status"] == "partial"
    assert "PRIVATE-BODY" not in json.dumps(report)
    assert any(row["code"] == "dsh_raw_usage_invalid" for row in report["limitations"])
