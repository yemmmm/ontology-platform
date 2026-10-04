"""R3.0-012 §4.3 partial-batch judging and attempt-unique reports.

Covers the T3 rows the §4.3 split owns: a partial batch is judged per question
instead of all-or-nothing (T3-2/T3-11/T3-13), a ``question-answer-review``
verdict blocks the whole-batch PASS without a layer misattribution (T3-4, with
the T3-16 ``sql-result-outside-cq-scope`` note contract), one question's
unresolved frozen evidence never drags the others, and the verified production
handoff directs the CLI into a unique attempt directory whose published report
is never overwritten (T3-12/T3-18).

The CLI tests drive the real ``_run_cq_acceptance`` executed path with the
injectable forwarder factory and a bounded per-question adapter double (the
R3.0-011 convention): the examiner half uses the real host seams -- the
persistence callback writes the retained artifact, the observables out-param
receives the sanitized receipt -- without starting a child.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from modeling_team.__main__ import (
    _CQ_JUDGE_ROLE_INSTRUCTIONS,
    _cq_consume_production_handoff,
    _run_cq_acceptance,
)
from modeling_team.contracts import TeamConfigurationError
from modeling_team.acceptance_runtime import (
    PLATFORM_READ_ARTIFACT_SCHEMA,
    V3ProxyCallReceipt,
    canonical_read_digest,
)
from modeling_team.competency_questions import CQ_BATCH_REPORT_SCHEMA
from modeling_team.tests.test_r3011_acceptance import REPO_ROOT, _freeze, _question
from modeling_team.tests.test_r3012_platform_responses import (
    _DualForwarder,
    _Factory,
    _QUERY_REQUEST,
    _RETAINED_QUERY_RESULT,
    _passing_verdict,
    _platform_context,
    _read_report,
    _ref,
    _report,
    _run_cli,
    _write_handoff,
    _write_run_root,
)

_EMPTY_QUERY_RESULT = {"ok": True, "matches": [], "matches_page": {"truncated": False}}


def _review_verdict(question_id: str, note: str = "sql-result-outside-cq-scope") -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": "batch-r3011",
        "question_id": question_id,
        "verdict": "question-answer-review",
        "failure_layer": None,
        "conflicting_evidence": [],
        "note": note,
    }


def _batch_adapter(
    *,
    result: dict | None = None,
    statuses=None,
    omitted=(),
    judge_verdicts=None,
    on_examiner_packet=None,
):
    """Examiner/Judge double with per-question control over the batch.

    The examiner half retains one real response artifact through the host
    persistence callback and emits the requested per-question status: a
    question named in ``omitted`` never reports, and ``runtime-incomplete``
    carries its failure layer as a real executed service failure.  The judge
    half records its packet payload and answers per-question verdicts.
    ``on_examiner_packet`` runs inside the examiner session (after this
    command's admission checks), the injection point a concurrent acceptance
    process occupies in the T3-18 interleaving.
    """

    retained = dict(result or _RETAINED_QUERY_RESULT)
    state: dict = {"judge_payload": None}

    class _ScenarioAdapter:
        def __init__(self, repository_root=None) -> None:
            self.repository_root = repository_root

        def bind_acceptance_model_profile(self, profile) -> None:
            return None

        def run_v3_acceptance_child(self, packet, *, role_instructions, reports, **kwargs):
            teardown = kwargs.get("teardown")
            if isinstance(teardown, dict):
                teardown.update(
                    {
                        "child_stopped": True,
                        "child_destroyed": True,
                        "report_sink_stopped": True,
                        "proxy_stopped": True,
                        "private_root_removed": True,
                        "socket_root_removed": True,
                    }
                )
            if kwargs.get("platform_forwarder") is None:
                state["judge_payload"] = packet.to_dict()["payload"]
                questions = state["judge_payload"]["questions"]
                if judge_verdicts is None:
                    return [_passing_verdict(str(item["question_id"])) for item in questions]
                return [dict(judge_verdicts[str(item["question_id"])]) for item in questions]
            persistence = kwargs["response_persistence"]
            observables = kwargs["examiner_observables"]
            if on_examiner_packet is not None:
                on_examiner_packet(packet)
            tool = "query_semantic_context"
            request = dict(_QUERY_REQUEST)
            artifact_path = f"acceptance/{packet.batch_id}/platform-read/{'a' * 64}/0.json"
            persistence(
                artifact_path,
                {
                    "schema_version": PLATFORM_READ_ARTIFACT_SCHEMA,
                    "tool": tool,
                    "request": request,
                    "result": retained,
                },
            )
            receipt = V3ProxyCallReceipt(
                ordinal=0,
                project_id="project-1",
                ontology_id="ontology-1",
                graph_set_id="graph-set-1",
                ticket_digest="b" * 64,
                model_state_digest="c" * 64,
                tool=tool,
                request_digest=canonical_read_digest({"tool": tool, "arguments": request}),
                response_digest=canonical_read_digest(retained),
                artifact_path=artifact_path,
                page={
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            )
            observables["receipts"] = [receipt]
            observables["persistence_failures"] = 0
            for question in packet.to_dict()["payload"]["questions"]:
                question_id = str(question["question_id"])
                if question_id in omitted:
                    continue
                status = (statuses or {}).get(question_id, "completed")
                report = _report(question_id, [_ref(receipt)])
                if status == "runtime-incomplete":
                    report["status"] = "runtime-incomplete"
                    report["failure_layer"] = "runtime/infrastructure"
                    report["reason"] = "platform read unavailable"
                elif status != "completed":
                    report["status"] = status
                reports.append(report)
            return [dict(report) for report in reports]

    return _ScenarioAdapter, state


# --- T3-2/T3-11: a partial batch is judged per question ------------------------


def test_a_partial_batch_judges_only_its_judgeable_questions(tmp_path, capsys, monkeypatch):
    run_root, frozen = _write_run_root(
        tmp_path, [_question("cq-1"), _question("cq-2"), _question("cq-3"), _question("cq-4")]
    )
    handoff = _write_handoff(tmp_path, frozen)
    forwarder = _DualForwarder(
        _platform_context(), [_RETAINED_QUERY_RESULT, _RETAINED_QUERY_RESULT]
    )
    adapter_class, state = _batch_adapter(
        statuses={"cq-3": "runtime-incomplete"}, omitted=("cq-4",)
    )
    code = _run_cli(tmp_path, run_root, handoff, forwarder, adapter_class, monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    report = _read_report(run_root, payload["batch_id"])

    # The judge packet carries only the judgeable questions -- no empty answer
    # or unknown ever masks an unexecuted question as judged (T3-11).
    judged_questions = [
        str(item["question_id"]) for item in state["judge_payload"]["questions"]
    ]
    assert judged_questions == ["cq-1", "cq-2"]
    assert [
        str(item["question_id"]) for item in state["judge_payload"]["examiner_reports"]
    ] == ["cq-1", "cq-2"]
    assert sorted(state["judge_payload"]["platform_read_responses"]) == ["cq-1", "cq-2"]

    # Verdicts exist for the judged questions only; the whole-batch PASS is
    # blocked by verdict coverage, not by discarding the executed answers.
    assert [item["question_id"] for item in report["verdicts"]] == ["cq-1", "cq-2"]
    assert [item["question_id"] for item in report["examiner_reports"]] == [
        "cq-1",
        "cq-2",
        "cq-3",
    ]
    # An executed service failure stays executed (T3-13 contrast): only the
    # question with no report at all is unexecuted.
    assert report["executed_question_ids"] == ["cq-1", "cq-2", "cq-3"]
    assert report["unexecuted_question_ids"] == ["cq-4"]
    assert payload["executed_question_ids"] == ["cq-1", "cq-2", "cq-3"]
    assert payload["unexecuted_question_ids"] == ["cq-4"]
    assert report["sessions"]["question_judging"] == {
        "judgeable_question_ids": ["cq-1", "cq-2"],
        "skipped": {
            "cq-3": "examiner-runtime-incomplete",
            "cq-4": "no-examiner-report",
        },
    }
    assert report["sessions"]["acceptance_judge"]["judged_question_ids"] == ["cq-1", "cq-2"]
    # The partial outcome is a recorded host observable, never a lifecycle error.
    assert report["sessions"]["lifecycle_errors"] == []
    assert report["full_pass"] is False


# --- T3-13: unanswered-with-evidence and empty queries vs service failures -----


def test_unanswered_with_evidence_and_empty_queries_are_judgeable(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(
        tmp_path, [_question("cq-1"), _question("cq-2"), _question("cq-3")]
    )
    handoff = _write_handoff(tmp_path, frozen)
    # A legitimate empty query result is still a successful response.
    forwarder = _DualForwarder(
        _platform_context(), [_EMPTY_QUERY_RESULT, _EMPTY_QUERY_RESULT]
    )
    adapter_class, state = _batch_adapter(
        result=_EMPTY_QUERY_RESULT,
        statuses={"cq-1": "unanswered", "cq-3": "runtime-incomplete"},
    )
    code = _run_cli(tmp_path, run_root, handoff, forwarder, adapter_class, monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    report = _read_report(run_root, payload["batch_id"])

    # The unanswered question with successful query evidence and the empty
    # query both reach the judge; only the service failure does not.
    assert [
        str(item["question_id"]) for item in state["judge_payload"]["questions"]
    ] == ["cq-1", "cq-2"]
    assert sorted(state["judge_payload"]["platform_read_responses"]) == ["cq-1", "cq-2"]
    assert report["sessions"]["question_judging"]["skipped"] == {
        "cq-3": "examiner-runtime-incomplete"
    }
    # The semantic gap never files the executed question as unexecuted.
    assert report["executed_question_ids"] == ["cq-1", "cq-2", "cq-3"]
    assert report["unexecuted_question_ids"] == []
    assert report["full_pass"] is False


# --- T3-4/T3-16: a review verdict blocks PASS without layer misattribution -----


def test_a_question_answer_review_blocks_full_pass_without_misattribution(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1"), _question("cq-2")])
    handoff = _write_handoff(tmp_path, frozen)
    forwarder = _DualForwarder(
        _platform_context(), [_RETAINED_QUERY_RESULT, _RETAINED_QUERY_RESULT]
    )
    adapter_class, _state = _batch_adapter(
        judge_verdicts={
            "cq-1": _passing_verdict("cq-1"),
            "cq-2": _review_verdict("cq-2"),
        }
    )
    code = _run_cli(tmp_path, run_root, handoff, forwarder, adapter_class, monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    report = _read_report(run_root, payload["batch_id"])

    # Every question executed and judged, no runtime failure anywhere -- the
    # batch still cannot PASS with one question-answer-review verdict.
    assert report["executed_question_ids"] == ["cq-1", "cq-2"]
    assert report["unexecuted_question_ids"] == []
    assert report["sessions"]["question_judging"]["skipped"] == {}
    assert report["sessions"]["lifecycle_errors"] == []
    review = report["verdicts"][1]
    assert review["verdict"] == "question-answer-review"
    assert review["failure_layer"] is None
    assert review["note"] == "sql-result-outside-cq-scope"
    assert report["full_pass"] is False
    # The judge role contract names the SQL boundary the verdict encodes.
    assert "sql-result-outside-cq-scope" in _CQ_JUDGE_ROLE_INSTRUCTIONS


# --- one question's unresolved frozen evidence never drags the others ----------


def test_unresolved_frozen_evidence_skips_only_its_question(tmp_path, capsys, monkeypatch):
    second = _question("cq-2")
    second["evidence_refs"] = [{"source": "missing-brief", "locator": "section 2"}]
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1"), second])
    handoff = _write_handoff(tmp_path, frozen)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
    adapter_class, state = _batch_adapter()
    code = _run_cli(tmp_path, run_root, handoff, forwarder, adapter_class, monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    report = _read_report(run_root, payload["batch_id"])

    # Only cq-1 is judged; cq-2 keeps its executed answer and is recorded as
    # lacking a valid verdict -- a per-question gap, never a host fault that
    # blocks the other questions.
    assert [
        str(item["question_id"]) for item in state["judge_payload"]["questions"]
    ] == ["cq-1"]
    skips = report["sessions"]["question_judging"]["skipped"]
    assert list(skips) == ["cq-2"]
    assert skips["cq-2"].startswith("evidence-unresolved: cq_evidence_unresolved")
    assert [
        error["stage"] for error in report["sessions"]["lifecycle_errors"]
    ] == []
    assert report["executed_question_ids"] == ["cq-1", "cq-2"]
    assert report["full_pass"] is False


# --- T3-12/T3-18: the verified handoff directs a unique attempt directory ------


def _production_handoff(frozen: dict, *, attempt: str = "attempt-0001") -> dict:
    return {
        "schema_version": "r3-0-012-production-handoff/v1",
        "run_id": "r3012-run",
        "task_id": "task-r3012",
        "profile_id": "profile-r3012",
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
        "joint_checklist": {
            "state": "pending",
            "note": "the 008B joint checklist is not a cq_semantic precondition",
        },
        "ready": True,
        "pending_writes": False,
        "acceptance_attempt_id": attempt,
        "batch_id": frozen["batch_id"],
        "report_directory": f"acceptance-v3/reports/{frozen['batch_id']}/{attempt}",
    }


def _publish_handoff(run_root: Path, handoff: dict) -> Path:
    path = run_root / "acceptance-v3" / "production-handoff.json"
    path.write_text(json.dumps(handoff, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def _handoff_file(tmp_path: Path, handoff: dict, name: str = "handoff.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(handoff, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def _write_handoff_checkpoint(
    run_root: Path,
    handoff: dict,
    *,
    checkpoint_id: str = "production_handoff-0001",
    kind: str = "production_handoff",
    event_kind: str = "production_handoff",
    source_run_id: str | None = None,
    platform_bindings: dict | None = None,
    scope_refs: dict | None = None,
    event_scope_refs: dict | None = None,
    manifest_digest: str | None = None,
    write_event: bool = True,
) -> Path:
    """Write the Runner's automatic production-handoff checkpoint package.

    Mirrors a real save: ``checkpoints/<id>/manifest.json`` plus the
    ``checkpoint-saved`` evidence line carrying the manifest byte digest and
    the freeze/attempt scope refs.  ``manifest_digest=""`` writes the event
    without the digest field; every other override exists for the failing
    verification cases.
    """

    refs = {
        "freeze_id": handoff["freeze_id"],
        "acceptance_attempt_id": handoff["acceptance_attempt_id"],
    }
    manifest = {
        "kind": kind,
        "source_run_id": source_run_id if source_run_id is not None else handoff["run_id"],
        "scope_refs": dict(scope_refs if scope_refs is not None else refs),
        "platform_bindings": platform_bindings if platform_bindings is not None else {
            "project_id": "project-1",
            "ontology_id": "ontology-1",
            "ontology_ids": ["ontology-1"],
            "run_scope": {"mode": "create"},
        },
    }
    path = run_root / "checkpoints" / checkpoint_id / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path.write_bytes(encoded)
    if write_event:
        event = {
            "event": "checkpoint-saved",
            "kind": event_kind,
            "checkpoint_id": checkpoint_id,
            "scope_refs": dict(event_scope_refs if event_scope_refs is not None else refs),
            "manifest_digest": (
                f"sha256:{hashlib.sha256(encoded).hexdigest()}"
                if manifest_digest is None else manifest_digest
            ),
        }
        if manifest_digest == "":
            event.pop("manifest_digest")
        evidence = run_root / "evidence" / "checkpoints.jsonl"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with evidence.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _consume(run_root: Path, frozen: dict, handoff: dict, **kwargs):
    contract = json.loads((run_root / "acceptance-v3" / "run-contract.json").read_text())
    return _cq_consume_production_handoff(
        run_root, handoff, contract=contract, batch_id=frozen["batch_id"],
        freeze_digest=frozen["snapshot_digest"], **kwargs,
    )


def _attempt_report(run_root: Path, batch_id: str, attempt: str) -> dict:
    return json.loads(
        (
            run_root / "acceptance-v3" / "reports" / batch_id / attempt / "batch-report.json"
        ).read_text(encoding="utf-8")
    )


def test_the_verified_handoff_directs_the_attempt_directory(tmp_path, capsys, monkeypatch):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1"), _question("cq-2")])
    handoff = _production_handoff(frozen)
    _publish_handoff(run_root, handoff)
    submitted = _handoff_file(tmp_path, handoff)
    forwarder = _DualForwarder(
        _platform_context(), [_RETAINED_QUERY_RESULT, _RETAINED_QUERY_RESULT]
    )
    adapter_class, _state = _batch_adapter()
    code = _run_cli(tmp_path, run_root, submitted, forwarder, adapter_class, monkeypatch)
    assert code == 0

    attempt_dir = run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
    report = json.loads((attempt_dir / "batch-report.json").read_text(encoding="utf-8"))
    assert report["full_pass"] is True
    # No batch-level report is written next to the attempt directories.
    assert not (
        run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "batch-report.json"
    ).exists()
    # The attempt retains its own handoff copy (design §4.5).
    retained = json.loads((attempt_dir / "production-handoff.json").read_text(encoding="utf-8"))
    assert retained == handoff
    assert (attempt_dir / "attribution.json").is_file()


def test_a_published_attempt_report_is_never_overwritten(tmp_path, capsys, monkeypatch):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    first_handoff = _production_handoff(frozen)
    _publish_handoff(run_root, first_handoff)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
    adapter_class, _state = _batch_adapter()
    code = _run_cli(
        tmp_path, run_root, _handoff_file(tmp_path, first_handoff), forwarder,
        adapter_class, monkeypatch,
    )
    assert code == 0
    attempt_dir = run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
    original = (attempt_dir / "batch-report.json").read_bytes()
    original_copy = (attempt_dir / "production-handoff.json").read_bytes()

    # Re-running the same registered attempt is a typed conflict, never an
    # overwrite (T3-12/T3-18).
    again = _run_cli(
        tmp_path, run_root, _handoff_file(tmp_path, first_handoff, "handoff-again.json"),
        _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT]), adapter_class,
        monkeypatch,
    )
    assert again == 2
    assert "cq_handoff_immutable" in capsys.readouterr().err
    assert (attempt_dir / "batch-report.json").read_bytes() == original
    assert (attempt_dir / "production-handoff.json").read_bytes() == original_copy
    assert not (run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0002").exists()

    # A newly registered attempt recovers the conflict: the CLI writes the new
    # directory and the old attempt's bytes are untouched.
    second_handoff = _production_handoff(frozen, attempt="attempt-0002")
    _publish_handoff(run_root, second_handoff)
    recovered = _run_cli(
        tmp_path, run_root, _handoff_file(tmp_path, second_handoff, "handoff-second.json"),
        _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT]), adapter_class,
        monkeypatch,
    )
    assert recovered == 0
    assert (attempt_dir / "batch-report.json").read_bytes() == original
    second_report = _attempt_report(run_root, frozen["batch_id"], "attempt-0002")
    assert second_report["full_pass"] is True


def test_known_not_applied_work_does_not_block_read_only_acceptance(
    tmp_path, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = _production_handoff(frozen)
    handoff["not_applied"] = [{"batch_id": "rejected-before-write"}]
    _publish_handoff(run_root, handoff)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
    adapter_class, _state = _batch_adapter()

    code = _run_cli(
        tmp_path,
        run_root,
        _handoff_file(tmp_path, handoff),
        forwarder,
        adapter_class,
        monkeypatch,
    )

    assert code == 0
    retained = json.loads(
        (
            run_root
            / "acceptance-v3"
            / "reports"
            / frozen["batch_id"]
            / "attempt-0001"
            / "production-handoff.json"
        ).read_text(encoding="utf-8")
    )
    assert retained["not_applied"] == [{"batch_id": "rejected-before-write"}]


def test_t0_5_the_three_acceptance_names_are_recorded_on_separate_surfaces(
    tmp_path, capsys, monkeypatch
):
    """T0-5 (executed half, independent round defect D2): ``acceptance_target``
    (the Task/run-contract selector), ``acceptance_mode`` (the read-only
    acceptance attribution) and ``blind_status`` (the exposure label) appear
    together in one cq_semantic run and are each recorded on their own surface
    -- none is reused as, or overwritten by, another."""
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    # The Runner-written snapshot of a cq_semantic Task (contracts T0-2/T0-4).
    contract_path = run_root / "acceptance-v3" / "run-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["parameters"]["acceptance_target"] = "cq_semantic"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    handoff = _production_handoff(frozen)
    _publish_handoff(run_root, handoff)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
    adapter_class, _state = _batch_adapter()
    code = _run_cli(
        tmp_path, run_root, _handoff_file(tmp_path, handoff), forwarder,
        adapter_class, monkeypatch,
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    # The mode and the exposure label coexist in the CLI payload; the target
    # stays where the Runner froze it and the run does not rewrite it.
    assert payload["acceptance_mode"] == "read-only-acceptance"
    assert payload["blind_status"] == "blind"
    assert json.loads(contract_path.read_text(encoding="utf-8"))["parameters"] == {
        "competency_question_acceptance": True,
        "acceptance_target": "cq_semantic",
    }
    attempt_dir = (
        run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
    )
    attribution = json.loads((attempt_dir / "attribution.json").read_text(encoding="utf-8"))
    assert attribution["acceptance_mode"] == "read-only-acceptance"
    assert attribution["blind_status"] == "blind"
    report = json.loads((attempt_dir / "batch-report.json").read_text(encoding="utf-8"))
    assert report["blind_status"]["blind_status"] == "blind"
    # The handoff's target selector round-trips through the retained copy.
    retained = json.loads((attempt_dir / "production-handoff.json").read_text(encoding="utf-8"))
    assert retained["acceptance_target"] == "cq_semantic"


def test_a_mid_run_publication_of_the_same_attempt_is_a_typed_conflict(
    tmp_path, capsys, monkeypatch
):
    """T3-18 concurrent clause (independent round defect D1): two acceptance
    processes can both pass the admission-time ``exists`` check on the same
    attempt.  Whichever publishes first owns the report; the loser must get the
    typed ``cq_handoff_immutable`` conflict at its own publication and never
    replace the winner's bytes."""
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = _production_handoff(frozen)
    _publish_handoff(run_root, handoff)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])

    def publish_as_another_process(packet) -> None:
        report_dir = run_root / "acceptance-v3" / "reports" / packet.batch_id / "attempt-0001"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "batch-report.json").write_bytes(
            b'{"process-B": "published first"}'
        )

    adapter_class, _state = _batch_adapter(on_examiner_packet=publish_as_another_process)
    code = _run_cli(
        tmp_path, run_root, _handoff_file(tmp_path, handoff), forwarder,
        adapter_class, monkeypatch,
    )
    assert code == 2
    assert "cq_handoff_immutable" in capsys.readouterr().err
    attempt_dir = (
        run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
    )
    # The concurrent winner's published bytes survive verbatim and no staging
    # file from this command's rejected publication lingers either.
    assert (attempt_dir / "batch-report.json").read_bytes() == b'{"process-B": "published first"}'
    assert list(attempt_dir.glob("*.tmp")) == []


def test_a_handoff_that_does_not_match_the_published_record_is_rejected(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    published = _production_handoff(frozen)
    _publish_handoff(run_root, published)
    forged = {**published, "ready": False, "pending_writes": True}
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
    adapter_class, _state = _batch_adapter()
    code = _run_cli(
        tmp_path, run_root, _handoff_file(tmp_path, forged), forwarder,
        adapter_class, monkeypatch,
    )
    assert code == 2
    assert "does not match the Runner-published production handoff" in capsys.readouterr().err
    assert not (run_root / "acceptance-v3" / "reports").exists()


@pytest.mark.parametrize(
    "mutation, code_fragment",
    [
        # An unsettled handoff: derived booleans say otherwise.
        ({"ready": False, "pending_writes": True}, "not a settled read-only handoff"),
        # An unsettled handoff: unknown staged writes are still in flight.
        ({"unknown_writes": [{"batch": "b-1"}]}, "cq_unknown_write_pending"),
        # The published record names a directory that is not its own attempt.
        ({"report_directory": "acceptance-v3/reports/batch-r3011/attempt-9999"},
         "does not match its batch and attempt"),
    ],
)
def test_an_invalid_published_handoff_record_is_rejected(
    tmp_path, capsys, monkeypatch, mutation, code_fragment
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), **mutation}
    _publish_handoff(run_root, handoff)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
    adapter_class, _state = _batch_adapter()
    code = _run_cli(
        tmp_path, run_root, _handoff_file(tmp_path, handoff), forwarder,
        adapter_class, monkeypatch,
    )
    assert code == 2
    assert code_fragment in capsys.readouterr().err
    # Nothing was written: no report directory, no judge session ran.
    assert not (run_root / "acceptance-v3" / "reports").exists()


def test_a_legacy_batch_level_report_is_neither_reused_nor_overwritten(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = _write_handoff(tmp_path, frozen)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
    adapter_class, _state = _batch_adapter()
    code = _run_cli(tmp_path, run_root, handoff, forwarder, adapter_class, monkeypatch)
    assert code == 0
    batch_report = run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "batch-report.json"
    original = batch_report.read_bytes()

    # The legacy 011-shape path gains the same first-write immutability.
    again = _run_cli(
        tmp_path, run_root, handoff, _DualForwarder(_platform_context(), []),
        adapter_class, monkeypatch,
    )
    assert again == 2
    assert "cq_handoff_immutable" in capsys.readouterr().err
    assert batch_report.read_bytes() == original


# --- R4.0-009: recovering the run's own single-Ontology scope decision ----------

_EMPTY_SCOPE = {"project_id": "project-1", "ontology_ids": []}


@pytest.mark.parametrize("continuation", [False, True])
@pytest.mark.parametrize(
    "bindings",
    [
        # The real save: direct platform bindings carry both shapes.
        {"project_id": "project-1", "ontology_id": "ontology-1",
         "ontology_ids": ["ontology-1"], "run_scope": {"mode": "create"}},
        # A list-only single-Ontology binding is the same verified identity.
        {"project_id": "project-1", "ontology_ids": ["ontology-1"]},
        # The recorded run scope is the fallback host-authoritative source.
        {"run_scope": {"mode": "existing", "project_id": "project-1",
                       "ontology_id": "ontology-1"}},
    ],
)
def test_an_empty_single_ontology_scope_recovers_from_the_handoff_checkpoint(
    tmp_path, continuation, bindings
):
    """R4.0-009: a handoff whose only defect is the empty authorized list is
    re-anchored to the run's own verified checkpoint identity -- exactly one
    Ontology of the same Project -- without touching any published bytes."""

    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), "scope_binding": dict(_EMPTY_SCOPE)}
    published = _publish_handoff(run_root, handoff)
    before = published.read_bytes()
    # Unrelated checkpoint history is present, as in a real run.
    _write_handoff_checkpoint(
        run_root, handoff, checkpoint_id="materialization_progress-0001",
        kind="materialization_progress", event_kind="materialization_progress",
        scope_refs={"freeze_id": frozen["batch_id"]},
    )
    _write_handoff_checkpoint(run_root, handoff, platform_bindings=bindings)
    output = tmp_path / "continuation"
    kwargs = ({"continuation_output": output, "continuation_attempt": "attempt-0002"}
              if continuation else {})
    directory, binding = _consume(run_root, frozen, handoff, **kwargs)
    assert [item["ontology_id"] for item in binding["ontologies"]] == ["ontology-1"]
    assert all(item["project_id"] == "project-1" for item in binding["ontologies"])
    # The published record and this attempt's retained copy keep the original
    # bytes: the recovery lives in this decision, never in rewritten evidence.
    assert published.read_bytes() == before
    assert (directory / "production-handoff.json").read_bytes() == before
    assert directory.is_relative_to(output if continuation else run_root)


def test_a_recorded_scope_is_never_merged_with_the_checkpoint_binding(tmp_path):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen),
               "scope_binding": {"project_id": "project-1", "ontology_ids": ["ontology-7"]}}
    _publish_handoff(run_root, handoff)
    _write_handoff_checkpoint(run_root, handoff)
    _directory, binding = _consume(run_root, frozen, handoff)
    assert [item["ontology_id"] for item in binding["ontologies"]] == ["ontology-7"]


@pytest.mark.parametrize(
    "defect, overrides",
    [
        # A digest that does not match the bytes on disk.
        ("digest_mismatch", {"manifest_digest": "sha256:" + "0" * 64}),
        # An event without any digest to verify the manifest with.
        ("missing_event_digest", {"manifest_digest": ""}),
        ("event_kind_mismatch", {"event_kind": "materialization_progress"}),
        ("manifest_kind_mismatch", {"kind": "materialization_progress"}),
        # Another attempt's or another freeze's checkpoint never authorizes.
        ("event_refs_mismatch",
         {"event_scope_refs": {"freeze_id": "cq-batch-9999",
                               "acceptance_attempt_id": "attempt-0001"}}),
        ("manifest_refs_mismatch",
         {"scope_refs": {"freeze_id": "cq-batch-9999",
                         "acceptance_attempt_id": "attempt-0001"}}),
        # Another Project's binding, or more than one Ontology: fail closed.
        ("project_mismatch",
         {"platform_bindings": {"project_id": "project-other",
                                "ontology_id": "ontology-1",
                                "ontology_ids": ["ontology-1"]}}),
        ("multi_ontology",
         {"platform_bindings": {"project_id": "project-1",
                                "ontology_ids": ["ontology-1", "ontology-2"]}}),
        # The source run is not this handoff's run.
        ("source_run_mismatch", {"source_run_id": "r-other"}),
    ],
)
def test_an_empty_scope_without_a_verified_checkpoint_is_refused(
    tmp_path, defect, overrides
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), "scope_binding": dict(_EMPTY_SCOPE)}
    published = _publish_handoff(run_root, handoff)
    before = published.read_bytes()
    _write_handoff_checkpoint(run_root, handoff, **overrides)
    with pytest.raises(TeamConfigurationError, match="cq_batch_scope_unauthorized"):
        _consume(run_root, frozen, handoff)
    assert published.read_bytes() == before
    attempt_dir = (
        run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
    )
    assert not (attempt_dir / "batch-report.json").exists()


def test_an_empty_scope_without_any_checkpoint_is_refused(tmp_path):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), "scope_binding": dict(_EMPTY_SCOPE)}
    _publish_handoff(run_root, handoff)
    with pytest.raises(TeamConfigurationError, match="cq_batch_scope_unauthorized"):
        _consume(run_root, frozen, handoff)


def test_an_empty_scope_with_unreadable_or_missing_evidence_is_refused(tmp_path):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), "scope_binding": dict(_EMPTY_SCOPE)}
    _publish_handoff(run_root, handoff)
    path = _write_handoff_checkpoint(run_root, handoff)
    path.unlink()
    with pytest.raises(TeamConfigurationError, match="cq_batch_scope_unauthorized"):
        _consume(run_root, frozen, handoff)
    path = _write_handoff_checkpoint(run_root, handoff)
    path.write_text("{corrupt", encoding="utf-8")
    with pytest.raises(TeamConfigurationError, match="cq_batch_scope_unauthorized"):
        _consume(run_root, frozen, handoff)
    (run_root / "evidence" / "checkpoints.jsonl").write_text(
        "not json\n", encoding="utf-8"
    )
    with pytest.raises(TeamConfigurationError, match="cq_batch_scope_unauthorized"):
        _consume(run_root, frozen, handoff)


def test_two_matching_handoff_checkpoints_are_ambiguous_and_refused(tmp_path):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), "scope_binding": dict(_EMPTY_SCOPE)}
    _publish_handoff(run_root, handoff)
    _write_handoff_checkpoint(run_root, handoff, checkpoint_id="production_handoff-0001")
    _write_handoff_checkpoint(run_root, handoff, checkpoint_id="production_handoff-0002")
    with pytest.raises(TeamConfigurationError, match="cq_batch_scope_unauthorized"):
        _consume(run_root, frozen, handoff)


def test_the_defective_handoff_completes_the_real_cli_start(tmp_path, capsys, monkeypatch):
    """The end-to-end R4.0-009 restart: the CLI binds the run's one verified
    Ontology and publishes its attempt report instead of exiting 2."""

    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), "scope_binding": dict(_EMPTY_SCOPE)}
    published = _publish_handoff(run_root, handoff)
    before = published.read_bytes()
    _write_handoff_checkpoint(run_root, handoff)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
    examiner_packets: list = []
    adapter_class, _state = _batch_adapter(on_examiner_packet=examiner_packets.append)
    code = _run_cli(
        tmp_path, run_root, _handoff_file(tmp_path, handoff), forwarder,
        adapter_class, monkeypatch,
    )
    assert code == 0
    assert "cq_batch_scope_unauthorized" not in capsys.readouterr().err
    attempt_dir = (
        run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
    )
    assert (attempt_dir / "batch-report.json").is_file()
    assert published.read_bytes() == before
    assert (attempt_dir / "production-handoff.json").read_bytes() == before
    # The examiner child was scoped to exactly the recovered Ontology.
    payload = examiner_packets[0].to_dict()["payload"]
    assert payload["authorized_scope"] == ["ontology-1"]
    assert [
        item["ontology_id"] for item in payload["model_binding"]["ontologies"]
    ] == ["ontology-1"]


def test_the_cli_still_refuses_an_empty_scope_without_a_verified_checkpoint(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), "scope_binding": dict(_EMPTY_SCOPE)}
    _publish_handoff(run_root, handoff)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])
    adapter_class, _state = _batch_adapter()
    code = _run_cli(
        tmp_path, run_root, _handoff_file(tmp_path, handoff), forwarder,
        adapter_class, monkeypatch,
    )
    assert code == 2
    assert "cq_batch_scope_unauthorized" in capsys.readouterr().err
    attempt_dir = (
        run_root / "acceptance-v3" / "reports" / frozen["batch_id"] / "attempt-0001"
    )
    assert not (attempt_dir / "batch-report.json").exists()


# --- R4.0-009 round 2: recovery serves the recorded empty list and nothing else ---

@pytest.mark.parametrize(
    "invalid_scope",
    [
        {"project_id": "project-1", "ontology_ids": [42]},
        {"project_id": "project-1", "ontology_ids": [None]},
        {"project_id": "project-1", "ontology_ids": [True]},
        {"project_id": "project-1", "ontology_ids": [""]},
        {"project_id": "project-1", "ontology_ids": ["", None]},
    ],
)
def test_an_invalid_non_empty_scope_never_borrows_the_checkpoint_identity(
    tmp_path, invalid_scope
):
    """Round-2 High: only the recorded ``[]`` may be recovered.  A non-empty
    list whose entries are not authorized non-empty strings is the original
    refusal -- it must not be laundered into the checkpoint's Ontology."""

    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), "scope_binding": invalid_scope}
    published = _publish_handoff(run_root, handoff)
    before = published.read_bytes()
    # A perfectly valid checkpoint is on disk: the entry list alone decides.
    _write_handoff_checkpoint(run_root, handoff)
    with pytest.raises(TeamConfigurationError, match="cq_batch_scope_unauthorized"):
        _consume(run_root, frozen, handoff)
    assert published.read_bytes() == before


@pytest.mark.parametrize(
    "bindings",
    [
        # production_resume_bindings stringifies list entries: 42 -> "42".
        {"project_id": "project-1", "ontology_ids": [42]},
        {"project_id": "project-1", "ontology_ids": [None]},
        {"project_id": "project-1", "ontology_ids": [True]},
        {"project_id": "project-1", "ontology_id": 42, "ontology_ids": ["ontology-1"]},
        {"project_id": "project-1", "ontology_id": None, "ontology_ids": ["ontology-1"]},
        {"project_id": "project-1", "ontology_id": "", "ontology_ids": ["ontology-1"]},
        # The run_scope fallback goes through the same stringification.
        {"run_scope": {"mode": "create", "project_id": "project-1",
                       "ontology_ids": [42]}},
        {"run_scope": {"mode": "create", "project_id": "project-1",
                       "ontology_ids": [None]}},
        {"run_scope": {"mode": "create", "project_id": "project-1",
                       "ontology_id": 42}},
    ],
)
def test_a_coerced_manifest_identity_is_never_a_trusted_identity(tmp_path, bindings):
    """Round-2 High: a manifest identity field must hold an original non-empty
    string; numbers, booleans and None are never converted into authorization."""

    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = {**_production_handoff(frozen), "scope_binding": dict(_EMPTY_SCOPE)}
    _publish_handoff(run_root, handoff)
    _write_handoff_checkpoint(run_root, handoff, platform_bindings=bindings)
    with pytest.raises(TeamConfigurationError, match="cq_batch_scope_unauthorized"):
        _consume(run_root, frozen, handoff)


def test_judge_native_input_partition_preserves_complete_ordered_evidence():
    from modeling_team import __main__ as cli
    from modeling_team.acceptance_runtime import AcceptanceBatchPacket, _unfreeze_packet
    from modeling_team.tests.test_r3011_acceptance_runtime import _batch_packet, _questions
    from modeling_team.runtimes.codex import (
        _CODEX_MAX_INPUT_TEXT_CHARS, _v3_acceptance_first_turn_text,
    )

    packet = _batch_packet(role="acceptance", questions=_questions(11))
    payload = _unfreeze_packet(packet.payload)
    # Each approved full evidence item is generic, distinct and retained intact.
    for index, entry in enumerate(payload["evidence_bundle"]["entries"]):
        entry["content"] = str(index) + "x" * 150_000
        from modeling_team.competency_questions import content_digest
        entry["content_digest"] = content_digest(entry["content"])
    payload["evidence_bundle"].pop("bundle_digest", None)
    packet = AcceptanceBatchPacket.build("acceptance", payload)
    groups = cli._cq_judge_input_packets(packet)
    assert len(groups) > 1
    assert [q["question_id"] for group in groups for q in group.payload["questions"]] == [
        q["question_id"] for q in packet.payload["questions"]
    ]
    for group in groups:
        assert len(_v3_acceptance_first_turn_text(group, _CQ_JUDGE_ROLE_INSTRUCTIONS)) <= (
            _CODEX_MAX_INPUT_TEXT_CHARS
        )
        ids = {q["question_id"] for q in group.payload["questions"]}
        assert [dict(e) for e in group.payload["evidence_bundle"]["entries"]] == [
            dict(e) for e in packet.payload["evidence_bundle"]["entries"]
            if e["question_id"] in ids
        ]
    small = _batch_packet(role="acceptance", questions=_questions(2))
    assert cli._cq_judge_input_packets(small) == [small]


@pytest.mark.parametrize("oversized,failed_group", [
    (None, None), (None, 1), ("first", None), ("first", 1),
    ("all", None), ("all-but-last", None),
])
def test_oversized_judge_groups_use_real_factory_sink_and_global_denominator(
    tmp_path, capsys, monkeypatch, oversized, failed_group,
):
    from io import StringIO
    from threading import Event
    from types import SimpleNamespace
    from modeling_team.acceptance_runtime import ReportSinkServer, _packet_canonical
    from modeling_team.runtimes.codex import CodexRuntimeAdapter, CodexRuntimeRPCError
    from modeling_team.tests.test_r3011_acceptance_runtime import _submit

    questions = [_question(f"cq-{index}") for index in range(11)]
    oversized_ids = set()
    for index, question in enumerate(questions):
        if (oversized == "all" or (oversized == "first" and index == 0)
                or (oversized == "all-but-last" and index < 10)):
            question["answer_points"] = ["generic required point " + "y" * 1_100_000]
            oversized_ids.add(question["question_id"])
    run_root, frozen = _write_run_root(tmp_path, questions)
    content = "generic approved evidence " + "x" * 150_000
    for role in ("coordinator", "modeling", "competency-question"):
        (run_root / "sources" / role / "scenario-brief").write_text(content)
    manifest = json.loads((run_root / "source-manifest.json").read_text())
    manifest["sources"][0]["sha256"] = hashlib.sha256(content.encode()).hexdigest()
    (run_root / "source-manifest.json").write_text(json.dumps(manifest))
    original_freeze = (run_root / "competency-questions/frozen/freeze-0001.json").read_bytes()
    handoff = _write_handoff(tmp_path, frozen)
    platform, _ = _batch_adapter()
    constructions = []
    sinks = []
    start = ReportSinkServer.start
    def capture(sink):
        sinks.append(sink)
        start(sink)
    monkeypatch.setattr(ReportSinkServer, "start", capture)
    auth = tmp_path / "fixture-auth.json"
    auth.write_text("{}")
    observed = []

    def adapter_factory(repository_root):
        constructions.append(True)
        if len(constructions) == 1:
            return platform(repository_root=repository_root)
        process = SimpleNamespace(
            stdin=StringIO(), stdout=StringIO(), stderr=StringIO(),
            poll=lambda: None, terminate=lambda: None, kill=lambda: None,
            wait=lambda **kwargs: 0,
        )
        adapter = CodexRuntimeAdapter(
            repository_root=repository_root, use_bwrap=False,
            process_factory=lambda *args, **kwargs: process,
        )
        monkeypatch.setattr(adapter, "preflight_host_auth", lambda: auth)
        monkeypatch.setattr(adapter, "_ensure_standalone_provider_sessions", lambda: None)
        monkeypatch.setattr(adapter, "_seed_models_cache", lambda *args: None)
        def idle(agent, timeout):
            Event().wait(timeout)
            return None
        monkeypatch.setattr(adapter, "_read_output_line", idle)
        def rpc(agent, method, params):
            if method == "initialize":
                return {}
            if method == "thread/start":
                return {"thread": {"id": f"generic-thread-{len(sinks)}"}}
            if method == "mcpServerStatus/list":
                return {"data": [{"name": "examiner_report", "tools": [
                    {"name": "submit_examiner_report"},
                ]}]}
            if method == "turn/start":
                text = "".join(item["text"] for item in params["input"])
                if len(text) > 1_048_576:
                    raise CodexRuntimeRPCError(method, -32602, "rpc_error")
                payload = json.loads((agent.home / "input.json").read_text())
                ids = [q["question_id"] for q in payload["questions"]]
                assert ids == list(sinks[-1].batch_contract.question_ids)
                assert set(payload["platform_read_responses"]) == set(ids)
                assert all(e["content"] == content for e in payload["evidence_bundle"]["entries"])
                assert len(payload["examiner_reports"]) == len(ids)
                assert "verdicts" not in payload
                assert _packet_canonical(payload) == (agent.home / "input.json").read_bytes()
                observed.append((ids, len(text)))
                if len(observed) == failed_group:
                    raise CodexRuntimeRPCError(method, -32602, "rpc_error")
                for question_id in ids:
                    assert _submit(sinks[-1].socket_path, _passing_verdict(question_id),
                                   token=sinks[-1].token)["ok"] is True
                return {"turn": {"id": "generic-turn"}}
            raise AssertionError(method)
        monkeypatch.setattr(adapter, "_rpc", rpc)
        return adapter

    code = _run_cli(
        tmp_path, run_root, handoff,
        _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT, _RETAINED_QUERY_RESULT]),
        adapter_factory, monkeypatch,
    )
    output = json.loads(capsys.readouterr().out)
    report = _read_report(run_root, frozen["batch_id"])
    groups = report["sessions"]["acceptance_judge"].get("groups", [])
    assert report["sessions"]["acceptance_judge"]["judged_question_ids"] == [
        verdict["question_id"] for verdict in report["verdicts"]
    ]
    assert len(groups) == 0 if oversized in {"all", "all-but-last"} else len(groups) > 1
    eligible = [q["question_id"] for q in questions if q["question_id"] not in oversized_ids]
    assert [qid for ids, _ in observed for qid in ids] == eligible
    assert len(sinks) == (len(groups) or (1 if eligible else 0))
    assert all(g["teardown"]["child_destroyed"] for g in groups)
    complete = failed_group is None and not oversized_ids
    assert output["full_pass"] is complete
    assert code == (0 if complete else 1)
    cleanup = report["sessions"]["cleanup"]
    assert cleanup["children_destroyed"] is True
    assert len(cleanup["children"]) == 1 + len(sinks)
    if oversized_ids:
        assert set(report["sessions"]["question_judging"]["skipped"]) == oversized_ids
        failures = report["sessions"]["acceptance_judge"]["input_failures"]
        assert set(failures) == oversized_ids
        assert all(f["reason_code"] == "judge-input-too-large" for f in failures.values())
        assert all(f["failure_layer"] == "runtime/infrastructure" for f in failures.values())
    if failed_group:
        assert groups[0]["status"] == "runtime-incomplete"
        assert len(report["verdicts"]) == len(eligible) - len(groups[0]["question_ids"])
    else:
        assert len(report["verdicts"]) == len(eligible)
    assert (run_root / "competency-questions/frozen/freeze-0001.json").read_bytes() == original_freeze
    assert all(sink._thread is None or not sink._thread.is_alive() for sink in sinks)


def test_complete_single_question_over_native_limit_is_typed_not_truncated():
    from modeling_team import __main__ as cli
    from modeling_team.acceptance_runtime import (
        AcceptanceBatchPacket, ExaminerRuntimeBlocked, _unfreeze_packet,
    )
    from modeling_team.competency_questions import content_digest
    from modeling_team.tests.test_r3011_acceptance_runtime import _batch_packet, _questions

    payload = _unfreeze_packet(_batch_packet(role="acceptance", questions=_questions(1)).payload)
    entry = payload["evidence_bundle"]["entries"][0]
    entry["content"] = "x" * 1_048_576
    entry["content_digest"] = content_digest(entry["content"])
    payload["evidence_bundle"].pop("bundle_digest", None)
    packet = AcceptanceBatchPacket.build("acceptance", payload)
    with pytest.raises(ExaminerRuntimeBlocked) as blocked:
        cli._cq_judge_input_packets(packet)
    assert blocked.value.evidence["reason_code"] == "judge-input-too-large"
    assert blocked.value.evidence["input_chars"] > blocked.value.evidence["max_chars"]
    assert packet.payload["evidence_bundle"]["entries"][0]["content"] == entry["content"]
