"""R4.0-012 retired staged evidence capability cannot invoke a child process."""

from __future__ import annotations

import functools
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree

import pytest

from modeling_team.capability_mcp import STAGED_PROTOCOL_ASSOCIATE_EVIDENCE_OPERATION
from modeling_team.contracts import repository_root
from modeling_team.monitor_handoff import HANDOFF_ENV
from modeling_team.runner import TeamRunner
from modeling_team.staged_batch_write_forwarder import (
    forward_staged_associate_evidence,
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


def _read_record(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# --- the envelope and the child contract ---------------------------------------


# --- definite: refusals that provably precede any write ------------------------


# --- indeterminate: everything that cannot prove the write did not happen -------


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


def test_retired_capability_cannot_reach_the_offline_child(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        seam = _bind_fixture_evidence_forwarder(staged, tmp_path, "ok")

        response = _evidence_call(staged, _association())

        assert response["error"]["code"] == -32001
        assert _read_record(seam["record"]) is None

        # Evidence is not materialization: no intent, no receipt, and the write
        # integrity latch stays exactly where it was.
        assert not (staged.run_root / "staged-decisions" / "intents").exists()
        assert not (staged.run_root / "staged-decisions" / "receipts").exists()
        assert staged.runner._staged_gate_killed is False
    finally:
        staged.cleanup()


def test_retired_capability_rejects_repeated_calls_without_latching_the_run(tmp_path):
    staged = _StagedRunner(tmp_path)
    try:
        staged.prepare()
        seam = _bind_fixture_evidence_forwarder(staged, tmp_path, "reject", code="not_found")

        response = _evidence_call(staged, _association())

        assert response["error"]["code"] == -32001
        assert _evidence_call(staged, _association())["error"]["code"] == -32001
        assert _read_record(seam["record"]) is None
        assert not (staged.run_root / "staged-decisions" / "intents").exists()
        assert not (staged.run_root / "staged-decisions" / "receipts").exists()
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


def test_foreground_cli_does_not_bind_the_retired_evidence_forwarder(
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
        assert getattr(staged_runner, "staged_evidence_forwarder", None) is None

        # A run that does not select staged decisions keeps the fail-closed default.
        monkeypatch.setattr(sys, "argv", _cli_argv(MULTI_SLICE_SMOKE, run_ids[1], scope_path))
        with pytest.raises(_StopBeforeStart):
            cli.main()
        plain_runner = captured[-1]
        assert plain_runner._staged_decisions is False
        assert getattr(plain_runner, "staged_evidence_forwarder", None) is None
    finally:
        for runner in captured:
            runner.cleanup()
        for run_id in run_ids:
            run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
            if run_root.exists():
                rmtree(run_root)
