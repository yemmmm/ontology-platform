"""Real worker/import/compiler and CLI contracts, without provider or platform calls."""

import json
import subprocess

import pytest

from ontoweave_modeling.cli import main
from ontoweave_modeling.contracts import FrameworkError, TaskBinding, write_json
from ontoweave_modeling.host_bridge import HostBridge


def test_backend_worker_reuses_mechanics_without_loading_legacy_runner(tmp_path):
    bridge = HostBridge(tmp_path / "run")
    assert bridge.call("inspect") == {
        "runner_loaded": False,
        "compiler": "compile_model_changes",
        "executor": "DirectModelExecutor",
        "bootstrap": "bootstrap_helpers",
    }
    assert not (tmp_path / "run").exists()
    with pytest.raises(FrameworkError, match="host_operation_not_allowed"):
        bridge.call("arbitrary_python", {"source": "print('not allowed')"})


def test_host_worker_compiles_once_and_preserves_frozen_plan(task_file, tmp_path):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    bridge = HostBridge(binding.root)
    program = r"""
import json, sys
from types import SimpleNamespace
from pathlib import Path
from ontoweave_modeling.contracts import TaskBinding
from modeling_team.v5.host.worker import PlatformWorker
import modeling_team.direct_modeling as compiler
worker = PlatformWorker(TaskBinding.load(Path(sys.argv[1])))
worker.scope = lambda: SimpleNamespace(ontology_id="ontology")
worker.save_scope = lambda scope: None
worker.forwarder = lambda scope: SimpleNamespace(stop=lambda: None)
class Executor:
    def execute(self, batches, source_map):
        return {"status":"completed", "batches":[], "errors":[], "pending_changes":[]}
worker.executor = lambda *args, **kwargs: Executor()
request = {"schema_version":"r4-3-025-model-changes/v1", "candidate_ref":None, "changes":[{
    "change_id":"definition-a", "action":"create", "resource_kind":"class", "item_id":None,
    "target_ref":None, "fields":{"name":"Definition A", "description":"A generic definition",
                                  "semantic_definition":{"semantic_role":"object",
                                      "business_meaning":"Approved business meaning",
                                      "applicability":"This bounded test", "unknowns":[]}}}]}
payload = {"operation_id":"operation-a", "candidate":None, "changes":request}
worker.apply(payload)
plan_path = worker.root / "operations/operation-a/compiled.json"
original = plan_path.read_bytes()
def must_not_recompile(*args, **kwargs):
    raise AssertionError("original frozen plan must be reused")
compiler.compile_model_changes = must_not_recompile
worker.apply(payload)
assert plan_path.read_bytes() == original
assert "modeling_team.runner" not in sys.modules
print(json.dumps({"reused_plan":True, "batches":len(json.loads(original)["batches"])}))
"""
    process = subprocess.run(
        [bridge.command[0], "-c", program, str(binding.root)],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {"reused_plan": True, "batches": 1}


def test_old_public_exports_and_cli_bootstrap_remain_compatible(tmp_path):
    bridge = HostBridge(tmp_path)
    program = """
import sys
from modeling_team import TeamConfigurationError, load_team_configuration
assert 'modeling_team.runner' not in sys.modules
from modeling_team import TeamRunner
from modeling_team.runner import TeamRunner as CanonicalRunner
from modeling_team import __main__ as cli
assert TeamRunner is CanonicalRunner
cli.bootstrap_helpers = lambda root: ('create', 'revoke')
assert cli._bootstrap_helpers(None) == ('create', 'revoke')
print('compatible')
"""
    process = subprocess.run(
        [bridge.command[0], "-c", program],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "compatible"


def test_prepare_status_and_controls_use_real_postgres_without_live_calls(
    task_file,
    tmp_path,
    workspace,
    monkeypatch,
    capsys,
):
    def no_live_calls(*_):
        raise AssertionError("preparation/status/control must not call platform or model")

    monkeypatch.setattr(HostBridge, "call", no_live_calls)
    config = tmp_path / "postgres.json"
    write_json(config, workspace.connection)
    root = tmp_path / "run"
    arguments = ["--run-dir", str(root)]
    assert (
        main(
            [
                "start",
                *arguments,
                "--task",
                str(task_file),
                "--postgres-config",
                str(config),
                "--workspace-schema",
                workspace.schema,
                "--checkpoint-schema",
                workspace.schema + "_cp",
                "--prepare-only",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["result"]["status"] == "prepared"
    assert main(["status", *arguments]) == 0
    assert (
        json.loads(capsys.readouterr().out)["result"]["work"]["semantic_acceptance"] == "unverified"
    )
    assert main(["pause", *arguments]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["control"]["mode"] == "paused"
    assert main(["stop", *arguments]) == 0
    capsys.readouterr()
    assert main(["resume", *arguments]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "task_stopped"
    assert (root / "private-runtime.json").stat().st_mode & 0o077 == 0


def test_checkpoint_namespace_rejection_precedes_any_write(tmp_path, capsys):
    root = tmp_path / "must-not-exist"
    assert (
        main(
            [
                "start",
                "--run-dir",
                str(root),
                "--task",
                "missing",
                "--postgres-config",
                "missing",
                "--workspace-schema",
                "same",
                "--checkpoint-schema",
                "same",
            ]
        )
        == 2
    )
    assert (
        json.loads(capsys.readouterr().out)["error"]["code"]
        == "checkpoint_namespace_must_be_separate"
    )
    assert not root.exists()
