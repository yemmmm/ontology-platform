"""R3.0-011 G3 routing tests (v3 execution-gap closure, design §3.G3).

Covers test plan T-G3-1…T-G3-10: the appended public projection derived from
the single ``_cq_pool_questions`` replay, the map-only ``cq-slices-approved``
handoff on the real drain path (before any topology dependency), the
freeze-time projection, the recoverable projection/scenario-map consistency
feedback, the mid-phase ``cq_freeze_pending`` write-channel gate, and the
role-conditional task text.  No Agent process, no platform, no LLM.
"""

from __future__ import annotations

import hashlib
import json
import time as _time_module
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree

import pytest

from modeling_team.contracts import repository_root
from modeling_team.competency_questions import CQ_PUBLIC_PROJECTION_SCHEMA, CQContractError
from modeling_team.runner import TeamRunner
from modeling_team.staged_decisions import StagedSubmissionRejection
from modeling_team.tests.test_r30002_runner_wiring import FIXTURES, _gate_state
from modeling_team.tests.test_r3011_runner_wiring import (
    PROFILE,
    _CQRunner,
    _decision,
    _draft,
    _question,
    _read_evidence,
    _run_lifecycle_to_frozen,
    _slice_draft,
    _slice_question,
)
from modeling_team.tests.test_runner import CapturingAdapter

REPO_ROOT = repository_root()
FULL_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-006-real-full.yaml"
LEGACY_009_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-009-unified-graph-real.yaml"
LEGACY_PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml"

_UNIQUE = [0]


def _run_id() -> str:
    _UNIQUE[0] += 1
    seed = f"{_time_module.time()}-{_UNIQUE[0]}"
    return f"g3-{hashlib.sha256(seed.encode()).hexdigest()[:10]}"


class _G3Runner:
    """A prepared 011 runner over a chosen Task, cleaned up afterwards."""

    def __init__(self, task_path: Path) -> None:
        self.run_id = _run_id()
        self.run_root = REPO_ROOT / "workspaces" / "modeling-runs" / self.run_id
        self.adapter = CapturingAdapter()
        self.runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=self.adapter,
            ledger_root=self.run_root.parent / f"{self.run_id}-ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
        )
        self.task_path = task_path

    def prepare(self) -> TeamRunner:
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=self.task_path,
            scope={"mode": "create"},
        )
        return self.runner

    def cleanup(self) -> None:
        self.runner.cleanup()
        rmtree(self.run_root, ignore_errors=True)
        rmtree(self.run_root.parent / f"{self.run_id}-ledger", ignore_errors=True)


@pytest.fixture()
def cq_g3_runner():
    harness = _G3Runner(REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml")
    runner = harness.prepare()
    yield runner
    harness.cleanup()


def _public_dir(runner: TeamRunner) -> Path:
    return runner.run.root / "competency-questions" / "public"


def _projection_names(runner: TeamRunner) -> list[str]:
    return sorted(path.name for path in _public_dir(runner).glob("public-projection-*.json"))


def _cq_deliveries(runner: TeamRunner, kind: str) -> list:
    return [
        delivery
        for agent, delivery in runner.adapter.messages
        if agent == "competency-question" and delivery.kind == kind
    ]


# --- T-G3-1: the slice review appends a projection -----------------------------


def test_t_g3_1_slice_review_appends_a_public_projection(cq_g3_runner):
    runner = cq_g3_runner
    runner._publish_cq_question_draft(
        {
            "cq_id": "competency-question",
            "draft": _draft([_question("cq-1"), _question("cq-2", visibility="hidden")]),
        }
    )
    runner.handle_cq_outer_input(_decision(runner))
    first = (_public_dir(runner) / "public-projection-0001.json").read_bytes()
    assert [q["question_id"] for q in runner._cq_public_projection()["questions"]] == ["cq-1"]

    runner._publish_cq_question_draft(
        {
            "cq_id": "competency-question",
            "draft": _slice_draft(
                [
                    _slice_question("cq-3", visibility="public"),
                    _slice_question("cq-4", visibility="hidden"),
                ]
            ),
        }
    )
    runner.handle_cq_outer_input(_decision(runner, 2))

    # Append-only: the panorama projection file is untouched, one file added.
    assert _projection_names(runner) == [
        "public-projection-0001.json",
        "public-projection-0002.json",
    ]
    assert (_public_dir(runner) / "public-projection-0001.json").read_bytes() == first
    second = json.loads((_public_dir(runner) / "public-projection-0002.json").read_text("utf-8"))
    assert second["schema_version"] == CQ_PUBLIC_PROJECTION_SCHEMA
    # The highest ordinal is the complete current public set, not a delta.
    assert [q["question_id"] for q in second["questions"]] == ["cq-1", "cq-3"]
    assert second["questions"][1]["scope"]["kind"] == "slice"
    # Hidden questions (id and text) never reach the public directory.
    dump = "\n".join(
        path.read_text("utf-8") for path in _public_dir(runner).glob("*.json")
    )
    assert "cq-2" not in dump and "cq-4" not in dump


# --- T-G3-2: the projection is the pool filtered to public ---------------------


def test_t_g3_2_projection_equals_the_pool_filtered_to_public(cq_g3_runner):
    runner = cq_g3_runner
    runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1"), _question("cq-2")])}
    )
    runner.handle_cq_outer_input(_decision(runner))
    # One decision replay variant: delete cq-2 in a second decision.
    runner.handle_cq_outer_input(
        _decision(runner, 1, question_id="cq-2", decision="delete")
    )
    runner._publish_cq_question_draft(
        {
            "cq_id": "competency-question",
            "draft": _slice_draft(
                [_slice_question("cq-3", visibility="public"), _slice_question("cq-4")]
            ),
        }
    )
    runner.handle_cq_outer_input(_decision(runner, 2))

    pool, order = runner._cq_pool_questions()
    expected = [
        question["question_id"]
        for question in pool
        if question["proposed_visibility"] == "public"
    ]
    projection = runner._cq_public_projection()
    assert [q["question_id"] for q in projection["questions"]] == expected == ["cq-1", "cq-3"]
    assert order == ["cq-1", "cq-3", "cq-4"]

    # One decision replay only: the projection derives from _cq_pool_questions.
    calls = []
    original = runner._cq_pool_questions

    def counted():
        calls.append(1)
        return original()

    runner._cq_pool_questions = counted  # type: ignore[method-assign]
    try:
        runner._write_cq_public_projection("cq-review-0002")
    finally:
        del runner._cq_pool_questions
    assert calls == [1]


# --- T-G3-3: map-only handoff on the real drain path ---------------------------


@pytest.mark.parametrize("decision", ["modify", "supplement", "delete"])
def test_full_pool_slice_review_keeps_unique_ids_and_applies_later_decisions(
    cq_g3_runner, decision
):
    runner = cq_g3_runner
    panorama = [_question("cq-1"), _question("cq-2", visibility="hidden")]
    runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft(panorama)}
    )
    for question in panorama:
        runner.handle_cq_outer_input(_decision(runner, question_id=question["question_id"]))
    original_projection = (_public_dir(runner) / "public-projection-0001.json").read_bytes()

    full_pool = [
        *panorama,
        _slice_question("cq-3", visibility="public"),
        _slice_question("cq-4", visibility="hidden"),
    ]
    runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _slice_draft(full_pool)}
    )
    replacement = _question(
        "cq-1", question="reviewed replacement question?", content_version=2,
        answer_points=["reviewed replacement point"],
    )
    runner.handle_cq_outer_input(
        _decision(
            runner, 2, decision=decision,
            modified_question=None if decision == "delete" else replacement,
        )
    )
    for question in full_pool[1:]:
        runner.handle_cq_outer_input(_decision(runner, 2, question_id=question["question_id"]))
    runner.handle_cq_outer_input({"action": "cq_freeze"})

    frozen = runner._cq_freeze
    expected_order = ["cq-2", "cq-3", "cq-4"] if decision == "delete" else [
        "cq-1", "cq-2", "cq-3", "cq-4"
    ]
    assert frozen["ordering"] == expected_order
    assert [question["question_id"] for question in frozen["questions"]] == expected_order
    assert len(frozen["questions"]) == len(set(expected_order))
    assert {question["question_id"]: question["visibility"] for question in frozen["questions"]} == {
        question_id: "hidden" if question_id in {"cq-2", "cq-4"} else "public"
        for question_id in expected_order
    }
    if decision != "delete":
        assert frozen["questions"][0]["question"] == replacement["question"]
        assert frozen["questions"][0]["answer_points"] == replacement["answer_points"]
        assert frozen["questions"][0]["content_version"] == 2
    projection = runner._cq_public_projection()
    assert [question["question_id"] for question in projection["questions"]] == [
        question_id for question_id in expected_order if question_id in {"cq-1", "cq-3"}
    ]
    assert (_public_dir(runner) / "public-projection-0001.json").read_bytes() == original_projection


class _DrainTransport:
    results: dict = {}
    issue_escalation_enabled = False

    def drain(self):
        return []

    def stop(self):
        return None


def test_t_g3_3_drain_delivers_approved_slices_before_topology(cq_g3_runner):
    harness = _G3Runner(FULL_TASK)
    runner = harness.prepare()
    try:
        root = runner.run.root
        runner.transport = _DrainTransport()
        (root / "scenario-map" / "scenario-map.json").write_text(
            json.dumps(FIXTURES["scenario_map"]["valid"]), encoding="utf-8"
        )
        # No topology decision, no neutral candidate stage, no freeze.
        assert not (root / "scenario-map" / "topology-decision.json").exists()
        assert not (root / "stage3-neutral-graph" / "neutral-candidate.json").exists()
        assert list((root / "competency-questions" / "frozen").glob("*.json")) == []

        runner.drain()

        deliveries = _cq_deliveries(runner, "cq-slices-approved")
        assert len(deliveries) == 1, runner.adapter.messages
        payload = json.loads(deliveries[0].text)
        assert payload["slice_ids"] == ["S1", "S2", "S3", "S4", "S5"]
        assert payload["run_id"] == runner.run.run_id
        assert payload["scenario_map_digest"]
        # Bounded slice objects in the existing map schema, with meaningfully
        # different business scopes per slice.
        assert [set(item) for item in payload["slices"]] == [
            {"slice_id", "name", "scope", "owner", "status"}
        ] * len(payload["slices"])
        scopes = {item["slice_id"]: item["scope"] for item in payload["slices"]}
        assert len(set(scopes.values())) == len(scopes)
        assert scopes["S1"] != scopes["S2"]
        # The topology gate keeps its own state: closed without a decision.
        assert _gate_state(root)["state"] == "closed"
        assert runner._formal_failure_latched is False

        # Idempotent: a second drain re-delivers nothing for the same map.
        runner.drain()
        assert len(_cq_deliveries(runner, "cq-slices-approved")) == 1

        # A failed notification retries on a later drain.
        def _broken(kind, payload_text):
            raise RuntimeError("transport down")

        runner._deliver_to_cq = _broken  # type: ignore[method-assign]
        runner._cq_approved_slices_fingerprint = None
        runner.drain()
        events = _read_evidence(runner, "competency-questions")
        assert any(
            event.get("event") == "cq-slices-approved-delivery-failed" for event in events
        )
        del runner._deliver_to_cq
        runner.drain()
        assert len(_cq_deliveries(runner, "cq-slices-approved")) == 2
    finally:
        harness.cleanup()


def test_t_g3_3_no_map_means_no_delivery(cq_g3_runner):
    harness = _G3Runner(FULL_TASK)
    runner = harness.prepare()
    try:
        runner.transport = _DrainTransport()
        runner.drain()
        assert _cq_deliveries(runner, "cq-slices-approved") == []
        # An unparsable or structurally invalid map is never delivered either.
        map_path = runner.run.root / "scenario-map" / "scenario-map.json"
        map_path.write_text("{not json", encoding="utf-8")
        runner.drain()
        assert _cq_deliveries(runner, "cq-slices-approved") == []
        map_path.write_text(
            json.dumps({"schema_version": "r3-0-002-scenario-map/v1"}), encoding="utf-8"
        )
        runner.drain()
        assert _cq_deliveries(runner, "cq-slices-approved") == []
    finally:
        harness.cleanup()


# --- T-G3-4: the freeze projection equals the frozen public set -----------------


def test_t_g3_4_freeze_projection_matches_the_frozen_public_set(cq_g3_runner):
    runner = cq_g3_runner
    ack = _run_lifecycle_to_frozen(runner)
    root = runner.run.root
    snapshot = json.loads(
        (root / "competency-questions" / "frozen" / "freeze-0001.json").read_text("utf-8")
    )
    public_ids = [
        question["question_id"]
        for question in snapshot["questions"]
        if question["visibility"] == "public"
    ]
    projection = runner._cq_public_projection()
    assert projection["snapshot_digest"] == ack["snapshot_digest"]
    assert [q["question_id"] for q in projection["questions"]] == public_ids == ["cq-1"]
    # Panorama review, slice review and freeze each appended one projection.
    assert _projection_names(runner) == [
        "public-projection-0001.json",
        "public-projection-0002.json",
        "public-projection-0003.json",
    ]
    # frozen/ stays host-only (0700); the v3 run contract is still published.
    assert (root / "competency-questions" / "frozen").stat().st_mode & 0o777 == 0o700
    assert (root / "acceptance-v3" / "run-contract.json").is_file()
    # The evidence carries ids and digests, never hidden question text.
    text = (root / "evidence" / "cq-public-projection.jsonl").read_text("utf-8")
    for question in snapshot["questions"]:
        if question["visibility"] == "hidden":
            assert question["question"] not in text
            assert question["question_id"] not in text


# --- T-G3-5: the handoff is typed-rejected on a disagreeing map -----------------


def test_t_g3_5_handoff_rejects_a_map_that_disagrees_with_the_projection(cq_g3_runner):
    runner = cq_g3_runner
    ack = _run_lifecycle_to_frozen(runner)
    map_path = runner.run.root / "scenario-map" / "scenario-map.json"
    map_path.write_text(
        json.dumps(
            {
                "cross_slice_competency_questions": [
                    {
                        "question_id": "cq-minted",
                        "question": "invented question text",
                        "spans_slices": ["S1"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    runner.transport = type(
        "_Stub",
        (),
        {
            "results": {
                agent.agent_id: type("R", (), {"status": "completed"})()
                for agent in runner.run.configuration.profile.agents
                if agent.package.role in {"coordinator", "modeling", "protocol"}
            },
            "stop": lambda self: None,
        },
    )()
    message = {
        "action": "cq_handoff_complete",
        "freeze_id": ack["freeze_id"],
        "freeze_digest": ack["snapshot_digest"],
        "delivery_binding": {"delivery_id": "d1"},
    }
    with pytest.raises(CQContractError) as error:
        runner.handle_cq_outer_input(message)
    assert error.value.data["reason_code"] == "cq_projection_scenario_map_mismatch"
    assert runner._formal_failure_latched is False

    # Either repair releases the same message: align the map with the
    # published projection (no rewording).
    projected = runner._cq_public_projection()["questions"][0]
    map_path.write_text(
        json.dumps(
            {
                "cross_slice_competency_questions": [
                    {
                        "question_id": projected["question_id"],
                        "question": projected["question"],
                        "spans_slices": ["S1"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    ack_result = runner.handle_cq_outer_input(message)
    assert ack_result["ok"] is True


# --- T-G3-6: recoverable Coordinator feedback on a mismatch ---------------------


def test_t_g3_6_projection_write_gives_coordinator_recoverable_feedback(cq_g3_runner):
    runner = cq_g3_runner
    map_path = runner.run.root / "scenario-map" / "scenario-map.json"
    map_path.write_text(
        json.dumps(
            {
                "cross_slice_competency_questions": [
                    {
                        "question_id": "cq-minted",
                        "question": "invented question text",
                        "spans_slices": ["S1"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1")])}
    )
    runner.handle_cq_outer_input(_decision(runner))

    events = _read_evidence(runner, "cq-projection-consistency")
    assert events and events[-1]["event"] == "cross-slice-projection-mismatch"
    feedback = [
        (agent, delivery)
        for agent, delivery in runner.adapter.messages
        if delivery.kind == "cq-projection-feedback"
    ]
    assert len(feedback) == 1
    agent, delivery = feedback[0]
    assert agent.endswith("coordinator")
    notice = json.loads(delivery.text)
    assert notice["reason_code"] == "cq_projection_scenario_map_mismatch"
    assert "invented question text" not in delivery.text
    # The run is alive: the panorama phase completed normally.
    assert runner._cq_phase == "awaiting-slices"
    assert runner._formal_failure_latched is False


# --- T-G3-7: the mid-phase write-channel freeze gate ----------------------------


def test_t_g3_7_unfrozen_pool_blocks_the_staged_write_channel(cq_g3_runner):
    runner = cq_g3_runner
    with pytest.raises(StagedSubmissionRejection) as error:
        runner._handle_staged_submit_modeling_batch({})
    assert error.value.data["reason_code"] == "cq_freeze_pending"

    _run_lifecycle_to_frozen(runner)
    with pytest.raises(StagedSubmissionRejection) as after:
        runner._handle_staged_submit_modeling_batch({})
    assert after.value.data["reason_code"] != "cq_freeze_pending"


# --- T-G3-8: legacy runs keep the baseline text and no freeze gate --------------


def test_t_g3_8_legacy_run_has_no_cq_gate_or_text(tmp_path):
    run_id = _run_id()
    run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
    runner = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=CapturingAdapter(),
        ledger_root=tmp_path / "ledger",
        freeze_started_at=datetime.now(UTC).isoformat(),
    )
    try:
        runner.prepare(
            run_id=run_id,
            profile_path=LEGACY_PROFILE,
            task_path=LEGACY_009_TASK,
            scope={"mode": "create"},
        )
        assert runner._competency_questions is False
        for role in ("coordinator", "modeling", "protocol"):
            text = runner._task_text(role)
            assert "competency-questions/public" not in text
            assert "cq-slices-approved" not in text
            assert "exactly once before ending" in text
        with pytest.raises(StagedSubmissionRejection) as error:
            runner._handle_staged_submit_modeling_batch({})
        assert error.value.data["reason_code"] != "cq_freeze_pending"
    finally:
        runner.cleanup()
        rmtree(run_root, ignore_errors=True)


# --- T-G3-9: the 011 task text is role conditional ------------------------------


def test_t_g3_9_task_text_is_role_conditional_on_011_runs(cq_g3_runner):
    runner = cq_g3_runner
    cq_text = runner._task_text("competency-question")
    for needle in (
        "cq-slices-approved",
        "cq_publish_question_draft",
        "cq-review-decision",
        "hidden question text",
    ):
        assert needle in cq_text, needle
    for role in ("coordinator", "modeling", "protocol"):
        text = runner._task_text(role)
        assert "/agent/work/competency-questions/public/" in text
        assert "highest-ordinal public-projection-*.json" in text
        assert "sole legal source of the competency-question set" in text
        # Narrowed wording: public business meaning may be modeled with
        # provenance; raw dumps and hidden material stay excluded.
        assert "public business meaning" in text
        assert "hidden material" in text
        assert "exactly once before ending" in text

    # Formal-only R2.3-005 acceptance text must not reach this non-formal staged
    # run; the CQ duties asserted above are what stays.
    for role in ("coordinator", "modeling", "protocol"):
        text = runner._task_text(role)
        for phrase in ("acceptance_start", "coordinator_ticket_draft", "Acceptance have each reported"):
            assert phrase not in text, (role, phrase)
    assert "ready_for_acceptance" not in runner._task_text("modeling")
    assert "Modeling, Protocol, and Acceptance" not in runner._task_text("coordinator")
    assert (
        "Modeling and Protocol have each reported completed or blocked"
        in runner._task_text("coordinator")
    )


# --- T-G3-10: the consistency verify runs inside the real flow ------------------


def test_t_g3_10_consistency_verify_runs_in_the_real_projection_flow(cq_g3_runner):
    runner = cq_g3_runner
    entry = {
        "question_id": "cq-1",
        "question": "placeholder question cq-1?",
        "spans_slices": ["S1"],
    }
    (runner.run.root / "scenario-map" / "scenario-map.json").write_text(
        json.dumps({"cross_slice_competency_questions": [entry]}), encoding="utf-8"
    )
    runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1")])}
    )
    runner.handle_cq_outer_input(_decision(runner))
    events = _read_evidence(runner, "cq-projection-consistency")
    assert events and events[-1]["event"] == "cross-slice-projection-consistent"
    assert [
        delivery.kind
        for _agent, delivery in runner.adapter.messages
        if delivery.kind == "cq-projection-feedback"
    ] == []
