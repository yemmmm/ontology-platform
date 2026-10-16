"""R3.0-012 D: retained platform responses and the evidence recheck (design §4.1/§4.2).

Mechanical coverage for the read-time response retention seam, the receipt-bound
collector that resolves Examiner evidence refs, the post-exit evidence recheck,
and the report/packet projections.  No App Server, no child process and no LLM:
the proxy tests use the real ``ScopedReadProxy`` with a local forward callable
(the exact seam ``McpReadForwarder`` occupies), and the CLI tests drive the real
``_run_cq_acceptance`` executed path through the injectable forwarder factory
with a bounded stub adapter -- the same developer-double convention the R3.0-011
CLI file uses.
"""

from __future__ import annotations

import hashlib
import json
import socket
import stat
from argparse import Namespace
from pathlib import Path, PurePosixPath

import pytest

from modeling_team.__main__ import (
    _CQ_PLATFORM_READ_KEY_ENV,
    _cq_collect_platform_read_responses,
    _cq_load_platform_read_artifact,
    _cq_platform_read_persistence,
    _cq_recheck_evidence_responses,
    _cq_semantic_projection,
    _run_cq_acceptance,
)
from modeling_team.acceptance_runtime import (
    PLATFORM_READ_ARTIFACT_SCHEMA,
    ChildRuntimeError,
    ScopedReadProxy,
    V3ProxyCallReceipt,
    build_acceptance_judge_packet,
    canonical_read_digest,
    v3_examiner_proxy_schemas,
    v3_proxy_scope_entries,
    v3_ticket_digest,
)
from modeling_team.competency_questions import (
    CQ_BATCH_REPORT_SCHEMA,
    CQ_EVIDENCE_BUNDLE_SCHEMA,
    batch_report_is_full_pass,
    build_batch_report,
    content_digest,
)
from modeling_team.contracts import TeamConfigurationError, repository_root
from modeling_team.handoff_materials import HandoffMaterials
from modeling_team.tests.test_r3011_acceptance import _question, _freeze, _platform_packet

REPO_ROOT = repository_root()

_RUN_CONTRACT = {
    "schema_version": "r3-0-011-run-contract/v1",
    "run_id": "r3012-run",
    "profile_id": "r3-0-011-competency-question",
    "task_id": "r3-0-008b-staged-real",
    "parameters": {"competency_question_acceptance": True},
}


# --- shared fixtures -----------------------------------------------------------


def _platform_context() -> dict:
    """The live workspace state the scripted forwarder serves.

    This is the ``data`` payload of the canonical success envelope, exactly the
    value ``McpReadForwarder.forward`` nests one level down.
    """

    return {
        "state": "ready",
        "model_revision": 1,
        "ontology_id": "ontology-1",
        "content_hash": "h1",
    }


def _handoff_binding(*, batch_id: str, freeze_digest: str) -> dict:
    return {
        "schema_version": "r3-0-011-model-binding/v1",
        "batch_id": batch_id,
        "freeze_digest": freeze_digest,
        "bound_at": "2026-09-13T00:00:00+00:00",
        "ontologies": [
            {
                "project_id": "project-1",
                "ontology_id": "ontology-1",
                "workspace_state": {"state_digest": "handoff-marker:workspace"},
                "model_version_state": {"state_digest": "handoff-marker:graph"},
                "authorized_read_tools": ["query_semantic_context"],
            }
        ],
    }


def _retaining_proxy(
    tmp_path: Path,
    artifact_root: Path,
    *,
    forward,
    tools=("get_ontology_workspace_context",),
    response_material=None,
    packet=None,
):
    """A real v3 ScopedReadProxy whose reads persist under ``artifact_root``."""

    packet = packet or _platform_packet([_question("cq-1")])
    entries = v3_proxy_scope_entries(packet)
    proxy = ScopedReadProxy(
        socket_path=tmp_path / "platform-proxy.sock",
        token="proxy-token",
        read_key="read-key",
        authorized_ontologies=entries,
        ticket_digest=packet.freeze_digest,
        model_state_digest="ws-1",
        allowed_tools=list(tools),
        forward=forward,
        acceptance_round_id="r3012-batch",
        child_handle_digest="a" * 64,
        exact_schemas=v3_examiner_proxy_schemas(tools),
        persist_response=_cq_platform_read_persistence(artifact_root),
        response_material=response_material,
    )
    return proxy


def _read_once(proxy: ScopedReadProxy) -> dict:
    return proxy.handle(
        {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "get_ontology_workspace_context",
            "arguments": {"project_id": "project-1", "ontology_id": "ontology-1"},
        }
    )


# --- §4.1 read-time retention (T2-14/T2-5) -------------------------------------


def test_a_successful_read_retains_the_canonical_request_and_result(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()

    def forward(tool: str, arguments: dict, key: str) -> dict:
        assert key == "read-key"
        return {"ok": True, "data": {"ontology_id": arguments["ontology_id"]}}

    proxy = _retaining_proxy(tmp_path, artifact_root, forward=forward)
    response = _read_once(proxy)
    assert response["ok"] is True
    receipt = proxy.receipt_snapshot[0]
    assert receipt.artifact_path == f"acceptance/r3012-batch/platform-read/{'a' * 64}/0.json"

    # The retention happens at read time, so the host reloads the same document
    # even after teardown, with the digests recomputed from the parsed content.
    loaded = _cq_load_platform_read_artifact(artifact_root, receipt)
    assert loaded["tool"] == "get_ontology_workspace_context"
    # The retained request is the proxy's host-injected scoped request, never a
    # child transcription: the frozen scope keys are present and authoritative.
    assert loaded["request"]["project_id"] == "project-1"
    assert loaded["request"]["ontology_id"] == "ontology-1"
    assert loaded["request"]["ontology_id"] == "ontology-1"
    assert loaded["result"] == {"ok": True, "data": {"ontology_id": "ontology-1"}}
    assert receipt.request_digest == canonical_read_digest(
        {"tool": loaded["tool"], "arguments": loaded["request"]}
    )
    assert receipt.response_digest == canonical_read_digest(loaded["result"])

    artifact = artifact_root.joinpath(*PurePosixPath(receipt.artifact_path).parts)
    text = artifact.read_text(encoding="utf-8")
    document = json.loads(text)
    assert set(document) == {"schema_version", "tool", "request", "result"}
    assert document["schema_version"] == PLATFORM_READ_ARTIFACT_SCHEMA
    # No key, token or socket ever lands in the retained bytes.
    assert "read-key" not in text
    assert "proxy-token" not in text
    assert "platform-proxy.sock" not in text
    # Host-only permissions: owner-only file inside owner-only directories.
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o600
    assert stat.S_IMODE(artifact.parent.stat().st_mode) == 0o700


def test_a_retention_failure_is_observable_and_leaves_no_receipt(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()

    def failing_persistence(locator: str, document) -> None:
        raise OSError("disk full")

    packet = _platform_packet([_question("cq-1")])
    entries = v3_proxy_scope_entries(packet)
    proxy = ScopedReadProxy(
        socket_path=tmp_path / "platform-proxy.sock",
        token="proxy-token",
        read_key="read-key",
        authorized_ontologies=entries,
        ticket_digest=packet.freeze_digest,
        model_state_digest="ws-1",
        allowed_tools=["get_ontology_workspace_context"],
        forward=lambda tool, arguments, key: {"ok": True},
        acceptance_round_id="r3012-batch",
        child_handle_digest="a" * 64,
        exact_schemas=v3_examiner_proxy_schemas(("get_ontology_workspace_context",)),
        persist_response=failing_persistence,
    )
    response = _read_once(proxy)
    assert response["ok"] is False
    assert response["code"] == "platform-response-retention-failed"
    assert proxy.persistence_failures == 1
    # The failed call appended no receipt, so it can never become evidence.
    assert proxy.receipt_snapshot == ()
    assert not (artifact_root / "acceptance").exists()


def test_real_socket_response_material_ref_is_readable_without_changing_receipt(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    materials = HandoffMaterials(tmp_path / "materials", "r3012-response-scope")
    materials.register_actor("host", {}, {"judge"})
    materials.register_actor("judge", {}, set())
    seen: list[dict] = []

    def forward(tool: str, arguments: dict, key: str) -> dict:
        return {
            "ok": True,
            "rows": [{"ontology_id": arguments["ontology_id"], "value": 7}],
            "nested": {"source": "governed-read"},
        }

    def publish_response(result):
        seen.append(dict(result))
        written = materials.write_output(
            "host", "responses/read-0.json", json.dumps(result, ensure_ascii=False, sort_keys=True)
        )
        published = materials.publish("host", "judge", written["source_path"])
        return {"material_id": published["material_id"], "path": "read-0.json"}

    proxy = _retaining_proxy(
        tmp_path,
        artifact_root,
        forward=forward,
        response_material=publish_response,
    )
    proxy.start()
    try:
        request = {
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "get_ontology_workspace_context",
            "arguments": {"project_id": "project-1", "ontology_id": "ontology-1"},
        }
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(proxy.socket_path))
            client.sendall(json.dumps(request).encode("utf-8") + b"\n")
            raw = b""
            while b"\n" not in raw:
                block = client.recv(8192)
                assert block
                raw += block
        response = json.loads(raw.split(b"\n", 1)[0].decode("utf-8"))
    finally:
        proxy.stop()

    expected = {
        "ok": True,
        "rows": [{"ontology_id": "ontology-1", "value": 7}],
        "nested": {"source": "governed-read"},
    }
    assert response["ok"] is True
    assert response["result"] == expected
    assert seen == [expected]
    result_ref = response["result_ref"]
    assert set(result_ref) == {"material_id", "path"}
    assert json.loads(materials.resolve("judge", result_ref)) == expected

    receipt = proxy.receipt_snapshot[0]
    assert response["response_digest"] == canonical_read_digest(expected)
    assert receipt.response_digest == response["response_digest"]
    assert receipt.request_digest == response["request_digest"]
    assert response["artifact_path"] == receipt.artifact_path


def test_response_material_failure_keeps_inline_read_and_receipt_retryable(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    attempts = []

    def publish_response(result):
        attempts.append(dict(result))
        if len(attempts) == 1:
            raise OSError("handoff unavailable")
        return {"material_id": "material-retry"}

    proxy = _retaining_proxy(
        tmp_path,
        artifact_root,
        forward=lambda tool, arguments, key: {"ok": True, "value": 7},
        response_material=publish_response,
    )
    first = _read_once(proxy)
    assert first["ok"] is True
    assert "result_ref" not in first
    assert first["material_error"] == "platform-response-material-failed"
    assert first["result"] == {"ok": True, "value": 7}
    assert len(proxy.receipt_snapshot) == 1
    first_receipt = proxy.receipt_snapshot[0]
    assert first_receipt.response_digest == canonical_read_digest(first["result"])

    second = _read_once(proxy)
    assert second["ok"] is True
    assert second["result_ref"] == {"material_id": "material-retry"}
    assert "material_error" not in second
    assert len(proxy.receipt_snapshot) == 2
    assert proxy.receipt_snapshot[0] == first_receipt
    assert attempts == [{"ok": True, "value": 7}, {"ok": True, "value": 7}]


def test_real_read_proxy_facade_preserves_v3_handle_with_response_material(tmp_path, monkeypatch):
    import sys
    from io import StringIO

    from modeling_team import read_proxy_mcp

    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    packet = _platform_packet([_question("cq-1")])
    attempts = 0

    def publish_response(result):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("handoff temporarily unavailable")
        return {"material_id": "material-response", "path": "read.json"}

    proxy = _retaining_proxy(
        tmp_path,
        artifact_root,
        packet=packet,
        forward=lambda tool, arguments, key: {"ok": True, "value": 7},
        response_material=publish_response,
    )
    token_path = tmp_path / "platform-proxy.token"
    token_path.write_text("proxy-token\n", encoding="utf-8")
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_ontology_workspace_context",
                "arguments": {"project_id": "project-1", "ontology_id": "ontology-1"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_ontology_workspace_context",
                "arguments": {"project_id": "project-1", "ontology_id": "ontology-1"},
            },
        },
    ]
    stdin = StringIO("".join(json.dumps(request) + "\n" for request in requests))
    stdout = StringIO()
    proxy.start()
    try:
        monkeypatch.setattr(sys, "argv", [
            "read_proxy_mcp.py",
            "--stdio",
            "--socket",
            str(proxy.socket_path),
            "--token-file",
            str(token_path),
        ])
        monkeypatch.setattr(sys, "stdin", stdin)
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setenv("PLATFORM_PROXY_MODE", "v3-acceptance")
        monkeypatch.setenv("PLATFORM_PROXY_TICKET_DIGEST", v3_ticket_digest(packet.freeze_digest))
        assert read_proxy_mcp.main() == 0
    finally:
        proxy.stop()

    replies = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [reply["id"] for reply in replies] == [1, 2]
    first = json.loads(replies[0]["result"]["content"][0]["text"])
    second = json.loads(replies[1]["result"]["content"][0]["text"])
    assert first["evidence_handle"] == "p0"
    assert first["result_ref"] == {"material_id": "material-response", "path": "read.json"}
    assert first["ok"] is True and first["value"] == 7
    assert second["evidence_handle"] == "p1"
    assert second["material_error"] == "platform-response-material-failed"
    assert "result_ref" not in second
    assert second["ok"] is True and second["value"] == 7


def test_the_persistence_callback_rejects_escaping_locators(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    persist = _cq_platform_read_persistence(artifact_root)
    for locator in ("/etc/passwd", "../../outside.json", ""):
        with pytest.raises(TeamConfigurationError):
            persist(locator, {"schema_version": PLATFORM_READ_ARTIFACT_SCHEMA})
    assert list(artifact_root.iterdir()) == []


def test_a_retained_artifact_validates_after_teardown_and_reformatting(tmp_path):
    """The digest is recomputed over the parsed canonical content, never file bytes."""

    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    proxy = _retaining_proxy(
        tmp_path, artifact_root, forward=lambda tool, arguments, key: {"ok": True, "rows": [1, 2]}
    )
    assert _read_once(proxy)["ok"] is True
    receipt = proxy.receipt_snapshot[0]
    proxy.stop()

    artifact = artifact_root.joinpath(*PurePosixPath(receipt.artifact_path).parts)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    # Whitespace and key order change; the canonical digest must not care.
    artifact.write_text(json.dumps(payload, indent=4, sort_keys=False), encoding="utf-8")
    loaded = _cq_load_platform_read_artifact(artifact_root, receipt)
    assert loaded["result"] == {"ok": True, "rows": [1, 2]}


# --- §4.1 collector: receipt-bound ref resolution (T2-6/T2-7/T2-13) ------------


_QUERY_REQUEST = {
    "project_id": "project-1",
    "ontology_id": "ontology-1",
    "scope_mode": "ontologies",
    "ontology_ids": ["ontology-1"],
    "query": "business meaning",
}
_QUERY_RESULT = {"ok": True, "matches": [], "matches_page": {"truncated": False}}
_TRUNCATED_PAGE = {
    "ordinal": 1,
    "input_cursor": "cursor-1",
    "output_cursor": "cursor-2",
    "has_more": True,
    "sequence_complete": False,
}


def _retained_receipt(
    artifact_root: Path,
    *,
    tool: str = "query_semantic_context",
    request: dict | None = None,
    result: dict | None = None,
    ordinal: int = 0,
    page: dict | None = None,
    retain: bool = True,
) -> V3ProxyCallReceipt:
    request = dict(request or _QUERY_REQUEST)
    result = dict(result or _QUERY_RESULT)
    artifact_path = f"acceptance/r3012-batch/platform-read/{'a' * 64}/{ordinal}.json"
    if retain:
        _cq_platform_read_persistence(artifact_root)(
            artifact_path,
            {
                "schema_version": PLATFORM_READ_ARTIFACT_SCHEMA,
                "tool": tool,
                "request": request,
                "result": result,
            },
        )
    return V3ProxyCallReceipt(
        ordinal=ordinal,
        project_id="project-1",
        ontology_id="ontology-1",

        ticket_digest="b" * 64,
        model_state_digest="c" * 64,
        tool=tool,
        request_digest=canonical_read_digest({"tool": tool, "arguments": request}),
        response_digest=canonical_read_digest(result),
        artifact_path=artifact_path,
        page=page if page is not None else {},
    )


def _ref(receipt: V3ProxyCallReceipt) -> str:
    """The short host-issued handle the proxy returned for this receipt."""

    return f"p{receipt.ordinal}"


def _report(question_id: str, refs: list) -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": "batch-r3011",
        "question_id": question_id,
        "question_content_version": 1,
        "answer": f"answer for {question_id}",
        "evidence_refs": refs,
        "explicit_unknown": [],
        "status": "completed",
        "failure_layer": None,
        "reason": None,
    }


_AUTHORIZED_TOOLS = ["query_semantic_context"]


def test_each_successful_v3_read_returns_the_short_host_issued_handle(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    proxy = _retaining_proxy(
        tmp_path,
        artifact_root,
        forward=lambda tool, arguments, key: {"ok": True, "read": arguments["ontology_id"]},
    )
    first = _read_once(proxy)
    second = _read_once(proxy)
    # One opaque p<ordinal> value per successful read, ready to copy verbatim
    # into evidence_refs -- no digest or path reconstruction left to the child.
    assert first["ok"] is True and first["evidence_handle"] == "p0"
    assert second["ok"] is True and second["evidence_handle"] == "p1"
    assert [receipt.ordinal for receipt in proxy.receipt_snapshot] == [0, 1]


def test_one_receipt_supports_several_questions_and_keeps_its_page(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    receipt = _retained_receipt(artifact_root, page=_TRUNCATED_PAGE)
    # cq-1 repeats the same handle; cq-2 reuses it.  Reuse and repetition are
    # both legal, and the entry still carries the receipt's canonical values.
    reports = [
        _report("cq-1", [_ref(receipt), _ref(receipt)]),
        _report("cq-2", [_ref(receipt)]),
    ]
    responses, rejected = _cq_collect_platform_read_responses(
        reports, [receipt], artifact_root, _AUTHORIZED_TOOLS
    )
    assert rejected == []
    assert sorted(responses) == ["cq-1", "cq-2"]
    for entries in responses.values():
        assert len(entries) == 1
        entry = entries[0]
        assert set(entry) == {
            "tool",
            "request_digest",
            "response_digest",
            "artifact_path",
            "page",
            "result",
            "request",
        }
        assert entry["tool"] == receipt.tool
        assert entry["request_digest"] == receipt.request_digest
        assert entry["response_digest"] == receipt.response_digest
        assert entry["artifact_path"] == receipt.artifact_path
        # Pagination/truncation markers stay exactly as the proxy recorded them.
        assert entry["page"] == _TRUNCATED_PAGE
        assert entry["result"] == _QUERY_RESULT
        assert entry["request"] == _QUERY_REQUEST


def test_malformed_unknown_and_out_of_range_handles_are_rejected(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    receipt = _retained_receipt(artifact_root)
    cases = [
        # Shape drift: a non-string, a non-handle string, extra segments, or a
        # non-canonical ordinal spelling.
        (12345, "ref-shape"),
        ("query_semantic_context", "ref-shape"),
        ("", "ref-shape"),
        ("p", "ref-shape"),
        ("p-1", "ref-shape"),
        ("p0|x", "ref-shape"),
        ("p00", "ref-shape"),
        # The old long-string transcription is no longer a resolvable ref.
        (
            f"{receipt.tool}|{receipt.request_digest}|{receipt.response_digest}",
            "ref-shape",
        ),
        # No current-session receipt carries this ordinal: an out-of-range,
        # cross-session or invented handle.
        ("p1", "receipt-unmatched"),
        ("p9", "receipt-unmatched"),
    ]
    reports = [
        _report(f"cq-{index}", [ref]) for index, (ref, _reason) in enumerate(cases, start=1)
    ]
    responses, rejected = _cq_collect_platform_read_responses(
        reports, [receipt], artifact_root, _AUTHORIZED_TOOLS
    )
    assert responses == {}
    assert [item["reason"] for item in rejected] == [
        reason for _ref_value, reason in cases
    ]
    # The rejected refs carry no key, token or locator content beyond the ref.
    for item in rejected:
        assert set(item) == {"question_id", "ref", "reason"}


def test_a_receipt_outside_the_authorized_tools_provides_no_evidence(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    # The host-side tool authorization survives the handle switch: it reads the
    # receipt's own host-recorded tool, never a child-transcribed label.
    receipt = _retained_receipt(artifact_root, tool="semantic_sparql_query")
    responses, rejected = _cq_collect_platform_read_responses(
        [_report("cq-1", [_ref(receipt)])], [receipt], artifact_root, _AUTHORIZED_TOOLS
    )
    assert responses == {}
    assert [item["reason"] for item in rejected] == ["tool-unauthorized"]


def test_a_missing_or_tampered_artifact_provides_no_evidence(tmp_path):
    artifact_root = tmp_path / "run"
    artifact_root.mkdir()
    receipt = _retained_receipt(artifact_root, retain=False)

    # A receipt whose artifact was never retained (retention failed, or the
    # file was removed) cannot support any question.
    responses, rejected = _cq_collect_platform_read_responses(
        [_report("cq-1", [_ref(receipt)])], [receipt], artifact_root, _AUTHORIZED_TOOLS
    )
    assert responses == {}
    assert "not a retained file" in rejected[0]["reason"]

    # A tampered result breaks the canonical response digest, so the whole
    # artifact is rejected instead of re-digested into evidence.
    tampered = _retained_receipt(artifact_root)
    artifact = artifact_root.joinpath(*PurePosixPath(tampered.artifact_path).parts)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["result"]["matches"] = [{"forged": True}]
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    responses, rejected = _cq_collect_platform_read_responses(
        [_report("cq-1", [_ref(tampered)])], [tampered], artifact_root, _AUTHORIZED_TOOLS
    )
    assert responses == {}
    assert "response digest mismatch" in rejected[0]["reason"]


# --- §4.2 semantic projection and the post-exit recheck (T2-2/T2-3) ------------


def _recheck_entry(
    *, result: dict, tool: str = "query_semantic_context", request: dict | None = None
) -> dict:
    return {
        "tool": tool,
        "request_digest": "a" * 64,
        "response_digest": "b" * 64,
        "artifact_path": "acceptance/r3012-batch/platform-read/x/0.json",
        "page": {},
        "result": result,
        "request": dict(request or _QUERY_REQUEST),
    }


def test_noise_and_order_changes_are_not_semantic_drift():
    retained = {
        "request_id": "req-1",
        "duration_ms": 12,
        "matches": [{"id": "a", "iri": "iri:a"}, {"id": "b", "iri": "iri:b"}],
    }
    reread = {
        "request_id": "req-2",
        "duration_ms": 45,
        "matches": [{"id": "b", "iri": "iri:b"}, {"id": "a", "iri": "iri:a"}],
    }
    assert _cq_semantic_projection(retained) == _cq_semantic_projection(reread)
    recheck = _cq_recheck_evidence_responses(
        lambda tool, arguments, key: reread, "read-key", {"cq-1": [_recheck_entry(result=retained)]}
    )
    assert recheck["replayed_responses"] == 1
    assert recheck["question_status"] == {"cq-1": "stable"}
    assert recheck["drift"] == []
    assert recheck["unavailable"] == []


def test_an_equal_count_substitution_is_still_drift():
    retained = {"matches": [{"id": "a"}, {"id": "b"}]}
    reread = {"matches": [{"id": "a"}, {"id": "c"}]}
    recheck = _cq_recheck_evidence_responses(
        lambda tool, arguments, key: reread, "read-key", {"cq-1": [_recheck_entry(result=retained)]}
    )
    assert recheck["question_status"] == {"cq-1": "drift"}
    assert recheck["drift"][0]["question_id"] == "cq-1"
    assert recheck["drift"][0]["tool"] == "query_semantic_context"


def test_an_unavailable_reread_is_platform_runtime_incomplete_and_wins():
    def failing_forward(tool: str, arguments: dict, key: str) -> dict:
        raise RuntimeError("mcp connection refused")

    responses = {
        # One drifting entry and one unavailable entry under the same question:
        # the unavailable re-read dominates, and nothing claims stability.
        "cq-1": [
            _recheck_entry(result={"matches": [{"id": "a"}]}),
            _recheck_entry(result={"matches": [{"id": "b"}]}),
        ]
    }
    recheck = _cq_recheck_evidence_responses(
        failing_forward, "read-key", responses
    )
    assert recheck["question_status"] == {"cq-1": "platform-runtime-incomplete"}
    assert recheck["replayed_responses"] == 2
    assert len(recheck["unavailable"]) == 2
    assert recheck["unavailable"][0]["error"].startswith("RuntimeError")


# The platform signs each continuation token per issuance (the cursor codec
# stamps every encoded payload), so two reads of one unchanged page
# legitimately carry different token bytes.  Only the two documented
# ``query_semantic_context`` pagination slots are transport state; the
# surrounding returned/truncated/expansion/scope markers stay semantic.
_CURSOR_PAGE_RESULT = {
    "result_status": "matched",
    "primary_matches": [{"id": "resource-1", "iri": "iri:1"}],
    "matches_page": {"returned": 1, "truncated": True, "next_match_cursor": "tok-a"},
    "context_page": {
        "returned": 0,
        "truncated": True,
        "next_context_cursor": "tok-x",
        "expansion": {"status": "complete"},
    },
}


def _recheck_status(retained: dict, reread: dict, *, tool: str = "query_semantic_context") -> str:
    recheck = _cq_recheck_evidence_responses(
        lambda forward_tool, arguments, key: reread,
        "read-key",
        {"cq-1": [_recheck_entry(result=retained, tool=tool)]},
    )
    assert recheck["replayed_responses"] == 1
    assert recheck["unavailable"] == []
    return recheck["question_status"]["cq-1"]


def _ranking_response(*, cache_hit: bool) -> dict:
    """Generalized context response with binding, facts, pages, and ranking."""

    return {
        "query": {
            "queries": ["reserve binding"],
            "normalized_queries": ["reserve binding"],
            "depth": 2,
            "result_scope": "authorized_query_scope",
            "ranking_version": "jev-v1",
        },
        "result_status": "matched",
        "scope": {
            "project_id": "project-1",
            "mode": "ontologies",
            "status": "complete",
            "ontologies": [{"ontology_id": "ontology-1", "model_revision": 1}],
        },
        "primary_matches": [
            {
                "id": "resource-1",
                "iri": "iri:1",
                "label": "Reserve binding",
                "match": {"relevance_score": 2.0, "relevance_status": "scored"},
            }
        ],
        "related_context": [],
        "matches_page": {
            "returned": 1,
            "truncated": False,
            "next_match_cursor": None,
        },
        "context_page": {
            "returned": 0,
            "truncated": False,
            "next_context_cursor": None,
            "expansion": {"status": "complete"},
        },
        "truncated": False,
        "recall": {
            "mode": "hybrid",
            "match_status": "candidate",
            "completeness": "complete",
            "ranking": {
                "status": "scored",
                "version": "jev-v1",
                "score_scale": [0, 3],
                "min_score": 1.0,
                "filtered_count": 0,
                "candidate_count": 1,
                "cache_hit": cache_hit,
            },
        },
        "warnings": [],
    }


@pytest.mark.parametrize("envelope", [False, True])
def test_reissued_query_ranking_cache_flag_is_stable_in_bare_and_api_envelopes(envelope):
    retained = _ranking_response(cache_hit=False)
    reread = _ranking_response(cache_hit=True)
    if envelope:
        retained = {"ok": True, "data": retained}
        reread = {"ok": True, "data": reread}

    assert _recheck_status(retained, reread) == "stable"


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("scope", "ontologies", 0, "model_revision"), 2),
        (("primary_matches", 0, "id"), "resource-9"),
        (("primary_matches", 0, "match", "relevance_score"), 1.0),
        (("matches_page", "returned"), 2),
        (("matches_page", "truncated"), True),
        (("recall", "ranking", "candidate_count"), 2),
    ],
)
def test_ranking_cache_flag_mask_does_not_hide_semantic_drift(path, replacement):
    retained = _ranking_response(cache_hit=False)
    reread = _ranking_response(cache_hit=True)
    parent = reread
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = replacement

    assert _recheck_status(retained, reread) == "drift"


def test_ranking_cache_flag_mask_is_limited_to_the_exact_recall_slot_and_tool():
    retained = _ranking_response(cache_hit=False)
    retained["primary_matches"][0]["data"] = {
        "cache_hit": False,
        "recall": {"ranking": {"cache_hit": False}},
    }
    retained["other"] = {"recall": {"ranking": {"cache_hit": False}}}
    reread = json.loads(json.dumps(retained))
    reread["recall"]["ranking"]["cache_hit"] = True
    reread["primary_matches"][0]["data"]["cache_hit"] = True
    reread["primary_matches"][0]["data"]["recall"]["ranking"]["cache_hit"] = True
    reread["other"]["recall"]["ranking"]["cache_hit"] = True

    assert _recheck_status(retained, reread) == "drift"
    assert _recheck_status(retained, reread, tool="get_ontology_workspace_context") == "drift"


def test_a_reissued_opaque_pagination_cursor_is_not_semantic_drift():
    retained = json.loads(json.dumps(_CURSOR_PAGE_RESULT))
    reread = json.loads(json.dumps(_CURSOR_PAGE_RESULT))
    reread["matches_page"]["next_match_cursor"] = "tok-b"
    reread["context_page"]["next_context_cursor"] = "tok-y"

    recheck = _cq_recheck_evidence_responses(
        lambda tool, arguments, key: reread,
        "read-key",
        {"cq-1": [_recheck_entry(result=retained)]},
    )
    assert recheck["question_status"] == {"cq-1": "stable"}
    assert recheck["drift"] == []
    assert recheck["unavailable"] == []
    # The comparison never rewrites the retained response, the re-read
    # response, or the retained entry's identity/digest fields.
    assert retained == _CURSOR_PAGE_RESULT
    assert retained["matches_page"]["next_match_cursor"] == "tok-a"
    assert reread["matches_page"]["next_match_cursor"] == "tok-b"
    assert reread["context_page"]["next_context_cursor"] == "tok-y"
    entry = _recheck_entry(result=retained)
    _cq_recheck_evidence_responses(
        lambda tool, arguments, key: reread, "read-key", {"cq-1": [entry]}
    )
    assert entry["result"] == _CURSOR_PAGE_RESULT
    assert entry["request_digest"] == "a" * 64
    assert entry["response_digest"] == "b" * 64


def test_api_envelope_reissued_pagination_cursors_are_not_semantic_drift():
    retained = {"status": "matched", "data": json.loads(json.dumps(_CURSOR_PAGE_RESULT))}
    reread = json.loads(json.dumps(retained))
    reread["data"]["matches_page"]["next_match_cursor"] = "issued-2"
    reread["data"]["context_page"]["next_context_cursor"] = "issued-context-2"
    before_retained = json.loads(json.dumps(retained))
    before_reread = json.loads(json.dumps(reread))
    entry = _recheck_entry(result=retained)
    before_entry = json.loads(json.dumps(entry))

    recheck = _cq_recheck_evidence_responses(
        lambda tool, arguments, key: reread, "read-key", {"cq-1": [entry]}
    )

    assert recheck["question_status"] == {"cq-1": "stable"}
    assert recheck["drift"] == []
    assert retained == before_retained
    assert reread == before_reread
    assert entry == before_entry


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("status",), "forbidden"),
        (("data", "result_status"), "no_match"),
        (("data", "scope", "ontology_ids"), ["ontology-2"]),
        (("data", "source"), {"id": "source-2"}),
        (("data", "model_revision"), 2),
        (("data", "primary_matches"), [{"id": "resource-9", "iri": "iri:9"}]),
        (("data", "primary_matches", 0, "iri"), "iri:changed"),
        (("data", "matches_page", "returned"), 2),
        (("data", "matches_page", "truncated"), False),
        (("data", "context_page", "expansion", "status"), "partial"),
        (("data", "matches_page", "next_match_cursor"), None),
        (("data", "matches_page", "next_match_cursor"), ""),
        (("data", "matches_page", "next_match_cursor"), 7),
        (("data", "matches_page", "next_match_cursor"), ["token"]),
        (("data", "context_page", "next_context_cursor"), None),
        (("data", "context_page", "next_context_cursor"), {"token": "x"}),
    ],
)
def test_api_envelope_semantic_and_pagination_state_drift_is_preserved(path, replacement):
    payload = json.loads(json.dumps(_CURSOR_PAGE_RESULT))
    payload.update(
        scope={"ontology_ids": ["ontology-1"]}, source={"id": "source-1"}, model_revision=1
    )
    retained = {"status": "matched", "data": payload}
    reread = json.loads(json.dumps(retained))
    reread["data"]["matches_page"]["next_match_cursor"] = "issued-2"
    reread["data"]["context_page"]["next_context_cursor"] = "issued-context-2"
    parent = reread
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = replacement
    assert _recheck_status(retained, reread) == "drift"


@pytest.mark.parametrize("page_key,cursor_key", [
    ("matches_page", "next_match_cursor"), ("context_page", "next_context_cursor")
])
def test_api_envelope_pagination_state_and_malformed_values_stay_observable(page_key, cursor_key):
    def envelope(cursor):
        return {"status": "matched", "data": {page_key: {cursor_key: cursor}}}

    assert _recheck_status(envelope(None), envelope(None)) == "stable"
    assert _recheck_status(envelope(None), envelope("issued")) == "drift"
    assert _recheck_status(envelope(7), envelope(["issued"])) == "drift"
    assert _recheck_status(envelope({"token": "x"}), envelope({"token": "y"})) == "drift"


def test_api_envelope_business_data_and_other_tools_are_not_masked():
    retained = {"status": "matched", "data": json.loads(json.dumps(_CURSOR_PAGE_RESULT))}
    retained["data"]["primary_matches"][0]["data"] = {
        "matches_page": {"next_match_cursor": "business-1"}
    }
    retained["data"]["other"] = {"data": {"context_page": {"next_context_cursor": "business-1"}}}
    # Top-level envelope fields are not pagination metadata either.
    retained["matches_page"] = {"next_match_cursor": "business-1"}
    reread = json.loads(json.dumps(retained))
    reread["data"]["matches_page"]["next_match_cursor"] = "issued-2"
    assert _recheck_status(retained, reread) == "stable"
    assert _recheck_status(retained, reread, tool="get_ontology_workspace_context") == "drift"
    for target in (
        reread["data"]["primary_matches"][0]["data"]["matches_page"],
        reread["data"]["other"]["data"]["context_page"],
        reread["matches_page"],
    ):
        cursor_key = next(iter(target))
        target[cursor_key] = "business-2"
        assert _recheck_status(retained, reread) == "drift"
        target[cursor_key] = "business-1"


def test_a_pagination_cursor_appearing_or_disappearing_is_still_drift():
    absent_match = {"truncated": False, "next_match_cursor": None}
    absent_context = {"truncated": False, "next_context_cursor": None}
    # An unchanged terminal page (no continuation on either side) stays stable.
    assert (
        _recheck_status({"matches_page": dict(absent_match)}, {"matches_page": dict(absent_match)})
        == "stable"
    )
    assert (
        _recheck_status(
            {"context_page": dict(absent_context)}, {"context_page": dict(absent_context)}
        )
        == "stable"
    )
    # A token on one side only -- in either direction and either slot -- is a
    # pagination-state change, never an interchangeable token spelling.
    assert (
        _recheck_status(
            {"matches_page": {"truncated": True, "next_match_cursor": "tok-a"}},
            {"matches_page": {"truncated": True, "next_match_cursor": None}},
        )
        == "drift"
    )
    assert (
        _recheck_status(
            {"matches_page": {"truncated": True, "next_match_cursor": None}},
            {"matches_page": {"truncated": True, "next_match_cursor": "tok-b"}},
        )
        == "drift"
    )
    assert (
        _recheck_status(
            {"context_page": {"truncated": True, "next_context_cursor": "tok-x"}},
            {"context_page": {"truncated": True, "next_context_cursor": None}},
        )
        == "drift"
    )
    assert (
        _recheck_status(
            {"context_page": {"truncated": True, "next_context_cursor": None}},
            {"context_page": {"truncated": True, "next_context_cursor": "tok-y"}},
        )
        == "drift"
    )
    # An empty string is not a valid continuation token either.
    assert (
        _recheck_status(
            {"matches_page": {"truncated": True, "next_match_cursor": "tok-a"}},
            {"matches_page": {"truncated": True, "next_match_cursor": ""}},
        )
        == "drift"
    )
    # An omitted slot is no continuation, exactly like an explicit None.
    assert (
        _recheck_status(
            {"matches_page": {"truncated": True, "next_match_cursor": "tok-a"}},
            {"matches_page": {"truncated": True}},
        )
        == "drift"
    )


def test_a_malformed_pagination_cursor_stays_observable():
    # A wrong type is never laundered into "present": a valid token against a
    # malformed value, and two different malformed values, both stay drift.
    assert (
        _recheck_status(
            {"matches_page": {"truncated": True, "next_match_cursor": "tok-a"}},
            {"matches_page": {"truncated": True, "next_match_cursor": 7}},
        )
        == "drift"
    )
    assert (
        _recheck_status(
            {"matches_page": {"truncated": True, "next_match_cursor": 7}},
            {"matches_page": {"truncated": True, "next_match_cursor": ["tok"]}},
        )
        == "drift"
    )
    assert (
        _recheck_status(
            {"context_page": {"truncated": True, "next_context_cursor": {"token": "x"}}},
            {"context_page": {"truncated": True, "next_context_cursor": {"token": "y"}}},
        )
        == "drift"
    )


def test_cursor_named_business_fields_and_other_tools_are_not_masked():
    # A resource property that happens to share the cursor name is business
    # content; only the two documented page slots are transport state.
    assert (
        _recheck_status(
            {
                "primary_matches": [{"id": "r1", "next_match_cursor": "biz-a"}],
                "matches_page": {"truncated": True, "next_match_cursor": "tok-a"},
            },
            {
                "primary_matches": [{"id": "r1", "next_match_cursor": "biz-b"}],
                "matches_page": {"truncated": True, "next_match_cursor": "tok-b"},
            },
        )
        == "drift"
    )
    # Another tool's response is never cursor-masked, even with the same shape.
    assert (
        _recheck_status(
            {"matches_page": {"truncated": True, "next_match_cursor": "tok-a"}},
            {"matches_page": {"truncated": True, "next_match_cursor": "tok-b"}},
            tool="get_ontology_workspace_context",
        )
        == "drift"
    )


def test_pagination_flags_scope_and_expansion_drift_still_block():
    base = json.loads(json.dumps(_CURSOR_PAGE_RESULT))
    base["scope"] = {"result_scope": "authorized_query_scope", "ontology_ids": ["ontology-1"]}
    reread = json.loads(json.dumps(base))
    # The tokens are reissued on every read, so a hidden drift must never rely
    # on their bytes: each mutation below also changes the token spelling.
    reread["matches_page"]["next_match_cursor"] = "tok-b"
    reread["context_page"]["next_context_cursor"] = "tok-y"
    assert _recheck_status(base, reread) == "stable"

    truncated = json.loads(json.dumps(reread))
    truncated["matches_page"]["truncated"] = False
    assert _recheck_status(base, truncated) == "drift"

    returned = json.loads(json.dumps(reread))
    returned["matches_page"]["returned"] = 2
    assert _recheck_status(base, returned) == "drift"

    scope = json.loads(json.dumps(reread))
    scope["scope"]["ontology_ids"] = ["ontology-2"]
    assert _recheck_status(base, scope) == "drift"

    expansion = json.loads(json.dumps(reread))
    expansion["context_page"]["expansion"]["status"] = "partial"
    assert _recheck_status(base, expansion) == "drift"

    substituted = json.loads(json.dumps(reread))
    substituted["primary_matches"] = [{"id": "resource-9", "iri": "iri:9"}]
    assert _recheck_status(base, substituted) == "drift"


# --- §4.1/§4.2 report and packet boundaries -----------------------------------


def _passing_verdict(question_id: str) -> dict:
    return {
        "schema_version": CQ_BATCH_REPORT_SCHEMA,
        "batch_id": "batch-r3011",
        "question_id": question_id,
        "verdict": "pass",
        "failure_layer": None,
        "conflicting_evidence": [],
        "note": "",
    }


def _full_pass_report(**extra) -> dict:
    return build_batch_report(
        run_id="r3012-run",
        batch_id="batch-r3011",
        freeze_digest="sha256:" + "0" * 64,
        model_binding_digest="sha256:" + "1" * 64,
        hidden_questions=[_question("cq-1")],
        examiner_reports=[_report("cq-1", ["p0"])],
        verdicts=[_passing_verdict("cq-1")],
        executed_question_ids=["cq-1"],
        unexecuted_question_ids=[],
        **extra,
    )


_PROJECTION_ENTRY = {
    "tool": "query_semantic_context",
    "request_digest": "a" * 64,
    "response_digest": "b" * 64,
    "artifact_path": "acceptance/r3012-batch/platform-read/x/0.json",
    "page": {},
    "result": {"ok": True},
}


def test_a_report_without_the_new_fields_keeps_the_011_full_pass_boundary():
    report = _full_pass_report()
    assert "platform_read_responses" not in report
    assert "evidence_recheck" not in report
    assert batch_report_is_full_pass(report) is True


def test_a_pass_verdict_requires_a_validated_response_and_a_stable_recheck():
    # A pass verdict on a question with no host-validated response can never
    # stand once the projection field is present (fail-closed on empty).
    report = _full_pass_report(platform_read_responses={})
    assert batch_report_is_full_pass(report) is False
    report = _full_pass_report(
        platform_read_responses={"cq-1": [dict(_PROJECTION_ENTRY)]}
    )
    assert batch_report_is_full_pass(report) is True
    # Drift and an unavailable re-read both block the valid PASS.
    for status in ("drift", "platform-runtime-incomplete"):
        report = _full_pass_report(
            platform_read_responses={"cq-1": [dict(_PROJECTION_ENTRY)]},
            evidence_recheck={"replayed_responses": 1, "question_status": {"cq-1": status}},
        )
        assert batch_report_is_full_pass(report) is False
    report = _full_pass_report(
        platform_read_responses={"cq-1": [dict(_PROJECTION_ENTRY)]},
        evidence_recheck={"replayed_responses": 1, "question_status": {"cq-1": "stable"}},
    )
    assert batch_report_is_full_pass(report) is True


def _judge_packet_payload(platform_read_responses) -> dict:
    bundle = {
        "schema_version": CQ_EVIDENCE_BUNDLE_SCHEMA,
        "batch_id": "batch-r3011",
        "freeze_digest": "sha256:" + "0" * 64,
        "entries": [
            {
                "question_id": "cq-1",
                "source": "scenario-brief",
                "locator": "section 1",
                "content": "approved bytes",
                "content_digest": content_digest("approved bytes"),
                "review_content_version": 1,
            }
        ],
    }
    packet = build_acceptance_judge_packet(
        run_id="r3012-run",
        batch_id="batch-r3011",
        freeze_digest="sha256:" + "0" * 64,
        questions=[
            {
                "question_id": "cq-1",
                "content_version": 1,
                "question": "placeholder cq-1?",
                "answer_points": ["point"],
                "evidence_refs": [{"source": "scenario-brief", "locator": "section 1"}],
                "unknown": [],
                "scope": {"kind": "panorama", "slice_ids": []},
            }
        ],
        model_binding_digest="sha256:" + "1" * 64,
        evidence_bundle=bundle,
        examiner_reports=[_report("cq-1", ["p0"])],
        platform_read_responses=platform_read_responses,
        verdict_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
    )
    return packet.to_dict()["payload"]


def test_the_judge_packet_accepts_only_host_validated_projections():
    payload = _judge_packet_payload({"cq-1": [dict(_PROJECTION_ENTRY)]})
    assert payload["platform_read_responses"] == {"cq-1": [_PROJECTION_ENTRY]}
    # The projection carries no request bytes, key, token or absolute path.
    entry = payload["platform_read_responses"]["cq-1"][0]
    assert "request" not in entry
    assert json.dumps(entry).count("/") == entry["artifact_path"].count("/")

    bad_projections = [
        # Bound to a question outside this batch.
        {"cq-9": [dict(_PROJECTION_ENTRY)]},
        # An empty entry list is not a validated response.
        {"cq-1": []},
        # Extra fields (the internal request must be stripped first).
        {"cq-1": [{**_PROJECTION_ENTRY, "request": dict(_QUERY_REQUEST)}]},
        # A write tool outside the proxy's read-only allowlist.
        {"cq-1": [{**_PROJECTION_ENTRY, "tool": "create_ontology"}]},
        # Malformed digests and locators.
        {"cq-1": [{**_PROJECTION_ENTRY, "request_digest": "not-a-digest"}]},
        {"cq-1": [{**_PROJECTION_ENTRY, "artifact_path": "/etc/passwd"}]},
        # page/result must stay objects.
        {"cq-1": [{**_PROJECTION_ENTRY, "page": []}]},
    ]
    for projection in bad_projections:
        with pytest.raises(ChildRuntimeError):
            _judge_packet_payload(projection)


# --- the executed CLI path: collect, recheck, project (end to end) -------------


class _DualForwarder:
    """Serves the state read and scripted query replays through one seam."""

    def __init__(self, context: dict, replay_results: list[dict]) -> None:
        self._context = context
        self._replay_results = list(replay_results)
        self._last_query_result: dict | None = None
        self.calls: list[tuple[str, dict]] = []
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def forward(self, tool: str, arguments: dict, read_key: str) -> dict:
        self.calls.append((tool, dict(arguments)))
        if tool == "query_semantic_context":
            # Later replays repeat the last scripted result, so a drifted
            # platform stays drifted for every question that referenced it.
            if self._replay_results:
                self._last_query_result = self._replay_results.pop(0)
            return self._last_query_result or {"ok": True, "matches": []}
        # The workspace read stands in for ``McpReadForwarder.forward``, which
        # returns the canonical structured content verbatim: the live state is
        # the payload inside the runtime wrapper's success envelope.
        return {"ok": True, "data": self._context}


class _Factory:
    def __init__(self, forwarder: _DualForwarder) -> None:
        self.forwarder = forwarder

    def __call__(self, **kwargs):
        return self.forwarder


_RETAINED_QUERY_RESULT = {"ok": True, "matches": [{"id": "resource-1", "iri": "iri:1"}]}


def _write_run_root(tmp_path: Path, questions: list[dict]) -> tuple[Path, dict]:
    run_root = tmp_path / "run"
    frozen = _freeze(questions)
    (run_root / "competency-questions" / "frozen").mkdir(parents=True)
    (run_root / "acceptance-v3").mkdir(parents=True)
    (run_root / "competency-questions" / "frozen" / "freeze-0001.json").write_text(
        json.dumps(frozen), encoding="utf-8"
    )
    (run_root / "acceptance-v3" / "run-contract.json").write_text(
        json.dumps(_RUN_CONTRACT), encoding="utf-8"
    )
    # The judge bundle resolves staged approved sources for every question.
    content = "approved scenario bytes\n"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    manifest = [{"path": "scenario-brief", "sha256": digest, "review_content_version": 1}]
    for role in ("coordinator", "modeling", "competency-question"):
        copy = run_root / "sources" / role / "scenario-brief"
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(content, encoding="utf-8")
    (run_root / "source-manifest.json").write_text(
        json.dumps({"schema_version": "r3-0-009-source-manifest/v1", "sources": manifest}),
        encoding="utf-8",
    )
    return run_root, frozen


def _write_handoff(tmp_path: Path, frozen: dict) -> Path:
    binding = _handoff_binding(
        batch_id=frozen["batch_id"], freeze_digest=frozen["snapshot_digest"]
    )
    handoff = {
        "authorized_ontology_ids": ["ontology-1"],
        "production_delivery": {"ready": True, "pending_writes": False},
        "model_binding": binding,
        "post_batch_model_binding": json.loads(json.dumps(binding)),
    }
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(handoff), encoding="utf-8")
    return path


def _retaining_adapter(
    *,
    result: dict,
    examiner_run=None,
):
    """Build a ``CodexRuntimeAdapter`` developer double CLASS plus shared state.

    The class is what the host constructs twice (examiner, then judge); the
    returned ``state`` dict carries the judge payload across both instances.
    The examiner half uses the real host seams exactly as the runtime would --
    the persistence callback writes the retained artifact and the observables
    out-param receives the sanitized receipt -- without starting a child.  An
    ``examiner_run`` hook replaces the retaining behavior for failure tests.
    """

    state: dict = {"judge_payload": None}

    class _RetainingStubAdapter:
        def __init__(self, repository_root=None) -> None:
            self.repository_root = repository_root

        def bind_acceptance_model_profile(self, profile) -> None:
            return None

        def run_v3_acceptance_child(self, packet, *, role_instructions, reports, **kwargs):
            teardown = kwargs.get("teardown")
            if isinstance(teardown, dict):
                teardown.update(
                    {
                        "child_stopped": True,
                        "child_destroyed": True,
                        "report_sink_stopped": True,
                        "proxy_stopped": True,
                        "private_root_removed": True,
                        "socket_root_removed": True,
                    }
                )
            if kwargs.get("platform_forwarder") is None:
                state["judge_payload"] = packet.to_dict()["payload"]
                return [
                    _passing_verdict(str(question["question_id"]))
                    for question in state["judge_payload"]["questions"]
                ]
            if examiner_run is not None:
                examiner_run(packet, reports, kwargs)
                return [dict(report) for report in reports]
            persistence = kwargs["response_persistence"]
            observables = kwargs["examiner_observables"]
            tool = "query_semantic_context"
            request = dict(_QUERY_REQUEST)
            request_digest = canonical_read_digest({"tool": tool, "arguments": request})
            response_digest = canonical_read_digest(result)
            artifact_path = f"acceptance/r3011-{packet.batch_id}/platform-read/{packet.canonical_digest.removeprefix('sha256:')}/0.json"
            persistence(
                artifact_path,
                {
                    "schema_version": PLATFORM_READ_ARTIFACT_SCHEMA,
                    "tool": tool,
                    "request": request,
                    "result": result,
                },
            )
            receipt = V3ProxyCallReceipt(
                ordinal=0,
                project_id="project-1",
                ontology_id="ontology-1",

                ticket_digest="b" * 64,
                model_state_digest="c" * 64,
                tool=tool,
                request_digest=request_digest,
                response_digest=response_digest,
                artifact_path=artifact_path,
                page={
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            )
            observables["receipts"] = [receipt]
            observables["persistence_failures"] = 0
            hidden_ids = [
                str(question["question_id"])
                for question in packet.to_dict()["payload"]["questions"]
            ]
            for question_id in hidden_ids:
                # The same receipt (one handle) supports both questions.
                reports.append(_report(question_id, [_ref(receipt)]))
            return [dict(report) for report in reports]

    return _RetainingStubAdapter, state


def _run_cli(
    tmp_path: Path,
    run_root: Path,
    handoff: Path,
    forwarder: _DualForwarder,
    adapter_class,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("modeling_team.__main__.CodexRuntimeAdapter", adapter_class)
    monkeypatch.setenv(_CQ_PLATFORM_READ_KEY_ENV, "read-key")
    return _run_cq_acceptance(
        Namespace(
            run_root=run_root,
            freeze_id="freeze-0001",
            model_handoff=handoff,
            model_profile=None,
            session_timeout=2.0,
            unexecuted_report=False,
        ),
        REPO_ROOT,
        forwarder_factory=_Factory(forwarder),
    )


def _read_report(run_root: Path, batch_id: str) -> dict:
    return json.loads(
        (
            run_root / "acceptance-v3" / "reports" / batch_id / "batch-report.json"
        ).read_text(encoding="utf-8")
    )


def test_the_executed_batch_collects_rechecks_and_projects_responses(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1"), _question("cq-2")])
    handoff = _write_handoff(tmp_path, frozen)
    # Every replay returns exactly the retained result: the batch is stable.
    forwarder = _DualForwarder(
        _platform_context(), [_RETAINED_QUERY_RESULT, _RETAINED_QUERY_RESULT]
    )
    adapter_class, state = _retaining_adapter(result=_RETAINED_QUERY_RESULT)
    code = _run_cli(tmp_path, run_root, handoff, forwarder, adapter_class, monkeypatch)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["full_pass"] is True
    report = _read_report(run_root, frozen["batch_id"])

    # The retained artifact is on disk under the Runner-relative locator.
    artifact = run_root / report["platform_read_responses"]["cq-1"][0]["artifact_path"]
    document = json.loads(artifact.read_text(encoding="utf-8"))
    assert document["result"] == _RETAINED_QUERY_RESULT

    # The report projection carries both questions with the exact six fields.
    responses = report["platform_read_responses"]
    assert sorted(responses) == ["cq-1", "cq-2"]
    for entries in responses.values():
        assert len(entries) == 1
        assert set(entries[0]) == {
            "tool", "request_digest", "response_digest", "artifact_path", "page", "result",
        }
        assert entries[0]["result"] == _RETAINED_QUERY_RESULT
    assert report["evidence_recheck"]["question_status"] == {
        "cq-1": "stable",
        "cq-2": "stable",
    }
    assert report["evidence_recheck"]["replayed_responses"] == 2
    assert report["sessions"]["platform_read_responses"] == {
        "questions_with_responses": 2,
        "retained_receipts": 2,
        "persistence_failures": 0,
        "rejected_refs": [],
    }
    # The recheck replayed the exact authorized request through the forwarder.
    replayed = [call for call in forwarder.calls if call[0] == "query_semantic_context"]
    assert len(replayed) == 2
    assert all(call[1] == _QUERY_REQUEST for call in replayed)
    # The judge saw the same validated projection, never the request bytes.
    judged = state["judge_payload"]["platform_read_responses"]
    assert judged == responses


def test_an_equal_count_replay_drift_blocks_the_whole_batch_pass(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1"), _question("cq-2")])
    handoff = _write_handoff(tmp_path, frozen)
    # An equal-count substitution on replay: one resource id changed.
    substituted = {"ok": True, "matches": [{"id": "resource-1", "iri": "iri:1"},
                                           {"id": "resource-9", "iri": "iri:9"}]}
    retained = {"ok": True, "matches": [{"id": "resource-1", "iri": "iri:1"},
                                        {"id": "resource-2", "iri": "iri:2"}]}
    forwarder = _DualForwarder(_platform_context(), [substituted])
    adapter_class, _state = _retaining_adapter(result=retained)
    code = _run_cli(tmp_path, run_root, handoff, forwarder, adapter_class, monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    report = _read_report(run_root, payload["batch_id"])
    # The Examiner answers are retained untouched, drift is recorded per
    # question, and no valid per-question or whole-batch PASS is published even
    # though every verdict claims pass.
    assert [item["question_id"] for item in report["examiner_reports"]] == ["cq-1", "cq-2"]
    assert report["verdicts"] and all(
        item["verdict"] == "pass" for item in report["verdicts"]
    )
    assert report["evidence_recheck"]["question_status"] == {
        "cq-1": "drift",
        "cq-2": "drift",
    }
    assert report["full_pass"] is False


def test_unmatched_refs_and_persistence_failures_surface_and_fail_closed(
    tmp_path, capsys, monkeypatch
):
    run_root, frozen = _write_run_root(tmp_path, [_question("cq-1"), _question("cq-2")])
    handoff = _write_handoff(tmp_path, frozen)
    forwarder = _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT])

    def unretained_examiner(packet, reports, kwargs) -> None:
        """A retention failure plus an invented reference: no valid evidence."""

        observables = kwargs["examiner_observables"]
        observables["receipts"] = []
        observables["persistence_failures"] = 1
        for index, question in enumerate(packet.to_dict()["payload"]["questions"]):
            # The handle names an ordinal nothing the host retained this
            # session ever carried.
            reports.append(_report(str(question["question_id"]), [f"p{index}"]))

    adapter_class, _state = _retaining_adapter(
        result=_RETAINED_QUERY_RESULT, examiner_run=unretained_examiner
    )
    code = _run_cli(tmp_path, run_root, handoff, forwarder, adapter_class, monkeypatch)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    report = _read_report(run_root, payload["batch_id"])
    # Fail-closed: no question carries a validated response, so no pass
    # verdict can stand, and the retention failure plus rejected refs are
    # both observable in the host-only report.
    assert report["platform_read_responses"] == {}
    assert report["evidence_recheck"]["question_status"] == {}
    session = report["sessions"]["platform_read_responses"]
    assert session["questions_with_responses"] == 0
    assert session["retained_receipts"] == 0
    assert session["persistence_failures"] == 2
    assert [item["reason"] for item in session["rejected_refs"]] == [
        "receipt-unmatched",
        "receipt-unmatched",
    ]
    assert report["full_pass"] is False


@pytest.mark.parametrize("envelope", [False, True])
def test_r4318_only_exact_context_snapshot_flag_is_normalized(envelope):
    retained = _ranking_response(cache_hit=False)
    retained["context_page"]["ranking"] = {"snapshot_reused": False, "status": "applied"}
    retained["related_context"] = [{"data": {"snapshot_reused": False},
                                     "relevance": {"relevance_score": 2}}]
    reread = json.loads(json.dumps(retained))
    reread["context_page"]["ranking"]["snapshot_reused"] = True
    first, second = (({"ok": True, "data": retained}, {"ok": True, "data": reread})
                     if envelope else (retained, reread))
    assert _recheck_status(first, second) == "stable"
    reread["related_context"][0]["data"]["snapshot_reused"] = True
    assert _recheck_status(first, second) == "drift"
    reread["related_context"][0]["data"]["snapshot_reused"] = False
    reread["related_context"][0]["relevance"]["relevance_score"] = 1
    assert _recheck_status(first, second) == "drift"
    reread["related_context"][0]["relevance"]["relevance_score"] = 2
    reread["context_page"]["ranking"]["status"] = "degraded"
    assert _recheck_status(first, second) == "drift"
