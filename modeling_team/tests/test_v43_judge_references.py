"""Frozen Judge references and lossless input transport; no semantic start."""
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from threading import Event
from types import SimpleNamespace

import pytest

from modeling_team.acceptance_runtime import (
    ChildRuntimeError, V3BatchReportContract, build_acceptance_judge_packet, _unfreeze_packet,
)
from modeling_team.competency_questions import CQ_REFERENCE_PACKET_SCHEMA, content_digest
from modeling_team.tests.test_r3011_acceptance_runtime import (
    _batch_packet, _start_sink, _submit, _verdict_entry, _questions,
)
from modeling_team.__main__ import _cq_judge_input_packets, _cq_judge_transport_statistics
from modeling_team.runtimes.codex import _v3_acceptance_first_turn_text, _v3_judge_lossless_transport


def reference_packet(count=2, *, platform_body=None):
    payload = _unfreeze_packet(_batch_packet(role="acceptance", questions=_questions(count)).payload)
    bundle = payload.pop("evidence_bundle")
    bundle.pop("bundle_digest", None)
    if platform_body is not None:
        payload["platform_read_responses"] = {
            q["question_id"]: [{"tool": "query_semantic_context", "request_digest": "a" * 64,
                                "response_digest": "b" * 64, "artifact_path": f"reads/{q['question_id']}.json",
                                "page": {"has_more": False, "sequence_complete": True},
                                "result": platform_body}] for q in payload["questions"]}
    return build_acceptance_judge_packet(**payload, frozen_evidence_bundle=bundle)


def arguments(packet, reference_id=None):
    return {"run_id": packet.payload["run_id"], "batch_id": packet.batch_id,
            "freeze_digest": packet.freeze_digest,
            "reference_id": reference_id or packet.payload["evidence_bundle"]["entries"][0]["reference_id"]}


def verdict(packet, qid, ref=None):
    result = _verdict_entry(packet.batch_id, qid)
    result["note"] += " " + (ref or packet.payload["evidence_bundle"]["entries"][0]["reference_id"])
    return result


def test_manifest_read_reuse_reread_and_no_read_pass_denial():
    packet = reference_packet()
    assert packet.schema_version == CQ_REFERENCE_PACKET_SCHEMA
    assert all("content" not in e for e in packet.payload["evidence_bundle"]["entries"])
    assert "approved material" not in _v3_acceptance_first_turn_text(packet, "judge")
    contract = V3BatchReportContract(role="acceptance", packet=packet)
    with pytest.raises(ChildRuntimeError, match="actually read"):
        contract.validate(verdict(packet, "cq-1"))
    assert contract.read_frozen_evidence(arguments(packet))["content"] == "approved material"
    contract.record(contract.validate(verdict(packet, "cq-1")))
    contract.validate(verdict(packet, "cq-2"))  # Same frozen original can support another question.
    contract.read_frozen_evidence(arguments(packet))
    assert len(contract.source_read_receipts) == 2


@pytest.mark.parametrize("change", [
    {"run_id": "another-run"}, {"freeze_digest": "sha256:" + "c" * 64},
    {"batch_id": "another-batch"}, {"reference_id": "/etc/passwd"},
    {"path": "sources/current.md"}, {"reference_id": "unknown"},
])
def test_source_tool_refuses_foreign_paths_or_identity(change):
    packet = reference_packet()
    contract = V3BatchReportContract(role="acceptance", packet=packet)
    with pytest.raises(ChildRuntimeError):
        contract.read_frozen_evidence({**arguments(packet), **change})
    assert contract.source_read_receipts == []


def test_tampered_registry_and_manifest_missing_content_rejected():
    packet = reference_packet()
    payload = _unfreeze_packet(packet.payload)
    payload["evidence_bundle"].pop("bundle_digest")
    with pytest.raises(ChildRuntimeError, match="unavailable"):
        build_acceptance_judge_packet(**payload)
    with pytest.raises(ChildRuntimeError, match="missing or changed"):
        build_acceptance_judge_packet(**payload, source_registry={arguments(packet)["reference_id"]: "tampered"})
    payload["evidence_bundle"]["entries"][0]["content_digest"] = "sha256:" + "c" * 64
    with pytest.raises(ChildRuntimeError, match="identity changed"):
        build_acceptance_judge_packet(**payload, source_registry=packet.source_registry)


def test_different_chapters_and_versions_remain_distinct():
    payload = _unfreeze_packet(_batch_packet(role="acceptance").payload)
    bundle = payload.pop("evidence_bundle")
    bundle.pop("bundle_digest")
    second = bundle["entries"][1]
    second.update(locator="section 2", content="different version", review_content_version=2,
                  content_digest=content_digest("different version"))
    payload["questions"][1]["evidence_refs"][0]["locator"] = "section 2"
    packet = build_acceptance_judge_packet(**payload, frozen_evidence_bundle=bundle)
    refs = [e["reference_id"] for e in packet.payload["evidence_bundle"]["entries"]]
    assert refs[0] != refs[1]
    contract = V3BatchReportContract(role="acceptance", packet=packet)
    contract.read_frozen_evidence(arguments(packet, refs[0]))
    contract.record(contract.validate(verdict(packet, "cq-1", refs[0])))
    with pytest.raises(ChildRuntimeError, match="actually read"):
        contract.validate(verdict(packet, "cq-2", refs[1]))
    assert contract.read_frozen_evidence(arguments(packet, refs[1]))["content"] == "different version"
    contract.validate(verdict(packet, "cq-2", refs[1]))


@pytest.mark.parametrize("count", [5, 27])
def test_active_lossless_transport_and_volume_groups(monkeypatch, count):
    packet = reference_packet(count, platform_body={"body": "中文" * 1000, "complete": False})
    text = _v3_acceptance_first_turn_text(packet, "judge")
    assert "TRANSPORT_JSON=" in text and " PACKET_JSON=" not in text
    transport = _v3_judge_lossless_transport(packet.payload)
    expanded = transport["packet"]
    assert len(transport["result_body_registry"]) == 1
    for entries in expanded["platform_read_responses"].values():
        for entry in entries:
            entry["result"] = transport["result_body_registry"][entry.pop("result_ref")]
    assert expanded == _unfreeze_packet(packet.payload)
    # Includes metadata for all actual responses, not just the unique body size.
    one = _cq_judge_input_packets(packet, soft_target_bytes=1)
    target = len(_v3_acceptance_first_turn_text(one[0], __import__("modeling_team.__main__", fromlist=["_CQ_JUDGE_ROLE_INSTRUCTIONS"])._CQ_JUDGE_ROLE_INSTRUCTIONS).encode()) + 1
    groups = _cq_judge_input_packets(packet, soft_target_bytes=target)
    assert len(groups) > 1
    assert [q["question_id"] for p in groups for q in p.payload["questions"]] == [f"cq-{i}" for i in range(1, count + 1)]
    assert all(p.source_registry is not None for p in groups)
    metrics = _cq_judge_transport_statistics(packet, groups)
    assert metrics["source_prompt_body_bytes"] == 0
    assert metrics["source_original_body_bytes"] > 0
    assert metrics["platform_original_body_bytes"] == metrics["platform_registry_body_bytes"] * count
    assert metrics["group_count"] == len(groups)
    import modeling_team.__main__ as cli
    monkeypatch.setattr(cli, "_CODEX_MAX_INPUT_TEXT_CHARS", 100)
    failures = {}
    assert _cq_judge_input_packets(packet, input_failures=failures) == []
    assert list(failures) == [f"cq-{i}" for i in range(1, count + 1)]
    assert all(f["reason_code"] == "judge-input-too-large" for f in failures.values())


def test_real_stdio_facade_constrained_read_then_report_and_closed_lifecycle(tmp_path):
    packet = reference_packet()
    contract = V3BatchReportContract(role="acceptance", packet=packet)
    sink, submitted = _start_sink(tmp_path, contract=contract, kind="acceptance")
    token_file = tmp_path / "token"
    token_file.write_text(sink.token)
    script = Path(__file__).parents[1] / "report_sink_mcp.py"
    process = subprocess.Popen([sys.executable, str(script), "--stdio", "--kind", "acceptance",
        "--socket", str(sink.socket_path), "--token-file", str(token_file),
        "--schema", contract.schema_version, "--batch-id", packet.batch_id,
        "--role", "acceptance", "--question-ids", "cq-1,cq-2", "--frozen-evidence-reads"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    def call(method, params=None):
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}) + "\n")
        process.stdin.flush()
        return json.loads(process.stdout.readline())["result"]
    try:
        assert {t["name"] for t in call("tools/list")["tools"]} == {"submit_examiner_report", "read_frozen_evidence"}
        assert call("tools/call", {"name": "submit_examiner_report", "arguments": verdict(packet, "cq-1")})["isError"]
        denied = call("tools/call", {"name": "read_frozen_evidence", "arguments": arguments(packet, "/etc/passwd")})
        assert denied["isError"] and "unauthorized" in denied["content"][0]["text"]
        read = call("tools/call", {"name": "read_frozen_evidence", "arguments": arguments(packet)})
        assert json.loads(read["content"][0]["text"])["content"] == "approved material"
        for qid in ("cq-1", "cq-2"):
            assert not call("tools/call", {"name": "submit_examiner_report", "arguments": verdict(packet, qid)})["isError"]
        assert call("tools/call", {"name": "read_frozen_evidence", "arguments": arguments(packet)})["isError"]
        assert len(submitted.calls) == 2
    finally:
        process.stdin.close()
        process.wait(timeout=10)
        sink.stop()
    assert len(contract.source_read_receipts) == 1


def test_verified_staged_original_survives_live_source_change(tmp_path):
    from modeling_team.__main__ import _cq_build_judge_evidence_bundle
    from modeling_team.tests.test_r3011_acceptance_cli import (
        _write_run_root, _question, _stage_sources, _judge_questions, _RUN_CONTRACT,
    )
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-src")])
    _stage_sources(run_root, ("scenario-brief",), "frozen approved original")
    live_source = tmp_path / "scenario-brief"
    live_source.write_text("changed current source")
    bundle, failures = _cq_build_judge_evidence_bundle(run_root, frozen, frozen["questions"])
    assert failures == {}
    packet = build_acceptance_judge_packet(run_id=_RUN_CONTRACT["run_id"],
        batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"],
        questions=_judge_questions(frozen), model_binding_digest="sha256:" + "b" * 64,
        frozen_evidence_bundle=bundle, examiner_reports=[],
        verdict_schema={"schema_version": "r3-0-011-acceptance-batch-report/v1"})
    live_source.write_text("another current change")
    contract = V3BatchReportContract(role="acceptance", packet=packet)
    assert contract.read_frozen_evidence(arguments(packet))["content"] == "frozen approved original"


def test_native_judge_factory_mounts_only_frozen_read_tool_and_retains_receipts(tmp_path, monkeypatch):
    from modeling_team.acceptance_runtime import ReportSinkServer
    from modeling_team.contracts import repository_root
    from modeling_team.model_routing import load_team_model_profile
    from modeling_team.runtimes.codex import CodexRuntimeAdapter
    from modeling_team.report_sink_mcp import read_frozen_evidence
    packet = reference_packet()
    process = SimpleNamespace(stdin=StringIO(), stdout=StringIO(), stderr=StringIO(),
        poll=lambda: None, terminate=lambda: None, kill=lambda: None, wait=lambda **kwargs: 0)
    launches = []
    def process_factory(command, **kwargs):
        launches.append((command, kwargs))
        return process
    adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False,
                                  process_factory=process_factory)
    adapter._team_model_profile = load_team_model_profile(repository_root(), "openai-sol-medium")
    auth = tmp_path / "fixture-auth.json"
    auth.write_text("{}")
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: auth)
    monkeypatch.setattr(adapter, "_ensure_standalone_provider_sessions", lambda: None)
    monkeypatch.setattr(adapter, "_seed_models_cache", lambda *args: None)
    def output(agent, timeout):
        Event().wait(min(timeout, 0.01))
        return None
    monkeypatch.setattr(adapter, "_read_output_line", output)
    sinks = []
    start = ReportSinkServer.start
    def capture(sink):
        sinks.append(sink)
        start(sink)
    monkeypatch.setattr(ReportSinkServer, "start", capture)
    native_inputs = []
    def rpc(agent, method, params):
        if method == "initialize":
            return {}
        if method == "thread/start":
            assert "dynamicTools" not in params
            assert params["config"]["default_tools_enabled"] is False
            config = (agent.home / "config.toml").read_text()
            assert "--frozen-evidence-reads" in config
            assert "platform_read_proxy" not in config and "runner_capability" not in config
            assert (agent.home / "report_sink_mcp.py").is_file()
            assert "approved material" not in (agent.home / "input.json").read_text()
            return {"thread": {"id": "fixture-judge-thread"}}
        if method == "mcpServerStatus/list":
            return {"data": [{"name": "examiner_report", "tools": [
                {"name": "submit_examiner_report"}, {"name": "read_frozen_evidence"}]}]}
        if method == "turn/start":
            native_inputs.append(params["input"])
            sink = sinks[0]
            # This is the actual standalone facade/socket seam the mounted native tool uses.
            assert not read_frozen_evidence(str(sink.socket_path), sink.token, arguments(packet))["isError"]
            for qid in ("cq-1", "cq-2"):
                assert _submit(sink.socket_path, verdict(packet, qid), token=sink.token)["ok"]
            return {"turn": {"id": "fixture-judge-turn"}}
        raise AssertionError(method)
    monkeypatch.setattr(adapter, "_rpc", rpc)
    reports, teardown = [], {}
    adapter.run_v3_acceptance_child(packet, role_instructions="judge", reports=reports,
                                   timeout_seconds=5, teardown=teardown)
    assert len(reports) == 2 and len(launches) == 1 and len(native_inputs) == 1
    assert len(teardown["frozen_source_read_receipts"]) == 1
    assert teardown["report_sink_stopped"] and teardown["private_root_removed"]
    assert "approved material" not in json.dumps(native_inputs)


def test_judge_elicitation_keeps_only_mounted_server(monkeypatch):
    from modeling_team.runtimes.codex import CodexRuntimeAdapter
    from modeling_team.contracts import repository_root
    adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
    agent = SimpleNamespace(agent_id="judge-fixture", package=SimpleNamespace(
        package_id="acceptance", role="acceptance"), schema_version=2)
    responses = []
    monkeypatch.setattr(adapter, "_append_runtime_evidence", lambda *args: None)
    monkeypatch.setattr(adapter, "_respond_server_request", lambda *args: responses.append(args[-1]))
    for server in ("examiner_report", "ontology_platform", "runner_capability", "database"):
        adapter._dispatch_server_request(agent, {"id": 1, "method": "mcpServer/elicitation/request",
                                                "params": {"serverName": server}})
    assert [r["action"] for r in responses] == ["accept", "decline", "decline", "decline"]
