from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PATH = Path(__file__).parents[1] / "lib" / "platform_adapter.py"
SPEC = importlib.util.spec_from_file_location("platform_adapter", PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)


class PlatformAdapterTest(unittest.TestCase):
    """Migrated local_modeling_adapter tests with the Claude Harness receipt replaced by a one-shot
    Runner authorization. Deterministic platform-write semantics are preserved."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        (self.repo / "backend").mkdir()
        (self.repo / "workspaces" / "modeling-adapter").mkdir(parents=True)
        self.env = self.repo / "backend" / ".env"
        self.env.write_text(
            "ONTOLOGY_MCP_API_KEY=adapter-test-key\n"
            "MODELING_BATCH_MAX_ITEMS=100\n"
            "MODELING_BATCH_MAX_REQUEST_BYTES=1048576\n"
            "MODELING_BATCH_MAX_INLINE_EVIDENCE=100\n"
            "MODELING_BATCH_MAX_EVIDENCE_EXCERPT_CHARS=20000\n",
            encoding="utf-8",
        )
        self.config = self.repo / "workspaces" / "modeling-adapter" / "local.json"
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "project_id": "project-1",
                    "api_base_url": "http://127.0.0.1:8001/api",
                }
            ),
            encoding="utf-8",
        )
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "source.md").write_text("Customer places Order.\n", encoding="utf-8")
        self.run_dir = self.repo / "workspaces" / "modeling-runs" / "run-local-123"
        adapter.smd.initialize_run(
            self.run_dir,
            {
                "run_id": "run-local-123",
                "execution_profile": "local",
                "repository_root": str(self.repo),
                "project_ref": {"project_id": "project-1"},
                "brief": "Confirmed customer ordering behavior.",
                "allowed_command_kinds": ["create_class"],
                "sources": [
                    {
                        "source_id": "s",
                        "locator": "docs/source.md",
                        "scope": {"ontology_ids": ["o"]},
                    }
                ],
                "competency_questions": [
                    {
                        "competency_question_id": "cq",
                        "ontology_id": "o",
                        "text": "Which customer ordered?",
                        "acceptance": {"must_return": ["Customer"]},
                    }
                ],
                "coverage_items": [
                    {
                        "coverage_id": "coverage",
                        "ontology_id": "o",
                        "work_unit_id": "u",
                        "source_ids": ["s"],
                        "competency_question_ids": ["cq"],
                        "status": "planned",
                    }
                ],
                "work_units": [
                    {
                        "work_unit_id": "u",
                        "ontology_id": "o",
                        "source_ids": ["s"],
                        "coverage_ids": ["coverage"],
                        "competency_question_ids": ["cq"],
                        "output_contract": {
                            "result_schema": "result",
                            "allowed_command_kinds": ["create_class"],
                        },
                    }
                ],
                "ontologies": [{"ontology_id": "o"}],
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _seed_session(self) -> None:
        ledger = adapter._ledger(self.repo, "run-local-123")
        state = adapter._read_json(ledger) if ledger.exists() else {}
        state.setdefault("schema_version", 1)
        state.setdefault("build_session_id", "session-1")
        adapter._atomic_json(ledger, state)
        adapter.smd.bind_local_execution(self.run_dir, build_session_id="session-1")

    def _authorize(self, operation_id: str = "op-1", **kwargs) -> None:
        """Record one Runner-confirmed authorization for a protected write."""
        self._seed_session()
        adapter.authorize_runner_write(
            self.repo,
            self.run_dir,
            operation_id,
            operation=kwargs.get("operation", "commit_business"),
            role_settled=True,
            artifact_hash=kwargs.get("artifact_hash"),
            review_verdict=kwargs.get("review_verdict"),
            dry_run_clean=kwargs.get("dry_run_clean", False),
        )

    def test_local_config_reads_only_loopback_and_never_returns_api_key(self) -> None:
        config, limits = adapter.load_config(self.repo, self.config)
        self.assertEqual(config["project_id"], "project-1")
        self.assertEqual(limits["modeling_batch_max_items"], 100)
        envelope = adapter._envelope(
            "start", "blocked", next_action="resolve", error="credential_unavailable"
        )
        self.assertNotIn("adapter-test-key", json.dumps(envelope))

    def test_remote_and_missing_credential_are_rejected_with_stable_code(self) -> None:
        remote = json.loads(self.config.read_text(encoding="utf-8"))
        remote["api_base_url"] = "https://example.test/api"
        self.config.write_text(json.dumps(remote), encoding="utf-8")
        with self.assertRaisesRegex(adapter.AdapterError, "local_service_required"):
            adapter.load_config(self.repo, self.config)
        self.config.write_text(
            json.dumps({"schema_version": 1, "project_id": "p"}), encoding="utf-8"
        )
        self.env.unlink()
        with self.assertRaisesRegex(adapter.AdapterError, "credential_unavailable"):
            adapter.load_config(self.repo, self.config)

    def test_start_then_commit_business_creates_once_and_binds_platform_cq(self) -> None:
        calls: list[tuple[str, str, object]] = []

        def request(_config, method, path, payload=None):
            calls.append((method, path, payload))
            if path == "/health":
                return {"status": "ok"}
            if method == "POST" and path.endswith("/build-sessions"):
                return {
                    "session": {
                        "id": "session-1",
                        "project_id": "project-1",
                        "status": "active",
                        "revision": 1,
                    }
                }
            if method == "GET" and path.endswith("/competency-questions"):
                return []
            if method == "POST" and path.endswith("/competency-questions"):
                return {"id": "remote-cq-1", "status": "draft"}
            if path.endswith("/status"):
                return {"id": "remote-cq-1", "status": "approved"}
            return {"project_id": "project-1"}

        with mock.patch.object(adapter, "_request", side_effect=request):
            started = adapter.start(self.repo, self.run_dir, self.config)
            self._authorize("commit-1", operation="commit_business")
            manifest = self.repo / "business.json"
            manifest.write_text(
                json.dumps(
                    {
                        "brief": {
                            "fields": {"business_goal": "Order retrieval"},
                            "confirmed_fields": ["business_goal"],
                        },
                        "questions": {
                            "cq": {
                                "query_definition": {},
                                "source_brief_fields": ["business_goal"],
                                "accepted": True,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            committed = adapter.commit_business(
                self.repo, self.run_dir, self.config, manifest, "commit-1"
            )
        self.assertEqual(started["references"]["build_session_id"], "session-1")
        self.assertEqual(started["next_action"], "organize_business")
        self.assertEqual(committed["status"], "ok")
        coverage = adapter.smd._read_json(self.run_dir / "shared" / "coverage.json")
        self.assertEqual(
            coverage["competency_questions"][0]["platform_competency_question_id"], "remote-cq-1"
        )
        self.assertEqual(
            sum(
                path.endswith("/competency-questions") and method == "POST"
                for method, path, _ in calls
            ),
            1,
        )

    def test_commit_business_blocks_without_runner_authorization(self) -> None:
        def request(_config, method, path, _payload=None):
            if path == "/health":
                return {"status": "ok"}
            if method == "POST" and path.endswith("/build-sessions"):
                return {
                    "session": {
                        "id": "session-1",
                        "project_id": "project-1",
                        "status": "active",
                        "revision": 1,
                    }
                }
            raise AssertionError((method, path))

        manifest = self.repo / "business-blocked.json"
        manifest.write_text(
            json.dumps(
                {
                    "brief": {"fields": {}, "confirmed_fields": []},
                    "questions": {"cq": {"query_definition": {}, "source_brief_fields": []}},
                }
            ),
            encoding="utf-8",
        )
        with mock.patch.object(adapter, "_request", side_effect=request) as request_mock:
            started = adapter.start(self.repo, self.run_dir, self.config)
            # No authorize_runner_write: the protected write must be refused before any platform call.
            with self.assertRaisesRegex(adapter.AdapterError, "runner_authorization_required"):
                adapter.commit_business(
                    self.repo, self.run_dir, self.config, manifest, "never-authorized"
                )
        self.assertEqual(started["next_action"], "organize_business")
        # Only health + build-session creation happened; no business write attempted.
        self.assertEqual(request_mock.call_count, 2)

    def test_business_ambiguity_blocks_without_duplicate_and_batch_identity_uses_run_id(
        self,
    ) -> None:
        manifest = self.repo / "business.json"
        manifest.write_text(
            json.dumps(
                {
                    "brief": {
                        "fields": {"business_goal": "Order retrieval"},
                        "confirmed_fields": ["business_goal"],
                    },
                    "questions": {
                        "cq": {
                            "accepted": True,
                            "query_definition": {},
                            "source_brief_fields": ["business_goal"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        duplicate = {
            "id": "remote",
            "ontology_id": "o",
            "question": "Which customer ordered?",
            "query_definition": {},
        }
        self._authorize("ambiguity-1")
        with mock.patch.object(
            adapter, "_request", side_effect=[{}, [duplicate, {**duplicate, "id": "remote-2"}]]
        ):
            with self.assertRaisesRegex(adapter.AdapterError, "business_sync_ambiguous"):
                adapter.commit_business(
                    self.repo, self.run_dir, self.config, manifest, "ambiguity-1"
                )
        captured = {}
        with mock.patch.object(
            adapter,
            "_request",
            side_effect=lambda _c, _m, _p, payload=None: (
                captured.setdefault("payload", payload) or {}
            ),
        ):
            adapter._request_for_batch(
                {"api_key": "x", "api_base_url": "http://127.0.0.1"},
                "s",
                {"client_batch_id": "b", "ontology_id": "o", "items": []},
                run_id="run-local-123",
                mode="dry_run",
                workspace_version="v",
            )
        self.assertEqual(
            captured["payload"]["idempotency_key"],
            adapter._attempt_identity("run-local-123", "b", "dry_run"),
        )

    def test_business_retry_updates_only_existing_bound_question(self) -> None:
        self._authorize("retry-1")
        coverage_path = self.run_dir / "shared" / "coverage.json"
        coverage = adapter.smd._read_json(coverage_path)
        coverage["competency_questions"][0]["platform_competency_question_id"] = "remote-cq-1"
        adapter.smd._atomic_write_json(coverage_path, coverage)
        manifest = self.repo / "business-update.json"
        manifest.write_text(
            json.dumps(
                {
                    "brief": {
                        "fields": {"business_goal": "Order retrieval"},
                        "confirmed_fields": ["business_goal"],
                    },
                    "questions": {
                        "cq": {
                            "accepted": True,
                            "question": "Which customer placed an order?",
                            "query_definition": {},
                            "source_brief_fields": ["business_goal"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        calls: list[tuple[str, str]] = []

        def request(_config, method, path, payload=None):
            calls.append((method, path))
            if method == "GET":
                return [
                    {
                        "id": "remote-cq-1",
                        "ontology_id": "o",
                        "question": "old",
                        "query_definition": {},
                        "status": "approved",
                    }
                ]
            if method == "PATCH" and path.endswith("/brief"):
                return {}
            if method == "PATCH":
                return {"id": "remote-cq-1", "status": "draft"}
            if path.endswith("/status"):
                return {"id": "remote-cq-1", "status": "approved"}
            raise AssertionError((method, path, payload))

        with mock.patch.object(adapter, "_request", side_effect=request):
            result = adapter.commit_business(
                self.repo, self.run_dir, self.config, manifest, "retry-1"
            )
        self.assertEqual(result["status"], "ok")
        self.assertIn(("PATCH", "/competency-questions/remote-cq-1"), calls)
        self.assertFalse(
            any(
                method == "POST" and path.endswith("/competency-questions")
                for method, path in calls
            )
        )

    def test_reconcile_uses_real_batch_detail_attempt_without_resubmission(self) -> None:
        adapter._atomic_json(
            adapter._ledger(self.repo, "run-local-123"),
            {
                "schema_version": 1,
                "build_session_id": "session-1",
                "attempts": {
                    "batch-1": {
                        "immutable_content_hash": "hash",
                        "modes": {
                            "apply_atomic": {
                                "mode": "apply_atomic",
                                "idempotency_key": "stable",
                                "immutable_content_hash": "hash",
                            }
                        },
                    }
                },
            },
        )
        batch = {"client_batch_id": "batch-1", "immutable_content_hash": "hash"}
        responses = iter(
            [
                {"batches": [{"batch_id": "platform-batch", "client_batch_id": "batch-1"}]},
                {
                    "batch_id": "platform-batch",
                    "attempts": [
                        {
                            "batch_id": "platform-batch",
                            "client_batch_id": "batch-1",
                            "mode": "apply_atomic",
                            "attempt_status": "applied",
                            "items": [],
                        }
                    ],
                },
            ]
        )
        with (
            mock.patch.object(
                adapter, "load_config", return_value=({"project_id": "project-1"}, {})
            ),
            mock.patch.object(
                adapter.smd,
                "_load_run",
                return_value={"run_id": "run-local-123"},
            ),
            mock.patch.object(adapter, "_next_planned_batch", return_value=batch),
            mock.patch.object(
                adapter, "_request", side_effect=lambda *_args, **_kwargs: next(responses)
            ),
            mock.patch.object(adapter.smd, "bind_platform_response") as bind,
        ):
            result = adapter.reconcile_apply(self.repo, self.run_dir, self.config, "o")
        self.assertEqual(result["status"], "ok")
        bind.assert_called_once()
        self.assertEqual(bind.call_args.args[-1]["attempt_status"], "applied")

    def test_unaccepted_question_rejects_before_any_platform_write(self) -> None:
        self._authorize("unaccepted-1")
        manifest = self.repo / "business-unaccepted.json"
        manifest.write_text(
            json.dumps(
                {
                    "brief": {"fields": {}, "confirmed_fields": []},
                    "questions": {
                        "cq": {
                            "accepted": False,
                            "query_definition": {},
                            "source_brief_fields": [],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        with mock.patch.object(adapter, "_request") as request:
            with self.assertRaisesRegex(adapter.AdapterError, "business_question_not_accepted"):
                adapter.commit_business(
                    self.repo, self.run_dir, self.config, manifest, "unaccepted-1"
                )
        request.assert_not_called()

    def test_cq_acceptance_and_confirmed_sources_are_required_before_any_write(self) -> None:
        omitted = self.repo / "business-omitted-accepted.json"
        source_mismatch = self.repo / "business-source-mismatch.json"
        omitted.write_text(
            json.dumps(
                {
                    "brief": {"fields": {}, "confirmed_fields": []},
                    "questions": {"cq": {"query_definition": {}, "source_brief_fields": []}},
                }
            ),
            encoding="utf-8",
        )
        source_mismatch.write_text(
            json.dumps(
                {
                    "brief": {
                        "fields": {"business_goal": "retrieval"},
                        "confirmed_fields": ["business_goal"],
                    },
                    "questions": {
                        "cq": {
                            "accepted": True,
                            "query_definition": {},
                            "source_brief_fields": ["scope"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        for manifest, error in (
            (omitted, "business_question_not_accepted"),
            (source_mismatch, "business_question_source_not_confirmed"),
        ):
            self._authorize("sources-1")
            with mock.patch.object(adapter, "_request") as request:
                with self.assertRaisesRegex(adapter.AdapterError, error):
                    adapter.commit_business(
                        self.repo, self.run_dir, self.config, manifest, "sources-1"
                    )
            request.assert_not_called()

    def test_runner_authorization_required_by_each_protected_action_and_single_use(self) -> None:
        protected = (
            adapter.commit_business,
            adapter.dry_run_next,
            adapter.apply_next,
            adapter.verify,
            adapter.finish,
        )
        for action in protected:
            self.assertIn("_consume_runner_grant", inspect.getsource(action))
        manifest = self.repo / "protected-business.json"
        verification = self.repo / "protected-verification.json"
        manifest.write_text(
            json.dumps({"brief": {"fields": {}, "confirmed_fields": []}, "questions": {}}),
            encoding="utf-8",
        )
        verification.write_text("{}", encoding="utf-8")
        invocations = (
            lambda: adapter.commit_business(
                self.repo, self.run_dir, self.config, manifest, "fresh-required"
            ),
            lambda: adapter.dry_run_next(
                self.repo, self.run_dir, self.config, "o", "fresh-required"
            ),
            lambda: adapter.apply_next(self.repo, self.run_dir, self.config, "o", "fresh-required"),
            lambda: adapter.verify(
                self.repo, self.run_dir, self.config, "o", verification, "fresh-required"
            ),
            lambda: adapter.finish(self.repo, self.run_dir, self.config, "fresh-required"),
        )
        for invoke in invocations:
            with (
                mock.patch.object(adapter, "load_config", return_value=({}, {})),
                mock.patch.object(
                    adapter.smd,
                    "_load_run",
                    return_value={"run_id": "run-local-123", "execution_profile": "local"},
                ),
                mock.patch.object(
                    adapter,
                    "_consume_runner_grant",
                    side_effect=adapter.AdapterError("runner_authorization_required"),
                ),
                mock.patch.object(adapter, "_request") as request,
            ):
                with self.assertRaisesRegex(adapter.AdapterError, "runner_authorization_required"):
                    invoke()
            request.assert_not_called()
        # A granted authorization is consumed exactly once.
        self._seed_session()
        run = adapter.smd._load_run(self.run_dir)
        adapter.authorize_runner_write(
            self.repo,
            self.run_dir,
            "grant-1",
            operation="commit_business",
            role_settled=True,
        )
        adapter._consume_runner_grant(self.repo, run, "grant-1")
        with self.assertRaisesRegex(adapter.AdapterError, "runner_authorization_required"):
            adapter._consume_runner_grant(self.repo, run, "grant-1")

    def test_authorize_runner_write_validates_preconditions(self) -> None:
        self._seed_session()
        with self.assertRaisesRegex(adapter.AdapterError, "runner_authorization_required"):
            adapter.authorize_runner_write(
                self.repo, self.run_dir, "", operation="commit_business", role_settled=True
            )
        with self.assertRaisesRegex(adapter.AdapterError, "runner_authorization_invalid"):
            adapter.authorize_runner_write(
                self.repo,
                self.run_dir,
                "bad-op",
                operation="commit_business",
                role_settled=True,
                review_verdict="NOPE",
            )
        result = adapter.authorize_runner_write(
            self.repo,
            self.run_dir,
            "ok-1",
            operation="verify",
            role_settled=True,
            review_verdict="PASS",
            dry_run_clean=True,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["next_action"], "execute_protected_write")

    def test_apply_reuses_materialized_content_and_binds_without_token_leak(self) -> None:
        self._authorize("apply-1", operation="apply_next")
        batch = {
            "client_batch_id": "batch-1",
            "ontology_id": "o",
            "state": "dry_run_bound",
            "immutable_content_hash": "hash",
            "materialized_items": [{"client_item_id": "item-1", "command_kind": "create_class"}],
        }
        sent: list[dict] = []
        dry_payload: dict[str, object] = {}

        with mock.patch.object(
            adapter,
            "_request",
            side_effect=lambda _c, _m, _p, payload=None: dry_payload.update(payload) or {},
        ):
            adapter._request_for_batch(
                {"api_base_url": "http://127.0.0.1", "api_key": "x"},
                "session-1",
                {
                    "client_batch_id": "batch-1",
                    "ontology_id": "o",
                    "items": batch["materialized_items"],
                },
                run_id="run-local-123",
                mode="dry_run",
                workspace_version="workspace-1",
            )
        adapter._save_attempt(
            self.repo,
            "run-local-123",
            client_batch_id="batch-1",
            mode="dry_run",
            immutable_content_hash="hash",
        )

        def request(_config, method, path, payload=None):
            if method == "POST" and path.endswith("/modeling-batches"):
                sent.append(payload)
                return {"attempt_status": "applied", "batch_id": "platform-batch", "items": []}
            if path.endswith(":acquire"):
                return {"lease_token": "do-not-leak", "lease_revision": 2}
            if path.endswith("/modeling-context"):
                return {"workspace": {"workspace_version": "workspace-2"}}
            if path.endswith(":release"):
                return {"released": True}
            return {"session": {"revision": 1}}

        with (
            mock.patch.object(
                adapter, "load_config", return_value=({"project_id": "project-1"}, {})
            ),
            mock.patch.object(
                adapter.smd,
                "_load_run",
                return_value={"run_id": "run-local-123"},
            ),
            mock.patch.object(adapter, "_next_planned_batch", return_value=batch),
            mock.patch.object(adapter, "_request", side_effect=request),
            mock.patch.object(adapter.smd, "bind_platform_response") as bind,
        ):
            applied = adapter.apply_next(self.repo, self.run_dir, self.config, "o", "apply-1")
        payload = sent[0]
        self.assertEqual(payload["client_batch_id"], "batch-1")
        self.assertEqual(payload["items"], batch["materialized_items"])
        self.assertEqual(payload["items"], dry_payload["items"])
        self.assertEqual(
            payload["idempotency_key"],
            adapter._attempt_identity("run-local-123", "batch-1", "apply_atomic"),
        )
        self.assertEqual(applied["status"], "ok")
        self.assertNotIn("do-not-leak", json.dumps(applied))
        self.assertNotIn("do-not-leak", adapter._ledger(self.repo, "run-local-123").read_text())
        ledger = adapter._read_json(adapter._ledger(self.repo, "run-local-123"))
        self.assertEqual(ledger["attempts"]["batch-1"]["immutable_content_hash"], "hash")
        self.assertEqual(set(ledger["attempts"]["batch-1"]["modes"]), {"dry_run", "apply_atomic"})
        bind.assert_called_once()

    def test_verify_executes_cq_lifecycle_and_invalid_evidence_is_rejected(self) -> None:
        self._authorize("verify-1", operation="verify")
        coverage_path = self.run_dir / "shared" / "coverage.json"
        coverage = adapter.smd._read_json(coverage_path)
        coverage["competency_questions"][0].update(
            {
                "platform_competency_question_id": "remote-cq-1",
                "query_definition": {"kind": "entity_count"},
            }
        )
        adapter.smd._atomic_write_json(coverage_path, coverage)
        verification = self.repo / "verification.json"
        verification.write_text("{}", encoding="utf-8")
        calls: list[str] = []

        def request(_config, _method, path, _payload=None):
            calls.append(path)
            if path.endswith("/competency-questions"):
                return [{"id": "remote-cq-1", "status": "approved"}]
            if path.endswith("/status"):
                return {"id": "remote-cq-1", "status": "testable"}
            return {"id": "remote-cq-1", "status": "passed"}

        with (
            mock.patch.object(
                adapter, "load_config", return_value=({"project_id": "project-1"}, {})
            ),
            mock.patch.object(adapter, "_request", side_effect=request),
            mock.patch.object(
                adapter.smd, "validate_verification", return_value={"verdict": "PASS"}
            ),
        ):
            result = adapter.verify(
                self.repo, self.run_dir, self.config, "o", verification, "verify-1"
            )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(any(path.endswith("/status") for path in calls))
        self.assertTrue(any(path.endswith("/validate") for path in calls))
        self._authorize("verify-2", operation="verify")
        with (
            mock.patch.object(
                adapter, "load_config", return_value=({"project_id": "project-1"}, {})
            ),
            mock.patch.object(adapter, "_request", side_effect=request),
            mock.patch.object(
                adapter.smd,
                "validate_verification",
                side_effect=adapter.smd.DirectoryContractError("invalid evidence"),
            ),
        ):
            with self.assertRaisesRegex(adapter.smd.DirectoryContractError, "invalid evidence"):
                adapter.verify(
                    self.repo, self.run_dir, self.config, "o", verification, "verify-2"
                )

    def _bind_required_cq(self, remote_id: str = "remote-cq-1") -> Path:
        coverage_path = self.run_dir / "shared" / "coverage.json"
        coverage = adapter.smd._read_json(coverage_path)
        coverage["competency_questions"][0].update(
            {
                "platform_competency_question_id": remote_id,
                "query_definition": {"kind": "entity_count"},
            }
        )
        adapter.smd._atomic_write_json(coverage_path, coverage)
        verification = self.repo / "verification.json"
        verification.write_text('{"local": "PASS"}', encoding="utf-8")
        return verification

    def test_verify_blocks_existing_failed_cq_before_local_verification(self) -> None:
        self._authorize("verify-block-1", operation="verify")
        verification = self._bind_required_cq()
        stored_verification = self.run_dir / "ontologies" / "o" / "verification.json"

        with (
            mock.patch.object(
                adapter, "load_config", return_value=({"project_id": "project-1"}, {})
            ),
            mock.patch.object(
                adapter,
                "_request",
                return_value=[{"id": "remote-cq-1", "status": "failed"}],
            ) as request,
            mock.patch.object(adapter.smd, "validate_verification") as validate,
        ):
            result = adapter.verify(
                self.repo, self.run_dir, self.config, "o", verification, "verify-block-1"
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "competency_question_failed")
        self.assertEqual(result["next_action"], "retry_verify")
        self.assertFalse(stored_verification.exists())
        validate.assert_not_called()
        self.assertFalse(any(call.args[2].endswith("/validate") for call in request.call_args_list))
        state = adapter._read_json(adapter._ledger(self.repo, "run-local-123"))
        self.assertEqual(state["cq_recovery_required"], ["remote-cq-1"])

    def test_verify_recovers_failed_cq_with_fresh_authorization_then_persists(self) -> None:
        self._authorize("verify-rec-1", operation="verify")
        verification = self._bind_required_cq()

        def failed_request(_config, _method, path, _payload=None):
            if path.endswith("/competency-questions"):
                return [{"id": "remote-cq-1", "status": "failed"}]
            raise AssertionError("failed CQ must block before any lifecycle request")

        with (
            mock.patch.object(
                adapter, "load_config", return_value=({"project_id": "project-1"}, {})
            ),
            mock.patch.object(adapter, "_request", side_effect=failed_request),
            mock.patch.object(adapter.smd, "validate_verification") as validate,
        ):
            first = adapter.verify(
                self.repo, self.run_dir, self.config, "o", verification, "verify-rec-1"
            )
        self.assertEqual(first["error_code"], "competency_question_failed")
        validate.assert_not_called()

        self._authorize("verify-rec-2", operation="verify")
        calls: list[str] = []

        def recovered_request(_config, _method, path, _payload=None):
            calls.append(path)
            if path.endswith("/competency-questions"):
                return [{"id": "remote-cq-1", "status": "failed"}]
            if path.endswith("/status"):
                return {"id": "remote-cq-1", "status": "testable"}
            if path.endswith("/validate"):
                return {"id": "remote-cq-1", "status": "passed"}
            raise AssertionError(path)

        with (
            mock.patch.object(
                adapter, "load_config", return_value=({"project_id": "project-1"}, {})
            ),
            mock.patch.object(adapter, "_request", side_effect=recovered_request),
            mock.patch.object(
                adapter.smd, "validate_verification", return_value={"verdict": "PASS"}
            ),
        ):
            result = adapter.verify(
                self.repo, self.run_dir, self.config, "o", verification, "verify-rec-2"
            )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(any(path.endswith("/status") for path in calls))
        self.assertTrue(any(path.endswith("/validate") for path in calls))

    def test_verify_accepts_already_passed_cq_after_client_crash(self) -> None:
        self._authorize("verify-pass-1", operation="verify")
        verification = self._bind_required_cq()

        with (
            mock.patch.object(
                adapter, "load_config", return_value=({"project_id": "project-1"}, {})
            ),
            mock.patch.object(
                adapter,
                "_request",
                return_value=[{"id": "remote-cq-1", "status": "passed"}],
            ) as request,
            mock.patch.object(
                adapter.smd, "validate_verification", return_value={"verdict": "PASS"}
            ),
        ):
            result = adapter.verify(
                self.repo, self.run_dir, self.config, "o", verification, "verify-pass-1"
            )

        self.assertEqual(result["status"], "ok")
        self.assertFalse(any(call.args[2].endswith("/validate") for call in request.call_args_list))

    def test_verify_blocks_all_local_persistence_when_one_of_multiple_cqs_fails(self) -> None:
        self._authorize("verify-multi-1", operation="verify")
        verification = self._bind_required_cq()
        coverage_path = self.run_dir / "shared" / "coverage.json"
        coverage = adapter.smd._read_json(coverage_path)
        coverage["competency_questions"].append(
            {
                "ontology_id": "o",
                "platform_competency_question_id": "remote-cq-2",
                "query_definition": {"kind": "relation_count"},
            }
        )
        adapter.smd._atomic_write_json(coverage_path, coverage)
        stored_verification = self.run_dir / "ontologies" / "o" / "verification.json"

        def request(_config, _method, path, _payload=None):
            if path.endswith("/competency-questions"):
                return [
                    {"id": "remote-cq-1", "status": "testable"},
                    {"id": "remote-cq-2", "status": "testable"},
                ]
            if path.endswith("remote-cq-1/validate"):
                return {"id": "remote-cq-1", "status": "passed"}
            if path.endswith("remote-cq-2/validate"):
                return {"id": "remote-cq-2", "status": "failed"}
            raise AssertionError(path)

        with (
            mock.patch.object(
                adapter, "load_config", return_value=({"project_id": "project-1"}, {})
            ),
            mock.patch.object(adapter, "_request", side_effect=request),
            mock.patch.object(adapter.smd, "validate_verification") as validate,
        ):
            result = adapter.verify(
                self.repo, self.run_dir, self.config, "o", verification, "verify-multi-1"
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "competency_question_failed")
        self.assertNotEqual(result["next_action"], "finish")
        self.assertFalse(stored_verification.exists())
        validate.assert_not_called()

    def test_finish_requires_every_ontology_before_completion(self) -> None:
        self._authorize("finish-1", operation="finish")
        run = {
            "run_id": "run-local-123",
            "ontologies": [{"ontology_id": "o"}, {"ontology_id": "o2"}],
        }
        with (
            mock.patch.object(adapter, "load_config", return_value=({}, {})),
            mock.patch.object(adapter.smd, "_load_run", return_value=run),
            mock.patch.object(
                adapter.smd,
                "validate_verification",
                side_effect=[{"verdict": "PASS"}, {"verdict": "BLOCKED"}],
            ),
            mock.patch.object(
                adapter.smd,
                "validate_batch_plan",
                return_value={"batches": [{"state": "applied"}]},
            ),
            mock.patch.object(adapter, "_request") as request,
        ):
            with self.assertRaisesRegex(adapter.AdapterError, "verification_not_passed"):
                adapter.finish(self.repo, self.run_dir, self.config, "finish-1")
        request.assert_not_called()
        self._authorize("finish-2", operation="finish")
        with (
            mock.patch.object(adapter, "load_config", return_value=({}, {})),
            mock.patch.object(adapter.smd, "_load_run", return_value=run),
            mock.patch.object(
                adapter.smd, "validate_verification", return_value={"verdict": "PASS"}
            ),
            mock.patch.object(
                adapter.smd,
                "validate_batch_plan",
                return_value={"batches": [{"state": "applied"}]},
            ),
            mock.patch.object(
                adapter, "_request", return_value={"session": {"revision": 1}}
            ) as completed_request,
        ):
            result = adapter.finish(self.repo, self.run_dir, self.config, "finish-2")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["next_action"], "done")
        self.assertTrue(
            any(":complete" in call.args[2] for call in completed_request.call_args_list)
        )

    def test_cancel_blocks_unreconciled_apply(self) -> None:
        adapter._atomic_json(
            adapter._ledger(self.repo, "run-local-123"),
            {
                "schema_version": 1,
                "build_session_id": "session-1",
                "attempts": {"batch": {"modes": {"apply_atomic": {"mode": "apply_atomic", "reconciled": False}}}},
            },
        )
        with self.assertRaisesRegex(adapter.AdapterError, "in_flight_batch"):
            adapter.cancel(self.repo, self.run_dir, self.config, "explicit abandonment")

    def test_apply_timeout_keeps_original_identity_for_reconciliation(self) -> None:
        self._authorize("apply-timeout-1", operation="apply_next")
        batch = {
            "client_batch_id": "batch-1",
            "state": "dry_run_bound",
            "immutable_content_hash": "hash",
            "materialized_items": [],
        }
        responses = iter(
            [
                {"session": {"revision": 1}},
                {"lease_token": "fixture-lease-token-not-persisted", "lease_revision": 1},
                {"workspace": {"workspace_version": "v1"}},
                adapter.AdapterError("platform_unavailable"),
                {"released": True},
            ]
        )

        def request(*_args, **_kwargs):
            value = next(responses)
            if isinstance(value, Exception):
                raise value
            return value

        with (
            mock.patch.object(adapter, "load_config", return_value=({}, {})),
            mock.patch.object(
                adapter.smd,
                "_load_run",
                return_value={"run_id": "run-local-123"},
            ),
            mock.patch.object(adapter, "_next_planned_batch", return_value=batch),
            mock.patch.object(adapter, "_request", side_effect=request),
        ):
            result = adapter.apply_next(self.repo, self.run_dir, self.config, "o", "apply-timeout-1")
        self.assertEqual(result["next_action"], "reconcile-apply")
        state = adapter._read_json(adapter._ledger(self.repo, "run-local-123"))
        attempt = state["attempts"]["batch-1"]["modes"]["apply_atomic"]
        self.assertEqual(
            attempt["idempotency_key"],
            adapter._attempt_identity("run-local-123", "batch-1", "apply_atomic"),
        )
        self.assertNotIn("fixture-lease-token-not-persisted", json.dumps(state))


if __name__ == "__main__":
    unittest.main()
