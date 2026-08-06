from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from shutil import rmtree
from unittest.mock import patch

from modeling_team.acceptance import (
    AcceptanceContractError,
    CoordinatorPhaseController,
    ModelStateBoundary,
    PlatformScopeShim,
    ReadOnlyKeyLifecycle,
    RunnerAcceptanceCarrier,
    SettlementCAS,
    canonical_mode_preflight,
    canonical_platform_allowlist,
    classify_comparison,
    model_state_digest,
    modeling_receipt_digest,
    report_digest,
    ticket_digest,
    verdict_digest,
    validate_page_chain,
    validate_location_hint,
    validate_model_state,
    validate_platform_read_scope,
    validate_report,
    validate_typed_evidence_ref,
    validate_ticket,
    validate_verdict,
)
from modeling_team.contracts import TeamConfigurationError, _load_package, repository_root
from modeling_team import preflight as preflight_module
from modeling_team.runner import TeamRunner
from modeling_team.preflight import normalize_formal_scope
from modeling_team.runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError, _Agent
from modeling_team.start_ledger import StartLedger
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _ticket(round_suffix: str = "1") -> dict:
    state = {
        "project_id": "project-r23005",
        "ontology_id": "ontology-r23005",
        "workspace_version": "workspace-1",
        "source_signature": "source-1",
        "build_session_id": "session-r23005",
        "graph_set_id": "graph-r23005",
    }
    state["state_digest"] = model_state_digest(state)
    sources = [{"path": "source.md", "sha256": "b" * 64}]
    source_bundle_digest = _sha(sources)
    artifact = {"path": "acceptance/standard.json", "digest": "d" * 64}
    receipts = []
    for stage, status in (
        ("dry-run", "validated"),
        ("apply", "applied"),
        ("readback", "complete"),
        ("validation", "succeeded"),
        ("reasoning", "succeeded"),
    ):
        ref = {
            "type": "platform_read",
            "ref_id": f"ref-{stage.replace('-', '')}",
            "ticket_digest": None,
            "model_state_digest": state["state_digest"],
            "tool": "get_modeling_context",
            "request_digest": "e" * 64,
            "response_digest": "f" * 64,
            "artifact_path": f"evidence/{stage}.json",
            "page": {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        }
        receipts.append(
            {
                "stage": stage,
                "status": status,
                "receipt_digest": None,
                "run_id": "producer-r23005",
                "project_id": state["project_id"],
                "ontology_id": state["ontology_id"],
                "slice_revision": "slice-1",
                "model_state_digest": state["state_digest"],
                "evidence_ref": ref,
            }
        )
        receipts[-1]["receipt_digest"] = modeling_receipt_digest(receipts[-1])
    ticket = {
        "schema_version": "r2-3-005-slice-acceptance-ticket/v1",
        "ticket_id": f"ticket-r23005-{round_suffix}",
        "acceptance_round_id": f"round-r23005-{round_suffix}",
        "task_id": "task-r23005",
        "producer_run_id": "producer-r23005",
        "slice_id": "slice-r23005",
        "slice_revision": "slice-1",
        "question_id": "cq1",
        "question": "Which output is consumed?",
        "approved_sources": sources,
        "source_bundle_digest": source_bundle_digest,
        "platform_read_scope": {
            "project_id": state["project_id"],
            "ontology_id": state["ontology_id"],
            "graph_set_id": state["graph_set_id"],
        },
        "model_state": state,
        "model_state_digest": state["state_digest"],
        "competency_questions": [{"id": "cq1", "question": "Which output is consumed?"}],
        "allowed_read_tools": sorted(
            {
                "get_modeling_context",
                "list_semantic_validation_runs",
                "get_semantic_validation_run",
                "list_semantic_reasoning_runs",
                "get_semantic_reasoning_run",
            }
        ),
        "modeling_receipts": receipts,
        "timeout_seconds": 60,
        "quality_standard_ref": "docs/requirements/requirements-v2.3.md#R2.3-005",
        "quality_standard_digest": "c" * 64,
        "quality_standard_artifact": artifact,
        "unknown_policy": "preserve-explicit-unknown",
        "ticket_revision": 1,
        "ticket_digest": None,
    }
    digest = ticket_digest(ticket)
    ticket["ticket_digest"] = digest
    for receipt in ticket["modeling_receipts"]:
        receipt["evidence_ref"]["ticket_digest"] = digest
    return ticket


def _report(ticket: dict, handle, *, kind: str, conclusion: str = "confirmed") -> dict:
    if kind == "source":
        evidence_refs = [{
            "type": "approved_source",
            "ref_id": "source-ref",
            "ticket_digest": ticket["ticket_digest"],
            "source_bundle_digest": ticket["source_bundle_digest"],
            "location": "source.md#answer",
            "artifact_path": "evidence/source.md",
            "artifact_digest": "b" * 64,
        }]
        source_bundle_digest = ticket["source_bundle_digest"]
    else:
        evidence_refs = [{
            "type": "platform_read",
            "ref_id": "platform-ref",
            "ticket_digest": ticket["ticket_digest"],
            "model_state_digest": ticket["model_state_digest"],
            "tool": "get_modeling_context",
            "request_digest": "e" * 64,
            "response_digest": "f" * 64,
            "artifact_path": "evidence/platform.json",
            "page": {
                "ordinal": 0,
                "input_cursor": None,
                "output_cursor": None,
                "has_more": False,
                "sequence_complete": True,
            },
        }]
        source_bundle_digest = None
    return {
        "task_id": ticket["task_id"],
        "acceptance_round_id": ticket["acceptance_round_id"],
        "ticket_digest": ticket["ticket_digest"],
        "examiner_kind": kind,
        "child_handle_digest": handle.digest,
        "child_session_id": handle.session_id,
        "child_input_digest": handle.input_digest,
        "source_bundle_digest": source_bundle_digest,
        "answerability": "answerable",
        "conclusion": conclusion,
        "evidence": [{"ref_id": evidence_refs[0]["ref_id"], "summary": "bound evidence"}],
        "coverage": {"queries_or_sections": ["cq1"], "complete": True},
        "gaps": [],
        "model_state": ticket["model_state"],
        "evidence_refs": evidence_refs,
        "report_digest": None,
    }


def _pass_verdict(ticket: dict, source: dict, platform: dict) -> dict:
    evidence_refs = [source["evidence_refs"][0], platform["evidence_refs"][0]]
    verdict = {
        "schema_version": "r2-3-005-acceptance-verdict/v1",
        "task_id": ticket["task_id"],
        "acceptance_round_id": ticket["acceptance_round_id"],
        "question_id": ticket["question_id"],
        "slice_id": ticket["slice_id"],
        "slice_revision": ticket["slice_revision"],
        "ticket_id": ticket["ticket_id"],
        "ticket_digest": ticket["ticket_digest"],
        "quality_standard_digest": ticket["quality_standard_digest"],
        "quality_standard_artifact": ticket["quality_standard_artifact"],
        "model_state": ticket["model_state"],
        "model_state_digest": ticket["model_state_digest"],
        "source_bundle_digest": ticket["source_bundle_digest"],
        "modeling_receipts": ticket["modeling_receipts"],
        "source_report_digest": source["report_digest"],
        "platform_report_digest": platform["report_digest"],
        "failure_evidence_digests": [],
        "infrastructure_failure_digests": [],
        "failure_evidence_refs": [],
        "verdict": "PASS",
        "failure_layer": None,
        "blocked_reason": None,
        "evidence_refs": evidence_refs,
        "checks": {key: "PASS" for key in ("source_fidelity", "scope", "ontology_structure", "explicit_unknowns", "validation_reasoning", "governed_retrieval", "evidence_lineage", "competency_questions")},
        "competency_question_results": [{
            "id": ticket["question_id"],
            "status": "PASS",
            "answer": source["conclusion"],
            "evidence_refs": evidence_refs,
        }],
        "recommended_action": "advance",
        "summary": "source and platform agree",
        "verdict_digest": None,
    }
    verdict["verdict_digest"] = verdict_digest(verdict)
    return verdict


def _blocked_verdict(
    ticket: dict,
    *,
    platform_report: dict | None,
    failure_refs: list[dict],
) -> dict:
    """Build the smallest canonical runtime-infrastructure BLOCKED envelope."""
    failure_digests = [ref["failure_digest"] for ref in failure_refs]
    verdict = {
        "schema_version": "r2-3-005-acceptance-verdict/v1",
        "task_id": ticket["task_id"],
        "acceptance_round_id": ticket["acceptance_round_id"],
        "question_id": ticket["question_id"],
        "slice_id": ticket["slice_id"],
        "slice_revision": ticket["slice_revision"],
        "ticket_id": ticket["ticket_id"],
        "ticket_digest": ticket["ticket_digest"],
        "quality_standard_digest": ticket["quality_standard_digest"],
        "quality_standard_artifact": ticket["quality_standard_artifact"],
        "model_state": ticket["model_state"],
        "model_state_digest": ticket["model_state_digest"],
        "source_bundle_digest": ticket["source_bundle_digest"],
        "modeling_receipts": ticket["modeling_receipts"],
        "source_report_digest": None,
        "platform_report_digest": platform_report.get("report_digest") if platform_report else None,
        "failure_evidence_digests": failure_digests,
        "infrastructure_failure_digests": failure_digests,
        "failure_evidence_refs": failure_refs,
        "verdict": "BLOCKED",
        "failure_layer": "runtime",
        "blocked_reason": "runtime-infrastructure",
        "evidence_refs": [],
        "checks": {
            key: ("BLOCKED" if key == "validation_reasoning" else "PASS")
            for key in (
                "source_fidelity",
                "scope",
                "ontology_structure",
                "explicit_unknowns",
                "validation_reasoning",
                "governed_retrieval",
                "evidence_lineage",
                "competency_questions",
            )
        },
        "competency_question_results": [
            {
                "id": ticket["question_id"],
                "status": "BLOCKED",
                "answer": "验收运行时基础设施失败，当前无法回答。",
                "evidence_refs": [],
            }
        ],
        "recommended_action": "retry-after-recovery",
        "summary": "child runtime failure requires bounded recovery",
        "verdict_digest": None,
    }
    verdict["verdict_digest"] = verdict_digest(verdict)
    return verdict


class R23005ContractTests(unittest.TestCase):
    def test_platform_scope_accepts_live_uuid_shape_and_rejects_non_platform_ids(self) -> None:
        scope = {
            "project_id": "289e3e51-f8a7-4e92-b279-55a940d3462b",
            "ontology_id": "2469c710-8d7b-4269-ba81-6ee66bd696c8",
            "graph_set_id": "553b91e4-785e-5816-a979-290a3d706c0b",
        }
        self.assertEqual(validate_platform_read_scope(scope), scope)
        short_scope = {"project_id": "a", "ontology_id": "b", "graph_set_id": "c"}
        self.assertEqual(validate_platform_read_scope(short_scope), short_scope)

        for field in scope:
            for invalid in ("", "A" + "a" * 35, "a_b", "a/b", "-abc", "abc-"):
                with self.subTest(field=field, invalid=invalid), self.assertRaisesRegex(
                    AcceptanceContractError, "safe platform identifier"
                ):
                    validate_platform_read_scope({**scope, field: invalid})

    def test_formal_scope_is_fresh_create_only(self) -> None:
        self.assertEqual(normalize_formal_scope({"mode": "create"}), {"mode": "create"})
        for value in (
            {"mode": "existing", "project_id": "project-1", "ontology_id": "ontology-1"},
            {"mode": "create", "project_id": "project-1"},
            {"mode": "create", "graph_set_id": "graph-1"},
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                Exception, "formal scope|unsupported fields"
            ):
                normalize_formal_scope(value)

    def test_formal_runner_preflight_fails_before_run_or_scope_side_effects(self) -> None:
        root = repository_root()
        run_id = f"r23005-preflight-{__import__('uuid').uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        calls: list[str] = []

        def scope_factory(_run):
            calls.append("scope")
            raise AssertionError("scope must not be constructed before preflight")

        def failing_preflight(**_kwargs):
            calls.append("canonical")
            raise TeamConfigurationError("canonical-mode preflight blocked")

        runner = TeamRunner(
            repository_root=root,
            adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
            scope_factory=scope_factory,
            freeze_started_at=datetime.now(UTC).isoformat(),
            prestart_preflight=failing_preflight,
        )
        try:
            with patch(
                "modeling_team.preflight.capture_clean_checkout",
                return_value={
                    "repository_root": str(root),
                    "head": "a" * 40,
                    "status_porcelain": "",
                    "status_digest": "b" * 64,
                },
            ), self.assertRaisesRegex(TeamConfigurationError, "canonical-mode"):
                runner.prepare(
                    run_id=run_id,
                    profile_path=root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
                    task_path=root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
                    scope={"mode": "create"},
                )
            self.assertEqual(calls, ["canonical"])
            self.assertIsNone(runner.run)
            self.assertFalse(run_root.exists())
            self.assertFalse(runner._ledger)
        finally:
            runner.cleanup()

    def test_formal_runner_stages_preflight_and_normalizes_scope_after_clean_gate(self) -> None:
        root = repository_root()
        run_id = f"r23005-preflight-success-{__import__('uuid').uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        ledger_root = Path(tempfile.mkdtemp()) / "ledger"
        runner = TeamRunner(
            repository_root=root,
            adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
            ledger_factory=lambda *, root, config, now: StartLedger(root, config=config, now=now),
            freeze_started_at=datetime.now(UTC).isoformat(),
            prestart_preflight=lambda **_kwargs: {
                "status_code": 200,
                "product_write_mode": "rdf_primary",
            },
        )
        # Temporary tests may redirect the canonical-root resolver, but the
        # factory must still construct the ledger at the root Runner supplies.
        runner._canonical_ledger_root = lambda: ledger_root
        try:
            with patch(
                "modeling_team.preflight.capture_clean_checkout",
                return_value={
                    "repository_root": str(root),
                    "head": "a" * 40,
                    "status_porcelain": "",
                    "status_digest": "b" * 64,
                },
            ):
                run = runner.prepare(
                    run_id=run_id,
                    profile_path=root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
                    task_path=root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
                    scope={"mode": "create"},
                )
            self.assertIsNotNone(runner._candidate_progress)
            self.assertEqual(runner._candidate_progress.timeout_seconds, 300.0)
            self.assertEqual(run.scope, {"mode": "create"})
            evidence = json.loads(
                (run.root / "evidence" / "prestart-preflight.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["canonical"]["product_write_mode"], "rdf_primary")
            self.assertTrue((run.root / "baseline-manifest.json").is_file())
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)

    def test_service_probe_requests_only_safe_scalar_properties(self) -> None:
        output = "ActiveState=active\nSubState=running\nMainPID=4242\nActiveEnterTimestamp=Mon 2026-08-03 00:00:00 UTC\n"
        with patch.object(preflight_module, "_run_checked", return_value=output) as checked:
            service = preflight_module._service_probe()
        self.assertEqual(checked.call_count, 1)
        command = checked.call_args.args[0]
        self.assertIn("--property=ActiveState,SubState,MainPID,ActiveEnterTimestamp", command)
        self.assertNotIn("Environment", command)
        self.assertNotIn("FragmentPath", command)
        self.assertEqual(set(service), {"unit", "active_state", "sub_state", "main_pid", "active_enter_timestamp"})

    def test_formal_runner_timeout_defaults_to_120_when_profile_omits_parameter(self) -> None:
        root = repository_root()
        run_id = f"r23005-timeout-default-{__import__('uuid').uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        ledger_root = Path(tempfile.mkdtemp()) / "ledger"
        profile_root = Path(tempfile.mkdtemp())
        profile_path = profile_root / "formal-profile.yaml"
        profile_path.write_text(
            (root / "modeling_team/profiles/r2-3-005-modeling-team.yaml")
            .read_text(encoding="utf-8")
            .replace("  candidate_progress_timeout_seconds: 300\n", ""),
            encoding="utf-8",
        )
        runner = TeamRunner(
            repository_root=root,
            adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
            ledger_factory=lambda *, root, config, now: StartLedger(root, config=config, now=now),
            freeze_started_at=datetime.now(UTC).isoformat(),
            prestart_preflight=lambda **_kwargs: {
                "status_code": 200,
                "product_write_mode": "rdf_primary",
            },
        )
        runner._canonical_ledger_root = lambda: ledger_root
        try:
            with patch(
                "modeling_team.preflight.capture_clean_checkout",
                return_value={
                    "repository_root": str(root),
                    "head": "a" * 40,
                    "status_porcelain": "",
                    "status_digest": "b" * 64,
                },
            ):
                runner.prepare(
                    run_id=run_id,
                    profile_path=profile_path,
                    task_path=root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
                    scope={"mode": "create"},
                )
            self.assertIsNotNone(runner._candidate_progress)
            self.assertEqual(runner._candidate_progress.timeout_seconds, 120.0)
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)
            rmtree(profile_root)

    def test_preflight_health_and_canonical_failures_are_read_only_and_path_safe(self) -> None:
        service = {
            "unit": "ontology-platform.service",
            "active_state": "active",
            "sub_state": "running",
            "main_pid": 4242,
            "active_enter_timestamp": "started",
        }
        process = {
            "unit": "ontology-platform.service",
            "pid": 4242,
            "started_at": "started",
            "cwd_digest": "a" * 64,
            "command_digest": "b" * 64,
            "cgroup_digest": "c" * 64,
            "process_env": {
                "SEMANTIC_CANONICAL_STORE": "rdf",
                "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                "SEMANTIC_READ_MODE": "canonical",
            },
        }
        with patch.object(preflight_module, "_service_probe", return_value=service), patch.object(
            preflight_module, "_process_probe", return_value=process
        ), patch.object(
            preflight_module,
            "_health_probe",
            side_effect=[TeamConfigurationError("backend health preflight failed")],
        ), self.assertRaisesRegex(TeamConfigurationError, "backend health"):
            preflight_module.canonical_platform_preflight(admin_key="delivery-secret")

        with patch.object(preflight_module, "_service_probe", return_value=service), patch.object(
            preflight_module, "_process_probe", return_value=process
        ), patch.object(
            preflight_module,
            "_health_probe",
            side_effect=[
                {"endpoint_role": "backend-health", "status_code": 200, "body_digest": "d" * 64},
                TeamConfigurationError("frontend health preflight failed"),
            ],
        ), self.assertRaisesRegex(TeamConfigurationError, "frontend health"):
            preflight_module.canonical_platform_preflight(admin_key="delivery-secret")

        with patch.object(preflight_module, "_service_probe", return_value=service), patch.object(
            preflight_module, "_process_probe", return_value=process
        ), patch.object(
            preflight_module,
            "_health_probe",
            side_effect=[
                {"endpoint_role": "backend-health", "status_code": 200, "body_digest": "d" * 64},
                {"endpoint_role": "frontend-root", "status_code": 200, "body_digest": "e" * 64},
            ],
        ), patch.object(
            preflight_module,
            "_canonical_http_get",
            return_value=(503, {"product_write_mode": "legacy_only"}),
        ), self.assertRaisesRegex(TeamConfigurationError, "canonical-mode"):
            preflight_module.canonical_platform_preflight(admin_key="delivery-secret")

        with patch.object(
            preflight_module,
            "capture_clean_checkout",
            return_value={"head": "a" * 40, "status_porcelain": "", "status_digest": "b" * 64},
        ):
            evidence = preflight_module.run_prestart_preflight(
                repository_root=repository_root(),
                probe=lambda **_kwargs: {
                    "status_code": 200,
                    "product_write_mode": "rdf_primary",
                    "path": "/tmp/private-source",
                    "secret": "delivery-secret",
                },
            )
        encoded = json.dumps(evidence, ensure_ascii=False)
        self.assertNotIn("/tmp/private-source", encoded)
        self.assertNotIn("delivery-secret", encoded)
        self.assertNotIn("repository_root", encoded)

    def test_health_probe_hashes_raw_bytes_before_canonical_gate_and_hides_errors(self) -> None:
        service = {
            "unit": "ontology-platform.service",
            "active_state": "active",
            "sub_state": "running",
            "main_pid": 4242,
            "active_enter_timestamp": "started",
        }
        process = {
            "unit": "ontology-platform.service",
            "pid": 4242,
            "started_at": "started",
            "cwd_digest": "a" * 64,
            "command_digest": "b" * 64,
            "cgroup_digest": "c" * 64,
            "process_env": {
                "SEMANTIC_CANONICAL_STORE": "rdf",
                "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                "SEMANTIC_READ_MODE": "canonical",
            },
        }
        backend_body = b'{"status":"ok"}'
        frontend_body = b"<html>ready</html>"
        with patch.object(preflight_module, "_service_probe", return_value=service), patch.object(
            preflight_module, "_process_probe", return_value=process
        ), patch.object(
            preflight_module,
            "_public_http_get",
            side_effect=[(200, backend_body), (200, frontend_body)],
        ) as public_get, patch.object(
            preflight_module,
            "_canonical_http_get",
            return_value=(200, {"product_write_mode": "rdf_primary"}),
        ) as canonical_get:
            evidence = preflight_module.canonical_platform_preflight(
                base_url="http://127.0.0.1:8001",
                admin_key="delivery-secret",
            )
        self.assertEqual(public_get.call_count, 2)
        self.assertEqual(canonical_get.call_count, 1)
        self.assertEqual(
            evidence["health"]["backend"]["body_digest"],
            hashlib.sha256(backend_body).hexdigest(),
        )
        self.assertEqual(
            evidence["health"]["frontend"]["body_digest"],
            hashlib.sha256(frontend_body).hexdigest(),
        )
        with patch.object(
            preflight_module,
            "_public_http_get",
            return_value=(503, b"private-health-response"),
        ), self.assertRaisesRegex(TeamConfigurationError, "backend-health health") as caught:
            preflight_module._health_probe(
                "http://127.0.0.1:8001",
                path="/api/health",
                endpoint_role="backend-health",
            )
        self.assertNotIn("private-health-response", str(caught.exception))

    def test_runner_health_failure_consumes_no_ledger_or_run_root(self) -> None:
        root = repository_root()
        run_id = f"r23005-health-block-{__import__('uuid').uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        ledger_root = Path(tempfile.mkdtemp()) / "ledger"
        runner = TeamRunner(
            repository_root=root,
            adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
            ledger_factory=lambda *, root, config, now: StartLedger(root, config=config, now=now),
            freeze_started_at=datetime.now(UTC).isoformat(),
        )
        runner._canonical_ledger_root = lambda: ledger_root
        try:
            with patch.object(
                preflight_module,
                "capture_clean_checkout",
                return_value={"head": "a" * 40, "status_porcelain": "", "status_digest": "b" * 64},
            ), patch.object(
                preflight_module,
                "canonical_platform_preflight",
                side_effect=TeamConfigurationError("frontend health preflight failed"),
            ), self.assertRaisesRegex(TeamConfigurationError, "frontend health"):
                runner.prepare(
                    run_id=run_id,
                    profile_path=root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
                    task_path=root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
                    scope={"mode": "create"},
                )
            self.assertFalse(run_root.exists())
            self.assertFalse(ledger_root.exists())
        finally:
            runner.cleanup()

    def test_cli_auth_preflight_runs_after_runner_prepare(self) -> None:
        from modeling_team import __main__ as team_main

        events: list[str] = []

        class Adapter:
            def preflight_host_auth(self):
                events.append("auth")

        class Runner:
            def __init__(self, **_kwargs):
                events.append("runner-init")
                self.run = None

            def prepare(self, **_kwargs):
                events.append("prepare")

            def start(self):
                events.append("start")
                raise KeyboardInterrupt

            def cleanup(self):
                events.append("cleanup")

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            scope = base / "scope.yaml"
            scope.write_text("mode: create\n", encoding="utf-8")
            configuration = SimpleNamespace(
                profile=SimpleNamespace(profile_id="legacy-test"),
                task=SimpleNamespace(schema_version=1, task_id="legacy-test"),
            )
            argv = [
                "modeling-team",
                "run",
                "--profile",
                str(base / "profile.yaml"),
                "--task",
                str(base / "task.yaml"),
                "--run-id",
                "r23005-ordering",
                "--scope",
                str(scope),
            ]
            with patch.object(team_main, "repository_root", return_value=base), patch.object(
                team_main, "load_formal_team_configuration", return_value=configuration
            ), patch.object(team_main, "_bootstrap_helpers", return_value=(lambda: ("key", "id"), lambda _id: True)), patch.object(
                team_main, "CodexRuntimeAdapter", return_value=Adapter()
            ), patch.object(team_main, "TeamRunner", side_effect=Runner), patch.object(
                team_main.sys, "argv", argv
            ):
                self.assertEqual(team_main.main(), 130)
        self.assertEqual(events, ["runner-init", "prepare", "auth", "start", "cleanup"])

    def test_formal_cli_scrubs_admin_env_before_auth_bootstrap_and_process(self) -> None:
        from modeling_team import __main__ as team_main

        secret = "r23005-fixed-formal-admin-secret"
        env_name = "ONTOLOGY_PLATFORM_ADMIN_API_KEY"
        events: list[tuple[str, str | None, str | None]] = []
        runner_holder: list[object] = []

        def observe(label: str, runner_key: str | None = None) -> None:
            events.append((label, os.environ.get(env_name), runner_key))

        class Adapter:
            def preflight_host_auth(self) -> None:
                observe("adapter-auth")

            def process_factory(self, *_args, **_kwargs) -> SimpleNamespace:
                observe("process-factory")
                return SimpleNamespace()

        class Runner:
            def __init__(self, **kwargs):
                self.adapter = kwargs["adapter"]
                self.canonical_admin_key = os.environ.get(env_name)
                self.run = None
                self.scope_factory = kwargs.get("scope_factory")
                runner_holder.append(self)
                observe("runner-init", self.canonical_admin_key)

            def prepare(self, **_kwargs) -> None:
                observe("prepare", self.canonical_admin_key)

                def probe(**probe_kwargs):
                    observe("preflight-seam", probe_kwargs.get("admin_key"))
                    return {"status_code": 200, "product_write_mode": "rdf_primary"}

                with patch.object(
                    preflight_module,
                    "capture_clean_checkout",
                    return_value={"head": "a" * 40, "status_porcelain": "", "status_digest": "b" * 64},
                ):
                    evidence = preflight_module.run_prestart_preflight(
                        repository_root=base,
                        admin_key=self.canonical_admin_key,
                        probe=probe,
                    )
                run_root = base / "run"
                (run_root / "evidence").mkdir(parents=True)
                safe_payload = json.dumps(evidence, sort_keys=True)
                for relative in (
                    "evidence/prestart-preflight.json",
                    "config.json",
                    "manifest.json",
                ):
                    path = run_root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(safe_payload, encoding="utf-8")
                self.run = SimpleNamespace(root=run_root)

            def start(self) -> None:
                observe("runner-start", self.canonical_admin_key)
                self.adapter.process_factory(["synthetic"])
                raise TeamConfigurationError("formal start blocked")

            def cleanup(self) -> None:
                observe("cleanup", self.canonical_admin_key)

        def bootstrap(_root: Path):
            observe("bootstrap")
            return (lambda: ("key", "id"), lambda _key_id: True)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            scope = base / "scope.yaml"
            scope.write_text("mode: create\n", encoding="utf-8")
            configuration = SimpleNamespace(
                profile=SimpleNamespace(profile_id="r2-3-005-modeling-team"),
                task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
            )
            argv = [
                "modeling-team",
                "run",
                "--profile",
                str(base / "profile.yaml"),
                "--task",
                str(base / "task.yaml"),
                "--run-id",
                "r23005-formal-env-scrub",
                "--scope",
                str(scope),
                "--freeze-started-at",
                "2026-08-03T00:00:00+00:00",
            ]
            stderr = io.StringIO()
            with (
                patch.dict(os.environ, {env_name: secret}, clear=False),
                redirect_stderr(stderr),
                patch.object(team_main, "repository_root", return_value=base),
                patch.object(team_main, "load_formal_team_configuration", return_value=configuration),
                patch.object(team_main, "_bootstrap_helpers", side_effect=bootstrap),
                patch.object(team_main, "CodexRuntimeAdapter", return_value=Adapter()),
                patch.object(team_main, "TeamRunner", side_effect=Runner),
                patch.object(team_main.sys, "argv", argv),
            ):
                self.assertEqual(team_main.main(), 2)

            self.assertEqual(
                [label for label, _env_value, _runner_key in events],
                [
                    "runner-init",
                    "prepare",
                    "preflight-seam",
                    "adapter-auth",
                    "bootstrap",
                    "runner-start",
                    "process-factory",
                    "cleanup",
                ],
            )
            self.assertEqual(events[1], ("prepare", secret, secret))
            self.assertEqual(events[2], ("preflight-seam", secret, secret))
            for event in events[3:]:
                self.assertIsNone(event[1], event)
                self.assertIsNone(event[2], event)
            self.assertIsNone(getattr(runner_holder[0], "canonical_admin_key"))
            self.assertNotIn(secret, stderr.getvalue())
            run_root = base / "run"
            for path in run_root.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret, path.read_text(encoding="utf-8"))

    def test_formal_cli_prepare_failure_never_reaches_auth_bootstrap_or_start(self) -> None:
        from modeling_team import __main__ as team_main

        secret = "r23005-fixed-formal-admin-secret"
        env_name = "ONTOLOGY_PLATFORM_ADMIN_API_KEY"
        events: list[tuple[str, str | None]] = []

        class Adapter:
            def preflight_host_auth(self) -> None:
                raise AssertionError("formal prepare failure must stop before adapter auth")

        class Runner:
            def __init__(self, **_kwargs):
                self.canonical_admin_key = os.environ.get(env_name)
                self.run = None
                events.append(("runner-init", os.environ.get(env_name)))

            def prepare(self, **_kwargs) -> None:
                events.append(("prepare", os.environ.get(env_name)))
                raise TeamConfigurationError("formal preflight blocked")

            def start(self) -> None:
                raise AssertionError("formal prepare failure must stop before runner start")

            def cleanup(self) -> None:
                events.append(("cleanup", os.environ.get(env_name)))

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            scope = base / "scope.yaml"
            scope.write_text("mode: create\n", encoding="utf-8")
            configuration = SimpleNamespace(
                profile=SimpleNamespace(profile_id="r2-3-005-modeling-team"),
                task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
            )
            argv = [
                "modeling-team",
                "run",
                "--profile",
                str(base / "profile.yaml"),
                "--task",
                str(base / "task.yaml"),
                "--run-id",
                "r23005-formal-env-failure",
                "--scope",
                str(scope),
                "--freeze-started-at",
                "2026-08-03T00:00:00+00:00",
            ]
            stderr = io.StringIO()
            with (
                patch.dict(os.environ, {env_name: secret}, clear=False),
                redirect_stderr(stderr),
                patch.object(team_main, "repository_root", return_value=base),
                patch.object(team_main, "load_formal_team_configuration", return_value=configuration),
                patch.object(
                    team_main,
                    "_bootstrap_helpers",
                    side_effect=AssertionError("formal prepare failure must stop before bootstrap"),
                ),
                patch.object(team_main, "CodexRuntimeAdapter", return_value=Adapter()),
                patch.object(team_main, "TeamRunner", side_effect=Runner),
                patch.object(team_main.sys, "argv", argv),
            ):
                self.assertEqual(team_main.main(), 2)
            self.assertEqual(
                events,
                [("runner-init", secret), ("prepare", secret), ("cleanup", secret)],
            )
            self.assertIn("formal preflight blocked", stderr.getvalue())
            self.assertNotIn(secret, stderr.getvalue())

    def test_nonformal_cli_preserves_admin_env_for_existing_path(self) -> None:
        from modeling_team import __main__ as team_main

        secret = "r23005-fixed-nonformal-admin-secret"
        env_name = "ONTOLOGY_PLATFORM_ADMIN_API_KEY"
        events: list[tuple[str, str | None]] = []

        class Adapter:
            def preflight_host_auth(self) -> None:
                events.append(("adapter-auth", os.environ.get(env_name)))

            def process_factory(self, *_args, **_kwargs) -> SimpleNamespace:
                events.append(("process-factory", os.environ.get(env_name)))
                return SimpleNamespace()

        class Runner:
            def __init__(self, **kwargs):
                self.adapter = kwargs["adapter"]
                self.canonical_admin_key = os.environ.get(env_name)
                self.run = None
                events.append(("runner-init", os.environ.get(env_name)))

            def prepare(self, **_kwargs) -> None:
                events.append(("prepare", os.environ.get(env_name)))

            def start(self) -> None:
                events.append(("runner-start", os.environ.get(env_name)))
                self.adapter.process_factory(["synthetic"])
                raise TeamConfigurationError("nonformal start blocked")

            def cleanup(self) -> None:
                events.append(("cleanup", os.environ.get(env_name)))

        def bootstrap(_root: Path):
            events.append(("bootstrap", os.environ.get(env_name)))
            return (lambda: ("key", "id"), lambda _key_id: True)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            scope = base / "scope.yaml"
            scope.write_text("mode: create\n", encoding="utf-8")
            configuration = SimpleNamespace(
                profile=SimpleNamespace(profile_id="legacy-test"),
                task=SimpleNamespace(schema_version=1, task_id="legacy-test"),
            )
            argv = [
                "modeling-team",
                "run",
                "--profile",
                str(base / "profile.yaml"),
                "--task",
                str(base / "task.yaml"),
                "--run-id",
                "r23005-nonformal-env-preserve",
                "--scope",
                str(scope),
            ]
            stderr = io.StringIO()
            with (
                patch.dict(os.environ, {env_name: secret}, clear=False),
                redirect_stderr(stderr),
                patch.object(team_main, "repository_root", return_value=base),
                patch.object(team_main, "load_formal_team_configuration", return_value=configuration),
                patch.object(team_main, "_bootstrap_helpers", side_effect=bootstrap),
                patch.object(team_main, "CodexRuntimeAdapter", return_value=Adapter()),
                patch.object(team_main, "TeamRunner", side_effect=Runner),
                patch.object(team_main.sys, "argv", argv),
            ):
                self.assertEqual(team_main.main(), 2)
            self.assertEqual(
                [label for label, _value in events],
                [
                    "bootstrap",
                    "runner-init",
                    "prepare",
                    "adapter-auth",
                    "runner-start",
                    "process-factory",
                    "cleanup",
                ],
            )
            self.assertTrue(all(value == secret for _label, value in events))
            self.assertIn("nonformal start blocked", stderr.getvalue())
            self.assertNotIn(secret, stderr.getvalue())

    def test_ticket_schema_location_hints_and_explicit_unknown_policy(self) -> None:
        ticket = _ticket()
        self.assertEqual(validate_ticket(ticket)["acceptance_round_id"], "round-r23005-1")
        with self.assertRaises(AcceptanceContractError):
            validate_ticket({**ticket, "expected_answer": "hidden"})

        hint = validate_location_hint(
            {
                "path": "source.md",
                "document_range": "L1-L3",
                "section": "Answer basis",
                "keywords": ["output"],
                "format": "markdown",
                "read_method": "bounded excerpt",
            },
            approved_paths={"source.md"},
        )
        self.assertEqual(hint["path"], "source.md")
        with self.assertRaises(AcceptanceContractError):
            validate_location_hint({"path": "unapproved.md"}, approved_paths={"source.md"})
        with self.assertRaises(AcceptanceContractError):
            validate_location_hint({"answer": "not a location hint"}, approved_paths={"source.md"})

    def test_report_unknown_and_platform_completeness_fail_closed(self) -> None:
        ticket = _ticket()
        handle = SimpleNamespace(
            digest="a" * 64,
            session_id="examiner-session",
            input_digest="b" * 64,
        )
        source = _report(ticket, handle, kind="source")
        source["answerability"] = "insufficient-evidence"
        source["conclusion"] = "因缺少相关证据无法回答"
        source["gaps"] = ["release behavior is not specified"]
        source["report_digest"] = report_digest(source)
        self.assertEqual(
            validate_report(
                source,
                ticket=ticket,
                kind="source",
                handle_digest=handle.digest,
                input_digest=handle.input_digest,
                session_id=handle.session_id,
            )["answerability"],
            "insufficient-evidence",
        )
        unsupported = dict(source)
        unsupported["conclusion"] = "unsupported guess"
        unsupported["report_digest"] = report_digest(unsupported)
        with self.assertRaises(AcceptanceContractError):
            validate_report(
                unsupported,
                ticket=ticket,
                kind="source",
                handle_digest=handle.digest,
                input_digest=handle.input_digest,
                session_id=handle.session_id,
            )

        platform = _report(ticket, handle, kind="platform")
        platform["evidence_refs"] = []
        platform["report_digest"] = report_digest(platform)
        with self.assertRaises(AcceptanceContractError):
            validate_report(
                platform,
                ticket=ticket,
                kind="platform",
                handle_digest=handle.digest,
                input_digest=handle.input_digest,
                session_id=handle.session_id,
            )

        outside_tool = _report(ticket, handle, kind="platform")
        outside_tool["evidence_refs"][0]["tool"] = "run_semantic_reasoning"
        outside_tool["report_digest"] = report_digest(outside_tool)
        with self.assertRaises(AcceptanceContractError):
            validate_report(
                outside_tool,
                ticket=ticket,
                kind="platform",
                handle_digest=handle.digest,
                input_digest=handle.input_digest,
                session_id=handle.session_id,
            )

        outside_source = _report(ticket, handle, kind="source")
        outside_source["evidence_refs"][0]["location"] = "unapproved.md#answer"
        outside_source["report_digest"] = report_digest(outside_source)
        with self.assertRaises(AcceptanceContractError):
            validate_report(
                outside_source,
                ticket=ticket,
                kind="source",
                handle_digest=handle.digest,
                input_digest=handle.input_digest,
                session_id=handle.session_id,
            )

    def test_classification_distinguishes_semantic_gap_unknown_and_unsupported_text(self) -> None:
        unknown_source = {
            "answerability": "insufficient-evidence",
            "conclusion": "因缺少相关证据无法回答",
            "evidence": [],
        }
        unknown_platform = {
            "answerability": "insufficient-evidence",
            "conclusion": "因缺少相关证据无法回答",
            "evidence": [],
        }
        self.assertEqual(
            classify_comparison(source=unknown_source, platform=unknown_platform),
            ("PASS", "", "advance"),
        )
        source = {"answerability": "answerable", "conclusion": "confirmed", "evidence": [{"id": 1}]}
        unavailable = {"answerability": "unavailable", "conclusion": "", "evidence": []}
        self.assertEqual(
            classify_comparison(source=source, platform=unavailable),
            ("FAIL", "modeling-quality", "model-repair"),
        )
        self.assertEqual(
            classify_comparison(
                source={"answerability": "insufficient-evidence", "conclusion": "guess", "evidence": []},
                platform=unavailable,
            ),
            ("BLOCKED", "acceptance-evidence", "revise-ticket"),
        )

    def test_model_state_and_ticket_digest_bindings_cannot_drift(self) -> None:
        ticket = _ticket()
        with self.assertRaises(AcceptanceContractError):
            validate_model_state({key: value for key, value in ticket["model_state"].items() if key != "graph_set_id"})
        mutated = json.loads(json.dumps(ticket))
        mutated["modeling_receipts"][0]["evidence_ref"]["ticket_digest"] = "e" * 64
        with self.assertRaises(AcceptanceContractError):
            validate_ticket(mutated)

    def test_ticket_digest_preimage_and_projection_are_immutable(self) -> None:
        ticket = _ticket()
        self.assertEqual(validate_ticket(ticket)["ticket_digest"], ticket["ticket_digest"])
        self.assertEqual(ticket_digest(ticket), ticket["ticket_digest"])
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance")
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            source_projection, source_digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            self.assertNotIn("model_state", source_projection)
            platform_projection, _ = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="platform")
            self.assertNotIn("approved_sources", platform_projection)
            source = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=source_projection, input_digest=source_digest, ticket_digest_value=ticket["ticket_digest"], request_id="start-source", attempt=0)
            with self.assertRaises(AcceptanceContractError):
                carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=source_projection, input_digest=source_digest, ticket_digest_value=ticket["ticket_digest"], request_id="start-source-conflict", attempt=0)
            self.assertEqual(source.opaque, source.token)

    def test_readiness_is_non_terminal_and_cannot_settle(self) -> None:
        phases = CoordinatorPhaseController()
        phases.start()
        phases.assign_slice(sender_id="coordinator", objective="one slice")
        generation = phases.generation
        phases.readiness(
            sender_id="modeling",
            message_kind="ready_for_acceptance",
            generation=generation,
        )
        phases.readiness(
            sender_id="protocol",
            message_kind="silent_for_acceptance",
            generation=generation,
        )
        self.assertEqual(phases.phase.value, "WAITING_ACCEPTANCE")
        self.assertTrue(all(not event.get("terminal", False) for event in phases.events if event["event"] == "coordination"))

    def test_canonical_mode_preflight_requires_authenticated_rdf_primary(self) -> None:
        evidence = canonical_mode_preflight(
            response={"product_write_mode": "rdf_primary"},
            status_code=200,
            unit="ontology-platform.service",
            pid=1234,
            started_at="2026-08-03T00:00:00Z",
            process_env={
                "SEMANTIC_CANONICAL_STORE": "rdf",
                "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                "SEMANTIC_READ_MODE": "canonical",
            },
        )
        self.assertEqual(evidence["response"]["product_write_mode"], "rdf_primary")
        with self.assertRaises(AcceptanceContractError):
            canonical_mode_preflight(
                response={"product_write_mode": "legacy"},
                status_code=200,
                unit="ontology-platform.service",
                pid=1234,
                started_at="now",
                process_env={
                    "SEMANTIC_CANONICAL_STORE": "rdf",
                    "SEMANTIC_PRODUCT_WRITE_MODE": "rdf_primary",
                    "SEMANTIC_READ_MODE": "canonical",
                },
            )

    def test_capability_separation_and_opaque_idempotent_child_start(self) -> None:
        ticket = _ticket()
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance")
            coordinator_key = carrier.capability_token("coordinator")
            acceptance_key = carrier.capability_token("acceptance")
            with self.assertRaises(AcceptanceContractError):
                carrier.publish_ticket(ticket, coordinator_id="acceptance", owner_revision=ticket["quality_standard_ref"], capability=coordinator_key)
            carrier.coordinator_publish_acceptance_ticket(ticket, owner_revision=ticket["quality_standard_ref"], capability=coordinator_key)
            with self.assertRaises(AcceptanceContractError):
                carrier.get_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], capability=coordinator_key)
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"], capability=acceptance_key)
            source_projection, source_digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            handle = carrier.start_child(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source",
                input_ref=source_projection, input_digest=source_digest,
                ticket_digest_value=ticket["ticket_digest"], request_id="start-source", attempt=0,
                capability=acceptance_key,
            )
            replay = carrier.start_child(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source",
                input_ref=source_projection, input_digest=source_digest,
                ticket_digest_value=ticket["ticket_digest"], request_id="start-source", attempt=0,
                capability=acceptance_key,
            )
            self.assertEqual(handle, replay)
            self.assertEqual(handle.opaque, handle.token)
            self.assertFalse(hasattr(handle, "pid"))
            with self.assertRaises(AcceptanceContractError):
                carrier.start_child(
                    acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source",
                    input_ref=source_projection, input_digest=source_digest,
                    ticket_digest_value=ticket["ticket_digest"], request_id="start-source-other", attempt=0,
                    capability=acceptance_key,
                )
            with self.assertRaises(AcceptanceContractError):
                carrier.start_child(
                    acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source",
                    input_ref=source_projection, input_digest=source_digest,
                    ticket_digest_value=ticket["ticket_digest"], request_id="start-source-bad-cap", attempt=0,
                    capability=coordinator_key,
                )

    def test_child_report_sink_and_terminal_recycle_are_immutable(self) -> None:
        ticket = _ticket()
        resources = []

        class FakeResource:
            def __init__(self, spec):
                self.spec = spec
                self.stopped = 0
                self.destroyed = 0
                resources.append(self)

            def stop(self):
                self.stopped += 1

            def destroy(self):
                self.destroyed += 1

        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance", child_factory=FakeResource)
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            source_projection, source_digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            handle = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=source_projection, input_digest=source_digest, ticket_digest_value=ticket["ticket_digest"], request_id="source-start", attempt=0)
            sink = carrier.report_sink(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle)
            report = sink.submit(_report(ticket, handle, kind="source"))
            with self.assertRaises(AcceptanceContractError):
                sink.submit(_report(ticket, handle, kind="source", conclusion="changed"))
            report_copy = carrier.get_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, request_id="get-source")
            report_copy["conclusion"] = "mutated"
            self.assertEqual(carrier.get_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, request_id="get-source-2")["conclusion"], report["conclusion"])
            receipt = carrier.recycle_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, completion_ref={"terminal_report_digest": report["report_digest"]}, request_id="recycle-source")
            replay = carrier.recycle_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, completion_ref={"terminal_report_digest": report["report_digest"]}, request_id="recycle-source")
            self.assertEqual(receipt, replay)
            self.assertEqual(receipt.completion_kind, "terminal_report")
            self.assertIn("child-input", receipt.destroyed_resources)
            self.assertEqual(resources[0].stopped, 1)
            self.assertEqual(resources[0].destroyed, 1)

    def test_infrastructure_retry_budget_and_blocked_round_keeps_acceptance_live(self) -> None:
        ticket = _ticket()
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance")
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            source_projection, source_digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            platform_projection, platform_digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="platform")
            source0 = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=source_projection, input_digest=source_digest, ticket_digest_value=ticket["ticket_digest"], request_id="source-0", attempt=0)
            platform = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="platform", input_ref=platform_projection, input_digest=platform_digest, ticket_digest_value=ticket["ticket_digest"], request_id="platform-0", attempt=0)
            failure0 = carrier.record_infrastructure_failure(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=source0, failure_category="timeout", reason_code="child-timeout")
            cleanup0 = carrier.recycle_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=source0, completion_ref={"infrastructure_failure_digest": failure0.failure_digest}, request_id="recycle-source-0")
            source1 = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=source_projection, input_digest=source_digest, ticket_digest_value=ticket["ticket_digest"], request_id="source-1", attempt=1)
            self.assertEqual(source1.input_digest, source0.input_digest)
            self.assertEqual(source1.ticket_digest, source0.ticket_digest)
            self.assertNotEqual(source1.session_id, source0.session_id)
            failure1 = carrier.record_infrastructure_failure(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=source1, failure_category="crash", reason_code="child-crash")
            cleanup1 = carrier.recycle_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=source1, completion_ref={"infrastructure_failure_digest": failure1.failure_digest}, request_id="recycle-source-1")
            with self.assertRaises(AcceptanceContractError):
                carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=source_projection, input_digest=source_digest, ticket_digest_value=ticket["ticket_digest"], request_id="source-2", attempt=2)
            platform_resource = carrier.child_resource_receipt(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=platform)
            private_root = Path(directory) / platform_resource.private_root
            self.assertTrue(private_root.is_dir())
            self.assertIsNotNone(platform_resource.read_key_id)
            assert platform_resource.read_key_id is not None
            self.assertTrue(carrier.key_lifecycle.plaintext_for(platform_resource.read_key_id))
            platform_report = carrier.ingest_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=platform, report=_report(ticket, platform, kind="platform"))
            cleanup_platform = carrier.recycle_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=platform, completion_ref={"terminal_report_digest": platform_report["report_digest"]}, request_id="recycle-platform")
            summary = carrier.round_summary(ticket["acceptance_round_id"])
            self.assertEqual(summary["status"], "blocked")
            self.assertTrue(summary["acceptance_live"])
            self.assertEqual(cleanup0.completion_kind, "infrastructure_failure")
            self.assertEqual(cleanup1.completion_kind, "infrastructure_failure")
            self.assertEqual(cleanup_platform.completion_kind, "terminal_report")
            self.assertEqual(carrier.key_lifecycle.get(platform_resource.read_key_id).status, "revoked")
            self.assertFalse(private_root.exists())
            with self.assertRaises(AcceptanceContractError):
                carrier.key_lifecycle.plaintext_for(platform_resource.read_key_id)
            self.assertEqual(carrier.get_failure_record(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], failure_digest=failure1.failure_digest), failure1)
            carrier.cleanup()
            self.assertFalse(carrier.is_live)

    def test_infrastructure_blocked_verdict_binds_failure_and_cleanup_receipts(self) -> None:
        ticket = _ticket()
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance")
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            projection, digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            source0 = carrier.start_child(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source",
                input_ref=projection, input_digest=digest, ticket_digest_value=ticket["ticket_digest"],
                request_id="blocked-source-0", attempt=0,
            )
            failure0 = carrier.record_infrastructure_failure(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=source0,
                failure_category="timeout", reason_code="child-timeout",
            )
            carrier.recycle_child(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=source0,
                completion_ref={"infrastructure_failure_digest": failure0.failure_digest},
                request_id="blocked-recycle-0",
            )
            source1 = carrier.start_child(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source",
                input_ref=projection, input_digest=digest, ticket_digest_value=ticket["ticket_digest"],
                request_id="blocked-source-1", attempt=1,
            )
            failure1 = carrier.record_infrastructure_failure(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=source1,
                failure_category="crash", reason_code="child-crash",
            )
            cleanup1 = carrier.recycle_child(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=source1,
                completion_ref={"infrastructure_failure_digest": failure1.failure_digest},
                request_id="blocked-recycle-1",
            )
            ref = carrier.failure_evidence_ref(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"],
                failure_digest=failure1.failure_digest,
                cleanup_receipt_digest=cleanup1.receipt_digest,
            )
            verdict = _blocked_verdict(ticket, platform_report=None, failure_refs=[ref])
            receipt = carrier.submit_verdict(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"],
                verdict=verdict, request_id="blocked-verdict",
            )
            self.assertEqual(receipt.verdict, "BLOCKED")
            self.assertEqual(carrier.round_summary(ticket["acceptance_round_id"])["verdict"], "BLOCKED")
            with self.assertRaises(AcceptanceContractError):
                carrier.failure_evidence_ref(
                    acceptance_id="acceptance", round_id=ticket["acceptance_round_id"],
                    failure_digest=failure1.failure_digest,
                    cleanup_receipt_digest=failure0.failure_digest,
                )

    def test_read_only_key_lifecycle_revokes_plaintext_and_allowlist_excludes_writes(self) -> None:
        ticket = _ticket()
        lifecycle = ReadOnlyKeyLifecycle()
        record = lifecycle.create(
            project_id=ticket["model_state"]["project_id"],
            ontology_id=ticket["model_state"]["ontology_id"],
            acceptance_round_id=ticket["acceptance_round_id"],
            ticket_digest_value=ticket["ticket_digest"],
            input_digest="a" * 64,
            config_digest="b" * 64,
        )
        self.assertTrue(lifecycle.plaintext_for(record.key_id))
        self.assertTrue(set(canonical_platform_allowlist()).isdisjoint({"run_semantic_validation", "run_semantic_reasoning"}))
        revoked = lifecycle.revoke(record.key_id)
        self.assertEqual(revoked.status, "revoked")
        with self.assertRaises(AcceptanceContractError):
            lifecycle.plaintext_for(record.key_id)
        lifecycle.assert_no_active()

    def test_report_binding_replay_and_runner_state_envelope_fail_closed(self) -> None:
        ticket = _ticket()
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance")
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            projection, digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            handle = carrier.start_child(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source",
                input_ref=projection, input_digest=digest, ticket_digest_value=ticket["ticket_digest"],
                request_id="report-binding-source", attempt=0,
            )
            self.assertNotIn("model_state", projection)
            bad = _report(ticket, handle, kind="source")
            bad["child_session_id"] = "other-session"
            bad["report_digest"] = report_digest(bad)
            with self.assertRaises(AcceptanceContractError):
                carrier.ingest_report(
                    acceptance_id="acceptance", round_id=ticket["acceptance_round_id"],
                    handle=handle, report=bad,
                )
            valid = carrier.ingest_report(
                acceptance_id="acceptance", round_id=ticket["acceptance_round_id"],
                handle=handle, report=_report(ticket, handle, kind="source"),
            )
            self.assertEqual(valid["model_state"]["state_digest"], ticket["model_state_digest"])
            changed = _report(ticket, handle, kind="source", conclusion="changed")
            with self.assertRaises(AcceptanceContractError):
                carrier.ingest_report(
                    acceptance_id="acceptance", round_id=ticket["acceptance_round_id"],
                    handle=handle, report=changed,
                )

    def test_canonical_round_receipts_standard_binding_and_digest_preimage(self) -> None:
        ticket = _ticket()
        with self.assertRaises(AcceptanceContractError):
            validate_ticket({**ticket, "round_id": ticket["acceptance_round_id"]})
        self.assertEqual({receipt["stage"] for receipt in ticket["modeling_receipts"]}, {"dry-run", "apply", "readback", "validation", "reasoning"})

        source_handle = SimpleNamespace(digest="a" * 64, session_id="source-session", input_digest="b" * 64)
        platform_handle = SimpleNamespace(digest="c" * 64, session_id="platform-session", input_digest="d" * 64)
        source = _report(ticket, source_handle, kind="source")
        platform = _report(ticket, platform_handle, kind="platform")
        source["report_digest"] = report_digest(source)
        platform["report_digest"] = report_digest(platform)
        verdict = _pass_verdict(ticket, source, platform)
        bad_artifact = dict(verdict)
        bad_artifact["quality_standard_artifact"] = {"path": "acceptance/other.json", "digest": "e" * 64}
        bad_artifact["verdict_digest"] = verdict_digest(bad_artifact)
        with self.assertRaises(AcceptanceContractError):
            validate_verdict(bad_artifact, ticket=ticket, source_report=source, platform_report=platform)

        nested_ticket_digest = dict(ticket)
        nested_ticket_digest["ticket_digest"] = "f" * 64
        for receipt in nested_ticket_digest["modeling_receipts"]:
            receipt["evidence_ref"]["ticket_digest"] = "f" * 64
        self.assertEqual(ticket_digest(nested_ticket_digest), ticket["ticket_digest"])
        changed_field = dict(ticket)
        changed_field["question"] = "changed question"
        self.assertNotEqual(ticket_digest(changed_field), ticket["ticket_digest"])

    def test_attempt_one_rejects_changed_input_and_request_ticket_drift(self) -> None:
        ticket = _ticket()
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance")
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            source_projection, source_digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            handle = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=source_projection, input_digest=source_digest, ticket_digest_value=ticket["ticket_digest"], request_id="lineage-source-0", attempt=0)
            failure = carrier.record_infrastructure_failure(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, failure_category="timeout", reason_code="timeout")
            carrier.recycle_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, completion_ref={"infrastructure_failure_digest": failure.failure_digest}, request_id="lineage-recycle-0")
            changed = {**source_projection, "question": "changed question"}
            changed_digest = _sha(changed)
            with self.assertRaisesRegex(AcceptanceContractError, "identical frozen input"):
                carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=changed, input_digest=changed_digest, ticket_digest_value=ticket["ticket_digest"], request_id="lineage-source-1", attempt=1)

    def test_ticket_publish_is_atomic_on_preexisting_symlink_or_write_failure(self) -> None:
        ticket = _ticket()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            carrier = RunnerAcceptanceCarrier(root, task_id=ticket["task_id"], acceptance_id="acceptance")
            path = carrier.acceptance_root / ticket["acceptance_round_id"] / "ticket.json"
            path.parent.mkdir(parents=True)
            path.write_text("existing", encoding="utf-8")
            with self.assertRaises(AcceptanceContractError):
                carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            with self.assertRaises(AcceptanceContractError):
                carrier.get_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"])
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance")
            with patch("modeling_team.acceptance._write_exclusive_json", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            with self.assertRaises(AcceptanceContractError):
                carrier.get_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"])

    def test_verdict_schema_digest_idempotency_and_coordinator_unknown_digest_recovery(self) -> None:
        ticket = _ticket()
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=ticket["task_id"], acceptance_id="acceptance")
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            source_projection, source_digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            platform_projection, platform_digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="platform")
            source = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=source_projection, input_digest=source_digest, ticket_digest_value=ticket["ticket_digest"], request_id="verdict-source", attempt=0)
            platform = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="platform", input_ref=platform_projection, input_digest=platform_digest, ticket_digest_value=ticket["ticket_digest"], request_id="verdict-platform", attempt=0)
            source_report = carrier.ingest_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=source, report=_report(ticket, source, kind="source"))
            platform_report = carrier.ingest_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=platform, report=_report(ticket, platform, kind="platform"))
            verdict = _pass_verdict(ticket, source_report, platform_report)
            receipt = carrier.submit_verdict(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], verdict=verdict, request_id="verdict-submit")
            replay = carrier.submit_verdict(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], verdict=verdict, request_id="verdict-submit")
            self.assertEqual(receipt, replay)
            self.assertEqual(carrier.coordinator_get_verdict(round_id=ticket["acceptance_round_id"]), receipt)
            self.assertEqual(carrier.coordinator_get_verdict(round_id=ticket["acceptance_round_id"], verdict_digest_value=None), receipt)
            changed = dict(verdict)
            changed["summary"] = "different retry"
            changed["verdict_digest"] = verdict_digest(changed)
            with self.assertRaises(AcceptanceContractError):
                carrier.submit_verdict(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], verdict=changed, request_id="different-request")

    def test_typed_evidence_union_and_complete_cursor_chain_fail_closed(self) -> None:
        ticket = _ticket()
        first = {
            "type": "platform_read", "ref_id": "page-a", "ticket_digest": ticket["ticket_digest"],
            "model_state_digest": ticket["model_state_digest"], "tool": "get_modeling_context",
            "request_digest": "e" * 64, "response_digest": "f" * 64, "artifact_path": "evidence/page-a.json",
            "page": {"ordinal": 0, "input_cursor": None, "output_cursor": "cursor-1", "has_more": True, "sequence_complete": False},
        }
        second = {**first, "ref_id": "page-b", "response_digest": "1" * 64, "page": {"ordinal": 1, "input_cursor": "cursor-1", "output_cursor": None, "has_more": False, "sequence_complete": True}}
        self.assertEqual(validate_typed_evidence_ref(first, expected_ticket=ticket["ticket_digest"], expected_state=ticket["model_state_digest"])["ref_id"], "page-a")
        validate_page_chain([first, second])
        broken = {**second, "page": {**second["page"], "input_cursor": "wrong"}}
        with self.assertRaises(AcceptanceContractError):
            validate_page_chain([first, broken])
        with self.assertRaises(AcceptanceContractError):
            validate_typed_evidence_ref({"type": "platform_read", "ref": "generic"})

    def test_scope_shim_rejects_foreign_graph_and_settlement_cas_withholds_drift(self) -> None:
        ticket = _ticket()
        shim = PlatformScopeShim(ticket)
        request = {
            "project_id": ticket["platform_read_scope"]["project_id"],
            "ontology_id": ticket["platform_read_scope"]["ontology_id"],
            "graph_set_id": ticket["platform_read_scope"]["graph_set_id"],
            "tool": "get_modeling_context",
            "ticket_digest": ticket["ticket_digest"],
            "request_digest": None,
        }
        request["request_digest"] = _sha(request)
        self.assertEqual(shim.authorize(request)["graph_set_id"], ticket["platform_read_scope"]["graph_set_id"])
        foreign = {**request, "graph_set_id": "graph-foreign"}
        foreign["request_digest"] = _sha(foreign)
        with self.assertRaises(AcceptanceContractError):
            shim.authorize(foreign)
        cas = SettlementCAS.create(expected_state_digest=ticket["model_state_digest"], workspace_version=ticket["model_state"]["workspace_version"])
        observed = {"state_digest": ticket["model_state_digest"], "workspace_version": ticket["model_state"]["workspace_version"], "phase": "SETTLED", "token": cas.token}
        self.assertEqual(cas.evaluate(observed, post_cleanup=observed)["status"], "settled")
        drifted = {**observed, "workspace_version": "workspace-drift"}
        result = cas.commit(observed, post_cleanup=drifted)
        self.assertEqual(result["status"], "withheld")
        self.assertTrue(result["rerun_competency_questions"])

    def test_model_state_boundary_invalidates_all_old_passes_and_unsupported_text_is_fail(self) -> None:
        ticket = _ticket()
        boundary = ModelStateBoundary(ticket["model_state"])
        boundary.record_pass("a" * 64)
        changed = {**ticket["model_state"], "workspace_version": "workspace-2"}
        changed["state_digest"] = model_state_digest(changed)
        self.assertFalse(boundary.revalidate(changed, boundary="before-next-cq"))
        self.assertTrue(boundary.invalidated)
        self.assertEqual(boundary.old_passes, [])
        source = {"answerability": "answerable", "conclusion": "same", "evidence": []}
        platform = {"answerability": "answerable", "conclusion": "same", "evidence": []}
        self.assertEqual(classify_comparison(source=source, platform=platform), ("FAIL", "modeling-quality", "model-repair"))

    def test_round_two_requires_round_one_cleanup_and_cleanup_is_idempotent(self) -> None:
        first, second = _ticket("1"), _ticket("2")
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory), task_id=first["task_id"], acceptance_id="acceptance")
            for ticket in (first, second):
                carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
                carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            projection, digest = carrier.project_child_input(round_id=first["acceptance_round_id"], kind="source")
            source1 = carrier.start_child(acceptance_id="acceptance", round_id=first["acceptance_round_id"], kind="source", input_ref=projection, input_digest=digest, ticket_digest_value=first["ticket_digest"], request_id="round1-source", attempt=0)
            second_projection, second_digest = carrier.project_child_input(round_id=second["acceptance_round_id"], kind="source")
            with self.assertRaises(AcceptanceContractError):
                carrier.start_child(acceptance_id="acceptance", round_id=second["acceptance_round_id"], kind="source", input_ref=second_projection, input_digest=second_digest, ticket_digest_value=second["ticket_digest"], request_id="round2-before-cleanup", attempt=0)
            report = carrier.ingest_report(acceptance_id="acceptance", round_id=first["acceptance_round_id"], handle=source1, report=_report(first, source1, kind="source"))
            carrier.recycle_child(acceptance_id="acceptance", round_id=first["acceptance_round_id"], handle=source1, completion_ref={"terminal_report_digest": report["report_digest"]}, request_id="round1-recycle-source")
            platform_projection, platform_digest = carrier.project_child_input(round_id=first["acceptance_round_id"], kind="platform")
            platform1 = carrier.start_child(acceptance_id="acceptance", round_id=first["acceptance_round_id"], kind="platform", input_ref=platform_projection, input_digest=platform_digest, ticket_digest_value=first["ticket_digest"], request_id="round1-platform", attempt=0)
            platform_report = carrier.ingest_report(acceptance_id="acceptance", round_id=first["acceptance_round_id"], handle=platform1, report=_report(first, platform1, kind="platform"))
            carrier.recycle_child(acceptance_id="acceptance", round_id=first["acceptance_round_id"], handle=platform1, completion_ref={"terminal_report_digest": platform_report["report_digest"]}, request_id="round1-recycle-platform")
            second_handle = carrier.start_child(acceptance_id="acceptance", round_id=second["acceptance_round_id"], kind="source", input_ref=second_projection, input_digest=second_digest, ticket_digest_value=second["ticket_digest"], request_id="round2-source", attempt=0)
            second_report = carrier.ingest_report(acceptance_id="acceptance", round_id=second["acceptance_round_id"], handle=second_handle, report=_report(second, second_handle, kind="source"))
            carrier.recycle_child(acceptance_id="acceptance", round_id=second["acceptance_round_id"], handle=second_handle, completion_ref={"terminal_report_digest": second_report["report_digest"]}, request_id="round2-recycle-source")
            second_platform_projection, second_platform_digest = carrier.project_child_input(round_id=second["acceptance_round_id"], kind="platform")
            second_platform = carrier.start_child(acceptance_id="acceptance", round_id=second["acceptance_round_id"], kind="platform", input_ref=second_platform_projection, input_digest=second_platform_digest, ticket_digest_value=second["ticket_digest"], request_id="round2-platform", attempt=0)
            second_platform_report = carrier.ingest_report(acceptance_id="acceptance", round_id=second["acceptance_round_id"], handle=second_platform, report=_report(second, second_platform, kind="platform"))
            carrier.recycle_child(acceptance_id="acceptance", round_id=second["acceptance_round_id"], handle=second_platform, completion_ref={"terminal_report_digest": second_platform_report["report_digest"]}, request_id="round2-recycle-platform")
            self.assertEqual(carrier.cleanup(), carrier.cleanup())

    def test_codex_acceptance_config_has_no_auth_or_sources_and_separate_capabilities(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home, work, skills = base / "acceptance-home", base / "acceptance-work", base / "acceptance-skills"
            for path in (home, work, skills):
                path.mkdir()
            (base / "sources").mkdir()
            (base / "sources" / "raw-source.md").write_text("must not be staged", encoding="utf-8")
            agent = _Agent("acceptance", _load_package(root, "acceptance"), home, work, skills)
            run = SimpleNamespace(root=base, configuration=SimpleNamespace(task=SimpleNamespace(schema_version=1)), protocol_key=None)
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._write_config(run, agent)
            adapter.agents[agent.agent_id] = agent
            self.assertFalse((home / "auth.json").exists())
            self.assertEqual(list((home / "sources").iterdir()), [])
            manifest = json.loads((home / "runner-capabilities.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["role"], "acceptance")
            self.assertFalse(manifest["team_transport_terminal_state"])
            self.assertTrue(manifest["opaque_handles_only"])
            self.assertEqual(
                manifest["capabilities"],
                [
                    "acceptance_get_ticket",
                    "acceptance_child_start",
                    "acceptance_child_get_report",
                    "acceptance_child_recycle",
                    "acceptance_get_failure_record",
                    "submit_acceptance_result",
                    "acceptance_get_verdict",
                ],
            )
            adapter.stop()
            self.assertFalse((home / "runner-capabilities.json").exists())
            self.assertFalse((home / "config.toml").exists())

    def test_formal_acceptance_config_stages_private_provider_auth_without_sources(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home, work, skills = base / "acceptance-home", base / "acceptance-work", base / "acceptance-skills"
            for path in (home, work, skills):
                path.mkdir(mode=0o700)
            (base / "sources").mkdir(mode=0o700)
            codex_home = base / "codex-home"
            codex_home.mkdir(mode=0o700)
            (codex_home / "auth.json").write_text("formal-provider-auth", encoding="utf-8")
            agent = _Agent("acceptance", _load_package(root, "acceptance"), home, work, skills)
            run = SimpleNamespace(
                root=base,
                configuration=SimpleNamespace(
                    task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance")
                ),
                protocol_key=None,
                acceptance=None,
            )
            adapter = CodexRuntimeAdapter(repository_root=root)
            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False):
                adapter._write_config(run, agent)
            auth = home / "auth.json"
            self.assertEqual(auth.read_text(encoding="utf-8"), "formal-provider-auth")
            self.assertEqual(stat.S_IMODE(auth.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)
            self.assertEqual(list((home / "sources").iterdir()), [])
            adapter.agents[agent.agent_id] = agent
            adapter.stop()
            self.assertFalse(auth.exists())

    def test_formal_acceptance_config_rejects_provider_auth_symlink(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home, work, skills = base / "acceptance-home", base / "acceptance-work", base / "acceptance-skills"
            for path in (home, work, skills):
                path.mkdir(mode=0o700)
            (base / "sources").mkdir(mode=0o700)
            codex_home = base / "codex-home"
            codex_home.mkdir(mode=0o700)
            target = base / "provider-auth.json"
            target.write_text("must-not-follow", encoding="utf-8")
            (codex_home / "auth.json").symlink_to(target)
            agent = _Agent("acceptance", _load_package(root, "acceptance"), home, work, skills)
            run = SimpleNamespace(
                root=base,
                configuration=SimpleNamespace(
                    task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance")
                ),
                protocol_key=None,
                acceptance=None,
            )
            adapter = CodexRuntimeAdapter(repository_root=root)
            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False):
                with self.assertRaisesRegex(CodexRuntimeError, "authentication is unavailable"):
                    adapter._write_config(run, agent)
            self.assertFalse((home / "auth.json").exists())

    def test_formal_protocol_config_stages_role_bound_runner_capability(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home, work, skills = base / "protocol-home", base / "protocol-work", base / "protocol-skills"
            for path in (home, work, skills):
                path.mkdir(mode=0o700)
            (base / "sources" / "protocol").mkdir(parents=True, mode=0o700)
            host_auth = base / "host-auth.json"
            host_auth.write_text("protocol-provider-auth", encoding="utf-8")
            agent = _Agent("protocol", _load_package(root, "protocol"), home, work, skills)
            carrier = RunnerAcceptanceCarrier(
                base / "acceptance-carrier",
                task_id="r2-3-005-formal-acceptance",
                acceptance_id="acceptance",
            )
            run = SimpleNamespace(
                root=base,
                run_id="run-r23005-protocol-capability",
                configuration=SimpleNamespace(
                    task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance")
                ),
                protocol_key="protocol-platform-key",
                acceptance=carrier,
            )
            adapter = CodexRuntimeAdapter(repository_root=root)
            adapter._acceptance = carrier
            with patch.object(adapter, "preflight_host_auth", return_value=host_auth):
                adapter._write_config(run, agent)
            config = (home / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.runner_capability]", config)
            self.assertIn("runner_capability_mcp.py", config)
            self.assertTrue((home / "runner-capability.token").is_file())
            manifest = json.loads((home / "runner-capabilities.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["role"], "protocol")
            self.assertEqual(
                manifest["capabilities"],
                [
                    "protocol_list_platform_artifacts",
                    "protocol_build_acceptance_stage_handoff",
                ],
            )
            adapter.agents[agent.agent_id] = agent
            adapter._coordination_enabled = True
            adapter.stop()
            carrier.cleanup()
            self.assertFalse((home / "runner-capability.token").exists())

    def test_codex_child_resource_seam_stops_and_destroys_private_tree_without_launching(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            private_root = base / "private-child"
            private_root.mkdir()
            (private_root / "input.json").write_text("{}", encoding="utf-8")
            adapter = CodexRuntimeAdapter(repository_root=root, use_bwrap=False)
            resource = adapter.acceptance_child_factory(
                {
                    "child_handle_digest": "a" * 64,
                    "private_root": str(private_root),
                    "session_id": "examiner-session",
                    "kind": "platform",
                }
            )
            self.assertIsNone(resource.process)
            self.assertTrue(private_root.exists())
            adapter.stop()
            self.assertTrue(resource.stopped)
            self.assertTrue(resource.destroyed)
            self.assertFalse(private_root.exists())
            self.assertTrue(adapter.cleanup_identifiers()["acceptance_children"]["zero_residue"])

    def test_four_role_terminal_dependencies_make_coordinator_last_and_settlement_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roles = {"coordinator", "modeling", "protocol", "acceptance"}
            permissions = {(sender, recipient) for sender in roles for recipient in roles if sender != recipient}
            broker = TeamTransportBroker(
                root / "transport",
                permissions,
                terminal_dependencies={
                    "protocol": {"modeling"},
                    "coordinator": {"modeling", "protocol", "acceptance"},
                },
                modeling_agent_id="modeling",
            )
            with self.assertRaisesRegex(RoutingError, "terminal handoffs: acceptance, modeling, protocol"):
                broker.report("coordinator", "completed", "coordinator must be last")
            request = broker.send("modeling", "protocol", "handoff", expects_reply=True)
            reply = broker.send("protocol", "modeling", "handoff-ack", reply_to_delivery_id=request.delivery_id)
            broker.ack_delivery(reply.delivery_id)
            broker.report("modeling", "completed", "modeling")
            broker.ack_terminal_handoff("protocol", "modeling")
            broker.report("protocol", "blocked", "protocol")
            broker.ack_terminal_handoff("coordinator", "modeling")
            broker.ack_terminal_handoff("coordinator", "protocol")
            broker.report("acceptance", "completed", "acceptance")
            broker.ack_terminal_handoff("coordinator", "acceptance")
            coordinator = broker.report("coordinator", "completed", "coordinator")
            self.assertEqual(coordinator.agent_id, "coordinator")
            self.assertEqual(list(broker.results), ["modeling", "protocol", "acceptance", "coordinator"])
            self.assertEqual(set(broker.results), roles)
            broker.stop()

    def test_baseline_and_retained_handoff_include_acceptance_package_skill_and_terminal_status(self) -> None:
        root = repository_root()
        run_id = f"r23005-t4-{__import__('uuid').uuid4().hex}"
        run_root = root / "workspaces" / "modeling-runs" / run_id
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}))
        try:
            run = runner.prepare(
                run_id=run_id,
                profile_path=root / "modeling_team/profiles/base-three-agent.yaml",
                task_path=root / "modeling_team/tasks/base-capability-smoke.yaml",
                scope={"mode": "create"},
            )
            baseline = json.loads((run.root / "baseline-manifest.json").read_text(encoding="utf-8"))
            self.assertIn("package:acceptance", baseline["files"])
            self.assertTrue(any(key.startswith("instructions:acceptance") for key in baseline["files"]))
            self.assertTrue(any(key.startswith("skill:acceptance:") for key in baseline["files"]))
            self.assertIn("runner.acceptance_carrier", baseline["call_sites"])
            interventions_key = "team_transport_interventions"
            self.assertIn(interventions_key, baseline["files"])
            self.assertEqual(
                baseline["call_sites"]["transport.staged_interventions"],
                baseline["files"][interventions_key],
            )
            self.assertEqual(
                baseline["runtime_contract"]["team_transport"]["staged_dependency"]["sha256"],
                baseline["files"][interventions_key],
            )
            self.assertEqual({agent.package.role for agent in run.configuration.profile.agents}, {"coordinator", "modeling", "protocol", "acceptance"})
            run.terminal_results = {role: {"status": "completed"} for role in ("coordinator", "modeling", "protocol", "acceptance")}
            scope = {
                "mode": "create",
                "owned": True,
                "scope_disposition": "retained-pending-acceptance",
                "project_id": "project-r23005",
                "ontology_id": "ontology-r23005",
                "workspace_version": "workspace-r23005",
                "completed_session_id": "session-r23005",
                "sessions_terminal": True,
                "protocol_key_revoked": True,
                "admin_key_revoked": True,
            }
            runner._write_retained_handoff_evidence(scope)
            retained = json.loads((run.root / "evidence" / "retained-handoff-input.json").read_text(encoding="utf-8"))
            self.assertEqual(set(retained["terminal_statuses"]), {"coordinator", "modeling", "protocol", "acceptance"})
            self.assertEqual(retained["terminal_statuses"]["acceptance"], "completed")
        finally:
            if run_root.exists():
                rmtree(run_root)


if __name__ == "__main__":
    unittest.main()
