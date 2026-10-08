"""Tests for the Runner capability broker stage-handoff no_match diagnostic.

Platform-contract coverage only: when ``protocol_build_acceptance_stage_handoff``
cannot resolve a Protocol-supplied ``(tool, arguments, artifact_path)`` triple to
exactly one observed platform call, the broker returns the structured
``no_match`` diagnostic on the success path with ``structuredContent``
``{ok: False, error: ...}`` (plus a readable text block).  The codex CLI MCP
client wrapper strips ``error.data`` when re-wrapping a JSON-RPC error, so the
diagnostic must not travel on the ``-32001`` error path; Protocol reads
``ok: False`` and self-corrects instead of guessing.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from modeling_team.acceptance import (
    RunnerAcceptanceCarrier,
    model_state_digest,
    stage_handoff_no_match_diagnostic,
)
from modeling_team.capability_mcp import RunnerCapabilityEndpoint


class _StructuredError(ValueError):
    """A fake dispatch error that carries a structured ``data`` mapping."""

    def __init__(self, message: str, *, data: dict[str, Any]) -> None:
        super().__init__(message)
        self.data = data


def _broker(
    directory: Path,
    *,
    dispatch: Any,
    role: str = "protocol",
    operations: tuple[str, ...] | None = None,
) -> RunnerCapabilityEndpoint:
    return RunnerCapabilityEndpoint(
        role=role,
        socket_path=directory / f"{role}.sock",
        token=f"{role}-token",
        dispatch=dispatch,
        operations=operations,
    )


class BrokerDiagnosticPassthroughTests(unittest.TestCase):
    """The broker routes a dispatch exception's Mapping ``data`` to a success-path ``{ok: False}`` result."""

    def test_structured_dispatch_error_surfaces_diagnostic_on_success_path(self) -> None:
        captured: list[tuple[str, str, dict[str, Any]]] = []

        def dispatch(role: str, operation: str, arguments: dict[str, Any]) -> Any:
            captured.append((role, operation, dict(arguments)))
            raise _StructuredError(
                "stage handoff builder request is not one observed platform call",
                data={
                    "reason": "stage_handoff_no_match",
                    "stage": "dry-run",
                    "requested": {"tool": "t", "arguments": {}, "artifact_path": "p"},
                    "observed_total": 1,
                    "observed_candidates": 0,
                    "near_misses": [],
                },
            )

        with tempfile.TemporaryDirectory() as directory:
            endpoint = _broker(Path(directory), dispatch=dispatch)
            response = endpoint.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "req-1",
                    "token": "protocol-token",
                    "method": "tools/call",
                    "params": {
                        "name": "protocol_build_acceptance_stage_handoff",
                        "arguments": {
                            "protocol_id": "protocol",
                            "stage_calls": {
                                "dry-run": {"tool": "t", "arguments": {}, "artifact_path": "p"},
                                "apply": {"tool": "t", "arguments": {}, "artifact_path": "p"},
                                "readback": {"tool": "t", "arguments": {}, "artifact_path": "p"},
                            },
                        },
                    },
                }
            )
        self.assertEqual(captured[0][1], "protocol_build_acceptance_stage_handoff")
        self.assertNotIn("error", response)
        structured = response["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        diagnostic = structured["error"]
        self.assertEqual(diagnostic["reason"], "stage_handoff_no_match")
        self.assertEqual(diagnostic["stage"], "dry-run")
        # The text block carries the same diagnostic so the codex CLI MCP
        # wrapper surfaces it even when structuredContent is not inspected.
        text = response["result"]["content"][0]["text"]
        self.assertIn("stage_handoff_no_match", text)
        self.assertIn("dry-run", text)

    def test_plain_dispatch_error_stays_opaque_without_data(self) -> None:
        def dispatch(role: str, operation: str, arguments: dict[str, Any]) -> Any:
            raise ValueError("anything")

        with tempfile.TemporaryDirectory() as directory:
            endpoint = _broker(Path(directory), dispatch=dispatch)
            response = endpoint.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "req-2",
                    "token": "protocol-token",
                    "method": "tools/call",
                    "params": {
                        "name": "protocol_build_acceptance_stage_handoff",
                        "arguments": {
                            "protocol_id": "protocol",
                            "stage_calls": {
                                stage: {"tool": "t", "arguments": {}, "artifact_path": "p"}
                                for stage in ("dry-run", "apply", "readback")
                            },
                        },
                    },
                }
            )
        error = response["error"]
        self.assertEqual(error["code"], -32001)
        self.assertNotIn("data", error)

    def test_non_mapping_data_attribute_is_not_surfaced(self) -> None:
        class _BadError(Exception):
            data = "not-a-mapping"

        def dispatch(role: str, operation: str, arguments: dict[str, Any]) -> Any:
            raise _BadError()

        with tempfile.TemporaryDirectory() as directory:
            endpoint = _broker(Path(directory), dispatch=dispatch)
            response = endpoint.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "req-3",
                    "token": "protocol-token",
                    "method": "tools/call",
                    "params": {
                        "name": "protocol_build_acceptance_stage_handoff",
                        "arguments": {
                            "protocol_id": "protocol",
                            "stage_calls": {
                                stage: {"tool": "t", "arguments": {}, "artifact_path": "p"}
                                for stage in ("dry-run", "apply", "readback")
                            },
                        },
                    },
                }
            )
        self.assertNotIn("data", response["error"])

    def test_protocol_errors_remain_opaque(self) -> None:
        def dispatch(role: str, operation: str, arguments: dict[str, Any]) -> Any:
            raise AssertionError("dispatch must not run for protocol errors")

        cases = [
            {"id": "bad-token", "token": "wrong", "method": "tools/list", "params": {}},
            {"id": "bad-method", "token": "protocol-token", "method": "tools/call", "params": {}},
            {
                "id": "bad-shape",
                "token": "protocol-token",
                "method": "tools/call",
                "params": {"name": "protocol_build_acceptance_stage_handoff", "arguments": {}},
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            endpoint = _broker(Path(directory), dispatch=dispatch)
            for case in cases:
                response = endpoint.handle(case)
                error = response["error"]
                self.assertEqual(error["code"], -32001, msg=f"case={case}")
                self.assertNotIn("data", error, msg=f"case={case}")

    def test_successful_dispatch_still_returns_structured_content(self) -> None:
        def dispatch(role: str, operation: str, arguments: dict[str, Any]) -> Any:
            return {"built": True}

        with tempfile.TemporaryDirectory() as directory:
            endpoint = _broker(Path(directory), dispatch=dispatch)
            response = endpoint.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "ok-1",
                    "token": "protocol-token",
                    "method": "tools/call",
                    "params": {
                        "name": "protocol_build_acceptance_stage_handoff",
                        "arguments": {
                            "protocol_id": "protocol",
                            "stage_calls": {
                                stage: {"tool": "t", "arguments": {}, "artifact_path": "p"}
                                for stage in ("dry-run", "apply", "readback")
                            },
                        },
                    },
                }
            )
        self.assertNotIn("error", response)
        self.assertTrue(response["result"]["structuredContent"]["ok"])
        self.assertEqual(response["result"]["structuredContent"]["data"], {"built": True})


class StageHandoffNoMatchDiagnosticTests(unittest.TestCase):
    """Unit-test the diagnostic builder for 0-match and defensive >1 cases."""

    @staticmethod
    def _record(tool: str, arguments: dict[str, Any], artifact_path: str) -> dict[str, Any]:
        return {
            "tool": tool,
            "request_arguments": dict(arguments),
            "artifact_path": artifact_path,
            "request_digest": "0" * 64,
            "response_digest": "1" * 64,
        }

    def test_zero_match_lists_near_misses_sharing_tool_or_artifact_path(self) -> None:
        records = {
            "evidence/a-1.json": self._record("submit_modeling_batch", {"mode": "dry_run"}, "evidence/a-1.json"),
            "evidence/b-2.json": self._record("get_modeling_context", {"ontology_id": "o"}, "evidence/b-2.json"),
        }
        entry = {
            "tool": "submit_modeling_batch",
            "arguments": {"mode": "dry_run"},
            "artifact_path": "evidence/typo-wrong.json",
        }
        diagnostic = stage_handoff_no_match_diagnostic(
            "dry-run", entry, matches=[], observed_records=records
        )
        self.assertEqual(diagnostic["reason"], "stage_handoff_no_match")
        self.assertEqual(diagnostic["stage"], "dry-run")
        self.assertEqual(diagnostic["observed_total"], 2)
        self.assertEqual(diagnostic["observed_candidates"], 0)
        self.assertEqual(
            diagnostic["requested"],
            {"tool": "submit_modeling_batch", "arguments": {"mode": "dry_run"}, "artifact_path": "evidence/typo-wrong.json"},
        )
        near = diagnostic["near_misses"]
        self.assertEqual(len(near), 1)
        self.assertEqual(near[0]["tool"], "submit_modeling_batch")
        self.assertEqual(near[0]["arguments"], {"mode": "dry_run"})
        self.assertEqual(near[0]["artifact_path"], "evidence/a-1.json")

    def test_zero_match_with_no_near_miss_returns_empty_list(self) -> None:
        records = {
            "evidence/a-1.json": self._record("unrelated_tool", {"x": 1}, "evidence/a-1.json"),
        }
        entry = {"tool": "submit_modeling_batch", "arguments": {}, "artifact_path": "evidence/missing.json"}
        diagnostic = stage_handoff_no_match_diagnostic(
            "apply", entry, matches=[], observed_records=records
        )
        self.assertEqual(diagnostic["observed_candidates"], 0)
        self.assertEqual(diagnostic["near_misses"], [])

    def test_multiple_matches_is_defensive_count_without_near_misses(self) -> None:
        # ``_platform_read_artifacts`` is keyed by artifact_path, so two records
        # sharing the full triple cannot occur via the public registration path.
        # The >1 branch is a defensive guard; it reports the count and does not
        # list near misses.
        shared = self._record("submit_modeling_batch", {"mode": "dry_run"}, "evidence/same.json")
        records = {"evidence/same.json": shared, "duplicate-key": dict(shared)}
        entry = {"tool": "submit_modeling_batch", "arguments": {"mode": "dry_run"}, "artifact_path": "evidence/same.json"}
        diagnostic = stage_handoff_no_match_diagnostic(
            "dry-run", entry, matches=[shared, dict(shared)], observed_records=records
        )
        self.assertEqual(diagnostic["reason"], "stage_handoff_multiple_matches")
        self.assertEqual(diagnostic["observed_candidates"], 2)
        self.assertNotIn("near_misses", diagnostic)


class CapabilityHandoffBrokerEndToEndTests(unittest.TestCase):
    """Drive the real carrier through the real broker endpoint for no_match."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        directory = Path(self._tmp.name)
        self.root = directory / "modeling-runs" / "run-1" / "acceptance-carrier"
        self.carrier = RunnerAcceptanceCarrier(
            self.root,
            task_id="platform-contract-diagnostic",
            acceptance_id="acceptance",
        )
        state = {
            "project_id": "project-1",
            "ontology_id": "ontology-1",
            "workspace_version": "workspace-1",
            "source_signature": "source-1",
            "build_session_id": "session-1",
            "graph_set_id": "graph-1",
        }
        state["state_digest"] = model_state_digest(state)
        self.carrier.bind_model_state(state)
        # Candidate with no consumer_query plan disables the ordinary retrieval
        # gate so the builder reaches the exact-match guard directly.
        candidate = {
            "candidate_kind": "platform-neutral-candidate-v2",
            "candidate_revision": "revision-1",
            "scope": "slice",
            "constraints": [],
            "items": [],
        }
        digest = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.candidate_digest = hashlib.sha256(digest).hexdigest()
        self.carrier.register_accepted_candidate(
            candidate_revision="revision-1",
            candidate_digest=self.candidate_digest,
            candidate=candidate,
        )
        # Register the one real dry-run observation Protocol should have picked.
        self.dry_run_arguments = {
            "session_id": "session-1",
            "client_batch_id": "batch-dry",
            "ontology_id": "ontology-1",
            "idempotency_key": "idem-dry",
            "expected_workspace_version": "workspace-0",
            "items": [{"client_item_id": "item-dry", "command_kind": "create_class", "payload": {"name": "X"}}],
            "mode": "dry_run",
        }
        record = self.carrier.register_platform_tool_result(
            tool="submit_modeling_batch",
            arguments=self.dry_run_arguments,
            result={"structuredContent": {"ok": True, "data": {"mode": "dry_run", "attempt_status": "validated"}}},
        )
        self.real_artifact_path = record["artifact_path"]
        self.endpoint = self.carrier.capability_endpoint("protocol")
        self.token = self.carrier.capability_token("protocol")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _handoff_response(self, stage_calls: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return self.endpoint.handle(
            {
                "jsonrpc": "2.0",
                "id": "handoff-1",
                "token": self.token,
                "method": "tools/call",
                "params": {
                    "name": "protocol_build_acceptance_stage_handoff",
                    "arguments": {"protocol_id": "protocol", "stage_calls": stage_calls},
                },
            }
        )

    def test_wrong_artifact_path_returns_structured_no_match_with_near_miss(self) -> None:
        wrong_path = "evidence/platform-responses/wrong-artifact-path.json"
        self.assertNotEqual(wrong_path, self.real_artifact_path)
        stage_calls = {
            "dry-run": {
                "tool": "submit_modeling_batch",
                "arguments": dict(self.dry_run_arguments),
                "artifact_path": wrong_path,
            },
            "apply": {"tool": "submit_modeling_batch", "arguments": dict(self.dry_run_arguments), "artifact_path": self.real_artifact_path},
            "readback": {"tool": "get_modeling_context", "arguments": {"ontology_id": "ontology-1"}, "artifact_path": self.real_artifact_path},
        }
        response = self._handoff_response(stage_calls)
        self.assertNotIn("error", response)
        structured = response["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        data = structured["error"]
        self.assertEqual(data["reason"], "stage_handoff_no_match")
        self.assertEqual(data["stage"], "dry-run")
        self.assertEqual(data["requested"]["tool"], "submit_modeling_batch")
        self.assertEqual(data["requested"]["arguments"], self.dry_run_arguments)
        self.assertEqual(data["requested"]["artifact_path"], wrong_path)
        self.assertEqual(data["observed_total"], 1)
        self.assertEqual(data["observed_candidates"], 0)
        near = data["near_misses"]
        self.assertEqual(len(near), 1)
        self.assertEqual(near[0]["tool"], "submit_modeling_batch")
        self.assertEqual(near[0]["arguments"], self.dry_run_arguments)
        self.assertEqual(near[0]["artifact_path"], self.real_artifact_path)

    def test_unknown_tool_returns_empty_near_misses(self) -> None:
        stage_calls = {
            "dry-run": {
                "tool": "totally_unknown_tool",
                "arguments": {},
                "artifact_path": "evidence/platform-responses/missing.json",
            },
            "apply": {"tool": "submit_modeling_batch", "arguments": dict(self.dry_run_arguments), "artifact_path": self.real_artifact_path},
            "readback": {"tool": "get_modeling_context", "arguments": {"ontology_id": "ontology-1"}, "artifact_path": self.real_artifact_path},
        }
        response = self._handoff_response(stage_calls)
        structured = response["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        data = structured["error"]
        self.assertEqual(data["reason"], "stage_handoff_no_match")
        self.assertEqual(data["observed_candidates"], 0)
        self.assertEqual(data["near_misses"], [])


class CapabilityAuditTrailTests(unittest.TestCase):
    """The Runner-private audit log records every tools/call outcome.

    The audit trail is the debugging/acceptance channel distinct from the
    Agent-visible response: even when ``handle`` returns an opaque ``-32001``
    (which by contract hides the failure reason from the caller), the original
    exception type/message is recoverable from this file.
    """

    def _endpoint(
        self, directory: Path, dispatch: Any, audit_path: Path
    ) -> RunnerCapabilityEndpoint:
        return RunnerCapabilityEndpoint(
            role="protocol",
            socket_path=directory / "protocol.sock",
            token="protocol-token",
            dispatch=dispatch,
            audit_path=audit_path,
        )

    @staticmethod
    def _handoff_request(request_id: str, stage_calls: dict[str, Any] | None = None) -> dict[str, Any]:
        sc = stage_calls or {
            stage: {"tool": "t", "arguments": {}, "artifact_path": "p"}
            for stage in ("dry-run", "apply", "readback")
        }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "token": "protocol-token",
            "method": "tools/call",
            "params": {
                "name": "protocol_build_acceptance_stage_handoff",
                "arguments": {"protocol_id": "protocol", "stage_calls": sc},
            },
        }

    def test_audit_records_success_structured_plain_and_schema_rejections(self) -> None:
        behaviors: list[tuple[str, Exception | None]] = [
            ("ok", None),
            ("structured", _StructuredError("no match", data={"reason": "stage_handoff_no_match", "stage": "dry-run"})),
            ("plain", ValueError("formal accepted candidate identity is unavailable")),
        ]
        cursor = {"i": 0}

        def dispatch(role: str, operation: str, arguments: dict[str, Any]) -> Any:
            _, exc = behaviors[cursor["i"]]
            cursor["i"] += 1
            if exc is not None:
                raise exc
            return {"built": True}

        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory) / "run" / "evidence" / "capability-calls.jsonl"
            endpoint = self._endpoint(Path(directory), dispatch, audit)
            endpoint.handle(self._handoff_request("ok-1"))
            endpoint.handle(self._handoff_request("struct-1"))
            endpoint.handle(self._handoff_request("plain-1"))
            endpoint.handle(self._handoff_request("bad-1", stage_calls={"dry-run": {}}))
            records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual([r["ok"] for r in records], [True, False, False, False])
        self.assertEqual(records[0]["operation"], "protocol_build_acceptance_stage_handoff")
        self.assertNotIn("error_type", records[0])
        self.assertNotIn("error_message", records[0])
        # Structured diagnostic: original exception type/message AND diagnostic payload.
        self.assertEqual(records[1]["error_type"], "_StructuredError")
        self.assertEqual(records[1]["diagnostic"]["reason"], "stage_handoff_no_match")
        # Plain error: type/message recoverable, no diagnostic, response was opaque -32001.
        self.assertEqual(records[2]["error_type"], "ValueError")
        self.assertIn("accepted candidate identity is unavailable", records[2]["error_message"])
        self.assertNotIn("diagnostic", records[2])
        # Schema/operation rejection is audited as its own category.
        self.assertEqual(records[3]["error_type"], "schema_or_operation_rejected")
        self.assertNotIn("diagnostic", records[3])
        # Every record carries role + timestamp.
        for record in records:
            self.assertEqual(record["role"], "protocol")
            self.assertIn("recorded_at", record)

    def test_no_audit_path_is_silent_and_writes_no_file(self) -> None:
        def dispatch(role: str, operation: str, arguments: dict[str, Any]) -> Any:
            raise ValueError("anything")

        with tempfile.TemporaryDirectory() as directory:
            endpoint = RunnerCapabilityEndpoint(
                role="protocol",
                socket_path=Path(directory) / "protocol.sock",
                token="protocol-token",
                dispatch=dispatch,
            )
            response = endpoint.handle(self._handoff_request("x-1"))
        self.assertEqual(response["error"]["code"], -32001)


class HandoffPreconditionDiagnosticTests(unittest.TestCase):
    """A precondition failure (not a stage no-match) surfaces as ``{ok: False, reason}``.

    Before this, every handoff precondition except stage-binding raised a plain
    AcceptanceContractError, which the broker collapsed into an opaque -32001;
    Protocol could not tell WHICH precondition failed.  Now each protocol-level
    precondition carries a stable ``reason`` that rides the same structured
    channel as ``stage_handoff_no_match``.
    """

    def test_missing_accepted_candidate_returns_structured_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory), task_id="precondition-test", acceptance_id="acceptance"
            )
            endpoint = carrier.capability_endpoint("protocol")
            token = carrier.capability_token("protocol")
            response = endpoint.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "pre-1",
                    "token": token,
                    "method": "tools/call",
                    "params": {
                        "name": "protocol_build_acceptance_stage_handoff",
                        "arguments": {
                            "protocol_id": "protocol",
                            "stage_calls": {
                                stage: {"tool": "t", "arguments": {}, "artifact_path": "p"}
                                for stage in ("dry-run", "apply", "readback")
                            },
                        },
                    },
                }
            )
        self.assertNotIn("error", response)
        structured = response["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertEqual(structured["error"]["reason"], "accepted_candidate_unavailable")


if __name__ == "__main__":
    unittest.main()
