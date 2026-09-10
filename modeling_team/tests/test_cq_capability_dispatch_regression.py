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

import json
import tempfile
from pathlib import Path
from typing import Any

from modeling_team.acceptance import RunnerAcceptanceCarrier
from modeling_team.capability_mcp import (
    COMPETENCY_QUESTION_ROLE,
    CQ_OPERATION,
    _stdio_request,
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
