"""Cooperative idle inquiry: nudge the Coordinator when the run goes silent.

R2.3-009 start10/12 (2026-08-21): between the initial slice assignment and
the first candidate dispatch no component owns progress.  A Coordinator that
receives a Modeling clarification and never files the owner question (or a
capability probe that gives up) idles with every role quiet, and the only
remaining watchdog is the 5400s run-fallback timeout — the whole round is
burned for a stall a single inquiry could have rescued.  These tests lock
the mechanical behavior of ``TeamRunner._check_cooperative_idle``.

R2.3-009 start15 (2026-08-21): the original per-run budget of two inquiries
was consumed while legitimately waiting for an owner answer; the real
protocol/modeling deadlock an hour later then got no inquiry at all.  The
inquiry is therefore no longer budget-capped — the idle window between two
inquiries is the only rate limit.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from modeling_team.acceptance import RunnerAcceptanceCarrier
from modeling_team.runtimes.base import AgentState
from modeling_team.runner import TeamRunner


class _IdleAdapter:
    """Minimal adapter double exposing the two activity surfaces."""

    def __init__(self, *, running: bool = False, last_output: float = 0.0) -> None:
        self.sent: list[tuple[str, Any]] = []
        self.running = running
        self.last_output = last_output

    def get_agent_states(self) -> list[AgentState]:
        return [AgentState("coordinator", "running" if self.running else "idle")]

    def last_output_monotonic(self) -> float:
        return self.last_output

    def send_message(self, agent_id: str, delivery: Any) -> Any:
        self.sent.append((agent_id, delivery))
        return SimpleNamespace(mode="dispatch", turn_id="turn-1")


def _idle_runner(
    tmp_path: Path,
    adapter: _IdleAdapter,
    *,
    now: list[float],
    acceptance: RunnerAcceptanceCarrier | None = None,
) -> TeamRunner:
    agents = [
        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
        for role in ("modeling", "protocol", "coordinator", "acceptance")
    ]
    configuration = SimpleNamespace(
        task=SimpleNamespace(schema_version=2, task_id="r2-3-009-formal-acceptance"),
        profile=SimpleNamespace(
            profile_id="r2-3-009-modeling-team",
            agents=agents,
            parameters={},
        ),
    )
    run_root = tmp_path / "run"
    (run_root / "evidence").mkdir(parents=True, exist_ok=True)
    runner = TeamRunner(
        repository_root=tmp_path,
        adapter=adapter,
        monotonic_clock=lambda: now[0],
    )
    runner.run = SimpleNamespace(
        run_id="run-1",
        root=run_root,
        scope={"mode": "create"},
        configuration=configuration,
        formal_contract=SimpleNamespace(requirement_id="R2.3-009"),
    )
    runner.acceptance = acceptance
    runner._idle_inquiry_seconds = 300.0
    runner._idle_inquiries_sent = 0
    runner._idle_inquiry_baseline = 1000.0
    return runner


def test_idle_run_sends_one_bounded_inquiry_to_coordinator(tmp_path: Path) -> None:
    now = [1300.0]
    adapter = _IdleAdapter(last_output=1000.0)
    runner = _idle_runner(tmp_path, adapter, now=now)
    runner._check_cooperative_idle()
    assert len(adapter.sent) == 1
    recipient, delivery = adapter.sent[0]
    assert recipient == "coordinator"
    assert delivery.kind == "idle-inquiry"
    assert delivery.sender_id == "runner/idle-inquiry"
    assert "300" in delivery.text
    evidence = [
        json.loads(line)
        for line in (tmp_path / "run" / "evidence" / "idle-inquiry.jsonl").read_text().splitlines()
    ]
    assert evidence[0]["inquiry_count"] == 1
    assert evidence[0]["idle_seconds"] == pytest.approx(300.0)
    # A second call inside the same idle window is suppressed by the reset
    # baseline; the next inquiry must wait a full window again.
    runner._check_cooperative_idle()
    assert len(adapter.sent) == 1


def test_inquiries_repeat_every_idle_window_without_budget_cap(tmp_path: Path) -> None:
    # start15: the two-inquiry budget was spent waiting for an owner answer,
    # so the later deadlock got no inquiry.  The idle window is now the only
    # rate limit: every further full window of silence sends one more
    # inquiry, indefinitely.
    now = [3000.0]
    adapter = _IdleAdapter(last_output=1000.0)
    runner = _idle_runner(tmp_path, adapter, now=now)
    for _ in range(4):
        now[0] += 300.0
        runner._check_cooperative_idle()
    assert len(adapter.sent) == 4
    evidence = [
        json.loads(line)
        for line in (tmp_path / "run" / "evidence" / "idle-inquiry.jsonl")
        .read_text()
        .splitlines()
    ]
    assert [record["inquiry_count"] for record in evidence] == [1, 2, 3, 4]


def test_running_turn_or_recent_activity_suppresses_inquiry(tmp_path: Path) -> None:
    # A role mid-turn must never look idle.
    now = [1300.0]
    adapter = _IdleAdapter(running=True, last_output=1000.0)
    runner = _idle_runner(tmp_path, adapter, now=now)
    runner._check_cooperative_idle()
    assert adapter.sent == []

    # Fresh activity inside the idle window is not idle either.
    adapter = _IdleAdapter(last_output=1200.0)
    runner = _idle_runner(tmp_path, adapter, now=now)
    runner._check_cooperative_idle()
    assert adapter.sent == []


def test_open_candidate_channel_suppresses_inquiry(tmp_path: Path) -> None:
    # A candidate handoff in flight owns progress; the candidate nudges
    # watch it, so the idle inquiry must stay silent.
    now = [1300.0]
    adapter = _IdleAdapter(last_output=1000.0)
    runner = _idle_runner(tmp_path, adapter, now=now)
    runner._candidate_progress = SimpleNamespace(channel_open=True)
    runner._check_cooperative_idle()
    assert adapter.sent == []


def test_completed_candidate_channel_no_longer_suppresses_inquiry(tmp_path: Path) -> None:
    # R2.3-009 start17 (2026-08-21): after the candidate receipt was accepted
    # the pending record stays alive with state "complete" forever, so the old
    # ``pending is not None`` gate muted the idle inquiry for the rest of the
    # run — the post-candidate protocol/modeling stall got no inquiry at all.
    # A terminal (completed/exhausted/failed) candidate channel is closed and
    # must not suppress the inquiry.
    now = [1300.0]
    adapter = _IdleAdapter(last_output=1000.0)
    runner = _idle_runner(tmp_path, adapter, now=now)
    runner._candidate_progress = SimpleNamespace(channel_open=False)
    runner._check_cooperative_idle()
    assert len(adapter.sent) == 1


def test_live_acceptance_children_suppress_inquiry(tmp_path: Path) -> None:
    now = [1300.0]
    adapter = _IdleAdapter(last_output=1000.0)
    carrier = SimpleNamespace(has_live_children=True)
    runner = _idle_runner(tmp_path, adapter, now=now, acceptance=carrier)
    runner._check_cooperative_idle()
    assert adapter.sent == []


def test_carrier_has_live_children_tracks_child_lifecycle(tmp_path: Path) -> None:
    carrier = RunnerAcceptanceCarrier(
        tmp_path / "carrier", task_id="task-idle", acceptance_id="acceptance"
    )
    # A fresh carrier has no rounds, and a round without children (the state
    # after recycle) is not live; a child binding makes it live.
    assert carrier.has_live_children is False
    carrier._rounds["round-1"] = {"children": {}}
    assert carrier.has_live_children is False
    carrier._rounds["round-1"]["children"]["platform"] = object()
    assert carrier.has_live_children is True
