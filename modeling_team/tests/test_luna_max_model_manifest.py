from __future__ import annotations

import json
import os
import shutil
import threading
import time
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from modeling_team.contracts import TeamConfigurationError, _load_package
from modeling_team.model_manifest import (
    FORMAL_MODEL_PACKAGE_IDS,
    FORMAL_MODEL_TUPLE,
    load_formal_model_manifest,
)
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import (
    CodexRuntimeAdapter,
    CodexRuntimeError,
    _Agent,
    audit_private_artifacts,
)


ROOT = Path(__file__).resolve().parents[2]


def _copy_packages(root: Path) -> None:
    target = root / "modeling_team" / "model-manifests" / "r2-3-005-luna-max.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        ROOT / "modeling_team" / "model-manifests" / "r2-3-005-luna-max.yaml",
        target,
    )


def _edit_package(root: Path, package_id: str, edit) -> None:
    path = root / "modeling_team" / "model-manifests" / "r2-3-005-luna-max.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    edit(value["packages"], package_id)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def test_formal_manifest_requires_the_exact_same_tuple_for_all_six_packages(tmp_path: Path) -> None:
    _copy_packages(tmp_path)
    manifest = load_formal_model_manifest(tmp_path)
    assert tuple(manifest.overrides) == FORMAL_MODEL_PACKAGE_IDS
    assert set(manifest.overrides.values()) == {FORMAL_MODEL_TUPLE}
    assert manifest.digest
    for package_id in FORMAL_MODEL_PACKAGE_IDS:
        package = yaml.safe_load(
            (ROOT / "modeling_team" / "agent-packages" / package_id / "package.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert not (
            set(package["runtime"]["codex"])
            & {"model", "model_provider", "model_reasoning_effort"}
        )


@pytest.mark.parametrize(
    "edit",
    [
        lambda packages, package_id: packages[package_id].update(model_temperature=0.2),
        lambda packages, package_id: packages[package_id].pop("model_provider"),
        lambda packages, package_id: packages[package_id].update(model="gpt-5.5"),
        lambda packages, package_id: packages[package_id].update(model_provider="openai"),
        lambda packages, package_id: packages[package_id].update(model_reasoning_effort="high"),
    ],
)
def test_formal_manifest_rejects_unknown_partial_or_unsupported_model_values(tmp_path: Path, edit) -> None:
    _copy_packages(tmp_path)
    _edit_package(tmp_path, "source-examiner", edit)
    with pytest.raises(TeamConfigurationError):
        load_formal_model_manifest(tmp_path)


def test_formal_manifest_rejects_missing_examiner_and_cross_package_mismatch(tmp_path: Path) -> None:
    _copy_packages(tmp_path)
    path = tmp_path / "modeling_team" / "model-manifests" / "r2-3-005-luna-max.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    value["packages"].pop("platform-examiner")
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(TeamConfigurationError):
        load_formal_model_manifest(tmp_path)

    _copy_packages(tmp_path)
    _edit_package(
        tmp_path,
        "platform-examiner",
        lambda packages, package_id: packages[package_id].update(model="gpt-5.5"),
    )
    with pytest.raises(TeamConfigurationError):
        load_formal_model_manifest(tmp_path)


def test_runner_formal_model_gate_has_zero_side_effects_before_platform_preflight(tmp_path: Path) -> None:
    config = SimpleNamespace(
        task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
        profile=SimpleNamespace(profile_id="r2-3-005-modeling-team"),
    )
    preflight_calls: list[object] = []
    runner = TeamRunner(repository_root=tmp_path, adapter=SimpleNamespace())
    with (
        patch("modeling_team.runner.load_formal_team_configuration", return_value=config),
        patch(
            "modeling_team.runner.load_formal_model_manifest",
            side_effect=TeamConfigurationError("manifest rejected"),
        ),
        patch(
            "modeling_team.runner.run_prestart_preflight",
            side_effect=lambda **_kwargs: preflight_calls.append(True),
        ),
    ):
        with pytest.raises(TeamConfigurationError, match="manifest rejected"):
            runner.prepare(
                run_id="luna-preflight-gate",
                profile_path=tmp_path / "profile.yaml",
                task_path=tmp_path / "task.yaml",
                scope={"mode": "create"},
            )
    assert preflight_calls == []
    assert runner.run is None
    assert not (tmp_path / "workspaces").exists()


def test_private_artifact_audit_covers_evidence_sqlite_wal_and_shm_without_secret_content(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    sentinel = b"synthetic-auth-sentinel"
    (evidence / "session.jsonl").write_bytes(b"prefix:" + sentinel)
    (evidence / "state.sqlite-wal").write_bytes(b"wal:" + sentinel)
    (evidence / "state.sqlite-shm").write_bytes(b"shm:" + sentinel)
    result = audit_private_artifacts(tmp_path, [sentinel])
    assert result["match_count"] == 3
    assert result["matched_secret_count"] == 1
    assert sentinel.decode() not in repr(result)

    for path in evidence.iterdir():
        path.unlink()
    clean = audit_private_artifacts(tmp_path, [sentinel])
    assert clean["match_count"] == 0


def test_private_artifact_audit_scans_shell_snapshots_with_and_without_suffix(
    tmp_path: Path,
) -> None:
    shell_root = tmp_path / "shell_snapshots"
    shell_root.mkdir()
    sentinel = b"shell-only-auth-token"
    (shell_root / "command.sh").write_bytes(b"#!/bin/sh\n" + sentinel)
    (shell_root / "extensionless").write_bytes(b"echo " + sentinel)
    result = audit_private_artifacts(tmp_path, [sentinel])
    assert result["match_count"] == 2
    assert sentinel.decode() not in repr(result)


def test_auth_json_leaf_audit_catches_token_only_logs_without_echoing_values(
    tmp_path: Path,
) -> None:
    access_token = "access-token-only-in-log"
    refresh_token = "refresh-token-only-in-log"
    payload = json.dumps(
        {
            "tokens": {
                "access_token": access_token,
                "refreshToken": refresh_token,
            },
            "id_token": "id-token-only-in-log",
            "api_key": "api-key-only-in-log",
            "metadata": {"id": "ordinary-metadata-id", "name": "provider"},
        }
    ).encode("utf-8")
    adapter = CodexRuntimeAdapter(repository_root=ROOT)
    adapter._remember_secret(payload)
    (tmp_path / "events.jsonl").write_bytes(b"turn event: " + access_token.encode())

    result = audit_private_artifacts(tmp_path, adapter._secret_audit_values)

    assert result["match_count"] == 1
    assert result["matched_secret_count"] == 1
    assert access_token not in repr(result)
    assert refresh_token not in repr(result)


def _barrier_fixture(tmp_path: Path) -> tuple[CodexRuntimeAdapter, _Agent, int, object]:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    home, work, skills = (tmp_path / name for name in ("home", "work", "skills"))
    for path in (home, work, skills):
        path.mkdir(mode=0o700)
    auth = home / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    read_fd, write_fd = os.pipe()
    stream = os.fdopen(read_fd, "r", encoding="utf-8")
    process = SimpleNamespace(stdin=StringIO(), stdout=stream)
    agent = _Agent(
        "coordinator",
        _load_package(ROOT, "coordinator"),
        home,
        work,
        skills,
        process=process,
        thread_id="thread-1",
        auth_path=auth,
        auth_barrier_pending=True,
    )
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    adapter._run_root = tmp_path
    return adapter, agent, write_fd, stream


def test_first_turn_barrier_buffers_notifications_and_unlinks_before_tool_response(
    tmp_path: Path,
) -> None:
    adapter, agent, write_fd, stream = _barrier_fixture(tmp_path)
    request_id = 99

    def server() -> None:
        ordinary = {"method": "turn/started", "params": {"turn": {"id": "turn-1"}}}
        server_request = {
            "id": request_id,
            "method": "item/tool/call",
            "params": {"tool": "mcp__unknown__tool", "arguments": {}},
        }
        os.write(write_fd, (json.dumps(ordinary) + "\n").encode())
        os.write(write_fd, (json.dumps(server_request) + "\n").encode())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if f'"id": {request_id}' in agent.process.stdin.getvalue():
                break
            time.sleep(0.01)
        os.write(
            write_fd,
            (json.dumps({"id": 1, "result": {"turn": {"id": "turn-1"}}}) + "\n").encode(),
        )

    thread = threading.Thread(target=server)
    thread.start()
    try:
        result = adapter._rpc(agent, "turn/start", {})
    finally:
        thread.join(timeout=2)
        os.close(write_fd)
        stream.close()
    assert result == {"turn": {"id": "turn-1"}}
    assert not agent.auth_path.exists()
    assert agent.auth_unlinked_monotonic is not None
    assert agent.first_dispatch_monotonic is not None
    assert agent.auth_unlinked_monotonic <= agent.first_dispatch_monotonic
    evidence = (tmp_path / "evidence" / "app-server-events.jsonl").read_text()
    assert evidence.count('"method": "turn/started"') == 1
    assert evidence.count('"method": "item/tool/call"') == 1
    responses = [json.loads(line) for line in agent.process.stdin.getvalue().splitlines()]
    assert next(item for item in responses if item.get("id") == request_id)["result"]["success"] is False


@pytest.mark.parametrize(
    ("method", "params", "assertion"),
    [
        (
            "item/commandExecution/requestApproval",
            {},
            lambda response: response["result"]["decision"] == "decline",
        ),
        (
            "item/fileChange/requestApproval",
            {},
            lambda response: response["result"]["decision"] == "decline",
        ),
        (
            "item/permissions/requestApproval",
            {},
            lambda response: response["result"]["decision"] == "decline",
        ),
        (
            "item/tool/requestUserInput",
            {},
            lambda response: response["result"]["answers"] == {},
        ),
        (
            "mcpServer/elicitation/request",
            {"serverName": "unexpected", "requestedSchema": {}},
            lambda response: response["result"]["action"] == "decline",
        ),
        (
            "unknown/server/request",
            {},
            lambda response: response["error"]["code"] == -32601,
        ),
    ],
)
def test_first_turn_barrier_fail_closed_server_requests_do_not_deadlock(
    tmp_path: Path, method: str, params: dict[str, object], assertion
) -> None:
    adapter, agent, write_fd, stream = _barrier_fixture(tmp_path)
    request_id = 41

    def server() -> None:
        os.write(
            write_fd,
            (
                json.dumps({"id": request_id, "method": method, "params": params})
                + "\n"
            ).encode(),
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if f'"id": {request_id}' in agent.process.stdin.getvalue():
                break
            time.sleep(0.01)
        os.write(
            write_fd,
            (json.dumps({"id": 1, "result": {"turn": {"id": "turn-1"}}}) + "\n").encode(),
        )

    thread = threading.Thread(target=server)
    thread.start()
    try:
        adapter._rpc(agent, "turn/start", {})
    finally:
        thread.join(timeout=2)
        os.close(write_fd)
        stream.close()
    responses = [json.loads(line) for line in agent.process.stdin.getvalue().splitlines()]
    response = next(item for item in responses if item.get("id") == request_id)
    assert assertion(response)
    assert not agent.auth_path.exists()


def test_host_auth_requires_owner_private_regular_file(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700)
    auth = codex_home / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    with pytest.raises(CodexRuntimeError, match="owner-private"):
        CodexRuntimeAdapter.preflight_host_auth()
    auth.chmod(0o600)
    assert CodexRuntimeAdapter.preflight_host_auth() == auth


def test_private_auth_staging_is_exclusive_and_removes_copy_failure(tmp_path: Path) -> None:
    source = tmp_path / "host-auth.json"
    source.write_bytes(b"{}")
    target = tmp_path / "home" / "auth.json"
    target.parent.mkdir(mode=0o700)
    target.write_bytes(b"existing")
    with pytest.raises(CodexRuntimeError, match="destination is occupied"):
        CodexRuntimeAdapter._stage_private_auth(source, target)
    assert target.read_bytes() == b"existing"

    target.unlink()
    with patch(
        "modeling_team.runtimes.codex._copy_private",
        side_effect=OSError("synthetic copy failure"),
    ):
        with pytest.raises(CodexRuntimeError, match="staging failed"):
            CodexRuntimeAdapter._stage_private_auth(source, target)
    assert not target.exists()
