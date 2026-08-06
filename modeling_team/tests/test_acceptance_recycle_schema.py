from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from modeling_team.capability_mcp import RunnerCapabilityEndpoint


class AcceptanceRecycleSchemaTests(unittest.TestCase):
    def test_start40_timeout_fixture_requires_outer_typed_digest_wrapper(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "r23005-start40-cq002-timeout-recycle.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        calls: list[dict[str, Any]] = []

        def dispatch(_role: str, _operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
            calls.append(dict(arguments))
            return {"accepted": True}

        with tempfile.TemporaryDirectory() as directory:
            endpoint = RunnerCapabilityEndpoint(
                role="acceptance",
                socket_path=Path(directory) / "acceptance.sock",
                token="acceptance-token",
                dispatch=dispatch,
            )

            def request(completion_ref: dict[str, Any], request_id: str) -> dict[str, Any]:
                return endpoint.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "token": "acceptance-token",
                        "method": "tools/call",
                        "params": {
                            "name": "acceptance_child_recycle",
                            "arguments": {
                                "acceptance_id": fixture["acceptance_id"],
                                "round_id": fixture["round_id"],
                                "child_handle": fixture["child_handle"],
                                "completion_ref": completion_ref,
                                "request_id": request_id,
                            },
                        },
                    }
                )

            failure = fixture["failure"]
            wrong_refs = (
                {"failure_digest": failure["failure_digest"]},
                {**fixture["recycle_completion_ref"], "type": failure["type"]},
                failure,
            )
            for index, completion_ref in enumerate(wrong_refs):
                self.assertIn("error", request(completion_ref, f"wrong-{index}"))
            self.assertEqual(calls, [])

            accepted = request(fixture["recycle_completion_ref"], "correct")
            self.assertNotIn("error", accepted)
            self.assertEqual(calls[0]["completion_ref"], fixture["recycle_completion_ref"])

            terminal = request({"terminal_report_digest": "b" * 64}, "terminal")
            self.assertNotIn("error", terminal)
            self.assertEqual(calls[1]["completion_ref"], {"terminal_report_digest": "b" * 64})


if __name__ == "__main__":
    unittest.main()
