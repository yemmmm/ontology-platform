"""Focused R3.0-011 CLI edge coverage (G4).

These tests cover the executed ``cq-acceptance`` path's own lifecycle edges --
the observed pre/post batch binding, bounded post-read/judge failures, typed
blocked failures, real cleanup evidence, credential gating and the removed
``--platform-base-url`` option -- through the injectable ``forwarder_factory``
seam.  They deliberately do not start an App Server or a child process: the
full controlled-subprocess CLI flow is a separate developer's file, and no test
here monkeypatches the runtime to fake a passing batch.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from modeling_team.__main__ import (
    _CQ_INTERVIEW_SCHEMA,
    _CQ_PLATFORM_READ_KEY_ENV,
    _cq_build_judge_evidence_bundle,
    _run_cq_acceptance,
    main,
)
from modeling_team.acceptance_runtime import (
    ChildRuntimeError,
    ExaminerRuntimeBlocked,
    build_acceptance_judge_packet,
)
from modeling_team.competency_questions import CQ_BATCH_REPORT_SCHEMA, content_digest
from modeling_team.contracts import TeamConfigurationError, repository_root
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.tests.test_r3011_acceptance import _freeze, _question

REPO_ROOT = repository_root()

_RUN_CONTRACT = {
    "schema_version": "r3-0-011-run-contract/v1",
    "run_id": "r3011-run",
    "profile_id": "r3-0-011-competency-question",
    "task_id": "r3-0-008b-staged-real",
    "parameters": {"competency_question_acceptance": True},
}


def _platform_context(
    *,
    source_signature: str = "sig-1",
    graph_set_id: str = "gs-1",
    status: str = "ready",
) -> dict:
    """One canonical read-only workspace context the forwarder can serve."""

    return {
        "state": "ready",
        "source_signature": source_signature,
        "default_graph_set_id": graph_set_id,
        "graph_set_status": status,
        "members": [{"role": "asserted", "revision": "r1", "content_hash": "h1"}],
    }


def _observed_binding(
    context: dict,
    *,
    batch_id: str,
    freeze_digest: str,
    ontology_id: str = "ontology-1",
) -> dict:
    """The CLI's own batch-start observation of one served context (D5)."""

    revisions = sorted(
        (item.get("role"), item.get("revision"), item.get("content_hash"))
        for item in context["members"]
    )
    return {
        "schema_version": "r3-0-011-model-binding/v1",
        "batch_id": batch_id,
        "freeze_digest": freeze_digest,
        "bound_at": "2026-09-09T00:00:00+00:00",
        "ontologies": [
            {
                "project_id": "project-1",
                "ontology_id": ontology_id,
                "workspace_state": {
                    "state_digest": content_digest(
                        {"state": context["state"], "source_signature": context["source_signature"]}
                    )
                },
                "graph_state": {
                    "state_digest": content_digest(
                        {
                            "graph_set_id": context["default_graph_set_id"],
                            "status": context["graph_set_status"],
                            "revisions": revisions,
                        }
                    )
                },
                "authorized_read_tools": ["query_semantic_context"],
            }
        ],
    }


def _handoff_binding(*, batch_id: str, freeze_digest: str, ontology_id: str = "ontology-1") -> dict:
    """The handoff's carried binding: authorization scope plus opaque markers.

    A handoff is written before the batch and cannot own live platform state,
    so its state digests are non-empty opaque markers.  Only the Ontology ids,
    the project and the read-tool scope are authoritative.
    """

    return {
        "schema_version": "r3-0-011-model-binding/v1",
        "batch_id": batch_id,
        "freeze_digest": freeze_digest,
        "bound_at": "2026-09-09T00:00:00+00:00",
        "ontologies": [
            {
                "project_id": "project-1",
                "ontology_id": ontology_id,
                "workspace_state": {"state_digest": f"handoff-marker:{ontology_id}:workspace"},
                "graph_state": {"state_digest": f"handoff-marker:{ontology_id}:graph"},
                "authorized_read_tools": ["query_semantic_context"],
            }
        ],
    }


class _ScriptedForwarder:
    """Controlled read forwarder: records every read, serves scripted state."""

    def __init__(
        self,
        contexts: list[dict],
        *,
        fail_after: int | None = None,
        stop_error: str | None = None,
        failure: Exception | None = None,
    ) -> None:
        self._contexts = contexts
        self._fail_after = fail_after
        self._stop_error = stop_error
        self._failure = failure
        self.calls: list[tuple[str, dict]] = []
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True
        if self._stop_error is not None:
            raise RuntimeError(self._stop_error)

    def forward(self, tool: str, arguments: dict, read_key: str) -> dict:
        self.calls.append((tool, dict(arguments)))
        if self._fail_after is not None and len(self.calls) > self._fail_after:
            if self._failure is not None:
                raise self._failure
            raise TeamConfigurationError("cq_model_state_missing: post-batch read failed")
        return self._contexts[min(len(self.calls) - 1, len(self._contexts) - 1)]


class _RecordingFactory:
    def __init__(self, forwarder: _ScriptedForwarder) -> None:
        self.forwarder = forwarder
        self.requested: list[dict] = []

    def __call__(self, **kwargs):
        self.requested.append(kwargs)
        return self.forwarder


def _write_run_root(tmp_path: Path, questions: list[dict] | None = None) -> tuple[Path, dict]:
    run_root = tmp_path / "run"
    # Zero hidden questions unless a test asks for them: no focused CLI test
    # may start a child session or an App Server.
    frozen = _freeze(questions or [])
    (run_root / "competency-questions" / "frozen").mkdir(parents=True)
    (run_root / "acceptance-v3").mkdir(parents=True)
    (run_root / "competency-questions" / "frozen" / "freeze-0001.json").write_text(
        json.dumps(frozen), encoding="utf-8"
    )
    (run_root / "acceptance-v3" / "run-contract.json").write_text(
        json.dumps(_RUN_CONTRACT), encoding="utf-8"
    )
    return run_root, frozen


def _write_handoff(
    tmp_path: Path,
    frozen: dict,
    binding: dict,
    *,
    post: dict | None = "copy",
) -> Path:
    handoff = {
        "authorized_ontology_ids": [entry["ontology_id"] for entry in binding["ontologies"]],
        "production_delivery": {"ready": True, "pending_writes": False},
        "model_binding": binding,
    }
    if post == "copy":
        handoff["post_batch_model_binding"] = json.loads(json.dumps(binding))
    elif post is not None:
        handoff["post_batch_model_binding"] = post
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(handoff), encoding="utf-8")
    return path


def _run(
    tmp_path: Path,
    run_root: Path,
    handoff: Path,
    factory: _RecordingFactory,
    *,
    unexecuted_report: bool = False,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> int:
    if monkeypatch is not None:
        monkeypatch.setenv(_CQ_PLATFORM_READ_KEY_ENV, "read-key")
    return _run_cq_acceptance(
        Namespace(
            run_root=run_root,
            freeze_id="freeze-0001",
            model_handoff=handoff,
            model_profile=None,
            # Mocked sessions are bounded: nothing here may wait 300 seconds.
            session_timeout=2.0,
            unexecuted_report=unexecuted_report,
        ),
        REPO_ROOT,
        forwarder_factory=factory,
    )


def _report(run_root: Path, payload: dict) -> tuple[Path, dict]:
    report_dir = run_root / "acceptance-v3" / "reports" / payload["batch_id"]
    return report_dir, json.loads((report_dir / "batch-report.json").read_text(encoding="utf-8"))


# --- the executed path binds the state it actually observed (D5) ---------------


def test_marker_handoff_never_gates_and_markers_never_reach_the_report(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path)
    context = _platform_context()
    forwarder = _ScriptedForwarder([context])
    factory = _RecordingFactory(forwarder)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
        post=None,
    )
    code = _run(tmp_path, run_root, handoff, factory, monkeypatch=monkeypatch)
    # The batch starts: the handoff's marker digests are not compared against
    # the live read.  An empty hidden set is still a permanent coverage gap.
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["full_pass"] is False
    assert factory.requested == [
        {
            "repository_root": REPO_ROOT,
            "read_key": "read-key",
            "expected_tools": ("query_semantic_context",),
        }
    ]
    observed = _observed_binding(
        context, batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]
    )
    # The command read the live state twice itself: before and after the batch.
    assert [tool for tool, _ in forwarder.calls] == [
        "get_ontology_workspace_context",
        "get_ontology_workspace_context",
    ]
    assert forwarder.started and forwarder.stopped
    report_dir, report = _report(run_root, payload)
    sessions = report["sessions"]
    # The retained batch binding is the CLI's own observation, markers replaced.
    assert sessions["batch_model_binding"] == observed
    assert sessions["post_batch_model_binding"] == observed
    assert sessions["pre_batch_model_state_drift"] == []
    assert sessions["post_batch_model_state_drift"] == []
    assert sessions["lifecycle_errors"] == []
    assert sessions["cleanup"]["forwarder_stopped"] is True
    assert sessions["cleanup"]["children_destroyed"] is True
    # No handoff marker digest survives into any persisted artifact.
    for name in ("batch-report.json", "attribution.json"):
        assert "handoff-marker" not in (report_dir / name).read_text(encoding="utf-8")
    attribution = json.loads((report_dir / "attribution.json").read_text(encoding="utf-8"))
    assert attribution["platform_read_path"] == "local-canonical-mcp-forwarder"


def test_post_session_drift_is_measured_against_the_actual_pre_binding(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path)
    pre_context = _platform_context(source_signature="sig-1")
    post_context = _platform_context(source_signature="sig-2")
    forwarder = _ScriptedForwarder([pre_context, post_context])
    factory = _RecordingFactory(forwarder)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
        post=None,
    )
    code = _run(tmp_path, run_root, handoff, factory, monkeypatch=monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    sessions = _report(run_root, payload)[1]["sessions"]
    assert sessions["batch_model_binding"] == _observed_binding(
        pre_context, batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]
    )
    assert sessions["post_batch_model_binding"] == _observed_binding(
        post_context, batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]
    )
    # Actual post vs actual pre: the mid-batch state change is named.
    assert sessions["post_batch_model_state_drift"] == ["ontology-1"]
    assert sessions["pre_batch_model_state_drift"] == []


def test_the_unexecuted_report_branch_still_requires_the_post_batch_binding(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path)
    context = _platform_context()
    forwarder = _ScriptedForwarder([context])
    factory = _RecordingFactory(forwarder)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
        post=None,
    )
    code = _run(
        tmp_path, run_root, handoff, factory, unexecuted_report=True, monkeypatch=monkeypatch
    )
    assert code == 2
    assert "cq_model_binding_missing" in capsys.readouterr().err
    # The legacy branch never touched the platform.
    assert factory.requested == []


def test_a_failed_post_batch_state_read_is_bounded_and_keeps_the_reports(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    context = _platform_context()
    # One successful pre-read, then the post-batch re-read fails.
    forwarder = _ScriptedForwarder([context], fail_after=1)
    factory = _RecordingFactory(forwarder)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
    )
    emitted = [
        {
            "schema_version": CQ_BATCH_REPORT_SCHEMA,
            "batch_id": frozen["batch_id"],
            "question_id": "cq-1",
            "question_content_version": 1,
            "answer": "answer for cq-1",
            "evidence_refs": ["resource-1"],
            "explicit_unknown": [],
            "status": "completed",
            "failure_layer": None,
            "reason": None,
        }
    ]

    class _StubAdapter:
        """Bounded-lifecycle edge double: one completed question, no model run.

        This is NOT the real-factory proof -- the controlled App Server CLI
        flow belongs to the parallel developer's fixture file.  This test only
        exercises what the CLI itself does when the post-batch read fails after
        a question has already landed.
        """

        def __init__(self, *, repository_root: Path) -> None:
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
            return [dict(report) for report in emitted]

    monkeypatch.setattr("modeling_team.__main__.CodexRuntimeAdapter", _StubAdapter)
    code = _run(tmp_path, run_root, handoff, factory, monkeypatch=monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    report = _report(run_root, payload)[1]
    assert [item["question_id"] for item in report["examiner_reports"]] == ["cq-1"]
    assert report["executed_question_ids"] == ["cq-1"]
    stages = [item["stage"] for item in report["sessions"]["lifecycle_errors"]]
    # Both follow-up lifecycle steps are bounded here: the post-batch state
    # read failed, and with the run root carrying no approved evidence the
    # judge bundle fails too.  Neither discards the landed report.
    assert stages == ["post-batch-model-state-read", "judge-evidence-bundle"]
    # The judge is skipped on post-state failure; the batch can never pass.
    assert "skipped" in report["sessions"]["acceptance_judge"]["reason"]
    assert report["full_pass"] is False


def test_a_blocked_child_session_keeps_its_typed_reason_and_partial_reports(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    context = _platform_context()
    forwarder = _ScriptedForwarder([context])
    factory = _RecordingFactory(forwarder)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
    )

    class _DyingAdapter:
        """One accepted question, then the child dies before the batch ends."""

        def __init__(self, *, repository_root: Path) -> None:
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
            reports.append(
                {
                    "schema_version": CQ_BATCH_REPORT_SCHEMA,
                    "batch_id": frozen["batch_id"],
                    "question_id": "cq-1",
                    "question_content_version": 1,
                    "answer": "answer for cq-1",
                    "evidence_refs": ["resource-1"],
                    "explicit_unknown": [],
                    "status": "completed",
                    "failure_layer": None,
                    "reason": None,
                }
            )
            raise ExaminerRuntimeBlocked(
                "runtime-infrastructure",
                role="platform",
                evidence={"reason_code": "child-exited", "reports": 1},
            )

    monkeypatch.setattr("modeling_team.__main__.CodexRuntimeAdapter", _DyingAdapter)
    code = _run(tmp_path, run_root, handoff, factory, monkeypatch=monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    report = _report(run_root, payload)[1]
    examiner = report["sessions"]["platform_examiner"]
    # The typed reason and layer survive into the report, not just str(exc).
    assert examiner["failure"]["status"] == "BLOCKED"
    assert examiner["failure"]["blocked_reason"] == "runtime-infrastructure"
    assert examiner["failure"]["evidence"]["reason_code"] == "child-exited"
    assert "child-exited" in examiner["failure_reason"]
    assert "runtime-infrastructure" in examiner["failure_reason"]
    assert examiner["first_failure"]["failure_layer"] == "runtime-infrastructure"
    lifecycle = report["sessions"]["lifecycle_errors"][0]
    assert lifecycle["stage"] == "platform-examiner-session"
    assert lifecycle["failure"]["evidence"]["reason_code"] == "child-exited"
    # The accepted question is still retained and the judge never ran.
    assert [item["question_id"] for item in report["examiner_reports"]] == ["cq-1"]
    assert "skipped" in report["sessions"]["acceptance_judge"]["reason"]
    assert report["full_pass"] is False


def test_a_missing_read_key_is_rejected_before_the_forwarder_starts(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path)
    context = _platform_context()
    forwarder = _ScriptedForwarder([context])
    factory = _RecordingFactory(forwarder)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
    )
    monkeypatch.delenv(_CQ_PLATFORM_READ_KEY_ENV, raising=False)
    code = _run(tmp_path, run_root, handoff, factory)
    assert code == 2
    errors = capsys.readouterr().err
    assert "cq_acceptance_credentials_missing" in errors
    assert _CQ_PLATFORM_READ_KEY_ENV in errors
    assert factory.requested == []
    assert forwarder.started is False


def test_a_forwarder_stop_failure_is_recorded_and_is_never_a_pass(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path)
    context = _platform_context()
    forwarder = _ScriptedForwarder([context], stop_error="socket busy")
    factory = _RecordingFactory(forwarder)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
    )
    code = _run(tmp_path, run_root, handoff, factory, monkeypatch=monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    cleanup = _report(run_root, payload)[1]["sessions"]["cleanup"]
    assert cleanup["forwarder_stopped"] is False
    assert "socket busy" in str(cleanup["forwarder_stop_error"])


def test_cleanup_evidence_uses_this_invocation_only(tmp_path, capsys, monkeypatch):
    # An unrelated concurrently "running" batch root must not affect this batch
    # result and must survive this command untouched.
    unrelated = Path("/tmp") / "r3011-acceptance-cli-unrelated"
    shutil.rmtree(unrelated, ignore_errors=True)
    unrelated.mkdir()
    try:
        run_root, frozen = _write_run_root(tmp_path)
        context = _platform_context()
        forwarder = _ScriptedForwarder([context])
        factory = _RecordingFactory(forwarder)
        handoff = _write_handoff(
            tmp_path,
            frozen,
            _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
        )
        code = _run(tmp_path, run_root, handoff, factory, monkeypatch=monkeypatch)
        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        cleanup = _report(run_root, payload)[1]["sessions"]["cleanup"]
        # No v3 child ran for this zero-hidden batch, so the children list is
        # empty and cleanup is clean: the unrelated root is simply not observed.
        assert cleanup["children"] == []
        assert cleanup["children_destroyed"] is True
        assert unrelated.exists()
    finally:
        shutil.rmtree(unrelated, ignore_errors=True)


def test_the_removed_platform_base_url_option_is_rejected(tmp_path, capsys, monkeypatch):
    run_root, frozen = _write_run_root(tmp_path)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
    )
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
            str(handoff),
            "--platform-base-url",
            "http://127.0.0.1:9999",
        ],
    )
    with pytest.raises(SystemExit) as exited:
        main()
    assert exited.value.code == 2
    assert "platform-base-url" in capsys.readouterr().err


# --- judge evidence: multi-role copies, tampering, interview records ----------


def _stage_sources(run_root: Path, names: tuple[str, ...], content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    manifest = []
    for name in names:
        for role in ("coordinator", "modeling", "competency-question"):
            copy = run_root / "sources" / role / name
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_text(content, encoding="utf-8")
        manifest.append({"path": name, "sha256": digest, "review_content_version": 1})
    (run_root / "source-manifest.json").write_text(
        json.dumps({"schema_version": "r3-0-009-source-manifest/v1", "sources": manifest}),
        encoding="utf-8",
    )
    return digest


def _judge_questions(frozen: dict, overrides: dict[str, list[dict]] | None = None) -> list[dict]:
    hidden = [dict(item) for item in frozen["questions"] if item["visibility"] == "hidden"]
    if overrides:
        for question in hidden:
            question.update(overrides.get(str(question["question_id"]), {}))
    return [
        {
            "question_id": question["question_id"],
            "content_version": question["content_version"],
            "question": question["question"],
            "answer_points": list(question["answer_points"]),
            "evidence_refs": [dict(ref) for ref in question["evidence_refs"]],
            "unknown": list(question["unknown"]),
            "scope": dict(question["scope"]),
        }
        for question in hidden
    ]


def _examiner_report(batch_id: str, question_id: str) -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": batch_id,
        "question_id": question_id,
        "question_content_version": 1,
        "answer": f"answer for {question_id}",
        "evidence_refs": ["resource-1"],
        "explicit_unknown": [],
        "status": "completed",
        "failure_layer": None,
        "reason": None,
    }


def test_a_failed_post_batch_state_read_blocks_the_judge_with_resolvable_evidence(
    tmp_path, capsys, monkeypatch
):
    """The judge never starts on a failed post-batch read, even when the judge
    evidence itself resolves cleanly: the read is runtime evidence, not a
    silent skip (product finding P5)."""
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    _stage_sources(run_root, ("scenario-brief",), "approved scenario bytes\n")
    context = _platform_context()
    # One successful pre-read, then the post-batch re-read fails.
    forwarder = _ScriptedForwarder([context], fail_after=1)
    factory = _RecordingFactory(forwarder)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
    )
    emitted = [_examiner_report(frozen["batch_id"], "cq-1")]

    class _StubAdapter:
        def __init__(self, *, repository_root: Path) -> None:
            self.repository_root = repository_root

        def bind_acceptance_model_profile(self, profile) -> None:
            return None

        def run_v3_acceptance_child(self, packet, *, role_instructions, reports, **kwargs):
            assert packet.role == "platform-examiner", "no judge child may start here"
            reports.extend(dict(report) for report in emitted)
            return list(reports)

    monkeypatch.setattr("modeling_team.__main__.CodexRuntimeAdapter", _StubAdapter)
    code = _run(tmp_path, run_root, handoff, factory, monkeypatch=monkeypatch)
    assert code == 1
    report = _report(run_root, json.loads(capsys.readouterr().out))[1]
    assert [item["question_id"] for item in report["examiner_reports"]] == ["cq-1"]
    stages = [item["stage"] for item in report["sessions"]["lifecycle_errors"]]
    # The judge bundle resolves, so the ONLY bounded failure is the post-read.
    assert stages == ["post-batch-model-state-read"]
    post_read = report["sessions"]["post_batch_model_state_read"]
    assert post_read["failure"]["failure_layer"] == "runtime/infrastructure"
    assert post_read["first_failure"]["failure_layer"] == "runtime/infrastructure"
    judge = report["sessions"]["acceptance_judge"]
    assert "verdicts" not in judge
    assert "skipped" in str(judge["reason"])
    assert report["verdicts"] == []
    assert report["full_pass"] is False


def test_a_canonical_forwarder_runtime_error_at_the_post_read_is_bounded(
    tmp_path, capsys, monkeypatch
):
    """The canonical forwarder signals a failed read with ``ChildRuntimeError``
    (MCP isError decoding), not ``TeamConfigurationError``.  That concrete
    runtime exception must be bounded at the post-batch boundary too: the
    executed reports stay, the judge is skipped, and the batch report is still
    finalized instead of the CLI crashing with no report at all."""
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1"), _question("cq-2")])
    _stage_sources(run_root, ("scenario-brief",), "approved scenario bytes\n")
    context = _platform_context()
    # One successful pre-read, then the post-batch re-read fails exactly the
    # way the real canonical McpReadForwarder fails.
    forwarder = _ScriptedForwarder(
        [context],
        fail_after=1,
        failure=ChildRuntimeError("canonical MCP read tool failed"),
    )
    factory = _RecordingFactory(forwarder)
    handoff = _write_handoff(
        tmp_path,
        frozen,
        _handoff_binding(batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]),
    )
    emitted = [
        _examiner_report(frozen["batch_id"], "cq-1"),
        _examiner_report(frozen["batch_id"], "cq-2"),
    ]

    class _StubAdapter:
        def __init__(self, *, repository_root: Path) -> None:
            self.repository_root = repository_root

        def bind_acceptance_model_profile(self, profile) -> None:
            return None

        def run_v3_acceptance_child(self, packet, *, role_instructions, reports, **kwargs):
            assert packet.role == "platform-examiner", "no judge child may start here"
            reports.extend(dict(report) for report in emitted)
            return list(reports)

    monkeypatch.setattr("modeling_team.__main__.CodexRuntimeAdapter", _StubAdapter)
    code = _run(tmp_path, run_root, handoff, factory, monkeypatch=monkeypatch)
    assert code == 1
    report = _report(run_root, json.loads(capsys.readouterr().out))[1]
    # Both accepted examiner reports survive the failed post-read.
    assert [item["question_id"] for item in report["examiner_reports"]] == ["cq-1", "cq-2"]
    assert report["executed_question_ids"] == ["cq-1", "cq-2"]
    stages = [item["stage"] for item in report["sessions"]["lifecycle_errors"]]
    assert stages == ["post-batch-model-state-read"]
    post_read = report["sessions"]["post_batch_model_state_read"]
    assert "canonical MCP read tool failed" in str(post_read["failure_reason"])
    assert post_read["failure"]["failure_layer"] == "runtime/infrastructure"
    assert post_read["first_failure"]["failure_layer"] == "runtime/infrastructure"
    judge = report["sessions"]["acceptance_judge"]
    assert "verdicts" not in judge
    assert report["verdicts"] == []
    assert report["full_pass"] is False


def test_source_and_interview_bundles_reach_the_actual_judge_packet(tmp_path):
    run_root, frozen = _write_run_root(
        tmp_path,
        [
            _question("cq-src"),
            dict(_question("cq-int"), evidence_refs=[
                {"source": "interview-0001.json", "locator": "answer"}
            ]),
        ],
    )
    _stage_sources(run_root, ("scenario-brief",), "approved scenario bytes\n")
    record = {
        "schema_version": _CQ_INTERVIEW_SCHEMA,
        "interview_id": "interview-0001",
        "text": "recorded business answer for cq-int",
    }
    private = run_root / "competency-questions" / "private"
    private.mkdir(parents=True)
    (private / "interview-0001.json").write_text(json.dumps(record), encoding="utf-8")
    bundle = _cq_build_judge_evidence_bundle(
        run_root, frozen, [dict(item) for item in frozen["questions"]]
    )
    # The raw schema bundle is handed over: no derived digest field, so the
    # packet seam's own strict re-validation passes.
    assert sorted(bundle) == ["batch_id", "entries", "freeze_digest", "schema_version"]
    sources = {entry["source"]: entry for entry in bundle["entries"]}
    assert sources["scenario-brief"]["content"] == "approved scenario bytes\n"
    assert sources["interview-0001.json"]["content"] == json.dumps(record)
    packet = build_acceptance_judge_packet(
        run_id=str(_RUN_CONTRACT["run_id"]),
        batch_id=frozen["batch_id"],
        freeze_digest=frozen["snapshot_digest"],
        questions=_judge_questions(frozen),
        model_binding_digest="sha256:" + "b" * 64,
        evidence_bundle=bundle,
        examiner_reports=[
            _examiner_report(frozen["batch_id"], "cq-src"),
            _examiner_report(frozen["batch_id"], "cq-int"),
        ],
        verdict_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
    )
    assert packet.role == "acceptance"
    assert packet.batch_id == frozen["batch_id"]


def test_identical_multi_role_copies_are_approved_bytes(tmp_path):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    _stage_sources(run_root, ("scenario-brief",), "approved scenario bytes\n")
    bundle = _cq_build_judge_evidence_bundle(
        run_root, frozen, [dict(item) for item in frozen["questions"]]
    )
    assert bundle["entries"] == [
        {
            "question_id": "cq-1",
            "source": "scenario-brief",
            "locator": "section 1",
            "content": "approved scenario bytes\n",
            "content_digest": content_digest("approved scenario bytes\n"),
            "review_content_version": frozen["review_binding"]["review_content_version"],
        }
    ]


def test_a_tampered_role_copy_is_never_repackaged_as_approved(tmp_path):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    _stage_sources(run_root, ("scenario-brief",), "approved scenario bytes\n")
    tampered = run_root / "sources" / "modeling" / "scenario-brief"
    tampered.write_text("modified scenario bytes\n", encoding="utf-8")
    with pytest.raises(Exception) as rejected:
        _cq_build_judge_evidence_bundle(
            run_root, frozen, [dict(item) for item in frozen["questions"]]
        )
    assert "does not match the manifest digest" in str(rejected.value)
    # The manifest digest still names the approved bytes, not the tampered ones.
    assert "modified scenario bytes" not in str(rejected.value)


# --- the v3 prompt surface is dispatched, legacy assets stay untouched --------


def test_v3_prompt_assets_are_mounted_for_both_roles_and_legacy_paths_survive():
    for kind in ("platform", "acceptance"):
        package_file, instructions, skill = CodexRuntimeAdapter._child_package_assets(
            kind, REPO_ROOT, v3_batch=True
        )
        assert package_file.name == "package.yaml"
        assert instructions.parent.name == "v3-acceptance-batch"
        assert skill == (
            REPO_ROOT / "modeling_team" / "skills" / "v3-acceptance-batch" / "SKILL.md"
        )
        text = instructions.read_text(encoding="utf-8")
        assert "packet order" in text
        # The v3 batch has no Source Examiner and no old single-question fields.
        assert "Source Examiner" not in text or "no Source Examiner" in text
        assert "evidence_ref_ids" not in text
        assert "max 3 inferences" not in text.lower()
    # The legacy branches still mount their own untouched assets.
    legacy_platform = CodexRuntimeAdapter._child_package_assets("platform", REPO_ROOT)
    legacy_acceptance = CodexRuntimeAdapter._child_package_assets("acceptance", REPO_ROOT)
    assert legacy_platform[1] == (
        REPO_ROOT / "modeling_team" / "agent-packages" / "platform-examiner" / "instructions.md"
    )
    assert legacy_acceptance[1] == (
        REPO_ROOT / "modeling_team" / "agent-packages" / "acceptance-examiner" / "instructions.md"
    )
    for kind, skill_name in (
        ("source", "source-examiner"),
        ("platform", "platform-examiner"),
        ("acceptance", "lean-acceptance-examiner"),
    ):
        assert CodexRuntimeAdapter._child_package_assets(kind, REPO_ROOT)[2] == (
            REPO_ROOT / "modeling_team" / "skills" / skill_name / "SKILL.md"
        )
