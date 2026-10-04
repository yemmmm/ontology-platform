"""R3.0-016 S2 start/lifecycle/checkpoint operation-layer contract tests.

Covers shared plan §3 groups A (pre-checks and exemption boundary), B
(pause/resume/stop over a real FIFO), C (inspect/save/resume/settle) and the
op-layer parts of D (isolation and credential-leak scanning), plus the
S2-START-007 S1 regression sample and S2-START-009/011 baseline and ledger
exemption evidence on a real prepared run.

Isolation (shared plan §2.1): every test injects ``tmp_path`` through the
op-layer ``repository_root`` parameter, so no real workspace run, platform
or credential is touched.  Envelope, receipt and manifest shapes come from the
real code paths (``submit_fifo_action``, the Runner admission wrapper,
``checkpoints.save_checkpoint``), never from hand-written fixtures.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree

import pytest

from modeling_team import host_ops
from modeling_team.competency_questions import content_digest
from modeling_team.contracts import repository_root
from modeling_team.outer_input import OuterInputFifo
from modeling_team.runner import TeamRunner
from modeling_team.tests.test_r30006_mechanical_increments import _StartAdapter

REPO_ROOT = repository_root()
MULTI_SLICE_PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml"
MULTI_SLICE_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-002-multi-slice-smoke.yaml"
FREEZE = "2026-09-18T08:00:00+00:00"
FABRICATED_FREEZE = "2020-01-01T00:00:00+00:00"
CREDENTIAL = "host-secret-admin-key-do-not-leak"


class _FakeProcess:
    def __init__(self, pid: int = 424242) -> None:
        self.pid = pid
        self.wait_calls = 0

    def wait(self, timeout=None):
        self.wait_calls += 1
        return 0


@pytest.fixture(autouse=True)
def _host_credential(monkeypatch):
    """The host credential channel is present by default (§5.5 pre-check).

    The credential-gate test removes it explicitly for its own assertions.
    """

    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, CREDENTIAL)


def _make_run(tmp_path: Path, run_id: str, *, state: str = "RUNNING", fifo=True):
    """A minimal real run root (state.json + evidence + real FIFO object)."""

    root = tmp_path / "workspaces" / "modeling-runs" / run_id
    (root / "evidence").mkdir(parents=True)
    (root / "control").mkdir(parents=True)
    (root / "state.json").write_text(
        json.dumps({"state": state, "run_id": run_id}), encoding="utf-8"
    )
    handle = OuterInputFifo(root / "control" / "outer-input.fifo") if fifo else None
    if handle is not None:
        handle.open()
    return root, handle


def _ledger(run_root: Path) -> list[dict]:
    path = run_root / "control" / "host-requests.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def _fifo_lines(handle: OuterInputFifo) -> list[dict]:
    lines = []
    while True:
        handle.read_ready()
        line = handle.pop_line()
        if line is None:
            return lines
        lines.append(json.loads(line))


# --- group A: occupancy pre-checks and the exemption boundary ---------------------


def test_existing_run_id_with_a_run_root_reports_the_known_state(tmp_path):
    root, _fifo = _make_run(tmp_path, "s2life", state="PAUSED")
    launcher_calls: list[list[str]] = []

    def launcher(argv, **kwargs):
        launcher_calls.append(argv)
        return _FakeProcess()

    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.start_run(
            run_id="s2life",
            task="modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
            profile="modeling_team/profiles/r3-0-002-modeling-team.yaml",
            model_profile="glm-flash-high",
            scope="modeling_team/scopes/create-scope.yaml",
            freeze_started_at=FREEZE,
            repository_root=tmp_path,
            launcher=launcher,
        )
    error = excinfo.value
    assert error.code == "run_id_already_exists"
    assert error.obj == "run_id"
    assert error.passthrough["existing_run_root"] == "workspaces/modeling-runs/s2life"
    assert error.passthrough["recorded_state"] == "PAUSED"
    assert error.passthrough["query"] == {
        "status": "get_run_status",
        "events": "get_run_events",
    }
    assert launcher_calls == []
    assert root.is_dir()  # the existing run is untouched


def test_live_registration_blocks_a_second_launch(tmp_path):
    # A registration whose process is alive: this test process is alive.
    live_pid = os.getpid()
    launches = tmp_path / "workspaces" / "modeling-runs" / host_ops.HOST_LAUNCHES_DIRECTORY
    launches.mkdir(parents=True)
    (launches / "s2live.json").write_text(
        json.dumps(
            {
                "schema": host_ops.HOST_LAUNCH_RECORD_SCHEMA,
                "run_id": "s2live",
                "pid": live_pid,
                "status": host_ops.HOST_LAUNCH_STATUS_LAUNCHED,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.start_run(
            run_id="s2live",
            task="t.yaml",
            profile="p.yaml",
            model_profile="m",
            scope="s.yaml",
            freeze_started_at=FREEZE,
            repository_root=tmp_path,
            launcher=lambda argv, **kwargs: (_ for _ in ()).throw(AssertionError("no launch")),
        )
    assert excinfo.value.code == "run_launch_in_progress"
    assert excinfo.value.passthrough["observed_pid"] == live_pid


def test_unresolvable_run_id_shapes_are_rejected_before_anything_else(tmp_path):
    for bad in ["", "../escape", "a/b", ".", "..", "a\\b", "x" * 129]:
        with pytest.raises(host_ops.HostOpError) as excinfo:
            host_ops.start_run(
                run_id=bad,
                task="t.yaml",
                profile="p.yaml",
                model_profile="m",
                scope="s.yaml",
                freeze_started_at=FREEZE,
                repository_root=tmp_path,
                launcher=lambda argv, **kwargs: (_ for _ in ()).throw(AssertionError("no launch")),
            )
        assert excinfo.value.code == "run_id_invalid"


def test_op_layer_never_touches_the_start_ledger(tmp_path):
    """S2-START-008 (transparency half): no second hard gate, no rewriting.

    The op layer never reads, reserves or judges the StartLedger: a ledger
    rejection therefore reaches the host verbatim through the run's own
    records, and the tool cannot have turned it into a tool-level code.
    """

    for name in ("start_run", "resume_from_checkpoint", "settle_source_run"):
        function = getattr(host_ops, name)
        source = inspect.getsource(function)
        assert "start_ledger" not in source
        assert ".reserve(" not in source
    import modeling_team.host_ops as module

    s2_section = Path(module.__file__).read_text("utf-8").split("# --- R3.0-016 S2")[-1]
    assert "start_ledger" not in s2_section
    assert "StartLedger" not in s2_section


# --- group A: real prepared run (baseline evidence + exemption boundary) ----------


class _PreparedRun:
    """A real multi-slice (budget-exempt) run, removed afterwards."""

    def __init__(self, tmp_path: Path) -> None:
        self.run_id = (
            f"s2start009-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:10]}"
        )
        self.ledger_root = tmp_path / "ledger"
        self.runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=_StartAdapter(),
            ledger_root=self.ledger_root,
            freeze_started_at=datetime.now(UTC).isoformat(),
        )
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=MULTI_SLICE_PROFILE,
            task_path=MULTI_SLICE_TASK,
            scope={"mode": "create"},
        )
        self.root = REPO_ROOT / "workspaces" / "modeling-runs" / self.run_id

    def cleanup(self) -> None:
        self.runner.cleanup()
        rmtree(self.root, ignore_errors=True)
        rmtree(self.ledger_root, ignore_errors=True)


def test_start_run_baseline_evidence_and_ledger_exemption_boundary(tmp_path):
    """S2-START-009 + S2-START-011 + S2-START-007 (S1 sample) on a real run."""

    from modeling_team.start_ledger import StartLedger

    prepared = _PreparedRun(tmp_path)
    try:
        manifest = json.loads(
            (prepared.root / "baseline-manifest.json").read_text("utf-8")
        )
        reservations = [
            json.loads(line)
            for line in (prepared.root / "evidence" / "start-ledger.jsonl")
            .read_text("utf-8")
            .splitlines()
            if line
        ]
        reservation = next(
            item for item in reservations if item.get("event") == "reservation"
        )
        assert reservation["baseline_hash"] == StartLedger.baseline_hash(manifest)
        # The exempt (multi-slice) run has no global ledger record at all and
        # its run-internal reservation carries no ledger identity or freeze
        # timepoint -- so a wrong timepoint leaves no detectable trace.
        global_ledgers = list((REPO_ROOT / "workspaces" / "modeling-runs").glob(".*-start-ledger.jsonl"))
        for ledger_path in global_ledgers:
            assert prepared.run_id not in ledger_path.read_text("utf-8")
        assert "ledger_identity" not in reservation
        assert "freeze_started_at" not in reservation
        assert reservation["baseline_hash"]

        # The returned references locate exactly these two artifacts.
        result = host_ops.start_run(
            run_id=f"{prepared.run_id}-ref",
            task="modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
            profile="modeling_team/profiles/r3-0-002-modeling-team.yaml",
            model_profile="glm-flash-high",
            scope="modeling_team/scopes/create-scope.yaml",
            freeze_started_at=FABRICATED_FREEZE,
            repository_root=tmp_path,
            launcher=lambda argv, **kwargs: _FakeProcess(),
            run_root_wait_seconds=0.05,
        )
        assert "baseline-manifest.json" in result["baseline_evidence"]["manifest"]
        assert result["baseline_evidence"]["manifest"].startswith(
            f"workspaces/modeling-runs/{prepared.run_id}-ref"
        )
        assert "start-ledger.jsonl" in result["baseline_evidence"]["hash_ref"]
        assert "baseline_hash" in result["baseline_evidence"]["hash_ref"]
        # A fabricated but well-formed timepoint is accepted verbatim: no
        # rewrite, no fill-in, and no claim that the platform validated it.
        assert result["launch_record"]["argv"][
            result["launch_record"]["argv"].index("--freeze-started-at") + 1
        ] == FABRICATED_FREEZE
        assert "semantic start" in result["note"]
        # No return field claims a platform-side freeze-timepoint or budget check.
        assert not any("validated" in key or "gate" in key for key in result)
        assert "never proves a semantic start" in result["semantic_start_evidence"]

        # S2-START-007: the unchanged S1 read surface still serves this run.
        status = host_ops.get_run_status(prepared.run_id)
        assert status["run_id"] == prepared.run_id
        assert status["recorded_state"]["state"]
        events = host_ops.get_run_events(prepared.run_id, limit=5)
        assert events["events"]
        pending = host_ops.pending_items(prepared.root)
        assert isinstance(pending[0], list)
    finally:
        prepared.cleanup()


# --- group B: pause / resume / stop over the real FIFO ----------------------------


def test_three_lifecycle_actions_submit_and_correlate(tmp_path):
    root, fifo = _make_run(tmp_path, "s2lifecycle")
    try:
        paused = host_ops.pause_run("s2lifecycle", request_id="req-pause-1", repository_root=tmp_path)
        assert {
            key: paused[key]
            for key in (
                "run_id",
                "request_id",
                "action",
                "status",
                "consumption_evidence",
                "next_action",
            )
        } == {
            "run_id": "s2lifecycle",
            "request_id": "req-pause-1",
            "action": "pause",
            "status": "submitted",
            "consumption_evidence": "state.json",
            "next_action": "get_request_result",
        }
        assert paused["note"]
        resumed = host_ops.resume_live_run("s2lifecycle", request_id="req-resume-1", repository_root=tmp_path)
        stopped = host_ops.stop_run(
            "s2lifecycle", reason="host stop drill", request_id="req-stop-1", repository_root=tmp_path
        )
        assert resumed["status"] == "submitted"
        assert stopped["status"] == "submitted"
        assert stopped["consumption_evidence"] == "state.json"

        entries = _ledger(root)
        assert [entry["action"] for entry in entries] == ["pause", "resume", "stop"]
        assert [entry["request_id"] for entry in entries] == [
            "req-pause-1",
            "req-resume-1",
            "req-stop-1",
        ]
        lines = _fifo_lines(fifo)
        assert lines == [
            {"action": "pause", "request_id": "req-pause-1"},
            {"action": "resume", "request_id": "req-resume-1"},
            {"action": "stop", "reason": "host stop drill", "request_id": "req-stop-1"},
        ]
        # The submission digest is over the envelope exactly as the Runner
        # computes it after the request_id pop.
        assert entries[0]["content_digest"] == content_digest({"action": "pause"})
        assert entries[2]["content_digest"] == content_digest(
            {"action": "stop", "reason": "host stop drill"}
        )

        outcome = host_ops.get_request_result(
            "s2lifecycle", request_id="req-pause-1", repository_root=tmp_path
        )
        assert outcome["outcome"] == "submitted"
    finally:
        fifo.close()


def test_terminal_run_rejects_lifecycle_and_resume_names_its_limit(tmp_path):
    root, fifo = _make_run(tmp_path, "s2terminal", state="CLEANED")
    try:
        for action in (host_ops.pause_run, host_ops.stop_run):
            with pytest.raises(host_ops.HostOpError) as excinfo:
                action("s2terminal", repository_root=tmp_path)
            assert excinfo.value.code == "outer_input_channel_unavailable"
            assert excinfo.value.retryable is False
        with pytest.raises(host_ops.HostOpError) as excinfo:
            host_ops.resume_live_run("s2terminal", repository_root=tmp_path)
        error = excinfo.value
        assert error.code == "outer_input_channel_unavailable"
        assert "resume_from_checkpoint" in error.next_action
        assert _ledger(root) == [] and _fifo_lines(fifo) == []
    finally:
        fifo.close()


def test_fifo_boundaries_keep_the_s1_codes(tmp_path):
    root_without_fifo, _none = _make_run(tmp_path, "s2nofifo", fifo=False)
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.pause_run("s2nofifo", repository_root=tmp_path)
    assert excinfo.value.code == "outer_input_channel_unavailable"

    root, fifo = _make_run(tmp_path, "s2huge")
    try:
        with pytest.raises(host_ops.HostOpError) as excinfo:
            host_ops.stop_run(
                "s2huge",
                reason="x" * (host_ops.FIFO_MAX_LINE_BYTES + 10),
                repository_root=tmp_path,
            )
        assert excinfo.value.code == "fifo_line_too_large"
        assert _ledger(root) == [] and _fifo_lines(fifo) == []
    finally:
        fifo.close()


def test_request_id_conflict_and_replay(tmp_path):
    root, fifo = _make_run(tmp_path, "s2idem")
    try:
        first = host_ops.stop_run(
            "s2idem", reason="first", request_id="req-stop-dup", repository_root=tmp_path
        )
        assert first["status"] == "submitted"
        with pytest.raises(host_ops.HostOpError) as excinfo:
            host_ops.stop_run(
                "s2idem", reason="second", request_id="req-stop-dup", repository_root=tmp_path
            )
        assert excinfo.value.code == "request_id_conflict"
        replay = host_ops.stop_run(
            "s2idem", reason="first", request_id="req-stop-dup", repository_root=tmp_path
        )
        assert replay["status"] == "submitted"
        assert replay["idempotent"] is True
        assert replay["note"]
        assert len(_ledger(root)) == 1
        assert len(_fifo_lines(fifo)) == 1
    finally:
        fifo.close()


def test_stop_reason_only_travels_in_the_envelope(tmp_path):
    """S2-LIFE-006 (half): the Runner stop branch does not read ``reason``."""

    runner_source = (REPO_ROOT / "modeling_team" / "runner.py").read_text("utf-8")
    start = runner_source.index('action == "stop"')
    branch = runner_source[start : start + 3000]
    assert 'message.get("reason")' not in branch
    assert '"reason"' not in branch


# --- group C: inspect / save / resume / settle ------------------------------------


def test_inspect_checkpoints_is_read_only_and_passes_through_codes(tmp_path):
    root, _fifo = _make_run(tmp_path, "s2inspect", fifo=False)

    def tree_digest() -> str:
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            digest.update(str(path.relative_to(root)).encode())
            if path.is_file():
                digest.update(path.read_bytes())
        return digest.hexdigest()

    before = tree_digest()
    result = host_ops.inspect_checkpoints("s2inspect", repository_root=tmp_path)
    assert result["read_only"] is True
    assert result["run_id"] == "s2inspect"
    assert result["published_count"] == 0
    assert result["checkpoints"] == []
    assert result["resume"]["modes"]["production"]["semantic_starts"] == 1
    assert result["resume"]["modes"]["acceptance"]["semantic_starts"] == 0
    assert tree_digest() == before

    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.inspect_checkpoints(
            "s2inspect", checkpoint_id="does-not-exist", repository_root=tmp_path
        )
    assert excinfo.value.code == "checkpoint_not_found"
    assert excinfo.value.next_action
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.inspect_checkpoints("missing-run", repository_root=tmp_path)
    assert excinfo.value.code == "run_not_found"


def test_save_checkpoint_envelope_and_single_request_id(tmp_path):
    root, fifo = _make_run(tmp_path, "s2save")
    try:
        result = host_ops.save_checkpoint(
            "s2save",
            kind="materialization_progress",
            scope_refs={"slice_id": "slice-0001"},
            request_id="req-save-1",
            repository_root=tmp_path,
        )
        assert result["action"] == "checkpoint"
        assert result["status"] == "submitted"
        assert result["request_id"] == "req-save-1"
        assert result["consumption_evidence"] == "evidence/checkpoints.jsonl"
        assert result["next_action"] == "get_request_result"
        (entry,) = _ledger(root)
        assert entry["content_digest"] == content_digest(
            {
                "action": "checkpoint",
                "command": "save",
                "kind": "materialization_progress",
                "scope_refs": {"slice_id": "slice-0001"},
            }
        )
        (line,) = _fifo_lines(fifo)
        # The same single id travels on the wire for the Runner receipt and the
        # 015 manifest provenance.
        assert line["request_id"] == "req-save-1"
        assert line["command"] == "save"

        # A replayed id with the same content is intercepted before a second
        # save can be produced.
        replay = host_ops.save_checkpoint(
            "s2save",
            kind="materialization_progress",
            scope_refs={"slice_id": "slice-0001"},
            request_id="req-save-1",
            repository_root=tmp_path,
        )
        assert replay["idempotent"] is True
        assert _fifo_lines(fifo) == []  # no second line was written
    finally:
        fifo.close()


def test_save_checkpoint_rejects_non_save_commands_before_the_fifo(tmp_path):
    root, fifo = _make_run(tmp_path, "s2savecmd")
    try:
        with pytest.raises(host_ops.HostOpError) as excinfo:
            host_ops.save_checkpoint(
                "s2savecmd", kind="materialization_progress", command="inspect",
                repository_root=tmp_path,
            )
        assert excinfo.value.code == "launch_arguments_invalid"
        assert "inspect_checkpoints" in excinfo.value.next_action
        assert _ledger(root) == [] and _fifo_lines(fifo) == []
    finally:
        fifo.close()


def test_checkpoint_envelope_reaches_the_runner_with_the_original_contract(tmp_path):
    """The Runner-side validation stays authoritative: the envelope is exactly
    what ``_handle_checkpoint_outer`` reads, so its original codes come back."""

    runner_source = (REPO_ROOT / "modeling_team" / "runner.py").read_text("utf-8")
    for key in ('message.get("command")', 'message.get("kind")', 'message.get("scope_refs")'):
        assert key in runner_source


def test_resume_argv_is_exactly_the_real_checkpoint_resume_contract(tmp_path):
    source_run, _fifo = _make_run(tmp_path, "s2source", state="CLEANED")
    argvs: list[list[str]] = []

    def launcher(argv, **kwargs):
        argvs.append(list(argv))
        return _FakeProcess(525252)

    result = host_ops.resume_from_checkpoint(
        source_run_id="s2source",
        checkpoint_id="materialization_progress-0001",
        new_run_id="s2resume1",
        mode="production",
        authorization_reference="auth-r3018-s2/resume (user-approved 2026-09-18T09:00:00+00:00)",
        freeze_started_at="2026-09-18T09:30:00+00:00",
        repository_root=tmp_path,
        launcher=launcher,
        run_root_wait_seconds=0.05,
    )
    assert argvs == [
        [
            sys.executable,
            "-m",
            "modeling_team",
            "checkpoint",
            "resume",
            "--run-id",
            "s2source",
            "--checkpoint-id",
            "materialization_progress-0001",
            "--new-run-id",
            "s2resume1",
            "--mode",
            "production",
            "--authorization-reference",
            "auth-r3018-s2/resume (user-approved 2026-09-18T09:00:00+00:00)",
            "--freeze-started-at",
            "2026-09-18T09:30:00+00:00",
            "--enable-outer-input-fifo",
        ]
    ]
    assert "--source-run" not in argvs[0]
    assert set(argvs[0]) <= set(host_ops.CHECKPOINT_RESUME_FLAGS) | {
        sys.executable,
        "-m",
        "modeling_team",
        "checkpoint",
        "resume",
        "s2source",
        "materialization_progress-0001",
        "s2resume1",
        "production",
        "auth-r3018-s2/resume (user-approved 2026-09-18T09:00:00+00:00)",
        "2026-09-18T09:30:00+00:00",
    }
    assert result["run_id"] == "s2resume1"
    assert result["source_run_id"] == "s2source"
    assert result["checkpoint_id"] == "materialization_progress-0001"
    assert result["mode"] == "production"
    assert result["launch_record"]["kind"] == "checkpoint_resume"
    assert result["pid"] == 525252
    assert "1 semantic start" in result["semantic_starts_note"]
    # The source run was never written to.
    assert sorted(path.name for path in source_run.iterdir()) == ["control", "evidence", "state.json"]

    acceptance = host_ops.resume_from_checkpoint(
        source_run_id="s2source",
        checkpoint_id="materialization_progress-0001",
        new_run_id="s2resume2",
        mode="acceptance",
        authorization_reference="auth-r3018-s2/acceptance (user-approved 2026-09-18T09:00:00+00:00)",
        session_timeout=120,
        question_visibility="public",
        model_profile="openai-sol-medium",
        repository_root=tmp_path,
        launcher=launcher,
        run_root_wait_seconds=0.05,
    )
    assert acceptance["mode"] == "acceptance"
    assert "--freeze-started-at" not in argvs[1]
    assert argvs[1][argvs[1].index("--session-timeout") + 1] == "120"
    assert argvs[1][argvs[1].index("--model-profile") + 1] == "openai-sol-medium"
    assert argvs[1][argvs[1].index("--question-visibility") + 1] == "public"
    assert "--question-visibility" not in argvs[0]
    assert "consumes 0" in acceptance["semantic_starts_note"]
    assert "015" in acceptance["semantic_starts_note"]


@pytest.mark.parametrize("model_profile", ["", "--unexpected", "profile name", 7])
def test_resume_model_profile_rejects_invalid_argv_values_before_launch(tmp_path, model_profile):
    _make_run(tmp_path, "sourceprofile", state="CLEANED")
    calls = []
    with pytest.raises(host_ops.HostOpError) as rejected:
        host_ops.resume_from_checkpoint(
            source_run_id="sourceprofile", checkpoint_id="production_handoff-0001",
            new_run_id="newprofile", mode="acceptance", authorization_reference="auth-test",
            model_profile=model_profile, repository_root=tmp_path,
            launcher=lambda *args, **kwargs: calls.append(args),
        )
    assert rejected.value.code == "launch_arguments_invalid"
    assert calls == []


def test_resume_mode_and_freeze_rules_are_pre_checked(tmp_path):
    _root, _fifo = _make_run(tmp_path, "s2sourcerules", state="CLEANED")
    calls: list = []

    def launcher(argv, **kwargs):
        calls.append(argv)
        return _FakeProcess()

    common = {
        "source_run_id": "s2sourcerules",
        "checkpoint_id": "materialization_progress-0001",
        "authorization_reference": "auth-x/resume (user-approved t)",
        "repository_root": tmp_path,
        "launcher": launcher,
    }
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.resume_from_checkpoint(
            new_run_id="s2resprod", mode="production", **common
        )
    assert excinfo.value.code == "launch_arguments_invalid"
    assert excinfo.value.obj == "freeze_started_at"
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.resume_from_checkpoint(
            new_run_id="s2resacc",
            mode="acceptance",
            freeze_started_at=FREEZE,
            **common,
        )
    assert excinfo.value.code == "launch_arguments_invalid"
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.resume_from_checkpoint(
            new_run_id="s2resbad",
            mode="production",
            freeze_started_at="2026-09-18T09:30:00",
            **common,
        )
    assert excinfo.value.code == "freeze_started_at_invalid"
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.resume_from_checkpoint(
            new_run_id="s2resmode", mode="rollback", **common
        )
    assert excinfo.value.code == "launch_arguments_invalid"
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.resume_from_checkpoint(
            new_run_id="s2resckpt",
            mode="acceptance",
            checkpoint_id="   ",
            **{key: value for key, value in common.items() if key != "checkpoint_id"},
        )
    assert excinfo.value.code == "checkpoint_id_required"
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.resume_from_checkpoint(
            source_run_id="s2sourcerules",
            new_run_id="s2resauth",
            mode="acceptance",
            checkpoint_id="materialization_progress-0001",
            authorization_reference="   ",
            repository_root=tmp_path,
            launcher=launcher,
        )
    assert excinfo.value.code == "launch_arguments_invalid"
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.resume_from_checkpoint(
            new_run_id="../escape", mode="acceptance", **common
        )
    assert excinfo.value.code == "run_id_invalid"
    assert calls == []


def test_resume_of_an_occupied_new_run_id_never_starts(tmp_path):
    _root, _fifo = _make_run(tmp_path, "s2srcocc", state="CLEANED")
    _occupied, _occupied_fifo = _make_run(tmp_path, "s2newocc")

    def launcher(argv, **kwargs):
        raise AssertionError("no launch may happen")

    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.resume_from_checkpoint(
            source_run_id="s2srcocc",
            checkpoint_id="materialization_progress-0001",
            new_run_id="s2newocc",
            mode="acceptance",
            authorization_reference="auth-x/resume (user-approved t)",
            repository_root=tmp_path,
            launcher=launcher,
        )
    assert excinfo.value.code == "run_id_already_exists"


def test_credential_gate_runs_first_and_never_leaks(tmp_path, monkeypatch):
    _root, _fifo = _make_run(tmp_path, "s2credsrc", state="CLEANED")
    monkeypatch.delenv(host_ops.HOST_CREDENTIAL_ENV, raising=False)
    settle_calls: list = []

    def launcher(argv, **kwargs):
        raise AssertionError("no subprocess without credentials")

    def fake_settle(**kwargs):
        settle_calls.append(kwargs)
        raise AssertionError("settle must not be called without credentials")

    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.resume_from_checkpoint(
            source_run_id="s2credsrc",
            checkpoint_id="materialization_progress-0001",
            new_run_id="s2credres",
            mode="acceptance",
            authorization_reference="auth-x/resume (user-approved t)",
            repository_root=tmp_path,
            launcher=launcher,
        )
    assert excinfo.value.code == "host_credential_missing"
    assert excinfo.value.retryable is True
    assert CREDENTIAL not in json.dumps(excinfo.value.as_envelope())

    monkeypatch.setattr(host_ops, "settle_source_run_record", fake_settle)
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.settle_source_run(
            "s2credsrc",
            stop_reference="stop-1",
            repository_root=tmp_path,
        )
    assert excinfo.value.code == "host_credential_missing"
    assert settle_calls == []
    assert not (tmp_path / "workspaces" / "modeling-runs" / "s2credres").exists()

    # With the credential present nothing leaks into records, logs or errors.
    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, CREDENTIAL)
    result = host_ops.resume_from_checkpoint(
        source_run_id="s2credsrc",
        checkpoint_id="materialization_progress-0001",
        new_run_id="s2credres",
        mode="acceptance",
        authorization_reference="auth-x/resume (user-approved t)",
        repository_root=tmp_path,
        launcher=lambda argv, **kwargs: _FakeProcess(),
        run_root_wait_seconds=0.05,
    )
    launches = tmp_path / "workspaces" / "modeling-runs" / host_ops.HOST_LAUNCHES_DIRECTORY
    observed = json.dumps(result) + "".join(
        path.read_text("utf-8", errors="replace") for path in launches.iterdir()
    )
    assert CREDENTIAL not in observed
    assert CREDENTIAL not in result["launch_record"]["argv_note"]


def test_settle_uses_the_real_function_with_the_real_readback(tmp_path, monkeypatch):
    _root, _fifo = _make_run(tmp_path, "s2settlesrc", state="CLEANED")
    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, CREDENTIAL)
    seen: dict = {}
    sentinel = object()

    monkeypatch.setattr(
        host_ops,
        "http_readback",
        lambda base_url, key: sentinel if key == CREDENTIAL else None,
    )

    def fake_settle(*, run_root, stop_reference, readback):
        seen["run_root"] = run_root
        seen["stop_reference"] = stop_reference
        seen["readback"] = readback
        return {"source_run_id": run_root.name, "status": "settled"}

    monkeypatch.setattr(host_ops, "settle_source_run_record", fake_settle)
    result = host_ops.settle_source_run(
        "s2settlesrc",
        stop_reference="stop-ref-1",
        base_url="http://127.0.0.1:8001",
        request_id="req-settle-1",
        repository_root=tmp_path,
    )
    assert seen["run_root"] == tmp_path / "workspaces" / "modeling-runs" / "s2settlesrc"
    assert seen["stop_reference"] == "stop-ref-1"
    assert seen["readback"] is sentinel  # never a stub readback
    assert result["source_run_id"] == "s2settlesrc"
    assert result["settled"] is True
    assert result["settlement_record"]["status"] == "settled"
    assert result["settlement_record_ref"].endswith(
        ".recovery-settlements/s2settlesrc.json"
    )


def test_settle_refusals_keep_the_original_typed_codes(tmp_path, monkeypatch):
    root, _fifo = _make_run(tmp_path, "s2settleref", state="CLEANED")
    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, CREDENTIAL)
    monkeypatch.setattr(
        host_ops,
        "http_readback",
        lambda base_url, key: None,
    )

    from modeling_team.checkpoints import CheckpointError

    def refusing_settle(**kwargs):
        raise CheckpointError(
            "source_possibly_live",
            "the recorded state CLEANED is outside the settle-allowed states",
            obj="state",
            retryable=False,
            retry="record the real controlled stop first",
        )

    monkeypatch.setattr(host_ops, "settle_source_run_record", refusing_settle)
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.settle_source_run(
            "s2settleref", stop_reference="stop-ref-2", repository_root=tmp_path
        )
    assert excinfo.value.code == "source_possibly_live"
    assert excinfo.value.next_action.startswith("record the real controlled stop")
    assert not (root / ".recovery-settlements").exists()
    # The settlement record path is shared with the CLI; nothing else is added.
    assert not (tmp_path / "workspaces" / "modeling-runs" / ".recovery-settlements").exists()


# --- group D: credential-free records and launch arguments ------------------------


def test_launch_records_and_logs_never_carry_a_credential(tmp_path, monkeypatch):
    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, CREDENTIAL)
    host_ops.start_run(
        run_id="s2leak",
        task="modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
        profile="modeling_team/profiles/r3-0-002-modeling-team.yaml",
        model_profile="glm-flash-high",
        scope="modeling_team/scopes/create-scope.yaml",
        freeze_started_at=FREEZE,
        base_url="http://127.0.0.1:8001",
        repository_root=tmp_path,
        launcher=lambda argv, **kwargs: _FakeProcess(),
        run_root_wait_seconds=0.05,
    )
    launches = tmp_path / "workspaces" / "modeling-runs" / host_ops.HOST_LAUNCHES_DIRECTORY
    for path in launches.iterdir():
        assert CREDENTIAL not in path.read_text("utf-8", errors="replace")
    record = host_ops.read_launch_record("s2leak", repository_root=tmp_path)
    assert record["argv_note"]
    assert "ONTOLOGY_PLATFORM_ADMIN_API_KEY" not in json.dumps(record)
    # The credential is not a CLI parameter of the encapsulated command.
    assert not any(CREDENTIAL in item for item in record["argv"])


def test_lifecycle_and_checkpoint_consumption_evidence_is_declared():
    assert host_ops.LIFECYCLE_CONSUMPTION_EVIDENCE == {
        "pause": "state.json",
        "resume": "state.json",
        "stop": "state.json",
        "checkpoint": "evidence/checkpoints.jsonl",
    }
    assert set(host_ops.RUN_SUBCOMMAND_FLAGS) == {
        "--profile",
        "--task",
        "--task-overlay",
        "--model-profile",
        "--run-id",
        "--scope",
        "--base-url",
        "--freeze-started-at",
        "--enable-outer-input-fifo",
    }
    assert set(host_ops.CHECKPOINT_RESUME_FLAGS) == {
        "--run-id",
        "--checkpoint-id",
        "--new-run-id",
        "--mode",
        "--session-timeout",
        "--model-profile",
        "--question-visibility",
        "--authorization-reference",
        "--base-url",
        "--freeze-started-at",
        "--enable-outer-input-fifo",
    }


def test_real_cli_flags_back_the_declared_flag_sets():
    """The declared flag sets are the CLI's real parameters, not inventions."""

    import subprocess
    import sys

    def flags_of(argv: list[str]) -> set[str]:
        text = subprocess.run(
            [sys.executable, "-m", "modeling_team", *argv, "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return {
            token
            for token in text.replace("\n", " ").split()
            if token.startswith("--")
        }

    run_flags = flags_of(["run"])
    assert set(host_ops.RUN_SUBCOMMAND_FLAGS) <= run_flags
    assert not {"--authorization-reference", "--session-timeout"} & run_flags
    resume_flags = flags_of(["checkpoint", "resume"])
    assert set(host_ops.CHECKPOINT_RESUME_FLAGS) <= resume_flags
    assert "--source-run" not in resume_flags


@pytest.mark.parametrize("visibility", ["", "all", "--unexpected", None, []])
def test_resume_question_visibility_rejects_invalid_values_before_launch(tmp_path, visibility):
    _make_run(tmp_path, "sourceselection", state="CLEANED")
    calls = []
    with pytest.raises(host_ops.HostOpError) as rejected:
        host_ops.resume_from_checkpoint(
            source_run_id="sourceselection", checkpoint_id="production_handoff-0001",
            new_run_id="newselection", mode="acceptance", authorization_reference="auth-test",
            question_visibility=visibility, repository_root=tmp_path,
            launcher=lambda *args, **kwargs: calls.append(args),
        )
    assert rejected.value.code == "launch_arguments_invalid"
    assert calls == []
