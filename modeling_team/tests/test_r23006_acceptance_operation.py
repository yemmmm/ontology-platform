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
