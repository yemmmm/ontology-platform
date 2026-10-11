from __future__ import annotations

from modeling_team.handoff_materials import HANDOFF_TOOL_NAMES

import hashlib
import json
import socket
from pathlib import Path

import pytest

from modeling_team.acceptance import (
    AcceptanceContractError,
    RunnerAcceptanceCarrier,
    ticket_digest,
    validate_examiner_payload,
    validate_typed_evidence_ref,
)
from modeling_team.acceptance_runtime import ReportSinkServer
from modeling_team.report_sink_mcp import report_schema
from modeling_team.acceptance_runtime import PLATFORM_PROXY_READ_TOOLS
from modeling_team.model_routing import (
    DEFAULT_MODEL_PROFILE_ID,
    load_team_model_profile,
)
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.contracts import repository_root
from modeling_team.tests.test_r23005_contracts import _ticket


class _SessionsDouble:
    """Minimal ProviderSessionManager double for config/child-factory tests."""

    def base_url_for(self, provider_id: str) -> str:
        return "http://127.0.0.1:49152"

    def listening(self) -> bool:
        return True

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {"deepseek-direct": {"listening": True}}

    def secret_values(self) -> tuple[bytes, ...]:
        return ()

    def stop(self) -> dict[str, dict[str, bool | int]]:
        return {}


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_ticket(suffix: str, source_digest: str) -> dict:
    ticket = _ticket(suffix)
    ticket["approved_sources"] = [{"path": "source.md", "sha256": source_digest}]
    ticket["source_bundle_digest"] = _sha(ticket["approved_sources"])
    ticket["ticket_digest"] = ticket_digest(ticket)
    for receipt in ticket["modeling_receipts"]:
        receipt["evidence_ref"]["ticket_digest"] = ticket["ticket_digest"]
    ticket["ticket_digest"] = ticket_digest(ticket)
    return ticket


def _semantic_payload(ref: dict | list) -> dict:
    refs = ref if isinstance(ref, list) else [ref]
    return {
        "answerability": "answerable",
        "conclusion": "confirmed",
        "evidence": [{"summary": "bound evidence"}],
        "coverage": {"queries_or_sections": ["cq1"], "complete": True},
        "gaps": [],
        "evidence_refs": refs,
    }


def _socket_request(path: Path, payload: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(path))
        client.sendall(json.dumps(payload, separators=(",", ":")).encode())
        return json.loads(client.recv(65536).decode())


def test_report_schema_is_strict_and_kind_specific() -> None:
    source = report_schema("source")
    platform = report_schema("platform")
    assert source["additionalProperties"] is False
    assert platform["additionalProperties"] is False
    assert source["required"] == platform["required"] == [
        "answerability",
        "conclusion",
        "evidence",
        "coverage",
        "gaps",
        "evidence_refs",
    ]
    assert source["properties"]["evidence_refs"]["items"]["required"] == ["location"]
    assert platform["properties"]["evidence_refs"]["items"]["required"] == [
        "ref_id",
        "tool",
        "request_digest",
        "response_digest",
        "artifact_path",
        "page",
    ]


@pytest.mark.parametrize("kind", ["source", "platform"])
def test_report_sink_rejects_missing_and_extra_fields_even_on_raw_socket(
    tmp_path: Path, kind: str
) -> None:
    socket_path = tmp_path / "report.sock"
    accepted: list[dict] = []
    sink = ReportSinkServer(socket_path, "token", accepted.append, kind=kind)
    sink.start()
    try:
        ref = {"location": "source.md#answer"} if kind == "source" else {
            "ref_id": "proxy-ref",
            "tool": "get_modeling_context",
            "request_digest": "a" * 64,
            "response_digest": "b" * 64,
            "artifact_path": "acceptance/round/platform-read/handle/0.json",
            "page": {
                "ordinal": 0,
                "input_cursor": "cursor-in",
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        }
        payload = _semantic_payload(ref)
        if kind == "platform":
            for field, forged in (("input_cursor", {}), ("output_cursor", [])):
                invalid_ref = {**ref, "page": {**ref["page"], field: forged}}
                invalid = _semantic_payload(invalid_ref)
                response = _socket_request(socket_path, {"token": "token", "report": invalid})
                assert response["ok"] is False
                assert accepted == []
        response = _socket_request(socket_path, {"token": "token", "report": payload})
        assert response == {"ok": True}
        assert accepted == [payload]

        missing = dict(payload)
        missing.pop("gaps")
        assert _socket_request(socket_path, {"token": "token", "report": missing})["ok"] is False
    finally:
        sink.stop()


def test_report_sink_returns_detailed_rejection_and_allows_bounded_retry(tmp_path: Path) -> None:
    socket_path = tmp_path / "report.sock"
    accepted: list[dict] = []

    def validator(report: dict) -> None:
        refs = report.get("evidence_refs") or []
        if len(refs) != 2:
            from modeling_team.acceptance_runtime import ExaminerRuntimeBlocked

            raise ExaminerRuntimeBlocked(
                "acceptance-evidence",
                role="platform",
                evidence={
                    "binding_code": "receipt-count-mismatch",
                    "report_ref_count": len(refs),
                    "proxy_receipt_count": 2,
                    "report_ref_ids": ",".join(r.get("ref_id", "") for r in refs),
                    "proxy_receipt_ordinals": "0,1",
                },
            )

    sink = ReportSinkServer(socket_path, "token", accepted.append, kind="platform", validator=validator)
    sink.start()
    try:
        one_ref = _semantic_payload({
            "ref_id": "p0",
            "tool": "get_modeling_context",
            "request_digest": "a" * 64,
            "response_digest": "b" * 64,
            "artifact_path": "acceptance/round/platform-read/handle/0.json",
            "page": {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        })
        rejected = _socket_request(socket_path, {"token": "token", "report": one_ref})
        assert rejected["ok"] is False
        assert rejected["code"] == "report-binding-rejected"
        assert "receipt-count-mismatch" in rejected["detail"]
        assert "report_ref_count=1" in rejected["detail"]
        assert "proxy_receipt_count=2" in rejected["detail"]
        assert rejected["attempts_remaining"] == 2
        assert accepted == []

        two_refs = _semantic_payload([
            {
                "ref_id": "p0",
                "tool": "get_modeling_context",
                "request_digest": "a" * 64,
                "response_digest": "b" * 64,
                "artifact_path": "acceptance/round/platform-read/handle/0.json",
                "page": {
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            },
            {
                "ref_id": "p1",
                "tool": "query_semantic_context",
                "request_digest": "a" * 64,
                "response_digest": "b" * 64,
                "artifact_path": "acceptance/round/platform-read/handle/1.json",
                "page": {
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            },
        ])
        accepted_response = _socket_request(socket_path, {"token": "token", "report": two_refs})
        assert accepted_response == {"ok": True}
        assert len(accepted) == 1

        after = _socket_request(socket_path, {"token": "token", "report": two_refs})
        assert after["code"] == "report-already-submitted"
    finally:
        sink.stop()


def test_report_sink_exhausts_attempt_budget(tmp_path: Path) -> None:
    socket_path = tmp_path / "report.sock"
    accepted: list[dict] = []

    def validator(report: dict) -> None:
        from modeling_team.acceptance_runtime import ExaminerRuntimeBlocked

        raise ExaminerRuntimeBlocked(
            "acceptance-evidence",
            role="platform",
            evidence={"binding_code": "page-shape", "index": 0},
        )

    sink = ReportSinkServer(socket_path, "token", accepted.append, kind="platform", validator=validator, max_attempts=2)
    sink.start()
    try:
        bad = _semantic_payload({
            "ref_id": "p0",
            "tool": "get_modeling_context",
            "request_digest": "a" * 64,
            "response_digest": "b" * 64,
            "artifact_path": "acceptance/round/platform-read/handle/0.json",
            "page": {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        })
        first = _socket_request(socket_path, {"token": "token", "report": bad})
        assert first["code"] == "report-binding-rejected"
        assert first["attempts_remaining"] == 1
        second = _socket_request(socket_path, {"token": "token", "report": bad})
        assert second["code"] == "report-binding-rejected"
        assert second["attempts_remaining"] == 0
        third = _socket_request(socket_path, {"token": "token", "report": bad})
        assert third["code"] == "report-attempts-exceeded"
        assert accepted == []
    finally:
        sink.stop()


def test_source_child_payload_gets_host_bindings_and_manifest_ref(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(b"approved source")
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    ticket = _source_ticket("child-source", source_digest)
    carrier = RunnerAcceptanceCarrier(
        tmp_path / "carrier",
        task_id="task-r23005",
        acceptance_id="acceptance",
        source_materials={"source.md": source},
    )
    carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
    carrier.ack_ticket(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        ticket_digest_value=ticket["ticket_digest"],
    )
    projection, input_digest = carrier.project_child_input(
        round_id=ticket["acceptance_round_id"], kind="source"
    )
    handle = carrier.start_child(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        kind="source",
        input_ref=projection,
        input_digest=input_digest,
        ticket_digest_value=ticket["ticket_digest"],
        request_id="child-source-start",
        attempt=0,
    )
    stored = carrier.ingest_child_report(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        handle=handle,
        payload=_semantic_payload({"location": "source.md#answer"}),
    )
    ref = stored["evidence_refs"][0]
    assert ref["type"] == "approved_source"
    assert ref["ticket_digest"] == ticket["ticket_digest"]
    assert ref["source_bundle_digest"] == ticket["source_bundle_digest"]
    assert ref["artifact_digest"] == source_digest
    assert ref["artifact_path"] == (
        f"acceptance/{ticket['acceptance_round_id']}/approved-source/source.md.json"
    )
    assert ref["ref_id"].startswith("approved-source-")
    assert stored["source_bundle_digest"] == ticket["source_bundle_digest"]
    assert stored["model_state"] == ticket["model_state"]


def test_child_payload_rejects_runner_fields_and_unknown_source_location(tmp_path: Path) -> None:
    ticket = _source_ticket("child-reject", "b" * 64)
    carrier = RunnerAcceptanceCarrier(tmp_path / "carrier", task_id="task-r23005", acceptance_id="acceptance")
    carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
    carrier.ack_ticket(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        ticket_digest_value=ticket["ticket_digest"],
    )
    projection, input_digest = carrier.project_child_input(
        round_id=ticket["acceptance_round_id"], kind="source"
    )
    handle = carrier.start_child(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        kind="source",
        input_ref=projection,
        input_digest=input_digest,
        ticket_digest_value=ticket["ticket_digest"],
        request_id="child-reject-start",
        attempt=0,
    )
    extra = _semantic_payload({"location": "source.md"})
    extra["ticket_digest"] = ticket["ticket_digest"]
    with pytest.raises(AcceptanceContractError, match="fields drift"):
        carrier.ingest_child_report(
            acceptance_id="acceptance",
            round_id=ticket["acceptance_round_id"],
            handle=handle,
            payload=extra,
        )
    with pytest.raises(AcceptanceContractError, match="approved manifest"):
        carrier.ingest_child_report(
            acceptance_id="acceptance",
            round_id=ticket["acceptance_round_id"],
            handle=handle,
            payload=_semantic_payload({"location": "foreign.md"}),
        )


def test_platform_child_payload_matches_current_proxy_receipt_and_rejects_duplicate(tmp_path: Path) -> None:
    ticket = _ticket("child-platform")

    class Proxy:
        def __init__(self, receipt: dict) -> None:
            self._receipt = receipt

        def receipt_snapshot(self):
            return (self._receipt,)

    class Resource:
        def __init__(self, spec: dict) -> None:
            self.proxy = Proxy(
                {
                    "ordinal": 0,
                    "project_id": ticket["platform_read_scope"]["project_id"],
                    "ontology_id": ticket["platform_read_scope"]["ontology_id"],

                    "ticket_digest": ticket["ticket_digest"],
                    "model_state_digest": ticket["model_state_digest"],
                    "tool": "get_modeling_context",
                    "request_digest": "a" * 64,
                    "response_digest": "b" * 64,
                    "artifact_path": (
                        f"acceptance/{spec['acceptance_round_id']}/platform-read/"
                        f"{spec['child_handle_digest']}/0.json"
                    ),
                    "page": {
                        "ordinal": 0,
                        "input_cursor": None,
                        "output_cursor": None,
                        "has_more": False,
                        "sequence_complete": True,
                    },
                }
            )
            self.spec = spec

        def stop(self) -> None:
            pass

        def destroy(self) -> None:
            pass

    carrier = RunnerAcceptanceCarrier(
        tmp_path / "carrier", task_id="task-r23005", acceptance_id="acceptance", child_factory=Resource
    )
    carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
    carrier.ack_ticket(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        ticket_digest_value=ticket["ticket_digest"],
    )
    projection, input_digest = carrier.project_child_input(
        round_id=ticket["acceptance_round_id"], kind="platform"
    )
    handle = carrier.start_child(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        kind="platform",
        input_ref=projection,
        input_digest=input_digest,
        ticket_digest_value=ticket["ticket_digest"],
        request_id="child-platform-start",
        attempt=0,
    )
    path = f"acceptance/{ticket['acceptance_round_id']}/platform-read/{handle.digest}/0.json"
    locator = {
        "ref_id": "proxy-ref",
        "tool": "get_modeling_context",
        "request_digest": "a" * 64,
        "response_digest": "b" * 64,
        "artifact_path": path,
        "page": {
            "ordinal": 0,
            "input_cursor": None,
            "output_cursor": None,
            "has_more": False,
            "sequence_complete": True,
        },
    }
    for field, forged in (("input_cursor", {}), ("output_cursor", [])):
        invalid_locator = {**locator, "page": {**locator["page"], field: forged}}
        with pytest.raises(AcceptanceContractError, match="cursors"):
            carrier.ingest_child_report(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle,
                payload=_semantic_payload(invalid_locator),
            )
        assert carrier._reports == {}
        assert carrier._pending_reports == {}
        assert not (carrier.root / path).exists()
    stored = carrier.ingest_child_report(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        handle=handle,
        payload=_semantic_payload(locator),
    )
    assert stored["source_bundle_digest"] is None
    assert stored["evidence_refs"][0]["type"] == "platform_read"
    assert stored["evidence_refs"][0]["ticket_digest"] == ticket["ticket_digest"]
    duplicate = _semantic_payload(locator)
    duplicate["evidence_refs"] = [locator, locator]
    with pytest.raises(AcceptanceContractError, match="repeats"):
        validate_examiner_payload(duplicate, kind="platform")


def test_platform_payload_accepts_mistranscribed_digests_before_stamping() -> None:
    """R2.3-009 start23: hand-copied digests must not burn report attempts.

    The payload gate runs before ``ingest_child_report`` stamps the canonical
    receipt digests, so a one-character transcription error in a child-copied
    digest must pass this gate; the receipt binding, not this gate, owns
    digest truth.  Identity for the repeats check is the child's own
    (tool, ref_id) coordinates.
    """

    def locator_with(digests: tuple[str, str], ref_id: str) -> dict:
        return {
            "ref_id": ref_id,
            "tool": "query_semantic_context",
            "request_digest": digests[0],
            "response_digest": digests[1],
            "artifact_path": "acceptance/round/platform-read/handle/0.json",
            "page": {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        }

    payload = _semantic_payload(locator_with(("ac29ff42d279fa9b301dff956c3d3", "b58199a0bc99da573f51ca3c38757"), "p0"))
    validate_examiner_payload(payload, kind="platform")

    payload = _semantic_payload(locator_with(("", "b" * 64), "p0"))
    with pytest.raises(AcceptanceContractError, match="request_digest is invalid"):
        validate_examiner_payload(payload, kind="platform")

    two = _semantic_payload(locator_with(("a" * 64, "b" * 64), "p0"))
    two["evidence_refs"] = [
        locator_with(("a" * 64, "b" * 64), "p0"),
        locator_with(("a" * 64, "b" * 64), "p0"),
    ]
    with pytest.raises(AcceptanceContractError, match="repeats"):
        validate_examiner_payload(two, kind="platform")
    distinct = _semantic_payload(locator_with(("a" * 64, "b" * 64), "p0"))
    distinct["evidence_refs"] = [
        locator_with(("a" * 64, "b" * 64), "p0"),
        locator_with(("a" * 64, "b" * 64), "p1"),
    ]
    validate_examiner_payload(distinct, kind="platform")


@pytest.mark.parametrize("field, forged", [("input_cursor", {}), ("output_cursor", [])])
def test_stored_platform_typed_ref_rejects_forged_cursor_types(field: str, forged: object) -> None:
    ref = {
        "type": "platform_read",
        "ref_id": "proxy-ref",
        "ticket_digest": "a" * 64,
        "model_state_digest": "b" * 64,
        "tool": "get_modeling_context",
        "request_digest": "c" * 64,
        "response_digest": "d" * 64,
        "artifact_path": "acceptance/round/platform-read/handle/0.json",
        "page": {
            "ordinal": 0,
            "input_cursor": "cursor-in",
            "output_cursor": None,
            "has_more": False,
            "sequence_complete": True,
        },
    }
    ref["page"][field] = forged
    with pytest.raises(AcceptanceContractError, match="cursors"):
        validate_typed_evidence_ref(ref)

    valid = {
        **ref,
        "page": {**ref["page"], "input_cursor": "cursor-in", "output_cursor": None},
    }
    assert validate_typed_evidence_ref(valid)["page"] == valid["page"]


@pytest.mark.parametrize("kind", ["source", "platform"])
def test_long_private_paths_use_one_short_socket_root_and_cleanup(
    monkeypatch, tmp_path: Path, kind: str
) -> None:
    class Process:
        pid = 0

        def poll(self) -> int:
            return 0

    base = tmp_path
    for index in range(5):
        base = base / (f"long-private-segment-{index}-" + "x" * 16)
    private_root = base / "private"
    private_root.mkdir(parents=True, mode=0o700)
    (private_root / "input.json").write_text("{}", encoding="utf-8")

    if kind == "source":
        # A formal Source Examiner now requires the carrier-staged approved
        # bytes (R2.3-009 start21 SOURCE_TEXT_JSON seam); stage a minimal
        # manifest-shaped tree for the formal fixtures.
        sources = private_root / "sources"
        sources.mkdir()
        (sources / "source.md").write_text("# approved source\n", encoding="utf-8")
    host_auth = tmp_path / "auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    host_auth.chmod(0o600)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    adapter = CodexRuntimeAdapter(
        repository_root=repository_root(),
        use_bwrap=False,
        process_factory=lambda *_args, **_kwargs: Process(),
    )
    adapter._coordination_enabled = True
    adapter._team_model_profile = load_team_model_profile(
        repository_root(), DEFAULT_MODEL_PROFILE_ID
    )
    adapter._provider_sessions = _SessionsDouble()  # type: ignore[assignment]
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)

    def rpc(_agent, method: str, _params):
        if method == "thread/start":
            return {"thread": {"id": f"{kind}-thread"}}
        if method == "turn/start":
            return {"turn": {"id": f"{kind}-turn"}}
        if method == "mcpServerStatus/list":
            servers = [{"name": "examiner_report", "tools": [{"name": "submit_examiner_report"}, *({"name": name} for name in sorted(HANDOFF_TOOL_NAMES))]}]
            if kind == "platform":
                servers.append(
                    {
                        "name": "platform_read_proxy",
                        "tools": [{"name": name} for name in PLATFORM_PROXY_READ_TOOLS],
                    }
                )
            return {"data": servers}
        return {}

    adapter._rpc = rpc  # type: ignore[method-assign]
    spec: dict[str, object] = {
        "task_id": "r2-3-005-formal-acceptance",
        "acceptance_round_id": "round-1",
        "kind": kind,
        "attempt": 0,
        "session_id": "session-1",
        "child_handle_digest": "a" * 64,
        "ticket_digest": "b" * 64,
        "input_digest": "c" * 64,
        "private_root": str(private_root),
        "private_input": str(private_root / "input.json"),
        "descriptor": {"kind": f"{kind}_examiner", "package_digest": "d" * 64},
        "timeout_seconds": 30,
    }
    if kind == "platform":
        spec.update(
            {
                "read_key_id": "read-key",
                "read_key_digest": "e" * 64,
                "platform_read_scope": {
                    "project_id": "project",
                    "ontology_id": "ontology",

                },
                "model_state_digest": "f" * 64,
                "allowed_read_tools": list(PLATFORM_PROXY_READ_TOOLS),
                "read_key_plaintext": "platform-secret",
                "read_key_revoke": lambda _key: None,
            }
        )
    resource = adapter.acceptance_child_factory(spec)
    socket_root = Path(str(resource.spec["_runtime_socket_root"]))
    assert socket_root != private_root / "home"
    assert (socket_root / "report.sock").exists()
    if kind == "platform":
        assert (socket_root / "platform-proxy.sock").exists()
    resource.destroy()
    adapter.stop()
    assert not socket_root.exists()


def test_report_sink_preserves_generic_validator_rejection_detail(tmp_path: Path) -> None:
    # start11 fix (R2.3-009): a validator that raises outside the typed
    # ChildRuntimeError/ExaminerRuntimeBlocked pair (for example the carrier's
    # AcceptanceContractError) previously collapsed into a bare
    # "report-rejected" with no reason, leaving the rejection undiagnosable.
    # The sink must surface the exception type and message.
    socket_path = tmp_path / "report.sock"
    accepted: list[dict] = []

    def validator(report: dict) -> None:
        raise RuntimeError("ticket digest mismatch: published ticket is stale")

    sink = ReportSinkServer(socket_path, "token", accepted.append, kind="platform", validator=validator)
    sink.start()
    try:
        payload = _semantic_payload({
            "ref_id": "p0",
            "tool": "get_modeling_context",
            "request_digest": "a" * 64,
            "response_digest": "b" * 64,
            "artifact_path": "acceptance/round/platform-read/handle/0.json",
            "page": {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        })
        rejected = _socket_request(socket_path, {"token": "token", "report": payload})
        assert rejected["ok"] is False
        assert rejected["code"] == "report-rejected"
        assert "RuntimeError" in rejected["detail"]
        assert "ticket digest mismatch" in rejected["detail"]
        assert rejected["attempts_remaining"] == 2
        assert accepted == []
        assert sink._rejections == [
            rejected["detail"]
        ], "rejection history must retain the validator reason, not a bare label"
    finally:
        sink.stop()

def test_report_sink_preserves_submit_callback_rejection_detail(tmp_path: Path) -> None:
    # start13 fix (R2.3-009): the production submit callback runs the full
    # Host binding (handle lookup, envelope validation, receipt binding,
    # persistence).  Its exceptions escaped to the sink's outermost handler
    # and answered with a bare "report-rejected" with no detail and no
    # attempts accounting, so the examiner could neither correct its payload
    # nor exhaust its budget — three identical opaque rejections killed the
    # cq-001 round.  The submit path must surface the reason like the
    # validator paths do.
    socket_path = tmp_path / "report.sock"
    submitted: list[dict] = []

    def submit(report: dict) -> dict:
        submitted.append(report)
        raise RuntimeError("scoped proxy receipt scope binding drifted")

    sink = ReportSinkServer(socket_path, "token", submit, kind="platform", validator=None)
    sink.start()
    try:
        payload = _semantic_payload({
            "ref_id": "p0",
            "tool": "get_modeling_context",
            "request_digest": "a" * 64,
            "response_digest": "b" * 64,
            "artifact_path": "acceptance/round/platform-read/handle/0.json",
            "page": {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        })
        rejected = _socket_request(socket_path, {"token": "token", "report": payload})
        assert rejected["ok"] is False
        assert rejected["code"] == "report-submit-rejected"
        assert "RuntimeError" in rejected["detail"]
        assert "scope binding drifted" in rejected["detail"]
        assert rejected["attempts_remaining"] == 2
        assert len(submitted) == 1, "the callback ran and its failure was surfaced"
        assert sink._submitted is False, "a failed submit must not latch submitted"
        assert sink._rejections == [rejected["detail"]]
    finally:
        sink.stop()
