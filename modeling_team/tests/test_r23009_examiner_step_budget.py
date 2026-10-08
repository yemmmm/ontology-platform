"""R2.3-009 follow-up: unified examiner step-budget guardrail.

Live history: start2 (r23009-luna-20260820-start2, cq-001 acceptance round)
showed the platform examiner exhausting the previous platform-only 10-step
inference cap on both the first attempt and the single permitted
identical-input retry (``reason_code=runtime-budget``) while the source
examiner passed unchanged; 20 (platform-only) then passed that layer in
start3.  User decision 2026-08-20: one unified cap of 30 for every examiner
child, no per-role distinction.  The cap bounds runaway children only; it is
not an acceptance-quality gate.

These tests pin the unified budget for every role and the retry child's
identical budget so a future edit cannot silently shrink the live acceptance
path back below the observed live requirement.
"""

from __future__ import annotations

import unittest

from modeling_team.acceptance_runtime import (
    ExaminerRunMetrics,
    ExaminerRuntimeBlocked,
    LeanExaminerRuntime,
    _EXAMINER_MAX_INFERENCE_STEPS,
)


def _source_report() -> dict:
    return {
        "answerability": "answerable",
        "conclusion": "source",
        "evidence": [],
        "coverage": {"queries_or_sections": [], "complete": True},
        "gaps": [],
        "evidence_refs": [{"location": "source.md"}],
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


class R23009ExaminerStepBudgetTests(unittest.TestCase):
    def test_unified_examiner_budget_is_calibrated(self) -> None:
        self.assertEqual(_EXAMINER_MAX_INFERENCE_STEPS, 30)

    def test_every_role_defaults_to_the_unified_budget(self) -> None:
        for role in ("source", "platform", "acceptance"):
            self.assertEqual(ExaminerRunMetrics(role).max_inference_steps, 30)

    def test_platform_children_receive_the_calibrated_budget(self) -> None:
        observed: list[int] = []

        def source(packet, metrics):
            metrics.bind_thread(f"source-{packet.payload['ordinal']}")
            return _source_report()

        def platform(packet, metrics):
            metrics.bind_thread(f"platform-{packet.payload['ordinal']}")
            observed.append(metrics.max_inference_steps)
            return _platform_report()

        def acceptance(packet, metrics):
            metrics.bind_thread(f"acceptance-{packet.payload['ordinal']}")
            return {
                "status": "PASS",
                "answer": "ok",
                "evidence_ref_ids": ["platform-ref"],
                "current": True,
                "usable": True,
                "failure_layer": None,
                "blocked_reason": None,
            }

        runtime = LeanExaminerRuntime(
            source_executor=source,
            platform_executor=platform,
            acceptance_executor=acceptance,
        )
        result = runtime.run(
            [{"question": "q1"}],
            source_packets=[self._source_payload()],
            platform_packets=[self._platform_payload()],
            ticket_binding={"ticket_digest": "a" * 64},
            verdict_schema={"type": "verdict"},
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(observed, [_EXAMINER_MAX_INFERENCE_STEPS])

    def test_platform_retry_child_receives_the_same_calibrated_budget(self) -> None:
        observed: list[int] = []
        attempts = {"count": 0}

        def source(packet, metrics):
            metrics.bind_thread("source-1")
            return _source_report()

        def platform(packet, metrics):
            attempts["count"] += 1
            metrics.bind_thread(f"platform-{attempts['count']}")
            observed.append(metrics.max_inference_steps)
            if attempts["count"] == 1:
                raise ExaminerRuntimeBlocked(
                    "runtime-budget",
                    role="platform",
                    evidence={"steps": metrics.inference_steps},
                )
            return _platform_report()

        def acceptance(packet, metrics):
            metrics.bind_thread("acceptance-1")
            return {
                "status": "PASS",
                "answer": "ok",
                "evidence_ref_ids": ["platform-ref"],
                "current": True,
                "usable": True,
                "failure_layer": None,
                "blocked_reason": None,
            }

        runtime = LeanExaminerRuntime(
            source_executor=source,
            platform_executor=platform,
            acceptance_executor=acceptance,
        )
        result = runtime.run(
            [{"question": "q1"}],
            source_packets=[self._source_payload()],
            platform_packets=[self._platform_payload()],
            ticket_binding={"ticket_digest": "a" * 64},
            verdict_schema={"type": "verdict"},
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(attempts["count"], 2)
        self.assertEqual(
            observed,
            [_EXAMINER_MAX_INFERENCE_STEPS, _EXAMINER_MAX_INFERENCE_STEPS],
        )

    def _source_payload(self) -> dict:
        import hashlib

        source = b"approved source"
        manifest = [{"path": "source.md", "sha256": hashlib.sha256(source).hexdigest()}]
        return {
            "question": "Which output is consumed?",
            "ordinal": 1,
            "count": 1,
            "approved_sources": [
                {
                    "path": "source.md",
                    "sha256": hashlib.sha256(source).hexdigest(),
                    "bytes": source,
                }
            ],
            "source_bundle_digest": hashlib.sha256(
                __import__("json").dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "report_schema": {"type": "source-report"},
        }

    def _platform_payload(self) -> dict:
        from modeling_team.acceptance_runtime import (
            PLATFORM_PROXY_READ_TOOLS,
            examiner_proxy_schemas,
        )

        return {
            "question": "Which output is consumed?",
            "ordinal": 1,
            "count": 1,
            "ticket_binding": {"ticket_digest": "a" * 64},
            "model_state": {"model_revision": 1, "state_digest": "b" * 64},
            "platform_read_scope": {
                "project_id": "project-1",
                "ontology_id": "ontology-1",

            },
            "proxy_capability": {"capability_id": "proxy-1"},
            "allowed_read_tools": list(PLATFORM_PROXY_READ_TOOLS),
            "request_schema": examiner_proxy_schemas(PLATFORM_PROXY_READ_TOOLS),
            "report_schema": {"type": "platform-report"},
        }


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
