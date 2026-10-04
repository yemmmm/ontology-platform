"""R3.0-015 segment S4 tests (shared test plan M33-M37, M44 S4 side, and the
handoff/kind prerequisite rows).

Stand-in disclosure: the in-process cases reuse the controlled platform REST
stand-in (``FakeCursorPlatform``, cursor endpoints ONLY) and the R3.0-012
forwarder/adapter developer doubles (``_DualForwarder``/``_batch_adapter``) --
controlled Runtime stand-ins, NOT real model providers: no Agent process and
no LLM call happens anywhere in this file.  The process-boundary case is REAL:
a genuinely separate OS process runs a real ``TeamRunner`` (on
``CapturingAdapter``) that freezes the pool and publishes the production
handoff, cleans up and exits; the continuation itself then runs through the
real CLI in further separate processes, with only the cursor-paginated read
endpoints served by a local HTTP stand-in.  Hidden-material markers stay
inside temporary test run roots and never enter formal modeling materials.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import threading
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace

import pytest

import modeling_team.__main__ as main_module
from modeling_team import checkpoint_recovery as cr
from modeling_team.checkpoint_recovery import (
    ACCEPTANCE_CONTINUATION_RECORD,
    ACCEPTANCE_CONTINUATION_SCHEMA,
    REASON_SCOPE_DRIFT,
    REASON_SOURCE_ACTIVE,
    REASON_WRITE_UNRECONCILED,
    RECOVERY_DIRECTORY,
    prepare_acceptance_continuation,
)
from modeling_team.checkpoints import (
    CHECKPOINT_HOST_PRIVATE_DIRECTORY,
    CHECKPOINT_KIND_CQ_FROZEN,
    CHECKPOINT_KIND_PRODUCTION_HANDOFF,
    CheckpointArtifactSpec,
    CheckpointError,
    StagePackage,
    list_checkpoints,
    save_checkpoint,
)
from modeling_team.competency_questions import (
    CQ_BATCH_REPORT_SCHEMA,
    batch_report_is_full_pass,
    build_batch_report,
)
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.tests.test_r30015_checkpoints import (
    CONFIGURATION,
    REPO_ROOT,
    RUNS_ROOT,
    _tree_state,
    _write_json,
)
from modeling_team.tests.test_r30015_resume import (
    FakeCursorPlatform,
    _readback,
    _seed_chain_intent,
)
from modeling_team.tests.test_r3011_acceptance import _freeze, _question
from modeling_team.tests.test_r3012_partial_judging import _batch_adapter
from modeling_team.tests.test_r3012_platform_responses import (
    _RETAINED_QUERY_RESULT,
    _DualForwarder,
    _Factory,
    _platform_context,
    _write_handoff,
    _write_run_root,
)

_AUTHORIZATION = "user-2026-09-14-r3015-acceptance-1"


# --- module-tier source-run fixture -------------------------------------------------


def _write_sources(run_root: Path) -> None:
    """The staged approved sources the judge evidence bundle resolves."""

    content = "approved scenario bytes\n"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    manifest = [{"path": "scenario-brief", "sha256": digest, "review_content_version": 1}]
    for role in ("coordinator", "modeling", "competency-question"):
        copy = run_root / "sources" / role / "scenario-brief"
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(content, encoding="utf-8")
    _write_json(
        run_root / "source-manifest.json",
        {"schema_version": "r3-0-009-source-manifest/v1", "sources": manifest},
    )


def _handoff_payload(run_id: str, frozen: dict, **overrides) -> dict:
    payload = {
        "schema_version": "r3-0-012-production-handoff/v1",
        "run_id": run_id,
        "task_id": CONFIGURATION["task_id"],
        "profile_id": CONFIGURATION["profile_id"],
        "run_contract_digest": "0" * 64,
        "freeze_id": frozen["batch_id"],
        "freeze_digest": frozen["snapshot_digest"],
        "delivery_binding": {"delivered_by": "coordinator"},
        "acceptance_target": "cq_semantic",
        "scope_binding": {"project_id": "project-1", "ontology_ids": ["ontology-1"]},
        "role_states": {},
        "applied_batches": [],
        "not_applied": [],
        "unknown_writes": [],
        "write_phase": "read-only",
        "joint_checklist": {"state": "pending"},
        "ready": True,
        "pending_writes": False,
        "acceptance_attempt_id": "attempt-0001",
        "batch_id": frozen["batch_id"],
        "report_directory": f"acceptance-v3/reports/{frozen['batch_id']}/attempt-0001",
    }
    payload.update(overrides)
    return payload


def _acceptance_source_run(
    *,
    questions: list[dict] | None = None,
    handoff_overrides: dict | None = None,
    state: dict | None = None,
    with_sources: bool = True,
    interviews: dict[str, dict] | None = None,
) -> tuple[Path, dict, str]:
    """A source run whose COMPLETE production handoff was checkpointed."""

    run_id = f"r3015acc-{os.urandom(4).hex()}"
    run_root = RUNS_ROOT / run_id
    frozen = _freeze(
        questions if questions is not None else [_question("cq-1"), _question("cq-2")]
    )
    frozen_dir = run_root / "competency-questions" / "frozen"
    frozen_dir.mkdir(parents=True)
    # The Runner stores snapshots as freeze-NNNN.json while the handoff's
    # freeze_id is the batch id: the continuation must bind by digest.
    (frozen_dir / "freeze-0001.json").write_text(json.dumps(frozen), encoding="utf-8")
    _write_json(
        run_root / "acceptance-v3" / "run-contract.json",
        {
            "schema_version": "r3-0-011-run-contract/v1",
            "run_id": run_id,
            "profile_id": "r3-0-011-competency-question",
            "task_id": CONFIGURATION["task_id"],
            "parameters": {
                "competency_question_acceptance": True,
                "acceptance_target": "cq_semantic",
            },
        },
    )
    handoff = _handoff_payload(run_id, frozen, **(handoff_overrides or {}))
    (run_root / "acceptance-v3" / "production-handoff.json").write_text(
        json.dumps(handoff, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    if with_sources:
        _write_sources(run_root)
    if state is not None:
        _write_json(run_root / "state.json", state)
    for name, record in (interviews or {}).items():
        _write_json(run_root / "competency-questions/private" / name, record)
    saved = save_checkpoint(
        run_root,
        StagePackage(
            kind=CHECKPOINT_KIND_PRODUCTION_HANDOFF,
            scope_refs={"freeze_id": frozen["batch_id"]},
            artifacts=[
                *[
                    CheckpointArtifactSpec(
                        source=f"competency-questions/private/{name}", owner="host",
                        visible_to=("host",), host_private=True,
                    ) for name in (interviews or {})
                ],
                CheckpointArtifactSpec(
                    source="acceptance-v3/production-handoff.json",
                    owner="host",
                    visible_to=("host",),
                    host_private=True,
                ),
                CheckpointArtifactSpec(
                    source="acceptance-v3/run-contract.json",
                    owner="host",
                    visible_to=("host",),
                    host_private=True,
                ),
            ],
            stage_facts={
                "freeze_id": frozen["batch_id"],
                "acceptance_target": "cq_semantic",
            },
            platform_bindings={"project_id": "project-1", "ontology_ids": ["ontology-1"]},
            write_positions={},
        ),
        source_run_id=run_id,
        configuration=dict(CONFIGURATION),
    )
    return run_root, frozen, saved["checkpoint_id"]


def _prepare(
    run_root: Path,
    checkpoint_id: str,
    *,
    new_run_id: str | None = None,
    platform: FakeCursorPlatform | None = None,
):
    return prepare_acceptance_continuation(
        source_run_root=run_root,
        checkpoint_id=checkpoint_id,
        new_run_id=new_run_id or f"r3015out-{os.urandom(4).hex()}",
        readback=_readback(platform or FakeCursorPlatform()),
        authorization_reference=_AUTHORIZATION,
    )


def _assert_public_rejection(error: CheckpointError) -> dict:
    """Every S4 refusal carries the §8 tuple and never private content."""

    payload = error.data()
    # Design §8 field names: code/object_ref/phase/retryable/reason plus the
    # optional next_action -- never the legacy internal spellings (D3).
    assert set(payload) >= {"code", "object_ref", "phase", "retryable", "reason"}
    assert set(payload) <= {
        "code",
        "object_ref",
        "phase",
        "retryable",
        "reason",
        "next_action",
    }
    assert not set(payload) & {"reason_code", "detail", "object", "retry"}
    assert payload["phase"] == "checkpoint-resume-acceptance"
    encoded = json.dumps(payload)
    assert "host-key-stand-in" not in encoded
    assert "placeholder" not in encoded  # hidden question text never travels
    return payload


def _examiner_report(question_id: str) -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": "batch-r3011",
        "question_id": question_id,
        "question_content_version": 1,
        "answer": f"answer for {question_id}",
        "evidence_refs": ["query_semantic_context|a|b"],
        "explicit_unknown": [],
        "status": "completed",
        "failure_layer": None,
        "reason": None,
    }


def _pass_verdict(question_id: str) -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": "batch-r3011",
        "question_id": question_id,
        "verdict": "pass",
        "failure_layer": None,
        "conflicting_evidence": [],
        "note": "",
    }


def _batch_report_for(
    frozen: dict, run_id: str, *, passed: list[str], unexecuted: list[str] = ()
) -> dict:
    hidden = [
        dict(question)
        for question in frozen["questions"]
        if question.get("visibility") == "hidden"
    ]
    report = build_batch_report(
        run_id=run_id,
        batch_id=frozen["batch_id"],
        freeze_digest=frozen["snapshot_digest"],
        model_binding_digest="sha256:" + "1" * 64,
        hidden_questions=hidden,
        examiner_reports=[_examiner_report(item) for item in passed],
        verdicts=[_pass_verdict(item) for item in passed],
        executed_question_ids=list(passed),
        unexecuted_question_ids=list(unexecuted),
    )
    report["full_pass"] = batch_report_is_full_pass(report)
    return report


def _cli_args(run_id: str, checkpoint_id: str, new_run_id: str) -> Namespace:
    return Namespace(
        run_id=run_id,
        checkpoint_id=checkpoint_id,
        new_run_id=new_run_id,
        mode="acceptance",
        base_url="http://stand-in.invalid",
        authorization_reference=_AUTHORIZATION,
        session_timeout=5.0,
    )


def test_checkpoint_cli_passes_explicit_acceptance_model_profile(monkeypatch):
    captured = []
    monkeypatch.setenv("ONTOLOGY_PLATFORM_ADMIN_API_KEY", "test-host-key")
    monkeypatch.setattr(sys, "argv", [
        "modeling_team", "checkpoint", "resume", "--run-id", "source",
        "--checkpoint-id", "production_handoff-0001", "--new-run-id", "continued",
        "--mode", "acceptance", "--model-profile", "openai-sol-medium",
    ])
    monkeypatch.setattr(main_module, "_run_checkpoint_resume_acceptance",
                        lambda args, root: captured.append(args) or 0)
    assert main_module.main() == 0
    assert captured[0].model_profile == "openai-sol-medium"


def _cleanup_run(run_root: Path) -> None:
    rmtree(run_root, ignore_errors=True)
    rmtree(RUNS_ROOT / f"{run_root.name}-ledger", ignore_errors=True)
    lock = RUNS_ROOT / ".recovery-locks" / f"{run_root.name}.lock"
    if lock.is_file():
        lock.unlink()


# --- entry prerequisites: only a COMPLETE production_handoff continues --------------


def test_s4_entry_accepts_only_a_complete_production_handoff_package():
    run_root, frozen, checkpoint_id = _acceptance_source_run()
    try:
        # A pre-handoff kind can never continue through --mode acceptance.
        cq_saved = save_checkpoint(
            run_root,
            StagePackage(
                kind=CHECKPOINT_KIND_CQ_FROZEN,
                scope_refs={"freeze_id": frozen["batch_id"]},
                artifacts=[
                    CheckpointArtifactSpec(
                        source="source-manifest.json", owner="host", visible_to=("host",)
                    )
                ],
                stage_facts={},
                platform_bindings={},
                write_positions={},
            ),
            source_run_id=run_root.name,
            configuration=dict(CONFIGURATION),
        )
        with pytest.raises(CheckpointError) as mismatch:
            _prepare(run_root, cq_saved["checkpoint_id"])
        payload = _assert_public_rejection(mismatch.value)
        assert payload["code"] == cr.REASON_KIND_MODE_MISMATCH
        assert "--mode production" in payload["next_action"]

        # The run's published handoff is a continuation prerequisite.
        (run_root / "acceptance-v3" / "production-handoff.json").unlink()
        with pytest.raises(CheckpointError) as unpublished:
            _prepare(run_root, checkpoint_id)
        payload = _assert_public_rejection(unpublished.value)
        assert payload["code"] == "checkpoint_incomplete"
        assert "no published production handoff" in payload["reason"]
    finally:
        _cleanup_run(run_root)

    # A package whose own handoff copy is gone is incomplete, not continuable.
    run_root, _frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    try:
        packaged = (
            run_root
            / "checkpoints"
            / checkpoint_id
            / CHECKPOINT_HOST_PRIVATE_DIRECTORY
            / "acceptance-v3"
            / "production-handoff.json"
        )
        packaged.unlink()
        with pytest.raises(CheckpointError) as unpackaged:
            _prepare(run_root, checkpoint_id)
        payload = _assert_public_rejection(unpackaged.value)
        assert payload["code"] == "checkpoint_incomplete"
        assert "is missing" in payload["reason"]
    finally:
        _cleanup_run(run_root)

    # The continuation never overwrites an existing run directory either.
    run_root, _frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    try:
        with pytest.raises(CheckpointError) as occupied:
            _prepare(run_root, checkpoint_id, new_run_id=run_root.name)
        payload = _assert_public_rejection(occupied.value)
        assert payload["code"] == "resume_new_run_exists"
    finally:
        _cleanup_run(run_root)


# --- M35: drift and open write gates are typed refusals, never a model fix -----------


def test_m35_binding_drift_and_open_gates_are_typed_refusals():
    # (a) Post-freeze tamper: the edited content no longer reproduces the
    # stored snapshot digest, and only the typed reload code is reported.
    run_root, _frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    try:
        pool_path = run_root / "competency-questions" / "frozen" / "freeze-0001.json"
        pool = json.loads(pool_path.read_text(encoding="utf-8"))
        pool["questions"][0]["question"] = "tampered hidden-material-marker question"
        pool_path.write_text(json.dumps(pool), encoding="utf-8")
        with pytest.raises(CheckpointError) as drifted:
            _prepare(run_root, checkpoint_id)
        payload = _assert_public_rejection(drifted.value)
        assert payload["code"] == cr.REASON_ACCEPTANCE_BINDING_CHANGED
        assert "failed re-validation" in payload["reason"]
        assert "tampered" not in json.dumps(payload)
    finally:
        _cleanup_run(run_root)

    # (b) A structurally broken pool reports the reload outcome only.
    run_root, _frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    try:
        pool_path = run_root / "competency-questions" / "frozen" / "freeze-0001.json"
        pool_path.write_text("{not json", encoding="utf-8")
        with pytest.raises(CheckpointError) as broken:
            _prepare(run_root, checkpoint_id)
        payload = _assert_public_rejection(broken.value)
        assert payload["code"] == cr.REASON_ACCEPTANCE_BINDING_CHANGED
        assert "failed re-validation (unreadable)" in payload["reason"]
    finally:
        _cleanup_run(run_root)

    # (c) The run's published handoff drifted away from the checkpoint package.
    run_root, _frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    try:
        published = run_root / "acceptance-v3" / "production-handoff.json"
        handoff = json.loads(published.read_text(encoding="utf-8"))
        handoff["delivery_binding"] = {"delivered_by": "someone-else"}
        published.write_text(
            json.dumps(handoff, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        with pytest.raises(CheckpointError) as replaced:
            _prepare(run_root, checkpoint_id)
        payload = _assert_public_rejection(replaced.value)
        assert payload["code"] == cr.REASON_ACCEPTANCE_BINDING_CHANGED
        assert "no longer equals" in payload["reason"]
    finally:
        _cleanup_run(run_root)

    # (d) Known not-applied work is evidence of a settled non-write and does not
    # block read-only acceptance continuation.
    run_root, _frozen, checkpoint_id = _acceptance_source_run(
        with_sources=False, handoff_overrides={"not_applied": [{"batch_id": "b3"}]}
    )
    output_run_id = f"r3015out-{os.urandom(4).hex()}"
    try:
        continuation = _prepare(run_root, checkpoint_id, new_run_id=output_run_id)
        assert continuation.handoff["not_applied"] == [{"batch_id": "b3"}]
    finally:
        _cleanup_run(run_root)
        rmtree(RUNS_ROOT / output_run_id, ignore_errors=True)

    # (e) An unknown chain write keeps the write gate closed.
    run_root, _frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    try:
        _seed_chain_intent(
            run_root,
            7,
            key="idem-late",
            client_batch_id="cb-late",
            session_id="session-late",
            status="unknown",
            with_receipt=False,
        )
        with pytest.raises(CheckpointError) as unreconciled:
            _prepare(run_root, checkpoint_id)
        payload = _assert_public_rejection(unreconciled.value)
        assert payload["code"] == REASON_WRITE_UNRECONCILED
        assert "closed clean" in payload["reason"]
    finally:
        _cleanup_run(run_root)

    # (f) A possibly-live source writer: acceptance never runs alongside it.
    run_root, _frozen, checkpoint_id = _acceptance_source_run(
        with_sources=False, state={"state": "RUNNING"}
    )
    try:
        with pytest.raises(CheckpointError) as active:
            _prepare(run_root, checkpoint_id)
        payload = _assert_public_rejection(active.value)
        assert payload["code"] == REASON_SOURCE_ACTIVE
        assert payload["retryable"] is True
        assert "60s" in payload["next_action"]
    finally:
        _cleanup_run(run_root)

    # (g) Unattributable platform writes on the bound ontology are scope drift.
    run_root, _frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    try:
        platform = FakeCursorPlatform(
            ontology_batches={
                "ontology-1": [
                    {"batch_id": "b-foreign", "build_session_id": "session-other"}
                ]
            }
        )
        with pytest.raises(CheckpointError) as drift:
            _prepare(run_root, checkpoint_id, platform=platform)
        payload = _assert_public_rejection(drift.value)
        assert payload["code"] == REASON_SCOPE_DRIFT
    finally:
        _cleanup_run(run_root)


def test_s4_settlement_opens_the_stale_state_gate_for_a_fresh_source_run():
    """A host settlement of a fresh stale source run opens the S4 gate too."""

    run_root, _frozen, checkpoint_id = _acceptance_source_run(
        with_sources=False, state={"state": "WAITING_OWNER"}
    )
    try:
        with pytest.raises(CheckpointError) as stale:
            _prepare(run_root, checkpoint_id)
        payload = _assert_public_rejection(stale.value)
        assert payload["code"] == REASON_SOURCE_ACTIVE
        assert "settle-source" in payload["next_action"]
        cr.settle_source_run(
            run_root=run_root,
            stop_reference="host-stop-2026-09-17",
            readback=_readback(FakeCursorPlatform()),
        )
        plan = _prepare(run_root, checkpoint_id)
        assert plan.inspection["source_writer"]["verdict"] == "writer_process_exited"
    finally:
        _cleanup_run(run_root)
        cr.settlement_record_path(RUNS_ROOT, run_root.name).unlink(missing_ok=True)


# --- M36: frozen scope stays frozen; private material never leaks --------------------


def test_m36_frozen_scope_and_private_material_stay_frozen():
    run_root, frozen, checkpoint_id = _acceptance_source_run()
    platform = FakeCursorPlatform()
    try:
        continuation = _prepare(run_root, checkpoint_id, platform=platform)
        # The re-validated pool IS the handoff's pool: same batch, same digest,
        # resolved through the freeze-NNNN file (never a re-freeze).
        assert continuation.batch_id == frozen["batch_id"]
        assert continuation.freeze_digest == frozen["snapshot_digest"]
        assert continuation.freeze_file.name == "freeze-0001.json"
        inspection = continuation.inspection
        assert inspection["frozen_pool"]["source_file"] == (
            "competency-questions/frozen/freeze-0001.json"
        )
        assert inspection["frozen_pool"]["revalidated"] is True
        assert inspection["frozen_pool"]["hidden_question_count"] == 2
        # The frozen acceptance target travels unchanged (a CQ PASS is never
        # reported as full acceptance).
        assert continuation.handoff["acceptance_target"] == "cq_semantic"
        assert inspection["handoff"]["acceptance_target"] == "cq_semantic"
        # Host records carry structure, never hidden question text.
        assert "placeholder" not in json.dumps(inspection)
        assert "placeholder" not in json.dumps(continuation.origin)
        # The readback consulted only the cursor endpoint families.
        assert platform.unexpected == []
        allowed = (
            "/api/build-sessions/",
            "/api/ontologies/ontology-1/modeling-batches",
            "/api/modeling-batches/",
        )
        assert all(path.split("?")[0].startswith(allowed) for path in platform.paths)
    finally:
        _cleanup_run(run_root)


# --- M37: zero semantic starts; attempts allocate across continuation roots ----------


def test_m37_zero_semantic_starts_and_attempt_allocation_across_roots():
    run_root, frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    prior_output = RUNS_ROOT / f"r3015out-{os.urandom(4).hex()}"
    foreign_output = RUNS_ROOT / f"r3015out-{os.urandom(4).hex()}"
    try:
        # The source run's own attempt (whatever it holds) occupies its slot.
        (
            run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
        ).mkdir(parents=True)
        # An earlier continuation is discoverable through its origin record.
        (
            prior_output
            / "acceptance-v3"
            / "reports"
            / frozen["batch_id"]
            / "attempt-0003"
        ).mkdir(parents=True)
        _write_json(
            prior_output / RECOVERY_DIRECTORY / "origin.json",
            {
                "schema_version": cr.RECOVERY_SCHEMA,
                "kind": "acceptance_continuation",
                "source_run_id": run_root.name,
            },
        )
        # A continuation of a DIFFERENT source run is not part of this chain.
        _write_json(
            foreign_output / RECOVERY_DIRECTORY / "origin.json",
            {
                "schema_version": cr.RECOVERY_SCHEMA,
                "kind": "acceptance_continuation",
                "source_run_id": "someone-else",
            },
        )
        roots = cr.prior_continuation_roots(RUNS_ROOT, run_root.name)
        assert prior_output in roots
        assert foreign_output not in roots

        continuation = _prepare(run_root, checkpoint_id)
        assert continuation.prior_output_roots == roots
        assert continuation.report_roots == [run_root, prior_output]
        # attempt-0002 is the next FREE id even with attempt-0003 taken.
        assert continuation.attempt_id == "attempt-0002"
        assert continuation.prior_attempts == ["attempt-0001", "attempt-0003"]

        accounting = continuation.inspection["accounting"]
        assert accounting["semantic_starts"] == 0
        assert accounting["consumes_semantic_start"] is False
        assert accounting["kind"] == "acceptance_continuation"
        assert accounting["authorization_reference"] == _AUTHORIZATION
        assert continuation.origin["authorization_reference"] == _AUTHORIZATION
        # Prep (re-verification) time is measured and budgeted; execution time
        # is reported separately in the closing record.
        timing = continuation.inspection["prep_timing"]
        assert timing["budget_seconds"] == cr.PREP_BUDGET_SECONDS
        assert timing["over_budget"] is False
    finally:
        _cleanup_run(run_root)
        rmtree(prior_output, ignore_errors=True)
        rmtree(foreign_output, ignore_errors=True)


# --- M34: a complete usable PASS report means verification-only closing --------------


def test_m34_complete_pass_report_means_verification_only_closing(monkeypatch, capsys):
    run_root, frozen, checkpoint_id = _acceptance_source_run()
    new_run_id = f"r3015out-{os.urandom(4).hex()}"
    output_root = RUNS_ROOT / new_run_id
    try:
        report = _batch_report_for(frozen, run_root.name, passed=["cq-1", "cq-2"])
        assert report["full_pass"] is True
        attempt_dir = (
            run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
        )
        attempt_dir.mkdir(parents=True)
        (attempt_dir / "batch-report.json").write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        before = _tree_state(run_root)

        monkeypatch.setattr(
            main_module, "http_readback", lambda base_url, key: _readback(FakeCursorPlatform())
        )

        def _must_not_re_execute(*args, **kwargs):
            raise AssertionError(
                "a complete usable PASS report must not re-execute acceptance"
            )

        monkeypatch.setattr(main_module, "_run_cq_acceptance", _must_not_re_execute)
        code = main_module._run_checkpoint_resume_acceptance(
            _cli_args(run_root.name, checkpoint_id, new_run_id),
            REPO_ROOT,
            forwarder_factory=_Factory(_DualForwarder(_platform_context(), [])),
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["mode"] == "verification-only-closing"
        assert payload["full_pass"] is True
        assert payload["model_sessions_started"] == 0
        assert payload["semantic_starts"] == 0
        assert payload["consumes_semantic_start"] is False
        assert payload["verified_report"].endswith("attempt-0001/batch-report.json")

        # The origin landed before any execution; host-only permissions.
        origin_path = output_root / RECOVERY_DIRECTORY / "origin.json"
        origin = json.loads(origin_path.read_text(encoding="utf-8"))
        assert origin["kind"] == "acceptance_continuation"
        assert origin["source_run_id"] == run_root.name
        assert origin["checkpoint_id"] == checkpoint_id
        assert stat.S_IMODE(origin_path.stat().st_mode) == 0o600

        record = json.loads(
            (output_root / RECOVERY_DIRECTORY / ACCEPTANCE_CONTINUATION_RECORD).read_text(
                encoding="utf-8"
            )
        )
        assert record["schema_version"] == ACCEPTANCE_CONTINUATION_SCHEMA
        assert record["mode"] == "verification-only-closing"
        assert record["model_sessions_started"] == 0
        assert record["accounting"]["semantic_starts"] == 0
        assert record["accounting"]["consumes_semantic_start"] is False
        assert record["outcome"] == {"status": "closed", "full_pass": True}
        assert record["verified_report"]["report_path"].endswith(
            "attempt-0001/batch-report.json"
        )
        # Verification-only closing starts nothing: no report tree at all.
        assert not (output_root / "acceptance-v3").exists()
        # The source run keeps its own report bytes and gains nothing.
        assert _tree_state(run_root) == before
    finally:
        _cleanup_run(run_root)
        rmtree(output_root, ignore_errors=True)


# --- M34: a prior partial report is preserved and never spliced ---------------------


def test_m34_prior_partial_report_is_preserved_and_never_spliced(monkeypatch):
    run_root, frozen, checkpoint_id = _acceptance_source_run()
    new_run_id = f"r3015out-{os.urandom(4).hex()}"
    output_root = RUNS_ROOT / new_run_id
    try:
        reports = run_root / "acceptance-v3" / "reports" / frozen["batch_id"]
        partial = _batch_report_for(frozen, run_root.name, passed=["cq-1"], unexecuted=["cq-2"])
        assert partial["full_pass"] is False
        (reports / "attempt-0001").mkdir(parents=True)
        (reports / "attempt-0001" / "batch-report.json").write_text(
            json.dumps(partial, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        partial_bytes = (reports / "attempt-0001" / "batch-report.json").read_bytes()
        # A full-PASS-shaped report bound to a DIFFERENT freeze is not usable.
        foreign = _batch_report_for(frozen, run_root.name, passed=["cq-1", "cq-2"])
        foreign["freeze_digest"] = "sha256:" + "9" * 64
        (reports / "attempt-0009").mkdir(parents=True)
        (reports / "attempt-0009" / "batch-report.json").write_text(
            json.dumps(foreign, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        roots = [run_root]
        digest = frozen["snapshot_digest"]
        assert cr.find_complete_pass_report(roots, frozen["batch_id"], digest) is None

        before = _tree_state(run_root)
        monkeypatch.setattr(
            main_module, "http_readback", lambda base_url, key: _readback(FakeCursorPlatform())
        )
        adapter_class, state = _batch_adapter()
        monkeypatch.setattr(main_module, "CodexRuntimeAdapter", adapter_class)
        monkeypatch.setenv(main_module._CQ_PLATFORM_READ_KEY_ENV, "read-key")
        code = main_module._run_checkpoint_resume_acceptance(
            _cli_args(run_root.name, checkpoint_id, new_run_id),
            REPO_ROOT,
            forwarder_factory=_Factory(
                _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT] * 2)
            ),
        )
        assert code == 0

        # The judge packet carried the FULL frozen denominator: the new attempt
        # re-executes every question, it never splices the prior partial run.
        judged = [str(item["question_id"]) for item in state["judge_payload"]["questions"]]
        assert judged == ["cq-1", "cq-2"]
        new_attempt = output_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0002"
        report = json.loads((new_attempt / "batch-report.json").read_text(encoding="utf-8"))
        assert report["full_pass"] is True
        assert report["executed_question_ids"] == ["cq-1", "cq-2"]
        assert report["unexecuted_question_ids"] == []
        assert report["blind_status"]["blind_status"] == "blind"

        # The prior partial attempt keeps its own bytes on the source run, and
        # the source run gained nothing (input/output separation).
        assert (reports / "attempt-0001" / "batch-report.json").read_bytes() == partial_bytes
        assert _tree_state(run_root) == before
        # This attempt's platform-read artifacts live under the OUTPUT root.
        assert list((output_root / "acceptance").rglob("*.json"))
        assert not (run_root / "acceptance").exists()

        record = json.loads(
            (output_root / RECOVERY_DIRECTORY / ACCEPTANCE_CONTINUATION_RECORD).read_text(
                encoding="utf-8"
            )
        )
        assert record["mode"] == "re-executed"
        assert record["attempt_id"] == "attempt-0002"
        assert record["prior_attempts"] == ["attempt-0001", "attempt-0009"]
        assert record["report_published"] is True
        assert record["full_pass"] is True
        assert record["outcome"] == {"status": "pass"}
        assert record["accounting"]["semantic_starts"] == 0
        assert record["accounting"]["consumes_semantic_start"] is False
    finally:
        _cleanup_run(run_root)
        rmtree(output_root, ignore_errors=True)


def _evidence_root_adapter(adapter_class):
    """Wrap an Examiner/Judge developer double so each session records its evidence root.

    Both production adapter constructions in ``_cq_execute_batch`` must bind the
    existing ``_run_root`` to this attempt's artifact root before the session
    starts, or the real ``_append_runtime_evidence``/``_retain_child_session``
    sinks stay dead.  The double proves the binding by calling the real
    ``CodexRuntimeAdapter._append_runtime_evidence`` at session time and
    recording the root it observed.
    """

    state: dict = {"evidence_roots": []}

    class _EvidenceRootAdapter(adapter_class):
        def run_v3_acceptance_child(self, packet, **kwargs):
            run_root = getattr(self, "_run_root", None)
            state["evidence_roots"].append(run_root)
            if isinstance(run_root, Path):
                CodexRuntimeAdapter._append_runtime_evidence(
                    self, "runtime-evidence", {"session": "developer-double"}
                )
            return super().run_v3_acceptance_child(packet, **kwargs)

    return _EvidenceRootAdapter, state


# --- M44: runtime evidence is bound to this attempt's artifact root -----------------


@pytest.mark.parametrize("source", [
    "competency-questions/private/interview-0001.json",
    "private/interview-0001.json", "interview-0001.json",
])
def test_s4_judge_reads_checkpoint_interview_after_real_private_cleanup(monkeypatch, source):
    from modeling_team.runner import TeamRunner

    question = _question("cq-1")
    question["evidence_refs"] = [{
        "source": source, "locator": "interview 1",
    }]
    interview = {"schema_version": "r3-0-011-cq-interview/v1", "ordinal": 1,
                 "text": "Approved generic interview fixture."}
    run_root, frozen, checkpoint_id = _acceptance_source_run(
        questions=[question], interviews={"interview-0001.json": interview},
    )
    new_run_id = f"r3015out-{os.urandom(4).hex()}"
    output_root = RUNS_ROOT / new_run_id
    try:
        cleanup = TeamRunner._cleanup_cq_private(SimpleNamespace(
            run=SimpleNamespace(root=run_root), _append_evidence=lambda *args: None,
        ))
        assert cleanup["directory_removed"] is True
        assert not (run_root / "competency-questions/private").exists()
        before = _tree_state(run_root)
        _, unresolved = main_module._cq_build_judge_evidence_bundle(run_root, frozen, [question])
        assert "cq-1" in unresolved  # The ordinary live path stays fail-closed.
        examiner_packets = []
        adapter_class, state = _batch_adapter(
            on_examiner_packet=lambda packet: examiner_packets.append(packet.to_dict()),
        )
        monkeypatch.setattr(main_module, "CodexRuntimeAdapter", adapter_class)
        monkeypatch.setattr(main_module, "http_readback", lambda *args: _readback(FakeCursorPlatform()))
        monkeypatch.setenv(main_module._CQ_PLATFORM_READ_KEY_ENV, "read-key")
        code = main_module._run_checkpoint_resume_acceptance(
            _cli_args(run_root.name, checkpoint_id, new_run_id), REPO_ROOT,
            forwarder_factory=_Factory(_DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])),
        )
        assert code == 0
        entry = state["judge_payload"]["evidence_bundle"]["entries"][0]
        archived = run_root / "checkpoints" / checkpoint_id / "host-private/competency-questions/private/interview-0001.json"
        assert entry["content"] == archived.read_text()
        assert entry["content_digest"] == main_module.content_digest(archived.read_text())
        assert "Approved generic interview fixture." not in json.dumps(examiner_packets)
        assert _tree_state(run_root) == before
    finally:
        _cleanup_run(run_root)
        rmtree(output_root, ignore_errors=True)


def test_public_s4_reexecutes_after_hidden_pass_with_public_denominator_and_isolation(monkeypatch):
    questions = [_question("hidden-1"), _question("public-1", visibility="public"),
                 _question("public-2", visibility="public", kind="slice")]
    run_root, frozen, checkpoint_id = _acceptance_source_run(questions=questions)
    new_run_id = f"r3015out-{os.urandom(4).hex()}"
    output_root = RUNS_ROOT / new_run_id
    try:
        hidden_report = _batch_report_for(frozen, run_root.name, passed=["hidden-1"])
        _write_json(run_root / "acceptance-v3/reports" / frozen["batch_id"] / "attempt-0001/batch-report.json", hidden_report)
        before = _tree_state(run_root)
        packets = []
        adapter, state = _batch_adapter(on_examiner_packet=lambda packet: packets.append(packet.to_dict()["payload"]))
        monkeypatch.setattr(main_module, "CodexRuntimeAdapter", adapter)
        monkeypatch.setattr(main_module, "http_readback", lambda *args: _readback(FakeCursorPlatform()))
        monkeypatch.setenv(main_module._CQ_PLATFORM_READ_KEY_ENV, "read-key")
        args = _cli_args(run_root.name, checkpoint_id, new_run_id)
        args.model_profile = "openai-sol-medium"
        args.question_visibility = "public"
        code = main_module._run_checkpoint_resume_acceptance(
            args, REPO_ROOT,
            forwarder_factory=_Factory(_DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT] * 2)),
        )
        assert code == 0
        assert len(packets) == 1  # A hidden PASS must not close public verification.
        assert [item["question_id"] for item in packets[0]["questions"]] == ["public-1", "public-2"]
        assert all(set(item) == {"question_id", "content_version", "question", "scope"}
                   for item in packets[0]["questions"])
        assert [item["question_id"] for item in state["judge_payload"]["questions"]] == ["public-1", "public-2"]
        report = json.loads((output_root / "acceptance-v3/reports" / frozen["batch_id"] / "attempt-0002/batch-report.json").read_text())
        assert report["question_selection"] == {"visibility": "public", "question_ids": ["public-1", "public-2"]}
        assert report["blind_status"]["blind_status"] == "non-blind-regression"
        assert report["coverage_gaps"]["empty_public_set"] is False
        assert "empty_hidden_set" not in report["coverage_gaps"]
        assert report["executed_question_ids"] == ["public-1", "public-2"]
        assert report["full_pass"] is True
        assert cr.find_complete_pass_report(
            [output_root], frozen["batch_id"], frozen["snapshot_digest"],
            question_visibility="public", question_ids=["public-1", "public-2"],
        ) is not None
        assert cr.find_complete_pass_report(
            [output_root], frozen["batch_id"], frozen["snapshot_digest"],
            question_ids=["hidden-1"],
        ) is None
        assert cr.find_complete_pass_report(
            [output_root], frozen["batch_id"], frozen["snapshot_digest"],
            question_visibility="public", question_ids=["public-1", "public-2", "public-3"],
        ) is None
        assert _tree_state(run_root) == before
    finally:
        _cleanup_run(run_root)
        rmtree(output_root, ignore_errors=True)


@pytest.mark.parametrize("defect", [
    "record_digest", "manifest_digest", "source_binding", "checkpoint_binding",
    "file_symlink", "directory_symlink", "undeclared", "schema", "empty_text", "escape",
    "missing_archive",
])
def test_s4_archived_interview_keeps_binding_digest_path_and_schema_guards(defect):
    from copy import deepcopy

    question = _question("cq-1")
    source = "competency-questions/private/interview-0001.json"
    question["evidence_refs"] = [{"source": source, "locator": "generic interview"}]
    record = {"schema_version": "r3-0-011-cq-interview/v1", "ordinal": 1, "text": "Generic."}
    if defect == "schema":
        record["schema_version"] = "invalid"
    elif defect == "empty_text":
        record["text"] = ""
    run_root, frozen, checkpoint_id = _acceptance_source_run(
        questions=[question], interviews={"interview-0001.json": record},
    )
    try:
        plan = _prepare(run_root, checkpoint_id)
        package = run_root / "checkpoints" / checkpoint_id
        archived = package / "host-private" / source
        if defect == "record_digest":
            archived.chmod(0o600)
            archived.write_text(json.dumps({**record, "text": "Changed."}))
        elif defect == "missing_archive":
            archived.unlink()  # The still-present live record must not rescue S4.
        elif defect == "manifest_digest":
            manifest_file = package / "manifest.json"
            manifest_file.chmod(0o600)
            manifest_file.write_text(manifest_file.read_text() + "\n")
        elif defect == "source_binding":
            plan.manifest = {**plan.manifest, "source_run_id": "another-source"}
        elif defect == "checkpoint_binding":
            plan.checkpoint_id = "another-checkpoint"
        elif defect == "file_symlink":
            archived.unlink()
            archived.symlink_to(run_root / source)  # Same bytes still reject the link.
        elif defect == "directory_symlink":
            directory = archived.parent
            directory.rename(directory.with_name("saved-private"))
            directory.symlink_to(directory.with_name("saved-private"), target_is_directory=True)
        elif defect == "undeclared":
            plan.manifest = deepcopy(plan.manifest)
            plan.manifest["artifacts"] = [entry for entry in plan.manifest["artifacts"]
                                          if entry["source"] != source]
        elif defect == "escape":
            question["evidence_refs"][0]["source"] = "competency-questions/private/../interview-0001.json"
        bundle, failures = main_module._cq_build_judge_evidence_bundle(
            run_root, frozen, [question], interview_checkpoint=plan,
        )
        assert bundle["entries"] == []
        assert "cq-1" in failures
    finally:
        _cleanup_run(run_root)


def test_m44_continuation_sessions_bind_runtime_evidence_to_their_output_root(monkeypatch):
    run_root, frozen, checkpoint_id = _acceptance_source_run()
    new_run_id = f"r3015out-{os.urandom(4).hex()}"
    output_root = RUNS_ROOT / new_run_id
    try:
        before = _tree_state(run_root)
        monkeypatch.setattr(
            main_module, "http_readback", lambda base_url, key: _readback(FakeCursorPlatform())
        )
        adapter_class, state = _batch_adapter()
        evidence_adapter, evidence_state = _evidence_root_adapter(adapter_class)
        model_bindings = []
        original_bind = evidence_adapter.bind_acceptance_model_profile

        def capture_binding(self, profile):
            model_bindings.append(profile.profile_id)
            return original_bind(self, profile)

        monkeypatch.setattr(evidence_adapter, "bind_acceptance_model_profile", capture_binding)
        monkeypatch.setattr(main_module, "CodexRuntimeAdapter", evidence_adapter)
        monkeypatch.setenv(main_module._CQ_PLATFORM_READ_KEY_ENV, "read-key")
        args = _cli_args(run_root.name, checkpoint_id, new_run_id)
        args.model_profile = "openai-sol-medium"
        code = main_module._run_checkpoint_resume_acceptance(
            args,
            REPO_ROOT,
            forwarder_factory=_Factory(
                _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT] * 2)
            ),
        )
        assert code == 0
        assert model_bindings == ["openai-sol-medium", "openai-sol-medium"]
        # Both sessions of the re-executed attempt (platform Examiner, then
        # independent judge) write their runtime evidence under the
        # continuation's output root, never the read-only source run.
        assert evidence_state["evidence_roots"] == [output_root, output_root]
        assert (output_root / "evidence" / "runtime-evidence.jsonl").is_file()
        assert not (run_root / "evidence").exists()
        assert _tree_state(run_root) == before
    finally:
        _cleanup_run(run_root)
        rmtree(output_root, ignore_errors=True)


def test_m44_plain_acceptance_sessions_bind_runtime_evidence_to_the_run_root(
    monkeypatch, tmp_path
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1"), _question("cq-2")])
    handoff = _write_handoff(tmp_path, frozen)
    adapter_class, _state = _batch_adapter()
    evidence_adapter, evidence_state = _evidence_root_adapter(adapter_class)
    monkeypatch.setattr(main_module, "CodexRuntimeAdapter", evidence_adapter)
    monkeypatch.setenv(main_module._CQ_PLATFORM_READ_KEY_ENV, "read-key")
    code = main_module._run_cq_acceptance(
        Namespace(
            run_root=run_root,
            freeze_id="freeze-0001",
            model_handoff=handoff,
            model_profile=None,
            session_timeout=5.0,
            unexecuted_report=False,
        ),
        REPO_ROOT,
        forwarder_factory=_Factory(
            _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT] * 2)
        ),
    )
    assert code == 0
    # Without a continuation the run root IS the attempt's artifact root.
    assert evidence_state["evidence_roots"] == [run_root, run_root]
    assert (run_root / "evidence" / "runtime-evidence.jsonl").is_file()


# --- M33: REAL process boundary -- a terminated producer, the CLI continues ----------


class _CursorOnlyStandIn(BaseHTTPRequestHandler):
    """Local HTTP stand-in serving ONLY the cursor-paginated read endpoints.

    Every request is recorded; anything outside the read families (including
    every write method) is a 404, so the test can prove the continuation
    performed zero platform writes.
    """

    def _serve(self) -> None:
        self.server.requests.append((self.command, self.path))  # type: ignore[attr-defined]
        base = self.path.split("?", 1)[0]
        body = None
        if self.command == "GET":
            if base.endswith("/modeling-batches") and (
                base.startswith("/api/build-sessions/")
                or base.startswith("/api/ontologies/")
            ):
                body = {"batches": [], "next_cursor": None}
            elif base.startswith("/api/build-sessions/"):
                # Session detail is allowed for lease state only (D1).
                body = {
                    "session": {"id": base.rsplit("/", 1)[-1], "status": "completed"},
                    "leases": [],
                }
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    do_GET = _serve  # type: ignore[assignment]
    do_POST = _serve  # type: ignore[assignment]
    do_PUT = _serve  # type: ignore[assignment]
    do_PATCH = _serve  # type: ignore[assignment]
    do_DELETE = _serve  # type: ignore[assignment]

    def log_message(self, *args) -> None:  # noqa: ARG002
        return None


_CHILD_HANDOFF_SCRIPT = """
import hashlib
import json
import os
import sys

from modeling_team.tests.test_r30015_checkpoints import (
    PROFILE,
    _CheckpointRunner,
    _SettledTransport,
    _freeze,
)


class BoundHarness(_CheckpointRunner):
    def prepare(self):
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=self._task_path,
            scope={
                "mode": "create",
                "project_id": "project-1",
                "ontology_ids": ["ontology-1"],
            },
        )
        return self.runner


harness = BoundHarness()
runner = harness.prepare()
# batch-r3011 because the in-process step-(3) Examiner/Judge developer double
# hardcodes that batch id in its report envelopes (a stand-in constraint, not
# a product constraint); the real Runner accepts any batch id here.
# The judge evidence bundle resolves these staged sources later.
content = "approved scenario bytes\\n"
digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
manifest = [{"path": "scenario-brief", "sha256": digest, "review_content_version": 1}]
for role in ("coordinator", "modeling", "competency-question"):
    copy = runner.run.root / "sources" / role / "scenario-brief"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text(content, encoding="utf-8")
(runner.run.root / "source-manifest.json").write_text(
    json.dumps({"schema_version": "r3-0-009-source-manifest/v1", "sources": manifest}),
    encoding="utf-8",
)
frozen = _freeze(runner, batch_id="batch-r3011")
runner.transport = _SettledTransport(runner)
ack = runner.handle_cq_outer_input(
    {
        "action": "cq_handoff_complete",
        "freeze_id": "batch-r3011",
        "freeze_digest": frozen["snapshot_digest"],
        "delivery_binding": {"delivery_id": "d-r3015", "digest": frozen["snapshot_digest"]},
    }
)
runner.cleanup()
print(json.dumps({"run_id": harness.run_id, "ok": ack["ok"],
                  "freeze_digest": frozen["snapshot_digest"]}))
sys.stdout.flush()
os._exit(0)
"""


def _run_resume_cli(
    run_id: str, checkpoint_id: str, new_run_id: str, base_url: str
) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT),
        "ONTOLOGY_PLATFORM_ADMIN_API_KEY": "host-key-cli-stand-in",
    }
    env.pop(main_module._CQ_PLATFORM_READ_KEY_ENV, None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "modeling_team",
            "checkpoint",
            "resume",
            "--run-id",
            run_id,
            "--checkpoint-id",
            checkpoint_id,
            "--new-run-id",
            new_run_id,
            "--mode",
            "acceptance",
            "--base-url",
            base_url,
            "--authorization-reference",
            "user-2026-09-14-r3015-acceptance-cli",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(REPO_ROOT),
    )


def test_m33_real_cli_continuation_with_the_producer_process_gone(monkeypatch):
    # (1) A genuinely separate producer process: real TeamRunner, real freeze,
    # real published handoff + production_handoff checkpoint, then cleanup and
    # hard exit.  This pytest process and the CLI processes below are all
    # different OS processes from it.
    finished = subprocess.run(
        [sys.executable, "-c", _CHILD_HANDOFF_SCRIPT],
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(REPO_ROOT),
    )
    assert finished.returncode == 0, finished.stderr
    child = json.loads(finished.stdout.strip().splitlines()[-1])
    assert child["ok"] is True
    source_root = RUNS_ROOT / child["run_id"]
    try:
        handoff_checkpoints = [
            entry["checkpoint_id"]
            for entry in list_checkpoints(source_root)
            if entry["kind"] == CHECKPOINT_KIND_PRODUCTION_HANDOFF
        ]
        assert len(handoff_checkpoints) == 1
        checkpoint_id = handoff_checkpoints[0]

        server = ThreadingHTTPServer(("127.0.0.1", 0), _CursorOnlyStandIn)
        server.requests = []
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            # (2) First CLI continuation: no complete report exists, so the
            # executed path starts -- and refuses here for the accurate reason
            # that no authorized platform read key is present.  The refusal is
            # recorded under the OUTPUT root, never posted to the dead
            # producer's FIFO, and the source run gains nothing.
            producer_final = _tree_state(source_root)
            new_run_1 = f"r3015out-{os.urandom(4).hex()}"
            first = _run_resume_cli(child["run_id"], checkpoint_id, new_run_1, base_url)
            assert first.returncode == 2, first.stderr
            assert main_module._CQ_PLATFORM_READ_KEY_ENV in first.stderr
            output_1 = RUNS_ROOT / new_run_1
            origin = json.loads(
                (output_1 / RECOVERY_DIRECTORY / "origin.json").read_text(encoding="utf-8")
            )
            assert origin["kind"] == "acceptance_continuation"
            assert origin["source_run_id"] == child["run_id"]
            record = json.loads(
                (output_1 / RECOVERY_DIRECTORY / ACCEPTANCE_CONTINUATION_RECORD).read_text(
                    encoding="utf-8"
                )
            )
            assert record["mode"] == "re-executed"
            assert record["exit_status"] == 2
            assert record["report_published"] is False
            assert record["outcome"] == {"status": "no-report", "exit_status": 2}
            assert record["accounting"]["semantic_starts"] == 0
            # The dead producer's run is byte-for-byte exactly as it left it:
            # no dead-FIFO dependency, no appended failure classification.
            assert _tree_state(source_root) == producer_final

            # (3) The complete PASS report the producer's own acceptance
            # attempt would have published: driven here in-process through the
            # REAL cq-acceptance executed path with the developer doubles
            # (Examiner/Judge stand-ins, not real providers).
            monkeypatch.setattr(main_module, "CodexRuntimeAdapter", _batch_adapter()[0])
            monkeypatch.setenv(main_module._CQ_PLATFORM_READ_KEY_ENV, "read-key")
            freeze_file = next(
                (source_root / "competency-questions" / "frozen").glob("freeze-*.json")
            )
            code = main_module._run_cq_acceptance(
                Namespace(
                    run_root=source_root,
                    freeze_id=freeze_file.stem,
                    model_handoff=source_root
                    / "acceptance-v3"
                    / "production-handoff.json",
                    model_profile=None,
                    session_timeout=5.0,
                    unexecuted_report=False,
                ),
                REPO_ROOT,
                forwarder_factory=_Factory(
                    _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
                ),
            )
            assert code == 0
            source_report = (
                source_root
                / "acceptance-v3"
                / "reports"
                / "batch-r3011"
                / "attempt-0001"
                / "batch-report.json"
            )
            assert json.loads(source_report.read_text(encoding="utf-8"))["full_pass"] is True
            after_producer_report = _tree_state(source_root)
            report_bytes = source_report.read_bytes()

            # (4) Second CLI continuation in another fresh process: the
            # complete usable PASS report now means verification and host
            # closing only -- zero model sessions, zero read key needed.
            new_run_2 = f"r3015out-{os.urandom(4).hex()}"
            second = _run_resume_cli(child["run_id"], checkpoint_id, new_run_2, base_url)
            assert second.returncode == 0, second.stderr
            payload = json.loads(second.stdout.strip().splitlines()[-1])
            assert payload["mode"] == "verification-only-closing"
            assert payload["full_pass"] is True
            assert payload["model_sessions_started"] == 0
            assert payload["semantic_starts"] == 0
            assert payload["consumes_semantic_start"] is False
            assert payload["verified_report"].endswith("attempt-0001/batch-report.json")
            record = json.loads(
                (RUNS_ROOT / new_run_2 / RECOVERY_DIRECTORY / ACCEPTANCE_CONTINUATION_RECORD)
                .read_text(encoding="utf-8")
            )
            assert record["mode"] == "verification-only-closing"
            assert record["outcome"] == {"status": "closed", "full_pass": True}
            # The producer's report bytes and failure classification stay as
            # they were; nothing was appended to its run.
            assert source_report.read_bytes() == report_bytes
            assert _tree_state(source_root) == after_producer_report
            # Attempt bookkeeping spans the source run and the earlier
            # continuation output root without reusing either attempt.
            assert record["prior_attempts"] == ["attempt-0001"]
            assert record["attempt_id"] == "attempt-0002"

            # (5) Zero platform writes: only cursor-paginated GETs were ever
            # served across both CLI processes (zero write sessions, zero
            # production threads -- M33).
            methods = {method for method, _path in server.requests}
            assert methods <= {"GET"}
            allowed_prefixes = (
                "/api/build-sessions/",
                "/api/ontologies/",
                "/api/modeling-batches/",
            )
            assert all(
                path.split("?")[0].startswith(allowed_prefixes)
                for _method, path in server.requests
            )
        finally:
            server.shutdown()
            server.server_close()
    finally:
        _cleanup_run(source_root)
        for name in os.listdir(RUNS_ROOT):
            if name.startswith("r3015out-"):
                rmtree(RUNS_ROOT / name, ignore_errors=True)


def test_d2_acceptance_lock_conflict_is_a_typed_cli_rejection_no_traceback():
    """I — Round 1 defect D2 regression: a genuinely held root-run lock.

    The lock conflict must reach the host as the §8 typed tuple with reason
    ``source_active`` and exit 2 -- never an uncaught traceback -- through the
    REAL CLI subprocess, and the refusal happens before any output-root work.
    """
    run_root, _frozen, checkpoint_id = _acceptance_source_run(with_sources=False)
    try:
        lock = cr.acquire_root_run_lock(run_root.name, RUNS_ROOT)
        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), _CursorOnlyStandIn)
            server.requests = []
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                new_run_id = f"r3015out-{os.urandom(4).hex()}"
                finished = _run_resume_cli(run_root.name, checkpoint_id, new_run_id, base_url)
                assert finished.returncode == 2, finished.stdout + finished.stderr
                assert "Traceback" not in finished.stderr
                prefix = "checkpoint failed: "
                assert finished.stderr.count(prefix) == 1, finished.stderr
                payload = json.loads(
                    finished.stderr.split(prefix, 1)[1].splitlines()[0]
                )
                assert payload["code"] == REASON_SOURCE_ACTIVE
                assert payload["retryable"] is True
                assert "resume lock" in payload["reason"]
                # Exact §8 field names on the real CLI channel (D3): six
                # fields, nothing internal leaks.
                assert set(payload) == {
                    "code",
                    "object_ref",
                    "phase",
                    "retryable",
                    "reason",
                    "next_action",
                }
                # Refused before any output-root or origin work.
                assert not (RUNS_ROOT / new_run_id).exists()
            finally:
                server.shutdown()
                server.server_close()
        finally:
            lock.release()
    finally:
        _cleanup_run(run_root)
        for name in os.listdir(RUNS_ROOT):
            if name.startswith("r3015out-"):
                rmtree(RUNS_ROOT / name, ignore_errors=True)
