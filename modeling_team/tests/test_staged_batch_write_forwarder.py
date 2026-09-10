"""Host-side staged write forwarder: real child process, real envelope, real classification.

Every forwarding case below runs the real ``forward_staged_modeling_batch`` against a real
stdio MCP subprocess (the ``mcp`` client library spawns it; the controlled server is a
FastMCP app that mirrors the canonical tool signature and records exactly what it received).
Nothing here reaches the live platform: the controlled server never writes an ontology, and
no valid semantic batch is submitted anywhere.

The classification cases are the ones that matter for the Runner's fail-closed behaviour: a
reply that cannot prove the batch was refused before any write must stay indeterminate, so
``internal_error``-class envelopes and arbitrary tool-boundary failures are asserted UNKNOWN
while only the service's own explicit precondition rejections and the pre-body argument
validation are asserted definite.  The Runner-level cases drive the real AF_UNIX staged
capability endpoint so intent/receipt/kill-switch state is produced by the production
handler, not by the test.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree

import pytest

from modeling_team import __main__ as cli
from modeling_team.capability_mcp import STAGED_PROTOCOL_OPERATION
from modeling_team.contracts import repository_root
from modeling_team.monitor_handoff import HANDOFF_ENV
from modeling_team.protocol_mcp_launch import canonical_protocol_mcp_mode_contract
from modeling_team.runner import TeamRunner
from modeling_team.staged_batch_write_forwarder import (
    DEFINITE_REJECTION_CODES,
    WRITE_TOOL,
    forward_staged_modeling_batch,
)
from modeling_team.staged_decisions import (
    StagedBatchForwardError,
    StagedBatchForwardUnknown,
    staged_decision_artifact_paths,
)
from modeling_team.tests.test_r30002_runner_wiring import _gate_state
from modeling_team.tests.test_r30008b_runner_wiring import (
    MULTI_SLICE_SMOKE,
    PROFILE,
    SMOKE_TASK,
    _capability_args,
    _materialization_valid,
    _open_platform_gate,
    _socket_request,
    _StagedRunner,
)

REPO_ROOT = repository_root()
FIXTURE_KEY = "fixture-protocol-write-key-" + "0a" * 16
# The controlled canonical server.  Its tool mirrors the canonical write tool's parameter
# names (asserted against the real backend signature below) and answers with a mode the test
# chooses, so the forwarder's decoder is exercised over real MCP wire replies.
FIXTURE_SERVER_SOURCE = '''
"""Controlled stand-in for the canonical backend MCP write server."""

import json
import os
import sys
import time

from mcp.server.fastmcp import FastMCP

RECORD_PATH = sys.argv[1]
MODE = sys.argv[2]
ERROR_CODE = sys.argv[3] if len(sys.argv) > 3 else ""

server = FastMCP("staged-write-fixture")


def _record(values):
    with open(RECORD_PATH, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "pid": os.getpid(),
                "argv": sys.argv,
                "cwd": os.getcwd(),
                "env": dict(os.environ),
                "batch": values,
            },
            handle,
            sort_keys=True,
        )


@server.tool()
def submit_modeling_batch(
    session_id: str,
    client_batch_id: str,
    ontology_id: str,
    idempotency_key: str,
    expected_workspace_version: str,
    items: list[dict],
    mode: str = "apply_atomic",
    lease_token: str | None = None,
):
    _record(
        {
            "session_id": session_id,
            "client_batch_id": client_batch_id,
            "ontology_id": ontology_id,
            "idempotency_key": idempotency_key,
            "expected_workspace_version": expected_workspace_version,
            "items": items,
            "mode": mode,
            "lease_token": lease_token,
        }
    )
    if MODE == "ok":
        return {"ok": True, "data": {"batch_id": "fixture-batch-1", "status": "accepted"}}
    if MODE == "reject":
        return {
            "ok": False,
            "error": "fixture refusal",
            "error_code": ERROR_CODE or "workspace_revision_conflict",
        }
    if MODE == "garbage":
        return "this is not a canonical envelope"
    if MODE == "no_payload":
        return {"ok": True, "data": "not-a-mapping"}
    if MODE == "no_identity":
        return {"ok": True, "data": {"accepted": True}}
    if MODE == "raise":
        raise RuntimeError("fixture tool boundary failure")
    if MODE == "sleep":
        time.sleep(60)
        return {"ok": True, "data": {"batch_id": "fixture-batch-1"}}
    if MODE == "exit":
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(9)
    raise SystemExit(f"unknown fixture mode: {MODE}")


if __name__ == "__main__":
    server.run()
'''


def _record_path(tmp_path: Path) -> Path:
    return tmp_path / "fixture-write-record.json"


def _fixture_seam(
    tmp_path: Path, mode: str, *, code: str | None = None, name: str = "ok"
) -> dict:
    """The controlled canonical server boundary: command, args, and receive record."""

    backend = tmp_path / "backend"
    backend.mkdir(exist_ok=True)
    server = tmp_path / f"{name}-write-fixture-server.py"
    server.write_text(FIXTURE_SERVER_SOURCE, encoding="utf-8")
    args = [str(server), str(_record_path(tmp_path)), mode]
    if code is not None:
        args.append(code)
    return {
        "command": sys.executable,
        "args": args,
        "record": _record_path(tmp_path),
    }


def _forward(tmp_path: Path, mode: str, *, batch=None, code=None, timeout=30.0, **kwargs):
    """One real forward through a real MCP child; returns (result, record or None)."""

    seam = _fixture_seam(tmp_path, mode, code=code, name=mode)
    result = forward_staged_modeling_batch(
        _capability_args()["batch"] if batch is None else batch,
        repository_root=tmp_path,
        protocol_key=FIXTURE_KEY,
        command=seam["command"],
        args=seam["args"],
        call_timeout_seconds=timeout,
        **kwargs,
    )
    return result, _read_record(seam["record"])


def _read_record(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _child_still_running(pid: int) -> bool:
    """True while ``pid`` is a live process (a reaped/zombie child counts as gone)."""

    stat = Path(f"/proc/{pid}/stat")
    if not stat.exists():
        return False
    fields = stat.read_text(encoding="utf-8").rsplit(")", 1)[-1].split()
    return bool(fields) and fields[0] != "Z"


def _assert_child_gone(record: dict, *, timeout: float = 15.0) -> None:
    pid = record["pid"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _child_still_running(pid):
            return
        time.sleep(0.1)
    raise AssertionError(f"the forwarder left child {pid} running")


def _real_write_tool_params() -> list[str]:
    """The canonical ``submit_modeling_batch`` parameter names, from the real module."""

    from app.mcp.tools.modeling_batches import register_modeling_batches

    captured: dict[str, object] = {}

    class _RecorderServer:
        def tool(self):
            def decorator(function):
                captured[function.__name__] = function
                return function

            return decorator

    register_modeling_batches(_RecorderServer())
    function = captured.get(WRITE_TOOL)
    assert function is not None, f"the backend must register {WRITE_TOOL}"
    return list(inspect.signature(function).parameters)


# --- the envelope and the child contract ---------------------------------------


def test_forwarder_reaches_the_real_tool_shape_with_the_verbatim_envelope(tmp_path):
    batch = _capability_args()["batch"]
    result, record = _forward(tmp_path, "ok", batch=batch)

    # The canonical tool really declares exactly these parameters, and the forwarder sent
    # exactly them: the controlled server accepted the call and recorded what arrived.
    params = _real_write_tool_params()
    assert set(record["batch"]) == set(params)
    assert set(record["batch"]) == {
        "session_id",
        "client_batch_id",
        "ontology_id",
        "idempotency_key",
        "expected_workspace_version",
        "items",
        "mode",
        "lease_token",
    }

    # Byte-for-byte fidelity: nothing added, renamed, dropped or re-encoded.
    assert record["batch"] == json.loads(json.dumps(batch))
    assert json.dumps(record["batch"], sort_keys=True) == json.dumps(batch, sort_keys=True)
    assert record["batch"]["mode"] == batch["mode"]

    # The backend's own payload is returned whole, including the batch identity.
    assert result == {"batch_id": "fixture-batch-1", "status": "accepted"}


def test_forwarder_child_environment_is_the_allowlisted_canonical_contract(tmp_path):
    _, record = _forward(tmp_path, "ok", batch=_capability_args()["batch"])

    backend = str(tmp_path / "backend")
    reasoner = str(tmp_path / "backend" / "scripts" / "dev_owl_reasoner.py")
    expected = {
        "ONTOLOGY_MCP_API_KEY": FIXTURE_KEY,
        "PYTHONPATH": backend,
        # A concrete existing host reasoner path and its interpreter directory, never the
        # stale absolute path the child would otherwise read from ``backend/.env``.
        "SEMANTIC_REASONER_COMMAND": reasoner,
        "PATH": f"{tmp_path / 'backend' / '.venv' / 'bin'}:/usr/bin:/bin",
        "HOME": backend,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        **canonical_protocol_mcp_mode_contract(),
    }
    # Nothing the host holds is inherited beyond the stdio client's own POSIX safe list
    # (``mcp.client.stdio.DEFAULT_INHERITED_ENV_VARS``: HOME/LOGNAME/PATH/SHELL/TERM/USER),
    # which the accepted read forwarder already goes through as well: no API key, proxy,
    # plugin or Codex credential reaches the canonical server.  The canonical semantic mode
    # matches the Protocol agent's.
    env = record["env"]
    assert {name: env[name] for name in expected} == expected
    safe_inherited = {"HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER"}
    assert set(env) - set(expected) <= safe_inherited
    assert sorted(
        name for name in env if "KEY" in name or "TOKEN" in name or "PROXY" in name
    ) == ["ONTOLOGY_MCP_API_KEY"]
    # The pin names a file that really exists in the host checkout: the forwarder's default
    # root produces the same existing path, unlike the stale value in ``backend/.env``.
    assert (REPO_ROOT / "backend" / "scripts" / "dev_owl_reasoner.py").is_file()
    assert record["cwd"] == backend
    assert record["argv"][1:] == _fixture_seam(tmp_path, "ok")["args"][1:]


def test_forwarder_tears_its_child_down_after_the_call(tmp_path):
    _, record = _forward(tmp_path, "ok", batch=_capability_args()["batch"])
    _assert_child_gone(record)


# --- definite: the codes that provably precede any write -----------------------


@pytest.mark.parametrize(
    "code",
    [
        "build_session_not_active",
        "workspace_revision_conflict",
        "ontology_lease_conflict",
        "forbidden",
    ],
)
def test_explicit_precondition_rejections_stay_definite(tmp_path, code):
    assert code in DEFINITE_REJECTION_CODES
    with pytest.raises(StagedBatchForwardError) as failure:
        _forward(tmp_path, "reject", batch=_capability_args()["batch"], code=code)
    assert code in str(failure.value)
    assert not isinstance(failure.value, StagedBatchForwardUnknown)


def test_argument_validation_is_definite_because_the_body_never_ran(tmp_path):
    # A batch that cannot satisfy the canonical tool signature.
    with pytest.raises(StagedBatchForwardError) as failure:
        _forward(tmp_path, "ok", batch={"_": "not the canonical envelope"})
    assert f"for {WRITE_TOOL}Arguments" in str(failure.value)
    # The controlled server recorded nothing: the call never reached the tool body.
    assert _read_record(_record_path(tmp_path)) is None


# --- indeterminate: everything that cannot prove the write did not happen -------


@pytest.mark.parametrize("code", ["internal_error", "dependency_error", "never_seen_code"])
def test_post_commit_class_error_envelopes_stay_unknown(tmp_path, code):
    assert code not in DEFINITE_REJECTION_CODES
    with pytest.raises(StagedBatchForwardUnknown) as failure:
        _forward(tmp_path, "reject", batch=_capability_args()["batch"], code=code)
    assert code in str(failure.value)
    # The batch did reach the service; the envelope alone cannot say what happened to it.
    assert _read_record(_record_path(tmp_path))["batch"]["mode"] == "apply_atomic"


@pytest.mark.parametrize("mode", ["garbage", "no_payload", "no_identity"])
def test_unreadable_or_identityless_replies_stay_unknown(tmp_path, mode):
    with pytest.raises(StagedBatchForwardUnknown):
        _forward(tmp_path, mode, batch=_capability_args()["batch"])
    assert _read_record(_record_path(tmp_path)) is not None


def test_tool_boundary_failure_that_may_follow_a_write_stays_unknown(tmp_path):
    with pytest.raises(StagedBatchForwardUnknown):
        _forward(tmp_path, "raise", batch=_capability_args()["batch"])
    assert _read_record(_record_path(tmp_path)) is not None


def test_timeout_after_dispatch_stays_unknown_and_leaves_no_child(tmp_path):
    with pytest.raises(StagedBatchForwardUnknown):
        _forward(tmp_path, "sleep", batch=_capability_args()["batch"], timeout=1.0)
    # The server had already received the batch before the read timed out.
    record = _read_record(_record_path(tmp_path))
    assert record["batch"]["client_batch_id"] == _capability_args()["batch"]["client_batch_id"]
    _assert_child_gone(record)


def test_disconnect_after_dispatch_stays_unknown_and_leaves_no_child(tmp_path):
    with pytest.raises(StagedBatchForwardUnknown):
        _forward(tmp_path, "exit", batch=_capability_args()["batch"])
    record = _read_record(_record_path(tmp_path))
    assert record is not None
    _assert_child_gone(record)


# --- definite: refusals that happen before anything is dispatched ---------------


def test_missing_envelope_or_key_refuses_before_spawning(tmp_path):
    seam = _fixture_seam(tmp_path, "ok")
    with pytest.raises(StagedBatchForwardError):
        forward_staged_modeling_batch(
            "not an envelope",
            repository_root=tmp_path,
            protocol_key=FIXTURE_KEY,
            command=seam["command"],
            args=seam["args"],
        )
    with pytest.raises(StagedBatchForwardError) as failure:
        forward_staged_modeling_batch(
            _capability_args()["batch"],
            repository_root=tmp_path,
            protocol_key=None,
            command=seam["command"],
            args=seam["args"],
        )
    assert "protocol key" in str(failure.value)
    assert _read_record(seam["record"]) is None


def test_unstartable_child_is_definite_and_writes_nothing(tmp_path):
    seam = _fixture_seam(tmp_path, "ok")
    with pytest.raises(StagedBatchForwardError) as failure:
        forward_staged_modeling_batch(
            _capability_args()["batch"],
            repository_root=tmp_path,
            protocol_key=FIXTURE_KEY,
            command=str(tmp_path / "no-such-python"),
            args=seam["args"],
        )
    assert not isinstance(failure.value, StagedBatchForwardUnknown)
    with pytest.raises(StagedBatchForwardError):
        forward_staged_modeling_batch(
            _capability_args()["batch"],
            repository_root=tmp_path,
            protocol_key=FIXTURE_KEY,
            command=sys.executable,
            args=["-c", "raise SystemExit(3)"],
        )
    assert _read_record(seam["record"]) is None


# --- Runner integration: the real capability endpoint over its AF_UNIX socket ----


def _bind_fixture_forwarder(staged, tmp_path, mode, *, code=None, key=FIXTURE_KEY):
    seam = _fixture_seam(tmp_path, mode, code=code, name=f"runner-{mode}")
    staged.runner.staged_batch_forwarder = functools.partial(
        forward_staged_modeling_batch,
        repository_root=tmp_path,
        protocol_key=key,
        command=seam["command"],
        args=seam["args"],
    )
    return seam


def _capability_call(staged, arguments):
    """One real ``tools/call`` through the run's own protocol capability socket."""

    endpoint = staged.runner.acceptance.capability_endpoint("protocol")
    endpoint.start()
    try:
        return _socket_request(
            endpoint.socket_path,
            endpoint.token,
            "tools/call",
            name=STAGED_PROTOCOL_OPERATION,
            arguments=arguments,
        )
    finally:
        endpoint.stop()


def _intent(staged) -> dict:
    intents_dir = staged_decision_artifact_paths(staged.run_root)["intents_dir"]
    return json.loads((intents_dir / "intent-1.json").read_text(encoding="utf-8"))


def _receipts(staged) -> list[dict]:
    receipts_dir = staged_decision_artifact_paths(staged.run_root)["receipts_dir"]
    if not receipts_dir.exists():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(receipts_dir.iterdir())
    ]


def test_capability_submission_receipts_the_batch_written_by_the_real_child(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)
        seam = _bind_fixture_forwarder(staged, tmp_path, "ok")

        response = _capability_call(staged, _capability_args())

        assert "error" not in response, response
        structured = response["result"]["structuredContent"]
        assert structured["ok"] is True, structured
        # The capability entry wraps the staged handler's own result under ``data``.
        assert structured["data"]["batch_id"] == "fixture-batch-1"

        # The platform-side write really happened against the real child, with the
        # Runner's own envelope, after the durable intent was on disk.
        record = _read_record(seam["record"])
        assert record is not None
        assert record["batch"]["client_batch_id"] == "placeholder-batch-1"
        assert record["batch"]["mode"] == "apply_atomic"

        # The production handler wrote the receipt: intent receipted, batch identity bound.
        assert _intent(staged)["status"] == "receipted"
        receipts = _receipts(staged)
        assert len(receipts) == 1
        assert receipts[0]["batch_id"] == "fixture-batch-1"
        assert receipts[0]["submitted_via"] == STAGED_PROTOCOL_OPERATION
        assert staged.runner._staged_gate_killed is False
        _assert_child_gone(record)
    finally:
        staged.cleanup()


def test_capability_submission_keeps_an_unprovable_write_unknown(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)
        _bind_fixture_forwarder(staged, tmp_path, "reject", code="internal_error")

        response = _capability_call(staged, _capability_args())

        assert "error" not in response, response
        structured = response["result"]["structuredContent"]
        assert structured["ok"] is False, structured
        assert structured["error"]["reason_code"] == "staged_batch_forward_unknown"

        # The uncertainty is durable and latched: no receipt, intent unknown, kill switch.
        assert _receipts(staged) == []
        assert _intent(staged)["status"] == "unknown"
        assert staged.runner._staged_gate_killed is True
        assert _gate_state(staged.run_root)["reason_code"] == "staged_unreconciled_batch"
    finally:
        staged.cleanup()


def test_capability_submission_keeps_an_explicit_precondition_rejection_repairable(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        _open_platform_gate(staged)
        _materialization_valid(staged.run_root)
        _bind_fixture_forwarder(staged, tmp_path, "reject", code="build_session_not_active")

        response = _capability_call(staged, _capability_args())

        assert "error" not in response, response
        structured = response["result"]["structuredContent"]
        assert structured["ok"] is False, structured
        assert structured["error"]["reason_code"] == "staged_batch_forward_failed"
        assert "build_session_not_active" in structured["error"]["detail"]

        # Nothing was written, so the intent stays retryable under the same key.
        assert _receipts(staged) == []
        assert _intent(staged)["status"] == "submitted"
        assert staged.runner._staged_gate_killed is False
    finally:
        staged.cleanup()


# --- the foreground CLI binding -------------------------------------------------


class _StopBeforeStart(Exception):
    """Sentinel raised from ``TeamRunner.start``: this test never starts a roster."""


def _cli_argv(task: Path, run_id: str, scope_path: Path) -> list[str]:
    return [
        "modeling_team",
        "run",
        "--profile",
        str(PROFILE),
        "--task",
        str(task),
        "--run-id",
        run_id,
        "--scope",
        str(scope_path),
        # The v2 tasks fix their own freeze instant; a freeze start is mandatory for them.
        "--freeze-started-at",
        datetime.now(UTC).isoformat(),
    ]


def test_foreground_cli_binds_a_real_write_forwarder_only_for_staged_runs(
    tmp_path, monkeypatch
):
    captured: list[TeamRunner] = []
    original_prepare = TeamRunner.prepare

    def prepare(self, *args, **kwargs):
        result = original_prepare(self, *args, **kwargs)
        # What start() records for a live run; the binding must resolve it per call.
        self.run.protocol_key = FIXTURE_KEY
        captured.append(self)
        return result

    def start(self, *args, **kwargs):
        raise _StopBeforeStart(self.run.run_id)

    monkeypatch.setattr(TeamRunner, "prepare", prepare)
    monkeypatch.setattr(TeamRunner, "start", start)
    monkeypatch.delenv(HANDOFF_ENV, raising=False)
    scope_path = tmp_path / "scope.yaml"
    scope_path.write_text("mode: create\n", encoding="utf-8")
    run_ids = [
        f"r30008b-write-forwarder-cli-{os.getpid()}-staged",
        f"r30008b-write-forwarder-cli-{os.getpid()}-plain",
    ]
    try:
        monkeypatch.setattr(sys, "argv", _cli_argv(SMOKE_TASK, run_ids[0], scope_path))
        with pytest.raises(_StopBeforeStart):
            cli.main()
        staged_runner = captured[-1]
        assert staged_runner._staged_decisions is True
        bound = staged_runner.staged_batch_forwarder
        assert callable(bound)

        # The bound callable is the real forwarder for this run's root and key: with the
        # key absent it refuses as definite and spawns nothing at all.
        staged_runner.run.protocol_key = None
        with pytest.raises(StagedBatchForwardError) as failure:
            bound(_capability_args()["batch"])
        assert "protocol key" in str(failure.value)

        # A run that does not select staged decisions keeps the fail-closed default.
        monkeypatch.setattr(sys, "argv", _cli_argv(MULTI_SLICE_SMOKE, run_ids[1], scope_path))
        with pytest.raises(_StopBeforeStart):
            cli.main()
        plain_runner = captured[-1]
        assert plain_runner._staged_decisions is False
        assert plain_runner.staged_batch_forwarder is None
    finally:
        for runner in captured:
            runner.cleanup()
        for run_id in run_ids:
            run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
            if run_root.exists():
                rmtree(run_root)
