"""Public state identity follows prepared scope, including real topology expansion."""

import json
from types import SimpleNamespace

from modeling_team.runner import TeamRunner
from modeling_team.platform_scope import PlatformScope
from modeling_team.tests.test_platform_scope import ScopeClient


def runner(tmp_path):
    item = TeamRunner.__new__(TeamRunner)
    item.run = SimpleNamespace(root=tmp_path, run_id="new-run", scope={"project_id": "requested"})
    item.scope = None
    item._unified_graph = False
    item._append_evidence = lambda *_args: None
    item._deliver_multi_slice_ontology_ids = lambda *_args: None
    return item


def state(tmp_path):
    return json.loads((tmp_path / "state.json").read_text())


def test_state_does_not_use_unprepared_request_identity(tmp_path):
    item = runner(tmp_path)
    item._state("STARTING")
    assert "platform_binding" not in state(tmp_path)
    item.scope = SimpleNamespace(
        project_id="created-project", ontology_id="created-ontology", ontology_ids=[]
    )
    item._state("RUNNING", identities=["modeling"], note="retained")
    value = state(tmp_path)
    assert value["platform_binding"] == {
        "project_id": "created-project",
        "ontology_ids": ["created-ontology"],
    }
    assert "requested" not in json.dumps(value)


def test_created_scope_binding_uses_actual_platform_return_ids(tmp_path):
    item = runner(tmp_path)
    scope = PlatformScope(
        "http://fixture",
        "new-run",
        lambda: ("fixture-key", "fixture-key-id"),
        lambda _: True,
        ScopeClient(),
    )
    scope.prepare(
        {"mode": "create", "project_id": "untrusted-request", "ontology_id": "untrusted-request"}
    )
    item.scope = scope
    item._state("RUNNING")
    assert state(tmp_path)["platform_binding"] == {
        "project_id": "project-1",
        "ontology_ids": ["ontology-1"],
    }
    assert "fixture-key" not in json.dumps(state(tmp_path))


def test_real_topology_success_updates_running_scope_and_preserves_extra(tmp_path):
    item = runner(tmp_path)
    scope = SimpleNamespace(project_id="actual", ontology_id="first", ontology_ids=[])

    def apply(plan):
        assert plan == [{"name": "first"}, {"name": "second"}]
        scope.ontology_ids = ["first", "second"]
        return scope.ontology_ids

    scope.apply_ontology_plan = apply
    scope.read_protocol_context = lambda: {"ontology_ids": scope.ontology_ids}
    item.scope = scope
    item._state("RUNNING", identities=["modeling"], pending_decision="retained")
    item._apply_multi_slice_ontology_plan(
        {"ontology_plan": [{"name": "first"}, {"name": "second"}]}
    )
    value = state(tmp_path)
    assert value["state"] == "RUNNING"
    assert value["pending_decision"] == "retained" and value["identities"] == ["modeling"]
    assert value["platform_binding"]["ontology_ids"] == ["first", "second"]
    assert item.run.protocol_context["ontology_ids"] == ["first", "second"]
