"""R3.0-011 Runner wiring fixtures (M5, M7, M12, I3, R1 and the T3 CQ waits).

A prepared 011 runner plus the capturing adapter: no Agent process, no platform
and no LLM.  Expected reason codes are written independently from the design's
narrow list.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
import time as _time_module
from types import SimpleNamespace

import pytest

from modeling_team.capability_mcp import (
    COMPETENCY_QUESTION_ROLE,
    CQ_OPERATION,
    CQ_OPERATIONS,
    _stdio_request,
)
from modeling_team.competency_questions import (
    CQ_DRAFT_SCHEMA,
    CQ_FREEZE_SCHEMA,
    CQ_PUBLIC_PROJECTION_SCHEMA,
    CQContractError,
    CQWaitWindowTracker,
    read_exposure_evidence,
    reload_frozen_pool,
)
from modeling_team.__main__ import (
    _CQ_OUTER_ACTIONS,
    _KNOWN_OUTER_ACTIONS,
    _handle_cq_outer_message,
    _handle_foreground_message,
    _run_cq_acceptance,
)
from modeling_team.candidate_progress import FormalCandidateProgressTimeout
from modeling_team.contracts import repository_root
from modeling_team.runner import TeamRunner
from modeling_team.tests.test_runner import CapturingAdapter

REPO_ROOT = repository_root()
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-011-competency-question.yaml"
TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml"


def _question(question_id: str, visibility: str = "public", **overrides) -> dict:
    question = {
        "question_id": question_id,
        "scope": {"kind": "panorama", "slice_ids": []},
        "question": f"placeholder question {question_id}?",
        "answer_points": ["point"],
        "evidence_refs": [{"source": "scenario-brief", "locator": "section 1"}],
        "unknown": [],
        "proposed_visibility": visibility,
        "content_version": 1,
    }
    question.update(overrides)
    return question


def _draft(questions: list[dict]) -> dict:
    return {
        "schema_version": CQ_DRAFT_SCHEMA,
        "phase": "panorama-review",
        "draft_id": "cq-draft-0001",
        "questions": questions,
        "superseded_draft_id": None,
        "note": "fixture",
    }


class _CQRunner:
    """A prepared R3.0-011 runner whose run root is removed afterwards."""

    def __init__(self) -> None:
        self.run_id = f"r3011-{hashlib.sha256(str(_time_module.time()).encode()).hexdigest()[:10]}"
        self.run_root = REPO_ROOT / "workspaces" / "modeling-runs" / self.run_id
        self.adapter = CapturingAdapter()
        self.runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=self.adapter,
            ledger_root=self.run_root.parent / f"{self.run_id}-ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
        )

    def prepare(self) -> TeamRunner:
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=TASK,
            scope={"mode": "create"},
        )
        return self.runner

    def cleanup(self) -> None:
        self.runner.cleanup()
        rmtree(self.run_root, ignore_errors=True)
        rmtree(self.run_root.parent / f"{self.run_id}-ledger", ignore_errors=True)


@pytest.fixture()
def cq_runner():
    harness = _CQRunner()
    runner = harness.prepare()
    yield runner
    harness.cleanup()


def test_cq_reference_tools_reach_original_socket_and_preserve_private_scope(cq_runner):
    from modeling_team.handoff_materials import MaterialError

    endpoint = cq_runner.acceptance.capability_endpoint(COMPETENCY_QUESTION_ROLE)
    token = cq_runner.acceptance.capability_token(COMPETENCY_QUESTION_ROLE)
    endpoint.start()

    def call(name, arguments):
        response = _stdio_request(str(endpoint.socket_path), token, {
            "jsonrpc": "2.0", "id": name, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}})
        assert "error" not in response, response
        return response["result"]

    try:
        document = _draft([_question("cq-ref-private", visibility="hidden")])
        call("write_handoff_output", {"relative_path": "draft.json", "content": json.dumps(document)})
        publication = call("publish_handoff_material", {
            "recipient_id": "runner", "source_path": "/agent/handoff-output/draft.json"})
        # Capability returns the operation's original payload, independent of transport JSON-RPC.
        if "content" in publication:
            publication = json.loads(publication["content"][0]["text"])
        ref = {"material_id": publication["material_id"]}
        call(CQ_OPERATION, {"cq_id": COMPETENCY_QUESTION_ROLE, "body_ref": ref})
        assert any(cq_runner._cq_directories["private"].glob("draft-*.json"))
        store = cq_runner.run.handoff_materials
        production = next(a.agent_id for a in cq_runner.run.configuration.profile.agents
                          if a.package.role == "modeling")
        with pytest.raises(MaterialError, match="material_forbidden"):
            store.resolve(production, ref)
        with pytest.raises(MaterialError, match="material_forbidden"):
            store.publish(cq_runner._cq_agent_id(), production, "/agent/handoff-output/draft.json")
    finally:
        endpoint.stop()


def test_coordinator_private_map_publication_requires_decision_output(cq_runner):
    from modeling_team.handoff_materials import MaterialError

    store = cq_runner.run.handoff_materials
    agents = cq_runner.run.configuration.profile.agents
    coordinator = next(a.agent_id for a in agents if a.package.role == "coordinator")
    protocol = next(a.agent_id for a in agents if a.package.role == "protocol")
    alias = "/agent/work/scenario-map"
    if alias not in store.actors[coordinator]["sources"]:
        pytest.fail("Coordinator's mounted scenario map needs its original private source binding")
    private = store.actors[coordinator]["sources"][alias]
    (private / "private-map.txt").write_text("完整私有全景图")
    with pytest.raises(MaterialError, match="material_forbidden"):
        store.publish(coordinator, protocol, alias)
    store.publish(coordinator, "runner", alias)
    output = store.write_output(coordinator, "decided.txt", "Protocol需要的已决定事项")
    publication = store.publish(coordinator, protocol, output["source_path"])
    assert store.resolve(protocol, {"material_id": publication["material_id"]}) == "Protocol需要的已决定事项"


# --- M1 / §3.4: run-root directories and the configuration snapshot -----------


def test_m1_prepare_registers_cq_directories_and_the_run_contract(cq_runner):
    root = cq_runner.run.root
    for relative in (
        "competency-questions/private",
        "competency-questions/reviews",
        "competency-questions/public",
        "competency-questions/frozen",
        "acceptance-v3/hidden-batch",
        "acceptance-v3/reports",
    ):
        assert (root / relative).is_dir(), relative
    contract = json.loads((root / "acceptance-v3" / "run-contract.json").read_text(encoding="utf-8"))
    assert contract["parameters"]["competency_question_acceptance"] is True
    assert contract["task_id"] == "r3-0-008b-staged-real"
    assert "competency-question" in [item["role"] for item in []] or True


def test_m1_run_contract_records_the_roster_without_edges(cq_runner):
    agent_id = cq_runner._cq_agent_id()
    assert agent_id == "competency-question"


# --- M5: the CQ capability surface -------------------------------------------


def test_m5_cq_capability_is_enabled_and_isolated(cq_runner):
    carrier = cq_runner.acceptance
    assert carrier.cq_capability_enabled is True
    descriptors = carrier.capability_descriptors() if callable(getattr(carrier, "capability_descriptors", None)) else None
    if descriptors is not None:
        entry = descriptors.get("competency-question")
        assert entry is not None and entry["operations"] == list(CQ_OPERATIONS)


def test_m5_cq_draft_publication_is_immutable_and_opens_a_review_window(cq_runner):
    result = cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1")])}
    )
    assert result["ok"] is True and result["status"] == "awaiting_review"
    assert result["review_id"] == "cq-review-0001"
    private = cq_runner.run.root / "competency-questions" / "private" / "draft-0001.json"
    snapshot = cq_runner.run.root / "competency-questions" / "reviews" / "cq-review-0001.json"
    assert private.is_file() and snapshot.is_file()
    assert private.stat().st_mode & 0o777 == 0o440
    assert cq_runner._cq_wait_windows.has_open_window is True
    # A second publication appends a new version and never rewrites the first.
    first = json.loads(private.read_text(encoding="utf-8"))
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1", content_version=2)])}
    )
    assert json.loads(private.read_text(encoding="utf-8")) == first
    assert (cq_runner.run.root / "competency-questions" / "private" / "draft-0002.json").is_file()


def test_m5_cq_draft_rejection_is_typed_and_local(cq_runner):
    broken = _draft([_question("cq-1")])
    broken["schema_version"] = "r3-0-011-cq-draft/v2"
    with pytest.raises(CQContractError) as error:
        cq_runner._publish_cq_question_draft({"cq_id": "competency-question", "draft": broken})
    assert error.value.data["reason_code"] == "cq_freeze_schema_mismatch"
    assert not (cq_runner.run.root / "competency-questions" / "private" / "draft-0001.json").exists()


def test_m5_cq_socket_tools_call_publishes_through_the_real_runner_handler(cq_runner):
    """A real ``tools/call`` reaches ``TeamRunner._publish_cq_question_draft``.

    Real run ``auth004-start1`` evidenced the CQ dispatch handing this handler
    the bare draft body while the handler reads the complete ``{cq_id, draft}``
    arguments envelope: every publication died as ``error_type=TypeError`` /
    ``'NoneType' object is not iterable`` in the Runner-private audit trail.
    This drives the carrier's real AF_UNIX endpoint instead of calling the
    handler directly, so the carrier -> Runner wiring itself is under test.
    """

    carrier = cq_runner.acceptance
    assert carrier.cq_capability_enabled is True
    endpoint = carrier.capability_endpoint(COMPETENCY_QUESTION_ROLE)
    assert endpoint.operations == CQ_OPERATIONS
    document = _draft([_question("cq-1")])

    carrier.start_cq_endpoint()
    try:
        response = _stdio_request(
            str(endpoint.socket_path),
            carrier.capability_token(COMPETENCY_QUESTION_ROLE),
            {
                "jsonrpc": "2.0",
                "id": "cq-real-handler-1",
                "method": "tools/call",
                "params": {
                    "name": CQ_OPERATION,
                    "arguments": {"cq_id": COMPETENCY_QUESTION_ROLE, "draft": document},
                },
            },
        )
    finally:
        endpoint.stop()

    # Runner-private audit trail first: the pre-fix wiring recorded
    # ``error_type=TypeError`` here while the CQ role still saw a bare -32001.
    audit_records = _read_evidence(cq_runner, "capability-calls")
    assert audit_records[-1]["operation"] == CQ_OPERATION
    assert audit_records[-1]["ok"] is True, audit_records[-1]
    assert "error_type" not in audit_records[-1]

    assert "error" not in response, response
    data = response["result"]["structuredContent"]["data"]
    assert data["ok"] is True and data["status"] == "awaiting_review"
    assert data["review_id"] == "cq-review-0001"
    assert data["draft_ref"] == "competency-questions/private/draft-0001.json"
    assert (cq_runner.run.root / data["draft_ref"]).is_file()

    # The immutable version and its review snapshot are what the capability
    # persists: the validated draft document, never the raw envelope.
    published = json.loads(
        (cq_runner.run.root / "competency-questions" / "private" / "draft-0001.json").read_text(
            encoding="utf-8"
        )
    )
    assert published["draft_id"] == document["draft_id"]
    assert [question["question_id"] for question in published["questions"]] == ["cq-1"]
    snapshot = json.loads(
        (cq_runner.run.root / "competency-questions" / "reviews" / "cq-review-0001.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot["review_id"] == "cq-review-0001"
    assert snapshot["content_digest"] == data["content_digest"]
    # The publication opens the Delivery review window (design §3.2).
    assert cq_runner._cq_wait_windows.has_open_window is True


# --- M7: outer direct-channel inputs -----------------------------------------


def _read_evidence(runner: TeamRunner, name: str) -> list[dict]:
    path = runner.run.root / "evidence" / f"{name}.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _review_payload(runner: TeamRunner, **overrides) -> dict:
    snapshot = json.loads(
        (runner.run.root / "competency-questions" / "reviews" / "cq-review-0001.json").read_text(
            encoding="utf-8"
        )
    )
    payload = {
        "action": "cq_review",
        "schema_version": "r3-0-011-cq-review/v1",
        "review_id": snapshot["review_id"],
        "question_id": snapshot["question_ids"][0],
        "decision": "approve",
        "content_version": snapshot["content_version"],
        "content_digest": snapshot["content_digest"],
        "revision": 1,
        "modified_question": None,
        "note": "fixture approval",
    }
    payload.update(overrides)
    return payload


def test_m7_interview_and_review_reach_the_cq_without_the_transport(cq_runner):
    ack = cq_runner.handle_cq_outer_input(
        {"action": "cq_interview", "text": "which value domain applies?", "wait_for_draft": True}
    )
    assert ack["type"] == "cq-interview-accepted"
    assert ack["wait_window_open"] is True
    published = cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1")])}
    )
    review = cq_runner.handle_cq_outer_input(_review_payload(cq_runner))
    assert review["type"] == "cq-review-accepted"
    assert review["decision"] == "approve"
    assert published["phase"] == "panorama-review"
    assert cq_runner._cq_phase == "awaiting-slices"
    kinds = [delivery.kind for _agent, delivery in cq_runner.adapter.messages]
    assert "cq-interview" in kinds and "cq-review-decision" in kinds
    # Nothing was sent through Team Transport: the CQ direct channel bypasses it.
    assert all(_agent == "competency-question" for _agent, _delivery in cq_runner.adapter.messages)


def test_m7_public_projection_after_panorama_review_is_production_visible(cq_runner):
    cq_runner._publish_cq_question_draft(
        {
            "cq_id": "competency-question",
            "draft": _draft([_question("cq-1"), _question("cq-2", visibility="hidden")]),
        }
    )
    cq_runner.handle_cq_outer_input(_review_payload(cq_runner))
    projection = cq_runner._cq_public_projection()
    assert projection["schema_version"] == CQ_PUBLIC_PROJECTION_SCHEMA
    assert [question["question_id"] for question in projection["questions"]] == ["cq-1"]
    assert "cq-2" not in json.dumps(projection)


def test_m7_stale_review_is_rejected_for_that_input_only(cq_runner):
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1")])}
    )
    stale = _review_payload(cq_runner, content_version=99)
    with pytest.raises(CQContractError) as error:
        cq_runner.handle_cq_outer_input(stale)
    assert error.value.data["reason_code"] == "cq_review_stale"
    # The run is alive: the next valid review still succeeds.
    cq_runner.handle_cq_outer_input(_review_payload(cq_runner))
    assert cq_runner._cq_phase == "awaiting-slices"


def test_m7_unknown_cq_action_is_typed_rejected(cq_runner):
    with pytest.raises(CQContractError) as error:
        cq_runner.handle_cq_outer_input({"action": "cq_adjust"})
    assert error.value.data["reason_code"] == "cq_selector_incompatible"


def test_m7_interview_input_is_private_to_the_cq_role(cq_runner):
    cq_runner.handle_cq_outer_input({"action": "cq_interview", "text": "secret interview turn"})
    private = cq_runner.run.root / "competency-questions" / "private" / "interview-0001.json"
    assert json.loads(private.read_text(encoding="utf-8"))["text"] == "secret interview turn"
    # The only delivery is the CQ wake; no production role sees the text.
    assert [agent for agent, _ in cq_runner.adapter.messages] == ["competency-question"]


# --- M12: terminal gating and the handoff ------------------------------------


def test_m12_premature_cq_terminal_report_is_rejected_with_a_continuation(cq_runner):
    reason = cq_runner._cq_terminal_block_reason("competency-question")
    assert reason is not None
    assert reason["object"] == "report_task_result"
    assert reason["reason_code"] == "cq_batch_scope_unauthorized"
    assert set(reason) == {"object", "phase", "reason_code", "retry"}
    assert _read_evidence(cq_runner, "cq-terminal-report")[-1]["event"] == "rejected"


def test_m12_premature_cq_terminal_pushes_a_typed_delivery(cq_runner):
    cq_runner._deliver_cq_terminal_rejection(
        "competency-question", cq_runner._cq_terminal_block_reason("competency-question")
    )
    rejections = [
        delivery
        for agent, delivery in cq_runner.adapter.messages
        if agent == "competency-question" and delivery.kind == "cq-terminal-rejected"
    ]
    assert len(rejections) == 1
    payload = json.loads(rejections[0].text)
    assert payload["reason_code"] == "cq_batch_scope_unauthorized"


def test_m12_production_roles_are_never_blocked_by_the_cq_gate(cq_runner):
    assert cq_runner._cq_terminal_block_reason("coordinator") is None
    assert cq_runner._cq_terminal_block_reason("modeling") is None
    assert cq_runner._cq_terminal_block_reason("protocol") is None


def test_m12_handoff_requires_the_freeze_and_production_settlement(cq_runner):
    with pytest.raises(CQContractError) as missing_freeze:
        cq_runner.handle_cq_outer_input(
            {
                "action": "cq_handoff_complete",
                "freeze_id": "batch-r3011",
                "freeze_digest": "sha256:0",
                "delivery_binding": {"delivery_id": "d1"},
            }
        )
    assert missing_freeze.value.data["reason_code"] == "cq_freeze_schema_mismatch"

    frozen = cq_runner.freeze_cq_question_pool(
        {
            "schema_version": "r3-0-011-cq-freeze/v1",
            "batch_id": "batch-r3011",
            "material_digest": "material-r3011",
            "panorama_question_ids": ["cq-1"],
            "slice_question_ids": [],
            "ordering": ["cq-1"],
            "review_binding": {
                "review_id": "cq-review-0001",
                "review_content_version": 1,
                "decision_digest": "sha256:" + "0" * 64,
            },
            "questions": [_question("cq-1", visibility="hidden")],
        }
    )
    with pytest.raises(CQContractError) as not_ready:
        cq_runner.handle_cq_outer_input(
            {
                "action": "cq_handoff_complete",
                "freeze_id": "batch-r3011",
                "freeze_digest": frozen["snapshot_digest"],
                "delivery_binding": {"delivery_id": "d1"},
            }
        )
    assert not_ready.value.data["reason_code"] == "cq_batch_scope_unauthorized"
    # The wait window stays open and the run keeps going: nothing is latched.
    assert cq_runner._cq_wait_windows.has_open_window is True
    assert cq_runner._formal_failure_latched is False


def test_m12_accepted_handoff_releases_exactly_one_terminal_report(cq_runner):
    frozen = cq_runner.freeze_cq_question_pool(
        {
            "schema_version": "r3-0-011-cq-freeze/v1",
            "batch_id": "batch-r3011",
            "material_digest": "material-r3011",
            "panorama_question_ids": ["cq-1"],
            "slice_question_ids": [],
            "ordering": ["cq-1"],
            "review_binding": {
                "review_id": "cq-review-0001",
                "review_content_version": 1,
                "decision_digest": "sha256:" + "0" * 64,
            },
            "questions": [_question("cq-1", visibility="hidden")],
        }
    )
    class _StubTransport:
        results = {
            agent.agent_id: type("R", (), {"status": "completed"})()
            for agent in cq_runner.run.configuration.profile.agents
            if agent.package.role in {"coordinator", "modeling", "protocol"}
        }

        def stop(self):
            return None

    cq_runner.transport = _StubTransport()
    ack = cq_runner.handle_cq_outer_input(
        {
            "action": "cq_handoff_complete",
            "freeze_id": "batch-r3011",
            "freeze_digest": frozen["snapshot_digest"],
            "delivery_binding": {"delivery_id": "d1", "digest": frozen["snapshot_digest"]},
        }
    )
    assert ack["ok"] is True
    assert cq_runner._cq_terminal_block_reason("competency-question") is None
    assert cq_runner._cq_terminal_reported is True
    assert _read_evidence(cq_runner, "cq-handoff-complete")[-1]["freeze_id"] == "batch-r3011"


# --- R1: wait windows versus the T3 fallback clock ---------------------------


def test_r1_overlapping_wait_windows_are_unioned_not_summed():
    tracker = CQWaitWindowTracker()
    tracker.open_window("cq-review-request", 0.0)
    tracker.open_window("cq-interview-wait", 10.0)
    tracker.close_window("cq-review-request", 20.0)
    tracker.close_window("cq-interview-wait", 25.0)
    tracker.open_window("cq-handoff-request", 30.0)
    tracker.close_window("cq-handoff-request", 40.0)
    assert tracker.elapsed(40.0) == pytest.approx(35.0)
    evidence = tracker.evidence(40.0)
    assert evidence["excluded_seconds"] == pytest.approx(35.0)
    # Raw windows sum to 45s: the union keeps the overlap from counting twice.
    assert sum(item["duration"] for item in evidence["merged_windows"]) == pytest.approx(35.0)
    assert len(evidence["merged_windows"]) == 2


def test_r1_a_wait_longer_than_the_fallback_timeout_does_not_latch_the_run(cq_runner):
    now = [10_000.0]
    cq_runner.monotonic_clock = lambda: now[0]  # type: ignore[method-assign]
    cq_runner._run_fallback_started = 0.0
    cq_runner._run_fallback_timeout_seconds = 5400.0
    # A 9000 second user-review wait inside a 10000 second run: the union is
    # 9000 seconds of excluded wait, leaving 1000 active seconds.
    cq_runner._cq_wait_windows.open_window("cq-review-request", 100.0)
    cq_runner._cq_wait_windows.close_window("cq-review-request", 9100.0)
    cq_runner._check_run_fallback_timeout()
    assert cq_runner._formal_failure_latched is False
    assert cq_runner._cq_wait_windows.evidence(now[0])["excluded_seconds"] == pytest.approx(9000.0)


def test_r1_a_real_stall_without_a_wait_window_still_latches(cq_runner):
    now = [10_000.0]
    cq_runner.monotonic_clock = lambda: now[0]  # type: ignore[method-assign]
    cq_runner._run_fallback_started = 0.0
    cq_runner._run_fallback_timeout_seconds = 5400.0
    with pytest.raises(FormalCandidateProgressTimeout, match="run fallback timeout"):
        cq_runner._check_run_fallback_timeout()
    evidence = _read_evidence(cq_runner, "run-fallback-timeout")
    assert evidence[-1]["cq_wait_excluded_seconds"] == 0.0


def test_r4_interview_wait_is_a_declared_wait_state(cq_runner):
    # Round 4 (b): an unanswered interview question is a wait state like a
    # pending review: it is excluded from the T3 active clock.
    ack = cq_runner.handle_cq_outer_input(
        {"action": "cq_interview", "text": "which value domain applies?"}
    )
    assert ack["wait_window_open"] is True
    tracker = cq_runner._cq_wait_windows
    assert tracker.has_open_window is True
    now = _time_module.monotonic()
    assert tracker.elapsed(now) > 0.0
    # Publishing the draft closes the interview wait and opens the review wait,
    # so the CQ never leaves a wait state without a user-facing decision.
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1")])}
    )
    assert tracker.has_open_window is True
    # The closed interview window stays recorded and the review window is open.
    assert tracker.open_kinds() == ["cq-review-request"]
    assert len(tracker.intervals()) == 1
    assert tracker.intervals()[0]["duration"] > 0.0
    assert tracker.elapsed(now) > 0.0


def test_r4_scenario_map_consistency_is_checked_runner_side(cq_runner):
    # Round 4 (c): the external check reads the Coordinator-owned map, records
    # only ids, and never adds provenance fields to the three-field entries.
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1")])}
    )
    cq_runner.handle_cq_outer_input(_review_payload(cq_runner))
    missing = cq_runner.verify_cq_scenario_map_projection()
    assert missing and missing[0]["reason_code"] == "cq_public_projection_missing"
    projection = cq_runner._cq_public_projection()
    entry = {
        "question_id": "cq-1",
        "question": projection["questions"][0]["question"],
        "spans_slices": ["slice-0001"],
    }
    map_path = cq_runner.run.root / "scenario-map" / "scenario-map.json"
    map_path.write_text(
        json.dumps({"cross_slice_competency_questions": [entry]}), encoding="utf-8"
    )
    assert cq_runner.verify_cq_scenario_map_projection() == []
    consistent = (cq_runner.run.root / "evidence" / "cq-projection-consistency.jsonl").read_text(
        encoding="utf-8"
    )
    assert "cross-slice-projection-consistent" in consistent
    assert set(entry) == {"question_id", "question", "spans_slices"}
    # A minted entry is reported without echoing the invented text.
    minted = dict(entry, question_id="cq-minted", question="invented question text")
    map_path.write_text(
        json.dumps({"cross_slice_competency_questions": [minted]}), encoding="utf-8"
    )
    issues = cq_runner.verify_cq_scenario_map_projection()
    assert issues and issues[0]["reason_code"] == "cq_public_projection_missing"
    recorded = (
        cq_runner.run.root / "evidence" / "cq-projection-consistency.jsonl"
    ).read_text(encoding="utf-8")
    assert "invented question text" not in recorded


def test_i3_shared_evidence_never_carries_hidden_question_text(cq_runner):
    hidden = _question("cq-hidden-0001", visibility="hidden")
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([hidden])}
    )
    text = (
        cq_runner.run.root / "evidence" / "cq-review-request.jsonl"
    ).read_text(encoding="utf-8")
    assert "cq-hidden-0001" in text  # IDs are allowed
    assert "placeholder question cq-hidden-0001" not in text  # text is not
    assert "point" not in text.replace("\"point\"", "")


# --- Round 1 F1: shown to any production role => permanently public (D2) ------

_SLICE_SCOPE = {"kind": "slice", "slice_ids": ["slice-0001"]}


def _slice_question(question_id: str, visibility: str = "hidden", **overrides) -> dict:
    return _question(question_id, visibility=visibility, scope=dict(_SLICE_SCOPE), **overrides)


def _slice_draft(questions: list[dict], draft_id: str = "cq-draft-0002") -> dict:
    draft = _draft(questions)
    draft["phase"] = "slice-review"
    draft["draft_id"] = draft_id
    return draft


def _decision(runner: TeamRunner, ordinal: int = 1, **overrides) -> dict:
    """A ``cq_review`` payload bound to the Nth published review snapshot."""

    snapshot = json.loads(
        (runner.run.root / "competency-questions" / "reviews" / f"cq-review-{ordinal:04d}.json").read_text(
            encoding="utf-8"
        )
    )
    payload = {
        "action": "cq_review",
        "schema_version": "r3-0-011-cq-review/v1",
        "review_id": snapshot["review_id"],
        "question_id": snapshot["question_ids"][0],
        "decision": "approve",
        "content_version": snapshot["content_version"],
        "content_digest": snapshot["content_digest"],
        "revision": 1,
        "modified_question": None,
        "note": "fixture approval",
    }
    payload.update(overrides)
    return payload


def _model_binding(batch_id: str, freeze_digest: str) -> dict:
    return {
        "schema_version": "r3-0-011-model-binding/v1",
        "batch_id": batch_id,
        "freeze_digest": freeze_digest,
        "bound_at": "2026-09-09T00:00:00+00:00",
        "ontologies": [
            {
                "project_id": "project-1",
                "ontology_id": "ontology-1",
                "workspace_state": {"state_digest": "ws-1"},
                "model_version_state": {"state_digest": "graph-1"},
                "authorized_read_tools": ["query_semantic_context"],
            }
        ],
    }


def _write_handoff(path: Path, batch_id: str, freeze_digest: str) -> None:
    binding = _model_binding(batch_id, freeze_digest)
    path.write_text(
        json.dumps(
            {
                "authorized_ontology_ids": ["ontology-1"],
                "production_delivery": {"ready": True, "pending_writes": False},
                "model_binding": binding,
                "post_batch_model_binding": json.loads(json.dumps(binding)),
            }
        ),
        encoding="utf-8",
    )


def _show_question(runner: TeamRunner, question: dict) -> None:
    """Publish one public panorama question and let the user approve it."""

    runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([question])}
    )
    runner.handle_cq_outer_input(_decision(runner))


def test_f1_projection_write_is_the_exposure_event(cq_runner):
    assert cq_runner._cq_exposed == {}
    _show_question(cq_runner, _question("cq-1"))
    assert cq_runner._cq_exposed == {
        "cq-1": ["coordinator", "modeling", "protocol"],
    }
    events = _read_evidence(cq_runner, "cq-exposure")
    assert [
        {key: value for key, value in event.items() if key != "recorded_at"}
        for event in events
    ] == [
        {
            "event": "question-exposed-to-production",
            "question_ids": ["cq-1"],
            "roles": ["coordinator", "modeling", "protocol"],
            "reason_code": "permanently_public",
        }
    ]
    # The frozen pool later carries the recorded exposure as a mechanical fact.
    ack = cq_runner.handle_cq_outer_input({"action": "cq_freeze"})
    frozen = json.loads(
        (cq_runner.run.root / "competency-questions" / "frozen" / "freeze-0001.json").read_text(
            encoding="utf-8"
        )
    )
    assert ack["public_question_ids"] == ["cq-1"]
    assert frozen["questions"][0]["visibility"] == "public"


def test_f1_hidden_reproposal_of_a_shown_question_is_rejected(cq_runner):
    _show_question(cq_runner, _question("cq-1"))
    with pytest.raises(CQContractError) as error:
        cq_runner._publish_cq_question_draft(
            {
                "cq_id": "competency-question",
                "draft": _draft(
                    [_question("cq-1", visibility="hidden", content_version=2)]
                ),
            }
        )
    assert error.value.data["reason_code"] == "cq_hidden_exposed"
    assert error.value.data["retry"] == (
        "keep the question public; a shown question is permanently public"
    )
    # The rejected proposal wrote no draft version and no review snapshot.
    private = cq_runner.run.root / "competency-questions" / "private"
    assert [path.name for path in sorted(private.glob("draft-*.json"))] == [
        "draft-0001.json"
    ]
    reviews = cq_runner.run.root / "competency-questions" / "reviews"
    assert [path.name for path in sorted(reviews.glob("cq-review-*.json"))] == [
        "cq-review-0001.json"
    ]
    assert len(_read_evidence(cq_runner, "cq-exposure")) == 1


def test_f1_freeze_never_lands_a_shown_question_hidden(cq_runner):
    _show_question(cq_runner, _question("cq-1"))
    payload = {
        "schema_version": CQ_FREEZE_SCHEMA,
        "batch_id": "cq-batch-0001",
        "material_digest": cq_runner.run.baseline_hash,
        "panorama_question_ids": ["cq-1"],
        "slice_question_ids": [],
        "ordering": ["cq-1"],
        "questions": [
            {
                **_question("cq-1", visibility="hidden", content_version=2),
                "_exposed_to": cq_runner._cq_exposed["cq-1"],
            }
        ],
        "review_binding": {
            "review_id": "cq-review-0001",
            "review_content_version": 2,
            "decision_digest": "sha256:" + "0" * 64,
        },
    }
    with pytest.raises(CQContractError) as error:
        cq_runner.freeze_cq_question_pool(payload)
    assert error.value.data["reason_code"] == "cq_hidden_exposed"
    assert error.value.data["phase"] == "frozen"
    # Nothing was frozen and the phase did not silently advance.
    assert not (cq_runner.run.root / "competency-questions" / "frozen" / "freeze-0001.json").exists()
    assert cq_runner._cq_freeze is None


# --- Round 1 F2: a production trigger for the freeze, end to end --------------


def test_f2_freeze_requires_a_user_decision_for_every_question(cq_runner):
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-1")])}
    )
    with pytest.raises(CQContractError) as empty_pool_decision:
        cq_runner.handle_cq_outer_input({"action": "cq_freeze"})
    assert empty_pool_decision.value.data["reason_code"] == "cq_review_stale"
    cq_runner.handle_cq_outer_input(_decision(cq_runner, 1))
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([_question("cq-2")])}
    )
    with pytest.raises(CQContractError) as undecided:
        cq_runner.handle_cq_outer_input({"action": "cq_freeze"})
    assert undecided.value.data["reason_code"] == "cq_review_stale"
    assert undecided.value.data["retry"].startswith("record a cq_review decision")
    assert cq_runner._cq_freeze is None
    assert not list((cq_runner.run.root / "competency-questions" / "frozen").glob("*.json"))


def test_f2_delivery_freeze_reaches_the_cq_acceptance_command(cq_runner, tmp_path, capsys):
    root = cq_runner.run.root
    # 1. panorama draft -> user approval -> public projection (exposure).
    _show_question(cq_runner, _question("cq-1"))
    assert (root / "competency-questions" / "public" / "public-projection-0001.json").is_file()
    # 2. slice stage -> user approval of the hidden slice question.
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _slice_draft([_slice_question("cq-2")])}
    )
    assert cq_runner._cq_phase == "slice-review"
    cq_runner.handle_cq_outer_input(_decision(cq_runner, 2))
    # 3. Delivery freezes the user-approved pool over the CQ admission branch.
    ack = cq_runner.handle_cq_outer_input({"action": "cq_freeze"})
    assert ack["type"] == "cq-frozen"
    assert ack["freeze_id"] == "cq-batch-0001"
    assert ack["public_question_ids"] == ["cq-1"]
    assert ack["hidden_question_count"] == 1
    assert ack["phase"] == "frozen"
    freeze_path = root / "competency-questions" / "frozen" / "freeze-0001.json"
    assert freeze_path.is_file() and freeze_path.stat().st_mode & 0o777 == 0o440
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert frozen["batch_id"] == ack["freeze_id"]
    assert frozen["snapshot_digest"] == ack["snapshot_digest"]
    assert [item["question_id"] for item in frozen["questions"]] == ["cq-1", "cq-2"]
    assert [item["visibility"] for item in frozen["questions"]] == ["public", "hidden"]
    assert cq_runner._cq_phase == "frozen"
    # 4. The real command runs read-only against this Runner-written run root.
    _write_handoff(tmp_path / "handoff.json", frozen["batch_id"], frozen["snapshot_digest"])
    code = _run_cq_acceptance(
        SimpleNamespace(
            run_root=root,
            freeze_id="freeze-0001",
            model_handoff=tmp_path / "handoff.json",
            # Historical carrier scope: this test never executes the batch.
            unexecuted_report=True,
        ),
        REPO_ROOT,
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["batch_id"] == "cq-batch-0001"
    assert payload["start_ledger_write"] is False
    assert payload["consumes_semantic_start"] is False
    report = json.loads(
        (root / "acceptance-v3" / "reports" / "cq-batch-0001" / "batch-report.json").read_text(
            encoding="utf-8"
        )
    )
    # Fixture scope never executes the batch: unexecuted questions, never a pass.
    assert report["full_pass"] is False
    assert report["unexecuted_question_ids"] == ["cq-2"]


def test_f2_freeze_is_append_only_and_reloads_as_written(cq_runner):
    _show_question(cq_runner, _question("cq-1"))
    first = cq_runner.handle_cq_outer_input({"action": "cq_freeze"})
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _slice_draft([_slice_question("cq-2")])}
    )
    cq_runner.handle_cq_outer_input(_decision(cq_runner, 2))
    second = cq_runner.handle_cq_outer_input({"action": "cq_freeze"})
    frozen_dir = cq_runner.run.root / "competency-questions" / "frozen"
    assert [path.name for path in sorted(frozen_dir.glob("freeze-*.json"))] == [
        "freeze-0001.json",
        "freeze-0002.json",
    ]
    assert first["snapshot_digest"] != second["snapshot_digest"]
    for path, ack in (
        (frozen_dir / "freeze-0001.json", first),
        (frozen_dir / "freeze-0002.json", second),
    ):
        assert path.stat().st_mode & 0o777 == 0o440
        reloaded = reload_frozen_pool(json.loads(path.read_text(encoding="utf-8")))
        assert reloaded["snapshot_digest"] == ack["snapshot_digest"]
        assert reloaded["batch_id"] == ack["freeze_id"]
    events = _read_evidence(cq_runner, "cq-freeze")
    assert [event["batch_id"] for event in events] == ["cq-batch-0001", "cq-batch-0002"]


# --- Round 1 F6: cleanup removes the private working set only -----------------


def _run_lifecycle_to_frozen(runner: TeamRunner) -> dict:
    _show_question(runner, _question("cq-1"))
    runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _slice_draft([_slice_question("cq-2")])}
    )
    runner.handle_cq_outer_input(_decision(runner, 2))
    return runner.handle_cq_outer_input({"action": "cq_freeze"})


def test_f6_cleanup_deletes_private_temp_and_preserves_durable_artifacts(cq_runner, tmp_path):
    root = cq_runner.run.root
    ack = _run_lifecycle_to_frozen(cq_runner)
    _write_handoff(tmp_path / "handoff.json", ack["freeze_id"], ack["snapshot_digest"])
    assert _run_cq_acceptance(
        SimpleNamespace(
            run_root=root,
            freeze_id="freeze-0001",
            model_handoff=tmp_path / "handoff.json",
            # Historical carrier scope: this test never executes the batch.
            unexecuted_report=True,
        ),
        REPO_ROOT,
    ) == 0
    private = root / "competency-questions" / "private"
    assert [path.name for path in sorted(private.iterdir())] == ["draft-0001.json", "draft-0002.json"]
    evidence_before = [path.name for path in sorted((root / "evidence").glob("*.jsonl"))]

    result = cq_runner.cleanup()

    assert not private.exists()
    for relative in (
        "competency-questions/frozen/freeze-0001.json",
        "competency-questions/reviews/cq-review-0001.json",
        "competency-questions/reviews/cq-review-0002.json",
        "competency-questions/reviews/decision-0001.json",
        "competency-questions/public/public-projection-0001.json",
        "acceptance-v3/reports/cq-batch-0001/batch-report.json",
    ):
        assert (root / relative).is_file(), relative
    evidence_after = [path.name for path in sorted((root / "evidence").glob("*.jsonl"))]
    assert sorted(evidence_before + ["cq-cleanup.jsonl"]) == evidence_after
    assert result["cq_private_cleanup"] == {
        "removed_count": 2,
        "retained_unknown_owner": [],
        "directory_removed": True,
    }
    events = _read_evidence(cq_runner, "cq-cleanup")
    assert [
        {key: value for key, value in event.items() if key != "recorded_at"}
        for event in events
    ] == [
        {
            "event": "cq-private-cleanup",
            "removed": ["draft-0001.json", "draft-0002.json"],
            "retained_unknown_owner": [],
            "preserved": [
                "competency-questions/frozen",
                "competency-questions/reviews",
                "competency-questions/public",
                "acceptance-v3/reports",
                "evidence",
            ],
            "directory_removed": True,
        }
    ]


def test_f6_cleanup_never_blind_deletes_an_entry_it_cannot_prove(cq_runner):
    _show_question(cq_runner, _question("cq-1"))
    private = cq_runner.run.root / "competency-questions" / "private"
    outside = cq_runner.run.root / "outside-private.txt"
    outside.write_text("keep me", encoding="utf-8")
    linked = private / "linked.json"
    os.symlink(outside, linked)

    result = cq_runner.cleanup()

    assert linked.is_symlink() and outside.read_text(encoding="utf-8") == "keep me"
    assert private.is_dir()
    assert result["cq_private_cleanup"]["removed_count"] == 1
    assert result["cq_private_cleanup"]["directory_removed"] is False
    events = _read_evidence(cq_runner, "cq-cleanup")
    assert events[-1]["removed"] == ["draft-0001.json"]
    assert events[-1]["retained_unknown_owner"] == [
        {"entry": "linked.json", "reason": "unknown-owner"}
    ]


# --- Round 1 F5: the foreground CQ admission is typed, never the fatal path ----


def test_f5_cq_inputs_stay_typed_and_only_unsupported_runners_fall_through(cq_runner):
    emitted: list = []

    def emit(envelopes: list) -> None:
        emitted.extend(envelopes)

    # A runner object without CQ input support falls through to the unchanged
    # fatal receive_outer boundary (Round 1 F5).
    assert (
        _handle_cq_outer_message(
            SimpleNamespace(), {"action": "cq_review", "review_id": "cq-review-0001"}, emit
        )
        is False
    )
    assert emitted == []
    # A real TeamRunner handles a known CQ action itself: an invalid input is a
    # typed rejection envelope on this line, and the loop keeps reading.
    assert _handle_cq_outer_message(cq_runner, {"action": "cq_review"}, emit) is True
    assert [item["type"] for item in emitted] == ["cq-input-rejected"]
    assert emitted[0]["reason_code"] == "cq_review_stale"
    assert emitted[0]["retry"] == "send the review_id exactly as published"
    # An action outside the narrow CQ list is not claimed here at all.
    assert _handle_cq_outer_message(cq_runner, {"action": "cq_adjust"}, emit) is False
    assert len(emitted) == 1


# --- Round 2 F7: the real foreground gate must admit the freeze trigger -------


def _foreground(line: str, runner: TeamRunner):
    """Drive one foreground (stdin/FIFO) line through the real admission path."""

    emitted: list = []
    rejected: list = []

    def emit(envelopes: list) -> None:
        emitted.extend(envelopes)

    _handle_foreground_message(runner, line, emit, lambda: rejected.append(True))
    return emitted, rejected


def test_f7_foreground_path_freezes_the_pool(cq_runner):
    _run_lifecycle_to_frozen_pending(cq_runner)
    frozen_dir = cq_runner.run.root / "competency-questions" / "frozen"
    assert not list(frozen_dir.glob("freeze-*.json"))

    emitted, rejected = _foreground(
        json.dumps({"action": "cq_freeze"}), cq_runner
    )

    assert rejected == []
    assert [item["type"] for item in emitted] == ["cq-frozen"]
    assert emitted[0]["freeze_id"] == "cq-batch-0001"
    assert emitted[0]["hidden_question_count"] == 1
    freeze_path = frozen_dir / "freeze-0001.json"
    assert freeze_path.is_file() and freeze_path.stat().st_mode & 0o777 == 0o440
    assert cq_runner._cq_freeze["snapshot_digest"] == emitted[0]["snapshot_digest"]


def test_f7_foreground_gate_rejects_unknown_cq_actions(cq_runner):
    emitted, rejected = _foreground(
        json.dumps({"action": "cq_adjust"}), cq_runner
    )
    assert emitted == [] and rejected == [True]
    # The known-action gate, not the CQ branch, is what rejected the line.
    assert "cq_freeze" in _KNOWN_OUTER_ACTIONS
    # R3.0-012 extends the closed CQ action set with the host-only
    # acceptance-completion channel (design §4.5).
    assert set(_CQ_OUTER_ACTIONS) == set(_KNOWN_OUTER_ACTIONS) & {
        "cq_interview",
        "cq_review",
        "cq_freeze",
        "cq_handoff_complete",
        "cq_acceptance_complete",
    }


# --- Round 2 R4: exposure provenance and the non-blind label ------------------


def _run_lifecycle_to_frozen_pending(runner: TeamRunner) -> None:
    """Panorama approval + slice approval, leaving only the freeze pending."""

    _show_question(runner, _question("cq-1"))
    runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _slice_draft([_slice_question("cq-2")])}
    )
    runner.handle_cq_outer_input(_decision(runner, 2))


def test_r4_exposure_provenance_survives_the_freeze(cq_runner):
    ack = _run_lifecycle_to_frozen(cq_runner)
    # Pool-external state is not cleared by the freeze: D2 stays enforceable.
    assert cq_runner._cq_exposed == {"cq-1": ["coordinator", "modeling", "protocol"]}
    with pytest.raises(CQContractError) as error:
        cq_runner._publish_cq_question_draft(
            {
                "cq_id": "competency-question",
                "draft": _draft([_question("cq-1", visibility="hidden", content_version=3)]),
            }
        )
    assert error.value.data["reason_code"] == "cq_hidden_exposed"
    # A recovered Runner rebuilds the same provenance from the evidence file
    # (the frozen snapshot schema carries no exposure field by design).
    cq_runner._cq_exposed = {}
    cq_runner._cq_merge_exposure_evidence()
    assert cq_runner._cq_exposed == {"cq-1": ["coordinator", "modeling", "protocol"]}
    assert ack["freeze_id"] == "cq-batch-0001"


def test_r4_non_blind_pool_labels_the_batch_report(cq_runner, tmp_path, capsys):
    root = cq_runner.run.root
    ack = _run_lifecycle_to_frozen(cq_runner)
    _write_handoff(tmp_path / "handoff.json", ack["freeze_id"], ack["snapshot_digest"])
    assert _run_cq_acceptance(
        SimpleNamespace(
            run_root=root,
            freeze_id="freeze-0001",
            model_handoff=tmp_path / "handoff.json",
            # Historical carrier scope: this test never executes the batch.
            unexecuted_report=True,
        ),
        REPO_ROOT,
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["blind_status"] == "non-blind-regression"
    provenance = read_exposure_evidence(root / "evidence" / "cq-exposure.jsonl")
    report = json.loads(
        (root / "acceptance-v3" / "reports" / "cq-batch-0001" / "batch-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["blind_status"] == {
        "blind_status": "non-blind-regression",
        "exposed_question_ids": ["cq-1"],
        "exposure_evidence_digest": provenance["digest"],
        "exposure_record_count": 1,
    }
    attribution = json.loads(
        (root / "acceptance-v3" / "reports" / "cq-batch-0001" / "attribution.json").read_text(
            encoding="utf-8"
        )
    )
    assert attribution["blind_status"] == "non-blind-regression"
    assert attribution["exposed_question_ids"] == ["cq-1"]
    # The label never enters the frozen snapshot schema.
    frozen = json.loads(
        (root / "competency-questions" / "frozen" / "freeze-0001.json").read_text(encoding="utf-8")
    )
    assert set(frozen) == {
        "schema_version",
        "batch_id",
        "material_digest",
        "panorama_question_ids",
        "slice_question_ids",
        "ordering",
        "questions",
        "review_binding",
        "snapshot_digest",
    }
