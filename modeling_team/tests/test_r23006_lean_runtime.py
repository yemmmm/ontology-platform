from __future__ import annotations

import base64
import hashlib
import json
import socket
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from typing import Any
from unittest import mock

from modeling_team.acceptance_runtime import (
    ChildRuntimeError,
    ExaminerRunMetrics,
    ExaminerRuntimeBlocked,
    ExaminerTransport,
    ProxyCallReceipt,
    LeanExaminerRuntime,
    PLATFORM_PROXY_READ_TOOLS,
    ReportSinkServer,
    ScopedReadProxy,
    _packet_digest,
    aggregate_ordered_examiner_verdicts,
    build_platform_examiner_packet,
    build_source_examiner_packet,
    examiner_proxy_schemas,
    validate_examiner_proxy_arguments,
    _packet_canonical,
    _validate_platform_report_receipts,
)
from modeling_team.contracts import repository_root
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _CodexChildResource


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source_payload(ordinal: int = 1, count: int = 1) -> dict:
    source = b"approved source"
    manifest = [{"path": "source.md", "sha256": _digest(source)}]
    return {
        "question": "Which output is consumed?",
        "ordinal": ordinal,
        "count": count,
        "approved_sources": [{"path": "source.md", "sha256": _digest(source), "bytes": source}],
        "source_bundle_digest": hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "report_schema": {"type": "source-report"},
    }


def _source_evidence_id() -> str:
    return "source:" + _packet_digest(
        {"path": "source.md", "sha256": _digest(b"approved source")}
    )


def _platform_payload(ordinal: int = 1, count: int = 1) -> dict:
    exact = examiner_proxy_schemas(PLATFORM_PROXY_READ_TOOLS)
    return {
        "question": "Which output is consumed?",
        "ordinal": ordinal,
        "count": count,
        "ticket_binding": {"ticket_digest": "a" * 64},
        "model_state": {"model_revision": 1, "state_digest": "b" * 64},
        "platform_read_scope": {"project_id": "project-1", "ontology_id": "ontology-1"},
        "proxy_capability": {"capability_id": "proxy-1"},
        "allowed_read_tools": list(PLATFORM_PROXY_READ_TOOLS),
        "request_schema": exact,
        "report_schema": {"type": "platform-report"},
    }


def _platform_report() -> dict:
    return {
        "answerability": "answerable",
        "conclusion": "platform",
        "evidence": [],
        "coverage": {"queries_or_sections": [], "complete": True},
        "gaps": [],
        "evidence_refs": [
            {
                "ref_id": "platform-ref",
                "tool": "get_ontology_read_model",
                "request_digest": "a" * 64,
                "response_digest": "b" * 64,
                "artifact_path": "platform-read.json",
                "page": {
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            }
        ],
    }


def _complete_metrics(metrics: ExaminerRunMetrics, role: str) -> None:
    metrics.bind_thread(f"{role}-thread")
    metrics.observe_notification({
        "method": "thread/tokenUsage/updated",
        "params": {
            "threadId": f"{role}-thread",
            "turnId": f"{role}-turn",
            "tokenUsage": {"total": {
                "inputTokens": 10,
                "cachedInputTokens": 0,
                "cacheWriteInputTokens": 0,
                "outputTokens": 2,
                "reasoningOutputTokens": 0,
                "totalTokens": 12,
                "modelContextWindow": 1000,
            }},
        },
    })
    metrics.observe_notification({"method": "item/agentMessage/delta", "params": {"delta": "ok"}})
    metrics.observe_notification({"method": "turn/completed", "params": {}})


class R23006LeanRuntimeTests(unittest.TestCase):
    def test_packets_are_immutable_and_recomputable(self) -> None:
        packet = build_source_examiner_packet(**_source_payload())
        self.assertEqual(packet.schema_version, "ExaminerRolePacket/v1")
        self.assertEqual(packet.canonical_digest, packet.to_dict()["canonical_digest"])
        with self.assertRaises(TypeError):
            packet.payload["question"] = "history"  # type: ignore[index]
        self.assertIn("host_packet_tokens", packet.token_breakdown)

    def test_packet_token_accounting_excludes_source_bytes(self) -> None:
        payload = _source_payload()
        payload["approved_sources"] = [{"path": "source.md", "sha256": _digest(b"x" * 12000), "bytes": b"x" * 12000}]
        payload["source_bundle_digest"] = hashlib.sha256(
            json.dumps(
                [{"path": "source.md", "sha256": _digest(b"x" * 12000)}],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        packet = build_source_examiner_packet(**payload)
        self.assertGreater(packet.token_breakdown["source_bytes_tokens"], 2000)
        self.assertLess(packet.token_breakdown["host_packet_tokens"], 1000)
        self.assertEqual(packet.token_breakdown["task_tokens"], packet.token_breakdown["task_tokens"])

    def test_source_non_utf8_is_typed_source_missing(self) -> None:
        payload = _source_payload()
        invalid = b"\xff\xfe"
        digest = _digest(invalid)
        payload["approved_sources"] = [{"path": "source.md", "sha256": digest, "bytes": invalid}]
        payload["source_bundle_digest"] = _digest(
            json.dumps([{"path": "source.md", "sha256": digest}], sort_keys=True, separators=(",", ":")).encode()
        )
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            build_source_examiner_packet(**payload)
        self.assertEqual(blocked.exception.reason, "source-missing")

    def test_scoped_proxy_auto_injects_frozen_scope(self) -> None:
        # R2.3-009 (2026-08-21): live evidence showed the Examiner child never
        # receives ticket_digest/model_state_digest, so the proxy now injects
        # the frozen bindings itself and rejects only explicit contradictions.
        forwarded = []

        def forward(tool, arguments, read_key):
            forwarded.append((tool, dict(arguments)))
            return {"items": []}

        proxy = ScopedReadProxy(
            socket_path=Path("/tmp/r23006-test-proxy-inject.sock"),
            token="proxy-token",
            read_key="read-key",
            project_id="project-1",
            ontology_id="ontology-1",

            ticket_digest="a" * 64,
            model_state_digest="b" * 64,
            allowed_tools=list(PLATFORM_PROXY_READ_TOOLS),
            exact_schemas=examiner_proxy_schemas(PLATFORM_PROXY_READ_TOOLS),
            forward=forward,
        )
        bare = proxy.handle({
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {"query": "release"},
        })
        self.assertTrue(bare["ok"])
        self.assertEqual(proxy.backend_calls, 1)
        tool, arguments = forwarded[0]
        self.assertEqual(tool, "query_semantic_context")
        self.assertEqual(arguments["project_id"], "project-1")
        self.assertEqual(arguments["ontology_id"], "ontology-1")
        self.assertEqual(arguments["ticket_digest"], "a" * 64)
        self.assertEqual(arguments["model_state_digest"], "b" * 64)
        self.assertEqual(arguments["ontology_ids"], ["ontology-1"])
        self.assertEqual(arguments["scope_mode"], "ontologies")
        # An explicit contradiction still fails closed without a backend call.
        denied = proxy.handle({
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {"query": "release", "ontology_id": "foreign-ontology"},
        })
        self.assertEqual(denied["code"], "read-scope-denied")
        self.assertEqual(proxy.backend_calls, 1)
        # The compact projection parameter stays an accepted optional field.
        detail = proxy.handle({
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {"query": "release", "context_detail": "compact"},
        })
        self.assertTrue(detail["ok"])
        self.assertEqual(forwarded[1][1]["context_detail"], "compact")

    def test_exact_proxy_schema_rejects_extra_missing_wrong_type(self) -> None:
        schema = examiner_proxy_schemas(["query_semantic_context"])["query_semantic_context"]
        scope = {
            "project_id": "project-1", "ontology_id": "ontology-1",
            "ticket_digest": "a" * 64, "model_state_digest": "b" * 64,
        }
        valid = {**scope, "query": "release", "scope_mode": "ontologies", "ontology_ids": ["ontology-1"]}
        normalized = validate_examiner_proxy_arguments("query_semantic_context", valid, schema, scope=scope)
        self.assertEqual(normalized["query"], "release")
        self.assertEqual(normalized["resource_types"], ["fact", "instance", "relation", "rule"])
        self.assertEqual(normalized["depth"], 1)
        self.assertEqual(normalized["limit"], 10)
        self.assertEqual(normalized["context_limit"], 0)
        for changed in (
            {**valid, "extra": True},
            {key: value for key, value in valid.items() if key != "query"},
            {**valid, "depth": "10"},
            {**valid, "depth": 4},
            {**valid, "resource_types": ["unknown"]},
        ):
            with self.assertRaises(ChildRuntimeError):
                validate_examiner_proxy_arguments("query_semantic_context", changed, schema, scope=scope)

        for depth in (0, 2, 3):
            multiview = validate_examiner_proxy_arguments(
                "query_semantic_context",
                {**valid, "depth": depth, "semantic_roles": ["Mapping"], "resource_types": ["mapping"]},
                schema, scope=scope,
            )
            self.assertEqual(multiview["depth"], depth)
            self.assertEqual(multiview["semantic_roles"], ["Mapping"])

        nullable = examiner_proxy_schemas(["query_semantic_context"])["query_semantic_context"]
        nullable_valid = {**scope, "scope_mode": "ontologies", "ontology_ids": ["ontology-1"], "queries": ["a", "b"]}
        normalized_nullable = validate_examiner_proxy_arguments("query_semantic_context", nullable_valid, nullable, scope=scope)
        self.assertEqual(normalized_nullable["queries"], ["a", "b"])
        self.assertEqual(normalized_nullable["resource_types"], ["fact", "instance", "relation", "rule"])
        self.assertEqual(normalized_nullable["depth"], 1)
        self.assertEqual(normalized_nullable["limit"], 10)
        self.assertEqual(normalized_nullable["context_limit"], 0)
        with self.assertRaises(ChildRuntimeError):
            validate_examiner_proxy_arguments(
                "query_semantic_context",
                {**nullable_valid, "queries": {"bad": True}},
                nullable,
                scope=scope,
            )

        proxy = ScopedReadProxy(
            socket_path=Path("/tmp/r23006-test-proxy.sock"),
            token="proxy-token",
            read_key="read-key",
            project_id="project-1",
            ontology_id="ontology-1",

            ticket_digest="a" * 64,
            model_state_digest="b" * 64,
            allowed_tools=list(PLATFORM_PROXY_READ_TOOLS),
            exact_schemas=examiner_proxy_schemas(PLATFORM_PROXY_READ_TOOLS),
            forward=lambda _tool, _arguments, _key: {"items": []},
        )
        self.assertEqual(set(proxy.exact_schemas), set(PLATFORM_PROXY_READ_TOOLS))
        query_arguments = {
            **scope,
            "scope_mode": "ontologies",
            "ontology_ids": ["foreign-ontology"],
            "query": "release",
        }
        denied = proxy.handle({
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": query_arguments,
        })
        self.assertEqual(denied["code"], "read-scope-denied")
        self.assertEqual(proxy.backend_calls, 0)
        accepted = proxy.handle({
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {**query_arguments, "ontology_ids": ["ontology-1"]},
        })
        self.assertTrue(accepted["ok"])
        self.assertEqual(proxy.backend_calls, 1)
        self.assertEqual(accepted["call_ordinal"], 0)
        self.assertEqual(accepted["call_total"], 1)
        second = proxy.handle({
            "token": "proxy-token",
            "operation": "tools/call",
            "tool": "query_semantic_context",
            "arguments": {**query_arguments, "ontology_ids": ["ontology-1"]},
        })
        self.assertTrue(second["ok"])
        self.assertEqual(second["call_ordinal"], 1)
        self.assertEqual(second["call_total"], 2)
        self.assertEqual(len(proxy.receipt_snapshot), 2)

    def test_metrics_allow_one_continuation_turn_change(self) -> None:
        metrics = ExaminerRunMetrics("acceptance")
        metrics.bind_thread("thread-1")
        metrics.bind_first_turn_input([{"type": "text", "text": "packet"}])
        def usage(turn_id: str, total: int) -> dict:
            return {
                "method": "thread/tokenUsage/updated",
                "params": {"threadId": "thread-1", "turnId": turn_id, "tokenUsage": {"total": {
                    "inputTokens": total, "cachedInputTokens": 0, "cacheWriteInputTokens": 0,
                    "outputTokens": 1, "reasoningOutputTokens": 0, "totalTokens": total + 1,
                    "modelContextWindow": 1000,
                }}},
            }
        self.assertTrue(metrics.observe_notification(usage("turn-1", 10)))
        metrics.allow_continuation_turn()
        self.assertTrue(metrics.observe_notification(usage("turn-2", 20)))
        self.assertIsNone(metrics.blocked)
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            metrics.observe_notification(usage("turn-3", 30))
        self.assertEqual(blocked.exception.reason, "runtime-metrics")
        self.assertEqual(metrics.inference_steps, 2)

    def test_text_verdict_extraction_accepts_only_strict_verdict(self) -> None:
        valid = {
            "status": "FAIL",
            "answer": "no match found",
            "evidence_ref_ids": ["source:abc"],
            "current": True,
            "usable": False,
            "failure_layer": None,
            "blocked_reason": None,
        }
        class Agent:
            message_deltas = {"m1": ["my verdict: ", '{"status": "FAIL", "answer": "no match found", "evidence_ref_ids": ["source:abc"], "current": true, "usable": false, "failure_layer": null, "blocked_reason": null}']}

        extracted = CodexRuntimeAdapter._extract_verdict_from_text(Agent())
        self.assertEqual(extracted, valid)

        class EmptyAgent:
            message_deltas = {"m1": ["just reasoning, no verdict"]}

        self.assertIsNone(CodexRuntimeAdapter._extract_verdict_from_text(EmptyAgent()))

        class PartialAgent:
            message_deltas = {"m1": ['{"status": "PASS"}']}

        self.assertIsNone(CodexRuntimeAdapter._extract_verdict_from_text(PartialAgent()))

        class ExtraAgent:
            message_deltas = {"m1": ['{"status": "PASS", "answer": "x", "evidence_ref_ids": [], "current": true, "usable": true, "failure_layer": null, "blocked_reason": null, "extra": 1}']}

        self.assertEqual(
            CodexRuntimeAdapter._extract_verdict_from_text(ExtraAgent()),
            {
                "status": "PASS", "answer": "x", "evidence_ref_ids": [],
                "current": True, "usable": True,
                "failure_layer": None, "blocked_reason": None,
            },
        )

    def test_metrics_use_cumulative_increments_and_step_budget(self) -> None:
        metrics = ExaminerRunMetrics("platform")
        metrics.bind_thread("thread-1")
        metrics.bind_first_turn_input([{"type": "text", "text": "packet"}])
        def usage(total: int) -> dict:
            return {
                "method": "thread/tokenUsage/updated",
                "params": {"threadId": "thread-1", "turnId": "turn-1", "tokenUsage": {"total": {
                    "inputTokens": total, "cachedInputTokens": total // 2, "cacheWriteInputTokens": 0,
                    "outputTokens": total // 10, "reasoningOutputTokens": 0, "totalTokens": total + total // 10,
                    "modelContextWindow": 1000,
                }}},
            }
        self.assertFalse(metrics.observe_notification(usage(0)))
        self.assertTrue(metrics.observe_notification(usage(10)))
        self.assertFalse(metrics.observe_notification(usage(10)))
        self.assertTrue(metrics.observe_notification(usage(20)))
        self.assertTrue(metrics.observe_notification({"method": "item/agentMessage/delta", "params": {"delta": "x"}}) is False)
        self.assertEqual(metrics.as_dict()["first_input_tokens"], 10)
        self.assertEqual(metrics.as_dict()["inference_steps"], 2)
        self.assertIsNotNone(metrics.as_dict()["ttft_ms"])
        self.assertTrue(metrics.observe_notification(usage(30)))
        # Unified examiner guardrail (user 2026-08-20): every role caps at 30
        # inference steps, so the budget exhausts only after 30 increments.
        for total in range(40, 310, 10):
            self.assertTrue(metrics.observe_notification(usage(total)))
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            metrics.observe_notification(usage(310))
        self.assertEqual(blocked.exception.reason, "runtime-budget")
        metrics = ExaminerRunMetrics("platform")
        metrics.bind_thread("thread-1")
        for total in range(10, 310, 10):
            self.assertTrue(metrics.observe_notification(usage(total)))
        metrics.record_terminal_report({
            "answerability": "answerable", "conclusion": "ok", "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True}, "gaps": [],
            "evidence_refs": [{"location": "source.md"}],
        })
        self.assertIsNotNone(metrics.as_dict()["terminal_wall_ms"])
        self.assertTrue(metrics.observe_notification(usage(310)))
        self.assertIsNone(metrics.blocked)
        self.assertEqual(metrics.inference_steps, 30)
        snapshot = metrics.as_dict()
        increments = snapshot["token_usage_increments"]
        self.assertEqual(len(increments), 31)
        self.assertEqual(
            snapshot["total_tokens"],
            sum(row["totalTokens"] for row in increments),
        )

    def test_validated_report_is_metrics_terminal_without_provider_event(self) -> None:
        metrics = ExaminerRunMetrics("platform")
        metrics.bind_thread("thread-1")
        metrics.observe_notification({
            "method": "thread/tokenUsage/updated",
            "params": {"threadId": "thread-1", "turnId": "turn-1", "tokenUsage": {"total": {
                "inputTokens": 10, "cachedInputTokens": 0, "cacheWriteInputTokens": 0,
                "outputTokens": 2, "reasoningOutputTokens": 0, "totalTokens": 12,
                "modelContextWindow": 1000,
            }}},
        })
        metrics.observe_notification({"method": "item/agentMessage/delta", "params": {"delta": "x"}})
        snapshot = metrics.as_dict()
        self.assertFalse(snapshot["metrics_complete"])
        self.assertIsNone(snapshot["terminal_wall_ms"])
        metrics.record_terminal_report({
            "answerability": "answerable", "conclusion": "ok", "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True}, "gaps": [],
            "evidence_refs": [{"location": "source.md"}],
        })
        snapshot = metrics.as_dict()
        self.assertTrue(snapshot["metrics_complete"])
        self.assertIsNotNone(snapshot["terminal_wall_ms"])
        self.assertTrue(snapshot["terminal_report"])


    def test_transport_rejects_lateral_collaboration_with_receipt(self) -> None:
        transport = ExaminerTransport(owner_id="acceptance")
        receipt = transport.send(sender="source", recipient="platform", payload={"question": "q"})
        self.assertEqual(receipt.status, "rejected")
        self.assertEqual(receipt.reason, "collaboration/routing")
        self.assertEqual(len(transport.receipts), 1)

    def test_ordered_positive_n_and_fresh_acceptance(self) -> None:
        for count in (1, 2, 3, 5):
            calls = {"source": [], "platform": [], "acceptance": []}

            def source(packet, metrics):
                metrics.bind_thread(f"source-{packet.payload['ordinal']}")
                calls["source"].append(packet.payload["ordinal"])
                return {"answerability": "answerable", "conclusion": "source", "evidence": [], "coverage": {"queries_or_sections": [], "complete": True}, "gaps": [], "evidence_refs": [{"location": "source.md"}]}

            def platform(packet, metrics):
                metrics.bind_thread(f"platform-{packet.payload['ordinal']}")
                calls["platform"].append(packet.payload["ordinal"])
                return _platform_report()

            def acceptance(packet, metrics):
                metrics.bind_thread(f"acceptance-{packet.payload['ordinal']}")
                calls["acceptance"].append(packet.payload["ordinal"])
                evidence_ids = list(packet.payload["source_evidence_ref_ids"]) + list(packet.payload["platform_evidence_ref_ids"])
                return {"status": "PASS", "answer": "ok", "evidence_ref_ids": evidence_ids, "current": True, "usable": True, "failure_layer": None, "blocked_reason": None}

            runtime = LeanExaminerRuntime(source_executor=source, platform_executor=platform, acceptance_executor=acceptance)
            result = runtime.run(
                [{"question": f"q-{i}"} for i in range(count)],
                source_packets=[_source_payload(1, count) for _ in range(count)],
                platform_packets=[_platform_payload(1, count) for _ in range(count)],
                ticket_binding={"ticket_digest": "a" * 64},
                verdict_schema={"type": "verdict"},
            )
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["complete"])
            self.assertEqual(calls["source"], list(range(1, count + 1)))
            self.assertEqual(calls["acceptance"], list(range(1, count + 1)))

    def test_prior_nonpass_stops_next_cq(self) -> None:
        calls = []

        def source(packet, metrics):
            metrics.bind_thread(f"source-{packet.payload['ordinal']}")
            return {"answerability": "answerable", "conclusion": "source", "evidence": [], "coverage": {"queries_or_sections": [], "complete": True}, "gaps": [], "evidence_refs": [{"location": "source.md"}]}

        def platform(packet, metrics):
            metrics.bind_thread(f"platform-{packet.payload['ordinal']}")
            return _platform_report()

        def acceptance(packet, metrics):
            metrics.bind_thread(f"acceptance-{packet.payload['ordinal']}")
            calls.append(packet.payload["ordinal"])
            evidence_ids = list(packet.payload["source_evidence_ref_ids"]) + list(packet.payload["platform_evidence_ref_ids"])
            return {"status": "FAIL", "answer": "not current", "evidence_ref_ids": evidence_ids, "current": False, "usable": False, "failure_layer": "modeling-quality", "blocked_reason": None}

        runtime = LeanExaminerRuntime(source_executor=source, platform_executor=platform, acceptance_executor=acceptance)
        result = runtime.run(
            [{"question": "q1"}, {"question": "q2"}],
            source_packets=[_source_payload(1, 2), _source_payload(1, 2)],
            platform_packets=[_platform_payload(1, 2), _platform_payload(1, 2)],
            ticket_binding={"ticket_digest": "a" * 64}, verdict_schema={"type": "verdict"},
        )
        self.assertEqual(calls, [1])
        self.assertFalse(result["complete"])
        self.assertEqual(result["stopped_at"], 1)

    def test_platform_only_stage_skips_source_and_acceptance(self) -> None:
        source_calls = {"count": 0}
        acceptance_calls = {"count": 0}

        def source(packet, metrics):
            source_calls["count"] += 1
            metrics.bind_thread(f"source-{packet.payload['ordinal']}")
            return {"answerability": "answerable", "conclusion": "source", "evidence": [], "coverage": {"queries_or_sections": [], "complete": True}, "gaps": [], "evidence_refs": [{"location": "source.md"}]}

        def platform(packet, metrics):
            metrics.bind_thread(f"platform-{packet.payload['ordinal']}")
            return _platform_report()

        def acceptance(packet, metrics):
            acceptance_calls["count"] += 1
            metrics.bind_thread(f"acceptance-{packet.payload['ordinal']}")
            return {}

        runtime = LeanExaminerRuntime(source_executor=source, platform_executor=platform, acceptance_executor=acceptance)
        result = runtime.run(
            [{"question": "q1"}],
            source_packets=[_source_payload()],
            platform_packets=[_platform_payload()],
            ticket_binding={"ticket_digest": "a" * 64}, verdict_schema={"type": "verdict"},
            stage="platform",
        )
        self.assertEqual(source_calls["count"], 0)
        self.assertEqual(acceptance_calls["count"], 0)
        self.assertEqual(result["status"], "PLATFORM-ONLY")
        self.assertIn("platform_report", result)
        self.assertEqual([row["role"] for row in result["metrics"]], ["source", "platform"])

    def test_failure_metrics_capture_source_stage_and_are_copied(self) -> None:
        def source(_packet, _metrics):
            raise ExaminerRuntimeBlocked(
                "runtime-infrastructure",
                role="source",
                evidence={"failure_category": "runtime", "reason_code": "child-timeout"},
            )

        runtime = LeanExaminerRuntime(
            source_executor=source,
            platform_executor=lambda _packet, _metrics: _platform_report(),
            acceptance_executor=lambda _packet, _metrics: {},
        )
        with self.assertRaises(ExaminerRuntimeBlocked):
            runtime.run(
                [{"question": "q1"}],
                source_packets=[_source_payload()],
                platform_packets=[_platform_payload()],
                ticket_binding={"ticket_digest": "a" * 64},
                verdict_schema={"type": "verdict"},
            )
        snapshots = runtime.failure_metrics
        self.assertEqual([row["role"] for row in snapshots], ["source"])
        self.assertFalse(snapshots[0]["metrics_complete"])
        self.assertIsNotNone(snapshots[0]["blocked"])
        snapshots[0]["role"] = "tampered"
        self.assertEqual(runtime.failure_metrics[0]["role"], "source")
        self.assertNotIn("report", snapshots[0])

    def test_platform_executor_is_retried_once_on_stop_generation(self) -> None:
        attempts = {"count": 0}

        def source(_packet, metrics):
            _complete_metrics(metrics, "source")
            return {
                "answerability": "answerable", "conclusion": "source", "evidence": [],
                "coverage": {"queries_or_sections": [], "complete": True}, "gaps": [],
                "evidence_refs": [{"location": "source.md"}],
            }

        def platform(_packet, metrics):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ExaminerRuntimeBlocked(
                    "runtime-infrastructure",
                    role="platform",
                    evidence={"failure_category": "runtime", "reason_code": "child-timeout"},
                )
            _complete_metrics(metrics, "platform")
            return _platform_report()

        def acceptance(_packet, metrics):
            _complete_metrics(metrics, "acceptance")
            return {
                "status": "FAIL", "answer": "no match",
                "evidence_ref_ids": [_source_evidence_id()],
                "current": True, "usable": False, "failure_layer": None, "blocked_reason": None,
            }

        runtime = LeanExaminerRuntime(
            source_executor=source,
            platform_executor=platform,
            acceptance_executor=acceptance,
            platform_retry_limit=1,
        )
        result = runtime.run(
            [{"question": "q1"}],
            source_packets=[_source_payload()],
            platform_packets=[_platform_payload()],
            ticket_binding={"ticket_digest": "a" * 64},
            verdict_schema={"type": "verdict"},
        )
        self.assertEqual(attempts["count"], 2)
        self.assertEqual(result["status"], "FAIL")

    def test_failure_metrics_capture_source_and_incomplete_platform(self) -> None:
        def source(_packet, metrics):
            _complete_metrics(metrics, "source")
            return {
                "answerability": "answerable", "conclusion": "source", "evidence": [],
                "coverage": {"queries_or_sections": [], "complete": True}, "gaps": [],
                "evidence_refs": [{"location": "source.md"}],
            }

        def platform(_packet, metrics):
            metrics.bind_thread("platform-thread")
            raise ExaminerRuntimeBlocked(
                "runtime-infrastructure",
                role="platform",
                evidence={
                    "failure_category": "runtime",
                    "reason_code": "child-timeout",
                    "report_received": True,
                    "terminal_event": False,
                    "proxy_receipt_count": 2,
                },
            )

        runtime = LeanExaminerRuntime(
            source_executor=source,
            platform_executor=platform,
            acceptance_executor=lambda _packet, _metrics: {},
        )
        with self.assertRaises(ExaminerRuntimeBlocked):
            runtime.run(
                [{"question": "q1"}],
                source_packets=[_source_payload()],
                platform_packets=[_platform_payload()],
                ticket_binding={"ticket_digest": "a" * 64},
                verdict_schema={"type": "verdict"},
            )
        snapshots = runtime.failure_metrics
        self.assertEqual([row["role"] for row in snapshots], ["source", "platform"])
        self.assertTrue(snapshots[0]["metrics_complete"])
        self.assertTrue(snapshots[0]["terminal_report"])
        self.assertFalse(snapshots[1]["metrics_complete"])
        self.assertFalse(snapshots[1]["terminal_report"])
        self.assertEqual(snapshots[1]["blocked"]["evidence"]["proxy_receipt_count"], 2)

    def test_failure_metrics_capture_acceptance_stage_after_completed_source_platform(self) -> None:
        def source(_packet, metrics):
            _complete_metrics(metrics, "source")
            return {
                "answerability": "answerable", "conclusion": "source", "evidence": [],
                "coverage": {"queries_or_sections": [], "complete": True}, "gaps": [],
                "evidence_refs": [{"location": "source.md"}],
            }

        def platform(_packet, metrics):
            _complete_metrics(metrics, "platform")
            return _platform_report()

        def acceptance(_packet, metrics):
            metrics.bind_thread("acceptance-thread")
            raise ExaminerRuntimeBlocked(
                "runtime-infrastructure", role="acceptance",
                evidence={"failure_category": "runtime", "reason_code": "child-timeout"},
            )

        runtime = LeanExaminerRuntime(
            source_executor=source,
            platform_executor=platform,
            acceptance_executor=acceptance,
        )
        with self.assertRaises(ExaminerRuntimeBlocked):
            runtime.run(
                [{"question": "q1"}],
                source_packets=[_source_payload()],
                platform_packets=[_platform_payload()],
                ticket_binding={"ticket_digest": "a" * 64},
                verdict_schema={"type": "verdict"},
            )
        snapshots = runtime.failure_metrics
        self.assertEqual([row["role"] for row in snapshots], ["source", "platform", "acceptance"])
        self.assertTrue(all(row["metrics_complete"] for row in snapshots[:2]))
        self.assertFalse(snapshots[2]["metrics_complete"])

    def test_aggregate_rejects_received_out_of_order_rows(self) -> None:
        rows = [
            {"question_ordinal": 2, "question_count": 2, "previous_question_ordinal": 1, "next_question_ordinal": None, "final": True, "status": "PASS"},
            {"question_ordinal": 1, "question_count": 2, "previous_question_ordinal": None, "next_question_ordinal": 2, "final": False, "status": "PASS"},
        ]
        with self.assertRaises(ChildRuntimeError):
            aggregate_ordered_examiner_verdicts(rows, count=2)

    def test_codex_spec_binds_private_input_metrics_and_platform_scope(self) -> None:
        captured = {}

        class Resource:
            destroyed = False

            def destroy(self):
                self.destroyed = True
                shutil.rmtree(captured["private_root"], ignore_errors=True)

        def factory(spec):
            captured.update(spec)
            captured["private_root"] = spec["private_root"]
            return Resource()

        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False, acceptance_child_factory=factory)
        packet = build_platform_examiner_packet(**_platform_payload())
        metrics = ExaminerRunMetrics("platform")
        resource = adapter.launch_lean_examiner_child(
            packet,
            metrics,
            read_key="temporary-key",
            platform_forwarder=lambda _tool, _arguments, _key: {},
        )
        self.assertIs(captured["_metrics"], metrics)
        self.assertEqual(captured["ticket_digest"], "a" * 64)
        self.assertEqual(captured["allowed_read_tools"], list(PLATFORM_PROXY_READ_TOOLS))
        self.assertEqual(
            Path(captured["private_input"]).read_bytes(),
            _packet_canonical(packet.to_dict()["payload"]),
        )
        self.assertIs(resource.destroyed, False)
        resource.destroy()
        self.assertTrue(resource.destroyed)
        self.assertFalse(Path(captured["private_root"]).exists())

    def test_platform_launch_requires_ticket_bound_forwarder_before_child(self) -> None:
        calls = []
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        packet = build_platform_examiner_packet(**_platform_payload())
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            adapter.launch_lean_examiner_child(
                packet,
                ExaminerRunMetrics("platform"),
                read_key="temporary-key",
                platform_forwarder=None,
            )
        self.assertEqual(blocked.exception.reason, "acceptance-input")
        self.assertEqual(calls, [])

    def test_codex_first_turn_contains_current_immutable_packet(self) -> None:
        captured = {}

        class Resource:
            destroyed = False

            def destroy(self):
                self.destroyed = True
                shutil.rmtree(captured["private_root"], ignore_errors=True)

        def factory(spec):
            captured.update(spec)
            captured["private_root"] = spec["private_root"]
            return Resource()

        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False, acceptance_child_factory=factory)
        packet = build_source_examiner_packet(**_source_payload())
        resource = adapter.launch_lean_examiner_child(packet, ExaminerRunMetrics("source"))
        text = captured["first_turn_input"][0]["text"]
        serialized_packet = _packet_canonical(packet.to_dict()["payload"]).decode("utf-8")
        self.assertIn(serialized_packet, text)
        self.assertIn(packet.canonical_digest, text)
        self.assertIn(base64.b64encode(b"approved source").decode("ascii"), text)
        self.assertIn('SOURCE_TEXT_JSON=[{"path":"source.md","sha256":"', text)
        self.assertIn('"text":"approved source"', text)
        self.assertNotIn("Team Transport", text)
        self.assertNotIn("prior", text)
        self.assertNotIn("previous", text)
        resource.destroy()

    def test_examiner_prompts_require_inline_packet_without_filesystem_read(self) -> None:
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        expected = {
            "source": ("PACKET_JSON", "SOURCE_TEXT_JSON", "location-only"),
            "platform": ("PACKET_JSON",),
            "acceptance": ("PACKET_JSON",),
        }
        for kind, markers in expected.items():
            _, instructions, skill = adapter._child_package_assets(kind, repository_root())
            prompt = instructions.read_text(encoding="utf-8") + skill.read_text(encoding="utf-8")
            for marker in markers:
                self.assertIn(marker, prompt)
            self.assertNotIn("/agent/home/input.json", prompt)
            self.assertNotIn("staged in your private home", prompt)

    def test_platform_examiner_prompt_requires_iterative_semantic_querying(self) -> None:
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        _, instructions, skill = adapter._child_package_assets("platform", repository_root())
        prompt = " ".join(
            (instructions.read_text(encoding="utf-8") + skill.read_text(encoding="utf-8")).split()
        )
        for marker in (
            "query_semantic_context",
            "generic semantic query",
            "Query iteratively",
            "querying iteratively",
            "decide the next query",
            "returned information",
            "follow the returned matches",
            "Follow returned cursors",
            "no single-wave limit",
            "Do not guess facts",
            "Keep each query kind-focused",
            'resource_types: ["fact"]',
            "property name alone",
            "context_limit",
            "data.object",
            "proxy applies small defaults",
            "Exact navigation",
            "exact-anchor mode",
            "Prefer 2-3",
            "no more than 10 successful proxy calls",
            "yields exactly one",
            "receipt-count-mismatch",
            "p<call_ordinal>",
            "contiguous and complete",
            "page-sequence-invalid",
            "submit_examiner_report",
            "writing the report in your reply text is not a submission",
            "explicit unknown",
            "explicit gap",
            "distinguish",
            "not modeled",
            "do not use raw platform sockets",
        ):
            self.assertIn(marker, prompt)
        self.assertNotIn("one parallel assistant tool-call wave", prompt)
        self.assertNotIn("no more than 6 successful proxy calls", prompt)
        self.assertNotIn("each allowed tool at most once", prompt)
        self.assertNotIn("Do not start another retrieval wave", prompt)

    def test_lean_stdout_pump_does_not_leak_agent_messages(self) -> None:
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        resource = _CodexChildResource({"lean_examiner": True})
        metrics = ExaminerRunMetrics("source")
        resource.metrics = metrics

        class Agent:
            io_lock = threading.RLock()
            runtime_failure = None
            message_deltas = {}

        agent = Agent()
        events = [
            {"method": "item/agentMessage/delta", "params": {"delta": "answer"}},
            {"method": "item/agentMessage/completed", "params": {}},
            {"method": "item/completed", "params": {"item": {"id": "msg-1", "type": "agentMessage", "text": "answer"}}},
            {"method": "item/completed", "params": {"item": {"id": "mcp-1", "type": "mcpToolCall", "status": "completed"}}},
            {"method": "turn/completed", "params": {}},
        ]

        def read_output(_agent, _timeout):
            if events:
                return json.dumps(events.pop(0))
            resource._pump_stop.set()
            return None

        adapter._read_output_line = read_output  # type: ignore[method-assign]
        adapter._notification = mock.Mock()
        resource._adapter = adapter
        resource._child_agent = agent
        resource._run_stdout_pump()

        notified_methods = [call.args[1]["method"] for call in adapter._notification.call_args_list]
        self.assertEqual(notified_methods, ["item/completed", "turn/completed"])
        self.assertEqual(adapter._messages, [])
        self.assertEqual(adapter.receive_messages(), [])
        self.assertTrue(resource.terminal_event)

    def test_codex_executor_waits_for_terminal_event_after_report(self) -> None:
        report = {
            "answerability": "answerable",
            "conclusion": "source",
            "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True},
            "gaps": [],
            "evidence_refs": [{"location": "source.md"}],
        }

        class Resource:
            def __init__(self):
                self.submitted_reports = [report]
                self.blocked = None
                self.terminal_event = False
                self.destroyed = False
                self.process = None

            def failure_evidence(self):
                return None

            def destroy(self):
                self.destroyed = True

        resource = Resource()
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        adapter.launch_lean_examiner_child = mock.Mock(return_value=resource)
        metrics = ExaminerRunMetrics("source")

        def complete_later():
            time.sleep(0.05)
            metrics.observe_notification({
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "source-thread",
                    "turnId": "source-turn",
                    "tokenUsage": {"total": {
                        "inputTokens": 10, "cachedInputTokens": 0,
                        "cacheWriteInputTokens": 0, "outputTokens": 2,
                        "reasoningOutputTokens": 0, "totalTokens": 12,
                        "modelContextWindow": 1000,
                    }},
                },
            })
            metrics.observe_notification({"method": "item/agentMessage/delta", "params": {"delta": "ok"}})
            metrics.observe_notification({"method": "turn/completed", "params": {}})
            resource.terminal_event = metrics.terminal_event

        completion = threading.Thread(target=complete_later, daemon=True)
        completion.start()
        started = time.monotonic()
        result = adapter.run_lean_examiner_child(packet=build_source_examiner_packet(**_source_payload()), metrics=metrics, timeout_seconds=1)
        elapsed = time.monotonic() - started
        completion.join(timeout=1)
        self.assertEqual(result, report)
        # A short accounting grace captures late tokenUsage without waiting for
        # the provider's terminal event (which may never arrive).
        self.assertLess(elapsed, 0.16)
        self.assertEqual(metrics.as_dict()["inference_steps"], 1)
        self.assertEqual(metrics.as_dict()["total_tokens"], 12)
        self.assertTrue(resource.destroyed)

    def test_codex_executor_report_and_budget_block_prefers_blocked(self) -> None:
        report = {
            "answerability": "answerable",
            "conclusion": "source",
            "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True},
            "gaps": [],
            "evidence_refs": [{"location": "source.md"}],
        }

        class Resource:
            submitted_reports = [report]
            blocked = ExaminerRuntimeBlocked("runtime-budget", role="source")
            terminal_event = False
            process = None
            destroyed = False

            def failure_evidence(self):
                return None

            def destroy(self):
                self.destroyed = True

        resource = Resource()
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        adapter.launch_lean_examiner_child = mock.Mock(return_value=resource)
        metrics = ExaminerRunMetrics("source")
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            adapter.run_lean_examiner_child(
                packet=build_source_examiner_packet(**_source_payload()),
                metrics=metrics,
                timeout_seconds=1,
            )
        self.assertEqual(blocked.exception.reason, "runtime-budget")
        self.assertFalse(metrics.terminal_report)
        self.assertTrue(resource.destroyed)

    def test_codex_executor_failure_diagnostics_are_mechanical_and_destroy(self) -> None:
        packet = build_source_examiner_packet(**_source_payload())

        class Proxy:
            def __init__(self, receipts):
                self.receipts = receipts

            @property
            def receipt_snapshot(self):
                if self.receipts is None:
                    raise RuntimeError("receipt unavailable")
                return self.receipts

        class Resource:
            def __init__(self, reports, terminal, receipts):
                self.submitted_reports = reports
                self.terminal_event = terminal
                self.proxy = Proxy(receipts)
                self.blocked = None
                self.process = None
                self.destroyed = False

            def failure_evidence(self):
                return {"failure_category": "runtime", "reason_code": "child-timeout"}

            def destroy(self):
                self.destroyed = True

        cases = (
            ([{"unvalidated": "report"}], False, (object(), object()), True, False, 2),
            ([], False, None, False, False, 0),
        )
        for reports, terminal, receipts, report_received, terminal_event, receipt_count in cases:
            with self.subTest(report_received=report_received, receipt_count=receipt_count):
                resource = Resource(reports, terminal, receipts)
                adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
                adapter.launch_lean_examiner_child = mock.Mock(return_value=resource)
                with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
                    adapter.run_lean_examiner_child(packet, ExaminerRunMetrics("source"), timeout_seconds=1)
                self.assertEqual(
                    blocked.exception.evidence,
                    {
                        "failure_category": "runtime",
                        "reason_code": "child-timeout",
                        "report_received": report_received,
                        "terminal_event": terminal_event,
                        "proxy_receipt_count": receipt_count,
                    },
                )
                self.assertTrue(resource.destroyed)

    def test_codex_executor_failure_wins_report_race_before_validation(self) -> None:
        report = {
            "answerability": "answerable",
            "conclusion": "source",
            "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True},
            "gaps": [],
            "evidence_refs": [{"location": "not-approved.md"}],
        }

        class Resource:
            submitted_reports = [report]
            terminal_event = True
            proxy = SimpleNamespace(receipt_snapshot=(object(),))
            blocked = None
            process = None
            destroyed = False

            def failure_evidence(self):
                return {"failure_category": "runtime", "reason_code": "child-timeout"}

            def destroy(self):
                self.destroyed = True

        resource = Resource()
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        adapter.launch_lean_examiner_child = mock.Mock(return_value=resource)
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            adapter.run_lean_examiner_child(packet=build_source_examiner_packet(**_source_payload()), metrics=ExaminerRunMetrics("source"), timeout_seconds=1)
        self.assertEqual(blocked.exception.reason, "runtime-infrastructure")
        self.assertEqual(blocked.exception.evidence["report_received"], True)
        self.assertTrue(resource.destroyed)

    def test_codex_executor_sends_one_mechanical_continuation_when_turn_ends_without_report(self) -> None:
        report = {
            "answerability": "answerable",
            "conclusion": "platform",
            "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True},
            "gaps": [],
            "evidence_refs": [{
                "ref_id": "p0",
                "tool": "get_ontology_read_model",
                "request_digest": "c" * 64,
                "response_digest": "d" * 64,
                "artifact_path": "acceptance/r23006/platform-read/child/0.json",
                "page": {
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            }],
        }

        class Agent:
            thread_id = "thread-1"
            active_turn_id = "turn-1"

        class Resource:
            terminal_event = True
            submitted_reports = []
            proxy = SimpleNamespace(receipt_snapshot=(
                SimpleNamespace(
                    ordinal=0,
                    tool="get_ontology_read_model",
                    request_digest="c" * 64,
                    response_digest="d" * 64,
                    artifact_path="acceptance/r23006/platform-read/child/0.json",
                ),
            ))
            blocked = None
            process = None
            destroyed = False
            _continuation_count = 0
            _child_agent = Agent()
            continuation_calls = 0

            def failure_evidence(self):
                return None

            def destroy(self):
                self.destroyed = True

        resource = Resource()
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        adapter.launch_lean_examiner_child = mock.Mock(return_value=resource)

        def fake_rpc(agent, method, params):
            if method in ("turn/start", "turn/steer"):
                resource.continuation_calls += 1
                resource.submitted_reports.append(report)
                resource.terminal_event = True
                return {"id": "turn-2"}
            raise AssertionError(f"unexpected rpc {method}")

        adapter._rpc = fake_rpc
        result = adapter.run_lean_examiner_child(
            packet=build_platform_examiner_packet(**_platform_payload()),
            metrics=ExaminerRunMetrics("platform"),
            read_key="temporary-key",
            platform_forwarder=lambda _tool, _arguments, _key: {},
            timeout_seconds=1,
        )
        self.assertEqual(result, report)
        self.assertEqual(resource.continuation_calls, 1)
        self.assertEqual(resource._continuation_count, 1)
        self.assertTrue(resource.destroyed)

    def test_codex_executor_rejects_unapproved_source_locator_and_destroys(self) -> None:
        report = {
            "answerability": "answerable",
            "conclusion": "source",
            "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True},
            "gaps": [],
            "evidence_refs": [{"location": "not-approved.md#section"}],
        }

        class Resource:
            submitted_reports = [report]
            blocked = None
            terminal_event = True
            process = None
            destroyed = False

            def failure_evidence(self):
                return None

            def destroy(self):
                self.destroyed = True

        resource = Resource()
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        adapter.launch_lean_examiner_child = mock.Mock(return_value=resource)
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            adapter.run_lean_examiner_child(
                packet=build_source_examiner_packet(**_source_payload()),
                metrics=ExaminerRunMetrics("source"),
                timeout_seconds=1,
            )
        self.assertEqual(blocked.exception.reason, "acceptance-evidence")
        self.assertTrue(resource.destroyed)

        duplicate = dict(report)
        duplicate["evidence_refs"] = [
            {"location": "source.md#one"},
            {"location": "source.md#two"},
        ]
        duplicate_resource = Resource()
        duplicate_resource.submitted_reports = [duplicate]
        adapter.launch_lean_examiner_child = mock.Mock(return_value=duplicate_resource)
        with self.assertRaises(ExaminerRuntimeBlocked) as duplicate_blocked:
            adapter.run_lean_examiner_child(
                packet=build_source_examiner_packet(**_source_payload()),
                metrics=ExaminerRunMetrics("source"),
                timeout_seconds=1,
            )
        self.assertEqual(duplicate_blocked.exception.reason, "acceptance-evidence")
        self.assertTrue(duplicate_resource.destroyed)

    def test_codex_executor_binds_platform_locator_to_current_proxy_receipt(self) -> None:
        packet = build_platform_examiner_packet(**_platform_payload())
        receipt = ProxyCallReceipt(
            ordinal=0,
            project_id="project-1",
            ontology_id="ontology-1",

            ticket_digest="a" * 64,
            model_state_digest="b" * 64,
            tool="get_ontology_read_model",
            request_digest="c" * 64,
            response_digest="d" * 64,
            artifact_path="acceptance/r23006/platform-read/child/0.json",
        )
        report = {
            "answerability": "answerable",
            "conclusion": "platform",
            "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True},
            "gaps": [],
            "evidence_refs": [{
                "ref_id": "platform-ref",
                "tool": receipt.tool,
                "request_digest": receipt.request_digest,
                "response_digest": receipt.response_digest,
                "artifact_path": receipt.artifact_path,
                "page": {
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            }],
        }

        class Resource:
            def __init__(self, current_report, receipts=(receipt,)):
                self.submitted_reports = [current_report]
                self.proxy = SimpleNamespace(receipt_snapshot=tuple(receipts))
                self.blocked = None
                self.terminal_event = True
                self.process = None
                self.destroyed = False

            def failure_evidence(self):
                return None

            def destroy(self):
                self.destroyed = True

        resource = Resource(report)
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        adapter.launch_lean_examiner_child = mock.Mock(return_value=resource)
        result = adapter.run_lean_examiner_child(
            packet=packet,
            metrics=ExaminerRunMetrics("platform"),
            read_key="temporary-key",
            platform_forwarder=lambda _tool, _arguments, _key: {},
            timeout_seconds=1,
        )
        self.assertEqual(result, report)
        self.assertTrue(resource.destroyed)

        receipt_two = replace(
            receipt,
            ordinal=1,
            tool=receipt.tool,
            request_digest="e" * 64,
            response_digest="f" * 64,
            artifact_path="acceptance/r23006/platform-read/child/1.json",
        )
        report_two = dict(report)
        report_two["evidence_refs"] = [
            dict(report["evidence_refs"][0], page={
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": "cursor-1",
                "has_more": True,
                "sequence_complete": False,
            }),
            {
                "ref_id": "platform-ref-2",
                "tool": receipt_two.tool,
                "request_digest": receipt_two.request_digest,
                "response_digest": receipt_two.response_digest,
                "artifact_path": receipt_two.artifact_path,
                "page": {
                    "ordinal": 1,
                    "input_cursor": "cursor-1",
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            },
        ]
        resource_two = Resource(report_two, (receipt, receipt_two))
        adapter.launch_lean_examiner_child = mock.Mock(return_value=resource_two)
        self.assertEqual(
            adapter.run_lean_examiner_child(
                packet=packet,
                metrics=ExaminerRunMetrics("platform"),
                read_key="temporary-key",
                platform_forwarder=lambda _tool, _arguments, _key: {},
                timeout_seconds=1,
            ),
            report_two,
        )
        self.assertTrue(resource_two.destroyed)

        independent_report = dict(report)
        independent_report["evidence_refs"] = [
            dict(report["evidence_refs"][0]),
            {
                "ref_id": "platform-ref-independent",
                "tool": "get_semantic_read_model",
                "request_digest": "e" * 64,
                "response_digest": "f" * 64,
                "artifact_path": "acceptance/r23006/platform-read/child/1.json",
                "page": {
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            },
        ]
        independent_resource = Resource(
            independent_report,
            (
                receipt,
                replace(
                    receipt_two,
                    tool="get_semantic_read_model",
                ),
            ),
        )
        adapter.launch_lean_examiner_child = mock.Mock(return_value=independent_resource)
        self.assertEqual(
            adapter.run_lean_examiner_child(
                packet=packet,
                metrics=ExaminerRunMetrics("platform"),
                read_key="temporary-key",
                platform_forwarder=lambda _tool, _arguments, _key: {},
                timeout_seconds=1,
            ),
            independent_report,
        )
        self.assertTrue(independent_resource.destroyed)

        same_tool_single_receipt = replace(
            receipt_two,
            request_digest="g" * 64,
            response_digest="h" * 64,
            artifact_path="acceptance/r23006/platform-read/child/2.json",
        )
        same_tool_single = dict(report)
        same_tool_single["evidence_refs"] = [
            dict(report["evidence_refs"][0]),
            {
                "ref_id": "platform-ref-same-tool-single",
                "tool": same_tool_single_receipt.tool,
                "request_digest": same_tool_single_receipt.request_digest,
                "response_digest": same_tool_single_receipt.response_digest,
                "artifact_path": same_tool_single_receipt.artifact_path,
                "page": {
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            },
        ]
        same_tool_single_resource = Resource(
            same_tool_single,
            (receipt, same_tool_single_receipt),
        )
        adapter.launch_lean_examiner_child = mock.Mock(return_value=same_tool_single_resource)
        self.assertEqual(
            adapter.run_lean_examiner_child(
                packet=packet,
                metrics=ExaminerRunMetrics("platform"),
                read_key="temporary-key",
                platform_forwarder=lambda _tool, _arguments, _key: {},
                timeout_seconds=1,
            ),
            same_tool_single,
        )
        self.assertTrue(same_tool_single_resource.destroyed)

        def reject_report(current_report, current_receipts):
            rejected_resource = Resource(current_report, current_receipts)
            adapter.launch_lean_examiner_child = mock.Mock(return_value=rejected_resource)
            with self.assertRaises(ExaminerRuntimeBlocked) as rejected:
                adapter.run_lean_examiner_child(
                    packet=packet,
                    metrics=ExaminerRunMetrics("platform"),
                    read_key="temporary-key",
                    platform_forwarder=lambda _tool, _arguments, _key: {},
                    timeout_seconds=1,
                )
            self.assertEqual(rejected.exception.reason, "acceptance-evidence")
            self.assertTrue(rejected_resource.destroyed)

        cross_tool_continuation = dict(independent_report)
        cross_tool_continuation["evidence_refs"] = [
            dict(independent_report["evidence_refs"][0], page={
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": "cross-cursor",
                "has_more": True,
                "sequence_complete": False,
            }),
            dict(same_tool_single["evidence_refs"][1], page={
                "ordinal": 1,
                "input_cursor": "cross-cursor",
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            }),
        ]
        reject_report(cross_tool_continuation, (receipt, replace(same_tool_single_receipt, tool="get_semantic_read_model")))

        reordered = dict(report_two)
        reordered["evidence_refs"] = list(reversed(report_two["evidence_refs"]))
        reject_report(reordered, (receipt, receipt_two))

        missing_terminal_page = dict(report)
        missing_terminal_page["evidence_refs"] = [dict(report["evidence_refs"][0], page={
            "ordinal": 0,
            "input_cursor": None,
            "output_cursor": "missing-next",
            "has_more": True,
            "sequence_complete": False,
        })]
        reject_report(missing_terminal_page, (receipt,))

        broken_chain = dict(report_two)
        broken_chain["evidence_refs"] = [
            dict(report_two["evidence_refs"][0]),
            dict(report_two["evidence_refs"][1], page={
                **report_two["evidence_refs"][1]["page"],
                "input_cursor": "wrong-cursor",
            }),
        ]
        broken_resource = Resource(broken_chain, (receipt, receipt_two))
        adapter.launch_lean_examiner_child = mock.Mock(return_value=broken_resource)
        with self.assertRaises(ExaminerRuntimeBlocked) as chain_blocked:
            adapter.run_lean_examiner_child(
                packet=packet,
                metrics=ExaminerRunMetrics("platform"),
                read_key="temporary-key",
                platform_forwarder=lambda _tool, _arguments, _key: {},
                timeout_seconds=1,
            )
        self.assertEqual(chain_blocked.exception.reason, "acceptance-evidence")
        self.assertTrue(broken_resource.destroyed)

        # A hand-copied digest drift is repaired, not rejected: the binding
        # stamps the canonical receipt values onto the delivered report
        # (R2.3-009 examiner diagnosis, 2026-08-21).
        forged = dict(report)
        forged["evidence_refs"] = [dict(report["evidence_refs"][0], response_digest="e" * 64)]
        forged_resource = Resource(forged)
        adapter.launch_lean_examiner_child = mock.Mock(return_value=forged_resource)
        accepted_forged = adapter.run_lean_examiner_child(
            packet=packet,
            metrics=ExaminerRunMetrics("platform"),
            read_key="temporary-key",
            platform_forwarder=lambda _tool, _arguments, _key: {},
            timeout_seconds=1,
        )
        self.assertEqual(accepted_forged["evidence_refs"][0]["response_digest"], receipt.response_digest)
        self.assertTrue(forged_resource.destroyed)

        wrong_tool = dict(report)
        wrong_tool["evidence_refs"] = [
            dict(report["evidence_refs"][0], tool="query_semantic_context")
        ]
        wrong_tool_resource = Resource(wrong_tool)
        adapter.launch_lean_examiner_child = mock.Mock(return_value=wrong_tool_resource)
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            adapter.run_lean_examiner_child(
                packet=packet,
                metrics=ExaminerRunMetrics("platform"),
                read_key="temporary-key",
                platform_forwarder=lambda _tool, _arguments, _key: {},
                timeout_seconds=1,
            )
        self.assertEqual(blocked.exception.reason, "acceptance-evidence")
        self.assertTrue(forged_resource.destroyed)

        empty_resource = Resource(report)
        empty_resource.proxy = SimpleNamespace(receipt_snapshot=())
        adapter.launch_lean_examiner_child = mock.Mock(return_value=empty_resource)
        with self.assertRaises(ExaminerRuntimeBlocked) as empty_blocked:
            adapter.run_lean_examiner_child(
                packet=packet,
                metrics=ExaminerRunMetrics("platform"),
                read_key="temporary-key",
                platform_forwarder=lambda _tool, _arguments, _key: {},
                timeout_seconds=1,
            )
        self.assertEqual(empty_blocked.exception.reason, "acceptance-evidence")
        self.assertTrue(empty_resource.destroyed)

    def test_platform_receipt_gate_reports_safe_binding_counts(self) -> None:
        cases = (
            (
                {"answerability": "answerable"},
                (object(), object()),
                {"binding_code": "report-refs-invalid", "report_ref_count": 0, "proxy_receipt_count": 2},
            ),
            (
                {"evidence_refs": [{"ref_id": "ref-1"}]},
                (),
                {"binding_code": "receipts-empty", "report_ref_count": 1, "proxy_receipt_count": 0},
            ),
            (
                {"evidence_refs": [{"ref_id": "ref-1"}, {"ref_id": "ref-2"}]},
                (object(),),
                {
                    "binding_code": "receipt-count-mismatch",
                    "report_ref_count": 2,
                    "proxy_receipt_count": 1,
                    "report_ref_ids": "ref-1,ref-2",
                    "report_ref_tools": "",
                    "proxy_receipt_ordinals": "None",
                    "proxy_receipt_tools": "",
                },
            ),
        )
        for report, receipts, expected in cases:
            with self.subTest(expected=expected):
                resource = SimpleNamespace(proxy=SimpleNamespace(receipt_snapshot=receipts))
                with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
                    _validate_platform_report_receipts(report, resource)
                self.assertEqual(blocked.exception.reason, "acceptance-evidence")
                self.assertEqual(blocked.exception.role, "platform")
                self.assertEqual(blocked.exception.evidence, expected)

    def test_platform_receipt_gate_identifies_loop_binding_branch(self) -> None:
        def receipt(ordinal: int, tool: str = "get_ontology_read_model", digest: str = "d" * 64) -> SimpleNamespace:
            return SimpleNamespace(
                ordinal=ordinal, tool=tool, request_digest="a" * 64, response_digest=digest,
                artifact_path=f"acceptance/r/platform-read/child/{ordinal}.json",
            )

        def page(ordinal: int = 0, **overrides: Any) -> dict:
            value = {
                "ordinal": ordinal, "input_cursor": None, "output_cursor": None,
                "has_more": False, "sequence_complete": True,
            }
            value.update(overrides)
            return value

        def ref(ordinal: int, **overrides: Any) -> dict:
            value = {
                "ref_id": f"p{ordinal}", "tool": "get_ontology_read_model",
                "request_digest": "a" * 64, "response_digest": "d" * 64,
                "artifact_path": f"acceptance/r/platform-read/child/{ordinal}.json",
                "page": page(ordinal),
            }
            value.update(overrides)
            return value

        cases = (
            ([ref(0), [receipt(0), receipt(1)][0]], {"binding_code": "locator-shape", "index": 1}),
            ([ref(0, page=page(0, has_more=True))], {"binding_code": "page-has-more-invalid", "index": 0}),
            ([ref(0, page=page(0, sequence_complete=False))], {"binding_code": "page-final-invalid", "index": 0}),
            ([ref(0, page=page(0, input_cursor="cursor"))], {"binding_code": "page-first-invalid", "index": 0}),
            ([ref(0), ref(1, page=page(1, input_cursor="cursor"))], {"binding_code": "page-sequence-invalid", "index": 1}),
            (
                [ref(0, page=page(0, has_more=True, output_cursor="cursor", sequence_complete=False)),
                 ref(1, ref_id="p0", page=page(1, input_cursor="cursor", has_more=False))],
                {"binding_code": "ref-id-invalid", "index": 1},
            ),
        )
        for refs, expected in cases:
            with self.subTest(expected=expected):
                report = _platform_report()
                report["evidence_refs"] = refs
                resource = SimpleNamespace(
                    proxy=SimpleNamespace(receipt_snapshot=tuple(receipt(i) for i in range(len(refs))))
                )
                with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
                    _validate_platform_report_receipts(report, resource)
                self.assertEqual(blocked.exception.reason, "acceptance-evidence")
                self.assertEqual(blocked.exception.evidence, expected)

        locator_key_report = _platform_report()
        locator_key_report["evidence_refs"] = [ref(0, tool="query_semantic_context")]
        key_resource = SimpleNamespace(proxy=SimpleNamespace(receipt_snapshot=(receipt(0),)))
        with self.assertRaises(ExaminerRuntimeBlocked) as key_blocked:
            _validate_platform_report_receipts(locator_key_report, key_resource)
        self.assertEqual(key_blocked.exception.evidence, {"binding_code": "locator-key-mismatch", "index": 0})

    def test_platform_receipt_gate_stamps_canonical_locator_fields(self) -> None:
        """A hand-copied digest typo must not kill the round: the sink stamps receipt values."""

        def receipt(ordinal: int) -> SimpleNamespace:
            return SimpleNamespace(
                ordinal=ordinal, tool="query_semantic_context",
                request_digest="a" * 64, response_digest="d" * 64,
                artifact_path=f"acceptance/r/platform-read/child/{ordinal}.json",
            )

        page = {
            "ordinal": 0, "input_cursor": None, "output_cursor": None,
            "has_more": False, "sequence_complete": True,
        }
        report = _platform_report()
        # Live v2b evidence shape: one transcribed character too many in one
        # digest, and a drifted artifact path, on an otherwise correct locator.
        report["evidence_refs"] = [
            {
                "ref_id": "p0", "tool": "query_semantic_context",
                "request_digest": "a" * 64 + "a", "response_digest": "typo",
                "artifact_path": "acceptance/wrong/path.json", "page": dict(page),
            }
        ]
        resource = SimpleNamespace(proxy=SimpleNamespace(receipt_snapshot=(receipt(0),)))
        _validate_platform_report_receipts(report, resource)
        stamped = report["evidence_refs"][0]
        self.assertEqual(stamped["request_digest"], "a" * 64)
        self.assertEqual(stamped["response_digest"], "d" * 64)
        self.assertEqual(stamped["artifact_path"], "acceptance/r/platform-read/child/0.json")

    def test_lean_runtime_acceptance_rejects_invented_or_empty_pass_evidence(self) -> None:
        def source(packet, metrics):
            metrics.bind_thread("source-1")
            return {
                "answerability": "answerable", "conclusion": "source", "evidence": [],
                "coverage": {"queries_or_sections": [], "complete": True}, "gaps": [],
                "evidence_refs": [{"location": "source.md"}],
            }

        def platform(packet, metrics):
            metrics.bind_thread("platform-1")
            return _platform_report()

        for evidence_ref_ids in (["invented"], []):
            def acceptance(packet, metrics, evidence_ref_ids=evidence_ref_ids):
                metrics.bind_thread("acceptance-1")
                return {
                    "status": "PASS", "answer": "ok", "evidence_ref_ids": list(evidence_ref_ids),
                    "current": True, "usable": True, "failure_layer": None, "blocked_reason": None,
                }

            runtime = LeanExaminerRuntime(
                source_executor=source,
                platform_executor=platform,
                acceptance_executor=acceptance,
            )
            with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
                runtime.run(
                    [{"question": "q1"}],
                    source_packets=[_source_payload()],
                    platform_packets=[_platform_payload()],
                    ticket_binding={"ticket_digest": "a" * 64},
                    verdict_schema={"type": "verdict"},
                )
            self.assertEqual(blocked.exception.reason, "acceptance-evidence")

    def test_codex_executor_returns_terminal_payload_and_destroys_child(self) -> None:
        captured = {}
        report = {
            "answerability": "answerable",
            "conclusion": "source",
            "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True},
            "gaps": [],
            "evidence_refs": [{"location": "source.md"}],
        }

        class Resource:
            def __init__(self):
                self.submitted_reports = [report]
                self.terminal_event = True
                self.destroyed = False
                self.process = None

            def failure_evidence(self):
                return None

            def destroy(self):
                self.destroyed = True
                shutil.rmtree(captured["private_root"], ignore_errors=True)

        def factory(spec):
            captured.update(spec)
            captured["private_root"] = spec["private_root"]
            return Resource()

        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False, acceptance_child_factory=factory)
        packet = build_source_examiner_packet(**_source_payload())
        metrics = ExaminerRunMetrics("source")
        result = adapter.run_lean_examiner_child(packet, metrics, timeout_seconds=1)
        self.assertEqual(result, report)
        self.assertTrue(captured["private_root"])
        self.assertFalse(Path(captured["private_root"]).exists())
        self.assertEqual(metrics.terminal_report, True)

    def test_codex_executor_waits_for_real_report_sink_callback_without_factory(self) -> None:
        report = {
            "answerability": "answerable",
            "conclusion": "source",
            "evidence": [],
            "coverage": {"queries_or_sections": [], "complete": True},
            "gaps": [],
            "evidence_refs": [{"location": "source.md"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            socket_path = root / "report.sock"
            token = "sink-token"
            reports = []
            sink = ReportSinkServer(socket_path, token, reports.append, kind="source")
            sink.start()

            class Resource:
                process = None
                blocked = None
                destroyed = False
                terminal_event = True

                @property
                def submitted_reports(self):
                    return reports

                def failure_evidence(self):
                    return None

                def destroy(self):
                    self.destroyed = True
                    sink.stop()

            resource = Resource()
            adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
            adapter.launch_lean_examiner_child = mock.Mock(return_value=resource)

            def submit_later():
                time.sleep(0.03)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                    connection.connect(str(socket_path))
                    connection.sendall(json.dumps({"token": token, "report": report}).encode("utf-8"))

            sender = threading.Thread(target=submit_later, daemon=True)
            sender.start()
            packet = build_source_examiner_packet(**_source_payload())
            metrics = ExaminerRunMetrics("source")
            result = adapter.run_lean_examiner_child(packet, metrics, timeout_seconds=1)
            sender.join(timeout=1)
            self.assertEqual(result, report)
            self.assertTrue(resource.destroyed)

    def test_codex_executor_preserves_budget_blocked_reason(self) -> None:
        class Resource:
            process = None
            blocked = ExaminerRuntimeBlocked("runtime-budget", role="source")
            submitted_reports = []
            destroyed = False

            def failure_evidence(self):
                return None

            def destroy(self):
                self.destroyed = True

        resource = Resource()
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        adapter.launch_lean_examiner_child = mock.Mock(return_value=resource)
        packet = build_source_examiner_packet(**_source_payload())
        with self.assertRaises(ExaminerRuntimeBlocked) as blocked:
            adapter.run_lean_examiner_child(packet, ExaminerRunMetrics("source"), timeout_seconds=1)
        self.assertEqual(blocked.exception.reason, "runtime-budget")
        self.assertTrue(resource.destroyed)

    def test_lean_acceptance_package_and_inventory_are_report_only(self) -> None:
        package, instructions, skill = CodexRuntimeAdapter._child_package_assets("acceptance", repository_root())
        self.assertEqual(package.name, "package.yaml")
        package_text = package.read_text(encoding="utf-8")
        self.assertIn("team_transport: false", package_text)
        self.assertNotIn("Team Transport", instructions.read_text(encoding="utf-8"))
        self.assertNotIn("Team Transport", skill.read_text(encoding="utf-8"))
        adapter = CodexRuntimeAdapter(repository_root=repository_root(), use_bwrap=False)
        agent = mock.Mock()
        agent.package.package_id = "acceptance"
        with mock.patch.object(adapter, "_require_mcp_surface") as required:
            adapter._require_lean_examiner_mcp_servers(agent)
        required.assert_called_once_with(agent, {"examiner_report": {"submit_examiner_report"}})


if __name__ == "__main__":
    unittest.main()
