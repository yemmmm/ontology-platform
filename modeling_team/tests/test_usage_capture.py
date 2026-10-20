"""Collection cannot alter runtime behavior or expose request content."""

import json
import os
import signal
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


from modeling_team.close_statistics import ActivityRecorder
from modeling_team.deepseek_provider_proxy import preflight_deepseek_credential
from modeling_team.model_routing import RoleModelBinding
from modeling_team.task_budget import TaskBudget, bind_budget
from modeling_team.usage_capture import NumericReceiptWriter
from modeling_team.tests.test_delivery_runtime import ROOT, _runtime
from modeling_team.model_routing import load_team_model_profile
from modeling_team.runtimes import delivery as delivery_module
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.runtimes.budget import runtime_budget
from modeling_team.runtimes.dsh_delivery import DSHDeliveryRuntime
from modeling_team.runtimes.dsh import DshRuntimeAdapter, _DshAgent


def _delivery_native_budget_fixture(tmp_path):
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "auth-a",
            "amount": "10",
            "prices": [{
                "provider": "route-a",
                "actual_model": "model-a",
                "cached_input_per_million": "0.2",
                "uncached_input_per_million": "2",
                "output_per_million": "8",
            }],
        },
    )
    binding = RoleModelBinding("delivery", "route-a", "model-a", "low", "low")
    runtime = delivery_module.DeliveryRuntime(
        binding=binding,
        home=tmp_path / "native",
        instructions="fixture",
        tools=[],
        tool_handler=lambda *_args, **_kwargs: {},
        usage_context={"session_id": "native-session"},
        budget=budget,
        budget_owner_id="delivery-owner",
    )
    runtime.home.mkdir(parents=True)
    runtime._budget = runtime_budget(
        tmp_path,
        "delivery-owner",
        binding=binding,
        runtime="codex",
        explicit=budget,
        role="delivery",
    )
    usage_path = runtime.home / "usage-events.jsonl"
    runtime._budget.register_source(usage_path, "capture")
    runtime.activity = ActivityRecorder(
        runtime.home.parent,
        {
            "runtime": "codex",
            "agent_id": "delivery",
            "role": "delivery",
            "provider": "route-a",
            "requested_model": "model-a",
            "process_instance": runtime.process_instance,
        },
        usage_sources=[{"path": usage_path, "kind": "capture"}],
        fresh_session=True,
        budget=budget,
        budget_owner_id="delivery-owner",
        budget_binding=binding,
        budget_runtime="codex",
    )
    runtime.thread_id = "thread-native"
    runtime.activity.bind(runtime.thread_id)
    runtime._usage_writer.context.update(runtime.activity.context)
    return runtime, budget


def test_numeric_whitelist_duplicate_notifications_and_failure(tmp_path, caplog):
    writer = NumericReceiptWriter(
        tmp_path / "usage.jsonl",
        {"session_id": "session", "role": "business-answerer", "secret": "DO_NOT_STORE"},
    )
    event = dict(
        event="thread_usage",
        thread_id="thread",
        turn_id="turn",
        total=dict(inputTokens=100, outputTokens=20, cachedInputTokens=110),
        body="DO_NOT_STORE",
        headers="DO_NOT_STORE",
        error="DO_NOT_STORE",
    )
    writer(event)
    writer(event)
    rows = [json.loads(line) for line in writer.path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["total"]["input_tokens"] == 100
    assert rows[0]["total"]["cached_input_tokens"] is None
    assert rows[0]["total"]["reasoning_output_tokens"] is None
    assert rows[0]["invalid_fields"] == ["cached_input_tokens"]
    assert "DO_NOT_STORE" not in writer.path.read_text()
    assert writer.path.stat().st_mode & 0o777 == 0o600
    broken = NumericReceiptWriter(tmp_path / "usage.jsonl" / "child")
    broken(event)
    assert "usage_capture_incomplete" in caplog.text
    assert "DO_NOT_STORE" not in caplog.text


def test_local_budget_denial_keeps_not_admitted_without_usage(tmp_path):
    writer = NumericReceiptWriter(tmp_path / "attempts.jsonl")
    writer({
        "event": "attempt_end",
        "request_id": "request-denied",
        "attempt_index": 1,
        "status": "not_admitted",
        "provider": "route-a",
        "raw_usage": {"input_tokens": 999},
    })
    row = json.loads((tmp_path / "attempts.jsonl").read_text())
    assert row["status"] == "not_admitted"
    assert "raw_usage" not in row


def test_delivery_usage_does_not_enter_observations_or_change_turn(tmp_path, caplog):
    runtime = _runtime(
        delivery_module,
        load_team_model_profile(ROOT, "openai-sol-medium"),
        tmp_path / "native",
        usage_context={
            "role": "business-answerer",
            "operation_id": "answer-operation",
            "session_id": "session",
        },
    )
    value = {
        "method": "thread/tokenUsage/updated",
        "params": {
            "threadId": "thread",
            "turnId": "turn",
            "business": "DO_NOT_STORE",
            "tokenUsage": {"total": {"inputTokens": 100, "outputTokens": 20}},
        },
    }
    runtime.busy = True
    runtime._handle(value)
    row = json.loads((runtime.home / "usage-events.jsonl").read_text())
    assert row["role"] == "business-answerer"
    assert row["operation_id"] == "answer-operation"
    assert row["requested_model"] == runtime.binding.model
    assert runtime.busy is True
    assert runtime._observations == []
    runtime._usage_writer = lambda _event: (_ for _ in ()).throw(RuntimeError("DO_NOT_STORE"))
    runtime._handle(value)
    assert runtime.busy is True
    assert caplog.messages[-1] == "usage_capture_incomplete"


def test_delivery_native_handler_marks_busy_turn_inflight_and_missing_usage(tmp_path):
    runtime, budget = _delivery_native_budget_fixture(tmp_path)
    runtime.busy = True
    runtime._handle({
        "method": "turn/started",
        "params": {
            "threadId": "thread-native",
            "turn": {"id": "turn-native", "status": "inProgress"},
        },
    })
    started_at = datetime.now(timezone.utc)
    inflight = budget.tick(now=started_at)
    assert inflight["inflight_count"] == 1

    runtime._handle({
        "method": "turn/completed",
        "params": {
            "threadId": "thread-native",
            "turn": {"id": "turn-native", "status": "completed"},
        },
    })
    late = budget.tick(now=started_at + timedelta(seconds=11))
    assert any(
        item.get("reason") == "metering_error"
        for item in late["pause_reasons"]
    )


def test_delivery_native_handler_token_usage_settles_the_same_turn(tmp_path):
    runtime, budget = _delivery_native_budget_fixture(tmp_path)
    runtime.busy = True
    runtime._handle({
        "method": "turn/started",
        "params": {
            "threadId": "thread-native",
            "turn": {"id": "turn-native", "status": "inProgress"},
        },
    })
    started_at = datetime.now(timezone.utc)
    assert budget.tick(now=started_at)["inflight_count"] == 1
    runtime._handle({
        "method": "thread/tokenUsage/updated",
        "params": {
            "threadId": "thread-native",
            "turnId": "turn-native",
            "tokenUsage": {
                "total": {
                    "inputTokens": 1_100_000,
                    "cachedInputTokens": 1_000_000,
                    "outputTokens": 10_000,
                }
            },
        },
    })
    runtime._handle({
        "method": "turn/completed",
        "params": {
            "threadId": "thread-native",
            "turn": {"id": "turn-native", "status": "completed"},
        },
    })
    settled = budget.tick(now=started_at + timedelta(seconds=1))
    assert settled["charged_estimate"] == "0.48"
    assert settled["inflight_count"] == 0


def test_runtime_budget_initializes_source_once_and_keeps_later_deletion_visible(tmp_path):
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "auth-a",
            "amount": "1",
            "prices": [],
        },
    )
    member = runtime_budget(
        tmp_path,
        "delivery-owner",
        binding=RoleModelBinding("delivery", "route-a", "model-a", "low", "low"),
        runtime="codex",
        explicit=budget,
        role="delivery",
    )
    source = tmp_path / "evidence" / "owned-receipts.jsonl"
    member.register_source(source, "capture")
    assert source.exists()
    assert source.read_text(encoding="utf-8") == ""
    source.unlink()
    # A later lifecycle refresh must not recreate a source that disappeared.
    member.register_source(source, "capture")
    assert not source.exists()
    state = budget.tick(now=datetime.now(timezone.utc) + timedelta(seconds=11))
    assert any(
        item.get("reason") == "metering_error"
        for item in state["pause_reasons"]
    )


def test_codex_production_and_standalone_keep_numeric_attempt_receipts(tmp_path):
    runtime = CodexRuntimeAdapter(repository_root=tmp_path)
    event = {
        "event": "attempt_start",
        "request_id": "req",
        "attempt_index": 1,
        "status": "unfinished",
        "provider": "provider",
        "body": "DO_NOT_STORE",
    }
    runtime._record_provider_attempt(event)
    paths = list((tmp_path / "workspaces" / "usage-receipts").rglob("provider-attempts.jsonl"))
    assert len(paths) == 1
    assert json.loads(paths[0].read_text())["run_id"] is None
    runtime._run_root = tmp_path / "run"
    runtime._run_id = "run-id"
    runtime._record_provider_attempt(event)
    row = json.loads((runtime._run_root / "evidence" / "provider-attempts.jsonl").read_text())
    assert row["run_id"] == "run-id"
    assert "DO_NOT_STORE" not in json.dumps(row)


def test_resumed_numeric_file_and_directory_remain_private(tmp_path):
    parent = tmp_path / 'previous-evidence'
    parent.mkdir(mode=0o755)
    target = parent / 'dsh-provider.jsonl'
    target.write_text('')
    target.chmod(0o644)
    NumericReceiptWriter(target)({'event': 'attempt_start', 'request_id': 'single-request'})
    assert target.stat().st_mode & 0o777 == 0o600
    assert parent.stat().st_mode & 0o777 == 0o700


def test_real_codex_thread_usage_uses_fresh_zero_baseline_and_prices(tmp_path):
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "auth-a",
            "amount": "10",
            "prices": [{
                "provider": "route-a",
                "actual_model": "model-a",
                "cached_input_per_million": "0.2",
                "uncached_input_per_million": "2",
                "output_per_million": "8",
            }],
        },
    )
    bind_budget(tmp_path, budget.ref, "codex-owner", role="consumer")
    binding = RoleModelBinding("consumer", "route-a", "model-a", "low", "low")
    usage_path = tmp_path / "evidence" / "close-statistics-capture" / "codex-usage.jsonl"
    recorder = ActivityRecorder(
        tmp_path,
        {
            "runtime": "codex",
            "agent_id": "consumer",
            "role": "consumer",
            "provider": "route-a",
            "requested_model": "model-a",
        },
        usage_sources=[{"path": str(usage_path), "kind": "capture"}],
        fresh_session=True,
        budget=budget,
        budget_owner_id="codex-owner",
        budget_binding=binding,
        budget_runtime="codex",
    )
    try:
        # The source is registered before thread/start. bind() replaces the
        # provisional process identity with the real native thread identity.
        recorder.bind("thread-real")
        writer = NumericReceiptWriter(
            usage_path,
            recorder.context,
            budget=budget,
            budget_owner_id="codex-owner",
            budget_binding=binding,
        )
        writer({
            "event": "thread_usage",
            "thread_id": "thread-real",
            "turn_id": "turn-1",
            "total": {
                "inputTokens": 1_100_000,
                "cachedInputTokens": 1_000_000,
                "outputTokens": 10_000,
            },
        })
        state = budget.tick(now="2026-10-20T12:00:00+00:00")
        assert state["charged_estimate"] == "0.48"
        assert state["coverage"]["units"] == 1
        assert not any(
            issue["code"] in {"budget_price_missing", "cumulative_baseline_unproven"}
            for issue in state["coverage"]["issues"]
        )
        capture_source = next(
            source for source in state["sources"].values() if source["kind"] == "capture"
        )
        assert capture_source["binding"]["provider"] == "route-a"
        assert capture_source["binding"]["cumulative_segment"]["id"] == "thread-real"
        writer({
            "event": "thread_usage",
            "thread_id": "thread-real",
            "turn_id": "turn-2",
            "total": {
                "inputTokens": 2_200_000,
                "cachedInputTokens": 2_000_000,
                "outputTokens": 20_000,
            },
        })
        assert budget.tick(now="2026-10-20T12:00:01+00:00")["charged_estimate"] == "0.96"
    finally:
        recorder.exit(0)
    owner = budget.show()["owners"]["codex-owner"]
    assert owner["status"] == "exited"
    assert budget.show()["sources"][capture_source["source_id"]]["binding"]["cumulative_segment"]["end"] != "9999-12-31T23:59:59.999999+00:00"


def test_real_dsh_native_numeric_event_is_priced_without_provider_original(tmp_path):
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "auth-a",
            "amount": "10",
            "prices": [{
                "provider": "route-a",
                "actual_model": "model-a",
                "cached_input_per_million": "0.2",
                "uncached_input_per_million": "2",
                "output_per_million": "8",
            }],
        },
    )
    source = tmp_path / "evidence" / "dsh-native-role.jsonl"
    budget.bind_owner("dsh-owner", role="delivery", runtime="dsh")
    budget.register_source(
        "dsh-native-source",
        source,
        "dsh_native",
        binding={
            "provider": "route-a",
            "actual_model": "model-a",
            "runtime": "dsh",
            "runtime_session_id": "dsh-session",
            "process_instance": "dsh-process",
            "role": "delivery",
            "usage_definition_ref": "dsh:fixture",
        },
        owner_id="dsh-owner",
    )
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps({
        "runtime": "dsh",
        "process_instance": "dsh-process",
        "frame": {
            "method": "session.event",
            "params": {
                "sessionId": "dsh-session",
                "event": {
                    "type": "assistant/message",
                    "timestamp": "2026-10-20T12:00:00+00:00",
                    "seq": 1,
                    "data": {
                        "turn": 1,
                        "step": 1,
                        "usage": {
                            "inputTokens": 900_000,
                            "cacheReadTokens": 100_000,
                            "cacheWriteTokens": 0,
                            "outputTokens": 10_000,
                        },
                    },
                },
            },
        },
    }) + "\n")
    state = budget.tick(now="2026-10-20T12:00:01+00:00")
    assert state["charged_estimate"] == "1.9"
    assert state["coverage"]["units"] == 1
    assert state["units"]
    assert not any(issue["code"] == "budget_price_missing" for issue in state["coverage"]["issues"])


def test_real_dsh_register_usage_propagates_verified_credential_key_ref(tmp_path):
    credential_path = tmp_path / "deepseek.env"
    credential_path.write_text("DEEPSEEK_API_KEY=fixture-key\n", encoding="utf-8")
    credential_path.chmod(0o600)
    credential_binding = preflight_deepseek_credential(credential_path)
    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "auth-a",
            "amount": "10",
            "prices": [],
        },
    )
    run_root = tmp_path / "run"
    adapter = DshRuntimeAdapter(repository_root=tmp_path, budget=budget)
    adapter._run = SimpleNamespace(
        root=run_root,
        run_id="run-a",
        provider_credential_bindings={"deepseek-direct": credential_binding},
    )

    class Provider:
        def register_usage_session(self, _session_id, context, *, evidence_ref):
            self.context = dict(context)
            self.evidence_ref = evidence_ref

    adapter._provider = Provider()
    agent = _DshAgent(
        "delivery", SimpleNamespace(role="delivery"), run_root / "runtime", "session-a"
    )
    binding = RoleModelBinding("delivery", "deepseek-direct", "model-a", "low", "low")
    adapter._register_usage(agent, binding, run_id="run-a", phase="production")

    assert agent.usage_context["key_ref"] == credential_binding.key_ref
    assert adapter._provider.context["key_ref"] == credential_binding.key_ref
    native_source = next(
        source
        for source in budget.show()["sources"].values()
        if source["kind"] == "dsh_native"
    )
    assert native_source["binding"]["key_ref"] == credential_binding.key_ref


def test_real_dsh_delivery_process_control_works_without_model_price(tmp_path):
    """SIGSTOP/SIGCONT protects the native group without a model admission call."""

    budget = TaskBudget.create(
        tmp_path / "budget",
        {
            "task_ref": "task-a",
            "authorization_reference": "auth-a",
            "amount": "1",
            "prices": [],
        },
    )
    binding = RoleModelBinding("delivery", "route-a", "model-a", "low", "low")
    member_budget = runtime_budget(
        tmp_path,
        "delivery-owner",
        binding=binding,
        runtime="dsh",
        explicit=budget,
        role="delivery",
    )
    runtime = DSHDeliveryRuntime(
        binding=binding,
        home=tmp_path / "native",
        instructions="fixture",
        tools=[],
        tool_handler=lambda *_args, **_kwargs: {},
        session_id="delivery-session",
    )
    runtime.home.mkdir(parents=True)
    runtime._budget = member_budget
    process = subprocess.Popen(["sleep", "30"], start_new_session=True)
    runtime.process = process
    runtime._native_pid_identity = runtime._process_info(process.pid)[2]
    try:
        paused = runtime.control_budget({
            "source": "task_budget",
            "budget_ref": str(budget.ref),
            "epoch": 0,
            "request_id": "budget-control-1",
            "action": "pause",
        })
        resumed = runtime.control_budget({
            "source": "task_budget",
            "budget_ref": str(budget.ref),
            "epoch": 0,
            "request_id": "budget-control-1-resume",
            "action": "resume",
        })
        assert paused["status"] == "effective"
        assert resumed["status"] == "effective"
        assert budget.show()["owners"]["delivery-owner"]["control"]["0"]["status"] == "effective"
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
