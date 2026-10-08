"""Early feedback through the actual CLI host path with existing CQ fixtures.

Developer seams use synthetic reports and retained reads, not a semantic PASS.
The independent tester separately drives the existing child/proxy/report sink.
"""
from __future__ import annotations

import json
from argparse import Namespace
from types import SimpleNamespace

import pytest

from modeling_team import __main__ as cli
from modeling_team.checkpoints import (
    CheckpointArtifactSpec, StagePackage, file_digest, save_checkpoint,
)
from modeling_team.contracts import repository_root
from modeling_team.staged_decisions import (
    build_submission_intent, staged_decision_artifact_paths, write_submission_intent,
)
from modeling_team.tests.test_r30015_checkpoints import _settled_apply_intent
from modeling_team.tests.test_r3011_acceptance import _question
from modeling_team.tests.test_r3012_partial_judging import _batch_adapter
from modeling_team.tests.test_r3012_platform_responses import _write_run_root
from modeling_team.tests.test_r3011_acceptance_cli import _ScriptedForwarder, _platform_context

ROOT = repository_root()


def seed_feedback_run(tmp_path):
    public = _question("cq-public", visibility="public")
    public["question"] = "公开链如何完成？"
    hidden = _question("cq-private")
    hidden["question"] = "PRIVATE HIDDEN MATERIAL"
    run_root, frozen = _write_run_root(tmp_path, [public, hidden])
    _settled_apply_intent(SimpleNamespace(run=SimpleNamespace(root=run_root)))
    freeze_source = "competency-questions/frozen/freeze-0001.json"
    paths = staged_decision_artifact_paths(run_root)
    stage_sources = [item.relative_to(run_root).as_posix()
                     for name in ("intents_dir", "receipts_dir") for item in paths[name].glob("*.json")]
    package = StagePackage(
        kind="materialization_progress", scope_refs={"freeze_id": "freeze-0001"},
        artifacts=[CheckpointArtifactSpec(source=source, owner="host", visible_to=("host",),
                                          host_private=True)
                   for source in [freeze_source, *stage_sources]],
        platform_bindings={"project_id": "project-1", "ontology_ids": ["ontology-1"],
                           "run_scope": {"mode": "existing", "project_id": "project-1",
                                         "ontology_id": "ontology-1"},
                           "model_profile_digest": "configuration-only-digest"},
        write_positions={"positions": [{"state": "applied", "ordinal": 1}],
                         "in_flight": [], "unknown": []},
        stage_facts={"bindings": [{"artifact": freeze_source, "digest": file_digest(run_root / freeze_source)}]},
    )
    result = save_checkpoint(run_root, package, source_run_id="feedback-production",
                             configuration={"task_parameters": {"modeling_checkpoints": True,
                                                                  "competency_question_acceptance": True}})
    (run_root / "evidence").mkdir(exist_ok=True)
    (run_root / "evidence/checkpoints.jsonl").write_text(json.dumps({
        "event": "checkpoint-" + result["status"],
        "checkpoint_id": result["checkpoint_id"], "manifest_digest": result["manifest_digest"]}) + "\n")
    (run_root / "phase.json").write_text('{"phase":"production"}')
    return run_root, result["checkpoint_id"], frozen


def execute_feedback(tmp_path, monkeypatch, *, callback=None, contexts=None, statuses=None,
                     question_ids=None, checkpoint_mutator=None, fail_read_after=None):
    run_root, checkpoint, frozen = seed_feedback_run(tmp_path)
    before = {path: path.read_bytes() for path in run_root.rglob("*") if path.is_file()}
    captured = {}

    def inspect(packet):
        captured["packet"] = packet.to_dict()["payload"]
        if callback:
            callback(run_root)

    adapter, state = _batch_adapter(on_examiner_packet=inspect,
                                    statuses=statuses)
    monkeypatch.setattr(cli, "CodexRuntimeAdapter", adapter)
    monkeypatch.setenv(cli._CQ_PLATFORM_READ_KEY_ENV, "SYNTHETIC-READ-KEY")
    if checkpoint_mutator:
        checkpoint_mutator(run_root, checkpoint)
    forwarder = _ScriptedForwarder(contexts or [_platform_context()], fail_after=fail_read_after)
    code = cli._run_public_feedback(Namespace(
        run_root=run_root, checkpoint_id=checkpoint, freeze_id="freeze-0001",
        question_id=question_ids or ["cq-public"], model_profile=None, session_timeout=2),
        ROOT, forwarder_factory=lambda **kwargs: forwarder)
    feedback_path = next((run_root / "early-feedback").glob("*/feedback.json"))
    record = json.loads(feedback_path.read_text())
    return code, record, run_root, before, captured, state, forwarder


def test_public_feedback_without_handoff_or_attempt_keeps_production_untouched(tmp_path, monkeypatch):
    code, record, run_root, before, captured, state, forwarder = execute_feedback(tmp_path, monkeypatch)
    assert code == 0
    assert record["status"] == "observed"
    assert record["formal_acceptance"] is False
    assert record["purpose"] == "public-nonblind-production-feedback"
    assert state["judge_payload"] is None
    assert record["reports"][0]["answer"]
    assert record["platform_read_responses"]["cq-public"][0]["artifact_path"]
    assert "PRIVATE HIDDEN MATERIAL" not in json.dumps(captured)
    assert "answer_points" not in json.dumps(captured)
    assert not (run_root / "acceptance-v3/reports").exists()
    assert not (run_root / "acceptance-v3/production-handoff.json").exists()
    assert {path: path.read_bytes() for path in before} == before
    assert forwarder.stopped
    assert record["pre_model_binding"] == record["post_model_binding"]
    assert record["model_profile_digest"] != record["pre_model_binding"]["ontologies"][0]["workspace_state"]["state_digest"]


@pytest.mark.parametrize("question_ids", [["cq-private"], ["missing"], ["cq-public", "cq-public"]])
def test_nonpublic_or_duplicate_selection_is_unavailable_without_runtime(tmp_path, monkeypatch, question_ids):
    code, record, _, _, captured, _, forwarder = execute_feedback(
        tmp_path, monkeypatch, question_ids=question_ids)
    assert code == 1
    assert record["status"] == "not-executed"
    assert not captured
    assert not forwarder.calls
    assert "PRIVATE HIDDEN MATERIAL" not in json.dumps(record)


@pytest.mark.parametrize("change", ["write", "model", "freeze"])
def test_feedback_changes_are_superseded_and_reports_preserved(tmp_path, monkeypatch, change):
    def mutate(run_root):
        if change == "write":
            _settled_apply_intent(SimpleNamespace(run=SimpleNamespace(root=run_root)), ordinal=2)
        if change == "freeze":
            path = run_root / "competency-questions/frozen/freeze-0001.json"
            path.write_text(path.read_text() + " ")
    contexts = [_platform_context(), _platform_context(model_revision=2)] if change == "model" else None
    code, record, _, _, _, state, _ = execute_feedback(
        tmp_path, monkeypatch, callback=mutate, contexts=contexts)
    assert code == 1
    assert record["status"] == "superseded"
    assert record["reports"]
    assert state["judge_payload"] is None


def test_unsettled_write_prevents_feedback_but_does_not_change_phase(tmp_path, monkeypatch):
    def pending(run_root, checkpoint):
        intent = build_submission_intent(2, idempotency_key="new-pending", client_batch_id="new-batch",
                                         session_id="session-1", mode="apply", commands=[], value_traces=[], l3_nodes=[])
        write_submission_intent(run_root, intent)
    code, record, run_root, _, captured, _, _ = execute_feedback(
        tmp_path, monkeypatch, checkpoint_mutator=pending)
    assert code == 1 and record["status"] == "not-executed"
    assert not captured
    assert json.loads((run_root / "phase.json").read_text())["phase"] == "production"
    assert "pending or unknown" in json.dumps(record)


def test_manifest_digest_must_match_published_receipt(tmp_path, monkeypatch):
    def changed_manifest(run_root, checkpoint):
        path = run_root / "checkpoints" / checkpoint / "manifest.json"
        data = json.loads(path.read_text())
        data["platform_bindings"]["project_id"] = "unauthorized-project"
        path.write_text(json.dumps(data))
    code, record, _, _, captured, _, _ = execute_feedback(
        tmp_path, monkeypatch, checkpoint_mutator=changed_manifest)
    assert code == 1 and record["status"] == "not-executed"
    assert "publication receipt" in json.dumps(record)
    assert not captured


def test_partial_examiner_report_remains_partial_not_formal_pass(tmp_path, monkeypatch):
    code, record, _, _, _, _, _ = execute_feedback(
        tmp_path, monkeypatch, statuses={"cq-public": "runtime-incomplete"})
    assert code == 1 and record["status"] == "partial"
    assert record["reports"][0]["status"] == "runtime-incomplete"
    assert record["examiner_first_failure"]["question_id"] == "cq-public"
    assert record["formal_acceptance"] is False


def test_post_observation_failure_retains_reports_receipts_and_cleanup(tmp_path, monkeypatch):
    code, record, _, _, _, state, forwarder = execute_feedback(
        tmp_path, monkeypatch, fail_read_after=1)
    assert code == 1 and record["status"] == "partial"
    assert record["first_failure"]["stage"] == "post-feedback-state"
    assert record["reports"][0]["question_id"] == "cq-public"
    assert record["platform_read_responses"]["cq-public"][0]["artifact_path"]
    assert record["cleanup"]["forwarder_stopped"] is True
    assert forwarder.stopped
    assert state["judge_payload"] is None


@pytest.mark.parametrize("failure", ["missing-package", "incomplete-package", "dry-run-only"])
def test_missing_checkpoint_or_dry_run_has_accurate_unexecuted_feedback(tmp_path, monkeypatch, failure):
    def unavailable(run_root, checkpoint):
        if failure == "missing-package":
            (run_root / "checkpoints" / checkpoint / "manifest.json").unlink()
        elif failure == "incomplete-package":
            artifact = next((run_root / "checkpoints" / checkpoint / "host-private" / "value-semantics/submission-receipts").glob("*.json"))
            artifact.unlink()
        else:
            _settled_apply_intent(SimpleNamespace(run=SimpleNamespace(root=run_root)), mode="dry_run")
    code, record, run_root, _, captured, _, forwarder = execute_feedback(
        tmp_path, monkeypatch, checkpoint_mutator=unavailable)
    assert code == 1 and record["status"] == "not-executed"
    assert record["first_failure"]["stage"] == "checkpoint-binding"
    assert not captured and not forwarder.started
    assert json.loads((run_root / "phase.json").read_text())["phase"] == "production"
