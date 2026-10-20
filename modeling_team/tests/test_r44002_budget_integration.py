"""R4.4-002 integration contracts across Host, Delivery and evaluation owners.

The fixtures use the real local budget and operation modules.  Launchers and
native runtimes are controlled local stubs, so no provider or model call is
made by this suite.
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team import __main__ as main_module
from modeling_team import delivery, delivery_ops, host_ops
from modeling_team import runner as runner_module
import modeling_team.task_budget as task_budget_module
from modeling_team.close_statistics import ActivityRecorder
from modeling_team.delivery import DeliverySession
from modeling_team.evaluation_owner import EvaluationOwner
from modeling_team.model_routing import RoleModelBinding
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.budget import runtime_budget
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.task_budget import BudgetError, TaskBudget, bind_budget, budget_for
from modeling_team.transport_mcp import Delivery
from modeling_team.usage_capture import NumericReceiptWriter
from modeling_team.tests.test_r30015_acceptance import (
    _acceptance_source_run,
    _batch_report_for,
    _cleanup_run,
    _cli_args,
)
from modeling_team.tests.test_r30015_resume import FakeCursorPlatform, _readback
from modeling_team.tests.test_r3012_platform_responses import (
    _DualForwarder,
    _Factory,
    _platform_context,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _price(**extra: str) -> dict[str, str]:
    return {
        "provider": "route-a",
        "actual_model": "model-a",
        "cached_input_per_million": "0.2",
        "uncached_input_per_million": "2",
        "output_per_million": "8",
        **extra,
    }


def _make_budget(tmp_path: Path, amount: str = "10") -> TaskBudget:
    return TaskBudget.create(
        tmp_path / "origin" / "cost-budget",
        {
            "budget_id": "budget-a",
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": amount,
            "prices": [_price()],
        },
    )


def _session_config(budget: TaskBudget | None = None, **extra: object) -> dict:
    config = {
        "session_id": "delivery-contract",
        "authorization_reference": "auth-r44002",
        "model_profile": "openai-sol-medium",
        "allowed_operations": ["read"],
        "resource_authorization": {"mode": "starts"},
    }
    if budget is not None:
        config.update(
            {
                "resource_authorization": {"mode": "amount", "budget_ref": str(budget.ref)},
                "allowed_operations": ["production"],
                "task": "task.md",
                "profile": "profile.yaml",
                "scope": "scope.yaml",
            }
        )
    config.update(extra)
    return config


def _new_session(tmp_path: Path, monkeypatch, config: dict) -> DeliverySession:
    real_loader = delivery.load_team_model_profile
    monkeypatch.setattr(
        delivery,
        "load_team_model_profile",
        lambda _root, profile_id: real_loader(REPOSITORY_ROOT, profile_id),
    )
    return DeliverySession(
        repository_root=tmp_path,
        session_root=tmp_path / "delivery-session",
        config=config,
    )


def _start_run_args(run_id: str) -> dict[str, str]:
    return {
        "run_id": run_id,
        "task": "task.md",
        "profile": "profile.yaml",
        "model_profile": "openai-sol-medium",
        "scope": "scope.yaml",
        "freeze_started_at": "2026-10-20T00:00:00+00:00",
    }


class _Process:
    def __init__(self, pid: int = 44002, exit_code: int = 0) -> None:
        self.pid = pid
        self.exit_code = exit_code

    def wait(self) -> int:
        return self.exit_code


def _run_root(repository_root: Path, run_id: str) -> Path:
    root = repository_root / "workspaces" / "modeling-runs" / run_id
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "state.json").write_text(
        json.dumps({"state": "RUNNING", "run_id": run_id}), encoding="utf-8"
    )
    return root


def test_activity_and_numeric_receipts_link_to_one_real_budget_attempt(tmp_path: Path) -> None:
    budget = _make_budget(tmp_path)
    run_root = tmp_path / "activity-run"
    usage_path = run_root / "evidence" / "provider-usage.jsonl"
    context = {
        "runtime": "codex",
        "agent_id": "modeling",
        "role": "modeling",
        "task_ref": "task-a",
        "provider": "route-a",
        "requested_model": "model-a",
        "runtime_session_id": "thread-a",
        "process_instance": "process-a",
    }
    binding = {
        "task_ref": "task-a",
        "provider": "route-a",
        "actual_model": "model-a",
        "key_ref": "key-a",
        "runtime": "codex",
        "runtime_session_id": "thread-a",
        "process_instance": "process-a",
    }
    owner_id = "run:activity-run"
    recorder = ActivityRecorder(
        run_root,
        context,
        usage_sources=[{"path": usage_path, "kind": "capture"}],
        budget=budget,
        budget_owner_id=owner_id,
        budget_binding=binding,
    )
    writer = NumericReceiptWriter(
        usage_path,
        {**context, "actual_model": "model-a", "key_ref": "key-a"},
        budget=budget,
        budget_owner_id=owner_id,
        budget_binding=binding,
    )
    recorder.emit("llm_start", call_id="call-1")
    assert budget.tick(now="2026-10-20T00:00:00+00:00")["inflight_count"] == 1
    writer(
        {
            "event": "response_usage",
            "request_id": "call-1",
            "response_id": "response-1",
            "actual_model": "model-a",
            "status": "completed",
            "raw_usage": {"input_tokens": 1_100_000, "output_tokens": 10_000},
            "present_fields": ["input_tokens", "output_tokens"],
            "usage_complete": True,
        }
    )
    recorder.emit("llm_end", call_id="call-1", status="completed")
    settled = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert settled["inflight_count"] == 0
    assert settled["coverage"]["units"] == 1
    assert settled["charged_estimate"] == "2.28"
    assert len(json.loads(budget.state_path.read_text(encoding="utf-8"))["_attempts"]) == 1
    assert budget.tick(now="2026-10-20T00:00:02+00:00")["charged_estimate"] == "2.28"


def test_shared_activity_and_provider_sources_keep_two_role_members_separate(
    tmp_path: Path,
) -> None:
    """A run-level activity/provider file must preserve each member's identity."""

    budget = TaskBudget.create(
        tmp_path / "origin" / "cost-budget",
        {
            "budget_id": "budget-shared-members",
            "task_ref": "task-a",
            "authorization_reference": "user-1",
            "amount": "20",
            "prices": [
                _price(),
                _price(
                    provider="route-b",
                    actual_model="model-b",
                    uncached_input_per_million="4",
                    output_per_million="16",
                ),
            ],
        },
    )
    run_root = tmp_path / "shared-member-run"
    provider_path = run_root / "evidence" / "provider-attempts.jsonl"
    binding_a = RoleModelBinding("modeling", "route-a", "model-a", "low", "low")
    binding_b = RoleModelBinding("protocol", "route-b", "model-b", "low", "low")

    def context(role: str, provider: str, model: str, process: str) -> dict:
        return {
            "runtime": "codex",
            "agent_id": role,
            "role": role,
            "phase": "production",
            "task_ref": "task-a",
            "provider": provider,
            "requested_model": model,
            "actual_model": model,
            "key_ref": f"key-{role}",
            "process_instance": process,
        }

    context_a = context("modeling", "route-a", "model-a", "process-a")
    context_b = context("protocol", "route-b", "model-b", "process-b")
    recorder_a = ActivityRecorder(
        run_root,
        context_a,
        usage_sources=[{"path": provider_path, "kind": "capture", "shared": True}],
        budget=budget,
        budget_owner_id="member:modeling",
        budget_binding=binding_a,
        budget_runtime="codex",
        fresh_session=True,
    )
    recorder_b = ActivityRecorder(
        run_root,
        context_b,
        usage_sources=[{"path": provider_path, "kind": "capture", "shared": True}],
        budget=budget,
        budget_owner_id="member:protocol",
        budget_binding=binding_b,
        budget_runtime="codex",
        fresh_session=True,
    )
    recorder_a.bind("thread-a")
    recorder_b.bind("thread-b")
    # Provider attempt capture is one append-only run-level source, as in the
    # runtime.  Each writer contributes its own provider/model/thread row.
    writer_a = NumericReceiptWriter(provider_path, recorder_a.context)
    writer_b = NumericReceiptWriter(provider_path, recorder_b.context)

    recorder_a.emit("llm_start", call_id="call-a")
    recorder_b.emit("llm_start", call_id="call-b")
    started = budget.tick(now="2026-10-20T00:00:00+00:00")
    assert started["inflight_count"] == 2
    assert started["coverage"]["issues"] == []

    writer_a(
        {
            "event": "response_usage",
            "request_id": "call-a",
            "response_id": "response-a",
            "actual_model": "model-a",
            "status": "completed",
            "raw_usage": {"input_tokens": 1_100_000, "output_tokens": 10_000},
            "present_fields": ["input_tokens", "output_tokens"],
            "usage_complete": True,
        }
    )
    recorder_a.emit("llm_end", call_id="call-a", status="completed")
    one_settled = budget.tick(now="2026-10-20T00:00:01+00:00")
    assert one_settled["inflight_count"] == 1
    assert one_settled["coverage"]["units"] == 1
    assert one_settled["coverage"]["issues"] == []
    assert one_settled["charged_estimate"] == "2.28"
    assert set(one_settled["coverage"]["by_model"]) == {"model-a"}

    writer_b(
        {
            "event": "response_usage",
            "request_id": "call-b",
            "response_id": "response-b",
            "actual_model": "model-b",
            "status": "completed",
            "raw_usage": {"input_tokens": 1_100_000, "output_tokens": 10_000},
            "present_fields": ["input_tokens", "output_tokens"],
            "usage_complete": True,
        }
    )
    recorder_b.emit("llm_end", call_id="call-b", status="completed")
    both_settled = budget.tick(now="2026-10-20T00:00:02+00:00")
    assert both_settled["inflight_count"] == 0
    assert both_settled["coverage"]["units"] == 2
    assert both_settled["coverage"]["issues"] == []
    assert both_settled["charged_estimate"] == "6.84"


def test_codex_budget_control_preserves_member_identity_and_restart_idempotency(
    tmp_path: Path,
) -> None:
    budget = _make_budget(tmp_path, amount="20")
    budget.request_pause("budget_exhausted")
    epoch = budget.show("host")["epoch"]
    run_root = tmp_path / "control-run"
    binding_a = RoleModelBinding("modeling", "route-a", "model-a", "low", "low")
    binding_b = RoleModelBinding("protocol", "route-b", "model-b", "low", "low")
    owner_a = "codex:control-run:modeling"
    owner_b = "codex:control-run:protocol"

    class _Process:
        def poll(self):
            return None

    class _RpcProbe:
        def __init__(self):
            self.calls: list[tuple[str, str, dict]] = []

        def __call__(self, agent, method, params):
            self.calls.append((agent.agent_id, method, params))
            return {"turn": {"id": f"turn:{agent.agent_id}"}}

    class _ControlManager:
        def __init__(self):
            self.calls: list[tuple[str, str, str]] = []

        def authorize_control(self, provider_id, text, control_id):
            self.calls.append((provider_id, text, control_id))

    def member(agent_id: str, owner_id: str, binding: RoleModelBinding):
        return SimpleNamespace(
            agent_id=agent_id,
            process=_Process(),
            thread_id=f"thread:{agent_id}",
            active_turn_id=None,
            state="idle",
            provider_id=binding.provider_id,
            binding=binding,
            activity=None,
            activity_turn_id=None,
            budget=runtime_budget(
                run_root,
                owner_id,
                binding=binding,
                runtime="codex",
                explicit=budget,
                role=agent_id,
                process_instance=f"process:{agent_id}",
            ),
        )

    message = {
        "source": "task_budget",
        "action": "pause",
        "request_id": "budget-request-1",
        "epoch": epoch,
        "control_id": "budget-control-1",
        "text": "暂停原始请求 budget-request-1，等待用户确认。",
    }
    manager = _ControlManager()
    rpc = _RpcProbe()
    adapter = CodexRuntimeAdapter(
        repository_root=tmp_path,
        use_bwrap=False,
        process_factory=lambda *_args, **_kwargs: None,
        budget=budget,
    )
    adapter._provider_sessions = manager
    adapter.agents = {
        "modeling": member("modeling", owner_a, binding_a),
        "protocol": member("protocol", owner_b, binding_b),
    }
    adapter._rpc = rpc

    first = adapter.control_budget(message)
    assert first["status"] == "instruction_delivered"
    assert {row["status"] for row in first["members"]} == {"instruction_delivered"}
    assert budget.show("host")["control_status"] == "pause_pending"

    rpc_text_by_recipient = {}
    for agent_id, method, params in rpc.calls:
        assert method == "turn/start"
        payload = json.loads(params["input"][0]["text"])
        rpc_text_by_recipient[payload["recipient_id"]] = payload
        assert payload["source"] == "task_budget"
        assert payload["request_id"] == message["request_id"]
        assert payload["epoch"] == epoch
        assert payload["recipient_id"] == agent_id
        assert payload["control_id"] == f"{message['control_id']}:{agent_id}"
    assert set(rpc_text_by_recipient) == {"modeling", "protocol"}

    manager_text_by_control_id = {
        control_id: json.loads(text)
        for _provider, text, control_id in manager.calls
    }
    assert set(manager_text_by_control_id) == {
        f"{message['control_id']}:modeling",
        f"{message['control_id']}:protocol",
    }
    for recipient, payload in rpc_text_by_recipient.items():
        assert manager_text_by_control_id[payload["control_id"]] == payload

    # A fresh adapter and fresh RuntimeBudget objects must use the durable
    # control grant/receipt before any second native RPC or provider auth turn.
    restarted_budget = TaskBudget(budget.ref)
    restarted_manager = _ControlManager()
    restarted_rpc = _RpcProbe()
    restarted_adapter = CodexRuntimeAdapter(
        repository_root=tmp_path,
        use_bwrap=False,
        process_factory=lambda *_args, **_kwargs: None,
        budget=restarted_budget,
    )
    restarted_adapter._provider_sessions = restarted_manager

    def restarted_member(agent_id: str, owner_id: str, binding: RoleModelBinding):
        return SimpleNamespace(
            agent_id=agent_id,
            process=_Process(),
            thread_id=f"thread:{agent_id}",
            active_turn_id=None,
            state="idle",
            provider_id=binding.provider_id,
            binding=binding,
            activity=None,
            activity_turn_id=None,
            budget=runtime_budget(
                run_root,
                owner_id,
                binding=binding,
                runtime="codex",
                explicit=restarted_budget,
                role=agent_id,
                process_instance=f"process:{agent_id}:restart",
            ),
        )

    restarted_adapter.agents = {
        "modeling": restarted_member("modeling", owner_a, binding_a),
        "protocol": restarted_member("protocol", owner_b, binding_b),
    }
    restarted_adapter._rpc = restarted_rpc
    replay = restarted_adapter.control_budget(message)
    assert replay["status"] == "instruction_delivered"
    assert {row["status"] for row in replay["members"]} == {"instruction_delivered"}
    assert all(row.get("deduplicated") is True for row in replay["members"])
    assert restarted_rpc.calls == []
    assert restarted_manager.calls == []
    assert restarted_budget.show("host")["control_status"] == "pause_pending"


def test_budget_crash_after_event_append_replays_safe_subtotal_and_no_duplicate(tmp_path, monkeypatch) -> None:
    budget = _make_budget(tmp_path)
    source = tmp_path / "usage.jsonl"
    source.write_text(
        json.dumps(
            {
                "event": "response_usage",
                "response_id": "response-1",
                "provider": "route-a",
                "key_ref": "key-a",
                "actual_model": "model-a",
                "usage": {
                    "input_tokens": 1_100_000,
                    "cached_input_tokens": 1_000_000,
                    "output_tokens": 10_000,
                },
                "status": "completed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    budget.register_source("receipts", source, "receipts", {})
    assert budget.tick(now="2026-10-20T00:00:00+00:00")["charged_estimate"] == "0.48"
    with source.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "event": "response_usage",
                    "response_id": "response-2",
                    "provider": "route-a",
                    "key_ref": "key-a",
                    "actual_model": "model-a",
                    "usage": {
                        "input_tokens": 1_100_000,
                        "cached_input_tokens": 1_000_000,
                        "output_tokens": 10_000,
                    },
                    "status": "completed",
                }
            )
            + "\n"
        )
    real_atomic = task_budget_module._atomic_json
    crashed = False

    def crash_after_event(path, value):
        nonlocal crashed
        if Path(path) == budget.state_path and not crashed:
            crashed = True
            raise OSError("simulated state publish crash")
        return real_atomic(path, value)

    monkeypatch.setattr(task_budget_module, "_atomic_json", crash_after_event)
    with pytest.raises(OSError, match="simulated state publish crash"):
        budget.tick(now="2026-10-20T00:00:01+00:00")
    assert crashed is True

    restarted = TaskBudget(budget.ref)
    assert restarted.show()["charged_estimate"] == "0.96"
    assert restarted.tick(now="2026-10-20T00:00:02+00:00")["charged_estimate"] == "0.96"

    source.write_text(
        json.dumps(
            {
                "event": "response_usage",
                "response_id": "response-2",
                "provider": "route-a",
                "key_ref": "key-a",
                "actual_model": "model-a",
                "usage": {
                    "input_tokens": 1_100_000,
                    "cached_input_tokens": 1_000_000,
                    "output_tokens": 10_000,
                },
                "status": "completed",
            }
        )
        + "\n"
    )
    # Replacing the source file cannot refund the already committed response or
    # charge the surviving response a second time.
    assert restarted.tick(now="2026-10-20T00:00:03+00:00")["charged_estimate"] == "0.96"


def test_delivery_amount_mode_bypasses_start_limit_and_hides_budget_ref_from_model(
    tmp_path: Path, monkeypatch
) -> None:
    budget = _make_budget(tmp_path)
    session = _new_session(
        tmp_path,
        monkeypatch,
        _session_config(budget, session_id="amount-delivery", production_start_limit=0),
    )
    seen: dict = {}

    def fake_start_run(**kwargs):
        seen.update(kwargs)
        return {"status": "submitted", "run_id": kwargs["run_id"]}

    monkeypatch.setattr(delivery.host_ops_mcp, "start_run", fake_start_run)
    schema = session._tools["start_run"]["inputSchema"]
    assert "budget_ref" not in schema["properties"]
    assert schema["additionalProperties"] is False

    result = session.call_tool("start_run", _start_run_args("amount-run"))
    assert result["ok"] is True
    assert seen["budget_ref"] == str(budget.ref)
    assert session.run_ids == {"amount-run"}

    rejected = session.call_tool(
        "start_run",
        {**_start_run_args("model-selected-budget"), "budget_ref": str(tmp_path / "other")},
    )
    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "delivery_tool_failed"
    assert "model-selected-budget" not in session.run_ids


def test_delivery_starts_mode_keeps_historical_start_limit(tmp_path: Path, monkeypatch) -> None:
    session = _new_session(
        tmp_path,
        monkeypatch,
        _session_config(
            None,
            session_id="starts-delivery",
            production_start_limit=0,
            allowed_operations=["production"],
            task="task.md",
            profile="profile.yaml",
            scope="scope.yaml",
        ),
    )
    called = False

    def unexpected_start(**_kwargs):
        nonlocal called
        called = True
        return {"status": "submitted"}

    monkeypatch.setattr(delivery.host_ops_mcp, "start_run", unexpected_start)
    result = session.call_tool("start_run", _start_run_args("old-count-limit"))
    assert result["ok"] is False
    assert "authorized production start limit exhausted" in result["error"]["message"]
    assert called is False


def test_delivery_numeric_budget_growth_does_not_wake(tmp_path: Path, monkeypatch) -> None:
    session = _new_session(tmp_path, monkeypatch, _session_config())

    def observation(charged: str) -> dict:
        task_budget = {"authorized_amount": "10", "charged_estimate": charged}
        return {
            "runs": {
                "run-1": {
                    "status": {"ok": True, "data": {"state": "RUNNING", "task_budget": task_budget}},
                    "pending": {"ok": True, "data": {"items": []}},
                    "events": {"ok": True, "data": {"events": []}},
                    "request_ledger": {"ok": True, "data": {}},
                }
            },
            "operations": {
                "operation-1": {
                    "ok": True,
                    "data": {"status": "running", "task_budget": task_budget},
                }
            },
            "repair_verifications": {},
        }

    assert session.record_observation(observation("0.48"), force_delivery=True) is True
    assert session.record_observation(observation("0.96")) is False
    saved = json.loads((session.session_root / "observation.json").read_text())
    assert saved["wake_count"] == 1


def test_zero_amount_delivery_rejects_before_native_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    budget = _make_budget(tmp_path, amount="0")
    session_id = "zero-amount-r44002"
    session_root = REPOSITORY_ROOT / "workspaces" / "delivery-sessions" / session_id
    shutil.rmtree(session_root, ignore_errors=True)
    native_calls: list[str] = []

    class UnexpectedRuntime:
        def __init__(self, *_args, **_kwargs):
            native_calls.append("created")
            raise AssertionError("zero amount must not construct a native runtime")

    monkeypatch.setattr(delivery, "DeliveryRuntime", UnexpectedRuntime)
    config = _session_config(
        budget,
        session_id=session_id,
        allowed_operations=["read"],
    )
    try:
        result = delivery._run_delivery(config, repository_root=REPOSITORY_ROOT, resume=False)
        assert result == 2
        assert native_calls == []
        saved = json.loads((session_root / "session.json").read_text())
        assert saved["state"] == "budget_paused"
    finally:
        shutil.rmtree(session_root, ignore_errors=True)


def test_host_start_and_evaluation_inherit_original_budget_and_reject_replacement(
    tmp_path: Path,
) -> None:
    budget = _make_budget(tmp_path)
    other_budget = _make_budget(tmp_path / "other")
    session_ref = tmp_path / "host-session.json"
    session_ref.write_text(
        json.dumps(
            {
                "resource_authorization": {
                    "mode": "amount",
                    "budget_ref": str(budget.ref),
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "task.md").write_text("task", encoding="utf-8")
    (tmp_path / "profile.yaml").write_text("profile", encoding="utf-8")
    (tmp_path / "scope.yaml").write_text("scope", encoding="utf-8")
    launched: list[list[str]] = []

    def launcher(argv, **_kwargs):
        launched.append(list(argv))
        return _Process()

    wrong_run_args = _start_run_args("host-wrong-budget")
    with pytest.raises(host_ops.HostOpError) as error:
        host_ops.start_run(
            **wrong_run_args,
            repository_root=tmp_path,
            host_session_ref=str(session_ref),
            budget_ref=str(other_budget.ref),
            launcher=launcher,
            run_root_wait_seconds=0,
        )
    assert error.value.code == "budget_binding_conflict"
    assert launched == []

    host_result = host_ops.start_run(
        **_start_run_args("host-budget-run"),
        repository_root=tmp_path,
        host_session_ref=str(session_ref),
        launcher=launcher,
        run_root_wait_seconds=0,
    )
    assert host_result["launched"] is True
    launch_record = host_ops.read_launch_record("host-budget-run", repository_root=tmp_path)
    assert launch_record["budget_ref"] == str(budget.ref)
    assert launched[-1][-2:] == ["--budget-ref", str(budget.ref)]

    run_root = _run_root(tmp_path, "evaluation-budget-run")
    bind_budget(run_root, budget.ref, "run:evaluation-budget-run", kind="production")
    with pytest.raises(host_ops.HostOpError) as error:
        delivery_ops.start_evaluation(
            run_id="evaluation-budget-run",
            operation_id="evaluation-wrong-budget",
            mode="public-feedback",
            freeze_id="freeze-1",
            checkpoint_id="checkpoint-1",
            question_ids=["q-1"],
            repository_root=tmp_path,
            budget_ref=str(other_budget.ref),
            launcher=launcher,
        )
    assert error.value.code == "budget_binding_conflict"

    evaluation_result = delivery_ops.start_evaluation(
        run_id="evaluation-budget-run",
        operation_id="evaluation-budget",
        mode="public-feedback",
        freeze_id="freeze-1",
        checkpoint_id="checkpoint-1",
        question_ids=["q-1"],
        repository_root=tmp_path,
        launcher=launcher,
    )
    assert evaluation_result["request"]["budget_ref"] == str(budget.ref)
    owner_root = tmp_path / ".delivery-ops" / "evaluation-budget.owner"
    assert budget_for(owner_root).ref == budget.ref


def test_checkpoint_acceptance_inherits_source_budget_and_binds_evaluation_owner(
    tmp_path: Path, monkeypatch
) -> None:
    source_root, _frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    budget = _make_budget(tmp_path)
    other_budget = _make_budget(tmp_path / "other")
    bind_budget(
        source_root,
        budget.ref,
        "run:" + source_root.name,
        kind="production",
        run_id=source_root.name,
    )
    new_run_id = f"r44002-checkpoint-{tmp_path.name}"
    owner_root = REPOSITORY_ROOT / ".delivery-ops" / (new_run_id + ".owner")
    launch_root = REPOSITORY_ROOT / "workspaces" / "modeling-runs" / ".host-launches"
    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, "host-key-r44002")
    monkeypatch.setattr(host_ops, "_spawn_exit_reaper", lambda *_args: None)
    try:
        with pytest.raises(host_ops.HostOpError) as error:
            host_ops.resume_from_checkpoint(
                source_run_id=source_root.name,
                checkpoint_id=checkpoint_id,
                new_run_id=new_run_id + "-wrong",
                mode="acceptance",
                authorization_reference="user-r44002-checkpoint",
                model_profile="openai-sol-medium",
                budget_ref=str(other_budget.ref),
                repository_root=REPOSITORY_ROOT,
                run_root_wait_seconds=0,
            )
        assert error.value.code == "budget_binding_conflict"

        def launcher(_argv, **_kwargs):
            return _Process(pid=44002002)

        result = host_ops.resume_from_checkpoint(
            source_run_id=source_root.name,
            checkpoint_id=checkpoint_id,
            new_run_id=new_run_id,
            mode="acceptance",
            authorization_reference="user-r44002-checkpoint",
            model_profile="openai-sol-medium",
            repository_root=REPOSITORY_ROOT,
            launcher=launcher,
            run_root_wait_seconds=0,
        )
        assert result["mode"] == "acceptance"
        assert result["launch_record"]["budget_ref"] == str(budget.ref)
        assert result["launch_record"]["argv"][result["launch_record"]["argv"].index("--budget-ref") + 1] == str(budget.ref)
        assert result["launch_record"]["argv"][result["launch_record"]["argv"].index("--owner-root") + 1] == str(owner_root)
        assert budget_for(owner_root).ref == budget.ref
        owner = budget.show()["owners"]["evaluation:" + new_run_id]
        assert owner["kind"] == "evaluation"
        assert owner["run_id"] == new_run_id
    finally:
        _cleanup_run(source_root)
        shutil.rmtree(owner_root, ignore_errors=True)
        for suffix in (".json", ".out.log", ".err.log"):
            (launch_root / f"{new_run_id}{suffix}").unlink(missing_ok=True)
            (launch_root / f"{new_run_id}-wrong{suffix}").unlink(missing_ok=True)


def test_checkpoint_zero_budget_complete_report_closes_without_model_call(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source_root, frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    budget = _make_budget(tmp_path, amount="0")
    bind_budget(
        source_root,
        budget.ref,
        "run:" + source_root.name,
        kind="production",
        run_id=source_root.name,
    )
    other_budget = _make_budget(tmp_path / "other")
    new_run_id = f"r44002-zero-checkpoint-{tmp_path.name}"
    output_root = REPOSITORY_ROOT / "workspaces" / "modeling-runs" / new_run_id
    try:
        report = _batch_report_for(frozen, source_root.name, passed=["cq-1", "cq-2"])
        report_dir = source_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
        report_dir.mkdir(parents=True)
        (report_dir / "batch-report.json").write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        monkeypatch.setattr(
            main_module,
            "http_readback",
            lambda _base_url, _key: _readback(FakeCursorPlatform()),
        )
        monkeypatch.setattr(
            main_module,
            "_run_cq_acceptance",
            lambda *_args, **_kwargs: pytest.fail("verification-only closing must not call a model"),
        )

        wrong_args = _cli_args(source_root.name, checkpoint_id, new_run_id + "-wrong")
        wrong_args.budget_ref = str(other_budget.ref)
        assert (
            main_module._run_checkpoint_resume_acceptance(
                wrong_args,
                REPOSITORY_ROOT,
                forwarder_factory=_Factory(_DualForwarder(_platform_context(), [])),
            )
            == 2
        )
        assert not (REPOSITORY_ROOT / "workspaces" / "modeling-runs" / (new_run_id + "-wrong")).exists()

        code = main_module._run_checkpoint_resume_acceptance(
            _cli_args(source_root.name, checkpoint_id, new_run_id),
            REPOSITORY_ROOT,
            forwarder_factory=_Factory(_DualForwarder(_platform_context(), [])),
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out.splitlines()[-1])
        assert payload["mode"] == "verification-only-closing"
        assert payload["model_sessions_started"] == 0
        assert payload["semantic_starts"] == 0
        assert budget_for(output_root).ref == budget.ref
        owner_root = output_root / "control" / ("evaluation-" + frozen["batch_id"])
        assert budget_for(owner_root).ref == budget.ref
        owner_id = "evaluation:evaluation-" + frozen["batch_id"]
        assert budget.show()["owners"][owner_id]["control"][str(budget.show()["epoch"])]["status"] == "not_started"
    finally:
        _cleanup_run(source_root)
        _cleanup_run(output_root)
        _cleanup_run(REPOSITORY_ROOT / "workspaces" / "modeling-runs" / (new_run_id + "-wrong"))


def test_delivery_budget_control_text_contains_full_request_id(tmp_path: Path, monkeypatch) -> None:
    budget = _make_budget(tmp_path)
    session = _new_session(tmp_path, monkeypatch, _session_config(budget, session_id="request-id-text"))
    budget.request_pause("budget_exhausted")
    captured: dict = {}

    class Runtime:
        def control_budget(self, message):
            captured.update(message)
            return {"status": "instruction_delivered"}

    assert session.sync_budget_control(Runtime()) is True
    assert captured["request_id"] in captured["text"]


def test_evaluation_owner_composes_user_pause_with_budget_continue_without_judge(
    tmp_path: Path,
) -> None:
    budget = _make_budget(tmp_path)
    owner_root = tmp_path / "evaluation-compose.owner"
    bind_budget(owner_root, budget.ref, "evaluation:evaluation-compose", kind="evaluation")
    owner = EvaluationOwner(owner_root)

    try:
        with (owner_root / "input.fifo").open("w") as stream:
            stream.write(json.dumps({"request_id": "user-pause", "action": "pause", "text": "pause"}) + "\n")
        owner.poll()
        assert owner.receipts["user-pause"]["status"] == "owner_waiting"
        assert owner.pending_pause == "user-pause"
        assert owner._pause_reasons == {"user"}
        assert owner.active == [] and owner.retained == [] and owner.current is None

        budget.request_pause("budget_exhausted")
        owner.poll()
        budget_receipts = [
            receipt
            for receipt in owner.receipts.values()
            if receipt.get("source") == "task_budget"
        ]
        assert len(budget_receipts) == 1
        assert budget_receipts[0]["action"] == "pause"

        budget.add({"delta_amount": "1", "authorization_id": "continue-auth"})
        budget.continue_authorized("continue-auth")
        owner.poll()
        resume_receipt = [
            receipt
            for receipt in owner.receipts.values()
            if receipt.get("source") == "task_budget" and receipt.get("action") == "resume"
        ]
        assert len(resume_receipt) == 1
        assert resume_receipt[0]["status"] == "pause_pending"
        assert owner._pause_reasons == {"user"}
        # The retained control identity can be the budget epoch's request;
        # the user reason is the invariant that keeps the owner paused.
        assert owner.pending_pause is not None
        assert owner.active == [] and owner.retained == [] and owner.current is None
        state = json.loads((owner_root / "state.json").read_text())
        assert state["active_members"] == []
        assert state["retained_members"] == []
    finally:
        owner.close()


def test_codex_budget_control_stays_pending_until_all_members_confirm(
    tmp_path: Path,
) -> None:
    budget = _make_budget(tmp_path)
    sent: list[tuple[str, str]] = []

    class Adapter:
        runtime = "codex"

        def runtime_identity(self, agent_id):
            return {"thread_id": agent_id}

        def send_message(self, agent_id, delivery):
            sent.append((agent_id, delivery.text))
            return SimpleNamespace(mode="steer")

    agents = [
        SimpleNamespace(agent_id="coordinator", package=SimpleNamespace(role="coordinator")),
        SimpleNamespace(agent_id="modeling", package=SimpleNamespace(role="modeling")),
    ]
    runner = TeamRunner.__new__(TeamRunner)
    runner.run = SimpleNamespace(
        run_id="budget-run",
        configuration=SimpleNamespace(profile=SimpleNamespace(agents=agents)),
    )
    runner.adapter = Adapter()
    runner.budget = budget
    runner._flow_pause_reasons = set()
    runner._flow_requests = {}
    runner._append_evidence = lambda *_args, **_kwargs: None

    epoch = budget.show()["epoch"]
    message = {
        "source": "task_budget",
        "epoch": epoch,
        "request_id": "budget-pause-1",
        "action": "pause",
        "text": "pause",
    }
    result = runner._relay_flow_message("pause", message)
    assert result[0]["status"] == "instruction_delivered"
    assert {agent_id for agent_id, _text in sent} == {"coordinator", "modeling"}

    confirmed = runner._observe_flow_confirmation(
        SimpleNamespace(
            agent_id="coordinator",
            text=json.dumps({"flow_confirmation": {"request_id": "budget-pause-1", "action": "pause"}}),
        )
    )
    assert confirmed is True
    assert runner._budget_member_control["confirmed"] == ["coordinator"]
    assert runner._budget_member_control["targets"] == ["coordinator", "modeling"]
    assert budget.show()["owners"]["run:budget-run"]["control"][str(epoch)]["status"] == "instruction_delivered"


def test_runner_drain_budget_refusal_keeps_run_observable_without_cleanup(
    tmp_path: Path,
) -> None:
    runner = TeamRunner(repository_root=tmp_path, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(run_id="budget-refusal-run")
    states: list[tuple[str, dict]] = []
    cleanup_calls: list[str] = []

    def refusal():
        raise BudgetError("budget_exhausted")

    runner._drain_current_work = refusal
    runner._state = lambda state, **details: states.append((state, details))
    runner.cleanup = lambda: cleanup_calls.append("cleanup")

    result = runner.drain()

    assert result == [{"type": "budget-pause", "code": "budget_exhausted", "retryable": True}]
    assert states == [("PAUSE_PENDING", {"budget_error": "budget_exhausted"})]
    assert cleanup_calls == []
    assert runner.run.run_id == "budget-refusal-run"


def test_runner_requeues_budget_refusal_suffix_without_replaying_accepted_delivery(
    tmp_path: Path,
) -> None:
    sent: list[str] = []
    acknowledged: list[str] = []
    requeued: list[list[str]] = []

    class Adapter:
        runtime = "codex"

        def receive_messages(self):
            return []

        def send_message(self, _recipient_id, delivery):
            sent.append(delivery.delivery_id)
            if delivery.delivery_id == "delivery-2":
                raise BudgetError("budget_exhausted")
            return SimpleNamespace(mode="steer")

    class Transport:
        issue_ledger = None
        terminal_dependencies: dict = {}
        results: dict = {}

        def drain(self):
            return [
                Delivery(index, "modeling", "coordinator", f"message-{index}", float(index), f"delivery-{index}")
                for index in range(1, 4)
            ]

        def requeue(self, deliveries):
            requeued.append([delivery.delivery_id for delivery in deliveries])

        def ack_delivery(self, delivery_id):
            acknowledged.append(delivery_id)

        def record_work_transport(self, *_args, **_kwargs):
            return None

    coordinator = SimpleNamespace(
        agent_id="coordinator", package=SimpleNamespace(role="coordinator")
    )
    runner = TeamRunner(repository_root=tmp_path, adapter=Adapter())
    runner.run = SimpleNamespace(
        run_id="budget-requeue-run",
        configuration=SimpleNamespace(profile=SimpleNamespace(agents=[coordinator])),
    )
    runner.transport = Transport()
    runner._sync_task_budget = lambda: False
    runner._consume_runtime_failures = lambda: []
    runner._append_evidence = lambda *_args, **_kwargs: None
    runner._state = lambda *_args, **_kwargs: None
    runner._formal_candidate_roles = lambda: None
    runner._observe_formal_candidate_delivery = lambda _delivery: None
    runner._register_stage_handoff_delivery_if_exact = lambda _delivery: None
    runner._check_provider_waits = lambda _output: None
    runner._track_issue_pending = lambda: None
    runner._track_provider_wait = lambda: None
    runner._check_run_fallback_timeout = lambda: None
    runner._cq_check_scenario_map_slices = lambda: None
    runner._check_staged_decision_gates = lambda: False
    runner._check_cooperative_idle = lambda: None
    runner._wake_acceptance_on_child_terminal = lambda: None
    runner._handle_issue_events = lambda _output: None
    runner._drain_coordination_runtime_deliveries = lambda: None
    runner._finalize_acceptance_if_ready = lambda: None
    runner._issue_ledger = lambda: None
    cleanup_calls: list[str] = []
    runner.cleanup = lambda: cleanup_calls.append("cleanup")

    output = runner.drain()

    assert [entry["delivery_id"] for entry in output] == ["delivery-1"]
    assert sent == ["delivery-1", "delivery-2"]
    assert acknowledged == ["delivery-1"]
    assert requeued == [["delivery-2", "delivery-3"]]
    assert cleanup_calls == []
    assert runner.run.run_id == "budget-requeue-run"


def test_amount_start_budget_refusal_keeps_unlaunched_suffix_and_run(
    tmp_path: Path, monkeypatch
) -> None:
    budget = _make_budget(tmp_path)
    starts: list[str] = []
    cleanup_calls: list[str] = []
    states: list[str] = []

    class Adapter:
        runtime = "codex"

        def start_roster(self, _run, agents):
            return [SimpleNamespace(agent_id=agent.agent_id) for agent in agents]

        def start_task(self, agent_id, task, _skills, _roster):
            starts.append(f"{agent_id}:{task}")
            if agent_id == "modeling":
                raise BudgetError("budget_exhausted")

    class Broker:
        def __init__(self, root, *_args, **_kwargs):
            self.root = Path(root)
            self.root.mkdir(parents=True, exist_ok=True)

        def start(self, _agent_ids):
            return None

    def agent(agent_id: str, role: str):
        return SimpleNamespace(
            agent_id=agent_id,
            package=SimpleNamespace(role=role, required_skills=()),
        )

    agents = [
        agent("coordinator", "coordinator"),
        agent("modeling", "modeling"),
        agent("protocol", "protocol"),
    ]
    run_root = tmp_path / "amount-mid-refusal"
    run_root.mkdir(parents=True)
    runner = TeamRunner(repository_root=tmp_path, adapter=Adapter(), budget_ref=budget.ref)
    runner.run = SimpleNamespace(
        run_id="amount-mid-refusal",
        root=run_root,
        configuration=SimpleNamespace(
            profile=SimpleNamespace(
                agents=agents,
                communication=(),
                parameters={},
                runtime="codex",
            ),
            task=SimpleNamespace(schema_version=1, retain_nonempty=False),
        ),
        handoff_materials=None,
    )
    runner._formal_coordination_enabled = lambda: False
    runner._is_r23003_modeling_run = lambda: False
    runner._runtime_profile_agents = lambda: tuple(agents)
    runner._task_text = lambda role=None: f"original-task:{role}"
    runner._state = lambda state, **_details: states.append(state)
    runner.cleanup = lambda: cleanup_calls.append("cleanup")
    monkeypatch.setattr(runner_module, "TeamTransportBroker", Broker)

    runner.start()

    assert starts == ["coordinator:original-task:coordinator", "modeling:original-task:modeling"]
    assert [agent.agent_id for agent in runner._budget_pending_start_agents] == [
        "modeling",
        "protocol",
    ]
    assert states[-1] == "PAUSE_PENDING"
    assert cleanup_calls == []
    assert runner.run.run_id == "amount-mid-refusal"


def test_evaluation_owner_rejects_late_budget_confirmation_after_epoch_advance(
    tmp_path: Path,
) -> None:
    budget = _make_budget(tmp_path)
    owner_root = tmp_path / "evaluation-race.owner"
    bind_budget(owner_root, budget.ref, "evaluation:evaluation-race", kind="evaluation")

    class Adapter:
        agents: dict[str, object] = {}

        def send_message(self, _agent_id, _delivery):
            return SimpleNamespace(mode="steer")

    resource = SimpleNamespace(
        spec={"v3_role": "platform-examiner"},
        thread_id="evaluation-thread",
        process=SimpleNamespace(pid=44002, poll=lambda: None),
        task_closed=False,
        blocked_task=False,
        user_waiting=False,
        runtime="codex",
        _child_agent=SimpleNamespace(agent_id="examiner"),
        _watchdog_stop=threading.Event(),
    )
    owner = EvaluationOwner(owner_root)
    adapter = Adapter()
    try:
        owner.bind(adapter, resource)
        with (owner_root / "input.fifo").open("w") as stream:
            stream.write(json.dumps({"request_id": "user-pause", "action": "pause", "text": "pause"}) + "\n")
        owner.poll()
        assert owner.receipts["user-pause"]["status"] == "instruction_delivered"

        budget.request_pause("budget_exhausted")
        owner.poll()
        budget_request_id, budget_receipt = next(
            (request_id, receipt)
            for request_id, receipt in owner.receipts.items()
            if receipt.get("source") == "task_budget" and receipt.get("action") == "pause"
        )
        old_epoch = budget_receipt["epoch"]
        assert old_epoch == budget.show()["epoch"]

        budget.add({"delta_amount": "1", "authorization_id": "continue-auth"})
        budget.continue_authorized("continue-auth")
        assert budget.show()["epoch"] == old_epoch + 1

        stale = owner.confirm(
            resource,
            {"request_id": budget_request_id, "action": "pause"},
        )
        assert stale == {"status": "stale_control", "action": "pause"}
        assert budget_receipt.get("confirmed_threads") in (None, [])
        assert resource.user_waiting is False

        owner.poll()
        resume_receipt = next(
            receipt
            for receipt in owner.receipts.values()
            if receipt.get("source") == "task_budget" and receipt.get("action") == "resume"
        )
        assert resume_receipt["epoch"] == old_epoch + 1
        assert resume_receipt["status"] == "pause_pending"
        assert owner._pause_reasons == {"user"}
        assert owner.pending_pause is not None
        assert owner.receipts["user-pause"]["status"] == "instruction_delivered"
    finally:
        owner.close()
