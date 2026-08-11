from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

import modeling_team.runtimes.codex as codex_runtime
from modeling_team.contracts import _load_package, repository_root
from modeling_team.runtimes.codex import (
    CodexRuntimeAdapter,
    CodexRuntimeError,
    _Agent,
    audit_private_artifacts,
)


def _agent(root: Path, role: str) -> _Agent:
    home, work, skills = (root / role / name for name in ("home", "work", "skills"))
    for path in (home, work, skills):
        path.mkdir(parents=True, mode=0o700)
    return _Agent(role, _load_package(repository_root(), role), home, work, skills)


class _Proxy:
    def __init__(
        self,
        key: bytes,
        *,
        stop_result: bool = True,
        thread_alive: bool = False,
        socket_open: bool = False,
    ) -> None:
        self.key = key
        self.stop_result = stop_result
        self.thread_alive = thread_alive
        self.socket_open = socket_open
        self.stop_calls = 0
        self.audit_observed = False

    def snapshot(self) -> dict[str, bool]:
        return {"listening": True}

    def secret_snapshot(self) -> bytes:
        self.audit_observed = bool(self.key)
        return self.key

    def stop_snapshot(self) -> dict[str, bool]:
        return {
            "lifecycle_failure": not self.stop_result or self.thread_alive or self.socket_open,
            "thread_alive": self.thread_alive,
            "socket_open": self.socket_open,
        }

    def stop(self) -> bool:
        self.stop_calls += 1
        self.key = b""
        return self.stop_result

    def clear_secret(self) -> None:
        self.key = b""


def test_audit_oserror_is_additive_and_fail_closed(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "events.jsonl"
    target.write_bytes(b"sentinel")
    original = Path.read_bytes

    def fail_read(path: Path) -> bytes:
        if path == target:
            raise OSError("synthetic read failure")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    result = audit_private_artifacts(tmp_path, [b"sentinel"])
    assert result["match_count"] == 0
    assert result["scan_complete"] is False
    assert result["scan_error_count"] == 1


def test_formal_cleanup_unlinks_modeling_read_proxy_token_and_audits_token_suffix(
    tmp_path: Path,
) -> None:
    sentinel = b"modeling-read-proxy-secret"
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    agent = _agent(tmp_path, "modeling")
    token_path = agent.home / "modeling-read-proxy.token"
    token_path.write_bytes(sentinel)

    before = audit_private_artifacts(agent.home, [sentinel])
    assert before["match_count"] == 1
    assert "modeling-read-proxy.token" in codex_runtime._PRIVATE_FORMAL_AGENT_ARTIFACT_NAMES
    assert ".token" in codex_runtime._SECRET_AUDIT_SUFFIXES

    assert adapter._stop_agent_for_cleanup(
        agent,
        codex_runtime._PRIVATE_FORMAL_AGENT_ARTIFACT_NAMES,
        [],
    )
    assert not token_path.exists()
    after = audit_private_artifacts(agent.home, [sentinel])
    assert after["match_count"] == 0
    assert after["matched_secret_count"] == 0


def test_formal_cleanup_audits_once_before_proxy_wipe_and_projects_safe_counts(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "run"
    sentinel = b"formal-cleanup-sentinel"
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = True
    adapter._run_root = run_root
    adapter._secret_audit_values.append(sentinel)
    proxy = _Proxy(sentinel)
    adapter._formal_provider_proxy = proxy  # type: ignore[assignment]
    agents = [_agent(run_root, role) for role in ("coordinator", "modeling")]
    for agent in agents:
        adapter.agents[agent.agent_id] = agent
        (agent.home / "config.toml").write_bytes(sentinel)
        (agent.home / "session.jsonl").write_bytes(sentinel)

    calls = 0
    original_audit = codex_runtime.audit_private_artifacts

    def observe_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        assert all(not (agent.home / "config.toml").exists() for agent in agents)
        assert proxy.key == sentinel
        return original_audit(*args, **kwargs)

    monkeypatch.setattr(codex_runtime, "audit_private_artifacts", observe_once)
    adapter.stop()
    evidence = adapter.cleanup_identifiers()
    assert calls == 1
    assert proxy.stop_calls == 1
    assert proxy.key == b""
    assert evidence["aggregate_secret_audit"]["private_credentials_destroyed"] is False
    assert evidence["aggregate_secret_audit"]["secret_audit"]["match_count"] == 2
    assert evidence["aggregate_secret_audit"]["secret_audit"]["matched_secret_count"] == 1
    assert evidence["aggregate_secret_audit"]["match_count"] == 2
    assert evidence["aggregate_secret_audit"]["matched_secret_count"] == 1
    assert "matched_secret_digests" not in evidence["aggregate_secret_audit"]["secret_audit"]
    assert "matched_surfaces" not in evidence["aggregate_secret_audit"]["secret_audit"]
    assert all(
        not evidence[role]["private_credentials_destroyed"]
        for role in ("coordinator", "modeling")
    )
    assert sentinel.decode() not in repr(evidence)
    first = deepcopy(evidence)
    evidence["aggregate_secret_audit"]["secret_audit"]["match_count"] = 0
    adapter.stop()
    assert adapter.cleanup_identifiers() == first


def test_formal_proxy_stop_failure_fails_all_roles(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = True
    proxy = _Proxy(b"key", stop_result=False)
    adapter._formal_provider_proxy = proxy  # type: ignore[assignment]
    for role in ("coordinator", "modeling", "protocol", "acceptance"):
        agent = _agent(tmp_path, role)
        adapter.agents[role] = agent
    adapter.stop()
    evidence = adapter.cleanup_identifiers()
    assert evidence["aggregate_secret_audit"]["private_credentials_destroyed"] is False
    assert evidence["aggregate_secret_audit"]["proxy"]["lifecycle_failure"] is True
    assert all(
        not evidence[role]["private_credentials_destroyed"]
        for role in ("coordinator", "modeling", "protocol", "acceptance")
    )
    assert proxy.key == b""


def test_formal_proxy_residue_status_fails_all_roles_and_wipes_key(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = True
    proxy = _Proxy(b"key", thread_alive=True, socket_open=True)
    adapter._formal_provider_proxy = proxy  # type: ignore[assignment]
    for role in ("coordinator", "modeling", "protocol", "acceptance"):
        agent = _agent(tmp_path, role)
        adapter.agents[role] = agent
    adapter.stop()
    evidence = adapter.cleanup_identifiers()
    assert evidence["aggregate_secret_audit"]["private_credentials_destroyed"] is False
    assert evidence["aggregate_secret_audit"]["proxy"]["thread_alive"] is True
    assert evidence["aggregate_secret_audit"]["proxy"]["socket_open"] is True
    assert proxy.key == b""


def test_protocol_temporary_config_is_unlinked_before_clean_aggregate(tmp_path: Path) -> None:
    sentinel = b"temporary-protocol-key"
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = True
    adapter._run_root = tmp_path
    adapter._secret_audit_values.append(sentinel)
    adapter._formal_provider_proxy = _Proxy(sentinel)  # type: ignore[assignment]
    protocol = _agent(tmp_path, "protocol")
    adapter.agents[protocol.agent_id] = protocol
    (protocol.home / "config.toml").write_bytes(sentinel)
    adapter.stop()
    evidence = adapter.cleanup_identifiers()
    aggregate = evidence["aggregate_secret_audit"]
    assert not (protocol.home / "config.toml").exists()
    assert aggregate["private_credentials_destroyed"] is True
    assert aggregate["secret_audit"]["match_count"] == 0
    assert aggregate["secret_audit"]["matched_secret_count"] == 0


class _ResidueResource:
    def __init__(self, private_root: Path) -> None:
        self.spec = {"private_root": str(private_root)}
        self.destroyed = False

    def stop(self) -> None:
        return None

    def destroy(self) -> None:
        raise OSError("synthetic destroy failure")


def test_child_destroy_residue_is_safe_and_fail_closed(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = True
    adapter._run_root = tmp_path
    adapter._formal_provider_proxy = _Proxy(b"key")  # type: ignore[assignment]
    adapter._acceptance_children["child-digest"] = _ResidueResource(tmp_path / "child")
    adapter.stop()
    evidence = adapter.cleanup_identifiers()
    assert evidence["acceptance_children"]["zero_residue"] is False
    assert "child:child-digest" in evidence["acceptance_children"]["errors"]
    assert evidence["aggregate_secret_audit"]["private_credentials_destroyed"] is False


def test_nonformal_projection_has_no_formal_aggregate_key(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    agent = _agent(tmp_path, "modeling")
    adapter.agents[agent.agent_id] = agent
    adapter.stop()
    assert "aggregate_secret_audit" not in adapter.cleanup_identifiers()


def test_cleanup_then_next_lifecycle_resets_snapshot(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    old = _agent(tmp_path / "old", "modeling")
    adapter.agents[old.agent_id] = old
    adapter.stop()
    assert adapter._cleanup_snapshot is not None
    run = SimpleNamespace(
        root=tmp_path / "next",
        run_id="next-run",
        configuration=SimpleNamespace(
            task=SimpleNamespace(task_id="legacy", schema_version=1),
            profile=SimpleNamespace(profile_id="legacy", parameters={}),
        ),
        acceptance=None,
        scope={},
    )
    assert adapter.start_roster(run, []) == []
    assert adapter._cleanup_snapshot is None
    assert adapter.agents == {}


def test_formal_active_lifecycle_is_fail_closed(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=repository_root())
    adapter._coordination_enabled = True
    agent = _agent(tmp_path, "coordinator")
    agent.process = SimpleNamespace(poll=lambda: None)
    adapter.agents[agent.agent_id] = agent
    evidence = adapter.cleanup_identifiers()
    assert evidence["aggregate_secret_audit"]["active_resources"] is True
    assert evidence["aggregate_secret_audit"]["private_credentials_destroyed"] is False
    run = SimpleNamespace(
        root=tmp_path / "next",
        run_id="next-run",
        configuration=SimpleNamespace(
            task=SimpleNamespace(task_id="legacy", schema_version=1),
            profile=SimpleNamespace(profile_id="legacy", parameters={}),
        ),
        acceptance=None,
        scope={},
    )
    with pytest.raises(CodexRuntimeError, match="active resources"):
        adapter.start_roster(run, [])
