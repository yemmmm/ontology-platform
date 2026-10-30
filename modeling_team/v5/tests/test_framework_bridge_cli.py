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


def test_host_resolves_existing_reference_from_authorized_native_read(task_file, tmp_path):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    bridge = HostBridge(binding.root)
    program = r"""
import sys
from pathlib import Path
from types import SimpleNamespace
from ontoweave_modeling.contracts import TaskBinding, FrameworkError
from modeling_team.v5.host.worker import PlatformWorker
from modeling_team.direct_modeling import compile_model_changes
worker=PlatformWorker(TaskBinding.load(Path(sys.argv[1])))
iri="https://example.test/model/a-meaning-not-a-native-id"
calls=[]
def read(method,path):
    calls.append((method,path))
    return {"model_revision":7,"items":[{"id":"native-42","iri":iri}]}
scope=SimpleNamespace(ontology_ids=["ontology"],ontology_id="ontology",_ok=read)
ref={"artifact_ref":"model-read:class-detail:ontology","path":"/"+iri}
binding=worker.read_binding(scope,ref)
assert binding["resource_id"]=="native-42" and binding["resource_iri"]==iri
request={"schema_version":"r4-3-025-model-changes/v1","candidate_ref":None,"changes":[{
    "change_id":"update-existing","action":"update","resource_kind":"class",
    "item_id":None,"target_ref":ref,"fields":{"name":"Updated authorized concept"}}]}
batches,_=compile_model_changes(request,candidate=None,ontology_by_item={"update-existing":"ontology"},resolve_binding=lambda value:worker.read_binding(scope,value))
assert batches[0]["items"][0]["payload"]["class_iri"]==iri
try:
    worker.read_binding(scope,{"artifact_ref":"model-read:class-detail:another-ontology","path":"/"+iri})
except FrameworkError as error:
    assert error.code=="reference_scope_forbidden"
else:
    raise AssertionError("outside ontology scope")
assert len(calls)==2
print("native-read-identity-verified")
"""
    result = subprocess.run(
        [bridge.command[0], "-c", program, str(binding.root)],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "native-read-identity-verified"


def test_model_tool_projection_keeps_mcp_calls_and_removes_unused_resource_facade(tmp_path):
    bridge = HostBridge(tmp_path)
    program = """
from modeling_team.v5.host.worker import model_tool_projection
tools = [
    {"type":"namespace","name":"functions","tools":[
        {"name":"read_mcp_resource"}, {"name":"list_mcp_resources"},
        {"name":"mcp__workspace__read_material"}]},
    {"name":"list_mcp_resource_templates"},
    {"name":"mcp__workspace__read_handoff_material"},
]
expected = [
    {"type":"namespace","name":"functions","tools":[
        {"name":"mcp__workspace__read_material"}]},
    {"name":"mcp__workspace__read_handoff_material"},
]
assert model_tool_projection(tools) == expected
assert len(tools[0]["tools"]) == 3
print("configured-tools-only")
"""
    process = subprocess.run(
        [bridge.command[0], "-c", program],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "configured-tools-only"


def test_host_closes_prior_apply_session_before_followup_and_preserves_unknown_outcomes(
    task_file, tmp_path
):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    bridge = HostBridge(binding.root)
    program = r"""
import json, sys
from pathlib import Path
from types import SimpleNamespace
from ontoweave_modeling.contracts import TaskBinding, FrameworkError, write_json
from modeling_team.v5.host.worker import PlatformWorker
worker=PlatformWorker(TaskBinding.load(Path(sys.argv[1])))
scope=SimpleNamespace(ontology_id="ontology")
worker.scope=lambda:scope
worker.save_scope=lambda value:None
worker.forwarder=lambda value:SimpleNamespace(stop=lambda:None)
worker.snapshot=lambda:{"model_revisions":{"ontology":2}}
events=[]
class Executor:
    def __init__(self, root): self.root,self.session_id=root,None
    def _load_records(self): return ([{"ordinal":1}],[])
    def _load_snapshot(self,intent): return {"batch":{"ontology_id":"ontology","session_id":self.root.name}}
    def _adopt_snapshot_context(self,snapshot,ontology):
        assert ontology=="ontology"
        self.session_id=snapshot["batch"]["session_id"]
    def _refresh_session_revision(self): assert self.session_id==self.root.name
    def close_session(self):
        assert self.session_id==self.root.name
        events.append("close:"+self.root.name)
        return {"closed":True,"session_id":self.root.name}
    def execute(self,batches,source_map):
        assert events==["close:first"]
        events.append("apply:second")
        return {"status":"completed","batches":[],"errors":[],"pending_changes":[]}
worker.executor=lambda scope,root,*args,**kwargs:Executor(root)
first=worker.root/"operations/first"
write_json(first/"compiled.json",{})
write_json(first/"result.json",{"status":"completed","batches":[]})
rejected=worker.root/"operations/rejected"
write_json(rejected/"compiled.json",{})
write_json(rejected/"result.json",{"status":"not_written","errors":[{"code":"ontology_lease_conflict"}]})
request={"schema_version":"r4-3-025-model-changes/v1","candidate_ref":None,"changes":[{
    "change_id":"second-definition","action":"create","resource_kind":"class",
    "item_id":None,"target_ref":None,"fields":{"name":"Second definition"}}]}
result=worker.apply({"operation_id":"second","candidate":None,"changes":request})
assert result["status"]=="completed"
assert worker.finalize()=={"model_revisions":{"ontology":2}}
assert events==["close:first","apply:second","close:second"]
write_json(worker.root/"operations/unknown/compiled.json",{})
try: worker.finalize()
except FrameworkError as error: assert error.code=="application_outcome_unknown"
else: raise AssertionError("an unknown write must remain unresolved")
print("completed-session-closed-and-unknown-preserved")
"""
    process = subprocess.run(
        [bridge.command[0], "-c", program, str(binding.root)],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "completed-session-closed-and-unknown-preserved"


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


def test_multiple_authorized_ontologies_need_explicit_create_placement_and_keep_update_identity(
    task_file, tmp_path
):
    binding = TaskBinding.prepare(task_file, tmp_path / "multi-run")
    bridge = HostBridge(binding.root)
    program = r"""
import json,sys
from pathlib import Path
from types import SimpleNamespace
from ontoweave_modeling.contracts import TaskBinding
from modeling_team.v5.host.worker import PlatformWorker
import modeling_team.direct_binding as direct
w=PlatformWorker(TaskBinding.load(Path(sys.argv[1])))
w.scope=lambda:SimpleNamespace(ontology_id="one",ontology_ids=["one","two"])
w.save_scope=lambda scope:None
w.forwarder=lambda scope:SimpleNamespace(stop=lambda:None)
w.executor=lambda *a,**k:None
w._close_applied_sessions=lambda *a,**k:None
def execute(executor,batches,source_map):
    return {"status":"completed","batches":[{"ontology_id":b["ontology_id"],"resource_bindings":[
        {"change_id":i["client_item_id"],"resource_kind":"class",**({} if i["client_item_id"].startswith("update-") else
          {"resource_id":"urn:class:"+i["client_item_id"],"resource_iri":"urn:class:"+i["client_item_id"]})}
        for i in b["items"]]} for b in batches]}
direct.execute_bound_model_changes=execute
def create(key):
    return {"change_id":key,"action":"create","resource_kind":"class","item_id":None,"target_ref":None,"fields":{"name":key,"description":"Approved definition"}}
request={"schema_version":"r4-3-025-model-changes/v1","candidate_ref":None,"changes":[create("a"),create("b")]}
def call(key,targets=None):
    return w.apply({"operation_id":key,"candidate":None,"changes":request,"ontology_targets":targets})
missing=call("missing")
assert missing["status"]=="not_written" and any(e["code"]=="scope_binding_required" for e in missing["errors"])
assert call("outside",{"a":"forbidden","b":"two"})["errors"][0]["code"]=="ontology_target_forbidden"
result=call("placed",{"a":"one","b":"two"})
assert {b["ontology_id"] for b in result["batches"]}=={"one","two"}
bindings=json.loads((w.root/"applied-bindings.json").read_text())
assert bindings["b"]["ontology_id"]=="two"
request["changes"]=[{"change_id":"update-b","action":"update","resource_kind":"class","item_id":None,
"target_ref":{"artifact_ref":"applied-bindings.json","path":"/b"},"fields":{"description":"Revised definition"}}]
update=call("updated")
assert update["batches"][0]["ontology_id"]=="two"
assert json.loads((w.root/"applied-bindings.json").read_text())["update-b"]["resource_iri"]=="urn:class:b"
assert call("conflict",{"update-b":"one"})["errors"][0]["code"]=="ontology_target_conflict"
print(json.dumps({"placed":True,"updated_second":True}))
"""
    process = subprocess.run(
        [bridge.command[0], "-c", program, str(binding.root)],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {"placed": True, "updated_second": True}


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


def test_snapshot_references_compile_followup_against_existing_resources(task_file, tmp_path):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    bridge = HostBridge(binding.root)
    program = r"""
import json, sys
from types import SimpleNamespace
from pathlib import Path
from ontoweave_modeling.contracts import TaskBinding, write_json
from modeling_team.v5.host.worker import PlatformWorker
worker = PlatformWorker(TaskBinding.load(Path(sys.argv[1])))
worker.scope = lambda: SimpleNamespace(ontology_id="ontology", ontology_ids=[],
                                      project_id="project", protocol_key="test-key")
worker.save_scope = lambda scope: None
worker.forwarder = lambda scope: SimpleNamespace(stop=lambda: None,
    forward=lambda *args: {"data":{"workspace":{"model_revision":1}}})
class Executor:
    def execute(self, batches, source_map):
        return {"status":"completed", "batches":[], "errors":[], "pending_changes":[]}
worker.executor = lambda *args, **kwargs: Executor()
left, right = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
write_json(worker.root / "applied-bindings.json", {
    "left": {"resource_kind":"class", "resource_id":left, "resource_iri":"urn:left"},
    "right": {"resource_kind":"class", "resource_id":right, "resource_iri":"urn:right"}})
snapshot = worker.snapshot()
refs = snapshot["resource_refs"]
request = {"schema_version":"r4-3-025-model-changes/v1", "candidate_ref":None, "changes":[{
    "change_id":"followup", "action":"create", "resource_kind":"relation_type", "item_id":None,
    "target_ref":None, "fields":{"name":"Related to",
        "source_class_id":{"existing_resource_ref":refs["left"]},
        "target_class_id":{"existing_resource_ref":refs["right"]}}}]}
result = worker.apply({"operation_id":"followup", "candidate":None, "changes":request})
assert result["status"] == "completed", result
compiled = json.loads((worker.root / "operations/followup/compiled.json").read_text())
payload = compiled["batches"][0]["items"][0]["payload"]
assert payload["source_class_id"] == left and payload["target_class_id"] == right, payload
print("existing-resource-followup-compiled")
"""
    process = subprocess.run(
        [bridge.command[0], "-c", program, str(binding.root)],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "existing-resource-followup-compiled"


def test_cleanup_resource_retention_does_not_infer_legacy_producer_failure(task_file, tmp_path):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    bridge = HostBridge(binding.root)
    program = r"""
import json, sys
from types import SimpleNamespace
from pathlib import Path
from ontoweave_modeling.contracts import TaskBinding
from modeling_team.v5.host.worker import PlatformWorker
worker = PlatformWorker(TaskBinding.load(Path(sys.argv[1])))
scope = SimpleNamespace(cleanup=lambda: {
    "scope_disposition":"failed-written-retained", "sessions_terminal":True,
    "no_in_flight_attempts":True, "aggregate_keys_non_active":True})
worker.scope = lambda: scope
worker.save_scope = lambda scope: None
result = worker.cleanup()
assert result["scope_disposition"] == "written-retained", result
assert result["legacy_scope_disposition"] == "failed-written-retained"
assert result["aggregate_keys_non_active"] and result["no_in_flight_attempts"]
assert scope.scope_disposition == "written-retained"
print("resource-retention-is-not-a-semantic-verdict")
"""
    process = subprocess.run(
        [bridge.command[0], "-c", program, str(binding.root)],
        env=bridge.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "resource-retention-is-not-a-semantic-verdict"


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


@pytest.mark.parametrize("with_receipt", [False, True])
def test_governed_iri_is_not_used_as_native_relation_endpoint(task_file, tmp_path, with_receipt):
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    bridge = HostBridge(binding.root)
    program = r'''
import json, sys
from pathlib import Path
from types import SimpleNamespace
from ontoweave_modeling.contracts import TaskBinding, write_json
from modeling_team.v5.host.worker import PlatformWorker
from modeling_team.direct_modeling import compile_model_changes, ModelChangeCompilationError
worker = PlatformWorker(TaskBinding.load(Path(sys.argv[1])))
with_receipt = sys.argv[2] == "True"
iri = "https://example.test/semantic/class/meaning"
native_id = "11111111-1111-4111-8111-111111111111"
# This is the real semantic-read-v2 shape: id is the RDF IRI, not a native ID.
scope = SimpleNamespace(ontology_ids=["ontology"], ontology_id="ontology",
    _ok=lambda *args: {"model_revision":3,"items":[{"id":iri,"iri":iri}]})
if with_receipt:
    write_json(worker.root / "applied-bindings.json", {"existing": {
        "ontology_id":"ontology", "resource_kind":"class", "resource_iri":iri,
        "resource_id":native_id}})
ref = {"artifact_ref":"model-read:class-detail:ontology", "path":"/"+iri}
actual = worker.read_binding(scope, ref)
assert actual["resource_iri"] == iri
assert actual["resource_id"] == (native_id if with_receipt else None), actual
request = {"schema_version":"r4-3-025-model-changes/v1", "candidate_ref":None, "changes":[{
    "change_id":"relation", "action":"create", "resource_kind":"relation_type",
    "item_id":None, "target_ref":None, "fields":{"name":"Related",
        "source_class_id":{"existing_resource_ref":ref},
        "target_class_id":{"existing_resource_ref":ref}}}]}
try:
    batches,_ = compile_model_changes(request,candidate=None,
        ontology_by_item={"relation":"ontology"},resolve_binding=lambda _:actual)
except ModelChangeCompilationError as error:
    assert not with_receipt
    assert "binding_identity_missing" in str(error.errors), error.errors
else:
    assert with_receipt
    payload = batches[0]["items"][0]["payload"]
    assert payload["source_class_id"] == payload["target_class_id"] == native_id, payload
print("governed-reference-native-identity-checked")
'''
    result = subprocess.run(
        [bridge.command[0], "-c", program, str(binding.root), str(with_receipt)],
        env=bridge.env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "governed-reference-native-identity-checked"
