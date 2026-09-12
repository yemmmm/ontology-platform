"""Host-side staged evidence forwarder: real child process, real envelope, real classification.

``forward_staged_associate_evidence`` reuses the staged write forwarder's child discipline
(one allowlisted stdio MCP child per call) but targets the platform's
``associate_evidence_reference`` tool.  Every case below runs the real function against a
real stdio MCP subprocess; the controlled server mirrors the canonical tool signature and
records exactly what it received, and it never writes an ontology.

The classification contract differs from the batch write in one respect: an evidence
association is idempotent by ``(ontology, target, reference)``, so a definite rejection is
only what the platform proves is pre-write, and everything else stays indeterminate so the
Protocol role can retry the same association instead of guessing.
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

from modeling_team.capability_mcp import STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION
from modeling_team.contracts import repository_root
from modeling_team.monitor_handoff import HANDOFF_ENV
from modeling_team.protocol_mcp_launch import canonical_protocol_mcp_mode_contract
from modeling_team.runner import TeamRunner
from modeling_team.staged_batch_write_forwarder import (
    ASSOCIATE_DEFINITE_REJECTION_CODES,
    ASSOCIATE_EVIDENCE_TOOL,
    forward_staged_associate_evidence,
)
from modeling_team.staged_decisions import (
    StagedBatchForwardError,
    StagedBatchForwardUnknown,
)
from modeling_team.tests.test_r30008b_runner_wiring import (
    MULTI_SLICE_SMOKE,
    PROFILE,
    SMOKE_TASK,
    _socket_request,
    _StagedRunner,
)
from modeling_team.tests.test_staged_associate_evidence import _association

REPO_ROOT = repository_root()
FIXTURE_KEY = "fixture-protocol-evidence-key-" + "0b" * 16

# The controlled canonical server.  Its tool mirrors ``associate_evidence_reference``'s
# parameter names (asserted against the real backend signature below) and answers with a
# mode the test chooses, so the forwarder's decoder is exercised over real MCP wire replies.
FIXTURE_SERVER_SOURCE = '''
"""Controlled stand-in for the canonical backend MCP evidence server."""

import json
import os
import sys
import time

from mcp.server.fastmcp import FastMCP

RECORD_PATH = sys.argv[1]
MODE = sys.argv[2]
ERROR_CODE = sys.argv[3] if len(sys.argv) > 3 else ""

server = FastMCP("staged-evidence-fixture")


def _record(values):
    with open(RECORD_PATH, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "pid": os.getpid(),
                "argv": sys.argv,
                "cwd": os.getcwd(),
                "env": dict(os.environ),
                "association": values,
            },
            handle,
            sort_keys=True,
        )


@server.tool()
def associate_evidence_reference(
    project_id: str,
    ontology_id: str,
    target_type: str,
    target_id: str,
    evidence_reference_ids: list[str] | None = None,
    evidence: list[dict] | None = None,
    graph_set_id: str | None = None,
    client_item_id: str | None = None,
    edit_audit_id: str | None = None,
    actor: str | None = None,
):
    _record(
        {
            "project_id": project_id,
            "ontology_id": ontology_id,
            "target_type": target_type,
            "target_id": target_id,
            "evidence_reference_ids": evidence_reference_ids,
            "evidence": evidence,
            "graph_set_id": graph_set_id,
            "client_item_id": client_item_id,
            "edit_audit_id": edit_audit_id,
            "actor": actor,
        }
    )
    if MODE == "ok":
        return {"ok": True, "data": {"items": [{"id": "fixture-association-1"}], "total": 1}}
    if MODE == "reject":
        return {
            "ok": False,
            "error": "fixture refusal",
            "error_code": ERROR_CODE or "validation_error",
        }
    if MODE == "garbage":
        return "this is not a canonical envelope"
    if MODE == "no_payload":
        return {"ok": True, "data": "not-a-mapping"}
    if MODE == "no_verdict":
        return {"ok": True}
    if MODE == "raise":
        raise RuntimeError("fixture tool boundary failure")
    if MODE == "sleep":
        time.sleep(60)
        return {"ok": True, "data": {"items": [], "total": 0}}
    if MODE == "exit":
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(9)
    raise SystemExit(f"unknown fixture mode: {MODE}")


if __name__ == "__main__":
    server.run()
'''


def _record_path(tmp_path: Path) -> Path:
    return tmp_path / "fixture-evidence-record.json"


def _fixture_seam(
    tmp_path: Path, mode: str, *, code: str | None = None, name: str | None = None
) -> dict:
    """The controlled canonical server boundary: command, args, and receive record."""

    backend = tmp_path / "backend"
    backend.mkdir(exist_ok=True)
    server = tmp_path / f"{name or mode}-evidence-fixture-server.py"
    server.write_text(FIXTURE_SERVER_SOURCE, encoding="utf-8")
    args = [str(server), str(_record_path(tmp_path)), mode]
    if code is not None:
        args.append(code)
    return {"command": sys.executable, "args": args, "record": _record_path(tmp_path)}


def _forward(tmp_path: Path, mode: str, *, association=None, code=None, timeout=30.0):
    """One real forward through a real MCP child; returns (result, record or None)."""

    seam = _fixture_seam(tmp_path, mode, code=code)
    result = forward_staged_associate_evidence(
        _association() if association is None else association,
        repository_root=tmp_path,
        protocol_key=FIXTURE_KEY,
        command=seam["command"],
        args=seam["args"],
        call_timeout_seconds=timeout,
    )
    return result, _read_record(seam["record"])


def _read_record(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _real_associate_params() -> list[str]:
    """The canonical ``associate_evidence_reference`` parameter names, from the real module."""

    from app.mcp.tools.evidence import register_evidence

    captured: dict[str, object] = {}

    class _RecorderServer:
        def tool(self):
            def decorator(function):
                captured[function.__name__] = function
                return function

            return decorator

    register_evidence(_RecorderServer())
    function = captured.get(ASSOCIATE_EVIDENCE_TOOL)
    assert function is not None, f"the backend must register {ASSOCIATE_EVIDENCE_TOOL}"
    return list(inspect.signature(function).parameters)


# --- the envelope and the child contract ---------------------------------------


def test_evidence_forwarder_reaches_the_real_tool_shape_with_the_verbatim_envelope(tmp_path):
    association = _association()
    result, record = _forward(tmp_path, "ok", association=association)

    params = _real_associate_params()
    assert params == [
        "project_id",
        "ontology_id",
        "target_type",
        "target_id",
        "evidence_reference_ids",
        "evidence",
        "graph_set_id",
        "client_item_id",
        "edit_audit_id",
        "actor",
    ]
    # Byte-for-byte fidelity: every association field arrives verbatim, nothing is added,
    # renamed, dropped or re-encoded, every optional platform argument stays unset, and the
    # role's own identity never becomes a platform argument.
    recorded = record["association"]
    assert {key: recorded[key] for key in association} == association
    assert {key: value for key, value in recorded.items() if key not in association} == {
        key: None for key in params if key not in association
    }
    assert recorded["actor"] is None

    # The backend's own payload is returned whole.
    assert result == {"items": [{"id": "fixture-association-1"}], "total": 1}


def test_evidence_forwarder_child_environment_carries_only_the_protocol_key(tmp_path):
    _, record = _forward(tmp_path, "ok")

    backend = str(tmp_path / "backend")
    env = record["env"]
    expected = {
        "ONTOLOGY_MCP_API_KEY": FIXTURE_KEY,
        "PYTHONPATH": backend,
        "SEMANTIC_REASONER_COMMAND": str(tmp_path / "backend" / "scripts" / "dev_owl_reasoner.py"),
        "PATH": f"{tmp_path / 'backend' / '.venv' / 'bin'}:/usr/bin:/bin",
        "HOME": backend,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        **canonical_protocol_mcp_mode_contract(),
    }
    assert {name: env[name] for name in expected} == expected
    # Nothing the host holds is inherited beyond the stdio client's own POSIX safe list.
    safe_inherited = {"HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER"}
    assert set(env) - set(expected) <= safe_inherited
    assert sorted(
        name for name in env if "KEY" in name or "TOKEN" in name or "PROXY" in name
    ) == ["ONTOLOGY_MCP_API_KEY"]
    assert record["cwd"] == backend


# --- definite: refusals that provably precede any write ------------------------


@pytest.mark.parametrize(
    "code",
    ["validation_error", "not_found", "forbidden", "forbidden_scope", "request_too_large"],
)
def test_evidence_reference_rejections_stay_definite(tmp_path, code):
    assert code in ASSOCIATE_DEFINITE_REJECTION_CODES
    with pytest.raises(StagedBatchForwardError) as failure:
        _forward(tmp_path, "reject", code=code)
    assert code in str(failure.value)
    assert not isinstance(failure.value, StagedBatchForwardUnknown)


def test_argument_validation_is_definite_because_the_body_never_ran(tmp_path):
    payload = _association()
    del payload["target_id"]
    with pytest.raises(StagedBatchForwardError) as failure:
        _forward(tmp_path, "ok", association=payload)
    assert f"for {ASSOCIATE_EVIDENCE_TOOL}Arguments" in str(failure.value)
    # The controlled server recorded nothing: the call never reached the tool body.
    assert _read_record(_record_path(tmp_path)) is None


def test_missing_envelope_or_key_refuses_before_spawning(tmp_path):
    seam = _fixture_seam(tmp_path, "ok")
    with pytest.raises(StagedBatchForwardError):
        forward_staged_associate_evidence(
            "not an envelope",
            repository_root=tmp_path,
            protocol_key=FIXTURE_KEY,
            command=seam["command"],
            args=seam["args"],
        )
    with pytest.raises(StagedBatchForwardError) as failure:
        forward_staged_associate_evidence(
            _association(),
            repository_root=tmp_path,
            protocol_key=None,
            command=seam["command"],
            args=seam["args"],
        )
    assert "protocol key" in str(failure.value)
    assert _read_record(seam["record"]) is None


def test_unstartable_child_is_definite_and_writes_nothing(tmp_path):
    with pytest.raises(StagedBatchForwardError) as failure:
        forward_staged_associate_evidence(
            _association(),
            repository_root=tmp_path,
            protocol_key=FIXTURE_KEY,
            command=str(tmp_path / "no-such-python"),
            args=["-m", "app.mcp.server"],
        )
    assert not isinstance(failure.value, StagedBatchForwardUnknown)
    assert _read_record(_record_path(tmp_path)) is None


# --- indeterminate: everything that cannot prove the write did not happen -------


@pytest.mark.parametrize("code", ["internal_error", "dependency_error", "never_seen_code"])
def test_unclassifiable_error_envelopes_stay_unknown(tmp_path, code):
    assert code not in ASSOCIATE_DEFINITE_REJECTION_CODES
    with pytest.raises(StagedBatchForwardUnknown) as failure:
        _forward(tmp_path, "reject", code=code)
    assert code in str(failure.value)
    # The association did reach the service; the envelope alone cannot say what happened.
    assert _read_record(_record_path(tmp_path))["association"]["target_type"] == "modeling_item"


@pytest.mark.parametrize("mode", ["garbage", "no_payload", "no_verdict"])
def test_unreadable_replies_stay_unknown(tmp_path, mode):
    with pytest.raises(StagedBatchForwardUnknown):
        _forward(tmp_path, mode)
    assert _read_record(_record_path(tmp_path)) is not None


def test_tool_boundary_failure_that_may_follow_a_write_stays_unknown(tmp_path):
    with pytest.raises(StagedBatchForwardUnknown):
        _forward(tmp_path, "raise")
    assert _read_record(_record_path(tmp_path)) is not None


def test_timeout_after_dispatch_stays_unknown(tmp_path):
    with pytest.raises(StagedBatchForwardUnknown):
        _forward(tmp_path, "sleep", timeout=1.0)
    record = _read_record(_record_path(tmp_path))
    assert record["association"]["target_id"] == _association()["target_id"]


def test_disconnect_after_dispatch_stays_unknown(tmp_path):
    with pytest.raises(StagedBatchForwardUnknown):
        _forward(tmp_path, "exit")
    assert _read_record(_record_path(tmp_path)) is not None


# --- Runner integration: the real capability endpoint over its AF_UNIX socket ----


def _bind_fixture_evidence_forwarder(staged, tmp_path, mode, *, code=None, key=FIXTURE_KEY):
    seam = _fixture_seam(tmp_path, mode, code=code, name=f"runner-{mode}")
    staged.runner.staged_evidence_forwarder = functools.partial(
        forward_staged_associate_evidence,
        repository_root=tmp_path,
        protocol_key=key,
        command=seam["command"],
        args=seam["args"],
    )
    return seam


def _evidence_call(staged, association):
    endpoint = staged.runner.acceptance.capability_endpoint("protocol")
    endpoint.start()
    try:
        return _socket_request(
            endpoint.socket_path,
            endpoint.token,
            "tools/call",
            name=STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION,
            arguments={"protocol_id": "protocol", "association": association},
        )
    finally:
        endpoint.stop()


def test_capability_evidence_repost_reaches_the_real_child_without_a_receipt(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        seam = _bind_fixture_evidence_forwarder(staged, tmp_path, "ok")

        response = _evidence_call(staged, _association())

        assert "error" not in response, response
        structured = response["result"]["structuredContent"]
        assert structured["ok"] is True, structured
        assert structured["data"]["total"] == 1
        record = _read_record(seam["record"])
        assert record is not None
        assert record["association"]["target_type"] == "modeling_item"

        # Evidence is not materialization: no intent, no receipt, and the write
        # integrity latch stays exactly where it was.
        assert not (staged.run_root / "staged-decisions" / "intents").exists()
        assert not (staged.run_root / "staged-decisions" / "receipts").exists()
        assert staged.runner._staged_gate_killed is False
    finally:
        staged.cleanup()


def test_capability_evidence_repost_keeps_a_definite_refusal_retryable(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        _bind_fixture_evidence_forwarder(staged, tmp_path, "reject", code="not_found")

        response = _evidence_call(staged, _association())

        structured = response["result"]["structuredContent"]
        assert structured["ok"] is False, structured
        assert structured["error"]["reason_code"] == "staged_evidence_forward_failed"
        assert "not_found" in structured["error"]["detail"]
        # An idempotent association has no durable attempt state: nothing is latched
        # and the identical call may simply be replayed.
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
        "--freeze-started-at",
        datetime.now(UTC).isoformat(),
    ]


def test_foreground_cli_binds_a_real_evidence_forwarder_only_for_staged_runs(
    tmp_path, monkeypatch
):
    from modeling_team import __main__ as cli

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
        f"r30008b-evidence-forwarder-cli-{os.getpid()}-staged",
        f"r30008b-evidence-forwarder-cli-{os.getpid()}-plain",
    ]
    try:
        monkeypatch.setattr(sys, "argv", _cli_argv(SMOKE_TASK, run_ids[0], scope_path))
        with pytest.raises(_StopBeforeStart):
            cli.main()
        staged_runner = captured[-1]
        assert staged_runner._staged_decisions is True
        bound = staged_runner.staged_evidence_forwarder
        assert callable(bound)
        # The bound callable is the real forwarder for this run's root and key: with the
        # key absent it refuses as definite and spawns nothing at all.
        staged_runner.run.protocol_key = None
        with pytest.raises(StagedBatchForwardError) as failure:
            bound(_association())
        assert "protocol key" in str(failure.value)

        # A run that does not select staged decisions keeps the fail-closed default.
        monkeypatch.setattr(sys, "argv", _cli_argv(MULTI_SLICE_SMOKE, run_ids[1], scope_path))
        with pytest.raises(_StopBeforeStart):
            cli.main()
        plain_runner = captured[-1]
        assert plain_runner._staged_decisions is False
        assert plain_runner.staged_evidence_forwarder is None
    finally:
        for runner in captured:
            runner.cleanup()
        for run_id in run_ids:
            run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
            if run_root.exists():
                rmtree(run_root)
