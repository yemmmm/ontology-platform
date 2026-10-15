"""Current run scope and role catalogs without a provider or semantic start."""
import os
import stat
from types import SimpleNamespace

from modeling_team import runner as runner_module
from modeling_team.capability_mcp import DIRECT_MODELING_OPERATIONS
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.tests.test_r30009_runner_wiring import _UnifiedRunner
from modeling_team.tests.test_r30008b_runner_wiring import _socket_request


def test_fresh_create_read_proxy_uses_prepared_scope_not_unbound_input(tmp_path, monkeypatch):
    staged = _UnifiedRunner(tmp_path)
    staged.prepare()
    owner = staged.runner
    assert owner.run.scope == {"mode": "create"}
    owner.scope = SimpleNamespace(project_id="P", ontology_id="O", ontology_ids=[])
    created = []

    class Lifecycle:
        def __init__(self, scope, **kwargs):
            assert scope is owner.scope

        def create(self, **kwargs):
            created.append(kwargs)
            return SimpleNamespace(key_id="read-key-id", key_digest="digest", project_id="P", ontology_id="O")

        def plaintext_for(self, key_id):
            return "read-only-key"

        def forwarder_for(self, key_id):
            return lambda tool, arguments, key: {"ok": True, "data": arguments}

    monkeypatch.setattr(runner_module, "ModelingReadKeyLifecycle", Lifecycle)
    try:
        owner._ensure_modeling_read_surface()
        assert created == [{"project_id": "P", "ontology_id": "O", "run_id": owner.run.run_id}]
        proxy = owner.run.modeling_read_proxy
        assert proxy.project_id == "P" and proxy.ontology_ids == ("O",)
        assert "Current authorized read scope" in owner._task_text("modeling")
        assert proxy.handle({"token": proxy.token, "operation": "tools/call", "tool": "get_modeling_context",
                             "arguments": {"ontology_id": "foreign"}})["ok"] is False
    finally:
        if owner._modeling_read_proxy:
            owner._modeling_read_proxy.destroy()
        owner._modeling_read_lifecycle = None
        owner.scope = None
        staged.cleanup()


def test_native_modeling_catalog_and_runtime_descriptor_agree(tmp_path):
    staged = _UnifiedRunner(tmp_path)
    staged.prepare()
    owner = staged.runner
    endpoint = owner.acceptance.capability_endpoint("modeling")
    endpoint.start()
    try:
        catalog = _socket_request(endpoint.socket_path, endpoint.token, "tools/list")
        names = {entry["name"] for entry in catalog["result"]["tools"]}
        assert names == set(DIRECT_MODELING_OPERATIONS)
        runtime = CodexRuntimeAdapter(repository_root=staged.run_root.parents[2])
        runtime._coordination_enabled = False
        runtime._acceptance = owner.acceptance
        assert set(runtime._role_capability_operations("modeling", run=owner.run)) == names
        protocol = owner.acceptance.capability_endpoint("protocol")
        rejected = protocol.handle({"id": 1, "token": protocol.token, "method": "tools/call", "params": {
            "name": "modeling_finish_changes", "arguments": {"modeling_id": "modeling"},
        }})
        assert "error" in rejected
    finally:
        endpoint.stop()
        staged.cleanup()


def test_nonformal_unified_start_binds_direct_modeling_endpoint_before_roster(tmp_path):
    staged = _UnifiedRunner(tmp_path)
    staged.prepare()
    owner = staged.runner
    observed = {}
    original_start_roster = owner.adapter.start_roster

    def probe_start_roster(run, agents):
        carrier = owner.acceptance
        assert carrier is not None
        endpoint = carrier.capability_endpoint("modeling")
        path = endpoint.socket_path
        observed["is_socket"] = path.exists() and stat.S_ISSOCK(os.lstat(path).st_mode)
        observed["tools"] = (
            [
                item["name"]
                for item in _socket_request(
                    path, carrier.capability_token("modeling"), "tools/list"
                )["result"]["tools"]
            ]
            if observed["is_socket"]
            else []
        )
        return original_start_roster(run, agents)

    owner.adapter.start_roster = probe_start_roster
    try:
        owner.start()
        descriptor = owner.acceptance.capability_descriptors["modeling"]
        assert observed["is_socket"] is True
        assert observed["tools"] == descriptor["operations"]
    finally:
        staged.cleanup()


def test_internal_reconciliation_reads_exist_in_actual_mcp_and_stay_out_of_child_catalogs():
    from pathlib import Path
    import pytest
    from modeling_team.acceptance_runtime import (
        ChildRuntimeError, DIRECT_EXECUTION_READ_SCHEMAS, McpReadForwarder,
        PLATFORM_PROXY_READ_TOOLS, examiner_proxy_schemas, validate_examiner_proxy_arguments,
    )
    from modeling_team.modeling_readonly import MODELING_READ_TOOLS

    root = Path(__file__).resolve().parents[2]
    tools = ["get_modeling_context", "get_modeling_batch", "list_session_modeling_batches",
             "semantic_sparql_query", "query_semantic_context", "get_entity_statement_context"]
    internal = set(DIRECT_EXECUTION_READ_SCHEMAS)
    assert internal.isdisjoint(PLATFORM_PROXY_READ_TOOLS)
    assert internal.isdisjoint(MODELING_READ_TOOLS)
    for tool in internal:
        with pytest.raises(ChildRuntimeError):
            examiner_proxy_schemas([tool])
    schema = DIRECT_EXECUTION_READ_SCHEMAS["list_session_modeling_batches"]
    assert validate_examiner_proxy_arguments("list_session_modeling_batches", {"session_id": "owned"}, schema, scope={}) == {"session_id": "owned"}
    with pytest.raises(ChildRuntimeError):
        validate_examiner_proxy_arguments("list_session_modeling_batches", {"session_id": "owned", "project_id": "foreign"}, schema, scope={})
    forwarder = McpReadForwarder(
        repository_root=root, read_key="synthetic-catalog-only", expected_tools=tools,
        args=["-c", "from mcp.server.fastmcp import FastMCP; from app.mcp.tools import register_all; "
              "server = FastMCP('direct-registration'); register_all(server); server.run()"],
    )
    try:
        forwarder.start()
        assert forwarder.inventory_digest
        assert set(forwarder._tool_schemas) == set(tools)
        assert set(forwarder.exact_schemas) == internal
    finally:
        forwarder.stop()
    assert not forwarder.active


def test_unified_profile_prepares_without_protocol_but_legacy_keeps_its_dependency(tmp_path):
    import tempfile
    import yaml
    import pytest
    from pathlib import Path
    from modeling_team.contracts import TeamConfigurationError, load_multi_slice_team_configuration
    from modeling_team.tests.test_r30009_runner_wiring import PROFILE, UNIFIED_TASK

    staged = _UnifiedRunner(tmp_path)
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="direct-two-role-", dir=root / "workspaces") as directory:
        directory = Path(directory)
        profile = yaml.safe_load(PROFILE.read_text())
        profile["profile_id"] = "direct-two-role"
        profile["agents"] = [agent for agent in profile["agents"] if agent["agent_id"] != "protocol"]
        profile["communication"] = [{"from": "coordinator", "to": ["modeling"]},
                                    {"from": "modeling", "to": ["coordinator"]}]
        task = yaml.safe_load(UNIFIED_TASK.read_text())
        profile_path, task_path = directory / "profile.yaml", directory / "task.yaml"
        profile_path.write_text(yaml.safe_dump(profile))
        task_path.write_text(yaml.safe_dump(task))
        try:
            run = staged.runner.prepare(run_id=staged.run_id, profile_path=profile_path,
                                        task_path=task_path, scope={"mode": "create"})
            assert {agent.package.role for agent in run.configuration.profile.agents} == {"coordinator", "modeling"}
            assert staged.runner._multi_slice_role_ids() == {"coordinator": "coordinator", "modeling": "modeling"}
            assert staged.runner.acceptance.capability_endpoint("modeling")
            assert not (run.root / "sources" / "protocol").exists()
            staged.runner._probe_role_visibility()
        finally:
            staged.cleanup()
        task["parameters"]["unified_semantic_graph"] = False
        task_path.write_text(yaml.safe_dump(task))
        with pytest.raises(TeamConfigurationError, match="Protocol"):
            load_multi_slice_team_configuration(profile_path, task_path, root=root)
