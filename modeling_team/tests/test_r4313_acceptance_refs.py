"""R4.3-013 acceptance report-reference seams.

These tests stay at the private report sink and child MCP boundary.  They do
not start a model or platform service; a fake material store represents the
Host-owned HandoffMaterials object.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from modeling_team.acceptance_runtime import ReportSinkServer, V3BatchReportContract
from modeling_team.report_sink_mcp import (
    _validate_batch_payload,
    _validate_payload,
    HANDOFF_MATERIAL_TOOL_NAMES,
    native_report_tool_specs,
    report_schema,
)
from modeling_team.tests.test_r3011_acceptance_runtime import (
    _batch_packet,
    _examiner_entry,
    _verdict_entry,
)


class _Materials:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[tuple[str, dict]] = []

    def resolve(self, actor_id: str, ref: dict) -> str:
        self.calls.append((actor_id, dict(ref)))
        if ref.get("material_id") != "material-report":
            from modeling_team.handoff_materials import MaterialError

            raise MaterialError("material_source_unavailable", "material package is unavailable")
        return self.content

    def call(self, actor_id: str, name: str, args: dict) -> dict:
        self.calls.append((actor_id, {"name": name, **dict(args)}))
        if name == "list_handoff_material":
            return {"material_id": args["material_id"], "entries": [], "list_complete": True}
        return {"material_id": args["material_id"], "content": "中文", "read_complete": True}


def _request(path: Path, token: str, payload: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(str(path))
        client.sendall(json.dumps({"token": token, **payload}, ensure_ascii=False).encode())
        return json.loads(client.recv(65536).decode())


def _legacy_source_report() -> dict:
    return {
        "answerability": "answerable",
        "conclusion": "complete",
        "evidence": [],
        "coverage": {"queries_or_sections": ["section 1"], "complete": True},
        "gaps": [],
        "evidence_refs": [{"location": "source.md#section-1"}],
    }


def test_legacy_report_reference_resolves_before_validation_and_keeps_receipt(tmp_path: Path):
    materials = _Materials(json.dumps(_legacy_source_report(), ensure_ascii=False))
    accepted: list[dict] = []
    sink = ReportSinkServer(
        tmp_path / "report.sock",
        "token",
        accepted.append,
        kind="source",
        handoff_materials=materials,
        material_actor_id="source-examiner",
    )
    sink.start()
    try:
        response = _request(
            sink.socket_path,
            sink.token,
            {"report": {"report_ref": {"material_id": "material-report", "path": "report.json"}}},
        )
        assert response["ok"] is True
        assert accepted == [_legacy_source_report()]
        assert response["report_ref"]["report_ref"]["material_id"] == "material-report"
        assert sink.report_ref_receipts[0]["bytes"] > 0
        assert materials.calls == [
            (
                "source-examiner",
                {"material_id": "material-report", "path": "report.json"},
            )
        ]
    finally:
        sink.stop()


def test_legacy_material_failures_do_not_consume_report_retry_budget(tmp_path: Path):
    materials = _Materials(json.dumps(_legacy_source_report()))
    accepted: list[dict] = []
    sink = ReportSinkServer(
        tmp_path / "report.sock",
        "token",
        accepted.append,
        kind="source",
        handoff_materials=materials,
        material_actor_id="source-examiner",
        max_attempts=3,
    )
    sink.start()
    try:
        for _ in range(4):
            response = _request(
                sink.socket_path,
                sink.token,
                {"report": {"report_ref": {"material_id": "material-missing"}}},
            )
            assert response["ok"] is False
            assert response["code"] == "material_source_unavailable"
            assert "attempts_remaining" not in response
        valid = _request(sink.socket_path, sink.token, {"report": _legacy_source_report()})
        assert valid["ok"] is True
        assert accepted == [_legacy_source_report()]
        assert sink._rejections == []
    finally:
        sink.stop()


def test_v3_report_reference_is_resolved_before_batch_contract(tmp_path: Path):
    packet = _batch_packet(role="platform-examiner")
    entry = _examiner_entry(packet.batch_id, "cq-1")
    materials = _Materials(json.dumps(entry))
    accepted: list[dict] = []
    contract = V3BatchReportContract(role="platform-examiner", packet=packet)
    sink = ReportSinkServer(
        tmp_path / "report.sock",
        "token",
        accepted.append,
        kind="platform",
        batch_contract=contract,
        handoff_materials=materials,
        material_actor_id="platform-examiner",
    )
    sink.start()
    try:
        for _ in range(4):
            response = _request(
                sink.socket_path,
                sink.token,
                {"report": {"report_ref": {"material_id": "material-missing"}}},
            )
            assert response["ok"] is False
            assert response["code"] == "material_source_unavailable"
        accepted_ref = _request(
            sink.socket_path,
            sink.token,
            {"report": {"report_ref": {"material_id": "material-report", "path": "report.json"}}},
        )
        assert accepted_ref["ok"] is True
        assert accepted == [entry]
        assert contract.pending_question_ids == ["cq-2"]
    finally:
        sink.stop()


def test_child_report_wire_advertises_and_accepts_reference_shape():
    ref = {"report_ref": {"material_id": "material-report", "path": "report.json"}}
    assert _validate_payload(ref, kind="source") == ref
    assert _validate_payload(ref, kind="acceptance") == ref
    assert _validate_batch_payload(
        ref,
        kind="platform",
        batch_id="batch",
        question_ids=["cq-1"],
        role="platform-examiner",
    ) == ref
    assert _validate_batch_payload(
        ref,
        kind="acceptance",
        batch_id="batch",
        question_ids=["cq-1"],
        role="acceptance",
    ) == ref
    assert "report_ref" in report_schema("source")["properties"]
    assert "report_ref" in report_schema("platform")["properties"]

    with pytest.raises(ValueError, match="cannot be mixed"):
        _validate_payload({**ref, "answerability": "answerable"}, kind="source")
    assert _validate_payload(
        {"report_ref": {"material_id": "material-report"}}, kind="source"
    ) == {"report_ref": {"material_id": "material-report"}}
    with pytest.raises(ValueError, match="path is invalid"):
        _validate_payload(
            {"report_ref": {"material_id": "material-report", "path": None}}, kind="source"
        )


def test_report_sink_exposes_only_explicit_handoff_read_tools(tmp_path: Path):
    materials = _Materials("{}")
    sink = ReportSinkServer(
        tmp_path / "report.sock",
        "token",
        lambda report: None,
        handoff_materials=materials,
        material_actor_id="judge",
        handoff_tool_names={"list_handoff_material", "read_handoff_material"},
    )
    sink.start()
    try:
        listed = _request(
            sink.socket_path,
            sink.token,
            {"operation": "handoff_material", "name": "list_handoff_material",
             "arguments": {"material_id": "material-report"}},
        )
        assert listed["ok"] is True
        assert sink.handoff_tools == ("list_handoff_material", "read_handoff_material")
        denied = _request(
            sink.socket_path,
            sink.token,
            {"operation": "handoff_material", "name": "write_handoff_output",
             "arguments": {"relative_path": "x", "content": "x"}},
        )
        assert denied["ok"] is False and denied["code"] == "material_forbidden"
    finally:
        sink.stop()


def test_standalone_sink_and_stdio_bridge_share_default_handoff_surface(tmp_path: Path):
    """Exercise the real attempt-private store through the child MCP process."""

    accepted: list[dict] = []
    sink = ReportSinkServer(
        tmp_path / "report.sock",
        "token",
        accepted.append,
        kind="source",
        material_actor_id="source-examiner",
    )
    sink.start()
    token_file = tmp_path / "report.token"
    token_file.write_text(sink.token, encoding="utf-8")
    script = Path(__file__).parents[1] / "report_sink_mcp.py"
    process = subprocess.Popen(
        [
            sys.executable,
            str(script),
            "--stdio",
            "--kind",
            "source",
            "--socket",
            str(sink.socket_path),
            "--token-file",
            str(token_file),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def call(name: str, arguments: dict | None = None, method: str = "tools/call") -> dict:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": name, "method": method, "params": arguments or {}},
                ensure_ascii=False,
            )
            + "\n"
        )
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        return response["result"]

    try:
        listed = call("list", method="tools/list")
        names = {item["name"] for item in listed["tools"]}
        assert names == {"submit_examiner_report", *HANDOFF_MATERIAL_TOOL_NAMES}
        # Material failures are resolved before the original report validator
        # and therefore do not consume the legacy rejection budget.
        for index in range(4):
            result = call(
                f"missing-{index}",
                {"name": "submit_examiner_report", "arguments": {
                    "report_ref": {"material_id": "material-missing"}
                }},
            )
            assert result["isError"] is True
            assert "material_source_unavailable" in result["content"][0]["text"]

        written = call(
            "write",
            {"name": "write_handoff_output", "arguments": {
                "relative_path": "report.json",
                "content": json.dumps(_legacy_source_report(), ensure_ascii=False),
            }},
        )
        output_ref = json.loads(written["content"][0]["text"])
        assert output_ref["source_path"] == "/agent/handoff-output/report.json"
        published = call(
            "publish",
            {"name": "publish_handoff_material", "arguments": {
                "recipient_id": "host",
                "source_path": output_ref["source_path"],
            }},
        )
        package = json.loads(published["content"][0]["text"])
        material_id = package["material_id"]
        listing = call(
            "list",
            {"name": "list_handoff_material", "arguments": {"material_id": material_id}},
        )
        listing_payload = json.loads(listing["content"][0]["text"])
        assert listing_payload["file_count"] == 1
        read = call(
            "read",
            {"name": "read_handoff_material", "arguments": {"material_id": material_id}},
        )
        read_payload = json.loads(read["content"][0]["text"])
        assert json.loads(read_payload["content"]) == _legacy_source_report()

        accepted_result = call(
            "submit",
            {"name": "submit_examiner_report", "arguments": {
                "report_ref": {"material_id": material_id},
            }},
        )
        assert accepted_result["isError"] is False
        assert accepted == [_legacy_source_report()]
        assert sink.report_ref_receipts[0]["report_ref"]["material_id"] == material_id
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=10)
        sink.stop()


def test_judge_frozen_directory_lists_stable_members_and_qualifies_only_full_reads(tmp_path: Path):
    """The frozen directory is a view over the original Judge reader contract."""

    from modeling_team.tests.test_v43_judge_references import arguments, reference_packet

    packet = reference_packet()
    contract = V3BatchReportContract(role="acceptance", packet=packet)
    expected_receipt = V3BatchReportContract(role="acceptance", packet=packet).read_frozen_evidence(
        arguments(packet)
    )["receipt"]
    accepted: list[dict] = []
    sink = ReportSinkServer(
        tmp_path / "report.sock",
        "token",
        accepted.append,
        kind="acceptance",
        batch_contract=contract,
    )
    sink.start()
    try:
        frozen_ref = sink.frozen_material_ref
        assert frozen_ref and set(frozen_ref) == {"material_id"}
        listed = _request(
            sink.socket_path,
            sink.token,
            {
                "operation": "handoff_material",
                "name": "list_handoff_material",
                "arguments": frozen_ref,
            },
        )
        assert listed["ok"] is True
        listing = listed["result"]
        assert listing["frozen"] is True
        assert listing["binding"]["packet"]["batch_id"] == packet.batch_id
        assert len(listing["entries"]) == 1
        entry = listing["entries"][0]
        reference_id = packet.payload["evidence_bundle"]["entries"][0]["reference_id"]
        assert entry["path"] == reference_id + ".txt"
        assert entry["reference_id"] == reference_id

        read = _request(
            sink.socket_path,
            sink.token,
            {
                "operation": "handoff_material",
                "name": "read_handoff_material",
                "arguments": {
                    **frozen_ref,
                    "path": entry["path"],
                    "max_bytes": 3,
                },
            },
        )
        assert read["ok"] is True
        assert read["result"]["read_complete"] is False
        assert "receipt" not in read["result"]
        assert contract.source_read_receipts == []

        offset = read["result"]["next_offset"]
        while not read["result"]["read_complete"]:
            read = _request(
                sink.socket_path,
                sink.token,
                {
                    "operation": "handoff_material",
                    "name": "read_handoff_material",
                    "arguments": {
                        **frozen_ref,
                        "path": entry["path"],
                        "offset": offset,
                        "max_bytes": 3,
                    },
                },
            )
            assert read["ok"] is True
            offset = read["result"]["next_offset"]
        receipt = read["result"]["receipt"]
        assert len(contract.source_read_receipts) == 1
        assert receipt == contract.source_read_receipts[0]
        assert receipt == expected_receipt
        verdict = _verdict_entry(packet.batch_id, "cq-1")
        verdict["note"] += " " + reference_id
        submitted = _request(
            sink.socket_path,
            sink.token,
            {"report": verdict},
        )
        assert submitted["ok"] is True
        assert accepted == [verdict]
    finally:
        sink.stop()


def test_stdio_judge_reads_frozen_directory_then_passes_original_receipt(tmp_path: Path):
    """Exercise the actual child MCP process, socket and v3 PASS route together."""

    from modeling_team.tests.test_v43_judge_references import reference_packet

    packet = reference_packet()
    contract = V3BatchReportContract(role="acceptance", packet=packet)
    accepted: list[dict] = []
    sink = ReportSinkServer(
        tmp_path / "report.sock",
        "token",
        accepted.append,
        kind="acceptance",
        batch_contract=contract,
    )
    sink.start()
    token_file = tmp_path / "report.token"
    token_file.write_text(sink.token, encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "report_sink_mcp.py"),
            "--stdio",
            "--kind",
            "acceptance",
            "--socket",
            str(sink.socket_path),
            "--token-file",
            str(token_file),
            "--schema",
            contract.schema_version,
            "--batch-id",
            packet.batch_id,
            "--role",
            "acceptance",
            "--question-ids",
            "cq-1,cq-2",
            "--frozen-evidence-reads",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def call(name: str, arguments: dict | None = None, method: str = "tools/call") -> dict:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": name, "method": method, "params": arguments or {}},
                ensure_ascii=False,
            )
            + "\n"
        )
        process.stdin.flush()
        return json.loads(process.stdout.readline())["result"]

    try:
        names = {tool["name"] for tool in call("tools", method="tools/list")["tools"]}
        assert names == {"submit_examiner_report", "read_frozen_evidence", *HANDOFF_MATERIAL_TOOL_NAMES}
        frozen_ref = sink.frozen_material_ref
        assert frozen_ref is not None
        listing = call(
            "list-frozen",
            {"name": "list_handoff_material", "arguments": frozen_ref},
        )
        listing_payload = json.loads(listing["content"][0]["text"])
        entry = listing_payload["entries"][0]
        read = call(
            "read-frozen",
            {
                "name": "read_handoff_material",
                "arguments": {**frozen_ref, "path": entry["path"], "max_bytes": 4},
            },
        )
        read_payload = json.loads(read["content"][0]["text"])
        while not read_payload["read_complete"]:
            read = call(
                "read-frozen-next",
                {
                    "name": "read_handoff_material",
                    "arguments": {
                        **frozen_ref,
                        "path": entry["path"],
                        "offset": read_payload["next_offset"],
                        "max_bytes": 4,
                    },
                },
            )
            read_payload = json.loads(read["content"][0]["text"])
        assert len(contract.source_read_receipts) == 1
        assert read_payload["receipt"] == contract.source_read_receipts[0]
        reference_id = entry["reference_id"]
        for question_id in ("cq-1", "cq-2"):
            verdict = _verdict_entry(packet.batch_id, question_id)
            verdict["note"] += " " + reference_id
            submitted = call(
                question_id,
                {"name": "submit_examiner_report", "arguments": verdict},
            )
            assert submitted["isError"] is False
        assert accepted == [
            {**_verdict_entry(packet.batch_id, "cq-1"), "note": "answer matches for cq-1 " + reference_id},
            {**_verdict_entry(packet.batch_id, "cq-2"), "note": "answer matches for cq-2 " + reference_id},
        ]
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=10)
        sink.stop()


def test_native_report_manifest_makes_reference_and_handoff_reachable():
    tools = native_report_tool_specs("source")
    by_name = {tool["name"]: tool for tool in tools}
    assert set(by_name) == {"submit_examiner_report", *HANDOFF_MATERIAL_TOOL_NAMES}
    schema = by_name["submit_examiner_report"]["inputSchema"]
    assert {"report_ref"} <= set(schema["properties"])
    assert any(
        branch.get("required") == ["report_ref"]
        for branch in schema["oneOf"]
    )
