"""R3.0-002 wiring tests: the single gate predicate and the Runner gate loop.

Covers test plan offline layers W1-W3: the unified platform-gate predicate
(both codex wiring points), the MCP env / sandbox bind-mount behavior, and the
Runner-side independent topology gate lifecycle (fail-closed start, typed
deduplicated Coordinator feedback, identity-synthesized open).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from modeling_team import __main__ as team_main
from modeling_team.contracts import TeamConfigurationError
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.tests.test_runner import CapturingAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]
CODEX_SOURCE = REPO_ROOT / "modeling_team" / "runtimes" / "codex.py"
RUNNER_SOURCE = REPO_ROOT / "modeling_team" / "runner.py"
FIXTURES = json.loads(
    (
        REPO_ROOT / "modeling_team" / "tests" / "fixtures" / "r30002-scenario-map-fixtures.json"
    ).read_text(encoding="utf-8")
)


# --- W1: one predicate covers both gate wiring points ---


def _run_double(*, schema_version, task_id="ordinary-v2", profile_id="p", parameters=None):
    return SimpleNamespace(
        root=Path("/unused"),
        run_id="run-double",
        configuration=SimpleNamespace(
            profile=SimpleNamespace(profile_id=profile_id),
            task=SimpleNamespace(
                schema_version=schema_version,
                task_id=task_id,
                parameters=parameters,
            ),
        ),
    )


def test_gate_predicate_true_for_formal_and_multi_slice_runs():
    formal = _run_double(
        schema_version=2,
        task_id="r2-3-005-formal-acceptance",
        profile_id="r2-3-005-modeling-team",
    )
    multi_slice = _run_double(
        schema_version=2,
        task_id="r3-0-002-multi-slice",
        profile_id="r3-0-002-modeling-team",
        parameters={"multi_slice_workflow": True},
    )
    assert CodexRuntimeAdapter._candidate_platform_gate_enabled_for_run(formal) is True
    assert CodexRuntimeAdapter._candidate_platform_gate_enabled_for_run(multi_slice) is True


def test_gate_predicate_false_for_ordinary_and_v1_runs():
    ordinary = _run_double(schema_version=2, parameters={})
    legacy = _run_double(schema_version=1, parameters={"multi_slice_workflow": True})
    no_parameters = _run_double(schema_version=2, parameters=None)
    assert CodexRuntimeAdapter._candidate_platform_gate_enabled_for_run(ordinary) is False
    assert CodexRuntimeAdapter._candidate_platform_gate_enabled_for_run(legacy) is False
    assert CodexRuntimeAdapter._candidate_platform_gate_enabled_for_run(no_parameters) is False


def test_both_codex_gate_wiring_points_derive_from_the_single_predicate():
    source = CODEX_SOURCE.read_text(encoding="utf-8")
    # The bind-mount flag assignment (start_roster) and the MCP env decision
    # (_write_config) must both call the one predicate.
    unified_assignment = (
        "self._candidate_platform_gate_enabled = (\n"
        "            self._candidate_platform_gate_enabled_for_run(run)\n"
        "        )"
    )
    assert source.count(unified_assignment) == 1
    assert "self._candidate_platform_gate_enabled = self._is_formal_acceptance_run" not in source
    assert source.count("_candidate_platform_gate_enabled_for_run(run)") == 2
    # The Runner drain loop re-checks the multi-slice topology gate.
    runner_source = RUNNER_SOURCE.read_text(encoding="utf-8")
    assert runner_source.count("self._check_multi_slice_topology_gate()") == 1


# --- W2: MCP env and sandbox bind-mount follow the predicate ---


def _protocol_agent(root: Path, name: str = "protocol"):
    home, work, skills = (root / f"{name}-home", root / f"{name}-work", root / f"{name}-skills")
    for path in (home, work, skills):
        path.mkdir(parents=True, mode=0o700)
    package = SimpleNamespace(role="protocol", package_id="protocol")
    from modeling_team.runtimes.codex import _Agent

    return _Agent(
        name,
        package,
        home,
        work,
        skills,
        platform_tools=frozenset({"check_platform_health"}),
        schema_version=2,
    )


def _sessions_double():
    class _SessionsDouble:
        def base_url_for(self, provider_id):
            return "http://127.0.0.1:49152"

        def listening(self):
            return True

        def snapshot(self):
            return {"deepseek-direct": {"listening": True}}

        def secret_values(self):
            return ()

        def stop(self):
            return {}

    return _SessionsDouble()


def test_multi_slice_config_and_namespace_bind_gate_read_only(monkeypatch, tmp_path):
    base = tmp_path / "multi-slice"
    base.mkdir()
    (base / "sources" / "protocol").mkdir(parents=True)
    run = _run_double(
        schema_version=2,
        task_id="r3-0-002-multi-slice",
        profile_id="r3-0-002-modeling-team",
        parameters={"multi_slice_workflow": True},
    )
    run.root = base
    run.protocol_key = "platform-key"
    agent = _protocol_agent(base)
    host_auth = base / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    host_auth.chmod(0o600)
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    adapter._write_config(run, agent)
    config = (agent.home / "config.toml").read_text(encoding="utf-8")
    assert 'FORMAL_CANDIDATE_GATE_PATH = "/opt/candidate-gate/state.json"' in config
    assert (base / "candidate-gate" / "state.json").is_file()

    adapter._run_root = base
    adapter._candidate_platform_gate_enabled = (
        adapter._candidate_platform_gate_enabled_for_run(run)
    )
    assert adapter._candidate_platform_gate_enabled is True
    command = adapter.namespace_command(agent)
    mount = ["--ro-bind", str(base / "candidate-gate"), "/opt/candidate-gate"]
    assert any(command[index : index + 3] == mount for index in range(len(command) - 2))
    adapter.stop()


def test_ordinary_v2_config_and_namespace_have_no_gate(monkeypatch, tmp_path):
    base = tmp_path / "ordinary"
    base.mkdir()
    (base / "sources" / "protocol").mkdir(parents=True)
    run = _run_double(schema_version=2, parameters={})
    run.root = base
    run.protocol_key = "platform-key"
    agent = _protocol_agent(base)
    host_auth = base / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    host_auth.chmod(0o600)
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    adapter._write_config(run, agent)
    config = (agent.home / "config.toml").read_text(encoding="utf-8")
    assert "FORMAL_CANDIDATE_GATE_PATH" not in config
    assert not (base / "candidate-gate").exists()

    adapter._run_root = base
    adapter._candidate_platform_gate_enabled = (
        adapter._candidate_platform_gate_enabled_for_run(run)
    )
    assert adapter._candidate_platform_gate_enabled is False
    command = adapter.namespace_command(agent)
    assert "/opt/candidate-gate" not in command
    adapter.stop()


# --- W3: Runner-side independent topology gate lifecycle ---


PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml"
SMOKE_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-002-multi-slice-smoke.yaml"


def _gate_state(run_root: Path) -> dict:
    return json.loads(
        (run_root / "candidate-gate" / "state.json").read_text(encoding="utf-8")
    )


def _write_artifact(run_root: Path, filename: str, payload) -> None:
    directory = run_root / "scenario-map"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _feedback_reasons(adapter: CapturingAdapter) -> list[str]:
    reasons = []
    for _agent_id, delivery in adapter.messages:
        if delivery.kind == "multi-slice-topology-gate":
            notice = json.loads(delivery.text)
            assert notice["schema_version"] == "r3-0-002-multi-slice-gate-feedback/v1"
            reasons.append(notice["reason_code"])
    return reasons


def test_runner_multi_slice_gate_lifecycle(tmp_path):
    run_id = f"r30002-gate-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]}"
    run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
    adapter = CapturingAdapter()
    runner = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=adapter,
        ledger_root=tmp_path / "ledger",
        freeze_started_at=datetime.now(UTC).isoformat(),
    )
    try:
        runner.prepare(
            run_id=run_id,
            profile_path=PROFILE,
            task_path=SMOKE_TASK,
            scope={"mode": "create"},
        )
        # Fail-closed start: the gate exists, closed on the missing artifact.
        assert runner._multi_slice_workflow is True
        assert _gate_state(run_root) == {
            "schema_version": "r2-3-005-candidate-platform-gate/v1",
            "state": "closed",
            "reason_code": "topology_missing_artifact",
        }

        # Still missing after re-check: typed feedback once, run stays alive.
        runner._check_multi_slice_topology_gate()
        runner._check_multi_slice_topology_gate()
        assert _feedback_reasons(adapter) == ["topology_missing_artifact"]
        assert runner.run is not None

        # Structurally invalid decision: gate re-closed on the typed code.
        invalid_decision = FIXTURES["topology_decision"]["invalid"]["empty_rationale"]
        _write_artifact(run_root, "topology-decision.json", invalid_decision)
        runner._check_multi_slice_topology_gate()
        assert _gate_state(run_root)["reason_code"] == "topology_empty_rationale"
        assert _feedback_reasons(adapter) == [
            "topology_missing_artifact",
            "topology_empty_rationale",
        ]
        assert runner.run is not None

        # Non-single selection without ontology_plan: registered R3.0-006 M3
        # revision, closed on the typed missing-plan code.
        _write_artifact(
            run_root,
            "topology-decision.json",
            FIXTURES["topology_decision"]["valid"],
        )
        runner._check_multi_slice_topology_gate()
        assert _gate_state(run_root)["reason_code"] == "topology_missing_ontology_plan"
        assert _feedback_reasons(adapter) == [
            "topology_missing_artifact",
            "topology_empty_rationale",
            "topology_missing_ontology_plan",
        ]

        # Decision with a plan but no scenario map yet: still closed on the
        # map (the plan's slice closure cannot be checked without it).
        _write_artifact(
            run_root,
            "topology-decision.json",
            FIXTURES["topology_decision"]["multi_ontology_plan_valid"],
        )
        runner._check_multi_slice_topology_gate()
        assert _gate_state(run_root)["reason_code"] == "map_unparsable"

        # Complete artifacts: the gate opens with the synthesized identity.
        _write_artifact(run_root, "scenario-map.json", FIXTURES["scenario_map"]["valid"])
        runner._check_multi_slice_topology_gate()
        state = _gate_state(run_root)
        assert state["state"] == "open"
        assert state["run_id"] == run_id
        assert state["protocol_agent_id"] == "protocol"
        assert state["protocol_thread_id"]
        assert state["original_delivery_id"] == f"r30002-topology:{run_id}"
        assert state["candidate_revision"] == "1"
        assert state["semantic_digest"] == hashlib.sha256(
            (run_root / "scenario-map" / "scenario-map.json").read_bytes()
        ).hexdigest()
        assert state["candidate_digest"] == hashlib.sha256(
            (run_root / "scenario-map" / "topology-decision.json").read_bytes()
        ).hexdigest()

        # Opened gates are not re-checked or re-closed by later cycles.
        feedback_before = len(_feedback_reasons(adapter))
        runner._check_multi_slice_topology_gate()
        assert _gate_state(run_root)["state"] == "open"
        assert len(_feedback_reasons(adapter)) == feedback_before
    finally:
        runner.cleanup()
        if run_root.exists():
            rmtree(run_root)


def test_runner_existing_v2_task_keeps_no_multi_slice_gate(tmp_path):
    run_id = f"r30002-conservation-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]}"
    run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
    adapter = CapturingAdapter()
    runner = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=adapter,
        ledger_root=tmp_path / "ledger",
        freeze_started_at=datetime.now(UTC).isoformat(),
    )
    try:
        runner.prepare(
            run_id=run_id,
            profile_path=REPO_ROOT / "modeling_team" / "profiles" / "base-three-agent.yaml",
            task_path=REPO_ROOT / "modeling_team" / "tasks" / "new-scope-business-slice.yaml",
            scope={"mode": "create"},
        )
        assert runner._multi_slice_workflow is False
        assert not (run_root / "candidate-gate").exists()
        # The gate check is a no-op for non-multi-slice runs.
        runner._check_multi_slice_topology_gate()
        assert adapter.messages == []
    finally:
        runner.cleanup()
        if run_root.exists():
            rmtree(run_root)


# --- W4: preview_baseline / CLI baseline dispatch (increment 6(b) completion) ---


def test_preview_baseline_accepts_multi_slice_profile_and_task():
    manifest, baseline_hash = TeamRunner.preview_baseline(
        repository_root=REPO_ROOT,
        run_id="r30002-preview-multi-slice",
        profile_path=PROFILE,
        task_path=SMOKE_TASK,
    )
    assert manifest["run_id"] == "r30002-preview-multi-slice"
    assert manifest["files"]["profile"] == hashlib.sha256(
        PROFILE.read_bytes()
    ).hexdigest()
    assert manifest["files"]["task"] == hashlib.sha256(
        SMOKE_TASK.read_bytes()
    ).hexdigest()
    assert len(baseline_hash) == 64
    assert int(baseline_hash, 16) >= 0


def test_preview_baseline_multi_slice_rejects_model_profile_selection():
    with pytest.raises(TeamConfigurationError, match="model profile selection"):
        TeamRunner.preview_baseline(
            repository_root=REPO_ROOT,
            run_id="r30002-preview-multi-slice-profile",
            profile_path=PROFILE,
            task_path=SMOKE_TASK,
            model_profile_id="any-profile",
        )


def test_preview_baseline_multi_slice_task_rejects_formal_profile():
    # The dispatch must widen the loader, not the roster: pairing the
    # multi-slice Task with the strict four-role formal Profile still fails.
    with pytest.raises(TeamConfigurationError, match="multi-slice Profile is not registered"):
        TeamRunner.preview_baseline(
            repository_root=REPO_ROOT,
            run_id="r30002-preview-crosswire",
            profile_path=REPO_ROOT
            / "modeling_team" / "profiles" / "r2-3-005-modeling-team.yaml",
            task_path=SMOKE_TASK,
        )


def test_cli_baseline_accepts_multi_slice_profile_and_task(capsys):
    argv = [
        "modeling-team",
        "baseline",
        "--run-id",
        "r30002-cli-baseline-multi-slice",
        "--profile",
        str(PROFILE),
        "--task",
        str(SMOKE_TASK),
    ]
    with patch.object(team_main.sys, "argv", argv):
        assert team_main.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "r30002-cli-baseline-multi-slice"
    assert len(payload["baseline_hash"]) == 64
    assert payload["manifest"]["run_id"] == "r30002-cli-baseline-multi-slice"


def test_cli_baseline_multi_slice_rejects_model_profile_selection(capsys):
    argv = [
        "modeling-team",
        "baseline",
        "--run-id",
        "r30002-cli-baseline-multi-slice-profile",
        "--profile",
        str(PROFILE),
        "--task",
        str(SMOKE_TASK),
        "--model-profile",
        "any-profile",
    ]
    with patch.object(team_main.sys, "argv", argv):
        assert team_main.main() == 2
    assert "model profile selection" in capsys.readouterr().err


# --- W4: R3.0-006 start3 narrow repair — Coordinator scenario-map write path ---


def _role_agent(root: Path, role: str):
    home, work, skills = (root / f"{role}-home", root / f"{role}-work", root / f"{role}-skills")
    for path in (home, work, skills):
        path.mkdir(parents=True, mode=0o700)
    package = SimpleNamespace(
        role=role,
        package_id=role,
        runtime={"codex": {"sandbox": "read-only" if role != "protocol" else "workspace-write"}},
    )
    from modeling_team.runtimes.codex import _Agent

    return _Agent(
        role,
        package,
        home,
        work,
        skills,
        platform_tools=frozenset({"check_platform_health"}) if role == "protocol" else frozenset(),
        schema_version=2,
    )


def _multi_slice_run_double():
    return _run_double(
        schema_version=2,
        task_id="r3-0-002-multi-slice",
        profile_id="r3-0-002-modeling-team",
        parameters={"multi_slice_workflow": True},
    )


def test_multi_slice_coordinator_gets_scenario_map_bind_and_workspace_write(tmp_path):
    base = tmp_path / "run"
    base.mkdir()
    (base / "scenario-map").mkdir(mode=0o700)
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    adapter._run_root = base
    adapter._multi_slice_scenario_map_enabled = adapter._is_multi_slice_run(
        _multi_slice_run_double()
    )
    coordinator = _role_agent(base, "coordinator")

    command = adapter.namespace_command(coordinator)
    mount = ["--bind", str(base / "scenario-map"), "/agent/work/scenario-map"]
    assert any(command[index : index + 3] == mount for index in range(len(command) - 2))
    assert adapter._thread_sandbox(coordinator) == "workspace-write"
    adapter.stop()


def test_multi_slice_other_roles_and_artifacts_dir_unchanged(tmp_path):
    base = tmp_path / "run"
    base.mkdir()
    (base / "scenario-map").mkdir(mode=0o700)
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    adapter._run_root = base
    adapter._multi_slice_scenario_map_enabled = True

    for role in ("modeling", "protocol"):
        agent = _role_agent(base, role)
        command = adapter.namespace_command(agent)
        assert "/agent/work/scenario-map" not in command
        # Package sandbox is preserved for non-Coordinator roles.
        assert adapter._thread_sandbox(agent) == agent.package.runtime["codex"]["sandbox"]
    adapter.stop()


def test_ordinary_runs_keep_coordinator_read_only_without_scenario_map_bind(tmp_path):
    base = tmp_path / "run"
    base.mkdir()
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    adapter._run_root = base
    adapter._multi_slice_scenario_map_enabled = adapter._is_multi_slice_run(
        _run_double(schema_version=2, parameters={})
    )
    coordinator = _role_agent(base, "coordinator")

    command = adapter.namespace_command(coordinator)
    assert "/agent/work/scenario-map" not in command
    assert adapter._thread_sandbox(coordinator) == "read-only"
    adapter.stop()


def test_scenario_map_bind_fails_closed_when_directory_missing(tmp_path):
    base = tmp_path / "run"
    base.mkdir()
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    adapter._run_root = base
    adapter._multi_slice_scenario_map_enabled = True
    coordinator = _role_agent(base, "coordinator")

    with pytest.raises(Exception, match="scenario-map directory was not prepared"):
        adapter.namespace_command(coordinator)
    adapter.stop()
