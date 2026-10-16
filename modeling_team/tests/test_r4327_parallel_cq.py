"""R4.3-027: execute the real CQ carrier; replace only external model work."""
from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest

from modeling_team.acceptance_runtime import ChildRuntimeError
from modeling_team.evaluation_owner import EvaluationOwner, EvaluationStopped
from modeling_team.tests.test_r3011_acceptance import _question
from modeling_team.tests.test_r3012_partial_judging import _batch_adapter
from modeling_team.tests.test_r3012_platform_responses import (
    _DualForwarder, _RETAINED_QUERY_RESULT, _platform_context, _read_report,
    _run_cli, _write_handoff, _write_run_root,
)


@pytest.mark.parametrize("count,failed", [(5, None), (5, "cq-2"), (2, None)])
def test_parallel_questions_overlap_refill_and_preserve_full_results(
    tmp_path, capsys, monkeypatch, count, failed,
):
    questions = [_question(f"cq-{i}") for i in range(1, count + 1)]
    run_root, frozen = _write_run_root(tmp_path, questions)
    handoff = _write_handoff(tmp_path, frozen)
    base, _ = _batch_adapter()
    barrier = threading.Barrier(min(3, count))
    fourth_started = threading.Event()
    lock = threading.Lock()
    active = peak = 0
    completed = []

    class Adapter(base):
        def run_v3_acceptance_child(self, packet, **kwargs):
            nonlocal active, peak
            if kwargs.get("platform_forwarder") is None:
                return super().run_v3_acceptance_child(packet, **kwargs)
            # A whole-pool packet cannot satisfy independent question execution.
            assert len(packet.payload["questions"]) == 1
            qid = packet.payload["questions"][0]["question_id"]
            assert "answer_points" not in packet.payload["questions"][0]
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                if qid in {"cq-1", "cq-2", "cq-3"}:
                    barrier.wait(timeout=2)
                if count > 3 and qid == "cq-1":
                    assert fourth_started.wait(2), "no slot refill while first question waits"
                if qid == "cq-4":
                    fourth_started.set()
                if qid == failed:
                    raise ChildRuntimeError("question-specific external failure")
                return super().run_v3_acceptance_child(packet, **kwargs)
            finally:
                with lock:
                    active -= 1
                    completed.append(qid)

    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT] * count)
    code = _run_cli(tmp_path, run_root, handoff, forwarder, Adapter, monkeypatch)
    capsys.readouterr()
    report = _read_report(run_root, frozen["batch_id"])
    assert peak == min(3, count)
    assert sorted(completed) == [f"cq-{i}" for i in range(1, count + 1)]
    assert report["full_pass"] is (failed is None)
    assert code == (0 if failed is None else 1)
    assert report["unexecuted_question_ids"] == ([] if failed is None else [failed])
    assert [r["question_id"] for r in report["examiner_reports"]] == [
        f"cq-{i}" for i in range(1, count + 1) if f"cq-{i}" != failed]
    tasks = report["sessions"]["platform_examiner"]["tasks"]
    assert [t["question_id"] for t in tasks] == [f"cq-{i}" for i in range(1, count + 1)]
    assert max(t["started_offset_seconds"] for t in tasks[:min(3, count)]) < min(
        t["finished_offset_seconds"] for t in tasks[:min(3, count)])
    assert len({t["packet_digest"] for t in tasks}) == count
    assert len({t["model_binding_digest"] for t in tasks}) == 1
    # Every independent child issues p0. All must retain their own artifact.
    assert len({v[0]["artifact_path"] for v in report["platform_read_responses"].values()}) == count - bool(failed)
    assert report["sessions"]["platform_read_responses"]["rejected_refs"] == []
    if failed:
        failure = next(t for t in tasks if t["question_id"] == failed)
        assert "question-specific external failure" in json.dumps(failure)


def test_owner_controls_all_active_questions_and_retains_without_losing_peers(tmp_path):
    owner = EvaluationOwner(tmp_path)
    resources = []
    confirmations_during_dispatch = []

    class Adapter:
        def __init__(self):
            self.agents = {}

        def receive_messages(self):
            return []

        def send_message(self, agent_id, delivery):
            message = json.loads(delivery.text)
            resource = next(r for r in resources if r._child_agent.agent_id == agent_id)
            confirmation = threading.Thread(target=owner.confirm, args=(resource, {
                "request_id": message["request_id"], "action": message["action"]}))
            confirmation.start()
            confirmation.join(1)
            confirmations_during_dispatch.append(not confirmation.is_alive())
            return SimpleNamespace(mode="steer")

    def send(action):
        with (tmp_path / "input.fifo").open("w") as stream:
            stream.write(json.dumps({"request_id": action, "action": action, "text": action}) + "\n")
        owner.poll()

    try:
        for i in range(3):
            resource = SimpleNamespace(
                spec={"v3_role": "platform-examiner"}, thread_id=f"thread-{i}",
                process=SimpleNamespace(poll=lambda: None, pid=100 + i),
                user_waiting=False,
                _child_agent=SimpleNamespace(agent_id=f"agent-{i}"),
                _watchdog_stop=threading.Event(),
            )
            resources.append(resource)
            owner.bind(Adapter(), resource)
        send("pause")
        assert all(r.user_waiting for r in resources)
        assert owner.receipts["pause"]["status"] == "effective"
        # Another already-launching child can finish startup after pause was
        # dispatched. It must receive that same actual request on binding.
        late = SimpleNamespace(
            spec={"v3_role": "platform-examiner"}, thread_id="thread-late",
            process=SimpleNamespace(poll=lambda: None, pid=103), user_waiting=False,
            _child_agent=SimpleNamespace(agent_id="agent-late"), _watchdog_stop=threading.Event(),
        )
        resources.append(late)
        owner.bind(Adapter(), late)
        assert late.user_waiting
        send("resume")
        assert all(not r.user_waiting for r in resources)
        assert confirmations_during_dispatch == [True] * 8
        owner.retain(resources[1])
        state = json.loads((tmp_path / "state.json").read_text())
        assert {r["thread_id"] for r in state["active_members"]} == {"thread-0", "thread-2", "thread-late"}
        assert state["retained_members"][0]["thread_id"] == "thread-1"
        with pytest.raises(EvaluationStopped):
            send("stop")
        with pytest.raises(EvaluationStopped):
            owner.before_next_task()
    finally:
        # These resources have no external process; close only the real owner FIFO.
        owner.retained.clear()
        if hasattr(owner, "active"):
            owner.active.clear()
        owner.current = None
        owner.close()


def test_native_cli_runs_five_questions_with_three_overlapping_children(tmp_path):
    from modeling_team.tests.test_r3011_acceptance_cli_flow import (
        _build_scenario, _run_cli as run_native, _assert_batch_cleanup, _assert_no_key_leak,
    )
    result = run_native(_build_scenario(tmp_path, question_count=5))
    assert result["proc"].returncode == 0, result["proc"].stderr
    report = result["report"]
    assert report["full_pass"] and len(report["verdicts"]) == 5
    tasks = report["sessions"]["platform_examiner"]["tasks"]
    assert len({t["teardown"]["thread_id"] for t in tasks}) == 5
    assert max(t["started_offset_seconds"] for t in tasks[:3]) < min(
        t["finished_offset_seconds"] for t in tasks[:3])
    events = sorted([(t["started_offset_seconds"], 1) for t in tasks] + [
        (t["finished_offset_seconds"], -1) for t in tasks])
    active = peak = 0
    for _, delta in events:
        active += delta
        peak = max(peak, active)
    assert peak == 3 and active == 0
    assert tasks[3]["started_offset_seconds"] >= min(t["finished_offset_seconds"] for t in tasks[:3])
    assert all(t["model_usage"]["output_tokens"] > 0 for t in tasks)
    assert all("provider cost not reconciled" in t["usage_gap"] for t in tasks)
    _assert_batch_cleanup(report, expected_children=6)
    _assert_no_key_leak(result)
    assert result["final_owner"]["lifecycle"] == "stopped"
    assert not result["new_private_roots"]
