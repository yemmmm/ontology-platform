"""R3.0-012 runner-side production handoff tests (shared test plan T1 subset).

Mechanical coverage for the verified minimal production handoff (design §3.1,
§4.4): the run-local write admission shared by both staged write entry points,
the quiesce/drain order at ``cq_handoff_complete``, host-verified readiness
(role states as recorded input, write determinism as the gate), and the
immutable ``acceptance-v3/production-handoff.json`` with derived booleans and
an allocated acceptance attempt.  No Agent process, no platform, no LLM; the
completion channel, proxy persistence, and Judge reporting are later modules.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
import time as _time_module
from types import SimpleNamespace

import pytest
import yaml

from modeling_team.competency_questions import CQ_FREEZE_SCHEMA, CQContractError
from modeling_team import host_ops
from modeling_team.__main__ import _handle_foreground_message
from modeling_team.contracts import (
    ACCEPTANCE_TARGET_CQ_SEMANTIC,
    ACCEPTANCE_TARGET_PARAMETER,
    repository_root,
)
from modeling_team.platform_scope import PlatformScope
from modeling_team.runner import CQWriteAdmission, TeamRunner
from modeling_team.staged_batch_write_forwarder import StagedBatchForwardUnknown
from modeling_team.staged_decisions import (
    StagedSubmissionRejection,
    build_submission_intent,
    build_submission_receipt,
    mark_intent_status,
    staged_decision_artifact_paths,
    write_submission_intent,
    write_submission_receipt,
)
from modeling_team.tests.test_platform_scope import ScopeClient
from modeling_team.tests.test_r3011_runner_wiring import _question, _read_evidence
from modeling_team.tests.test_runner import CapturingAdapter

REPO_ROOT = repository_root()
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-011-competency-question.yaml"
TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml"


class _CQRunner:
    """A prepared 011 runner whose run root is removed afterwards."""

    def __init__(self, scope: dict | None = None, task_path: Path = TASK) -> None:
        self.run_id = (
            f"r3012h-{hashlib.sha256(str(_time_module.time()).encode()).hexdigest()[:10]}"
        )
        self.run_root = REPO_ROOT / "workspaces" / "modeling-runs" / self.run_id
        self.adapter = CapturingAdapter()
        self.runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=self.adapter,
            ledger_root=self.run_root.parent / f"{self.run_id}-ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
        )
        self._scope = scope or {"mode": "create"}
        self._task_path = task_path

    def prepare(self) -> TeamRunner:
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=self._task_path,
            scope=dict(self._scope),
        )
        return self.runner

    def cleanup(self) -> None:
        self.runner.cleanup()
        rmtree(self.run_root, ignore_errors=True)
        rmtree(self.run_root.parent / f"{self.run_id}-ledger", ignore_errors=True)


class _SettledTransport:
    """Production roles reported the given terminal status; stop() is a no-op."""

    def __init__(self, runner: TeamRunner, status: str) -> None:
        self.results = {
            agent.agent_id: type("R", (), {"status": status})()
            for agent in runner.run.configuration.profile.agents
            if agent.package.role in {"coordinator", "modeling", "protocol"}
        }

    def stop(self):
        return None


def _freeze(runner: TeamRunner) -> dict:
    return runner.freeze_cq_question_pool(
        {
            "schema_version": CQ_FREEZE_SCHEMA,
            "batch_id": "batch-r3012",
            "material_digest": "material-r3012",
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


def _handoff_message(frozen: dict) -> dict:
    return {
        "action": "cq_handoff_complete",
        "freeze_id": "batch-r3012",
        "freeze_digest": frozen["snapshot_digest"],
        "delivery_binding": {"delivery_id": "d1", "digest": frozen["snapshot_digest"]},
    }


def _association() -> dict:
    return {
        "project_id": "proj-1",
        "ontology_id": "https://example.test/ontology/placeholder",
        "target_type": "modeling_item",
        "target_id": "item-1",
        "evidence_reference_ids": ["ev-1"],
    }


def _handoff_path(runner: TeamRunner) -> Path:
    return runner.run.root / "acceptance-v3" / "production-handoff.json"


def _write_unknown_intent(runner: TeamRunner) -> None:
    intent = build_submission_intent(
        1,
        idempotency_key="idem-1",
        client_batch_id="cb-1",
        session_id="session-1",
        mode="apply",
        commands=[],
        value_traces=[],
        l3_nodes=[],
    )
    write_submission_intent(runner.run.root, mark_intent_status(intent, "unknown"))


def _adjudicate_intent(runner: TeamRunner) -> None:
    intent = build_submission_intent(
        1,
        idempotency_key="idem-1",
        client_batch_id="cb-1",
        session_id="session-1",
        mode="apply",
        commands=[],
        value_traces=[],
        l3_nodes=[],
    )
    write_submission_intent(runner.run.root, mark_intent_status(intent, "receipted"))
    write_submission_receipt(
        runner.run.root,
        build_submission_receipt(
            1, intent, batch_id="platform-batch-1", response_digest="sha256:" + "1" * 64
        ),
    )


# --- the run-local write admission ---------------------------------------------


def test_admission_open_quiescing_read_only_with_drain():
    admission = CQWriteAdmission()
    assert admission.phase == "open"
    ticket = admission.admit("staged_associate_evidence")
    assert ticket == 1
    assert admission.begin_quiescing() is True
    assert admission.admit("staged_submit_modeling_batch") is None
    assert admission.wait_until_drained(timeout=0.05) is False
    admission.complete(ticket, "associated")
    assert admission.wait_until_drained(timeout=0.05) is True
    admission.enter_read_only()
    assert admission.phase == "read-only"
    assert admission.begin_quiescing() is False
    snapshot = admission.snapshot()
    assert snapshot["records"] == [{"ticket": 1, "kind": "staged_associate_evidence", "outcome": "associated"}]


def test_admission_drain_does_not_hold_the_lock():
    admission = CQWriteAdmission()
    admission.admit("staged_submit_modeling_batch")
    drain_done = threading.Event()

    def _drain():
        admission.wait_until_drained(timeout=5.0)
        drain_done.set()

    drainer = threading.Thread(target=_drain)
    drainer.start()
    _time_module.sleep(0.05)
    # The drainer released the condition lock inside wait(): a new admission
    # and a snapshot still proceed while it is parked, never deadlock.
    late = admission.admit("staged_associate_evidence")
    assert late is not None
    assert admission.snapshot()["phase"] == "open"
    admission.complete(late, "rejected")
    admission.complete(1, "receipted")
    assert drain_done.wait(timeout=2.0) is True


# --- T1-1: verified handoff publishes with the checklist pending ----------------


def test_t1_1_verified_handoff_publishes_with_pending_checklist():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        ack = runner.handle_cq_outer_input(_handoff_message(frozen))
        assert ack["ok"] is True
        assert ack["acceptance_attempt_id"] == "attempt-0001"
        assert ack["report_directory"] == "acceptance-v3/reports/batch-r3012/attempt-0001"
        assert ack["model_handoff"] == str(_handoff_path(runner))
        assert ack["model_handoff_relative"] == str(_handoff_path(runner).relative_to(REPO_ROOT))

        path = _handoff_path(runner)
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "r3-0-012-production-handoff/v1"
        # Derived booleans exist only next to the evidence that produced them.
        assert payload["ready"] is True
        assert payload["pending_writes"] is False
        assert payload["scope_binding"] == {"project_id": "", "ontology_ids": []}
        assert payload["applied_batches"] == []
        assert payload["unknown_writes"] == []
        assert payload["write_phase"] == "read-only"
        assert payload["joint_checklist"]["state"] == "pending"
        assert payload["freeze_id"] == "batch-r3012"
        assert payload["freeze_digest"] == frozen["snapshot_digest"]
        assert payload["run_id"] == runner.run.run_id
        contract_bytes = (runner.run.root / "acceptance-v3" / "run-contract.json").read_bytes()
        assert payload["run_contract_digest"] == hashlib.sha256(contract_bytes).hexdigest()
        assert payload["acceptance_target"] == "full_joint"
        # The digest covers exactly the written bytes and is recorded outside
        # the file (event + attempt state), never self-embedded.
        encoded = path.read_bytes()
        assert ack["handoff_digest"] == f"sha256:{hashlib.sha256(encoded).hexdigest()}"
        assert "handoff_digest" not in payload
        assert runner._cq_acceptance_attempt["handoff_digest"] == ack["handoff_digest"]
        assert runner._cq_acceptance_attempt["batch_id"] == "batch-r3012"

        event = _read_evidence(runner, "cq-handoff-complete")[-1]
        assert event["handoff_digest"] == ack["handoff_digest"]
        assert event["acceptance_attempt_id"] == "attempt-0001"
        assert event["model_handoff"] == str(path)
        assert event["model_handoff_relative"] == str(path.relative_to(REPO_ROOT))
        assert event["readiness"]["ready"] is True
        assert runner._cq_wait_windows.has_open_window is False
        assert runner._cq_write_admission.phase == "read-only"
    finally:
        harness.cleanup()


def test_t1_1_scope_binding_is_recorded_from_the_run_scope():
    harness = _CQRunner(
        scope={
            "mode": "create",
            "project_id": "proj-1",
            "ontology_ids": ["https://example.test/ontology/a", "https://example.test/ontology/b"],
        }
    )
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        runner.handle_cq_outer_input(_handoff_message(frozen))
        payload = json.loads(_handoff_path(runner).read_text(encoding="utf-8"))
        assert payload["scope_binding"]["project_id"] == "proj-1"
        assert payload["scope_binding"]["ontology_ids"] == [
            "https://example.test/ontology/a",
            "https://example.test/ontology/b",
        ]
    finally:
        harness.cleanup()


def _bound_single_ontology_scope() -> PlatformScope:
    """A real PlatformScope prepared in create mode (project-1/ontology-1)."""

    scope = PlatformScope(
        "http://example", "r3012-single-ontology", lambda: ("admin", "admin-id"),
        lambda _: True, ScopeClient(),
    )
    scope.prepare({"mode": "create"})
    return scope


def test_t1_1_single_ontology_create_scope_records_the_bound_ontology():
    """R4.0-009: a create-mode run binds exactly one singular ``ontology_id``
    while the R3.0-006 M3 plan path leaves ``ontology_ids`` empty; the published
    handoff must record that verified identity as its authorized set instead of
    the empty list that blocked the independent CQ acceptance start."""

    harness = _CQRunner()
    runner = harness.prepare()
    try:
        scope = _bound_single_ontology_scope()
        assert scope.ontology_id == "ontology-1" and scope.ontology_ids == []
        runner.scope = scope
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        runner.handle_cq_outer_input(_handoff_message(frozen))
        payload = json.loads(_handoff_path(runner).read_text(encoding="utf-8"))
        assert payload["scope_binding"] == {
            "project_id": "project-1",
            "ontology_ids": ["ontology-1"],
        }
    finally:
        harness.cleanup()


def test_t1_1_scope_binding_records_a_frozen_singular_ontology_id():
    """The host-authored run scope is the same single-Ontology shape for the
    existing/checkpoint modes; the handoff records that frozen identity too."""

    harness = _CQRunner(
        scope={
            "mode": "existing",
            "project_id": "proj-1",
            "ontology_id": "https://example.test/ontology/a",
        }
    )
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        runner.handle_cq_outer_input(_handoff_message(frozen))
        payload = json.loads(_handoff_path(runner).read_text(encoding="utf-8"))
        assert payload["scope_binding"] == {
            "project_id": "proj-1",
            "ontology_ids": ["https://example.test/ontology/a"],
        }
    finally:
        harness.cleanup()


@pytest.mark.parametrize(
    "scope, run_scope, expected",
    [
        # A live multi-Ontology binding is the authorized set verbatim.
        (SimpleNamespace(project_id="p", ontology_id="o1", ontology_ids=["o1", "o2"]),
         {"mode": "checkpoint"}, {"project_id": "p", "ontology_ids": ["o1", "o2"]}),
        # The single-Ontology live binding is its one verified identity.
        (SimpleNamespace(project_id="p", ontology_id="o1", ontology_ids=[]),
         {"mode": "create"}, {"project_id": "p", "ontology_ids": ["o1"]}),
        # A live list wins over the frozen run scope, never merged.
        (SimpleNamespace(project_id="p", ontology_id="o1", ontology_ids=["o1", "o2"]),
         {"mode": "checkpoint", "project_id": "p", "ontology_ids": ["o9"]},
         {"project_id": "p", "ontology_ids": ["o1", "o2"]}),
        (None, {"mode": "create", "project_id": "p", "ontology_ids": ["o1", "o2"]},
         {"project_id": "p", "ontology_ids": ["o1", "o2"]}),
        (None, {"mode": "existing", "project_id": "p", "ontology_id": "o1"},
         {"project_id": "p", "ontology_ids": ["o1"]}),
        # Nothing verified: still the empty record, never a project-wide guess.
        (None, {"mode": "create"}, {"project_id": "", "ontology_ids": []}),
    ],
)
def test_t1_1_scope_binding_normalizes_singular_and_list_identities(scope, run_scope, expected):
    runner = SimpleNamespace(scope=scope, run=SimpleNamespace(scope=run_scope))
    assert TeamRunner._cq_scope_binding(runner) == expected


def test_t1_1_cq_semantic_target_flows_into_the_handoff(tmp_path):
    task = yaml.safe_load(TASK.read_text(encoding="utf-8"))
    task["task_id"] = "r3012-handoff-cq-semantic"
    task["parameters"][ACCEPTANCE_TARGET_PARAMETER] = ACCEPTANCE_TARGET_CQ_SEMANTIC
    task_path = TASK.parent / "r3012-handoff-cq-semantic.yaml"
    task_path.write_text(yaml.safe_dump(task, allow_unicode=True), encoding="utf-8")
    harness = _CQRunner(task_path=task_path)
    try:
        runner = harness.prepare()
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        runner.handle_cq_outer_input(_handoff_message(frozen))
        payload = json.loads(_handoff_path(runner).read_text(encoding="utf-8"))
        assert payload["acceptance_target"] == ACCEPTANCE_TARGET_CQ_SEMANTIC
    finally:
        harness.cleanup()
        task_path.unlink(missing_ok=True)


def test_t1_5_blocked_roles_with_determined_writes_are_ready():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "blocked")
        ack = runner.handle_cq_outer_input(_handoff_message(frozen))
        assert ack["ok"] is True
        event = _read_evidence(runner, "cq-handoff-complete")[-1]
        readiness = event["readiness"]
        # "blocked" alone is never readiness: it passes only because the host
        # write state is determined here, and the blocked label is recorded.
        assert readiness["blocked_agents"] == ["coordinator", "modeling", "protocol"]
        assert readiness["pending_agents"] == []
        assert readiness["ready"] is True
    finally:
        harness.cleanup()


# --- T1-6/T1-3: unknown writes block, preserve the scene, and recover ----------


def test_handoff_summary_does_not_call_validation_failed_receipts_applied(monkeypatch):
    import modeling_team.runner as runner_module

    harness = _CQRunner()
    runner = harness.prepare()
    try:
        runner.transport = _SettledTransport(runner, "completed")
        intents = [{"ordinal": n, "mode": "apply_atomic"} for n in [1, 2]]
        receipts = [{"intent_ordinal": n, "batch_id": f"batch-{n}",
                     "mode": "apply_atomic", "response_digest": "digest"} for n in [1, 2]]
        monkeypatch.setattr(runner_module, "read_submission_intents", lambda _: intents)
        monkeypatch.setattr(runner_module, "read_submission_receipts", lambda _: receipts)
        monkeypatch.setattr(runner_module, "bound_attempt_proof", lambda _, *, intent, receipt: {
            "attempt_status": "applied" if intent["ordinal"] == 1 else "validation_failed",
        }, raising=False)
        readiness = runner._cq_production_readiness()
        assert readiness["ready"] is True
        assert [r["batch_id"] for r in readiness["applied_batches"]] == ["batch-1"]
        assert readiness["not_applied"][0]["batch_id"] == "batch-2"
        assert readiness["not_applied"][0]["attempt_status"] == "validation_failed"
    finally:
        harness.cleanup()


def test_t1_6_unknown_write_blocks_and_stays_quiesced_then_recovers():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "blocked")
        _write_unknown_intent(runner)
        with pytest.raises(CQContractError) as blocked:
            runner.handle_cq_outer_input(_handoff_message(frozen))
        assert blocked.value.data["reason_code"] == "cq_unknown_write_pending"
        assert runner._cq_handoff_complete is False
        assert not _handoff_path(runner).exists()
        assert runner._cq_wait_windows.has_open_window is True
        # The scene stays quiesced: a later staged write is recoverably
        # rejected instead of racing the pending adjudication.
        runner.staged_evidence_forwarder = lambda association: {"items": [{"id": "ev-1"}]}
        with pytest.raises(StagedSubmissionRejection) as later:
            runner._handle_staged_associate_evidence({"association": _association()})
        assert later.value.data["reason_code"] == "staged_write_quiescing"
        # Recovery: the unknown intent is adjudicated (receipted + receipt),
        # then the same handoff message is resent and publishes.
        _adjudicate_intent(runner)
        ack = runner.handle_cq_outer_input(_handoff_message(frozen))
        assert ack["ok"] is True
        payload = json.loads(_handoff_path(runner).read_text(encoding="utf-8"))
        assert payload["ready"] is True
        assert payload["applied_batches"] == [
            {
                "intent_ordinal": 1,
                "batch_id": "platform-batch-1",
                "mode": "apply",
                "response_digest": "sha256:" + "1" * 64,
            }
        ]
    finally:
        harness.cleanup()


def test_t1_7_rejected_submissions_are_not_applied_but_do_not_block():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        # A definitely rejected staged submission (typed rejection, nothing
        # written) is recorded as not_applied evidence, not an unknown write:
        # partial delivery never blocks the CQ handoff by itself.
        ticket = runner._cq_write_admission.admit("staged_submit_modeling_batch")
        runner._cq_write_admission.complete(ticket, "rejected")
        ack = runner.handle_cq_outer_input(_handoff_message(frozen))
        assert ack["ok"] is True
        payload = json.loads(_handoff_path(runner).read_text(encoding="utf-8"))
        assert payload["not_applied"] == [
            {"source": "admission", "kind": "staged_submit_modeling_batch", "ticket": 1}
        ]
        assert payload["unknown_writes"] == []
        assert payload["ready"] is True
    finally:
        harness.cleanup()


def test_t1_7_reconciliation_latch_blocks_the_handoff():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        runner._staged_gate_kill_switch("staged_unreconciled_batch", "fixture latch")
        with pytest.raises(CQContractError) as blocked:
            runner.handle_cq_outer_input(_handoff_message(frozen))
        assert blocked.value.data["reason_code"] == "cq_unknown_write_pending"
        assert not _handoff_path(runner).exists()
        assert runner._staged_gate_killed is True
    finally:
        harness.cleanup()


# --- T1-11: the two race orders and the unknown outcome ------------------------


def test_t1_11_write_admitted_first_handoff_drains_it():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        release = threading.Event()
        forwarded = threading.Event()

        def _blocking_forwarder(association):
            forwarded.set()
            assert release.wait(timeout=5.0) is True
            return {"items": [{"id": "ev-1"}]}

        runner.staged_evidence_forwarder = _blocking_forwarder

        def _associate():
            runner._handle_staged_associate_evidence({"association": _association()})

        writer = threading.Thread(target=_associate)
        writer.start()
        assert forwarded.wait(timeout=2.0) is True

        ack_box: dict = {}

        def _handoff():
            ack_box["ack"] = runner.handle_cq_outer_input(_handoff_message(frozen))

        handoff_thread = threading.Thread(target=_handoff)
        handoff_thread.start()
        _time_module.sleep(0.2)
        # Quiescing began and the admitted write is still registered in
        # flight, so the handoff must not have published over it.
        assert runner._cq_write_admission.phase == "quiescing"
        assert runner._cq_handoff_complete is False
        assert not _handoff_path(runner).exists()
        release.set()
        handoff_thread.join(timeout=5.0)
        writer.join(timeout=5.0)
        assert ack_box["ack"]["ok"] is True
        assert _handoff_path(runner).is_file()
        records = runner._cq_write_admission.snapshot()["records"]
        assert records == [
            {"ticket": 1, "kind": "staged_associate_evidence", "outcome": "associated"}
        ]
    finally:
        harness.cleanup()


def test_t1_11_unknown_outcome_after_drain_blocks_publication():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")

        def _unknown_forwarder(association):
            raise StagedBatchForwardUnknown("association result is indeterminate")

        runner.staged_evidence_forwarder = _unknown_forwarder
        with pytest.raises(StagedSubmissionRejection) as rejected:
            runner._handle_staged_associate_evidence({"association": _association()})
        assert rejected.value.data["reason_code"] == "staged_evidence_forward_unknown"
        records = runner._cq_write_admission.snapshot()["records"]
        assert records[0]["outcome"] == "unknown"
        with pytest.raises(CQContractError) as blocked:
            runner.handle_cq_outer_input(_handoff_message(frozen))
        assert blocked.value.data["reason_code"] == "cq_unknown_write_pending"
        assert not _handoff_path(runner).exists()
    finally:
        harness.cleanup()


def test_t1_11_handoff_first_rejects_later_writes():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        assert runner.handle_cq_outer_input(_handoff_message(frozen))["ok"] is True
        assert runner._cq_write_admission.phase == "read-only"
        runner.staged_evidence_forwarder = lambda association: {"items": [{"id": "ev-1"}]}
        with pytest.raises(StagedSubmissionRejection) as evidence:
            runner._handle_staged_associate_evidence({"association": _association()})
        assert evidence.value.data["reason_code"] == "staged_write_quiescing"
        with pytest.raises(StagedSubmissionRejection) as batch:
            runner._handle_staged_submit_modeling_batch({})
        assert batch.value.data["reason_code"] == "staged_write_quiescing"
    finally:
        harness.cleanup()


# --- T1-10: published handoff evidence is immutable -----------------------------


def test_t1_10_duplicate_complete_is_idempotent_and_immutable():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner, "completed")
        first = runner.handle_cq_outer_input(_handoff_message(frozen))
        original = _handoff_path(runner).read_bytes()
        events_before = len(_read_evidence(runner, "cq-handoff-complete"))

        again = runner.handle_cq_outer_input(_handoff_message(frozen))
        assert again["ok"] is True
        assert again.get("idempotent") is True
        assert _handoff_path(runner).read_bytes() == original
        assert len(_read_evidence(runner, "cq-handoff-complete")) == events_before

        # State loss cannot manufacture a second publication over the first:
        # the O_EXCL write is a typed conflict and the original bytes survive.
        runner._cq_handoff_complete = False
        runner._cq_acceptance_attempt = None
        with pytest.raises(CQContractError) as conflict:
            runner.handle_cq_outer_input(_handoff_message(frozen))
        assert conflict.value.data["reason_code"] == "cq_handoff_immutable"
        assert _handoff_path(runner).read_bytes() == original
    finally:
        harness.cleanup()


# --- compat: an unsettled handoff request never wedges production --------------


def test_premature_handoff_does_not_quiesce_production():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        with pytest.raises(CQContractError) as premature:
            runner.handle_cq_outer_input(_handoff_message(frozen))
        assert premature.value.data["reason_code"] == "cq_production_pending"
        assert runner._cq_write_admission.phase == "open"
        assert not _handoff_path(runner).exists()
        # Production keeps writing: the capture adapter (no settled roles)
        # never moved the run into the read-only period.
        runner.staged_evidence_forwarder = lambda association: {"items": [{"id": "ev-1"}]}
        result = runner._handle_staged_associate_evidence({"association": _association()})
        assert result["items"] == [{"id": "ev-1"}]
    finally:
        harness.cleanup()


def test_pending_handoff_receipt_preserves_wait_guidance_and_same_binding_can_retry():
    harness = _CQRunner()
    runner = harness.prepare()
    try:
        frozen = _freeze(runner)
        message = _handoff_message(frozen)
        message.pop("delivery_binding")
        emitted = []

        def submit(request_id):
            _handle_foreground_message(
                runner,
                json.dumps({**message, "request_id": request_id}),
                emitted.extend,
                lambda *_: pytest.fail("CQ input must remain a typed, recoverable rejection"),
            )
            return host_ops.get_request_result(runner.run.run_id, request_id=request_id)

        waiting = submit("pending-handoff")
        assert waiting["outcome"] == "rejected"
        assert waiting["code"] == "cq_production_pending"
        assert waiting["reason"] == "production roles have not settled their deliveries"
        assert "pending production agents report" in waiting["next_action"]
        assert "NEW request_id" in waiting["next_action"]
        assert "fix the reported binding" not in waiting["next_action"]
        assert runner._cq_write_admission.phase == "open"
        assert not _handoff_path(runner).exists()

        # Production settles; no authorization change or delivery_binding is needed.
        runner.transport = _SettledTransport(runner, "completed")
        accepted = submit("settled-handoff")
        assert accepted["outcome"] == "accepted"
        assert runner._cq_write_admission.phase == "read-only"
        assert _handoff_path(runner).exists()
    finally:
        harness.cleanup()
