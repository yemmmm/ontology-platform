"""R3.0-011 v3 hidden-batch acceptance fixtures (M11, M12-M16, I6, R6, R7).

Mechanical packet, binding, report and read-only command checks only: no child
process, no platform call, and no semantic PASS is claimed anywhere here.
"""

from __future__ import annotations

import json
import shutil
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.acceptance_runtime import (
    AcceptanceBatchPacket,
    CQ_ACCEPTANCE_BRANCH_LEGACY,
    CQ_ACCEPTANCE_BRANCH_V3,
    acceptance_branch_for,
    build_acceptance_judge_packet,
    build_platform_batch_packet,
)
from modeling_team.__main__ import _run_cq_acceptance, main
from modeling_team.competency_questions import (
    CQ_BATCH_PACKET_SCHEMA,
    CQ_BATCH_REPORT_SCHEMA,
    CQ_EVIDENCE_BUNDLE_SCHEMA,
    CQ_FAILURE_LAYERS,
    CQ_FREEZE_SCHEMA,
    CQ_REQUIRED_FAILURE_LAYERS,
    CQ_VERDICT_STATES,
    acceptance_mode_evidence,
    batch_report_is_full_pass,
    blind_batch_label,
    build_batch_report,
    freeze_question_pool,
    model_binding_drift,
    read_exposure_evidence,
    validate_acceptance_verdict,
    validate_evidence_bundle,
    validate_examiner_report,
    validate_model_binding,
    content_digest,
)
from modeling_team.contracts import repository_root
from modeling_team.runtimes.codex import CodexRuntimeAdapter

REPO_ROOT = repository_root()
FREEZE_DIGEST = "sha256:" + "a" * 64


def _question(question_id: str, *, kind: str = "panorama", visibility: str = "hidden") -> dict:
    return {
        "question_id": question_id,
        "scope": {"kind": kind, "slice_ids": [] if kind == "panorama" else ["slice-1"]},
        "question": f"placeholder {question_id}?",
        "answer_points": ["point"],
        "evidence_refs": [{"source": "scenario-brief", "locator": "section 1"}],
        "unknown": [],
        "proposed_visibility": visibility,
        "content_version": 1,
    }


def _freeze(questions: list[dict] | None = None) -> dict:
    items = [_question("cq-1")] if questions is None else questions
    return freeze_question_pool(
        {
            "schema_version": CQ_FREEZE_SCHEMA,
            "batch_id": "batch-r3011",
            "material_digest": "material-r3011",
            "panorama_question_ids": [
                item["question_id"] for item in items if item["scope"]["kind"] == "panorama"
            ],
            "slice_question_ids": [
                item["question_id"] for item in items if item["scope"]["kind"] == "slice"
            ],
            "ordering": [item["question_id"] for item in items],
            "review_binding": {
                "review_id": "cq-review-0001",
                "review_content_version": 1,
                "decision_digest": "sha256:" + "0" * 64,
            },
            "questions": items,
        }
    )


def _binding(
    batch_id: str = "batch-r3011",
    ontology_id: str = "ontology-1",
    freeze_digest: str = FREEZE_DIGEST,
) -> dict:
    return {
        "schema_version": "r3-0-011-model-binding/v1",
        "batch_id": batch_id,
        "freeze_digest": freeze_digest,
        "bound_at": "2026-09-09T00:00:00+00:00",
        "ontologies": [
            {
                "project_id": "project-1",
                "ontology_id": ontology_id,
                "workspace_state": {"state_digest": "ws-1"},
                "graph_state": {"state_digest": "graph-1"},
                "authorized_read_tools": ["query_semantic_context"],
            }
        ],
    }


def _platform_packet(
    freeze: list[dict] | None = None,
    questions: list[dict] | None = None,
    **overrides,
) -> AcceptanceBatchPacket:
    frozen = _freeze(freeze)
    hidden = [dict(item) for item in frozen["questions"] if item["visibility"] == "hidden"]
    payload = {
        "run_id": "r3011-run",
        "batch_id": frozen["batch_id"],
        "freeze_digest": frozen["snapshot_digest"],
        "questions": [
            {
                "question_id": item["question_id"],
                "content_version": item["content_version"],
                "question": item["question"],
                "scope": dict(item["scope"]),
            }
            for item in hidden
        ],
        "authorized_scope": ["ontology-1"],
        "model_binding": _binding(frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
        "authorized_read_tools": ["query_semantic_context"],
        "report_schema": {"schema_version": CQ_BATCH_REPORT_SCHEMA},
        "session": {"mode": "single-continuous-batch", "ordered": True},
    }
    payload.update(overrides)
    if questions is not None:
        payload["questions"] = questions
    return AcceptanceBatchPacket.build("platform-examiner", payload)


# --- M13 / M11: explicit v3 dispatch and packet binding -----------------------


def test_m13_branch_dispatch_is_explicit_and_versioned():
    assert acceptance_branch_for(CQ_BATCH_PACKET_SCHEMA) == CQ_ACCEPTANCE_BRANCH_V3
    assert acceptance_branch_for("ExaminerRolePacket/v1") == CQ_ACCEPTANCE_BRANCH_LEGACY
    with pytest.raises(Exception):
        acceptance_branch_for("not-a-schema")


def test_m13_platform_packet_is_ordered_blind_and_single_session():
    packet = _platform_packet(freeze=[_question("cq-1"), _question("cq-2", kind="slice")])
    assert packet.schema_version == CQ_BATCH_PACKET_SCHEMA
    assert packet.role == "platform-examiner"
    assert [item["question_id"] for item in packet.to_dict()["payload"]["questions"]] == [
        "cq-1",
        "cq-2",
    ]
    assert dict(packet.payload["session"]) == {
        "mode": "single-continuous-batch",
        "ordered": True,
    }
    dumped = json.dumps(packet.to_dict())
    assert "answer_points" not in dumped and "point" not in dumped


def test_m13_platform_packet_rejects_answer_points_and_broad_tools():
    with pytest.raises(Exception) as blind:
        _platform_packet(
            questions=[
                {
                    "question_id": "cq-1",
                    "content_version": 1,
                    "question": "q",
                    "scope": {"kind": "panorama", "slice_ids": []},
                    "answer_points": ["point"],
                }
            ],
        )
    assert "blind" in str(blind.value) or "fields are invalid" in str(blind.value)
    with pytest.raises(Exception):
        _platform_packet(authorized_read_tools=["save_build_checkpoint"])


def test_m11_missing_or_unauthorized_model_binding_rejects_the_batch():
    binding = _binding()
    with pytest.raises(Exception):
        validate_model_binding(
            {**binding, "ontologies": []}, authorized_ontology_ids=["ontology-1"]
        )
    with pytest.raises(Exception) as unauthorized:
        validate_model_binding(binding, authorized_ontology_ids=["ontology-other"])
    assert unauthorized.value.data["reason_code"] == "cq_batch_scope_unauthorized"
    with pytest.raises(Exception) as missing:
        validate_model_binding(
            {
                **binding,
                "ontologies": [
                    {**binding["ontologies"][0], "workspace_state": {"state_digest": ""}}
                ],
            },
            authorized_ontology_ids=["ontology-1"],
        )
    assert missing.value.data["reason_code"] == "cq_model_binding_missing"


def test_m11_packet_scope_must_close_over_the_binding():
    binding = _binding("batch-r3011", "ontology-1")
    with pytest.raises(Exception) as mismatch:
        build_platform_batch_packet(
            run_id="r3011-run",
            batch_id="batch-r3011",
            freeze_digest=FREEZE_DIGEST,
            questions=[
                {
                    "question_id": "cq-1",
                    "content_version": 1,
                    "question": "q",
                    "scope": {"kind": "panorama", "slice_ids": []},
                }
            ],
            authorized_scope=["ontology-1", "ontology-2"],
            model_binding=binding,
            authorized_read_tools=["query_semantic_context"],
            report_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
            session={"mode": "single-continuous-batch", "ordered": True},
        )
    assert "scope" in str(mismatch.value)


def test_i6_only_authorized_ontologies_reach_the_packet():
    packet = _platform_packet()
    assert list(packet.payload["authorized_scope"]) == ["ontology-1"]
    assert dict(packet.payload["model_binding"])["ontologies"][0]["project_id"] == "project-1"


# --- M13/M14: the independent judge packet ------------------------------------


def _examiner_report(batch_id: str = "batch-r3011", **overrides) -> dict:
    payload = {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": batch_id,
        "question_id": "cq-1",
        "question_content_version": 1,
        "answer": "the modeled answer",
        "evidence_refs": ["resource-1"],
        "explicit_unknown": [],
        "status": "completed",
        "failure_layer": None,
        "reason": None,
    }
    payload.update(overrides)
    return payload


def test_m13_judge_packet_carries_freeze_answers_and_examiner_reports():
    frozen = _freeze()
    material = "approved material text"
    packet = build_acceptance_judge_packet(
        run_id="r3011-run",
        batch_id=frozen["batch_id"],
        freeze_digest=frozen["snapshot_digest"],
        questions=[
            {
                "question_id": item["question_id"],
                "content_version": item["content_version"],
                "question": item["question"],
                "answer_points": item["answer_points"],
                "evidence_refs": item["evidence_refs"],
                "unknown": item["unknown"],
                "scope": dict(item["scope"]),
            }
            for item in frozen["questions"]
        ],
        model_binding_digest="sha256:" + "b" * 64,
        evidence_bundle={
            "schema_version": CQ_EVIDENCE_BUNDLE_SCHEMA,
            "batch_id": frozen["batch_id"],
            "freeze_digest": frozen["snapshot_digest"],
            "entries": [
                {
                    "question_id": "cq-1",
                    "source": "scenario-brief",
                    "locator": "section 1",
                    "content": material,
                    "content_digest": content_digest(material),
                    "review_content_version": 1,
                }
            ],
        },
        examiner_reports=[_examiner_report()],
        verdict_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
    )
    assert packet.role == "acceptance"
    assert list(packet.payload["questions"][0]["answer_points"]) == ["point"]
    assert packet.payload["evidence_bundle"]["entries"][0]["content"] == material
    # The Examiner never sees this bundle.
    assert "evidence_bundle" not in json.dumps(_platform_packet().to_dict())


def test_m13_judge_packet_rejects_an_evidence_bundle_that_is_not_the_material():
    frozen = _freeze()
    material = "approved material text"
    with pytest.raises(Exception) as smuggled:
        build_acceptance_judge_packet(
            run_id="r3011-run",
            batch_id=frozen["batch_id"],
            freeze_digest=frozen["snapshot_digest"],
            questions=[
                {
                    "question_id": "cq-1",
                    "content_version": 1,
                    "question": "q",
                    "answer_points": ["point"],
                    "evidence_refs": [],
                    "unknown": [],
                    "scope": {"kind": "panorama", "slice_ids": []},
                }
            ],
            model_binding_digest="sha256:" + "b" * 64,
            evidence_bundle={
                "schema_version": CQ_EVIDENCE_BUNDLE_SCHEMA,
                "batch_id": frozen["batch_id"],
                "freeze_digest": frozen["snapshot_digest"],
                "entries": [
                    {
                        "question_id": "cq-1",
                        "source": "scenario-brief",
                        "locator": "section 1",
                        "content": "/some/path/only.md",
                        "content_digest": content_digest(material),
                        "review_content_version": 1,
                    }
                ],
            },
            examiner_reports=[],
            verdict_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
        )
    assert "content_digest does not match content" in str(smuggled.value)


def test_m14_conflicting_evidence_keeps_the_layer_empty():
    verdict = validate_acceptance_verdict(
        {
            "schema_version": CQ_BATCH_REPORT_SCHEMA,
            "batch_id": "batch-r3011",
            "question_id": "cq-1",
            "verdict": "question-answer-review",
            "failure_layer": None,
            "conflicting_evidence": ["material conflicts with the answer point"],
            "note": "pending user review",
        },
        question_ids=["cq-1"],
    )
    assert verdict["failure_layer"] is None
    with pytest.raises(Exception) as misattributed:
        validate_acceptance_verdict(
            {
                "schema_version": CQ_BATCH_REPORT_SCHEMA,
                "batch_id": "batch-r3011",
                "question_id": "cq-1",
                "verdict": "question-answer-review",
                "failure_layer": "modeling-quality",
                "conflicting_evidence": [],
                "note": "",
            },
            question_ids=["cq-1"],
        )
    assert "modeling-quality" in str(misattributed.value)


# --- R5/R6/R7: per-question continuation and the executed/unexecuted split ----


def test_r5_r6_examiner_states_and_failure_layers_are_mechanical():
    assert validate_examiner_report(
        _examiner_report(status="unanswered", reason="semantic miss"),
        question_ids=["cq-1"],
    )["status"] == "unanswered"
    runtime = validate_examiner_report(
        _examiner_report(
            status="runtime-incomplete",
            failure_layer="runtime/infrastructure",
            reason="read proxy unavailable",
        ),
        question_ids=["cq-1"],
    )
    assert runtime["failure_layer"] == "runtime/infrastructure"
    with pytest.raises(Exception):
        validate_examiner_report(_examiner_report(question_id="cq-9"), question_ids=["cq-1"])


def test_r7_reports_from_another_batch_never_merge_into_one_pass():
    report = build_batch_report(
        run_id="r3011-run",
        batch_id="batch-r3011",
        freeze_digest=FREEZE_DIGEST,
        model_binding_digest="sha256:" + "b" * 64,
        hidden_questions=[_question("cq-1")],
        examiner_reports=[_examiner_report(batch_id="batch-other")],
        verdicts=[],
        executed_question_ids=[],
        unexecuted_question_ids=["cq-1"],
    )
    assert report["examiner_reports"][0]["batch_id"] == "batch-other"
    assert report["unexecuted_question_ids"] == ["cq-1"]
    assert batch_report_is_full_pass(report) is False


# --- M16 + Round 4 (d): coverage gaps are a report field ----------------------


def test_m16_empty_hidden_set_is_a_reported_coverage_gap_and_never_a_pass():
    report = build_batch_report(
        run_id="r3011-run",
        batch_id="batch-empty",
        freeze_digest=FREEZE_DIGEST,
        model_binding_digest="sha256:" + "b" * 64,
        hidden_questions=[],
        examiner_reports=[],
        verdicts=[],
        executed_question_ids=[],
        unexecuted_question_ids=[],
    )
    assert report["coverage_gaps"]["empty_hidden_set"] is True
    assert batch_report_is_full_pass(report) is False


def test_m16_slice_without_a_hidden_question_is_a_reported_coverage_gap():
    report = build_batch_report(
        run_id="r3011-run",
        batch_id="batch-r3011",
        freeze_digest=FREEZE_DIGEST,
        model_binding_digest="sha256:" + "b" * 64,
        hidden_questions=[],
        examiner_reports=[],
        verdicts=[],
        executed_question_ids=[],
        unexecuted_question_ids=[],
        slices=["slice-1"],
    )
    assert report["coverage_gaps"]["slices_without_hidden_question"] == ["slice-1"]
    assert batch_report_is_full_pass(report) is False


def test_m15_model_drift_marks_the_batch_incomplete():
    before = _binding()
    after = _binding()
    after["ontologies"][0]["workspace_state"]["state_digest"] = "ws-2"
    drift = model_binding_drift(before, after)
    assert drift
    report = build_batch_report(
        run_id="r3011-run",
        batch_id="batch-r3011",
        freeze_digest=FREEZE_DIGEST,
        model_binding_digest="sha256:" + "b" * 64,
        hidden_questions=[],
        examiner_reports=[],
        verdicts=[],
        executed_question_ids=[],
        unexecuted_question_ids=[],
        model_state_drift=drift,
    )
    assert report["coverage_gaps"]["model_state_drift"]
    assert batch_report_is_full_pass(report) is False


# --- Round 4 (e): read-only attribution ---------------------------------------


def test_m12_acceptance_llm_calls_are_attributed_read_only():
    evidence = acceptance_mode_evidence(
        batch_id="batch-r3011", freeze_digest=FREEZE_DIGEST
    )
    assert evidence["acceptance_mode"] == "read-only-acceptance"
    assert evidence["start_ledger_write"] is False
    assert evidence["consumes_semantic_start"] is False


# --- M12: the cq-acceptance command ------------------------------------------


def _write_run_root(tmp_path: Path, *, with_contract: bool = True) -> Path:
    run_root = tmp_path / "run"
    frozen = _freeze()
    (run_root / "competency-questions" / "frozen").mkdir(parents=True)
    (run_root / "acceptance-v3").mkdir(parents=True)
    (run_root / "competency-questions" / "frozen" / "freeze-0001.json").write_text(
        json.dumps(frozen), encoding="utf-8"
    )
    if with_contract:
        (run_root / "acceptance-v3" / "run-contract.json").write_text(
            json.dumps(
                {
                    "schema_version": "r3-0-011-run-contract/v1",
                    "run_id": "r3011-run",
                    "profile_id": "r3-0-011-competency-question",
                    "task_id": "r3-0-008b-staged-real",
                    "parameters": {"competency_question_acceptance": True},
                }
            ),
            encoding="utf-8",
        )
    binding = _binding(frozen["batch_id"])
    binding["freeze_digest"] = frozen["snapshot_digest"]
    post = json.loads(json.dumps(binding))
    handoff = {
        "authorized_ontology_ids": ["ontology-1"],
        "production_delivery": {"ready": True, "pending_writes": False},
        "model_binding": binding,
        "post_batch_model_binding": post,
    }
    (tmp_path / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
    return run_root


def _command(tmp_path: Path, run_root: Path) -> int:
    return _run_cq_acceptance(
        Namespace(
            run_root=run_root,
            freeze_id="freeze-0001",
            model_handoff=tmp_path / "handoff.json",
            model_profile=None,
            session_timeout=300.0,
            # These tests pin the pre-authorization evidence shape explicitly.
            unexecuted_report=True,
        ),
        REPO_ROOT,
    )


def test_m12_cq_acceptance_writes_a_host_only_read_only_report(tmp_path, capsys):
    run_root = _write_run_root(tmp_path)
    assert _command(tmp_path, run_root) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["acceptance_mode"] == "read-only-acceptance"
    assert payload["start_ledger_write"] is False
    assert payload["consumes_semantic_start"] is False
    report_dir = run_root / "acceptance-v3" / "reports" / payload["batch_id"]
    report = json.loads((report_dir / "batch-report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == CQ_BATCH_REPORT_SCHEMA
    assert report["unexecuted_question_ids"] == ["cq-1"]
    assert report["full_pass"] is False
    attribution = json.loads((report_dir / "attribution.json").read_text(encoding="utf-8"))
    assert attribution["acceptance_mode"] == "read-only-acceptance"
    assert report_dir.stat().st_mode & 0o777 in {0o700, 0o750}


def test_m12_pending_checklist_does_not_block_but_missing_contract_does(tmp_path, capsys):
    run_root = _write_run_root(tmp_path)
    # The 008B joint checklist stays pending: no checklist file exists and the
    # command still succeeds.
    assert _command(tmp_path, run_root) == 0
    capsys.readouterr()
    legacy = tmp_path / "legacy-run"
    legacy.mkdir()
    assert _command(tmp_path, legacy) == 2


def test_m12_cq_acceptance_rejects_an_unready_production_delivery(tmp_path):
    run_root = _write_run_root(tmp_path)
    handoff = json.loads((tmp_path / "handoff.json").read_text(encoding="utf-8"))
    handoff["production_delivery"] = {"ready": False, "pending_writes": True}
    (tmp_path / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
    assert _command(tmp_path, run_root) == 2


def test_m15_cq_acceptance_records_drift_and_never_reuses_a_pass(tmp_path, capsys):
    run_root = _write_run_root(tmp_path)
    handoff = json.loads((tmp_path / "handoff.json").read_text(encoding="utf-8"))
    handoff["post_batch_model_binding"]["ontologies"][0]["graph_state"]["state_digest"] = "drift"
    (tmp_path / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
    assert _command(tmp_path, run_root) == 0
    batch_id = json.loads(capsys.readouterr().out)["batch_id"]
    report = json.loads(
        (run_root / "acceptance-v3" / "reports" / batch_id / "batch-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["coverage_gaps"]["model_state_drift"]
    assert report["full_pass"] is False


def test_m12_cq_acceptance_never_touches_the_start_ledger(tmp_path):
    run_root = _write_run_root(tmp_path)
    run_root.parent.mkdir(parents=True, exist_ok=True)
    before = sorted(path.name for path in run_root.parent.iterdir())
    assert _command(tmp_path, run_root) == 0
    after = sorted(path.name for path in run_root.parent.iterdir())
    assert before == after  # no ledger entry, no new run root, no semantic start
    assert not (run_root / "semantic-start.jsonl").exists()


def test_m12_a_tampered_freeze_file_is_rejected(tmp_path):
    run_root = _write_run_root(tmp_path)
    freeze_path = run_root / "competency-questions" / "frozen" / "freeze-0001.json"
    edited = json.loads(freeze_path.read_text(encoding="utf-8"))
    edited["questions"][0]["question"] = "a different question?"
    freeze_path.write_text(json.dumps(edited), encoding="utf-8")
    assert _command(tmp_path, run_root) == 2


def test_m12_cli_dispatch_reaches_the_command_without_a_runner(tmp_path, capsys, monkeypatch):
    """The cq-acceptance branch never builds a TeamRunner or a run root."""

    run_root = _write_run_root(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "modeling_team",
            "cq-acceptance",
            "--run-root",
            str(run_root),
            "--freeze-id",
            "freeze-0001",
            "--model-handoff",
            str(tmp_path / "handoff.json"),
            "--unexecuted-report",
        ],
    )
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["acceptance_mode"] == "read-only-acceptance"
    legacy = tmp_path / "legacy-run"
    legacy.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "modeling_team",
            "cq-acceptance",
            "--run-root",
            str(legacy),
            "--freeze-id",
            "freeze-0001",
            "--model-handoff",
            str(tmp_path / "handoff.json"),
        ],
    )
    assert main() == 2


# --- M13: versioned v3 role instructions -------------------------------------


def test_m13_v3_role_instructions_are_versioned_and_legacy_prompts_survive():
    for role, marker in (
        ("platform-examiner", "one\ncontinuous session"),
        ("acceptance", "verdict"),
    ):
        package = REPO_ROOT / "modeling_team" / "agent-packages" / role
        v3 = package / "instructions-v3.md"
        assert v3.is_file(), v3
        text = v3.read_text(encoding="utf-8")
        assert "R3.0-011" in text
        assert marker in text
        assert (package / "instructions.md").is_file()


# --- M13: the adapter seam keeps the v3 and legacy branches separate ----------


def _legacy_packet():
    from modeling_team.acceptance_runtime import (
        PLATFORM_PROXY_READ_TOOLS,
        build_platform_examiner_packet,
        examiner_proxy_schemas,
    )

    return build_platform_examiner_packet(
        question="Which output is consumed?",
        ordinal=1,
        count=1,
        ticket_binding={"ticket_digest": "a" * 64},
        model_state={"workspace_version": "w1", "state_digest": "b" * 64},
        platform_read_scope={
            "project_id": "project-1",
            "ontology_id": "ontology-1",
            "graph_set_id": "graph-1",
        },
        proxy_capability={"capability_id": "proxy-1"},
        allowed_read_tools=list(PLATFORM_PROXY_READ_TOOLS),
        request_schema=examiner_proxy_schemas(PLATFORM_PROXY_READ_TOOLS),
        report_schema={"type": "platform-report"},
    )


def test_m13_v3_child_seam_rejects_a_legacy_packet():
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT, use_bwrap=False)
    with pytest.raises(Exception):
        adapter.launch_v3_acceptance_child(
            _legacy_packet(),  # type: ignore[arg-type]
            role_instructions="irrelevant",
            reports=[],
        )


def test_m13_v3_child_seam_dispatches_one_session_per_batch(tmp_path):
    captured: dict = {}
    private_roots: list[str] = []

    def factory(spec):
        captured.update(spec)
        private_roots.append(spec["private_root"])
        return SimpleNamespace(spec=spec, destroyed=False)

    adapter = CodexRuntimeAdapter(
        repository_root=REPO_ROOT, use_bwrap=False, acceptance_child_factory=factory
    )
    packet = _platform_packet()
    reports: list = []
    adapter.launch_v3_acceptance_child(
        packet,
        role_instructions="submit one v3 report per question",
        reports=reports,
        read_key="read-key",
        platform_forwarder=lambda tool, arguments, key: {},
        graph_set_ids={"ontology-1": "graph-set-1"},
    )
    try:
        assert captured["v3_batch"] is True
        assert captured["v3_role"] == "platform-examiner"
        assert captured["session_id"].startswith("r3011-")
        assert captured["kind"] == "platform"
        assert captured["allowed_read_tools"] == ["query_semantic_context"]
        assert captured["v3_graph_set_ids"] == {"ontology-1": "graph-set-1"}
        assert captured["report_submit_payload"] == reports.append
        first_turn = captured["first_turn_input"][0]["text"]
        assert "One continuous session per batch" in first_turn
        assert "PACKET_DIGEST=" in first_turn
        # The blind packet really is what reached the child input file.
        private_input = json.loads(Path(captured["private_input"]).read_text(encoding="utf-8"))
        assert "answer_points" not in json.dumps(private_input)
        assert private_input["batch_id"] == packet.batch_id
        # A platform session without a read key and forwarder is blocked.
        with pytest.raises(Exception):
            adapter.launch_v3_acceptance_child(
                packet,
                role_instructions="submit one v3 report per question",
                reports=reports,
                graph_set_ids={"ontology-1": "graph-set-1"},
            )
        # Missing or incomplete graph sets are rejected before any private root
        # is allocated, so a rejected launch leaves nothing behind.
        before = set(tmp_path.iterdir()) | set(Path("/tmp").glob("r3011-acceptance-*"))
        with pytest.raises(Exception):
            adapter.launch_v3_acceptance_child(
                packet,
                role_instructions="submit one v3 report per question",
                reports=reports,
                read_key="read-key",
                platform_forwarder=lambda tool, arguments, key: {},
            )
        with pytest.raises(Exception):
            adapter.launch_v3_acceptance_child(
                packet,
                role_instructions="submit one v3 report per question",
                reports=reports,
                read_key="read-key",
                platform_forwarder=lambda tool, arguments, key: {},
                graph_set_ids={"ontology-1": ""},
            )
        after = set(tmp_path.iterdir()) | set(Path("/tmp").glob("r3011-acceptance-*"))
        assert before == after
    finally:
        for root in private_roots:
            shutil.rmtree(root, ignore_errors=True)


# --- Round 1 F3: the packet binding cannot point at another batch -------------


def test_f3_packet_rejects_a_binding_bound_to_another_batch_or_freeze():
    frozen = _freeze()
    snapshot_digest = frozen["snapshot_digest"]
    with pytest.raises(Exception) as other_batch:
        _platform_packet(
            model_binding=_binding("batch-other", freeze_digest=snapshot_digest)
        )
    assert "does not match this batch" in str(other_batch.value)
    with pytest.raises(Exception) as other_freeze:
        _platform_packet(model_binding=_binding(frozen["batch_id"]))
    assert "does not match this batch" in str(other_freeze.value)
    # The consistent binding still builds, so the rejection is about the pair.
    packet = _platform_packet(
        model_binding=_binding(frozen["batch_id"], freeze_digest=snapshot_digest)
    )
    assert packet.batch_id == frozen["batch_id"]


# --- Round 1 F4: design §4.2 failure-layer obligations ------------------------


def test_f4_recall_and_runtime_verdicts_must_name_their_failure_layer():
    assert CQ_REQUIRED_FAILURE_LAYERS == {
        "model-recall-insufficient": ("modeling-quality",),
        "platform-runtime-incomplete": ("runtime/infrastructure", "platform-contract", "collaboration/routing"),
    }

    def _verdict(**overrides) -> dict:
        payload = {
            "schema_version": CQ_BATCH_REPORT_SCHEMA,
            "batch_id": "batch-r3011",
            "question_id": "cq-1",
            "verdict": "pass",
            "failure_layer": None,
            "conflicting_evidence": [],
            "note": "",
        }
        payload.update(overrides)
        return payload

    assert (
        validate_acceptance_verdict(_verdict(), question_ids=["cq-1"])["failure_layer"]
        is None
    )
    assert (
        validate_acceptance_verdict(
            _verdict(verdict="question-answer-review"), question_ids=["cq-1"]
        )["failure_layer"]
        is None
    )
    attributed = validate_acceptance_verdict(
        _verdict(verdict="model-recall-insufficient", failure_layer="modeling-quality"),
        question_ids=["cq-1"],
    )
    assert attributed["failure_layer"] == "modeling-quality"
    assert validate_acceptance_verdict(
        _verdict(
            verdict="platform-runtime-incomplete", failure_layer="runtime/infrastructure"
        ),
        question_ids=["cq-1"],
    )["failure_layer"] == "runtime/infrastructure"
    for state, layer in (
        ("model-recall-insufficient", None),
        ("model-recall-insufficient", "platform-contract"),
        ("model-recall-insufficient", "collaboration/routing"),
        ("platform-runtime-incomplete", None),
        ("platform-runtime-incomplete", "modeling-quality"),
    ):
        with pytest.raises(Exception) as unattributed:
            validate_acceptance_verdict(
                _verdict(verdict=state, failure_layer=layer), question_ids=["cq-1"]
            )
        assert "failure_layer" in str(unattributed.value)


def test_i2_an_empty_evidence_bundle_is_rejected_and_can_never_pass():
    with pytest.raises(Exception) as empty:
        validate_evidence_bundle(
            {
                "schema_version": CQ_EVIDENCE_BUNDLE_SCHEMA,
                "batch_id": "batch-r3011",
                "freeze_digest": FREEZE_DIGEST,
                "entries": [],
            }
        )
    assert "entries is empty" in str(empty.value)


# --- Round 2 R4: the report always carries an explicit blind/non-blind label --


def test_r4_a_pool_without_recorded_exposure_is_labeled_blind(tmp_path, capsys):
    run_root = _write_run_root(tmp_path)
    assert not (run_root / "evidence" / "cq-exposure.jsonl").exists()
    assert _command(tmp_path, run_root) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["blind_status"] == "blind"
    report = json.loads(
        (run_root / "acceptance-v3" / "reports" / payload["batch_id"] / "batch-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["blind_status"] == {
        "blind_status": "blind",
        "exposed_question_ids": [],
        # The digest of the empty evidence list: it proves the command did read
        # the run root's cq-exposure evidence and found no recorded exposure.
        "exposure_evidence_digest": content_digest([]),
        "exposure_record_count": 0,
    }
    assert batch_report_is_full_pass(report) is False


def test_r4_only_exposure_inside_the_batch_scope_makes_it_non_blind(tmp_path):
    evidence_file = tmp_path / "cq-exposure.jsonl"
    evidence_file.write_text(
        json.dumps(
            {
                "recorded_at": "2026-09-09T00:00:00+00:00",
                "event": "question-exposed-to-production",
                "question_ids": ["cq-99"],
                "roles": ["coordinator"],
                "reason_code": "permanently_public",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evidence = read_exposure_evidence(evidence_file)
    assert evidence["exposure"] == {"cq-99": ["coordinator"]}
    assert evidence["record_count"] == 1 and evidence["digest"].startswith("sha256:")
    assert blind_batch_label(question_ids=["cq-1"], evidence=evidence)["blind_status"] == "blind"
    labeled = blind_batch_label(question_ids=["cq-1", "cq-99"], evidence=evidence)
    assert labeled == {
        "blind_status": "non-blind-regression",
        "exposed_question_ids": ["cq-99"],
        "exposure_evidence_digest": evidence["digest"],
        "exposure_record_count": 1,
    }
    # Missing evidence is empty provenance, never an error; broken evidence is
    # rejected instead of guessed.
    assert read_exposure_evidence(tmp_path / "absent.jsonl") == {
        "exposure": {},
        "digest": content_digest([]),
        "record_count": 0,
    }
    evidence_file.write_text("not json\n", encoding="utf-8")
    with pytest.raises(Exception) as broken:
        read_exposure_evidence(evidence_file)
    assert "cq_exposure_evidence" in str(broken.value)


# --- Round 2 informational: a pass never carries a failure layer --------------


def test_i2_a_pass_verdict_must_keep_the_failure_layer_empty():
    with pytest.raises(Exception) as attributed_pass:
        validate_acceptance_verdict(
            {
                "schema_version": CQ_BATCH_REPORT_SCHEMA,
                "batch_id": "batch-r3011",
                "question_id": "cq-1",
                "verdict": "pass",
                "failure_layer": "modeling-quality",
                "conflicting_evidence": [],
                "note": "",
            },
            question_ids=["cq-1"],
        )
    assert "must keep failure_layer empty" in str(attributed_pass.value)
    for layer in CQ_FAILURE_LAYERS:
        with pytest.raises(Exception):
            validate_acceptance_verdict(
                {
                    "schema_version": CQ_BATCH_REPORT_SCHEMA,
                    "batch_id": "batch-r3011",
                    "question_id": "cq-1",
                    "verdict": "pass",
                    "failure_layer": layer,
                    "conflicting_evidence": [],
                    "note": "",
                },
                question_ids=["cq-1"],
            )


def _judge_verdict(verdict: str, failure_layer: str | None) -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": "batch-r3011",
        "question_id": "cq-1",
        "verdict": verdict,
        "failure_layer": failure_layer,
        "conflicting_evidence": [],
        "note": "judged cq-1 against the frozen material",
    }


def test_the_v3_sink_repeats_only_the_canonical_verdict_states():
    """The standalone bridge cannot import the host package, so its copy of the
    verdict enum must stay an exact projection: a legal non-pass verdict is
    accepted and the legacy bare ``fail`` is rejected (product finding P6)."""
    from modeling_team import report_sink_mcp

    assert report_sink_mcp.CQ_VERDICT_STATES == tuple(CQ_VERDICT_STATES)
    advertised = report_sink_mcp._v3_batch_report_schema(platform=False)
    assert advertised["properties"]["verdict"]["enum"] == list(CQ_VERDICT_STATES)
    accepted = report_sink_mcp._validate_batch_payload(
        _judge_verdict("model-recall-insufficient", "modeling-quality"),
        kind="acceptance",
        batch_id="batch-r3011",
        question_ids=["cq-1"],
        role="acceptance-judge",
    )
    assert accepted["verdict"] == "model-recall-insufficient"
    accepted = report_sink_mcp._validate_batch_payload(
        _judge_verdict("platform-runtime-incomplete", "runtime/infrastructure"),
        kind="acceptance",
        batch_id="batch-r3011",
        question_ids=["cq-1"],
        role="acceptance-judge",
    )
    assert accepted["verdict"] == "platform-runtime-incomplete"
    for verdict in ("fail", "model-recall-insufficient-fail"):
        with pytest.raises(ValueError, match="verdict is invalid"):
            report_sink_mcp._validate_batch_payload(
                _judge_verdict(verdict, "modeling-quality"),
                kind="acceptance",
                batch_id="batch-r3011",
                question_ids=["cq-1"],
                role="acceptance-judge",
            )
