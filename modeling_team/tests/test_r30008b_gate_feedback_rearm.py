"""Staged-gate feedback re-arm on changed content (auth008-start1 forensics).

auth008-start1 (2026-09-11): ``_deliver_staged_gate_feedback`` deduplicated by
``recipient:reason_code:artifact`` only.  The Modeling role kept producing
conclusions with list-valued enum fields; every later issue of the same
reason code on the same artifact — even naming different conclusions and
fields — was silently dropped, so the Coordinator received one notice and the
run idled to its fallback timeout.  The fingerprint must therefore include
the issue content: same content stays deduplicated, changed content re-arms
the notice.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from modeling_team.runner import TeamRunner

CONCLUSIONS_ARTIFACT = "value-semantics/conclusions/analysis-conclusions.json"


class _RecordingAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, Any]] = []

    def send_message(self, agent_id: str, delivery: Any) -> Any:
        self.sent.append((agent_id, delivery))
        return SimpleNamespace(mode="dispatch", turn_id="turn-1")


def _gate_runner(tmp_path: Path, adapter: _RecordingAdapter) -> TeamRunner:
    """A staged, non-formal v3 run double (r3-0-006-real-full + CQ profile)."""

    agents = [
        SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
        for role in ("modeling", "protocol", "coordinator", "cq")
    ]
    configuration = SimpleNamespace(
        task=SimpleNamespace(schema_version=2, task_id="r3-0-006-real-full"),
        profile=SimpleNamespace(
            profile_id="r3-0-011-competency-question",
            agents=agents,
            parameters={},
        ),
    )
    run_root = tmp_path / "run"
    (run_root / "evidence").mkdir(parents=True, exist_ok=True)
    runner = TeamRunner(
        repository_root=tmp_path,
        adapter=adapter,
        monotonic_clock=lambda: 0.0,
    )
    runner.run = SimpleNamespace(
        run_id="run-1",
        root=run_root,
        scope={"mode": "create"},
        configuration=configuration,
        formal_contract=None,
    )
    runner._staged_decisions = True
    return runner


def test_same_content_gate_feedback_is_delivered_once(tmp_path: Path) -> None:
    adapter = _RecordingAdapter()
    runner = _gate_runner(tmp_path, adapter)
    runner._deliver_staged_gate_feedback("conclusions_schema_mismatch", CONCLUSIONS_ARTIFACT)
    runner._deliver_staged_gate_feedback("conclusions_schema_mismatch", CONCLUSIONS_ARTIFACT)
    assert len(adapter.sent) == 1
    assert adapter.sent[0][0] == "coordinator"
    assert adapter.sent[0][1].kind == "staged-decision-gate"


def test_changed_details_rearm_gate_feedback(tmp_path: Path) -> None:
    adapter = _RecordingAdapter()
    runner = _gate_runner(tmp_path, adapter)
    runner._deliver_staged_gate_feedback(
        "conclusions_schema_mismatch",
        CONCLUSIONS_ARTIFACT,
        details=("ac-0001:candidate_value is not a valid enum code set",),
    )
    runner._deliver_staged_gate_feedback(
        "conclusions_schema_mismatch",
        CONCLUSIONS_ARTIFACT,
        details=("ac-0002:business_meaning_hypothesis is empty",),
    )
    assert len(adapter.sent) == 2


def test_gate_notice_carries_issue_details(tmp_path: Path) -> None:
    import json

    adapter = _RecordingAdapter()
    runner = _gate_runner(tmp_path, adapter)
    runner._deliver_staged_gate_feedback(
        "conclusions_schema_mismatch",
        CONCLUSIONS_ARTIFACT,
        details=("beta detail", "alpha detail"),
    )
    notice = json.loads(adapter.sent[0][1].text)
    assert notice["reason_code"] == "conclusions_schema_mismatch"
    assert notice["artifact"] == CONCLUSIONS_ARTIFACT
    assert notice["details"] == ["alpha detail", "beta detail"]
