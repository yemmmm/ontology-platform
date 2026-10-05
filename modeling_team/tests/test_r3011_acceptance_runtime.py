"""R3.0-011 G4 acceptance runtime fixtures: sink contracts and read proxies.

Real AF_UNIX ``ReportSinkServer``/``ScopedReadProxy`` objects over real sockets.
No child process, no LLM, and no platform/backend call: the forward is a local
callable, which is exactly the seam the real ``McpReadForwarder`` occupies.
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.acceptance_runtime import (
    PLATFORM_PROXY_READ_TOOLS,
    ChildRuntimeError,
    ReportSinkServer,
    ScopedReadProxy,
    V3BatchReportContract,
    examiner_proxy_schemas,
    v3_examiner_proxy_schemas,
    v3_proxy_scope_entries,
    v3_ticket_digest,
)
from modeling_team.competency_questions import CQ_BATCH_REPORT_SCHEMA, content_digest
from modeling_team.tests.test_r3011_acceptance import _binding, _platform_packet

TOKEN = "sink-token"


# --- fixtures -----------------------------------------------------------------


def _questions(count: int = 2) -> list[dict]:
    items = []
    for index in range(1, count + 1):
        items.append(
            {
                "question_id": f"cq-{index}",
                "scope": {"kind": "panorama", "slice_ids": []},
                "question": f"placeholder {index}?",
                "answer_points": ["point"],
                "evidence_refs": [{"source": "scenario-brief", "locator": "section 1"}],
                "unknown": [],
                "proposed_visibility": "hidden",
                "content_version": 1,
            }
        )
    return items


def _batch_packet(*, role: str = "platform-examiner", questions: list[dict] | None = None):
    """Build one v3 batch packet for either role (judge packet derives answers)."""

    items = questions or _questions()
    if role == "platform-examiner":
        return _platform_packet(freeze=items)
    payload = json.loads(
        json.dumps(_platform_packet(freeze=items).to_dict()["payload"])
    )
    from modeling_team.acceptance_runtime import build_acceptance_judge_packet

    return build_acceptance_judge_packet(
        run_id=payload["run_id"],
        batch_id=payload["batch_id"],
        freeze_digest=payload["freeze_digest"],
        questions=[
            {
                "question_id": item["question_id"],
                "content_version": item["content_version"],
                "question": item["question"],
                "answer_points": ["point"],
                "evidence_refs": [{"source": "scenario-brief", "locator": "section 1"}],
                "unknown": [],
                "scope": dict(item["scope"]),
            }
            for item in payload["questions"]
        ],
        model_binding_digest="sha256:" + "b" * 64,
        evidence_bundle={
            "schema_version": "r3-0-011-acceptance-evidence/v1",
            "batch_id": payload["batch_id"],
            "freeze_digest": payload["freeze_digest"],
            "entries": [
                {
                    "question_id": item["question_id"],
                    "source": "scenario-brief",
                    "locator": "section 1",
                    "content": "approved material",
                    "content_digest": content_digest("approved material"),
                    "review_content_version": 1,
                }
                for item in payload["questions"]
            ],
        },
        examiner_reports=[],
        verdict_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
    )


def _examiner_entry(batch_id: str, question_id: str, *, version: int = 1) -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": batch_id,
        "question_id": question_id,
        "question_content_version": version,
        "answer": f"answer for {question_id}",
        "evidence_refs": ["resource-1"],
        "explicit_unknown": [],
        "status": "completed",
        "failure_layer": None,
        "reason": None,
    }


def _verdict_entry(batch_id: str, question_id: str) -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": batch_id,
        "question_id": question_id,
        "verdict": "pass",
        "failure_layer": None,
        "conflicting_evidence": [],
        "note": f"answer matches for {question_id}",
    }


def _start_sink(tmp_path: Path, *, contract: V3BatchReportContract | None, kind: str):
    """Start one real AF_UNIX sink and return (server, submit_call)."""

    def submit(report: dict) -> None:
        submit.calls.append(dict(report))

    submit.calls = []
    server = ReportSinkServer(
        tmp_path / "report.sock",
        TOKEN,
        submit,
        kind=kind,
        validator=lambda report: None,
        max_attempts=3,
        batch_contract=contract,
    )
    server.start()
    return server, submit


def _submit(socket_path: Path, report: object, *, token: str = TOKEN) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(str(socket_path))
        client.sendall(
            json.dumps({"token": token, "report": report}, ensure_ascii=False).encode("utf-8")
        )
        return json.loads(client.recv(65536).decode("utf-8"))


def _batch_contract(role: str, packet) -> V3BatchReportContract:
    return V3BatchReportContract(role=role, packet=packet)


# --- v3 sink: recoverable correction, ordered batch latch ---------------------


def test_v3_sink_stays_recoverable_past_the_legacy_attempt_budget(tmp_path):
    """More invalid submissions than the legacy budget, then a valid batch.

    The legacy single-report latch would refuse the fourth attempt outright;
    the v3 batch branch keeps typed correction feedback so the session deadline
    is the only bound on attempts (AGENTS.md recoverability rule).
    """

    packet = _batch_packet(role="platform-examiner")
    batch_id = packet.batch_id
    contract = _batch_contract("platform-examiner", packet)
    server, submit = _start_sink(tmp_path, contract=contract, kind="platform")
    try:
        # Four rejections: out of order, foreign batch, duplicate content
        # version, and an unknown question.
        first = _submit(tmp_path / "report.sock", _examiner_entry(batch_id, "cq-2"))
        assert first["ok"] is False and first["code"] == "report-binding-rejected"
        assert "expects the report for cq-1 next" in first["detail"]
        foreign = _examiner_entry("another-batch", "cq-1")
        second = _submit(tmp_path / "report.sock", foreign)
        assert second["ok"] is False and "bound to another batch" in second["detail"]
        drifted = _examiner_entry(batch_id, "cq-1", version=7)
        third = _submit(tmp_path / "report.sock", drifted)
        assert third["ok"] is False and "cites another content version" in third["detail"]
        unknown = _examiner_entry(batch_id, "cq-9")
        fourth = _submit(tmp_path / "report.sock", unknown)
        assert fourth["ok"] is False and fourth["code"] == "report-binding-rejected"
        # The corrected, ordered batch is still accepted afterwards.
        first_ok = _submit(tmp_path / "report.sock", _examiner_entry(batch_id, "cq-1"))
        assert first_ok["ok"] is True
        assert first_ok["reports_remaining"] == 1 and first_ok["batch_complete"] is False
        second_ok = _submit(tmp_path / "report.sock", _examiner_entry(batch_id, "cq-2"))
        assert second_ok["ok"] is True
        assert second_ok["batch_complete"] is True and second_ok["reports_remaining"] == 0
        assert [report["question_id"] for report in submit.calls] == ["cq-1", "cq-2"]
        assert contract.is_complete
        # The completed batch is latched: a later entry cannot reopen it.
        late = _submit(tmp_path / "report.sock", _examiner_entry(batch_id, "cq-1"))
        assert late["ok"] is False and late["code"] == "report-already-submitted"
    finally:
        server.stop()


def test_v3_judge_sink_latches_the_same_way_without_a_platform_read(tmp_path):
    packet = _batch_packet(role="acceptance")
    batch_id = packet.batch_id
    contract = _batch_contract("acceptance", packet)
    server, submit = _start_sink(tmp_path, contract=contract, kind="acceptance")
    try:
        for question_id in ("cq-1", "cq-2"):
            response = _submit(tmp_path / "report.sock", _verdict_entry(batch_id, question_id))
            assert response["ok"] is True
        assert response["batch_complete"] is True
        assert [report["question_id"] for report in submit.calls] == ["cq-1", "cq-2"]
    finally:
        server.stop()


def test_v3_verdict_rejection_detail_carries_the_retry_spelling():
    """2026-10-05 public judge failure: the typed ``retry`` guidance was dropped
    when the contract wrapped the validator error, so the judge only ever saw
    "pass must keep failure_layer empty" and no submission carried its named
    null spelling.  The wrap must surface the retry text."""
    packet = _batch_packet(role="acceptance")
    contract = _batch_contract("acceptance", packet)
    attributed = _verdict_entry(packet.batch_id, "cq-1")
    attributed["failure_layer"] = "modeling-quality"
    with pytest.raises(ChildRuntimeError, match="JSON null"):
        contract.validate(attributed)


def test_v3_rejections_do_not_carry_the_legacy_attempt_count(tmp_path):
    """2026-10-05 public judge failure: the v3 branch has no attempt budget
    (the session deadline is the only bound), yet its typed rejections echoed
    the legacy ``attempts_remaining`` countdown.  Once that countdown read 0
    the judge abandoned a session whose resubmission was still legal.  The
    v3 rejection feedback must keep the typed code and retry detail without
    the inapplicable legacy count."""

    packet = _batch_packet(role="acceptance")
    contract = _batch_contract("acceptance", packet)
    server, submit = _start_sink(tmp_path, contract=contract, kind="acceptance")
    try:
        # Four attributed rejections: one more than the legacy budget of 3.
        for _ in range(4):
            attributed = _verdict_entry(packet.batch_id, "cq-1")
            attributed["failure_layer"] = "modeling-quality"
            response = _submit(tmp_path / "report.sock", attributed)
            assert response["ok"] is False
            assert response["code"] == "report-binding-rejected"
            assert "attempts_remaining" not in response
            assert "JSON null" in response["detail"]
        accepted = _submit(tmp_path / "report.sock", _verdict_entry(packet.batch_id, "cq-1"))
        assert accepted["ok"] is True and accepted["batch_complete"] is False
        assert [report["question_id"] for report in submit.calls] == ["cq-1"]
    finally:
        server.stop()


def test_v3_submit_rejections_do_not_carry_the_legacy_attempt_count(tmp_path):
    """A failing Host submit callback is another recoverable v3 rejection;
    it must not present the legacy countdown either, and the same sink must
    accept the corrected resubmission."""

    packet = _batch_packet(role="acceptance")
    contract = _batch_contract("acceptance", packet)
    attempts = {"count": 0}

    def flaky_submit(report: dict) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("receipt binding unavailable")

    server = ReportSinkServer(
        tmp_path / "report.sock",
        TOKEN,
        flaky_submit,
        kind="acceptance",
        validator=lambda report: None,
        max_attempts=3,
        batch_contract=contract,
    )
    server.start()
    try:
        first = _submit(tmp_path / "report.sock", _verdict_entry(packet.batch_id, "cq-1"))
        assert first["ok"] is False and first["code"] == "report-submit-rejected"
        assert "attempts_remaining" not in first
        assert "receipt binding unavailable" in first["detail"]
        second = _submit(tmp_path / "report.sock", _verdict_entry(packet.batch_id, "cq-1"))
        assert second["ok"] is True
    finally:
        server.stop()


def test_legacy_sink_attempt_budget_is_retained(tmp_path):
    """The v3 recoverability change must not relax the legacy single report."""

    server, submit = _start_sink(tmp_path, contract=None, kind="acceptance")
    try:
        responses = [
            _submit(tmp_path / "report.sock", {"schema_version": "nope"}) for _ in range(3)
        ]
        assert all(response["ok"] is False for response in responses)
        assert responses[0]["code"] in {"report-rejected", "report-binding-rejected"}
        assert responses[-1]["attempts_remaining"] == 0
        fourth = _submit(tmp_path / "report.sock", {"schema_version": "nope"})
        assert fourth["ok"] is False and fourth["code"] == "report-attempts-exceeded"
        assert submit.calls == []
    finally:
        server.stop()


def test_sink_rejects_a_bad_token_without_touching_the_batch(tmp_path):
    packet = _batch_packet(role="platform-examiner")
    contract = _batch_contract("platform-examiner", packet)
    server, submit = _start_sink(tmp_path, contract=contract, kind="platform")
    try:
        response = _submit(
            tmp_path / "report.sock", _examiner_entry(packet.batch_id, "cq-1"), token="nope"
        )
        assert response["ok"] is False and response["code"] == "report-token-invalid"
        assert contract.pending_question_ids == ["cq-1", "cq-2"]
        assert submit.calls == []
    finally:
        server.stop()


# --- v3 read proxy: packet-scoped multi-Ontology reads ------------------------


def _proxy(tmp_path: Path, *, tools=( "get_ontology_read_model",), forward=None):
    from modeling_team.tests.test_r3011_acceptance import _freeze

    frozen = _freeze(_questions())
    packet = _platform_packet(
        freeze=_questions(),
        authorized_read_tools=list(tools),
        authorized_scope=["ontology-1", "ontology-2"],
        model_binding={
            "schema_version": "r3-0-011-model-binding/v1",
            "batch_id": frozen["batch_id"],
            "freeze_digest": frozen["snapshot_digest"],
            "bound_at": "2026-09-09T00:00:00+00:00",
            "ontologies": [
                {
                    "project_id": "project-1",
                    "ontology_id": "ontology-1",
                    "workspace_state": {"state_digest": "ws-1"},
                    "graph_state": {"state_digest": "graph-1"},
                    "authorized_read_tools": list(tools),
                },
                {
                    "project_id": "project-1",
                    "ontology_id": "ontology-2",
                    "workspace_state": {"state_digest": "ws-2"},
                    "graph_state": {"state_digest": "graph-2"},
                    "authorized_read_tools": list(tools),
                },
            ],
        },
    )
    entries = v3_proxy_scope_entries(
        packet, {"ontology-1": "graph-set-1", "ontology-2": "graph-set-2"}
    )
    proxy = ScopedReadProxy(
        socket_path=tmp_path / "platform-proxy.sock",
        token="proxy-token",
        read_key="read-key",
        authorized_ontologies=entries,
        ticket_digest=packet.freeze_digest,
        model_state_digest="ws-1",
        allowed_tools=list(tools),
        forward=forward,
        acceptance_round_id="r3011-batch",
        child_handle_digest="c" * 64,
        exact_schemas=v3_examiner_proxy_schemas(tools),
    )
    return proxy, packet


def test_v3_proxy_forwards_each_authorized_ontology(tmp_path):
    forwarded: list[tuple[str, dict, str]] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        forwarded.append((tool, dict(arguments), key))
        return {"ok": True, "data": {"ontology_id": arguments["ontology_id"]}}

    proxy, _packet_ = _proxy(tmp_path, forward=forward)
    proxy.start()
    try:
        first = proxy.handle(
            {
                "token": "proxy-token",
                "operation": "tools/call",
                "tool": "get_ontology_read_model",
                "arguments": {"model_name": "classes", "project_id": "project-1", "ontology_id": "ontology-1"},
            }
        )
        assert first["ok"] is True
        assert first["result"]["data"]["ontology_id"] == "ontology-1"
        second = proxy.handle(
            {
                "token": "proxy-token",
                "operation": "tools/call",
                "tool": "get_ontology_read_model",
                "arguments": {"model_name": "classes", "project_id": "project-1", "ontology_id": "ontology-2"},
            }
        )
        assert second["ok"] is True
        assert second["result"]["data"]["ontology_id"] == "ontology-2"
        # The proxy injected the frozen per-Ontology bindings for both calls.
        assert [call[1]["graph_set_id"] for call in forwarded] == [
            "graph-set-1",
            "graph-set-2",
        ]
        assert {call[1]["model_state_digest"] for call in forwarded} == {"ws-1", "ws-2"}
        assert {call[2] for call in forwarded} == {"read-key"}
        assert [receipt.ontologies for receipt in proxy._call_receipts] == [
            ({"project_id": "project-1", "ontology_id": "ontology-1",
              "graph_set_id": "graph-set-1", "model_state_digest": "ws-1",
              "graph_state_digest": "graph-1"},),
            ({"project_id": "project-1", "ontology_id": "ontology-2",
              "graph_set_id": "graph-set-2", "model_state_digest": "ws-2",
              "graph_state_digest": "graph-2"},),
        ]
    finally:
        proxy.stop()


def test_v3_proxy_refuses_unauthorized_and_cross_project_selections(tmp_path):
    forwarded: list[tuple[str, dict, str]] = []
    proxy, _packet_ = _proxy(
        tmp_path, forward=lambda tool, arguments, key: forwarded.append((tool, arguments, key)) or {}
    )
    try:
        unknown = proxy.handle(
            {
                "token": "proxy-token",
                "operation": "tools/call",
                "tool": "get_ontology_read_model",
                "arguments": {"model_name": "classes", "project_id": "project-1", "ontology_id": "ontology-9"},
            }
        )
        assert unknown["ok"] is False and unknown["code"] == "read-scope-denied"
        assert unknown["backend_calls"] == 0
        # A caller/bridge hint that contradicts the selected entry is replaced by
        # the Host-owned binding (the staged bridge projects the first authorized
        # Ontology's env scope); it can never widen the selection.
        hinted = proxy.handle(
            {
                "token": "proxy-token",
                "operation": "tools/call",
                "tool": "get_ontology_read_model",
                "arguments": {
                    "model_name": "classes",
                    "project_id": "project-1",
                    "ontology_id": "ontology-2",
                    "graph_set_id": "graph-set-1",
                    "model_state_digest": "ws-1",
                },
            }
        )
        assert hinted["ok"] is True
        assert forwarded[-1][1]["graph_set_id"] == "graph-set-2"
        assert forwarded[-1][1]["model_state_digest"] == "ws-2"
        # A wrong ticket is a batch-identity error, not a hint.
        wrong_ticket = proxy.handle(
            {
                "token": "proxy-token",
                "operation": "tools/call",
                "tool": "get_ontology_read_model",
                "arguments": {"model_name": "classes", "ticket_digest": "sha256:" + "9" * 64},
            }
        )
        assert wrong_ticket["ok"] is False and wrong_ticket["code"] == "read-scope-denied"
        assert len(forwarded) == 1
        assert proxy.backend_calls == 1
    finally:
        proxy.stop()


def test_v3_proxy_default_selection_is_the_first_authorized_ontology(tmp_path):
    forwarded: list[tuple[str, dict, str]] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        forwarded.append((tool, dict(arguments), key))
        return {"ok": True}

    proxy, _packet_ = _proxy(tmp_path, forward=forward)
    try:
        response = proxy.handle(
            {
                "token": "proxy-token",
                "operation": "tools/call",
                "tool": "get_ontology_read_model",
                "arguments": {"model_name": "classes", "project_id": "project-1"},
            }
        )
        assert response["ok"] is True
        assert forwarded[0][1]["ontology_id"] == "ontology-1"
        listed = proxy.handle({"token": "proxy-token", "operation": "tools/list"})
        assert listed["ok"] is True and listed["tools"] == ["get_ontology_read_model"]
        denied = proxy.handle(
            {
                "token": "proxy-token",
                "operation": "tools/call",
                "tool": "save_build_checkpoint",
                "arguments": {},
            }
        )
        assert denied["ok"] is False and denied["code"] == "read-tool-denied"
    finally:
        proxy.stop()


def test_v3_proxy_revocation_and_bad_token_stay_typed(tmp_path):
    proxy, _packet_ = _proxy(tmp_path, forward=lambda tool, arguments, key: {})
    try:
        bad = proxy.handle({"token": "wrong", "operation": "tools/list"})
        assert bad["ok"] is False and bad["code"] == "proxy-token-invalid"
        assert proxy.active is True
        revoked = proxy.revoke()
        assert revoked == {"status": "revoked", "post_revoke_denials": 0}
        assert proxy.active is False
        after = proxy.handle(
            {
                "token": "proxy-token",
                "operation": "tools/call",
                "tool": "get_ontology_read_model",
                "arguments": {"model_name": "classes", "project_id": "project-1"},
            }
        )
        assert after["ok"] is False and after["code"] == "read-key-revoked"
        assert proxy.post_revoke_denials == 1
    finally:
        proxy.stop()


def test_v3_proxy_serves_the_real_read_proxy_bridge(tmp_path):
    """The staged read_proxy_mcp.py bridge reaches this v3 proxy unchanged."""

    import shutil
    import subprocess
    import sys

    socket_path = tmp_path / "platform-proxy.sock"
    token_path = tmp_path / "platform-proxy.token"
    token_path.write_text("proxy-token\n", encoding="utf-8")
    forwarded: list[tuple[str, dict, str]] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        forwarded.append((tool, dict(arguments), key))
        return {"ok": True, "data": {"state": "ready"}}

    proxy, packet = _proxy(tmp_path, forward=forward)
    proxy.socket_path = socket_path
    proxy.start()
    bridge = tmp_path / "read_proxy_mcp.py"
    shutil.copyfile(
        Path(__file__).resolve().parents[1] / "read_proxy_mcp.py", bridge
    )
    primary = proxy.authorized_ontologies[0]
    bridge_env = {
        **os.environ,
        "PLATFORM_PROXY_PROJECT_ID": primary["project_id"],
        "PLATFORM_PROXY_ONTOLOGY_ID": primary["ontology_id"],
        "PLATFORM_PROXY_GRAPH_SET_ID": primary["graph_set_id"],
        "PLATFORM_PROXY_TICKET_DIGEST": v3_ticket_digest(packet.freeze_digest),
        "PLATFORM_PROXY_MODEL_STATE_DIGEST": primary["model_state_digest"],
    }
    process = subprocess.Popen(
        [
            sys.executable,
            str(bridge),
            "--stdio",
            "--socket",
            str(socket_path),
            "--token-file",
            str(token_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=bridge_env,
    )

    def request(request_id: int, method: str, params: dict | None = None) -> dict:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
                separators=(",", ":"),
            )
            + "\n"
        )
        process.stdin.flush()
        return json.loads(process.stdout.readline())

    try:
        listed = request(1, "tools/list")["result"]["tools"]
        assert [item["name"] for item in listed] == ["get_ontology_read_model"]
        called = request(
            2,
            "tools/call",
            {
                "name": "get_ontology_read_model",
                "arguments": {"model_name": "classes", "project_id": "project-1", "ontology_id": "ontology-2"},
            },
        )
        assert called["result"]["isError"] is False
        assert forwarded[0][1]["ontology_id"] == "ontology-2"
        assert forwarded[0][1]["graph_set_id"] == "graph-set-2"
        assert forwarded[0][2] == "read-key"
    finally:
        process.stdin.close() if process.stdin is not None else None
        process.wait(timeout=10)
        proxy.stop()


def test_v3_scope_entries_come_from_the_packet_binding(tmp_path):
    packet = _batch_packet(questions=_questions())
    with pytest.raises(Exception):
        v3_proxy_scope_entries(packet, {})
    entries = v3_proxy_scope_entries(packet, {"ontology-1": "graph-set-1"})
    assert entries == (
        {
            "project_id": "project-1",
            "ontology_id": "ontology-1",
            "graph_set_id": "graph-set-1",
            "model_state_digest": "ws-1",
            "graph_state_digest": "graph-1",
        },
    )
    # The legacy single-Ontology proxy is unchanged.
    legacy = ScopedReadProxy(
        socket_path=tmp_path / "legacy.sock",
        token="proxy-token",
        read_key="read-key",
        project_id="project-1",
        ontology_id="ontology-1",
        graph_set_id="graph-set-1",
        ticket_digest="d" * 64,
        model_state_digest="e" * 64,
        allowed_tools=["get_ontology_workspace_context"],
        forward=lambda tool, arguments, key: {"ok": True},
        exact_schemas=examiner_proxy_schemas(["get_ontology_workspace_context"]),
    )
    response = legacy.handle(
        {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "get_ontology_workspace_context",
            "arguments": {},
        }
    )
    assert response["ok"] is True
    assert list(PLATFORM_PROXY_READ_TOOLS)[:1] == ["check_platform_health"]
    assert _binding()["ontologies"][0]["authorized_read_tools"] == ["query_semantic_context"]


# --- v3 child boundary: partial retention and per-child teardown --------------


class _FakeSink:
    """Deterministic sink double that still carries the real batch contract."""

    def __init__(self, contract: V3BatchReportContract) -> None:
        self.batch_contract = contract
        self.active = False

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False


class _DeadProcess:
    """A child process that already exited (poll() is not None)."""

    @staticmethod
    def poll() -> int:
        return 1


class _IdleProcess:
    """A child process that stays alive until it is torn down."""

    @staticmethod
    def poll():
        return None


def _multi_proxy(
    tmp_path: Path,
    *,
    count: int = 3,
    tools: tuple[str, ...] = ("query_semantic_context",),
    forward=None,
):
    """Build one v3 proxy whose packet authorizes ``count`` Ontologies."""

    from modeling_team.tests.test_r3011_acceptance import _freeze

    questions = _questions(count)
    frozen = _freeze(questions)
    ids = [f"ontology-{index}" for index in range(1, count + 1)]
    packet = _platform_packet(
        freeze=questions,
        authorized_read_tools=list(tools),
        authorized_scope=ids,
        model_binding={
            "schema_version": "r3-0-011-model-binding/v1",
            "batch_id": frozen["batch_id"],
            "freeze_digest": frozen["snapshot_digest"],
            "bound_at": "2026-09-09T00:00:00+00:00",
            "ontologies": [
                {
                    "project_id": "project-1",
                    "ontology_id": ontology_id,
                    "workspace_state": {"state_digest": f"ws-{index}"},
                    "graph_state": {"state_digest": f"graph-{index}"},
                    "authorized_read_tools": list(tools),
                }
                for index, ontology_id in enumerate(ids, start=1)
            ],
        },
    )
    entries = v3_proxy_scope_entries(
        packet, {ontology_id: f"graph-set-{index}" for index, ontology_id in enumerate(ids, start=1)}
    )
    proxy = ScopedReadProxy(
        socket_path=tmp_path / "platform-proxy.sock",
        token="proxy-token",
        read_key="read-key",
        authorized_ontologies=entries,
        ticket_digest=packet.freeze_digest,
        model_state_digest="ws-1",
        allowed_tools=list(tools),
        forward=forward,
        acceptance_round_id="r3011-batch",
        child_handle_digest="c" * 64,
        exact_schemas=v3_examiner_proxy_schemas(tools),
    )
    return proxy, packet


def test_v3_partial_reports_survive_the_shared_list_teardown(tmp_path):
    """One accepted question then a dead child: the report is still retained.

    ``destroy()`` clears ``submitted_reports``, which is the caller's own list;
    the v3 boundary must put the accepted values back so a failed batch can
    still name the questions that landed (and mark the rest incomplete).
    """

    from modeling_team.runtimes.codex import (
        CodexRuntimeAdapter,
        ExaminerRuntimeBlocked,
        _CodexChildResource,
    )
    from modeling_team.contracts import repository_root

    packet = _batch_packet(role="platform-examiner")
    contract = _batch_contract("platform-examiner", packet)
    owned_roots: list[str] = []
    accepted = [_examiner_entry(packet.batch_id, "cq-1")]

    def factory(spec: dict):
        resource = _CodexChildResource(spec, None, report_sink=_FakeSink(contract))
        resource.submitted_reports = spec["_submitted_reports"]
        resource.submitted_reports.extend(accepted)
        resource.process = _DeadProcess()
        owned_roots.append(spec["private_root"])
        return resource

    adapter = CodexRuntimeAdapter(
        repository_root=repository_root(), acceptance_child_factory=factory
    )
    reports: list[dict] = []
    with pytest.raises(ExaminerRuntimeBlocked) as blocked:
        adapter.run_v3_acceptance_child(
            packet,
            role_instructions="answer the batch in order",
            reports=reports,
            read_key="read-key",
            platform_forwarder=lambda tool, arguments, key: {"ok": True},
            timeout_seconds=5.0,
            graph_set_ids={"ontology-1": "graph-set-1", "ontology-2": "graph-set-2"},
        )
    assert blocked.value.evidence["reason_code"] == "child-exited"
    assert [report["question_id"] for report in reports] == ["cq-1"]
    # The shared legacy teardown still removed the private tree it owned.
    assert owned_roots and not Path(owned_roots[0]).exists()


def test_v3_wait_ends_promptly_when_the_turn_ends_before_the_batch_completes(tmp_path):
    """2026-10-05 public judge failure: the judge turn went terminal with an
    incomplete batch, and the wait loop could only burn the full session
    deadline over a live-but-idle child.  The child's single turn is the only
    turn it will ever get, so the existing ``terminal_event`` latch must end
    the wait with the same ``batch-incomplete`` outcome (partial reports kept)
    after a short settle, long before the deadline."""
    from modeling_team.runtimes.codex import (
        CodexRuntimeAdapter,
        ExaminerRuntimeBlocked,
        _CodexChildResource,
    )
    from modeling_team.contracts import repository_root

    packet = _batch_packet(role="acceptance")
    contract = _batch_contract("acceptance", packet)
    sink, _ = _start_sink(tmp_path, contract=contract, kind="acceptance")

    def factory(spec: dict):
        resource = _CodexChildResource(spec, None, report_sink=sink)
        resource.submitted_reports = spec["_submitted_reports"]
        resource.submitted_reports.extend([_verdict_entry(packet.batch_id, "cq-1")])
        resource.process = _IdleProcess()
        # The stdout pump latches this on turn/completed; the turn is over and
        # no second turn is ever started for a v3 child.
        resource.terminal_event = True
        return resource

    adapter = CodexRuntimeAdapter(
        repository_root=repository_root(), acceptance_child_factory=factory
    )
    verdicts: list[dict] = []
    started = time.monotonic()
    with pytest.raises(ExaminerRuntimeBlocked) as blocked:
        adapter.run_v3_acceptance_child(
            packet,
            role_instructions="judge the batch in order",
            reports=verdicts,
            timeout_seconds=12.0,
        )
    elapsed = time.monotonic() - started
    assert blocked.value.evidence["reason_code"] == "batch-incomplete"
    assert blocked.value.evidence["turn_terminal"] is True
    # The partial verdict survived: the batch report can still name what did
    # land instead of discarding the session.
    assert [report["question_id"] for report in verdicts] == ["cq-1"]
    assert elapsed < 8.0


def test_v3_child_reports_its_own_teardown_outcome(tmp_path):
    """The v3 boundary observes its child's teardown; legacy destroy is untouched."""

    from modeling_team.runtimes.codex import (
        CodexRuntimeAdapter,
        _CodexChildResource,
    )
    from modeling_team.contracts import repository_root

    packet = _batch_packet(role="acceptance")
    contract = _batch_contract("acceptance", packet)
    # A REAL private sink: the observer must read its actual shutdown, never a
    # fake ``active`` flag (product finding P3).
    sink, _ = _start_sink(tmp_path, contract=contract, kind="acceptance")

    def factory(spec: dict):
        resource = _CodexChildResource(spec, None, report_sink=sink)
        resource.submitted_reports = spec["_submitted_reports"]
        # The batch-complete latch counts the shared list, exactly like a real
        # private sink appending through ``report_submit_payload``.
        resource.submitted_reports.extend(
            [_verdict_entry(packet.batch_id, "cq-1"), _verdict_entry(packet.batch_id, "cq-2")]
        )
        resource.process = _IdleProcess()
        return resource

    adapter = CodexRuntimeAdapter(
        repository_root=repository_root(), acceptance_child_factory=factory
    )
    verdicts: list[dict] = []
    teardown: dict = {}
    returned = adapter.run_v3_acceptance_child(
        packet,
        role_instructions="judge the batch in order",
        reports=verdicts,
        timeout_seconds=5.0,
        teardown=teardown,
    )
    assert [report["question_id"] for report in returned] == ["cq-1", "cq-2"]
    assert [report["question_id"] for report in verdicts] == ["cq-1", "cq-2"]
    assert teardown == {
        "child_stopped": True,
        "child_destroyed": True,
        "report_sink_stopped": True,
        "proxy_stopped": True,
        "private_root_removed": True,
        # This deterministic child never owned a socket root; absence is not a
        # teardown failure.
        "socket_root_removed": True,
    }
    # The sink above was a real AF_UNIX server stopped by the shared destroy;
    # a stopped real sink must finally read as stopped (product finding P3).


def test_the_v3_observer_reads_a_real_report_sink_shutdown(tmp_path):
    """``ReportSinkServer`` has no ``active`` property, so the v3 observer must
    read its real shutdown state instead of defaulting every real sink to
    "still running" (product finding P3: full_pass could never be true)."""

    from modeling_team.runtimes.codex import _v3_child_teardown_evidence

    resource = SimpleNamespace(stopped=True, destroyed=True)

    def evidence(sink, thread=None):
        return _v3_child_teardown_evidence(
            resource,
            proxy=None,
            report_sink=sink,
            private_root="",
            socket_root="",
            sink_thread=thread,
        )["report_sink_stopped"]

    # No sink at all: nothing is live, nothing to stop.
    assert evidence(None) is True
    # Never started: no serve loop and no socket were ever created, so there is
    # no live endpoint to report.
    sink = ReportSinkServer(tmp_path / "idle.sock", TOKEN, lambda report: None)
    assert evidence(sink) is True
    sink.start()
    thread = sink._thread
    # A genuinely running sink is reported as running -- success is never
    # fabricated here, which is exactly what the old ``active`` probe did.
    assert evidence(sink, thread) is False
    sink.stop()
    # Started and then stopped: serve loop exited, listener closed, socket file
    # removed, and the pre-destroy thread handle is no longer alive.
    assert evidence(sink, thread) is True


def test_v3_wrapper_restores_reports_even_when_destroy_raises(tmp_path):
    """A raising legacy ``destroy`` must not discard the accepted reports."""

    from modeling_team.runtimes.codex import (
        CodexRuntimeAdapter,
        ExaminerRuntimeBlocked,
        _CodexChildResource,
    )
    from modeling_team.contracts import repository_root

    packet = _batch_packet(role="platform-examiner")
    contract = _batch_contract("platform-examiner", packet)
    # A REAL started sink stays live when this destroy fails before stopping it;
    # the observer must see that instead of trusting a fake ``active`` flag.
    sink, _ = _start_sink(tmp_path, contract=contract, kind="platform")

    def factory(spec: dict):
        resource = _CodexChildResource(spec, None, report_sink=sink)
        resource.submitted_reports = spec["_submitted_reports"]
        resource.submitted_reports.extend([_examiner_entry(packet.batch_id, "cq-1")])
        resource.process = _DeadProcess()
        # Legacy destroy is not modified anywhere; this child's destroy simply
        # fails after marking itself destroyed (a socket unlink error, say).
        def broken_destroy():
            resource.destroyed = True
            raise RuntimeError("socket unlink failed")

        resource.destroy = broken_destroy
        return resource

    adapter = CodexRuntimeAdapter(
        repository_root=repository_root(), acceptance_child_factory=factory
    )
    reports: list[dict] = []
    teardown: dict = {}
    with pytest.raises(ExaminerRuntimeBlocked) as blocked:
        adapter.run_v3_acceptance_child(
            packet,
            role_instructions="answer the batch in order",
            reports=reports,
            read_key="read-key",
            platform_forwarder=lambda tool, arguments, key: {"ok": True},
            timeout_seconds=5.0,
            graph_set_ids={"ontology-1": "graph-set-1", "ontology-2": "graph-set-2"},
            teardown=teardown,
        )
    assert blocked.value.evidence["reason_code"] == "child-exited"
    # The accepted report is restored into the caller's list even though the
    # legacy destroy raised before clearing it.
    assert [report["question_id"] for report in reports] == ["cq-1"]
    # The exact cleanup outcome is recorded, including the destroy failure and
    # the sink it never reached.
    assert teardown["destroy_error"] == "RuntimeError: socket unlink failed"
    assert teardown["child_destroyed"] is True
    assert teardown["report_sink_stopped"] is False
    assert teardown["private_root_removed"] is False


# --- v3 read scope: subsets excluding the primary Ontology --------------------


def _hints(packet) -> dict:
    """One legacy-bridge style projection of the primary authorized entry."""

    return {
        "project_id": "project-1",
        "scope_mode": "ontologies",
        "query": "coverage",
        "ontology_id": "ontology-1",
        "graph_set_id": "graph-set-1",
        "model_state_digest": "ws-1",
        "ticket_digest": v3_ticket_digest(packet.freeze_digest),
    }


def test_v3_proxy_subset_reads_drop_the_primary_singleton_hints(tmp_path):
    """A/B/C authorized: B-only and B+C both read, with the primary's values gone."""

    forwarded: list[tuple[str, dict, str]] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        forwarded.append((tool, dict(arguments), key))
        return {"ok": True}

    proxy, packet = _multi_proxy(tmp_path, forward=forward)
    hints = _hints(packet)

    # B only: the selected entry's own binding is injected.
    first = proxy.handle(
        {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {**hints, "ontology_ids": ["ontology-2"]},
        }
    )
    assert first["ok"] is True
    sent = forwarded[-1][1]
    assert sent["ontology_ids"] == ["ontology-2"]
    assert sent["ontology_id"] == "ontology-2"
    assert sent["graph_set_id"] == "graph-set-2"
    assert sent["model_state_digest"] == "ws-2"
    assert sent["project_id"] == "project-1"

    # B+C: per-Ontology values cannot be one value, so the projected singletons
    # are dropped instead of turning the read into a contradictory denial.
    second = proxy.handle(
        {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {**hints, "ontology_ids": ["ontology-2", "ontology-3"]},
        }
    )
    assert second["ok"] is True
    sent = forwarded[-1][1]
    assert sent["ontology_ids"] == ["ontology-2", "ontology-3"]
    assert "ontology_id" not in sent
    assert "graph_set_id" not in sent
    assert "model_state_digest" not in sent
    assert sent["project_id"] == "project-1"
    assert sent["ticket_digest"] == v3_ticket_digest(packet.freeze_digest)
    assert [entry["ontology_ids"] for entry in proxy.requests] == [
        ["ontology-2"],
        ["ontology-2", "ontology-3"],
    ]


def test_v3_proxy_still_denies_an_unauthorized_subset(tmp_path):
    forwarded: list[tuple[str, dict, str]] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        forwarded.append((tool, dict(arguments), key))
        return {"ok": True}

    proxy, packet = _multi_proxy(tmp_path, forward=forward)
    response = proxy.handle(
        {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {
                **_hints(packet),
                "ontology_ids": ["ontology-2", "ontology-9"],
            },
        }
    )
    assert response["ok"] is False and response["code"] == "read-scope-denied"
    assert forwarded == [] and proxy.backend_calls == 0


def test_v3_proxy_tools_list_advertises_the_exact_schemas(tmp_path):
    proxy, _packet = _multi_proxy(tmp_path)
    response = proxy.handle({"token": "proxy-token", "operation": "tools/list"})
    assert response["ok"] is True
    assert response["tools"] == ["query_semantic_context"]
    schema = response["schemas"][0]
    assert schema["name"] == "query_semantic_context"
    required = schema["inputSchema"]["required"]
    assert "project_id" in required and "ticket_digest" in required
    assert not {"ontology_id", "graph_set_id", "model_state_digest"} & set(required)
    assert schema["inputSchema"]["properties"]["ontology_ids"]["type"] == "array"


# --- v3 read bridge: real subprocess selections and schema pass-through -------


def _drive_bridge(tmp_path: Path, proxy, *, env: dict) -> tuple[object, object]:
    """Start the real read bridge against ``proxy`` and return (process, request)."""

    import shutil
    import subprocess
    import sys

    socket_path = tmp_path / "platform-proxy.sock"
    token_path = tmp_path / "platform-proxy.token"
    token_path.write_text("proxy-token\n", encoding="utf-8")
    proxy.socket_path = socket_path
    proxy.start()
    bridge = tmp_path / "read_proxy_mcp.py"
    shutil.copyfile(Path(__file__).resolve().parents[1] / "read_proxy_mcp.py", bridge)
    process = subprocess.Popen(
        [
            sys.executable,
            str(bridge),
            "--stdio",
            "--socket",
            str(socket_path),
            "--token-file",
            str(token_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )

    def request(request_id: int, method: str, params: dict | None = None) -> dict:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}},
                separators=(",", ":"),
            )
            + "\n"
        )
        process.stdin.flush()
        return json.loads(process.stdout.readline())

    return process, request


def _close_bridge(process) -> None:
    if process.stdin is not None:
        process.stdin.close()
    process.wait(timeout=10)


def test_v3_bridge_forwards_subset_selections_and_exact_schemas(tmp_path):
    forwarded: list[tuple[str, dict, str]] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        forwarded.append((tool, dict(arguments), key))
        return {"ok": True, "data": {"state": "ready"}}

    proxy, packet = _multi_proxy(tmp_path, forward=forward)
    ticket = v3_ticket_digest(packet.freeze_digest)
    process, request = _drive_bridge(
        tmp_path,
        proxy,
        env={**os.environ, "PLATFORM_PROXY_MODE": "v3-acceptance", "PLATFORM_PROXY_TICKET_DIGEST": ticket},
    )
    try:
        listed = request(1, "tools/list")["result"]["tools"]
        schema = listed[0]
        assert schema["name"] == "query_semantic_context"
        assert "ontology_id" not in schema["inputSchema"]["required"]
        assert schema["inputSchema"]["properties"]["ontology_ids"]["type"] == "array"
        # Second-only selection through the real bridge.
        first = request(
            2,
            "tools/call",
            {
                "name": "query_semantic_context",
                "arguments": {
                    "project_id": "project-1",
                    "scope_mode": "ontologies",
                    "ontology_ids": ["ontology-2"],
                    "query": "coverage",
                },
            },
        )
        assert first["result"]["isError"] is False
        assert forwarded[-1][1]["ontology_ids"] == ["ontology-2"]
        assert forwarded[-1][1]["graph_set_id"] == "graph-set-2"
        assert forwarded[-1][1]["model_state_digest"] == "ws-2"
        assert forwarded[-1][2] == "read-key"
        # Multi-Ontology subset excluding the primary: no contradictory
        # singleton is injected by the bridge, and the proxy drops any hint.
        second = request(
            3,
            "tools/call",
            {
                "name": "query_semantic_context",
                "arguments": {
                    "project_id": "project-1",
                    "scope_mode": "ontologies",
                    "ontology_ids": ["ontology-2", "ontology-3"],
                    "query": "coverage",
                },
            },
        )
        assert second["result"]["isError"] is False
        sent = forwarded[-1][1]
        assert sent["ontology_ids"] == ["ontology-2", "ontology-3"]
        assert "ontology_id" not in sent and "graph_set_id" not in sent
        assert sent["ticket_digest"] == ticket
    finally:
        _close_bridge(process)
        proxy.stop()


def test_v3_bridge_binds_the_host_ticket_and_keeps_it_optional(tmp_path):
    """R3.0-015 S4: the child never transcribes the Host-owned batch ticket.

    The real acceptance3/4 examiner sent its own ``ticket_digest`` on all six
    reads; the value arrived at the proxy as a contradicting caller claim and
    every otherwise-authorized scope was refused with ``read-scope-denied``.
    The frozen ticket is Host scope like the per-Ontology bindings, so the child
    schema stops requiring it and the bridge binds the value it was launched
    with, whatever a caller sends or omits.
    """

    forwarded: list[tuple[str, dict, str]] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        forwarded.append((tool, dict(arguments), key))
        return {"ok": True, "data": {"state": "ready"}}

    proxy, packet = _multi_proxy(tmp_path, forward=forward)
    ticket = v3_ticket_digest(packet.freeze_digest)
    process, request = _drive_bridge(
        tmp_path,
        proxy,
        env={**os.environ, "PLATFORM_PROXY_MODE": "v3-acceptance", "PLATFORM_PROXY_TICKET_DIGEST": ticket},
    )
    try:
        schema = request(1, "tools/list")["result"]["tools"][0]["inputSchema"]
        assert "ticket_digest" not in schema["required"]
        # The property stays advertised as an optional, Host-owned sanity field;
        # only the requirement and the caller's influence are removed.
        assert "ticket_digest" in schema["properties"]
        assert "ontology_ids" in schema["properties"]
        selection = {
            "project_id": "project-1",
            "scope_mode": "ontologies",
            "ontology_ids": ["ontology-2"],
            "query": "coverage",
        }
        for request_id, fabricated in enumerate(("sha256:" + "9" * 64, "9" * 64), start=2):
            called = request(
                request_id,
                "tools/call",
                {
                    "name": "query_semantic_context",
                    "arguments": {**selection, "ticket_digest": fabricated},
                },
            )
            assert called["result"]["isError"] is False
            assert forwarded[-1][1]["ticket_digest"] == ticket
            assert forwarded[-1][1]["ontology_ids"] == ["ontology-2"]
        omitted = request(
            4,
            "tools/call",
            {"name": "query_semantic_context", "arguments": dict(selection)},
        )
        assert omitted["result"]["isError"] is False
        assert forwarded[-1][1]["ticket_digest"] == ticket
        assert len(forwarded) == 3
    finally:
        _close_bridge(process)
        proxy.stop()


@pytest.mark.parametrize("host_ticket", ["f" * 64, ""])
def test_v3_bridge_still_refuses_a_host_binding_outside_the_frozen_batch(tmp_path, host_ticket):
    """A stale or unset Host batch binding still fails closed before any forward.

    The bridge now supplies the Host value instead of the child's transcription,
    so the proxy's batch-identity check is what authorizes a read: a well-formed
    ticket for another batch -- or an unconfigured empty one -- is refused
    exactly as before, and the child's own correct-looking value cannot rescue it.
    """

    forwarded: list[tuple[str, dict, str]] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        forwarded.append((tool, dict(arguments), key))
        return {"ok": True, "data": {"state": "ready"}}

    proxy, _packet = _multi_proxy(tmp_path, forward=forward)
    process, request = _drive_bridge(
        tmp_path,
        proxy,
        env={
            **os.environ,
            "PLATFORM_PROXY_MODE": "v3-acceptance",
            "PLATFORM_PROXY_TICKET_DIGEST": host_ticket,
        },
    )
    try:
        denied = request(
            1,
            "tools/call",
            {
                "name": "query_semantic_context",
                "arguments": {
                    "project_id": "project-1",
                    "scope_mode": "ontologies",
                    "ontology_ids": ["ontology-2"],
                    "query": "coverage",
                },
            },
        )
        assert "result" not in denied
        assert "read-scope-denied" in json.dumps(denied)
        assert forwarded == []
    finally:
        _close_bridge(process)
        proxy.stop()


def test_legacy_bridge_mode_still_projects_the_primary_scope(tmp_path):
    """Without PLATFORM_PROXY_MODE the bridge keeps its legacy projection."""

    forwarded: list[tuple[str, dict, str]] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        forwarded.append((tool, dict(arguments), key))
        return {"ok": True, "data": {"state": "ready"}}

    proxy, packet = _multi_proxy(
        tmp_path, count=2, tools=("get_ontology_read_model",), forward=forward
    )
    process, request = _drive_bridge(
        tmp_path,
        proxy,
        env={
            **os.environ,
            "PLATFORM_PROXY_PROJECT_ID": "project-1",
            "PLATFORM_PROXY_ONTOLOGY_ID": "ontology-1",
            "PLATFORM_PROXY_GRAPH_SET_ID": "graph-set-1",
            "PLATFORM_PROXY_TICKET_DIGEST": v3_ticket_digest(packet.freeze_digest),
            "PLATFORM_PROXY_MODEL_STATE_DIGEST": "ws-1",
        },
    )
    try:
        listed = request(1, "tools/list")["result"]["tools"]
        # Legacy advertising is unchanged: a generic object, not v3 schemas.
        assert listed[0]["inputSchema"] == {"type": "object"}
        called = request(
            2,
            "tools/call",
            {"name": "get_ontology_read_model", "arguments": {"model_name": "classes"}},
        )
        assert called["result"]["isError"] is False
        sent = forwarded[-1][1]
        assert sent["ontology_id"] == "ontology-1"
        assert sent["graph_set_id"] == "graph-set-1"
        assert sent["model_state_digest"] == "ws-1"
        assert sent["project_id"] == "project-1"
    finally:
        _close_bridge(process)
        proxy.stop()


@pytest.mark.parametrize("startup_failure", [
    "plain", "rpc", None, "steps", "large",
    "pump-read", "pump-metrics", "pump-notification", "pump-first",
])
def test_native_public_judge_startup_failure_preserves_first_blocker(
    tmp_path, monkeypatch, startup_failure,
):
    """Real factory/sink; only the native process/RPC boundary is controlled."""
    from io import StringIO
    from threading import Event
    import hashlib

    from modeling_team.acceptance_runtime import ExaminerRuntimeBlocked, ExaminerRunMetrics
    from modeling_team.contracts import repository_root
    from modeling_team.model_routing import load_team_model_profile
    from modeling_team.runtimes.codex import (
        CodexRuntimeAdapter, CodexRuntimeError, CodexRuntimeRPCError, _CodexChildResource,
    )

    # Judge packets carry the selected questions, not freeze visibility.
    # Use the same whole-11 projection that public selection supplies.
    packet = _batch_packet(role="acceptance", questions=_questions(11))
    from modeling_team.acceptance_runtime import (
        AcceptanceBatchPacket, _packet_canonical, _unfreeze_packet,
    )
    if startup_failure == "large":
        payload = _unfreeze_packet(packet.payload)
        payload["platform_read_responses"] = {
            question["question_id"]: [{
                "tool": "query_semantic_context", "request_digest": "a" * 64,
                "response_digest": "b" * 64,
                "artifact_path": f"acceptance/generic/{question['question_id']}.json",
                "page": {"offset": 0},
                "result": {"id": "generic-resource", "content": (
                    "x" if index < 10 else "y"
                ) * 150_000},
            }]
            for index, question in enumerate(_questions(11))
        }
        payload["evidence_bundle"].pop("bundle_digest", None)
        packet = AcceptanceBatchPacket.build("acceptance", payload)
    original_bytes = _packet_canonical(_unfreeze_packet(packet.payload))
    process = SimpleNamespace(
        stdin=StringIO(), stdout=StringIO(), stderr=StringIO(),
        poll=lambda: None, terminate=lambda: None, kill=lambda: None,
        wait=lambda **kwargs: 0,
    )
    adapter = CodexRuntimeAdapter(
        repository_root=repository_root(), use_bwrap=False,
        process_factory=lambda *args, **kwargs: process,
    )
    adapter._team_model_profile = load_team_model_profile(repository_root(), "openai-sol-medium")
    auth = tmp_path / "fixture-auth.json"
    auth.write_text("{}")
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: auth)
    monkeypatch.setattr(adapter, "_ensure_standalone_provider_sessions", lambda: None)
    monkeypatch.setattr(adapter, "_seed_models_cache", lambda *args: None)
    pump_stage = (startup_failure.removeprefix("pump-")
                  if isinstance(startup_failure, str) and startup_failure.startswith("pump-")
                  else None)
    def pump_exception(*args):
        raise TypeError("private sentinel: fixture credentials and notification body")

    def idle_output(agent, timeout):
        if pump_stage in {"read", "first"}:
            pump_exception()
        if pump_stage:
            return json.dumps({"method": "item/started", "params": {
                "threadId": "fixture-judge-thread", "item": {"type": "userMessage"},
            }})
        Event().wait(timeout)
        return None

    monkeypatch.setattr(adapter, "_read_output_line", idle_output)
    if pump_stage == "metrics":
        monkeypatch.setattr(ExaminerRunMetrics, "observe_notification", pump_exception)
    elif pump_stage == "notification":
        monkeypatch.setattr(adapter, "_notification", pump_exception)
    sinks = []
    start = ReportSinkServer.start

    def capture_start(sink):
        sinks.append(sink)
        start(sink)

    monkeypatch.setattr(ReportSinkServer, "start", capture_start)
    calls = []

    def rpc(agent, method, params):
        calls.append(method)
        if method == "initialize":
            return {}
        if method == "thread/start":
            assert (agent.home / "input.json").read_bytes() == original_bytes
            return {"thread": {"id": "fixture-judge-thread"}}
        if method == "mcpServerStatus/list":
            if startup_failure == "rpc":
                raise CodexRuntimeRPCError(
                    method, -32603, "rpc_error", server_message="private sentinel",
                )
            if startup_failure == "plain":
                raise CodexRuntimeError("fixture MCP discovery failed; private sentinel")
            return {"data": [{"name": "examiner_report", "tools": [
                {"name": "submit_examiner_report"},
            ]}]}
        if method == "turn/start":
            if startup_failure == "large":
                text = "".join(item["text"] for item in params["input"])
                if len(text) > 1_048_576:
                    raise CodexRuntimeRPCError(method, -32602, "rpc_error")
                assert " PACKET_JSON=" not in text
                encoded = text.split(" TRANSPORT_JSON=", 1)[1]
                transport, _ = json.JSONDecoder().raw_decode(encoded)
                assert transport["encoding"] == "lossless-result-body-registry"
                expanded = transport["packet"]
                registry = transport["result_body_registry"]
                assert len(registry) == 2
                for entries in expanded["platform_read_responses"].values():
                    for entry in entries:
                        digest = entry.pop("result_ref")
                        assert digest in registry
                        entry["result"] = registry[digest]
                assert _packet_canonical(expanded) == original_bytes
                assert hashlib.sha256(original_bytes).hexdigest() == packet.canonical_digest
                assert f"PACKET_DIGEST={packet.canonical_digest}" in text
            if startup_failure == "steps" or pump_stage:
                return {"turn": {"id": "fixture-judge-turn"}}
            for question_id in sinks[0].batch_contract.question_ids:
                response = _submit(
                    sinks[0].socket_path, _verdict_entry(packet.batch_id, question_id),
                    token=sinks[0].token,
                )
                assert response["ok"] is True
            return {"turn": {"id": "fixture-judge-turn"}}
        raise AssertionError(method)

    monkeypatch.setattr(adapter, "_rpc", rpc)
    observed_metrics = []
    if pump_stage == "first":
        def first_failure_output(resource, adapter, agent):
            resource._adapter = adapter
            resource._child_agent = agent
            assert resource._record_failure("runtime", "fixture-first-failure") is True
            resource._run_stdout_pump()

        monkeypatch.setattr(_CodexChildResource, "start_stdout_pump", first_failure_output)
    if startup_failure == "steps":
        def batch_output(resource, adapter, agent):
            metrics = resource.metrics
            for step in range(1, 32):
                metrics.observe_notification({
                    "method": "thread/tokenUsage/updated",
                    "params": {"threadId": "fixture-judge-thread", "tokenUsage": {
                        "total": {"inputTokens": step, "outputTokens": step},
                    }},
                })
            metrics.allow_inference()
            observed_metrics.append(metrics)
            for question_id in sinks[0].batch_contract.question_ids:
                assert _submit(
                    sinks[0].socket_path, _verdict_entry(packet.batch_id, question_id),
                    token=sinks[0].token,
                )["ok"] is True

        monkeypatch.setattr(_CodexChildResource, "start_stdout_pump", batch_output)
    try:
        teardown = {}
        def run():
            return adapter.run_v3_acceptance_child(
                packet, role_instructions="judge the selected batch", reports=[],
                timeout_seconds=1, teardown=teardown,
            )

        if pump_stage:
            with pytest.raises(ExaminerRuntimeBlocked) as blocked:
                run()
            if pump_stage == "first":
                assert blocked.value.evidence["reason_code"] == "fixture-first-failure"
                assert "exception_class" not in blocked.value.evidence
                assert "output_stage" not in blocked.value.evidence
            else:
                assert blocked.value.evidence["reason_code"] == "child-output-failed"
                assert blocked.value.evidence["exception_class"] == "TypeError"
                assert blocked.value.evidence["output_stage"] == pump_stage
            assert "private sentinel" not in json.dumps(blocked.value.as_dict())
            assert "message" not in blocked.value.evidence
            assert teardown["child_destroyed"] is True
            assert teardown["private_root_removed"] is True
            assert teardown["socket_root_removed"] is True
        elif startup_failure in {"plain", "rpc"}:
            with pytest.raises(ExaminerRuntimeBlocked) as blocked:
                run()
            assert blocked.value.evidence["reason_code"] == "child-start-failed"
            assert blocked.value.evidence["startup_stage"] == "mcp-preflight"
            assert "private sentinel" not in str(blocked.value.evidence)
            if startup_failure == "rpc":
                assert blocked.value.evidence["rpc_error"] == {
                    "category": "rpc_error", "code": -32603,
                }
            else:
                assert "rpc_error" not in blocked.value.evidence
        else:
            verdicts = run()
            assert [item["question_id"] for item in verdicts] == [
                question["question_id"] for question in _questions(11)
            ]
        assert calls == ["initialize", "thread/start", "mcpServerStatus/list"] + (
            [] if startup_failure in {"plain", "rpc"} else ["turn/start"]
        )
        if startup_failure == "steps":
            assert observed_metrics[0].inference_steps == 31
            assert observed_metrics[0].max_inference_steps is None
            assert observed_metrics[0].blocked is None
        assert len(sinks) == 1
        assert isinstance(sinks[0].batch_contract, V3BatchReportContract)
        assert len(sinks[0].batch_contract.question_ids) == 11
        assert sinks[0]._thread is None or not sinks[0]._thread.is_alive()
    finally:
        adapter.stop()
