"""R4.1 fixed Team projection; no Runner or external business execution."""

import json
from pathlib import Path
import pytest
from app.api.modeling_workbench import get_workbench_service
from app.services.modeling_workbench import (
    ModelingWorkbenchService,
    WorkbenchNotFound,
    content_digest,
    workspace_digests,
)


def write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value))
    return target


def run_fixture(root, project="p", run="running"):
    path = root / run
    write(
        path,
        "state.json",
        {
            "state": "RUNNING",
            "run_id": run,
            "platform_binding": {"project_id": project, "ontology_ids": ["o"]},
        },
    )
    return path


def public(root, digest="freeze", version=1):
    return write(
        root,
        f"competency-questions/public/public-projection-{version:04d}.json",
        {
            "schema_version": "r3-0-011-public-projection/v1",
            "batch_id": "b",
            "snapshot_digest": digest,
            "projection_digest": "projection",
            "questions": [
                {
                    "question_id": "Q",
                    "question": "What is accepted?",
                    "answer_points": ["Acceptance is not completion"],
                    "review_content_version": version,
                    "scope": {"kind": "panorama"},
                    "review_binding": {
                        "review_id": "r",
                        "review_content_version": version,
                        "decision_digest": "approved",
                    },
                    "hidden_answer": "PRIVATE-SENTINEL",
                }
            ],
            "credentials": "PRIVATE-SENTINEL",
        },
    )


def report(root, digest="freeze", path="acceptance-v3/reports/b/attempt-1/batch-report.json"):
    return write(
        root,
        path,
        {
            "schema_version": "r3-0-011-acceptance-batch-report/v1",
            "run_id": root.name,
            "batch_id": "b",
            "freeze_digest": digest,
            "report_digest": "report",
            "full_pass": False,
            "executed_question_ids": ["Q", "secret"],
            "unexecuted_question_ids": ["unexecuted-hidden"],
            "blind_status": {"blind_status": "non-blind", "exposed_question_ids": ["Q", "secret"]},
            "verdicts": [
                {
                    "question_id": "Q",
                    "verdict": "model-recall-insufficient",
                    "note": "Point 1 misunderstood; point 2 cause unknown",
                },
                {"question_id": "secret", "verdict": "pass", "note": "PRIVATE-SENTINEL"},
            ],
            "examiner_reports": [
                {"question_id": "Q", "question_content_version": 1, "answer": "public"},
                {"question_id": "secret", "answer": "PRIVATE-SENTINEL"},
            ],
            "summary_by_scope": {"panorama": {"pass": 1, "model-recall-insufficient": 1}},
        },
    )


def test_running_real_public_data_without_handoff_or_cleanup(tmp_path):
    run = run_fixture(tmp_path)
    state = json.loads((run / "state.json").read_text())
    # The actual Runner records null until terminal role results are present.
    state["terminal_results"] = None
    write(run, "state.json", state)
    public(run)
    write(
        run,
        "scenario-map/scenario-map.json",
        {
            "schema_version": "r4-0-007-scenario-map/v1",
            "scenario_id": "scenario",
            "slices": [
                {
                    "slice_id": "s",
                    "name": "Service",
                    "scope": "bounded",
                    "owner": "owner",
                    "status": "active",
                    "viewpoints": [
                        {
                            "viewpoint": "object",
                            "status": "modeled",
                            "note": "not applied",
                            "candidate_refs": [
                                {"candidate_id": "c", "revision": 4, "item_ids": ["i"]}
                            ],
                        }
                    ],
                }
            ],
            "shared_terms": [
                {"term": "Work", "definition_id": "d", "owner_slice": "s", "used_by_slices": ["s"]}
            ],
            "cross_slice_dependencies": [
                {
                    "from_slice": "s",
                    "to_slice": "t",
                    "direction": "depends",
                    "connection_points": ["d"],
                }
            ],
            "cross_slice_competency_questions": [
                {"question_id": "Q", "question": "Public", "spans_slices": ["s", "t"]}
            ],
            "explicit_unknowns": [
                {"topic": "Identity conversion", "needed_from": "owner", "status": "unresolved"}
            ],
            "adjustments": [
                {"change": "Version changed", "approved_by_coordinator": "coordinator"}
            ],
        },
    )
    reader = ModelingWorkbenchService(tmp_path)
    assert reader.list_runs("p")["current_run_id"] == "running"
    detail = reader.detail("p", "running")
    cq = detail["artifacts"]["competency_questions"][0]
    assert cq["data"]["questions"][0]["review_binding"]["decision_digest"] == "approved"
    assert cq["source"]["sha256"] and cq["scope"]["project_id"] == "p"
    assert "PRIVATE-SENTINEL" not in json.dumps(detail)
    scenario = detail["artifacts"]["scenario_map"][0]["data"]
    assert scenario["slices"][0]["viewpoints"][0]["status"] == "modeled"
    assert scenario["explicit_unknowns"][0]["topic"] == "Identity conversion"
    assert scenario["cross_slice_competency_questions"][0]["spans_slices"] == ["s", "t"]
    assert scenario["adjustments"][0]["change"] == "Version changed"
    lifecycle = next(a for a in detail["artifacts"]["host"] if a["kind"] == "run_lifecycle")
    assert lifecycle["availability"] == "available"
    assert lifecycle["data"]["terminal_results"] == {}


def test_history_nested_cleanup_conflict_not_guessed(tmp_path):
    run = tmp_path / "history"
    write(
        run,
        "state.json",
        {"state": "CLEANED", "cleanup": {"scope": {"project_id": "p", "ontology_id": "o"}}},
    )
    reader = ModelingWorkbenchService(tmp_path)
    assert reader.list_runs("p")["runs"][0]["run_id"] == "history"
    assert reader.list_runs("p")["current_run_id"] is None
    write(
        run,
        "acceptance-v3/production-handoff.json",
        {"scope_binding": {"project_id": "q", "ontology_ids": ["o"]}},
    )
    assert reader.list_runs("p")["runs"] == []
    with pytest.raises(WorkbenchNotFound):
        reader.detail("p", "history")
    write(tmp_path / "unbound", "state.json", {"state": "RUNNING"})
    assert reader.list_runs("p")["runs"] == []


def test_handoff_preserves_producer_write_records_and_pending_joint_checklist(tmp_path):
    run = run_fixture(tmp_path)
    handoff = {
        "schema_version": "r3-0-012-production-handoff/v1",
        "run_id": "running",
        "scope_binding": {"project_id": "p", "ontology_ids": ["o"]},
        "ready": False,
        "pending_writes": True,
        "write_phase": "quiescing",
        "applied_batches": [
            {
                "intent_ordinal": i,
                "batch_id": f"batch-{i}",
                "mode": "apply_atomic",
                "response_digest": f"digest-{i}",
                "private_response": {"answer": "PRIVATE-SENTINEL"},
            }
            for i in range(63)
        ],
        "not_applied": [{"source": "admission", "kind": "write", "ticket": 64}],
        "unknown_writes": [
            {"source": "staged-artifacts", "detail": "receipt unavailable"},
            {"source": "intent", "intent_ordinal": 65, "idempotency_key": "submission-65"},
            {"source": "admission", "kind": "write", "ticket": 66},
        ],
        "joint_checklist": {"state": "pending", "note": "joint review remains pending"},
    }
    source = write(run, "acceptance-v3/production-handoff.json", handoff)
    before = source.read_bytes()
    detail = ModelingWorkbenchService(tmp_path).detail("p", "running")
    artifact = detail["artifacts"]["handoff"][0]
    assert artifact["availability"] == "available"
    data = artifact["data"]
    assert len(data["applied_batches"]) == 63
    assert data["applied_batches"][62] == {
        "intent_ordinal": 62,
        "batch_id": "batch-62",
        "mode": "apply_atomic",
        "response_digest": "digest-62",
    }
    assert data["not_applied"] == handoff["not_applied"]
    assert data["unknown_writes"] == handoff["unknown_writes"]
    assert data["joint_checklist"] == handoff["joint_checklist"]
    assert data["ready"] is False and data["pending_writes"] is True
    assert "PRIVATE-SENTINEL" not in json.dumps(detail)
    assert source.read_bytes() == before
    handoff["unknown_writes"] = []
    write(run, "acceptance-v3/production-handoff.json", handoff)
    assert (
        ModelingWorkbenchService(tmp_path).detail("p", "running")["artifacts"]["handoff"][0][
            "data"
        ]["unknown_writes"]
        == []
    )


def test_feedback_preserves_typed_first_failure_without_private_evidence(tmp_path):
    run = run_fixture(tmp_path)
    public(run)
    source = write(
        run,
        "early-feedback/bound/feedback.json",
        {
            "freeze_digest": "freeze",
            "batch_id": "b",
            "first_failure": {
                "stage": "platform-examiner-session",
                "failure": {
                    "schema_version": "ExaminerBlocked/v1",
                    "status": "BLOCKED",
                    "blocked_layer": "runtime/infrastructure",
                    "blocked_reason": "child-exited",
                    "role": "platform",
                    "evidence": {
                        "reason_code": "child-exited",
                        "exit_code": 1,
                        "private_answer": "PRIVATE-SENTINEL",
                        "raw_log": "PRIVATE-SENTINEL",
                        "credentials": "PRIVATE-SENTINEL",
                    },
                },
            },
        },
    )
    before = source.read_bytes()
    write(
        run,
        "early-feedback/unbound/feedback.json",
        {
            "first_failure": {
                "stage": "checkpoint-binding",
                "failure": {
                    "status": "FAILED",
                    "reason": "public_feedback_unavailable: PRIVATE-SENTINEL",
                },
            }
        },
    )
    detail = ModelingWorkbenchService(tmp_path).detail("p", "running")
    feedback = {a["artifact_id"]: a["data"] for a in detail["artifacts"]["public_feedback"]}
    failure = feedback["early-feedback/bound/feedback.json"]["first_failure"]["failure"]
    assert failure["status"] == "BLOCKED"
    assert failure["blocked_layer"] == "runtime/infrastructure"
    assert failure["blocked_reason"] == "child-exited"
    assert failure["evidence"] == {"reason_code": "child-exited", "exit_code": 1}
    unbound = feedback["early-feedback/unbound/feedback.json"]["first_failure"]["failure"]
    assert unbound["status"] == "FAILED"
    assert unbound["reason"] == "public_feedback_unavailable"
    assert unbound["reason_detail_visibility"] == "withheld_without_public_binding"
    assert "PRIVATE-SENTINEL" not in json.dumps(detail)
    assert source.read_bytes() == before


def test_scenario_adjustment_review_preserves_exact_shared_definition_references(tmp_path):
    run = run_fixture(tmp_path)
    ref = {"candidate_id": "shared", "revision": 1, "item_id": "definition"}
    review = {
        "definition_ids": ["shared-definition"],
        "before_refs": [ref],
        "after_refs": [{**ref, "revision": 2}],
        "coverage": "incomplete",
        "coverage_note": "One consumer is not reviewed",
        "references": [{**ref, "slice_id": "s", "result": "unknown", "note": "needs review"}],
        "outcome": "pending",
        "reason": "Consumers must confirm the changed definition",
    }
    source = write(
        run,
        "scenario-map/scenario-map.json",
        {
            "adjustments": [
                {
                    "change": "definition revised",
                    "approved_by_coordinator": "coordinator",
                    "review": {**review, "private_diagnostic": "PRIVATE-SENTINEL"},
                },
                {"change": "slice renamed", "approved_by_coordinator": "coordinator"},
            ]
        },
    )
    before = source.read_bytes()
    detail = ModelingWorkbenchService(tmp_path).detail("p", "running")
    artifact = detail["artifacts"]["scenario_map"][0]
    assert artifact["availability"] == "available"
    adjustments = artifact["data"]["adjustments"]
    assert adjustments[0]["review"] == review
    assert "review" not in adjustments[1]
    assert "PRIVATE-SENTINEL" not in json.dumps(detail)
    assert source.read_bytes() == before


def test_read_only_privacy_denominator_paths_symlinks(tmp_path):
    run = run_fixture(tmp_path)
    public(run)
    report(run)
    raw = {p: p.read_bytes() for p in run.rglob("*.json")}
    reader = ModelingWorkbenchService(tmp_path)
    detail = reader.detail("p", "running")
    assert all(p.read_bytes() == content for p, content in raw.items())
    assert detail["artifacts"]["scenario_map"][0]["availability"] == "missing"
    data = detail["artifacts"]["reports"][0]["data"]
    assert data["denominator"] == 3 and data["public_count"] == 1
    assert data["hidden_summary"]["unexecuted_count"] == 1
    assert data["blind_status"]["exposed_question_ids"] == ["Q"]
    assert data["verdicts"][0]["approved_answer_points"]
    assert data["verdicts"][0]["structured_point_verdicts"] == "not_recorded"
    assert "PRIVATE-SENTINEL" not in json.dumps(detail)
    for value in ["../running", ".", "running/../running"]:
        with pytest.raises(WorkbenchNotFound):
            reader.detail("p", value)
    cq = next((run / "competency-questions/public").glob("*.json"))
    outside = tmp_path.parent / f"{tmp_path.name}-private.json"
    outside.write_text('{"question":"PRIVATE-SENTINEL"}')
    cq.unlink()
    cq.symlink_to(outside)
    assert (
        reader.detail("p", "running")["artifacts"]["competency_questions"][0]["availability"]
        == "error"
    )
    cq.unlink()
    cq.write_text("{")
    assert (
        reader.detail("p", "running")["artifacts"]["competency_questions"][0]["availability"]
        == "error"
    )


def test_reused_public_id_does_not_declassify_other_freeze(tmp_path):
    run = run_fixture(tmp_path)
    public(run, digest="old-public")
    path = report(run, digest="new-hidden")
    content = json.loads(path.read_text())
    content["verdicts"][0]["note"] = "NEW-HIDDEN-SENTINEL"
    content["examiner_reports"][0]["answer"] = "NEW-HIDDEN-SENTINEL"
    path.write_text(json.dumps(content))
    write(
        run,
        "early-feedback/x/feedback.json",
        {
            "freeze_digest": "new-hidden",
            "reports": [{"question_id": "Q", "answer": "NEW-HIDDEN-SENTINEL"}],
        },
    )
    detail = ModelingWorkbenchService(tmp_path).detail("p", "running")
    assert "NEW-HIDDEN-SENTINEL" not in json.dumps(detail)
    assert detail["artifacts"]["reports"][0]["data"]["public_projection_binding"] == "unknown"


def test_unapplied_candidate_script_and_mapping_kept(tmp_path):
    run = run_fixture(tmp_path)
    write(
        run,
        "stage3-neutral-graph/candidates/c-r2.json",
        {
            "candidate_id": "c",
            "revision": 2,
            "items": [
                {
                    "item_id": "i",
                    "item_kind": "entity",
                    "business_meaning": "rule",
                    "semantic_definition": {
                        "semantic_role": "rule",
                        "unknowns": ["inputs"],
                        "not_applicable": ["execution"],
                    },
                    "value": {
                        "entity_id": "e",
                        "values": {
                            "rule_definition": {
                                "kind": "judgment_constraint",
                                "script_source": "return None",
                                "script_language": "python",
                                "output_status": "unknown",
                                "password": "PRIVATE-SENTINEL",
                            },
                            "mapping_payload": {
                                "table_mapping_id": "tm",
                                "mapped_definition": {"definition_ref": "i"},
                                "mapping_definition": {
                                    "row_grain": "one work order",
                                    "field_meanings": {"state": "state meaning"},
                                },
                            },
                        },
                    },
                }
            ],
        },
    )
    item = ModelingWorkbenchService(tmp_path).detail("p", "running")["artifacts"]["candidates"][0][
        "data"
    ]["items"][0]
    assert item["value"]["values"]["rule_definition"]["script_source"] == "return None"
    assert (
        item["value"]["values"]["mapping_payload"]["mapping_definition"]["row_grain"]
        == "one work order"
    )
    assert item["semantic_definition"]["not_applicable"] == ["execution"]
    assert "PRIVATE-SENTINEL" not in json.dumps(item)


def test_verified_report_then_drift_deleted_missing_evidence_and_tamper(tmp_path, monkeypatch):
    run = run_fixture(tmp_path)
    public(run)
    write(run, "evidence/cq-freeze.jsonl", {"batch_id": "b", "snapshot_digest": "freeze"})
    context = {
        "state": "ready",
        "default_graph_set_id": "gs",
        "graph_set_status": "active",
        "source_signature": "source",
        "members": [{"role": "asserted_data", "revision": 2, "content_hash": "content"}],
    }
    ws, gs = workspace_digests(context)
    binding = {
        "batch_id": "b",
        "freeze_digest": "freeze",
        "ontologies": [
            {"project_id": "p", "ontology_id": "o", "workspace_state": ws, "graph_state": gs}
        ],
    }
    path = report(run)
    value = json.loads(path.read_text())
    value["sessions"] = {"batch_model_binding": binding, "post_batch_model_binding": binding}
    value["model_binding_digest"] = content_digest(binding)
    value["report_digest"] = content_digest(
        {k: v for k, v in value.items() if k != "report_digest"}
    )
    path.write_text(json.dumps(value))
    reader = ModelingWorkbenchService(tmp_path, workspace_reader=lambda *_: context)

    def state():
        return reader.detail("p", "running")["artifacts"]["reports"][0]["data"]["applicability"]

    assert state() == "verified_current"
    # Match the real CLI order: producer hashes core, then the CLI appends
    # sessions and full_pass without recomputing the report digest.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from modeling_team.competency_questions import build_batch_report

    produced = build_batch_report(
        run_id=run.name,
        batch_id="b",
        freeze_digest="freeze",
        model_binding_digest=content_digest(binding),
        hidden_questions=[{"question_id": "Q", "scope": {"kind": "panorama"}}],
        examiner_reports=[],
        verdicts=[],
        executed_question_ids=[],
        unexecuted_question_ids=["Q"],
    )
    produced["sessions"] = value["sessions"]
    produced["full_pass"] = False
    path.write_text(json.dumps(produced))
    projection = reader.detail("p", "running")["artifacts"]["reports"][0]["data"]
    assert projection["applicability"] == "verified_current"
    assert projection["report_digest_scope"] == "batch_report_core"
    assert projection["full_pass"] is False
    assert projection["full_pass_verification"] == "recorded_only_not_rescored"
    assert "sessions_and_full_pass_outside_report_digest" in projection["applicability_limitations"]
    produced["unexecuted_question_ids"] = []
    path.write_text(json.dumps(produced))
    assert state() == "stale"
    path.write_text(json.dumps(value))
    context["source_signature"] = "new-source"
    assert state() == "stale"

    def missing(*_):
        raise LookupError("deleted")

    reader.workspace_reader = missing
    assert state() == "stale"
    reader.workspace_reader = None
    assert state() == "binding_unknown"
    value["full_pass"] = True
    path.write_text(json.dumps(value))
    assert state() == "stale"


def test_rest_project_admin_and_run_scope(tmp_path, r008_client):
    app = r008_client["client"].app
    project = r008_client["ids"]["p1"]
    run_fixture(tmp_path, project=project)
    app.dependency_overrides[get_workbench_service] = lambda: ModelingWorkbenchService(tmp_path)
    client = r008_client["client"]
    path = f"/api/projects/{project}/workbench"
    for name in ("p1_read_key", "p1_model_key"):
        assert (
            client.get(path, headers={"Authorization": "Bearer " + r008_client[name]}).status_code
            == 403
        )
    h = {"Authorization": "Bearer " + r008_client["p1_admin_key"]}
    response = client.get(path, headers=h)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert client.get(path + "/runs/running", headers=h).status_code == 200
    assert (
        client.get(f"/api/projects/{r008_client['ids']['p2']}/workbench", headers=h).status_code
        == 403
    )
    assert client.get(path + "/runs/absent", headers=h).status_code == 404
