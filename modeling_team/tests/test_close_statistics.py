"""R4.3-036 numerical/closure counterexamples; no model or provider requests."""

import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.close_statistics import (
    ActivityRecorder,
    aggregate_activity,
    clock_stamp,
    publish_close_statistics,
    read_close_statistics,
    register_statistics_link,
)
from modeling_team.usage_report import build_report, write_report


def event(kind, stamp, **extra):
    return dict(
        event=kind,
        monotonic_ns=int(stamp * 1e9),
        clock_ref="test-clock",
        runtime="dsh",
        process_instance="p1",
        agent_id="modeling",
        runtime_session_id="s1",
        role="modeling",
        **extra,
    )


def statistics(events, members=None):
    scope = {
        "view": "run_close",
        "cutoff_at": "2026-10-19T00:01:00Z",
        "cutoff_clock": {"clock_ref": "test-clock", "monotonic_ns": 60_000_000_000},
        "members": members
        or [
            {
                "runtime": "dsh",
                "process_instance": "p1",
                "agent_id": "modeling",
                "runtime_session_id": "s1",
                "role": "modeling",
            }
        ],
    }
    usage = {
        "cost_units": [],
        "attempts": [],
        "limitations": [],
        "cost_summary": [],
        "compaction_subset": {},
    }
    return aggregate_activity(scope, usage, events)


def test_request_tool_overlap_and_parallel_tools_have_distinct_totals():
    rows = [
        event("launch", 0),
        event("llm_start", 0, call_id="r1"),
        event("llm_end", 20, call_id="r1", status="completed"),
        event("tool_start", 15, call_id="t1", tool_name="read"),
        event("tool_end", 25, call_id="t1", tool_name="read", status="completed"),
        event("exit", 60, status="completed"),
    ]
    result = statistics(rows)
    assert result["summary"]["llm_request_seconds"] == 20
    assert result["summary"]["tool_execution_seconds"] == 10
    assert result["summary"]["active_seconds"] == 25
    assert result["members"][0]["lifecycle_seconds"] == 60
    parallel = statistics(
        [
            event("launch", 0),
            *[
                row
                for call in ("a", "b")
                for row in (
                    event("tool_start", 5, call_id=call, tool_name="wait"),
                    event("tool_end", 15, call_id=call, tool_name="wait", status="completed"),
                )
            ],
            event("exit", 20, status="completed"),
        ]
    )
    assert parallel["summary"]["tool_execution_seconds"] == 20
    assert parallel["summary"]["active_seconds"] == 10


def test_nested_duplicate_rejected_and_failed_calls_are_not_added_twice():
    rows = [
        event("launch", 0),
        event("tool_start", 1, call_id="root", tool_name="read"),
        event("tool_start", 2, call_id="child", root_call_id="root", tool_name="nested"),
        event("tool_end", 4, call_id="child", root_call_id="root", status="completed"),
        event("tool_end", 6, call_id="root", tool_name="read", status="failed"),
        event("tool_rejected", 7, call_id="rejected", status="rejected"),
        event("exit", 10, status="completed"),
    ]
    result = statistics(rows + rows)
    member = result["members"][0]
    assert member["tool_execution_seconds"] == 5
    assert member["tools"]["executed"] == 1
    assert member["tools"]["failed"] == 1
    assert member["tools"]["rejected"] == 1


def test_unfinished_clock_gaps_and_live_delivery_never_become_zero_or_closed():
    result = statistics(
        [
            event("launch", 2),
            event("llm_start", 10, call_id="failed-no-usage"),
            {**event("tool_start", 15, call_id="t"), "clock_ref": "other"},
            event("tool_end", 20, call_id="t", status="completed"),
        ]
    )
    member = result["members"][0]
    assert member["lifecycle_seconds"] is None
    assert member["elapsed_to_cutoff_seconds"] == 58
    assert member["llm_request_seconds"] is None
    assert member["llm"]["unfinished"] == 1
    assert member["llm"]["unfinished_elapsed_seconds"] == 50
    assert member["tool_execution_seconds"] is None
    assert member["active_seconds"] is None
    assert result["closure_status"] != "closed"
    assert member["usage"]["tokens"]["input_tokens"] is None


def test_linux_node_python_monotonic_clock_is_shared():
    before = time.monotonic_ns()
    node = int(
        subprocess.check_output(
            ["node", "-e", "process.stdout.write(String(process.hrtime.bigint()))"]
        )
    )
    after = time.monotonic_ns()
    assert before <= node <= after
    assert clock_stamp()["clock_ref"].startswith("linux-monotonic:")


def test_automatic_report_is_frozen_replayable_private_and_versioned(tmp_path):
    recorder = ActivityRecorder(
        tmp_path,
        {
            "runtime": "codex",
            "agent_id": "delivery",
            "role": "delivery",
            "task_ref": "task-a",
            "session_id": "business-a",
        },
        usage_sources=[{"path": str(tmp_path / "numeric.jsonl"), "kind": "capture"}],
        fresh_session=True,
    )
    recorder.bind("thread-a")
    (tmp_path / "numeric.jsonl").write_text(
        json.dumps(
            {
                "event": "thread_usage",
                "runtime": "codex",
                "runtime_session_id": "thread-a",
                "thread_id": "thread-a",
                "process_instance": recorder.context["process_instance"],
                "received_at": recorder.started_at,
                "total": {
                    "input_tokens": 100,
                    "cached_input_tokens": 40,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 5,
                },
            }
        )
        + "\n"
    )
    recorder.emit("tool_start", call_id="a", tool_name="read", arguments="SECRET")
    recorder.emit("tool_end", call_id="a", tool_name="read", status="completed", result="SECRET")
    recorder.exit(0)
    first = publish_close_statistics(tmp_path, view="task_close", task_ref="task-a")
    assert first["report_status"] == "ready"
    assert first["closure_status"] == "closed"
    report = json.loads((tmp_path / first["report_ref"]).read_text())
    assert first["summary"]["input_tokens"] == 100
    assert "SECRET" not in json.dumps(report)
    assert (tmp_path / first["markdown_ref"]).exists()
    assert read_close_statistics(tmp_path) == first
    assert publish_close_statistics(tmp_path, view="task_close", task_ref="task-a") == first
    frozen = tmp_path / first["scope_ref"]
    replay = write_report(frozen, tmp_path / "replay")
    assert replay["close_statistics"] == report["close_statistics"]
    old = (tmp_path / first["report_ref"]).read_bytes()
    recorder.emit("capture_gap", status="unknown")
    second = publish_close_statistics(tmp_path, view="task_close", task_ref="task-a")
    assert second["report_ref"] != first["report_ref"]
    assert second["previous_report_ref"] == first["report_ref"]
    assert (tmp_path / first["report_ref"]).read_bytes() == old


def test_phase_threads_keep_all_usage_without_duplicating_process_lifetime(tmp_path):
    source = tmp_path / "numeric.jsonl"
    recorder = ActivityRecorder(tmp_path, {"runtime": "codex", "agent_id": "delivery",
        "role": "delivery", "task_ref": "task"},
        usage_sources=[{"path": str(source), "kind": "capture"}], fresh_session=True)
    rows = []
    for thread_id, amount in [("old-phase", 100), ("new-phase", 200)]:
        recorder.bind(thread_id)
        rows.append({"event": "thread_usage", "runtime": "codex",
            "runtime_session_id": thread_id, "thread_id": thread_id,
            "process_instance": recorder.context["process_instance"],
            "received_at": recorder.started_at,
            "total": {"input_tokens": amount, "cached_input_tokens": 0, "output_tokens": 10}})
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    recorder.exit(0)
    result = publish_close_statistics(tmp_path, view="task_close", task_ref="task")
    assert result["summary"]["input_tokens"] == 300
    report = json.loads((tmp_path / result["report_ref"]).read_text())
    members = report["close_statistics"]["members"]
    assert len(members) == 1
    assert set(members[0]["runtime_session_ids"]) == {"old-phase", "new-phase"}
    assert members[0]["usage"]["tokens"]["input_tokens"] == 300
    replay = write_report(tmp_path / result["scope_ref"], tmp_path / "replay")
    assert replay["close_statistics"] == report["close_statistics"]


def test_report_failure_does_not_change_cleanup_or_publish_half_ready(tmp_path, monkeypatch):
    recorder = ActivityRecorder(tmp_path, {"runtime": "dsh", "agent_id": "a"})
    recorder.exit(0)
    import modeling_team.usage_report as reports

    monkeypatch.setattr(
        reports, "render_markdown", lambda _: (_ for _ in ()).throw(OSError("secret"))
    )
    result = publish_close_statistics(tmp_path, view="run_close", task_ref="task")
    assert result["report_status"] == "unavailable"
    assert "secret" not in json.dumps(result)
    assert not list((tmp_path / "evidence/close-statistics").glob("report-*/report.json"))


def test_explicit_links_include_finished_children_without_directory_guessing(tmp_path):
    child = tmp_path / "known-child"
    recorder = ActivityRecorder(child, {"runtime": "dsh", "agent_id": "judge", "role": "judge"})
    recorder.exit(0)
    register_statistics_link(tmp_path, child, "operation-member-ledger")
    result = publish_close_statistics(tmp_path, view="operation_close", task_ref="task")
    report = json.loads((tmp_path / result["report_ref"]).read_text())
    assert len(report["close_statistics"]["members"]) == 1
    assert read_close_statistics(tmp_path / "hard-killed")["closure_status"] == "unknown"


def test_old_scope_stays_compatible(tmp_path):
    report = build_report(
        {"schema_version": "model-usage-scope/v1", "task_ref": "old", "sources": []}
    )
    assert "close_statistics" not in report


def test_resumed_session_lifecycle_excludes_offline_gap_and_team_time_is_union():
    first = {
        "runtime": "dsh",
        "agent_id": "modeling",
        "role": "modeling",
        "runtime_session_id": "s1",
        "process_instance": "p1",
    }
    second = {**first, "process_instance": "p2"}
    rows = [
        event("launch", 0),
        event("exit", 10, status="completed"),
        {**event("launch", 30), "process_instance": "p2"},
        {**event("exit", 50, status="completed"), "process_instance": "p2"},
    ]
    value = statistics(rows, [first, second])
    assert value["sessions"][0]["lifecycle_seconds"] == 30
    assert value["sessions"][0]["launch_to_last_exit_span_seconds"] == 50
    assert value["sessions"][0]["offline_gap_seconds"] == 20
    parallel = [
        event("launch", 0),
        event("tool_start", 1, call_id="t"),
        event("tool_end", 11, call_id="t", status="completed"),
        event("exit", 20),
    ]
    both = statistics(
        parallel + [{**r, "process_instance": "p2"} for r in parallel], [first, second]
    )
    assert both["summary"]["active_seconds"] == 20
    assert both["team_active_seconds"] == 10


def test_attempt_retries_without_usage_are_counted_independently_of_tokens():
    from modeling_team.close_statistics import aggregate_activity

    attempts = []
    for attempt, start, end, outcome in [(1, 1, 6, "transport_error"), (2, 8, 18, "completed")]:
        base = {
            "runtime": "dsh",
            "process_instance": "p1",
            "agent_id": "modeling",
            "runtime_session_id": "s1",
            "proxy_session_id": "proxy",
            "request_id": "r",
            "attempt_index": attempt,
            "monotonic_start_ns": start * 1_000_000_000,
            "clock_ref": "test-clock",
            "purpose": "compaction",
        }
        attempts.extend(
            [
                {**base, "event": "attempt_start", "status": "unfinished"},
                {
                    **base,
                    "event": "attempt_end",
                    "monotonic_end_ns": end * 1_000_000_000,
                    "status": outcome,
                },
            ]
        )
    config = {
        "view": "run_close",
        "members": [
            {
                "runtime": "dsh",
                "process_instance": "p1",
                "agent_id": "modeling",
                "runtime_session_id": "s1",
            }
        ],
    }
    value = aggregate_activity(
        config,
        {"cost_units": [], "attempts": attempts + attempts},
        [event("launch", 0), event("exit", 30)],
    )
    member = value["members"][0]
    assert member["llm_request_seconds"] == 15
    assert member["llm"]["logical_requests"] == 1
    assert member["llm"]["executed"] == 2
    assert member["llm"]["failed"] == 1
    assert member["llm"]["compaction_requests"] == 1
    assert member["usage"]["tokens"]["input_tokens"] is None


def test_not_admitted_attempt_is_not_projected_as_llm_interval():
    from modeling_team.close_statistics import aggregate_activity

    attempt = {
        "runtime": "dsh",
        "process_instance": "p1",
        "agent_id": "modeling",
        "runtime_session_id": "s1",
        "proxy_session_id": "proxy",
        "request_id": "denied",
        "attempt_index": 1,
        "event": "attempt_end",
        "status": "not_admitted",
        "clock_ref": "test-clock",
        "monotonic_end_ns": 5_000_000_000,
    }
    value = aggregate_activity(
        {
            "view": "run_close",
            "members": [{
                "runtime": "dsh",
                "process_instance": "p1",
                "agent_id": "modeling",
                "runtime_session_id": "s1",
            }],
        },
        {"cost_units": [], "attempts": [attempt]},
        [event("launch", 0), event("exit", 10, status="completed")],
    )
    assert value["members"][0]["llm"]["logical_requests"] == 0
    assert value["members"][0]["llm"]["executed"] == 0


@pytest.mark.parametrize(
    "change,code",
    [
        ({"monotonic_ns": -1}, "monotonic_boundary_missing"),
        ({"monotonic_ns": 0}, "clock_reversed"),
        ({"clock_ref": "another-boot"}, "clock_incomparable"),
    ],
)
def test_bad_time_boundaries_have_located_unknowns(change, code):
    value = statistics(
        [
            event("launch", 0),
            event("tool_start", 10, call_id="t"),
            {**event("tool_end", 20, call_id="t"), **change},
            event("exit", 30),
        ]
    )
    assert value["summary"]["tool_execution_seconds"] is None
    assert code in value["members"][0]["limitations"]


def test_capture_failure_preserves_callback_result_and_original_exception(tmp_path, monkeypatch):
    recorder = ActivityRecorder(tmp_path, {"runtime": "codex", "agent_id": "a"})
    import modeling_team.close_statistics as capture

    monkeypatch.setattr(
        capture.os, "open", lambda *a, **kw: (_ for _ in ()).throw(OSError("private"))
    )
    result = object()
    assert recorder.execute_tool("a", "read", lambda: result) is result
    error = RuntimeError("original-error")
    with pytest.raises(RuntimeError) as caught:
        recorder.execute_tool("b", "read", lambda: (_ for _ in ()).throw(error))
    assert caught.value is error


def test_original_run_status_and_receipt_only_read_published_report(tmp_path, monkeypatch):
    from modeling_team import host_ops
    from modeling_team.tests.test_host_ops import _make_run, _append_evidence, _set_state

    repo, root = _make_run(tmp_path)
    recorder = ActivityRecorder(root, {"runtime": "dsh", "agent_id": "a"})
    recorder.exit(0)
    ready = publish_close_statistics(root, view="run_close", task_ref="task")
    _set_state(root, "CLEANED")
    _append_evidence(
        root,
        "outer-input-receipts",
        [{"request_id": "r436-stop", "action": "stop", "outcome": "accepted"}],
    )
    before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    import modeling_team.close_statistics as reports

    monkeypatch.setattr(
        reports,
        "publish_close_statistics",
        lambda *a, **kw: pytest.fail("query regenerated statistics"),
    )
    assert host_ops.get_run_status(root.name, repository_root=repo)["close_statistics"] == ready
    receipt = host_ops.get_request_result(root.name, request_id="r436-stop", repository_root=repo)
    assert receipt["outcome"] == "accepted" and receipt["close_statistics"] == ready
    assert before == {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_owner_includes_a_child_that_finished_before_final_close(tmp_path):
    from modeling_team.evaluation_owner import EvaluationOwner

    owner = EvaluationOwner(tmp_path / "operation.owner")
    child_root = tmp_path / "child"
    recorder = ActivityRecorder(
        child_root, {"runtime": "dsh", "agent_id": "judge", "role": "judge"}
    )
    recorder.bind("native-judge")
    resource = SimpleNamespace(
        statistics_root=child_root,
        spec={"v3_role": "judge"},
        thread_id=None,
        runtime="dsh",
        identity=recorder.context,
        report_sink=None,
        process=SimpleNamespace(pid=None, poll=lambda: None),
    )
    owner.bind(SimpleNamespace(), resource)
    recorder.exit(0)
    owner.release(resource)
    owner.close()
    value = read_close_statistics(owner.root)
    assert value["report_status"] == "ready" and value["closure_status"] == "closed"
    assert (
        json.loads((owner.root / value["report_ref"]).read_text())["close_statistics"]["members"][
            0
        ]["role"]
        == "judge"
    )


def test_delivery_statistics_follow_runtime_exit_and_preserve_control_state(tmp_path):
    from modeling_team.delivery import _publish_delivery_statistics
    from modeling_team.tests.test_delivery_session import session

    host = session(tmp_path)
    recorder = ActivityRecorder(
        host.session_root, {"runtime": "codex", "role": "delivery", "agent_id": "delivery"}
    )
    host.activity = "stopped"
    host._save("stopped")
    assert (
        json.loads((host.session_root / "session.json").read_text())["close_statistics"][
            "report_status"
        ]
        == "pending"
    )
    recorder.exit(0)
    host._append("session-events.jsonl", {"event": "native_runtime_closed"})
    _publish_delivery_statistics(host)
    state = json.loads((host.session_root / "session.json").read_text())
    assert state["state"] == "stopped" and state["close_statistics"]["report_status"] == "ready"
    events = [
        json.loads(line)
        for line in (host.session_root / "session-events.jsonl").read_text().splitlines()
    ]
    assert next(
        i for i, e in enumerate(events) if e.get("event") == "native_runtime_closed"
    ) < next(i for i, e in enumerate(events) if e.get("event") == "close_statistics_ready")


def test_pinned_tools_execute_observer_measures_completion_before_ordered_results():
    from modeling_team.runtimes.dsh_build import freeze_build

    root = Path(__file__).resolve().parents[2]
    build = freeze_build(Path("/home/yangxiang/deepseek-harness"))
    context = Path(build["modules"]["@deepseek-ai/cordis"]).as_uri()
    tools = Path(build["modules"]["@deepseek-ai/dsh-tools"]).as_uri()
    prompt = Path(build["modules"]["@deepseek-ai/dsh-system-prompt"]).as_uri()
    observer = (root / "modeling_team/runtimes/dsh_node/activity.mjs").as_uri()
    script = f"""
      import {{Context}} from {json.dumps(context)};
      import tools from {json.dumps(tools)};
      import prompt from {json.dumps(prompt)};
      import {{observeActivity}} from {json.dumps(observer)};
      const ctx = new Context(); await ctx.plugin(prompt); await ctx.plugin(tools, {{mode:'native'}});
      const rows = []; observeActivity(ctx, {{clockRef:'test-clock'}}, row => rows.push(row.params));
      ctx.tools.register({{name:'probe', description:'test', parameters:{{type:'object'}},
        output:{{schema:{{}}, render:(_a,v)=>[{{type:'text',text:JSON.stringify(v)}}]}},
        execute: async args => {{ await new Promise(resolve=>setTimeout(resolve,args.ms)); return args; }} }});
      ctx.tools.guard(exec => exec.callId === 'blocked' ? 'denied' : undefined);
      const call = (id, ms) => ctx.tools.execute({{signal:new AbortController().signal,
        callId:id, name:'probe', arguments:{{ms}}}});
      const results = await Promise.all([call('long',80), call('short',5), call('blocked',0)]);
      await ctx.fiber.dispose(); process.stdout.write(JSON.stringify({{rows,results}}));
    """
    result = json.loads(
        subprocess.check_output(
            ["node", "--input-type=module", "-e", script], text=True, timeout=15
        )
    )
    ends = {r["call_id"]: r for r in result["rows"] if r["event"] == "tool_end"}
    assert int(ends["short"]["monotonic_ns"]) < int(ends["long"]["monotonic_ns"])
    assert "blocked" not in ends
    assert any(r["call_id"] == "blocked" and r["event"] == "tool_rejected" for r in result["rows"])
    assert result["results"][0]["value"] == {"ms": 80}
    assert result["results"][2]["isError"] is True


def test_shared_proxy_source_uses_explicit_session_binding_not_nearby_requests(tmp_path):
    source = tmp_path / "shared.jsonl"
    records = []
    for session, request, end in [("owned-adapter", "mine", 4), ("other-operation", "other", 44)]:
        base = dict(
            session_id=session,
            request_id=request,
            proxy_session_id="proxy",
            attempt_index=1,
            runtime="codex",
            clock_ref=clock_stamp()["clock_ref"],
            monotonic_start_ns=1_000_000_000,
        )
        records.extend(
            [
                {**base, "event": "attempt_start"},
                {
                    **base,
                    "event": "attempt_end",
                    "monotonic_end_ns": end * 1_000_000_000,
                    "status": "completed",
                },
            ]
        )
    source.write_text("".join(json.dumps(r) + "\n" for r in records))
    recorder = ActivityRecorder(
        tmp_path,
        {"runtime": "codex", "agent_id": "a"},
        usage_sources=[
            {
                "path": str(source),
                "kind": "capture",
                "shared": True,
                "capture_session_id": "owned-adapter",
            }
        ],
    )
    recorder.exit(0)
    ready = publish_close_statistics(tmp_path, view="run_close", task_ref="task")
    report = json.loads((tmp_path / ready["report_ref"]).read_text())
    assert {row["request_id"] for row in report["attempts"]} == {"mine"}
    assert report["close_statistics"]["unallocated_llm_activity"]["llm_request_seconds"] == 3
    assert report["close_statistics"]["members"][0]["llm_request_seconds"] is None


def test_still_running_delivery_is_only_task_cutoff_context_for_run_close(tmp_path):
    run, delivery = tmp_path / "run", tmp_path / "delivery"
    running = ActivityRecorder(
        delivery, {"runtime": "codex", "agent_id": "delivery", "role": "delivery"}
    )
    owned = ActivityRecorder(run, {"runtime": "dsh", "agent_id": "modeling", "role": "modeling"})
    owned.exit(0)
    (run / "control").mkdir()
    (run / "control/host-supervisor.json").write_text(
        json.dumps({"session_ref": str(delivery / "session.json")})
    )
    ready = publish_close_statistics(run, view="run_close", task_ref="task")
    assert ready["closure_status"] == "closed"
    report = json.loads((run / ready["report_ref"]).read_text())["close_statistics"]
    assert len(report["members"]) == 1 and report["members"][0]["role"] == "modeling"
    context = report["task_cutoff_members"][0]
    assert context["process_instance"] == running.context["process_instance"]
    assert context["lifecycle_seconds"] is None and context["closure_status"] == "closing"
    assert "delivery_still_running" in ready["limitations"]


def test_runner_cleanup_failure_keeps_first_exception_and_publishes_incomplete(
    tmp_path, monkeypatch
):
    from modeling_team.runner import TeamRunner

    runner = TeamRunner(repository_root=tmp_path, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(
        root=tmp_path / "run", configuration=SimpleNamespace(task=SimpleNamespace(task_id="task"))
    )
    recorder = ActivityRecorder(runner.run.root, {"runtime": "dsh", "agent_id": "a"})
    recorder.exit(0)
    original = RuntimeError("original cleanup layer")
    monkeypatch.setattr(runner, "_cleanup_resources", lambda: (_ for _ in ()).throw(original))
    with pytest.raises(RuntimeError) as caught:
        runner.cleanup()
    assert caught.value is original
    assert read_close_statistics(runner.run.root)["closure_status"] == "incomplete"


def test_runner_cleanup_cache_reuses_one_published_close_report(tmp_path):
    from modeling_team.tests.test_host_ops_s2 import _PreparedRun

    prepared = _PreparedRun(tmp_path)
    try:
        recorder = ActivityRecorder(prepared.root, {"runtime": "dsh", "agent_id": "a"})
        recorder.exit(0)
        first = prepared.runner.cleanup()
        assert first["close_statistics"]["report_status"] == "ready"
        second = prepared.runner.cleanup()
        assert second == first
        assert (
            len(list((prepared.root / "evidence/close-statistics").glob("report-*/report.json")))
            == 1
        )
    finally:
        prepared.cleanup()


def test_truncated_activity_and_failed_launch_retain_unknowns_without_body(tmp_path):
    recorder = ActivityRecorder(tmp_path, {"runtime": "dsh", "agent_id": "a"})
    recorder.exit(None, startup_failed=True)
    with recorder.path.open("a") as stream:
        stream.write('{"private":"BODY')
    ready = publish_close_statistics(tmp_path, view="run_close", task_ref="task")
    report = json.loads((tmp_path / ready["report_ref"]).read_text())
    member = report["close_statistics"]["members"][0]
    assert member["runtime_session_id"] is None
    assert member["exit_status"] == "startup_failed"
    assert "BODY" not in json.dumps(report)
    assert any(row["code"] == "truncated_line" for row in report["limitations"])


def test_late_version_links_last_ready_report_across_a_report_failure(tmp_path, monkeypatch):
    recorder = ActivityRecorder(tmp_path, {"runtime": "dsh", "agent_id": "a"})
    recorder.exit(0)
    first = publish_close_statistics(tmp_path, view="run_close", task_ref="task")
    recorder.emit("capture_gap", status="unknown")
    import modeling_team.usage_report as reports

    render = reports.render_markdown
    monkeypatch.setattr(
        reports, "render_markdown", lambda _: (_ for _ in ()).throw(OSError("private"))
    )
    failed = publish_close_statistics(tmp_path, view="run_close", task_ref="task")
    assert (
        failed["report_status"] == "unavailable"
        and failed["previous_report_ref"] == first["report_ref"]
    )
    monkeypatch.setattr(reports, "render_markdown", render)
    second = publish_close_statistics(tmp_path, view="run_close", task_ref="task")
    assert second["previous_report_ref"] == first["report_ref"]


def test_unbound_failed_launches_are_distinct_and_lifecycle_conflicts_are_unknown():
    members = [
        {"runtime": "dsh", "agent_id": "modeling", "process_instance": p} for p in ("p1", "p2")
    ]
    rows = [
        {**event("launch", 0), "runtime_session_id": None},
        {**event("exit", 5, status="startup_failed"), "runtime_session_id": None},
        {**event("launch", 10), "process_instance": "p2", "runtime_session_id": None},
        {
            **event("exit", 15, status="startup_failed"),
            "process_instance": "p2",
            "runtime_session_id": None,
        },
    ]
    result = statistics(rows, members)
    assert len(result["sessions"]) == 2
    assert {row["unbound_process_instance"] for row in result["sessions"]} == {"p1", "p2"}
    assert all(row["runtime_session_id"] is None for row in result["sessions"])
    conflicted = statistics(rows + [{**rows[1], "monotonic_ns": 6_000_000_000}], members)
    assert conflicted["members"][0]["lifecycle_seconds"] is None
    assert "lifecycle_endpoint_conflict" in conflicted["members"][0]["limitations"]


def test_numeric_statistics_do_not_enter_default_run_progress_feed(tmp_path):
    from modeling_team import host_ops
    from modeling_team.tests.test_host_ops import _make_run
    from modeling_team.runtimes.codex import CodexRuntimeAdapter

    repo, root = _make_run(tmp_path)
    recorder = ActivityRecorder(root, {"runtime": "codex", "agent_id": "a"})
    recorder.bind("native-thread")
    recorder.emit("tool_start", call_id="a", tool_name="read")
    CodexRuntimeAdapter._capture_usage(
        SimpleNamespace(activity=recorder, thread_id="native-thread"),
        {
            "method": "thread/tokenUsage/updated",
            "params": {"threadId": "native-thread", "tokenUsage": {"total": {"inputTokens": 10}}},
        },
    )
    register_statistics_link(root, tmp_path / "child", "owned-child")
    assert host_ops.get_run_events(root.name, repository_root=repo)["events"] == []


def test_dsh_activity_notifications_are_not_copied_into_decision_wire(tmp_path, monkeypatch):
    from io import StringIO
    from modeling_team.runtimes.dsh import DshRuntimeAdapter, _DshAgent

    adapter = DshRuntimeAdapter(repository_root=tmp_path)
    adapter._closed = True
    agent = _DshAgent("a", SimpleNamespace(role="modeling"), tmp_path, "native")
    agent.activity = ActivityRecorder(tmp_path, {"runtime": "dsh", "agent_id": "a"})
    frame = {
        "jsonrpc": "2.0",
        "method": "host/activity",
        "params": {
            "sessionId": "native",
            "event": "tool_start",
            "call_id": "call",
            "tool_name": "read",
            **clock_stamp(),
        },
    }
    agent.process = SimpleNamespace(
        stdout=StringIO(json.dumps(frame) + "\n"), wait=lambda timeout: 0
    )
    wire = []
    monkeypatch.setattr(adapter, "_record", lambda name, value: wire.append((name, value)))
    adapter._pump(agent)
    assert not any(name == "wire" for name, _ in wire)
    assert any(
        json.loads(line)["event"] == "tool_start"
        for line in agent.activity.path.read_text().splitlines()
    )
