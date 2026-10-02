"""R4.0-009 functional contracts; these fixtures do not establish L0/L1 quality."""

import asyncio
from copy import deepcopy
import json

import pytest

from modeling_team.__main__ import (
    _cq_collect_platform_read_responses, _cq_consume_production_handoff, _cq_read_tools,
)
from modeling_team.acceptance_runtime import (
    CQ_HOST_STATE_READ_TOOLS,
    CQ_SEMANTIC_READ_TOOLS,
    ChildRuntimeError,
    McpReadForwarder,
    PLATFORM_PROXY_READ_TOOLS,
    ProxyCallReceipt,
    ScopedReadProxy,
    build_acceptance_judge_packet,
    canonical_read_digest,
    v3_examiner_proxy_schemas,
)
from modeling_team.competency_questions import (
    batch_report_is_full_pass,
    build_batch_report,
    validate_acceptance_verdict,
)
from modeling_team.contracts import (
    TeamConfigurationError, load_multi_slice_team_configuration, repository_root,
)
from modeling_team.tests.test_r3011_acceptance import _binding, _platform_packet, _question
from modeling_team.tests.test_r3011_acceptance_runtime import (
    _batch_contract,
    _batch_packet,
    _examiner_entry,
    _start_sink,
    _submit,
    _verdict_entry,
)


NON_SEMANTIC_TOOLS = tuple(sorted(set(PLATFORM_PROXY_READ_TOOLS) - {
    "query_semantic_context", "get_semantic_read_model", "get_entity_statement_context",
    "get_ontology_read_model", "semantic_sparql_query",
}))


def test_009_task_reuses_current_roles_sources_and_tracing_suspension():
    root = repository_root()
    profile = root / "modeling_team/profiles/r3-0-011-competency-question.yaml"
    current = load_multi_slice_team_configuration(
        profile, root / "modeling_team/tasks/r4-0-012-tracing-suspension.yaml",
    )
    prepared = load_multi_slice_team_configuration(
        profile, root / "modeling_team/tasks/r4-0-009-multiview-semantic-acceptance.yaml",
    )
    assert prepared.profile == current.profile
    assert prepared.task.parameters == current.task.parameters
    assert prepared.task.parameters["acceptance_target"] == "cq_semantic"
    assert prepared.task.role_sources == current.task.role_sources
    assert prepared.task.protocol_tools == current.task.protocol_tools
    assert prepared.task.task_id == "r4-0-009-multiview-semantic-acceptance"
    assert "business-owner confirmation" in prepared.task.objective
    assert "R4.0-010/011" in prepared.task.objective


def test_loaded_judge_contract_agrees_with_routing_verdict():
    root = repository_root()
    active = (root / "modeling_team/agent-packages/v3-acceptance-batch/acceptance-judge.md").read_text()
    assert "`platform-runtime-incomplete` with `failure_layer=collaboration/routing`" in active
    assert "`model-recall-insufficient` with `failure_layer=collaboration/routing`" not in active
    legacy_v3 = (root / "modeling_team/agent-packages/acceptance/instructions-v3.md").read_text()
    assert "`runtime/infrastructure`, `platform-contract` or `collaboration/routing`" in legacy_v3


@pytest.mark.parametrize("continuation", [False, True])
def test_normal_and_checkpoint_handoffs_bind_only_semantic_tools(tmp_path, continuation):
    from modeling_team.tests.test_r3012_partial_judging import (
        _production_handoff, _publish_handoff, _write_run_root,
    )

    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    handoff = _production_handoff(frozen)
    handoff_path = _publish_handoff(run_root, handoff)
    before = handoff_path.read_bytes()
    contract = json.loads((run_root / "acceptance-v3/run-contract.json").read_text())
    output = tmp_path / "continuation"
    kwargs = ({"continuation_output": output, "continuation_attempt": "attempt-0002"}
              if continuation else {})
    directory, binding = _cq_consume_production_handoff(
        run_root, handoff, contract=contract,
        batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"], **kwargs,
    )
    tools = _cq_read_tools(binding)
    assert tools == list(CQ_SEMANTIC_READ_TOOLS)
    packet = _platform_packet(
        freeze=[_question("cq-1")], model_binding=binding, authorized_read_tools=tools,
    )
    assert set(v3_examiner_proxy_schemas(packet.payload["authorized_read_tools"])) == set(tools)
    assert "get_ontology_workspace_context" not in json.dumps(packet.to_dict())
    assert handoff_path.read_bytes() == before
    assert directory.is_relative_to(output if continuation else run_root)


def test_routing_verdict_is_recoverable_and_does_not_count_as_model_failure(tmp_path):
    packet = _batch_packet(role="acceptance")
    contract = _batch_contract("acceptance", packet)
    server, submit = _start_sink(tmp_path, contract=contract, kind="acceptance")
    try:
        incorrect = _verdict_entry(packet.batch_id, "cq-1")
        incorrect.update(verdict="model-recall-insufficient", failure_layer="collaboration/routing")
        refused = _submit(tmp_path / "report.sock", incorrect)
        assert refused["ok"] is False
        assert "failure_layer" in refused["detail"]
        assert submit.calls == []
        corrected = {**incorrect, "verdict": "platform-runtime-incomplete"}
        assert _submit(tmp_path / "report.sock", corrected)["ok"] is True
        last = _submit(tmp_path / "report.sock", _verdict_entry(packet.batch_id, "cq-2"))
        assert last["ok"] is True and last["batch_complete"] is True
        report = build_batch_report(
            run_id="run", batch_id=packet.batch_id, freeze_digest=packet.freeze_digest,
            model_binding_digest="b" * 64,
            hidden_questions=[_question("cq-1"), _question("cq-2")],
            examiner_reports=[_examiner_entry(packet.batch_id, q) for q in ("cq-1", "cq-2")],
            verdicts=submit.calls, executed_question_ids=["cq-1", "cq-2"],
            unexecuted_question_ids=[],
        )
        counts = report["summary_by_scope"]["panorama"]
        assert counts["platform-runtime-incomplete"] == 1
        assert counts["model-recall-insufficient"] == 0
        assert counts["pass"] == 1
        assert batch_report_is_full_pass(report) is False
    finally:
        server.stop()


@pytest.mark.parametrize("verdict,layer", [
    ("model-recall-insufficient", "collaboration/routing"),
    ("platform-runtime-incomplete", "modeling-quality"),
    ("pass", "collaboration/routing"),
])
def test_invalid_failure_combinations_still_refused(verdict, layer):
    entry = _verdict_entry("batch-r3011", "cq-1")
    entry.update(verdict=verdict, failure_layer=layer)
    with pytest.raises(ValueError, match="failure_layer"):
        validate_acceptance_verdict(entry, question_ids=["cq-1"])


@pytest.mark.parametrize("tool", NON_SEMANTIC_TOOLS)
def test_platform_packet_and_cli_refuse_production_or_host_tools(tool):
    binding = _binding()
    binding["ontologies"][0]["authorized_read_tools"] = [tool]
    with pytest.raises(ChildRuntimeError, match="read tools"):
        _platform_packet(authorized_read_tools=[tool])
    with pytest.raises(TeamConfigurationError, match="cq_read_tools_unsupported"):
        _cq_read_tools(binding)


def test_packet_and_cli_require_same_tools_for_all_bound_ontologies():
    binding = _platform_packet().to_dict()["payload"]["model_binding"]
    second = deepcopy(binding["ontologies"][0])
    second["ontology_id"] = "ontology-2"
    second["authorized_read_tools"] = ["get_ontology_read_model"]
    binding["ontologies"].append(second)
    with pytest.raises(ChildRuntimeError, match="read tools"):
        _platform_packet(model_binding=binding, authorized_scope=["ontology-1", "ontology-2"])
    with pytest.raises(TeamConfigurationError, match="cq_read_tools_unsupported"):
        _cq_read_tools(binding)


@pytest.mark.parametrize("tool", NON_SEMANTIC_TOOLS)
def test_child_refuses_non_semantic_calls_before_forwarding(tmp_path, tool):
    forwarded = []
    proxy = ScopedReadProxy(
        socket_path=tmp_path / "proxy.sock", token="proxy-token", read_key="synthetic-key",
        authorized_ontologies=[{
            "project_id": "project-1", "ontology_id": "ontology-1", "graph_set_id": "gs-1",
            "model_state_digest": "b" * 64, "graph_state_digest": "c" * 64,
        }], ticket_digest="a" * 64, model_state_digest="b" * 64,
        allowed_tools=list(CQ_SEMANTIC_READ_TOOLS),
        exact_schemas=v3_examiner_proxy_schemas(CQ_SEMANTIC_READ_TOOLS),
        forward=lambda *args: forwarded.append(args),
    )
    response = proxy.handle({
        "token": "proxy-token", "operation": "tools/call", "tool": tool,
        "arguments": {"project_id": "project-1", "ontology_id": "ontology-1"},
    })
    assert response["ok"] is False
    assert response["code"] == "read-tool-denied"
    assert forwarded == [] and proxy.receipt_snapshot == ()


def test_real_registration_and_forwarder_need_no_retired_tools():
    from app.mcp.tools import register_all
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("current-registration")
    register_all(server)
    registered = {tool.name for tool in asyncio.run(server.list_tools())}
    needed = CQ_SEMANTIC_READ_TOOLS + CQ_HOST_STATE_READ_TOOLS
    assert set(needed) <= registered
    assert {"list_evidence_references", "get_evidence_reference", "get_ontology_lineage",
            "inspect_semantic_statement_provenance"}.isdisjoint(registered)
    forwarder = McpReadForwarder(
        repository_root=repository_root(), read_key="synthetic-list-only-key",
        expected_tools=needed,
        # Start the actual current registry over stdio without database-backed
        # authentication. No tools/call, backend state, or real key is used.
        args=["-c", "from mcp.server.fastmcp import FastMCP; "
              "from app.mcp.tools import register_all; "
              "server = FastMCP('current-registration'); register_all(server); server.run()"],
    )
    try:
        forwarder.start()
        assert forwarder.inventory_digest
    finally:
        forwarder.stop()
    assert forwarder.active is False


@pytest.mark.parametrize("missing", ["query_semantic_context", "get_ontology_workspace_context"])
def test_missing_needed_tool_remains_a_startup_error(missing):
    # Use the real current registration, removing just one required tool.
    script = (
        "from mcp.server.fastmcp import FastMCP; "
        "from app.mcp.tools import register_all; "
        "server = FastMCP('missing-tool'); register_all(server); "
        f"server.remove_tool({missing!r}); server.run()"
    )
    root = repository_root()
    forwarder = McpReadForwarder(
        repository_root=root, read_key="synthetic-list-only-key",
        expected_tools=CQ_SEMANTIC_READ_TOOLS + CQ_HOST_STATE_READ_TOOLS,
        command=str(root / "backend/.venv/bin/python"), args=["-c", script],
    )
    try:
        with pytest.raises(ChildRuntimeError) as failed:
            forwarder.start()
        assert missing in repr(failed.value.__cause__)
    finally:
        forwarder.stop()
    assert forwarder.active is False


def test_brief_only_answer_cannot_be_used_as_semantic_evidence(tmp_path):
    tool = "get_project_build_context"
    request = {"project_id": "project-1"}
    result = {"ok": True, "data": {"brief": "answer exists only in the production brief"}}
    path = "platform-reads/brief.json"
    target = tmp_path / path
    target.parent.mkdir()
    target.write_text(json.dumps({
        "schema_version": "r3-0-012-platform-read-artifact/v1",
        "tool": tool, "request": request, "result": result,
    }))
    receipt = ProxyCallReceipt(
        ordinal=0, project_id="project-1", ontology_id="ontology-1", graph_set_id="gs-1",
        ticket_digest="a" * 64, model_state_digest="b" * 64,
        tool=tool, artifact_path=path,
        request_digest=canonical_read_digest({"tool": tool, "arguments": request}),
        response_digest=canonical_read_digest(result), page={},
    )
    responses, rejected = _cq_collect_platform_read_responses(
        [{"question_id": "cq-1", "evidence_refs": ["p0"]}],
        [receipt], tmp_path, list(PLATFORM_PROXY_READ_TOOLS),
    )
    assert responses == {} and rejected[0]["reason"] == "tool-unauthorized"
    batch = build_batch_report(
        run_id="run", batch_id="batch-r3011", freeze_digest="a" * 64,
        model_binding_digest="b" * 64, hidden_questions=[_question("cq-1")],
        examiner_reports=[_examiner_entry("batch-r3011", "cq-1")],
        verdicts=[_verdict_entry("batch-r3011", "cq-1")],
        executed_question_ids=["cq-1"], unexecuted_question_ids=[],
        platform_read_responses=responses,
    )
    assert batch_report_is_full_pass(batch) is False
    judge = _batch_packet(role="acceptance").to_dict()["payload"]
    judge["evidence_bundle"].pop("bundle_digest", None)
    judge["platform_read_responses"] = {"cq-1": [{
        "tool": tool, "request_digest": receipt.request_digest,
        "response_digest": receipt.response_digest, "artifact_path": path,
        "page": {}, "result": result,
    }]}
    with pytest.raises(ChildRuntimeError, match="response tool"):
        build_acceptance_judge_packet(**judge)
