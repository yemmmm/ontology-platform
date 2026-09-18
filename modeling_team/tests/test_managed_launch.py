"""R3.0-016 S2 managed-launch contract tests (shared plan §2.4, §3 group A).

Every launch here uses the injected fake launcher (recorded argv, controllable
pid and exit) so no modeling run is started; the single real-subprocess case at
the end launches ``python -m modeling_team --help``, which exits immediately and
proves only that the managed launch can raise the real CLI.

Isolation (shared plan §2.1): each test injects its own ``tmp_path`` through the
op-layer ``repository_root`` parameter, so ``workspaces/modeling-runs`` and the
``.host-launches`` registrations live inside the test's temporary repository.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from modeling_team import host_ops
from modeling_team.contracts import repository_root

REPO_ROOT = repository_root()
FREEZE = "2026-09-18T08:00:00+00:00"


class _FakeProcess:
    """A Popen stand-in whose exit the test controls."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode = None
        self._exited = threading.Event()
        self.wait_calls = 0

    def wait(self, timeout=None):
        self.wait_calls += 1
        self._exited.wait()
        return self.returncode

    def exit(self, code: int) -> None:
        self.returncode = code
        self._exited.set()


class _Launcher:
    """Records the launch call and optionally materialises the run root."""

    def __init__(self, *, pid: int = 424242, prepare_root: bool = True, fail=False):
        self.pid = pid
        self.prepare_root = prepare_root
        self.fail = fail
        self.calls: list[dict] = []
        self.processes: list[_FakeProcess] = []

    def __call__(self, argv, *, cwd, env, stdout, stderr):
        self.calls.append(
            {
                "argv": list(argv),
                "cwd": cwd,
                "env": env,
                "stdout": stdout,
                "stderr": stderr,
            }
        )
        if self.fail:
            raise OSError(13, "Permission denied")
        if self.prepare_root:
            run_id = argv[argv.index("--run-id") + 1]
            root = Path(cwd) / "workspaces" / "modeling-runs" / run_id
            (root / "control").mkdir(parents=True, exist_ok=True)
            (root / "state.json").write_text(
                json.dumps({"state": "PREPARING", "run_id": run_id}), encoding="utf-8"
            )
        process = _FakeProcess(self.pid)
        self.processes.append(process)
        return process


def _start(tmp_path: Path, run_id: str, launcher, **kwargs) -> dict:
    kwargs.setdefault("run_root_wait_seconds", 2.0)
    return host_ops.start_run(
        run_id=run_id,
        task="modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
        profile="modeling_team/profiles/r3-0-002-modeling-team.yaml",
        model_profile="modeling_team/model-profiles/glm-flash-high.yaml",
        scope="modeling_team/scopes/create-scope.yaml",
        freeze_started_at=FREEZE,
        repository_root=tmp_path,
        launcher=launcher,
        **kwargs,
    )


def _launches(tmp_path: Path) -> Path:
    return tmp_path / "workspaces" / "modeling-runs" / host_ops.HOST_LAUNCHES_DIRECTORY


def test_start_run_uses_exactly_the_real_run_subcommand_flags(tmp_path):
    launcher = _Launcher()
    result = _start(tmp_path, "s2start001", launcher, request_id="req-start-1")

    (call,) = launcher.calls
    argv = call["argv"]
    assert argv[:4] == [sys.executable, "-m", "modeling_team", "run"]
    # Exactly the real ``run`` subcommand parameters, in name order, and none of
    # the phantom ones (no authorization-reference / session-timeout / baseline).
    assert argv[4::2] == [
        "--profile",
        "--task",
        "--model-profile",
        "--run-id",
        "--scope",
        "--freeze-started-at",
        "--enable-outer-input-fifo",
    ]
    assert set(argv[4::2]) <= set(host_ops.RUN_SUBCOMMAND_FLAGS)
    values = dict(zip(argv[4:-1:2], argv[5::2]))
    assert values["--run-id"] == "s2start001"
    assert values["--freeze-started-at"] == FREEZE  # verbatim, never rewritten
    assert argv[-1] == "--enable-outer-input-fifo"
    assert not {"--authorization-reference", "--session-timeout", "--baseline-ref"} & set(argv)

    # The launch is detached against the injected repository, with the host
    # environment inherited (the credential channel) and no shell involved.
    assert call["cwd"] == str(tmp_path.resolve())
    assert isinstance(call["env"], dict) and call["env"].get("PATH")

    record = host_ops.read_launch_record("s2start001", repository_root=tmp_path)
    assert record["schema"] == host_ops.HOST_LAUNCH_RECORD_SCHEMA
    assert record["run_id"] == "s2start001"
    assert record["kind"] == "run"
    assert record["argv"] == argv
    assert record["pid"] == 424242
    assert record["status"] == host_ops.HOST_LAUNCH_STATUS_LAUNCHED
    assert record["request_id"] == "req-start-1"
    assert set(record["log_paths"]) == {"stdout", "stderr"}
    for relative in record["log_paths"].values():
        assert (_launches(tmp_path) / Path(relative).name).is_file()

    # The credential never travels in argv or in the registration.
    assert "ONTOLOGY_PLATFORM_ADMIN_API_KEY" not in json.dumps(record)

    assert result["launched"] is True
    assert result["run_id"] == "s2start001"
    assert result["pid"] == 424242
    assert result["supervisor_ref"] == "control/host-supervisor.json"
    assert result["launch_record"]["pid"] == 424242
    assert result["observation_limitation"] is None
    assert result["query"] == {
        "status": "get_run_status",
        "events": "get_run_events",
    }
    assert result["note"] == "launch accepted ≠ semantic start happened"
    assert "evidence/semantic-start.jsonl" in result["semantic_start_evidence"]
    assert (
        "baseline-manifest.json" in result["baseline_evidence"]["manifest"]
        and "baseline_hash" in result["baseline_evidence"]["hash_ref"]
    )
    # The process observation stays readable by the unchanged S1 supervisor path.
    supervisor = json.loads(
        (tmp_path / "workspaces/modeling-runs/s2start001/control/host-supervisor.json")
        .read_text(encoding="utf-8")
    )
    assert supervisor["schema"] == host_ops.HOST_SUPERVISOR_SCHEMA
    assert supervisor["pid"] == 424242
    assert supervisor["started_at"]


def test_start_run_without_a_run_root_reports_the_observation_limit(tmp_path):
    launcher = _Launcher(prepare_root=False)
    result = _start(tmp_path, "s2start002", launcher, run_root_wait_seconds=0.05)

    assert result["launched"] is True
    assert result["pid"] == 424242
    assert "supervisor_ref" not in result
    assert result["observation_limitation"]
    assert "unknown" in result["observation_limitation"]
    assert not (tmp_path / "workspaces/modeling-runs/s2start002").exists()


def test_slow_prepare_beyond_the_window_is_not_a_failure(tmp_path):
    """A run root appearing after the bounded window must not block or fail."""

    release = threading.Event()
    prepared = threading.Event()

    class _SlowLauncher(_Launcher):
        def __call__(self, argv, *, cwd, env, stdout, stderr):
            self.calls.append({"argv": list(argv), "cwd": cwd})
            process = _FakeProcess(424244)
            self.processes.append(process)

            def late_prepare():
                release.wait(5)
                run_id = argv[argv.index("--run-id") + 1]
                root = Path(cwd) / "workspaces" / "modeling-runs" / run_id
                (root / "control").mkdir(parents=True, exist_ok=True)
                prepared.set()

            threading.Thread(target=late_prepare, daemon=True).start()
            return process

    result = _start(tmp_path, "s2start002b", _SlowLauncher(), run_root_wait_seconds=0.05)
    assert result["launched"] is True
    assert result["pid"] == 424244
    assert "supervisor_ref" not in result
    assert "unknown" in result["observation_limitation"]
    # The tool returned before the run root existed; nothing was reported failed.
    assert not (tmp_path / "workspaces" / "modeling-runs" / "s2start002b").exists()
    release.set()
    assert prepared.wait(5)


def test_crash_before_prepare_leaves_registration_and_run_not_found(tmp_path):
    launcher = _Launcher(prepare_root=False)
    _start(tmp_path, "s2start003", launcher)

    record_path = _launches(tmp_path) / "s2start003.json"
    assert record_path.is_file()
    assert (_launches(tmp_path) / "s2start003.out.log").is_file()
    assert (_launches(tmp_path) / "s2start003.err.log").is_file()

    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.get_run_status("s2start003", repository_root=tmp_path)
    assert excinfo.value.code == "run_not_found"
    # The registration is evidence, never cleaned up by the tool.
    assert record_path.is_file()


def test_start_run_reports_a_dead_registration_instead_of_reusing_it(tmp_path):
    launcher = _Launcher(prepare_root=False)
    _start(tmp_path, "s2start005c", launcher)
    record_path = _launches(tmp_path) / "s2start005c.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    # Replace the recorded pid with one that is provably not alive.
    dead = next(
        candidate
        for candidate in range(4_000_000, 4_010_000)
        if host_ops.pid_is_alive(candidate) is False
    )
    record["pid"] = dead
    record_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(host_ops.HostOpError) as excinfo:
        _start(tmp_path, "s2start005c", _Launcher())
    error = excinfo.value
    assert error.code == "run_launch_failed"
    assert error.passthrough["launch_record"]["run_id"] == "s2start005c"
    assert error.passthrough["log_paths"]["stdout"].endswith("s2start005c.out.log")
    assert "manually" in error.next_action
    # A dead registration is never deleted implicitly.
    assert record_path.is_file()


def test_start_run_registration_write_failure_is_typed(tmp_path):
    launcher = _Launcher()
    # A file where the registration directory must be created fails the mkdir.
    (tmp_path / "workspaces").mkdir(parents=True)
    (tmp_path / "workspaces" / "modeling-runs").write_text("not a directory", "utf-8")
    with pytest.raises(host_ops.HostOpError) as excinfo:
        _start(tmp_path, "s2startregfail", launcher)
    assert excinfo.value.code == "run_launch_failed"
    assert launcher.calls == []


def test_subprocess_failure_keeps_the_registration_and_logs(tmp_path):
    launcher = _Launcher(fail=True)
    with pytest.raises(host_ops.HostOpError) as excinfo:
        _start(tmp_path, "s2startpopenfail", launcher)
    assert excinfo.value.code == "run_launch_failed"
    record = host_ops.read_launch_record("s2startpopenfail", repository_root=tmp_path)
    assert record["pid"] is None
    assert record["status"] == host_ops.HOST_LAUNCH_STATUS_LAUNCHED
    assert (_launches(tmp_path) / "s2startpopenfail.out.log").is_file()


def test_reaper_is_the_only_writer_of_the_exited_status(tmp_path):
    launcher = _Launcher(prepare_root=False)
    result = _start(tmp_path, "s2start010", launcher)
    process = launcher.processes[0]
    assert result["pid"] == process.pid

    record_path = _launches(tmp_path) / "s2start010.json"
    deadline = 5.0
    assert json.loads(record_path.read_text("utf-8"))["status"] == "launched"
    process.exit(7)
    while deadline > 0:
        record = json.loads(record_path.read_text("utf-8"))
        if record["status"] == host_ops.HOST_LAUNCH_STATUS_EXITED:
            break
        deadline = _sleep(0.05, deadline)
    record = json.loads(record_path.read_text("utf-8"))
    assert record["status"] == host_ops.HOST_LAUNCH_STATUS_EXITED
    assert record["exit_code"] == 7
    assert record["exited_at"]
    # The reaper waited for the child instead of leaving a zombie behind.
    assert process.wait_calls >= 1


def _sleep(seconds: float, budget: float) -> float:
    time.sleep(seconds)
    return budget - seconds


def test_exit_observation_never_blocks_the_tool_call(tmp_path):
    launcher = _Launcher(prepare_root=False)
    started = _start(tmp_path, "s2start010b", launcher)
    process = launcher.processes[0]
    # A still-running child must not delay the already returned result.
    assert started["launched"] is True
    process.exit(0)


def test_real_interpreter_can_raise_the_real_cli(tmp_path):
    """The only real-subprocess case: ``--help`` exits immediately.

    The launch happens against the real checkout (the CLI must be importable
    from its working directory), so the throwaway registration is removed at
    the end; no run root is ever created by ``--help``.
    """

    run_id = "s2starthelp"
    argv = [sys.executable, "-m", "modeling_team", "--help"]
    launches = REPO_ROOT / "workspaces" / "modeling-runs" / host_ops.HOST_LAUNCHES_DIRECTORY
    try:
        launched = host_ops._launch_managed_run(
            run_id=run_id,
            kind="run",
            argv=argv,
            repository_root=REPO_ROOT,
            run_root_wait_seconds=0.05,
        )
        assert launched["launched"] is True
        assert isinstance(launched["pid"], int)
        record_path = launches / f"{run_id}.json"
        deadline = 10.0
        while deadline > 0:
            record = json.loads(record_path.read_text("utf-8"))
            if record["status"] == host_ops.HOST_LAUNCH_STATUS_EXITED:
                break
            deadline = _sleep(0.1, deadline)
        record = json.loads(record_path.read_text("utf-8"))
        assert record["status"] == host_ops.HOST_LAUNCH_STATUS_EXITED
        assert record["exit_code"] == 0
        assert "usage" in (launches / f"{run_id}.out.log").read_text("utf-8")
        assert not (REPO_ROOT / "workspaces" / "modeling-runs" / run_id).exists()
    finally:
        for name in (f"{run_id}.json", f"{run_id}.out.log", f"{run_id}.err.log"):
            (launches / name).unlink(missing_ok=True)
        try:  # leave the real workspace exactly as it was found
            launches.rmdir()
        except OSError:
            pass


def test_registration_writes_leave_no_temporary_files(tmp_path):
    launcher = _Launcher()
    _start(tmp_path, "s2atomic", launcher)
    names = [entry.name for entry in _launches(tmp_path).iterdir()]
    assert not [name for name in names if name.endswith(".tmp")]
    # The registration file is private to the host user.
    mode = (_launches(tmp_path) / "s2atomic.json").stat().st_mode & 0o777
    assert mode == 0o600


def test_supervisor_conflict_is_reported_never_overwritten(tmp_path):
    run_root = tmp_path / "workspaces" / "modeling-runs" / "s2supervisor"
    (run_root / "control").mkdir(parents=True)
    (run_root / "control" / "host-supervisor.json").write_text(
        json.dumps({"schema": host_ops.HOST_SUPERVISOR_SCHEMA, "pid": 999999}),
        encoding="utf-8",
    )
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops._write_supervisor_record(run_root, pid=424242, started_at="t", session_ref=None)
    assert excinfo.value.code == "run_launch_in_progress"
    assert json.loads(
        (run_root / "control" / "host-supervisor.json").read_text("utf-8")
    )["pid"] == 999999
    # The same pid is an idempotent no-op.
    assert (
        host_ops._write_supervisor_record(
            run_root, pid=999999, started_at="t", session_ref=None
        )
        is False
    )


def test_freeze_shape_gate_never_touches_the_filesystem(tmp_path):
    launcher = _Launcher()
    for bad in [None, "", "   ", "not-a-time", "2026-09-18T08:00:00", 20260918]:
        with pytest.raises(host_ops.HostOpError) as excinfo:
            host_ops.start_run(
                run_id="s2freeze",
                task="modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
                profile="modeling_team/profiles/r3-0-002-modeling-team.yaml",
                model_profile="glm-flash-high",
                scope="modeling_team/scopes/create-scope.yaml",
                freeze_started_at=bad,
                repository_root=tmp_path,
                launcher=launcher,
            )
        assert excinfo.value.code == "freeze_started_at_invalid"
        assert excinfo.value.retryable is True
        assert "never fills" in excinfo.value.next_action or "never" in excinfo.value.next_action
    assert launcher.calls == []
    assert not (tmp_path / "workspaces" / "modeling-runs").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("task", "../../outside/task.yaml"),
        ("profile", "/etc/passwd"),
        ("scope", "modeling_tasks/../../etc/passwd"),
    ],
)
def test_input_paths_must_stay_inside_the_repository(tmp_path, field, value):
    kwargs = {
        "run_id": "s2escape",
        "task": "modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
        "profile": "modeling_team/profiles/r3-0-002-modeling-team.yaml",
        "model_profile": "glm-flash-high",
        "scope": "modeling_team/scopes/create-scope.yaml",
        "freeze_started_at": FREEZE,
        "repository_root": tmp_path,
        "launcher": _Launcher(),
    }
    kwargs[field] = value
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.start_run(**kwargs)
    assert excinfo.value.code == "input_path_invalid"
    assert excinfo.value.obj == field
    assert not (tmp_path / "workspaces" / "modeling-runs").exists()


def test_symlink_escape_is_rejected(tmp_path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("s2-outside-repository")
    (outside / "task.yaml").write_text("task: x", "utf-8")
    link = tmp_path / "link-task.yaml"
    link.symlink_to(outside / "task.yaml")
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.start_run(
            run_id="s2symlink",
            task="link-task.yaml",
            profile="modeling_team/profiles/r3-0-002-modeling-team.yaml",
            model_profile="glm-flash-high",
            scope="modeling_team/scopes/create-scope.yaml",
            freeze_started_at=FREEZE,
            repository_root=tmp_path,
            launcher=_Launcher(),
        )
    assert excinfo.value.code == "input_path_invalid"
    assert not (tmp_path / "workspaces" / "modeling-runs").exists()


@pytest.mark.parametrize("bad", ["ftp://platform", "127.0.0.1:8001", "", "//host"])
def test_base_url_protocol_gate(tmp_path, bad):
    with pytest.raises(host_ops.HostOpError) as excinfo:
        host_ops.start_run(
            run_id="s2url",
            task="modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
            profile="modeling_team/profiles/r3-0-002-modeling-team.yaml",
            model_profile="glm-flash-high",
            scope="modeling_team/scopes/create-scope.yaml",
            freeze_started_at=FREEZE,
            base_url=bad,
            repository_root=tmp_path,
            launcher=_Launcher(),
        )
    assert excinfo.value.code == "launch_arguments_invalid"


def test_overlay_and_base_url_are_forwarded_under_their_cli_names(tmp_path):
    launcher = _Launcher()
    host_ops.start_run(
        run_id="s2forward",
        task="modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
        profile="modeling_team/profiles/r3-0-002-modeling-team.yaml",
        model_profile="glm-flash-high",
        scope="modeling_team/scopes/create-scope.yaml",
        freeze_started_at=FREEZE,
        task_overlay="modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml",
        base_url="http://127.0.0.1:8001",
        repository_root=tmp_path,
        launcher=launcher,
        run_root_wait_seconds=0.05,
    )
    argv = launcher.calls[0]["argv"]
    assert "--task-overlay" in argv and "--base-url" in argv
    values = dict(zip(argv[4:-1:2], argv[5::2]))
    assert values["--base-url"] == "http://127.0.0.1:8001"
    assert values["--task-overlay"].endswith(".yaml")
