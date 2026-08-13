from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from modeling_team.r23006_acceptance_operation import (
    EXPECTED_SCOPE,
    R23006AcceptanceOperation,
    R23006OperationError,
    prepare_r23006_operation,
)
from modeling_team.acceptance_runtime import ExaminerRuntimeBlocked


ROOT = Path(__file__).resolve().parents[2]


def _metric(role: str, ordinal: int) -> dict[str, Any]:
    return {
        "schema_version": "ExaminerRunMetrics/v1",
        "role": role,
        "fresh_thread_id": f"thread-{ordinal}-{role}",
        "fresh_thread": True,
        "metrics_complete": True,
        "inherited_turns": 0,
        "first_turn_input": {"fields": ["text", "type"], "digest": "a" * 64},
        "turn_start_count": 1,
        "inference_steps": 1,
        "token_usage_increments": [{
            "inputTokens": 10,
            "cachedInputTokens": 0,
            "cacheWriteInputTokens": 0,
            "outputTokens": 2,
            "reasoningOutputTokens": 0,
            "totalTokens": 12,
            "modelContextWindow": 1000,
        }],
        "first_input_tokens": 10,
        "total_tokens": 12,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 2,
        "reasoning_output_tokens": 0,
        "model_context_window": 1000,
        "token_estimate_algorithm": "canonical_utf8_bytes_div_4_ceil",
        "estimated_task_tokens": 10,
        "estimated_evidence_tokens": 2,
        "task_tokens": 10,
        "evidence_tokens": 2,
        "ttft_ms": 2.0,
        "terminal_wall_ms": 5.0,
        "proxy_time_ms": 1.0 if role == "platform" else 0.0,
        "collaboration_rejections": 0,
        "terminal_report": True,
        "blocked": None,
    }


def _result() -> dict[str, Any]:
    verdicts = []
    for ordinal in (1, 2):
        verdicts.append(
            {
                "status": "PASS",
                "answer": f"answer-{ordinal}",
                "evidence_ref_ids": [f"source-{ordinal}", f"platform-{ordinal}"],
                "current": True,
                "usable": True,
                "failure_layer": None,
                "blocked_reason": None,
                "question_ordinal": ordinal,
                "question_count": 2,
                "previous_question_ordinal": ordinal - 1 if ordinal > 1 else None,
                "next_question_ordinal": ordinal + 1 if ordinal < 2 else None,
                "final": ordinal == 2,
            }
        )
    return {
        "schema_version": "ExaminerOrderedVerdicts/v1",
        "count": 2,
        "verdicts": verdicts,
        "status": "PASS",
        "previous": 1,
        "next": None,
        "final": True,
        "complete": True,
        "metrics": [
            _metric(role, ordinal)
            for ordinal in (1, 2)
            for role in ("source", "platform", "acceptance")
        ],
    }


class FakeHost:
    def __init__(self, _root: Path, _output: Path, *, fail_run: bool = False, drift: bool = False):
        self.fail_run = fail_run
        self.drift = drift
        self.started = False
        self.created = 0
        self.revoked = 0
        self.stopped = False
        self.snapshots = 0
        self.partial_metrics: list[Mapping[str, Any]] = []

    def start(self, _prepared) -> None:
        self.started = True

    def snapshot(self, _prepared) -> Mapping[str, Any]:
        self.snapshots += 1
        return {
            "platform_digest": "b" * 64 if self.drift and self.snapshots > 1 else "a" * 64,
            "ledger_sha256": "c" * 64,
            "ledger_record_count": 66,
        }

    def create_read_key(self, _prepared) -> None:
        self.created += 1

    def run_examiner(self, _prepared) -> Mapping[str, Any]:
        if self.fail_run:
            raise RuntimeError("provider failed")
        return _result()

    def failure_metrics(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.partial_metrics)

    def revoke_read_key(self) -> None:
        self.revoked += 1

    def key_evidence(self) -> Mapping[str, Any]:
        return {
            "create_count": self.created,
            "revoke_count": self.revoked,
            "post_revoke_status": 401,
            "post_revoke_denied": True,
        }

    def stop(self) -> Mapping[str, Any]:
        self.stopped = True
        return {
            "provider_stopped": True,
            "children_stopped": True,
            "forwarder_stopped": True,
            "runtime_root_removed": True,
            "admin_key_revoked": True,
            "plaintext_released": True,
        }


class R23006AcceptanceOperationTests(unittest.TestCase):
    def test_prepare_binds_retained_n2_sources_and_scope(self) -> None:
        prepared = prepare_r23006_operation(ROOT)
        self.assertEqual([row["question_id"] for row in prepared.questions], ["cq-001", "cq-002"])
        self.assertEqual(len(prepared.source_packets), 2)
        self.assertEqual(len(prepared.platform_packets), 2)
        self.assertEqual(
            prepared.platform_packets[0]["platform_read_scope"],
            {key: EXPECTED_SCOPE[key] for key in ("project_id", "ontology_id", "graph_set_id")},
        )
        for packet in prepared.source_packets:
            self.assertTrue(packet["approved_sources"])
            for source in packet["approved_sources"]:
                self.assertIsInstance(source["bytes"], bytes)
                self.assertEqual(len(source["sha256"]), 64)

    def test_success_writes_non_secret_evidence_after_cleanup(self) -> None:
        holder: dict[str, FakeHost] = {}

        def factory(root: Path, output: Path) -> FakeHost:
            holder["host"] = FakeHost(root, output)
            return holder["host"]

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            evidence = R23006AcceptanceOperation(ROOT, output, host_factory=factory).run()
            host = holder["host"]
            self.assertEqual((host.created, host.revoked), (1, 1))
            self.assertTrue(host.stopped)
            self.assertTrue(evidence["invariance"]["equal"])
            self.assertEqual(evidence["result"]["status"], "PASS")
            path = output / "r23006-retained-acceptance.json"
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], evidence["schema_version"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            serialized = path.read_text(encoding="utf-8")
            self.assertNotIn("plaintext_key", serialized)
            self.assertNotIn("Authorization", serialized)

    def test_provider_failure_still_revokes_and_stops(self) -> None:
        holder: dict[str, FakeHost] = {}

        def factory(root: Path, output: Path) -> FakeHost:
            holder["host"] = FakeHost(root, output, fail_run=True)
            return holder["host"]

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(R23006OperationError):
                R23006AcceptanceOperation(ROOT, Path(temporary), host_factory=factory).run()
        host = holder["host"]
        self.assertEqual((host.created, host.revoked), (1, 1))
        self.assertTrue(host.stopped)

    def test_typed_child_timeout_writes_blocked_evidence_and_safe_outer_error(self) -> None:
        holder: dict[str, FakeHost] = {}

        class TimeoutHost(FakeHost):
            def run_examiner(self, _prepared) -> Mapping[str, Any]:
                platform = _metric("platform", 1)
                platform["metrics_complete"] = False
                platform["terminal_report"] = False
                platform["ttft_ms"] = None
                platform["terminal_wall_ms"] = None
                blocked_evidence = {
                    "failure_category": "runtime",
                    "reason_code": "child-timeout",
                    "report_received": True,
                    "terminal_event": False,
                    "proxy_receipt_count": 2,
                }
                platform["blocked"] = ExaminerRuntimeBlocked(
                    "runtime-infrastructure",
                    role="platform",
                    evidence=blocked_evidence,
                ).as_dict()
                self.partial_metrics = [_metric("source", 1), platform]
                raise ExaminerRuntimeBlocked(
                    "runtime-infrastructure",
                    role="platform",
                    evidence=blocked_evidence,
                )

        def factory(root: Path, output: Path) -> FakeHost:
            holder["host"] = TimeoutHost(root, output)
            return holder["host"]

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "blocked"
            with self.assertRaisesRegex(
                R23006OperationError,
                r"role=platform reason=runtime-infrastructure category=runtime code=child-timeout",
            ):
                R23006AcceptanceOperation(ROOT, output, host_factory=factory).run()
            path = output / "r23006-retained-acceptance.json"
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            evidence = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "BLOCKED")
            self.assertEqual(evidence["result"]["status"], "BLOCKED")
            self.assertEqual(evidence["result"]["role"], "platform")
            self.assertEqual(evidence["result"]["reason_code"], "child-timeout")
            self.assertFalse(evidence["result"]["complete"])
            self.assertEqual(
                [metric["role"] for metric in evidence["partial_metrics"]],
                ["source", "platform"],
            )
            self.assertTrue(evidence["partial_metrics"][0]["metrics_complete"])
            self.assertFalse(evidence["partial_metrics"][1]["metrics_complete"])
            self.assertEqual(evidence["result"]["evidence"]["report_received"], True)
            self.assertEqual(evidence["result"]["evidence"]["terminal_event"], False)
            self.assertEqual(evidence["result"]["evidence"]["proxy_receipt_count"], 2)
            self.assertNotIn("secret", path.read_text(encoding="utf-8").lower())
        host = holder["host"]
        self.assertEqual((host.created, host.revoked), (1, 1))
        self.assertTrue(host.stopped)

    def test_secret_failure_evidence_is_rejected_and_not_written(self) -> None:
        holder: dict[str, FakeHost] = {}

        class SecretFailureHost(FakeHost):
            def run_examiner(self, _prepared) -> Mapping[str, Any]:
                raise ExaminerRuntimeBlocked(
                    "runtime-infrastructure",
                    role="platform",
                    evidence={
                        "failure_category": "runtime",
                        "reason_code": "child-timeout",
                        "read_key": "sk_read_secret",
                    },
                )

        def factory(root: Path, output: Path) -> FakeHost:
            holder["host"] = SecretFailureHost(root, output)
            return holder["host"]

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with self.assertRaisesRegex(R23006OperationError, "secret-bearing evidence") as raised:
                R23006AcceptanceOperation(ROOT, output, host_factory=factory).run()
            self.assertNotIn("sk_read_secret", str(raised.exception))
            self.assertFalse((output / "r23006-retained-acceptance.json").exists())
        host = holder["host"]
        self.assertEqual((host.created, host.revoked), (1, 1))
        self.assertTrue(host.stopped)

    def test_typed_runtime_and_launch_evidence_is_safely_projected(self) -> None:
        cases = (
            (
                "runtime-budget",
                {"steps": 4},
                {"steps": 4},
            ),
            (
                "runtime-metrics",
                {"field": "inputTokens"},
                {"field": "inputTokens"},
            ),
            (
                "runtime-metrics",
                {"thread_id": "thread-1"},
                {"thread_id": "thread-1"},
            ),
            (
                "runtime-metrics",
                {"turn_id": "turn-1"},
                {"turn_id": "turn-1"},
            ),
            (
                "acceptance-input",
                {"inherited_turns": 0},
                {"inherited_turns": 0},
            ),
            (
                "acceptance-input",
                {"host_packet_tokens": 12},
                {"host_packet_tokens": 12},
            ),
            (
                "acceptance-input",
                {"read_key": True},
                {"read_key_present": True},
            ),
            (
                "acceptance-input",
                {"forwarder": False},
                {"forwarder_callable": False},
            ),
            (
                "acceptance-input",
                {"packet": "platform Examiner packet"},
                {"packet": "platform-examiner-packet"},
            ),
            (
                "acceptance-evidence",
                {"path": "docs/source.md"},
                {"path": "docs/source.md"},
            ),
            (
                "acceptance-evidence",
                {
                    "binding_code": "receipt-count-mismatch",
                    "report_ref_count": 2,
                    "proxy_receipt_count": 1,
                },
                {
                    "binding_code": "receipt-count-mismatch",
                    "report_ref_count": 2,
                    "proxy_receipt_count": 1,
                },
            ),
            (
                "acceptance-evidence",
                {
                    "binding_code": "report-fields-invalid",
                    "report_field_set": "answerability,conclusion,evidence",
                },
                {
                    "binding_code": "report-fields-invalid",
                    "report_field_set": "answerability,conclusion,evidence",
                },
            ),
            (
                "acceptance-evidence",
                {
                    "binding_code": "locator-key-mismatch",
                    "index": 2,
                },
                {
                    "binding_code": "locator-key-mismatch",
                    "index": 2,
                },
            ),
            (
                "acceptance-evidence",
                {
                    "binding_code": "source-path-unauthorized",
                    "path": "docs/other.md",
                },
                {
                    "binding_code": "source-path-unauthorized",
                    "path": "docs/other.md",
                },
            ),
        )
        for reason, blocked_evidence, expected_evidence in cases:
            with self.subTest(reason=reason, blocked_evidence=blocked_evidence), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)

                class TypedBlockedHost(FakeHost):
                    def run_examiner(self, _prepared) -> Mapping[str, Any]:
                        raise ExaminerRuntimeBlocked(
                            reason,
                            role="platform",
                            evidence=blocked_evidence,
                        )

                def factory(root: Path, target: Path) -> FakeHost:
                    return TypedBlockedHost(root, target)

                with self.assertRaisesRegex(
                    R23006OperationError,
                    rf"role=platform reason={reason} category=unspecified code=unspecified",
                ):
                    R23006AcceptanceOperation(ROOT, output, host_factory=factory).run()
                evidence = json.loads(
                    (output / "r23006-retained-acceptance.json").read_text(encoding="utf-8")
                )
                self.assertEqual(evidence["status"], "BLOCKED")
                self.assertEqual(evidence["result"]["status"], "BLOCKED")
                self.assertEqual(evidence["result"]["evidence"], expected_evidence)
                self.assertIsNone(evidence["result"]["failure_category"])
                self.assertIsNone(evidence["result"]["reason_code"])

    def test_unknown_provider_text_or_wrong_typed_failure_evidence_is_not_written(self) -> None:
        cases = (
            {"provider_text": "provider timed out"},
            {"reason_code": "provider timed out"},
            {"packet": "other-packet"},
            {"path": "/etc/passwd"},
            {"path": "../secret"},
            {"path": "platform Examiner packet"},
            {"path": "provider report text"},
            {"steps": True},
            {"read_key": "true"},
            {"report_received": 1},
            {"terminal_event": "false"},
            {"proxy_receipt_count": True},
            {"proxy_receipt_count": -1},
            {"proxy_receipt_count": "2"},
            {"binding_code": "provider-text", "report_ref_count": 2, "proxy_receipt_count": 1},
            {"binding_code": "receipt-count-mismatch", "report_ref_count": True, "proxy_receipt_count": 1},
            {"binding_code": "receipt-count-mismatch", "report_ref_count": -1, "proxy_receipt_count": 1},
            {"binding_code": "receipt-count-mismatch", "report_ref_count": "2", "proxy_receipt_count": 1},
        )
        for blocked_evidence in cases:
            with self.subTest(blocked_evidence=blocked_evidence), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)

                class InvalidEvidenceHost(FakeHost):
                    def run_examiner(self, _prepared) -> Mapping[str, Any]:
                        raise ExaminerRuntimeBlocked(
                            "runtime-infrastructure",
                            role="platform",
                            evidence=blocked_evidence,
                        )

                def factory(root: Path, target: Path) -> FakeHost:
                    return InvalidEvidenceHost(root, target)

                with self.assertRaises(R23006OperationError):
                    R23006AcceptanceOperation(ROOT, output, host_factory=factory).run()
                self.assertFalse((output / "r23006-retained-acceptance.json").exists())

    def test_partial_metrics_reject_extra_role_bool_secret_and_invalid_blocked(self) -> None:
        cases: list[dict[str, Any]] = []
        extra = _metric("source", 1)
        extra["unexpected"] = True
        cases.append(extra)
        wrong_role = _metric("source", 1)
        wrong_role["role"] = "platform"
        cases.append(wrong_role)
        wrong_bool = _metric("source", 1)
        wrong_bool["metrics_complete"] = 1
        cases.append(wrong_bool)
        secret = _metric("source", 1)
        secret["fresh_thread_id"] = "sk_read_partial_secret"
        cases.append(secret)
        invalid_blocked = _metric("source", 1)
        invalid_blocked["blocked"] = {
            "schema_version": "ExaminerBlocked/v1",
            "status": "BLOCKED",
            "blocked_reason": "provider text",
            "role": "source",
            "evidence": {},
        }
        cases.append(invalid_blocked)
        for metric in cases:
            with self.subTest(metric=metric), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)

                class InvalidPartialHost(FakeHost):
                    def run_examiner(self, _prepared) -> Mapping[str, Any]:
                        self.partial_metrics = [metric]
                        raise ExaminerRuntimeBlocked(
                            "runtime-infrastructure",
                            role="platform",
                            evidence={"failure_category": "runtime", "reason_code": "child-timeout"},
                        )

                def factory(root: Path, target: Path) -> FakeHost:
                    return InvalidPartialHost(root, target)

                with self.assertRaises(R23006OperationError):
                    R23006AcceptanceOperation(ROOT, output, host_factory=factory).run()
                self.assertFalse((output / "r23006-retained-acceptance.json").exists())

    def test_partial_metrics_must_end_with_matching_outer_block(self) -> None:
        outer_evidence = {
            "failure_category": "runtime",
            "reason_code": "child-timeout",
            "report_received": True,
            "terminal_event": False,
            "proxy_receipt_count": 2,
        }

        def blocked(*, role: str = "platform", reason: str = "runtime-infrastructure", evidence=None):
            return ExaminerRuntimeBlocked(
                reason,
                role=role,
                evidence=dict(outer_evidence if evidence is None else evidence),
            ).as_dict()

        def rows(last_blocked, *, first_blocked=None):
            source = _metric("source", 1)
            source["blocked"] = first_blocked
            platform = _metric("platform", 1)
            platform["metrics_complete"] = False
            platform["terminal_report"] = False
            platform["ttft_ms"] = None
            platform["terminal_wall_ms"] = None
            platform["blocked"] = last_blocked
            return [source, platform]

        cases = {
            "role mismatch": rows(blocked(role="source")),
            "reason mismatch": rows(blocked(reason="runtime-budget")),
            "evidence mismatch": rows(blocked(evidence={**outer_evidence, "proxy_receipt_count": 1})),
            "prior completed blocked": rows(blocked(), first_blocked=blocked()),
            "last missing blocked": rows(None),
        }
        for label, partial_metrics in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)

                class InvalidTerminalBlockHost(FakeHost):
                    def run_examiner(self, _prepared) -> Mapping[str, Any]:
                        self.partial_metrics = partial_metrics
                        raise ExaminerRuntimeBlocked(
                            "runtime-infrastructure",
                            role="platform",
                            evidence=outer_evidence,
                        )

                def factory(root: Path, target: Path) -> FakeHost:
                    return InvalidTerminalBlockHost(root, target)

                with self.assertRaises(R23006OperationError):
                    R23006AcceptanceOperation(ROOT, output, host_factory=factory).run()
                self.assertFalse((output / "r23006-retained-acceptance.json").exists())

    def test_blocked_failure_does_not_write_artifact_when_cleanup_or_invariance_is_incomplete(self) -> None:
        cases: tuple[str, type[FakeHost]] = ()

        class CleanupFailureHost(FakeHost):
            def run_examiner(self, _prepared) -> Mapping[str, Any]:
                raise ExaminerRuntimeBlocked(
                    "runtime-infrastructure",
                    role="platform",
                    evidence={"failure_category": "runtime", "reason_code": "child-timeout"},
                )

            def stop(self) -> Mapping[str, Any]:
                cleanup = dict(super().stop())
                cleanup["children_stopped"] = False
                return cleanup

        class InvarianceFailureHost(CleanupFailureHost):
            def snapshot(self, prepared) -> Mapping[str, Any]:
                snapshot = dict(super().snapshot(prepared))
                if self.snapshots > 1:
                    snapshot["platform_digest"] = "c" * 64
                return snapshot

        cases = (("cleanup", CleanupFailureHost), ("invariance", InvarianceFailureHost))
        for label, host_type in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)

                def factory(root: Path, target: Path, host_type=host_type) -> FakeHost:
                    return host_type(root, target)

                with self.assertRaises(R23006OperationError):
                    R23006AcceptanceOperation(ROOT, output, host_factory=factory).run()
                self.assertFalse((output / "r23006-retained-acceptance.json").exists())

    def test_partial_key_create_side_effect_still_invokes_revoke_cleanup(self) -> None:
        holder: dict[str, FakeHost] = {}

        class PartialCreateHost(FakeHost):
            def create_read_key(self, _prepared) -> None:
                self.created += 1
                raise RuntimeError("creation response was lost")

        def factory(root: Path, output: Path) -> FakeHost:
            holder["host"] = PartialCreateHost(root, output)
            return holder["host"]

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(R23006OperationError):
                R23006AcceptanceOperation(ROOT, Path(temporary), host_factory=factory).run()
        host = holder["host"]
        self.assertEqual((host.created, host.revoked), (1, 1))
        self.assertTrue(host.stopped)

    def test_snapshot_drift_fails_after_cleanup(self) -> None:
        holder: dict[str, FakeHost] = {}

        def factory(root: Path, output: Path) -> FakeHost:
            holder["host"] = FakeHost(root, output, drift=True)
            return holder["host"]

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(R23006OperationError, "model or ledger changed"):
                R23006AcceptanceOperation(ROOT, Path(temporary), host_factory=factory).run()
        host = holder["host"]
        self.assertEqual((host.created, host.revoked), (1, 1))
        self.assertTrue(host.stopped)

    def test_malformed_metrics_fail_after_cleanup(self) -> None:
        holder: dict[str, FakeHost] = {}

        class BadMetricsHost(FakeHost):
            def run_examiner(self, _prepared) -> Mapping[str, Any]:
                result = _result()
                result["metrics"][0]["first_turn_input"]["digest"] = "x"
                result["metrics"][0]["token_usage_increments"] = [{"garbage": -1}]
                result["metrics"][0]["ttft_ms"] = -1
                return result

        def factory(root: Path, output: Path) -> FakeHost:
            holder["host"] = BadMetricsHost(root, output)
            return holder["host"]

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(R23006OperationError, "metrics completion"):
                R23006AcceptanceOperation(ROOT, Path(temporary), host_factory=factory).run()
        host = holder["host"]
        self.assertEqual((host.created, host.revoked), (1, 1))
        self.assertTrue(host.stopped)

    def test_secret_bearing_host_evidence_is_not_written(self) -> None:
        holder: dict[str, FakeHost] = {}

        class SecretHost(FakeHost):
            def key_evidence(self) -> Mapping[str, Any]:
                return {**super().key_evidence(), "plaintext_key": "sk_read_secret"}

        def factory(root: Path, output: Path) -> FakeHost:
            holder["host"] = SecretHost(root, output)
            return holder["host"]

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with self.assertRaisesRegex(R23006OperationError, "secret-bearing evidence"):
                R23006AcceptanceOperation(ROOT, output, host_factory=factory).run()
            self.assertFalse((output / "r23006-retained-acceptance.json").exists())
        host = holder["host"]
        self.assertEqual((host.created, host.revoked), (1, 1))
        self.assertTrue(host.stopped)


if __name__ == "__main__":
    unittest.main()
