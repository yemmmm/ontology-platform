"""Regression: a real CQ socket ``tools/call`` reaches the configured draft handler.

Real run r30006-20260910-auth002-start3 evidenced ``cq_publish_question_draft``
repeatedly failing with a generic ``-32001`` whose Runner-private audit trail
recorded ``error_type=NameError`` / ``name 'CQ_OPERATION' is not defined``:
``RunnerAcceptanceCarrier._dispatch_capability`` referenced the singular
constant while ``modeling_team.acceptance`` imported only the plural
``CQ_OPERATIONS``.  The role/operation gate therefore passed and the first CQ
dispatch crashed, so a configured draft handler was unreachable.

Real run ``auth004-start1`` evidenced the second half of the same wiring once
the dispatch ran: every ``cq_publish_question_draft`` call still failed with a
generic ``-32001`` whose audit trail recorded ``error_type=TypeError`` /
``'NoneType' object is not iterable``.  The configured handler's contract is the
complete ``{cq_id, draft}`` arguments envelope -- ``TeamRunner``'s
``_publish_cq_question_draft`` extracts and validates ``draft`` itself -- but the
CQ dispatch unwrapped the envelope and passed the bare draft body, so
``arguments.get("draft")`` was ``None`` inside the handler.

This test drives the real carrier-created competency-question endpoint over a
real AF_UNIX socket ``tools/call`` into a synthetic handler: it does not mock
``_dispatch_capability``, does not stop at ``tools/list``, and uses no real
business draft data.  The end-to-end counterpart that runs the same call through
the real ``TeamRunner._publish_cq_question_draft`` and its draft/review
persistence is ``test_m5_cq_socket_tools_call_publishes_through_the_real_runner_handler``
in ``test_r3011_runner_wiring.py``.
"""

from __future__ import annotations

import io
import json
import threading
import tempfile
import time
from pathlib import Path
from typing import Any

from modeling_team import capability_mcp
from modeling_team.acceptance import RunnerAcceptanceCarrier
from modeling_team.capability_mcp import (
    COMPETENCY_QUESTION_ROLE,
    CQ_OPERATION,
    _stdio_request,
    run_stdio_client,
)

# Synthetic envelope only: the advertised schema fixes ``draft`` as an object,
# and the synthetic handler below replaces the Runner's semantic validation.
_DRAFT: dict[str, Any] = {"phase": "synthetic", "questions": []}


def test_cq_socket_tools_call_reaches_the_configured_draft_handler() -> None:
    received: list[Any] = []

    def handler(arguments: Any) -> dict[str, Any]:
        # The handler owns the complete arguments envelope: it is entered once
        # with exactly what the CQ role submitted, and extracts ``draft`` itself.
        received.append(arguments)
        return {"ok": True, "received": arguments}

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "modeling-runs" / "run-1" / "acceptance-carrier"
        carrier = RunnerAcceptanceCarrier(
            root,
            task_id="cq-dispatch-regression",
            acceptance_id="acceptance",
            cq_draft_handler=handler,
        )
        assert carrier.cq_capability_enabled is True
        endpoint = carrier.capability_endpoint(COMPETENCY_QUESTION_ROLE)
        assert endpoint.operations == (CQ_OPERATION,)
        token = carrier.capability_token(COMPETENCY_QUESTION_ROLE)

        carrier.start_cq_endpoint()
        try:
            response = _stdio_request(
                str(endpoint.socket_path),
                token,
                {
                    "jsonrpc": "2.0",
                    "id": "cq-regression-1",
                    "method": "tools/call",
                    "params": {
                        "name": CQ_OPERATION,
                        "arguments": {
                            "cq_id": COMPETENCY_QUESTION_ROLE,
                            "draft": _DRAFT,
                        },
                    },
                },
            )
        finally:
            endpoint.stop()

        audit_path = root.parent / "evidence" / "capability-calls.jsonl"
        # The Runner-private audit trail must record the dispatch as ok, not as
        # the NameError the production evidence showed for every attempt.  Read
        # it before the temporary carrier root disappears.
        audit_records = [
            json.loads(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    # The synthetic handler must have been entered with the complete submitted
    # envelope, and the handler result must round-trip on the success path.
    envelope = {"cq_id": COMPETENCY_QUESTION_ROLE, "draft": _DRAFT}
    assert received == [envelope], f"draft handler not reached: {response}"
    assert "error" not in response, response
    assert response["result"]["structuredContent"] == {
        "ok": True,
        "data": {"ok": True, "received": envelope},
    }

    records = audit_records
    assert records, audit_path
    assert records[-1]["operation"] == CQ_OPERATION
    assert records[-1]["ok"] is True
    assert "error_type" not in records[-1]


def test_stdio_request_returns_delayed_real_socket_response(monkeypatch, tmp_path) -> None:
    original_socket = capability_mcp.socket.socket
    socket_path = tmp_path / "capability-return.sock"
    dispatch_count = 0

    server = original_socket(capability_mcp.socket.AF_UNIX, capability_mcp.socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(1)

    def serve_once() -> None:
        nonlocal dispatch_count
        try:
            connection, _ = server.accept()
            with connection:
                request = json.loads(connection.makefile("r", encoding="utf-8").readline())
                dispatch_count += 1
                time.sleep(0.08)
                response = {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "result": {"ok": True, "write_state": "applied"},
                }
                connection.sendall((json.dumps(response) + "\n").encode("utf-8"))
        finally:
            server.close()

    worker = threading.Thread(target=serve_once)
    worker.start()

    class _ShortTimeoutSocket(original_socket):
        def settimeout(self, value: float | None) -> None:
            # Make the historical 15-second read budget a 20ms fixture budget.
            # The fixed implementation clears this after the request is sent.
            super().settimeout(0.02 if value == 15 else value)

    monkeypatch.setattr(capability_mcp.socket, "socket", _ShortTimeoutSocket)
    try:
        response = _stdio_request(
            str(socket_path),
            "token",
            {"jsonrpc": "2.0", "id": "delayed", "method": "tools/call"},
        )
    finally:
        worker.join(timeout=2)

    assert response == {
        "jsonrpc": "2.0",
        "id": "delayed",
        "result": {"ok": True, "write_state": "applied"},
    }
    assert dispatch_count == 1


def test_stdio_client_keeps_each_request_id_on_forwarding_errors(tmp_path, monkeypatch) -> None:
    def fail_forward(*_args, **_kwargs):
        raise TimeoutError("capability response did not arrive")

    monkeypatch.setattr(capability_mcp, "_stdio_request", fail_forward)
    token_file = tmp_path / "token"
    token_file.write_text("token\n", encoding="utf-8")
    input_stream = io.StringIO(
        '{"jsonrpc":"2.0","id":"string-id","method":"tools/call"}\n'
        '{"jsonrpc":"2.0","id":17,"method":"tools/call"}\n'
        '{"jsonrpc":"2.0","id":\n'
    )
    output_stream = io.StringIO()

    assert run_stdio_client("/tmp/capability-return.sock", token_file, stdin=input_stream, stdout=output_stream) == 0

    responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert [response["id"] for response in responses] == ["string-id", 17, None]
