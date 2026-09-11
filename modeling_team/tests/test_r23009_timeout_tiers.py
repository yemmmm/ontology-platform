"""R2.3-009 timeout tiers: bounded nudges, cooperative escalation, one fallback.

The design replaces the two run-killing candidate timeouts
(``candidate-progress-timeout`` / ``candidate-redrive-exhausted``) with:

- T1: a ``candidate_progress_timeout_seconds`` deadline miss delivers one
  bounded nudge/redrive to Protocol (``candidate_redrive_limit``, default 3);
- T2: exhausted nudges or ``feedback_escalation_repeat`` (default 3) repeats of
  the same typed feedback open one cooperative issue via the Coordinator;
- T3: a run-level active clock ``run_fallback_timeout_seconds`` (default 5400,
  issue-pending time excluded) is the only remaining timeout latch
  (``run-fallback-timeout``) and still raises so the CLI cleanup path runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.candidate_progress import (
    FormalCandidateProgress,
    FormalCandidateProgressTimeout,
)
from modeling_team.contracts import TeamConfigurationError, load_profile, repository_root
from modeling_team.runner import TeamRunner
from modeling_team.transport_mcp import TeamTransportBroker
from modeling_team.runtimes.base import AgentState, RuntimeDispatchReceipt, RuntimeDelivery

from test_r23005_candidate_progress import _candidate


class _TierAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, RuntimeDelivery]] = []
        self.turns: dict[str, tuple[str | None, str | None]] = {"protocol": (None, None)}

    def send_message(self, recipient: str, delivery: RuntimeDelivery):
        self.sent.append((recipient, delivery))
        if recipient == "protocol" and delivery.kind == "peer":
            self.turns["protocol"] = ("turn-1", "turn-1")
            return RuntimeDispatchReceipt("start", "turn-1")
        if recipient == "protocol" and delivery.kind == "candidate-redrive":
            self.turns["protocol"] = ("turn-2", "turn-2")
            return RuntimeDispatchReceipt("start", "turn-2")
        return RuntimeDispatchReceipt("start", "other-turn")

    def receive_messages(self):
        return []

    def get_agent_states(self):
        started, completed = self.turns["protocol"]
        return [AgentState("protocol", "idle", started, completed)]


class _LedgerState:
    def __init__(self, pending: bool) -> None:
        self.pending = pending


class _FakeIssueTransport:
    issue_escalation_enabled = False

    def __init__(self, *, pending: bool = False) -> None:
        self.issue_ledger = _LedgerState(pending)
        self.reported: list[dict[str, object]] = []

    def drain(self):
        return []

    def requeue(self, deliveries):
        return None

    def report_issue(self, reporter_id, **arguments):
        self.reported.append({"reporter": reporter_id, **arguments})
        return {"issue_id": f"issue-{len(self.reported)}"}


def _tier_runner(
    tmp_path: Path,
    adapter: _TierAdapter,
    clock,
    *,
    issue_escalation_enabled: bool = False,
    redrive_limit: int = 3,
    timeout_seconds: float = 120.0,
) -> TeamRunner:
    agents = [
        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
        for role in ("modeling", "protocol", "coordinator", "acceptance")
    ]
    configuration = SimpleNamespace(
        task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
        profile=SimpleNamespace(profile_id="r2-3-005-modeling-team", agents=agents, parameters={}),
    )
    run_root = tmp_path / "run"
    (run_root / "evidence").mkdir(parents=True, exist_ok=True)
    runner = TeamRunner(repository_root=tmp_path, adapter=adapter, monotonic_clock=clock)
    runner.run = SimpleNamespace(
        run_id="run-1", root=run_root, scope={"mode": "create"}, configuration=configuration
    )
    permissions = {("modeling", "protocol"), ("protocol", "modeling")}
    if issue_escalation_enabled:
        permissions.update({("modeling", "coordinator"), ("coordinator", "modeling")})
    broker_kwargs: dict[str, object] = {"issue_escalation_enabled": issue_escalation_enabled}
    if issue_escalation_enabled:
        # Mirror the production closure: ``_handle_issue_events`` swaps the
        # queue list, so the callback must resolve the attribute at call time.
        def issue_event_callback(event: dict[str, object]) -> None:
            runner._issue_event_queue.append(event)

        broker_kwargs["issue_event_callback"] = issue_event_callback
    runner.transport = TeamTransportBroker(
        run_root / "broker",
        permissions,
        modeling_agent_id="modeling",
        coordinator_agent_id="coordinator",
        terminal_dependencies={},
        **broker_kwargs,
    )
    runner._candidate_progress = FormalCandidateProgress(
        clock=clock, timeout_seconds=timeout_seconds, redrive_limit=redrive_limit
    )
    return runner


def _evidence(runner: TeamRunner, name: str) -> list[dict[str, object]]:
    path = runner.run.root / "evidence" / f"{name}.jsonl"  # type: ignore[union-attr]
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _send_original_candidate(runner: TeamRunner) -> None:
    runner.transport.send(
        "modeling",
        "protocol",
        json.dumps(_candidate(), ensure_ascii=False, separators=(",", ":")),
        expects_reply=True,
    )


def test_t1_deadline_miss_is_a_bounded_nudge_not_a_kill(tmp_path: Path) -> None:
    now = [0.0]
    adapter = _TierAdapter()
    runner = _tier_runner(tmp_path, adapter, lambda: now[0], timeout_seconds=10.0)
    _send_original_candidate(runner)
    # The first drain dispatches the candidate; the completed Protocol turn
    # without a typed response already delivers the first bounded nudge.
    runner.drain()
    redrives = [delivery for _, delivery in adapter.sent if delivery.kind == "candidate-redrive"]
    assert len(redrives) == 1
    assert runner._nudges_sent == 1
    assert runner._formal_failure_latched is False
    assert runner._candidate_progress.state == "redrive_sent"  # type: ignore[union-attr]
    # The deadline is exceeded from here on; the miss stays a repeatable
    # boolean, never a latch or a raise.
    now[0] = 100.0
    assert runner._candidate_progress.check_deadline() is True  # type: ignore[union-attr]
    runner.drain()
    assert redrives[0].text  # the original candidate bytes are reused verbatim
    assert runner._formal_failure_latched is False
    events = [entry.get("event") for entry in _evidence(runner, "formal-candidate-progress")]
    assert "redrive_sent" in events


def test_t2_exhausted_nudges_open_one_cooperative_issue(tmp_path: Path) -> None:
    now = [0.0]
    adapter = _TierAdapter()
    runner = _tier_runner(
        tmp_path,
        adapter,
        lambda: now[0],
        issue_escalation_enabled=True,
        redrive_limit=1,
        timeout_seconds=10.0,
    )
    _send_original_candidate(runner)
    # Drain one: the turn-barrier nudge consumes the whole budget.
    runner.drain()
    assert runner._candidate_progress.pending.redrive_count == 1  # type: ignore[union-attr]
    now[0] = 100.0
    # Drain two: the redrive turn also completed without a typed response, so
    # the budget is spent and the Runner escalates cooperatively.
    runner.drain()
    assert runner._candidate_progress.redrive_exhausted is True  # type: ignore[union-attr]
    assert runner._issues_opened == 1
    escalation = _evidence(runner, "issue-escalation")
    assert escalation[-1]["reason_code"] == "candidate-stall"
    assert runner.transport.issue_ledger.pending is True
    # The issue callback is processed on the next drain and pauses the gate.
    runner.drain()
    assert runner._candidate_progress.paused is True  # type: ignore[union-attr]
    # The once-guard holds: further drains open no second issue.
    assert runner._issues_opened == 1


def test_t2_repeated_feedback_opens_one_issue_per_key(tmp_path: Path) -> None:
    now = [0.0]
    adapter = _TierAdapter()
    runner = _tier_runner(tmp_path, adapter, lambda: now[0])
    runner._feedback_escalation_repeat = 2
    transport = _FakeIssueTransport(pending=False)
    runner.transport = transport
    for index in range(3):
        runner._deliver_formal_feedback(
            issue_class="B",
            code="revision-not-strictly-newer",
            responsible_agent="modeling",
            original_delivery_id=f"delivery-{index}",
            detail="revision must strictly increase",
            remediation="send a strictly newer revision",
        )
    assert runner._feedback_counts[("B", "revision-not-strictly-newer", "modeling")] == 3
    assert len(transport.reported) == 1
    assert transport.reported[0]["reporter"] == "coordinator"
    assert transport.reported[0]["category"] == "protocol_guidance"
    escalation = _evidence(runner, "issue-escalation")
    assert escalation[-1]["reason_code"] == "repeated-validation-feedback"


def test_t3_run_fallback_timeout_latches_once_with_terminal_evidence(tmp_path: Path) -> None:
    now = [1000.0]
    adapter = _TierAdapter()
    runner = _tier_runner(tmp_path, adapter, lambda: now[0])
    runner._run_fallback_started = 0.0
    runner._run_fallback_timeout_seconds = 100.0
    runner._nudges_sent = 2
    runner._issues_opened = 1
    runner._last_responsible_agent = "modeling"
    with pytest.raises(FormalCandidateProgressTimeout, match="run fallback timeout"):
        runner.drain()
    assert runner._formal_failure_latched is True
    assert json.loads((tmp_path / "run" / "state.json").read_text())[
        "state"
    ] == "TERMINAL_FAILURE_PENDING_CLEANUP"
    terminal = _evidence(runner, "formal-candidate-terminal-failure")
    assert terminal[-1]["reason_code"] == "run-fallback-timeout"
    assert terminal[-1]["classification"] == "collaboration/routing"
    fallback = _evidence(runner, "run-fallback-timeout")
    assert fallback[-1]["nudges_sent"] == 2
    assert fallback[-1]["issues_opened"] == 1
    assert fallback[-1]["last_responsible_agent"] == "modeling"
    assert fallback[-1]["feedback_counts"] == {}
    # The latch is terminal: another drain does not raise again.
    runner.drain()


def test_t3_issue_pending_time_is_excluded_from_the_fallback_clock(tmp_path: Path) -> None:
    now = [1000.0]
    adapter = _TierAdapter()
    runner = _tier_runner(tmp_path, adapter, lambda: now[0])
    runner.transport = _FakeIssueTransport(pending=True)
    runner._run_fallback_started = 0.0
    runner._run_fallback_timeout_seconds = 100.0
    # A cooperative issue has been pending for almost the whole run.
    runner._issue_pending_started = 5.0
    runner.drain()
    assert runner._formal_failure_latched is False


def _formal_profile_with_parameters(tmp_path: Path, extra: str) -> Path:
    source = repository_root() / "modeling_team/profiles/r2-3-005-modeling-team.yaml"
    content = source.read_text(encoding="utf-8").replace(
        "  candidate_progress_timeout_seconds: 300\n",
        "  candidate_progress_timeout_seconds: 300\n" + extra,
    )
    path = tmp_path / "formal-profile.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_tier_parameters_load_from_the_formal_profile(tmp_path: Path) -> None:
    profile = load_profile(
        _formal_profile_with_parameters(
            tmp_path,
            "  candidate_redrive_limit: 5\n"
            "  feedback_escalation_repeat: 2\n"
            "  run_fallback_timeout_seconds: 1800\n",
        ),
        strict=True,
    )
    assert profile.parameters["candidate_redrive_limit"] == 5
    assert profile.parameters["feedback_escalation_repeat"] == 2
    assert profile.parameters["run_fallback_timeout_seconds"] == 1800


@pytest.mark.parametrize(
    "extra",
    [
        "  candidate_redrive_limit: 0\n",
        "  candidate_redrive_limit: -1\n",
        "  candidate_redrive_limit: true\n",
        "  candidate_redrive_limit: 1.5\n",
        "  feedback_escalation_repeat: 0\n",
        "  run_fallback_timeout_seconds: 0\n",
        "  run_fallback_timeout_seconds: -60\n",
        "  run_fallback_timeout_seconds: not-a-number\n",
    ],
)
def test_tier_parameters_reject_malformed_values(tmp_path: Path, extra: str) -> None:
    with pytest.raises(TeamConfigurationError):
        load_profile(_formal_profile_with_parameters(tmp_path, extra), strict=True)


def test_tier_parameters_are_restricted_to_the_formal_profile(tmp_path: Path) -> None:
    source = repository_root() / "modeling_team/profiles/base-three-agent.yaml"
    path = tmp_path / "nonformal-profile.yaml"
    path.write_text(
        source.read_text(encoding="utf-8").replace(
            "parameters: {}\n",
            "parameters:\n  candidate_redrive_limit: 3\n",
        ),
        encoding="utf-8",
    )
    with pytest.raises(TeamConfigurationError, match="restricted to the formal Profile"):
        load_profile(path)


def test_run_fallback_timeout_loads_from_the_cq_profile() -> None:
    path = repository_root() / "modeling_team/profiles/r3-0-011-competency-question.yaml"
    profile = load_profile(path, multi_slice=True)
    assert profile.parameters["run_fallback_timeout_seconds"] == 14400.0


def test_other_tier_parameters_stay_formal_only_for_the_cq_profile(
    tmp_path: Path,
) -> None:
    source = repository_root() / "modeling_team/profiles/r3-0-011-competency-question.yaml"
    for extra in ("  candidate_redrive_limit: 3\n", "  feedback_escalation_repeat: 2\n"):
        path = tmp_path / "cq-profile.yaml"
        path.write_text(
            source.read_text(encoding="utf-8").replace(
                "parameters:\n",
                "parameters:\n" + extra,
            ),
            encoding="utf-8",
        )
        with pytest.raises(TeamConfigurationError, match="restricted to the formal Profile"):
            load_profile(path, multi_slice=True)
