"""Real existing Host ledger and v5 control boundaries; no provider charges."""

import json
import subprocess
from datetime import UTC, datetime

import pytest

from ontoweave_modeling.budget import synchronize_budget
from ontoweave_modeling.contracts import FrameworkError, TaskBinding
from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.execution import ExecutionManager
from ontoweave_modeling.host_bridge import HostBridge


def amount_binding(task_file, tmp_path, amount="0.001", prices=None):
    task = json.loads(task_file.read_text())
    ref = tmp_path / "amount-budget"
    task["authorization"] = {
        "mode": "amount",
        "reference": "engineering-test",
        "budget_ref": str(ref),
    }
    task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(task_file, tmp_path / "amount-run")
    bridge = HostBridge(binding.root)
    config = {
        "task_ref": task["task_ref"],
        "amount": amount,
        "authorization_reference": "engineering-test",
        "allowed_bindings": [{"provider": "glm-direct", "actual_model": "glm-5.3-flash"}],
    }
    if prices is not None:
        config["prices"] = prices
    result = subprocess.run(
        [
            bridge.command[0],
            "-c",
            (
                "import json,sys; from modeling_team.task_budget import TaskBudget; "
                "TaskBudget.create(sys.argv[1],json.loads(sys.argv[2]))"
            ),
            str(ref),
            json.dumps(config),
        ],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return binding


def numeric_sources(binding, execution_id="turn-one", input_tokens=2000, role="modeling"):
    root = binding.root / "executions" / execution_id
    root.mkdir(parents=True, exist_ok=True)
    context = {
        "task_ref": binding.data["task_ref"],
        "run_id": binding.data["run_id"],
        "agent_id": execution_id,
        "role": role,
        "phase": "P1.1",
        "provider": "glm-direct",
        "requested_model": "glm-5.3-flash",
        "key_ref": "test-credential-alias",
        "runtime": "codex",
    }
    now = datetime.now(UTC).isoformat()
    rows = [
        {
            **context,
            "event": "attempt_start",
            "status": "unfinished",
            "proxy_session_id": execution_id,
            "request_id": "request-one",
            "attempt_index": 1,
            "start": now,
        },
        {
            **context,
            "event": "attempt_end",
            "status": "completed",
            "proxy_session_id": execution_id,
            "request_id": "request-one",
            "attempt_index": 1,
            "end": now,
        },
    ]
    (root / "provider-usage.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    native = {
        "event": "thread_usage",
        "thread_id": execution_id,
        "runtime_session_id": execution_id,
        "turn_id": "one",
        "received_at": now,
        "total": {"inputTokens": input_tokens, "cachedInputTokens": 0, "outputTokens": 100},
    }
    (root / "budget-native-usage.jsonl").write_text(json.dumps(native) + "\n")
    return root, native


def test_amount_pause_natural_end_and_addition_survives_restart(task_file, tmp_path, workspace):
    binding = amount_binding(task_file, tmp_path)
    control = TaskControl(workspace)
    assert synchronize_budget(binding, control)["admission_open"]
    assert control.begin_turn("unit", "turn-one")["admitted"]
    root, native = numeric_sources(binding)
    state = synchronize_budget(binding, control)
    assert state["charged_estimate"] == "0.0024"
    assert not state["admission_open"]
    assert control.view()["status"] == "waiting_for_turn_end"
    assert control.view()["active"] == {"unit": "turn-one"}
    assert not control.begin_turn("other", "turn-two")["admitted"]
    control.finish_turn("unit", "turn-one")
    assert control.view()["status"] == "settled"
    # Duplicate cumulative notifications and new worker processes cannot add the subtotal twice.
    with (root / "budget-native-usage.jsonl").open("a") as stream:
        stream.write(json.dumps(native) + "\n")
    assert (
        synchronize_budget(TaskBinding.load(binding.root), control)["charged_estimate"] == "0.0024"
    )
    control.enqueue("separate-user-pause", "pause")
    control.synchronize()
    addition = {
        "amount": "1",
        "authorization_id": "engineering-topup-1",
        "authorization_reference": "engineering-topup-1",
        "continue_authorized": True,
    }
    state = synchronize_budget(binding, control, addition=addition)
    assert state["authorized_amount"] == "1.001" and state["admission_open"]
    assert control.view()["mode"] == "paused"
    assert not control.begin_turn("unit", "turn-two")["admitted"]
    control.enqueue("explicit-user-resume", "resume")
    assert control.begin_turn("unit", "turn-two")["admitted"]
    assert synchronize_budget(binding, control, addition=addition)["authorized_amount"] == "1.001"


def test_completed_execution_replays_without_call_and_new_turn_is_denied(
    task_file, tmp_path, workspace
):
    binding = amount_binding(task_file, tmp_path)
    control = TaskControl(workspace)
    manager = ExecutionManager(workspace, control, binding)
    calls = []

    def invoke(root, purpose, prompt, inputs):
        calls.append(root.name)
        numeric_sources(binding, root.name)
        return {"status": "completed", "final_response": "original"}

    original = manager.run("turn-one", "model", "original", invoke)
    assert not control.view()["budget_open"]
    assert manager.run("turn-one", "model", "original", invoke) == original
    with pytest.raises(FrameworkError, match="execution_not_admitted"):
        manager.run("turn-two", "model", "next", invoke)
    assert calls == ["turn-one"]


def test_budget_reference_and_task_scope_are_real_boundaries(task_file, tmp_path, workspace):
    binding = amount_binding(task_file, tmp_path)
    # The Host reloads the frozen binding; check the ledger's independent task identity.
    ref = tmp_path / "wrong-budget"
    bridge = HostBridge(binding.root)
    program = (
        "from modeling_team.task_budget import TaskBudget; import sys; "
        "TaskBudget.create(sys.argv[1], {'task_ref':'another-task','amount':'1',"
        "'authorization_reference':'engineering-test', 'prices':[]})"
    )
    result = subprocess.run(
        [bridge.command[0], "-c", program, str(ref)],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    # A separately prepared run points to that ledger, without changing a frozen binding.
    task = json.loads(task_file.read_text())
    task["authorization"]["budget_ref"] = str(ref)
    task_file.write_text(json.dumps(task))
    other = TaskBinding.prepare(task_file, tmp_path / "wrong-run")
    with pytest.raises(FrameworkError, match="budget_task_mismatch"):
        synchronize_budget(other, TaskControl(workspace))


def test_usage_only_does_not_require_a_ledger(binding, workspace, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("usage_only must not call the amount worker")

    monkeypatch.setattr(HostBridge, "call", forbidden)
    assert synchronize_budget(binding, TaskControl(workspace)) is None


def test_unpriced_model_is_denied_before_native_dispatch(task_file, tmp_path, workspace):
    binding = amount_binding(task_file, tmp_path, amount="1", prices=[])
    manager = ExecutionManager(workspace, TaskControl(workspace), binding)

    def forbidden(*args):
        raise AssertionError("an unpriced model must not be dispatched")

    with pytest.raises(FrameworkError, match="budget_price_missing"):
        manager.run("unpriced", "model", "prompt", forbidden)
    assert not (binding.root / "executions/unpriced").exists()


def test_shared_budget_keeps_spend_across_runs_and_roles(task_file, tmp_path, workspace):
    first = amount_binding(task_file, tmp_path, amount="1")
    numeric_sources(first)
    control = TaskControl(workspace)
    assert synchronize_budget(first, control)["charged_estimate"] == "0.0024"
    task = json.loads(task_file.read_text())
    task["run_id"] = "second-run-same-authorization"
    task_file.write_text(json.dumps(task))
    second = TaskBinding.prepare(task_file, tmp_path / "second-run")
    assert synchronize_budget(second, control)["charged_estimate"] == "0.0024"
    numeric_sources(second, "evaluation-one", role="acceptance")
    state = synchronize_budget(second, control)
    assert state["charged_estimate"] == "0.0048"
    assert set(state["coverage"]["by_role"]) == {"modeling", "acceptance"}


def test_later_transport_attempts_are_not_filtered_by_native_observation_window(
    task_file, tmp_path, workspace
):
    binding = amount_binding(task_file, tmp_path, amount="1")
    root, native = numeric_sources(binding)
    control = TaskControl(workspace)
    synchronize_budget(binding, control)
    now = datetime.now(UTC).isoformat()
    path = root / "provider-usage.jsonl"
    template = json.loads(path.read_text().splitlines()[0])
    with path.open("a") as stream:
        for event, status in (("attempt_start", "unfinished"), ("attempt_end", "completed")):
            stream.write(
                json.dumps(
                    {
                        **template,
                        "request_id": "later-request",
                        "event": event,
                        "status": status,
                        "start": now,
                        "end": now,
                    }
                )
                + "\n"
            )
    native["received_at"] = now
    native["total"] = {"inputTokens": 4000, "cachedInputTokens": 0, "outputTokens": 200}
    with (root / "budget-native-usage.jsonl").open("a") as stream:
        stream.write(json.dumps(native) + "\n")
    assert synchronize_budget(binding, control)["charged_estimate"] == "0.0048"
    state = json.loads((tmp_path / "amount-budget/state.json").read_text())
    requests = {row.get("request_id") for row in state["_attempts"].values()}
    assert requests == {"request-one", "later-request"}


def test_amount_mode_requires_stable_budget_reference(task_file, tmp_path):
    task = json.loads(task_file.read_text())
    task["authorization"]["mode"] = "amount"
    task_file.write_text(json.dumps(task))
    with pytest.raises(FrameworkError, match="budget_reference_required"):
        TaskBinding.prepare(task_file, tmp_path / "unbound-run")
    assert not (tmp_path / "unbound-run").exists()
