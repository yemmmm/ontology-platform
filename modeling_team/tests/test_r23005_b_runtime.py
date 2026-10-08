from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modeling_team.acceptance import AcceptanceContractError, PlatformApiReadKeyLifecycle
from modeling_team.acceptance import RunnerAcceptanceCarrier
from modeling_team.acceptance_runtime import PLATFORM_PROXY_READ_TOOLS, ScopedReadProxy
from modeling_team.runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError, _CodexChildResource


class _FakeProcess:
    _next_pid = 90000

    def __init__(self, command: list[str], kwargs: dict[str, object]):
        self.command = command
        self.kwargs = kwargs
        self.pid = _FakeProcess._next_pid
        _FakeProcess._next_pid += 1
        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if not self.terminated and not self.killed else -15

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return -15


class _FakeForwarder:
    def __init__(self):
        self.stopped = False

    def start(self):
        return self

    def stop(self):
        self.stopped = True

    def forward(self, tool, arguments, read_key):
        return {"tool": tool, "arguments": dict(arguments), "read_key_digest": read_key[:2]}


class _FakePlatformScope:
    project_id = "project-one"
    admin_key = "admin-key"

    def __init__(self):
        self.calls = []

    def request(self, method, path, body, key):
        self.calls.append((method, path, body, key))
        if method == "POST" and path == "/api/api-keys":
            return 201, {"id": "platform-key-1", "plaintext_key": "temporary-read-key"}
        if method == "POST" and path.endswith(":revoke"):
            return 200, {"id": "platform-key-1", "revoked_at": "2026-08-03T00:00:00Z"}
        if method == "GET" and path == "/api/api-keys/platform-key-1":
            return 200, {"id": "platform-key-1", "revoked_at": "2026-08-03T00:00:00Z"}
        if method == "GET" and path == "/api/projects/project-one" and key == "temporary-read-key":
            return 401, {"detail": "revoked"}
        raise AssertionError((method, path, body, key))


class _CrashProcess(_FakeProcess):
    def poll(self):
        return -9


class _ImmediateFailureResource:
    def __init__(self, spec):
        self.spec = spec
        self.stopped = False
        self.destroyed = False
        spec["record_infrastructure_failure"]("runtime", "child-crash")

    def stop(self):
        self.stopped = True

    def destroy(self):
        self.destroyed = True


class R23005BRuntimeTests(unittest.TestCase):
    def test_project_child_input_matches_real_start38_cq001_fixture(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "r23005-start38-cq001-child-input.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        round_id = fixture["acceptance_round_id"]
        ticket = fixture["ticket"]
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory), task_id="r2-3-005-formal-acceptance", acceptance_id="acceptance"
            )
            # This fixture intentionally contains only the immutable fields that
            # the Runner's projection function is allowed to expose.  Keeping
            # the ticket in the carrier's Runner-private map avoids re-publishing
            # retained start38 evidence just to test the projection digest.
            carrier._tickets[round_id] = ticket
            source_projection, source_digest = carrier.project_child_input(
                round_id=round_id, kind="source"
            )
            with self.assertRaisesRegex(AcceptanceContractError, "non-read-only tool"):
                carrier.project_child_input(round_id=round_id, kind="platform")
            self.assertEqual(source_digest, fixture["expected"]["source_input_digest"])
            self.assertEqual(
                set(source_projection), {"question", "approved_sources", "source_bundle_digest"}
            )
            self.assertEqual(source_projection["question"], ticket["question"])
            carrier.cleanup()

    def test_capability_child_start_derives_host_projection_when_input_fields_are_omitted(self) -> None:
        from modeling_team.tests.test_r23005_contracts import _ticket

        ticket = _ticket("host-derived")
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory),
                task_id=ticket["task_id"],
                acceptance_id="acceptance",
            )
            carrier.publish_ticket(
                ticket,
                coordinator_id="coordinator",
                owner_revision=ticket["quality_standard_ref"],
            )
            carrier.ack_ticket(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                ticket_digest_value=ticket["ticket_digest"],
            )
            expected_projection, expected_digest = carrier.project_child_input(
                round_id=ticket["acceptance_round_id"], kind="source"
            )
            arguments = {
                "acceptance_id": "acceptance",
                "round_id": ticket["acceptance_round_id"],
                "kind": "source",
                "request_id": "host-derived-start",
            }
            endpoint = carrier._capability_endpoints["acceptance"]
            response = endpoint.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "token": carrier.capability_token("acceptance"),
                    "method": "tools/call",
                    "params": {
                        "name": "acceptance_child_start",
                        "arguments": arguments,
                    },
                }
            )
            self.assertNotIn("error", response)
            data = response["result"]["structuredContent"]["data"]
            self.assertEqual(data["input_digest"], expected_digest)
            self.assertEqual(data["acceptance_round_id"], ticket["acceptance_round_id"])
            self.assertEqual(expected_projection["question"], ticket["question"])
            # input_ref/input_digest are no longer accepted by the schema: the Host
            # always derives the projection.  A legacy caller passing either field
            # (even the correct projection) is rejected at the schema layer.
            legacy_response = endpoint.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "token": carrier.capability_token("acceptance"),
                    "method": "tools/call",
                    "params": {
                        "name": "acceptance_child_start",
                        "arguments": {
                            **arguments,
                            "request_id": "host-derived-start-legacy",
                            "input_ref": expected_projection,
                            "input_digest": expected_digest,
                        },
                    },
                }
            )
            self.assertEqual(legacy_response["error"]["code"], -32001)
            carrier.cleanup()

    def test_capability_child_start_rejects_mismatched_or_cross_bound_input_fields(self) -> None:
        from modeling_team.tests.test_r23005_contracts import _ticket

        first, second = _ticket("cross-round-1"), _ticket("cross-round-2")
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory), task_id=first["task_id"], acceptance_id="acceptance"
            )
            for ticket in (first, second):
                carrier.publish_ticket(
                    ticket,
                    coordinator_id="coordinator",
                    owner_revision=ticket["quality_standard_ref"],
                )
                carrier.ack_ticket(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    ticket_digest_value=ticket["ticket_digest"],
                )
            first_source, first_digest = carrier.project_child_input(
                round_id=first["acceptance_round_id"], kind="source"
            )
            # The synthetic ticket helper keeps every projection field stable
            # across suffixes.  Make the second round's immutable source bundle
            # distinct so a cross-round binding remains distinguishable.
            carrier._tickets[second["acceptance_round_id"]]["source_bundle_digest"] = "2" * 64
            second_source, second_digest = carrier.project_child_input(
                round_id=second["acceptance_round_id"], kind="source"
            )
            first_platform, first_platform_digest = carrier.project_child_input(
                round_id=first["acceptance_round_id"], kind="platform"
            )
            # The schema no longer accepts input_ref/input_digest: the Host always
            # derives the projection.  ticket_digest/attempt remain optional and
            # are accepted-but-ignored by the dispatcher.
            common = {
                "acceptance_id": "acceptance",
                "round_id": first["acceptance_round_id"],
                "kind": "source",
            }
            endpoint = carrier._capability_endpoints["acceptance"]

            def call(arguments: dict[str, object], request_id: int) -> dict[str, object]:
                return endpoint.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "token": carrier.capability_token("acceptance"),
                        "method": "tools/call",
                        "params": {
                            "name": "acceptance_child_start",
                            "arguments": arguments,
                        },
                    }
                )

            wrong_fabricated = {
                **common,
                "request_id": "wrong-fabricated",
                "input_ref": {
                    "ticket_digest": first["ticket_digest"],
                    "acceptance_round_id": first["acceptance_round_id"],
                    "question_id": "cq-001",
                },
                "input_digest": first["ticket_digest"],
            }
            self.assertEqual(call(wrong_fabricated, 1)["error"]["code"], -32001)

            cross_round = {
                **common,
                "request_id": "wrong-cross-round",
                "input_ref": second_source,
                "input_digest": second_digest,
            }
            self.assertEqual(call(cross_round, 2)["error"]["code"], -32001)

            cross_kind = {
                **common,
                "request_id": "wrong-cross-kind",
                "input_ref": first_platform,
                "input_digest": first_platform_digest,
            }
            self.assertEqual(call(cross_kind, 3)["error"]["code"], -32001)

            # A partial legacy binding is rejected by the endpoint schema before
            # dispatch, so it cannot accidentally trigger Host derivation.
            partial = {
                **common,
                "request_id": "wrong-partial",
                "input_digest": first_digest,
            }
            self.assertEqual(call(partial, 4)["error"]["code"], -32001)
            unknown = {
                **common,
                "request_id": "wrong-unknown",
                "input_hint": "must-not-be-accepted",
            }
            self.assertEqual(call(unknown, 5)["error"]["code"], -32001)

            # Direct dispatch bypasses the schema.  Even when a wrong/cross-bound
            # input_ref is supplied directly, the Host ignores it and starts the
            # child with its own projection; the resulting handle's input_digest
            # is the Host projection's digest, not the supplied wrong one.
            handle = carrier._dispatch_capability(
                "acceptance",
                "acceptance_child_start",
                {
                    "acceptance_id": "acceptance",
                    "round_id": first["acceptance_round_id"],
                    "kind": "source",
                    "request_id": "host-overrides-wrong-input",
                    "input_ref": second_source,
                    "input_digest": second_digest,
                    "ticket_digest": "0" * 64,
                    "attempt": 9,
                },
            )
            self.assertEqual(handle.input_digest, first_digest)
            self.assertEqual(handle.ticket_digest, first["ticket_digest"])
            self.assertEqual(handle.attempt, 0)
            carrier.cleanup()

    def test_capability_get_report_failure_readiness_recycles_once_then_blocks(self) -> None:
        from modeling_team.tests.test_r23005_contracts import _ticket

        ticket = _ticket("watchdog")
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory),
                task_id=ticket["task_id"],
                acceptance_id="acceptance",
                child_factory=_ImmediateFailureResource,
            )
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                ticket_digest_value=ticket["ticket_digest"],
            )
            projection, input_digest = carrier.project_child_input(
                round_id=ticket["acceptance_round_id"], kind="source"
            )
            args = {
                "acceptance_id": "acceptance",
                "round_id": ticket["acceptance_round_id"],
                "kind": "source",
                "input_ref": projection,
                "input_digest": input_digest,
                "ticket_digest": ticket["ticket_digest"],
                "request_id": "cap-start-0",
                "attempt": 0,
            }
            handle0 = carrier._dispatch_capability("acceptance", "acceptance_child_start", args)
            readiness0 = carrier._dispatch_capability(
                "acceptance",
                "acceptance_child_get_report",
                {
                    "acceptance_id": "acceptance",
                    "round_id": ticket["acceptance_round_id"],
                    "child_handle": handle0.token,
                    "request_id": "cap-report-0",
                },
            )
            self.assertEqual(readiness0["type"], "infrastructure_failure")
            failure0 = carrier._dispatch_capability(
                "acceptance",
                "acceptance_get_failure_record",
                {
                    "acceptance_id": "acceptance",
                    "round_id": ticket["acceptance_round_id"],
                    "failure_digest": readiness0["failure_digest"],
                },
            )
            self.assertEqual(failure0.failure_digest, readiness0["failure_digest"])
            carrier._dispatch_capability(
                "acceptance",
                "acceptance_child_recycle",
                {
                    "acceptance_id": "acceptance",
                    "round_id": ticket["acceptance_round_id"],
                    "child_handle": handle0.token,
                    "completion_ref": {"infrastructure_failure_digest": readiness0["failure_digest"]},
                    "request_id": "cap-recycle-0",
                },
            )
            args.update({"request_id": "cap-start-1", "attempt": 1})
            handle1 = carrier._dispatch_capability("acceptance", "acceptance_child_start", args)
            readiness1 = carrier._dispatch_capability(
                "acceptance",
                "acceptance_child_get_report",
                {
                    "acceptance_id": "acceptance",
                    "round_id": ticket["acceptance_round_id"],
                    "child_handle": handle1.token,
                    "request_id": "cap-report-1",
                },
            )
            self.assertEqual(readiness1["type"], "infrastructure_failure")
            carrier._dispatch_capability(
                "acceptance",
                "acceptance_child_recycle",
                {
                    "acceptance_id": "acceptance",
                    "round_id": ticket["acceptance_round_id"],
                    "child_handle": handle1.token,
                    "completion_ref": {"infrastructure_failure_digest": readiness1["failure_digest"]},
                    "request_id": "cap-recycle-1",
                },
            )
            with self.assertRaises(AcceptanceContractError):
                args.update({"request_id": "cap-start-2", "attempt": 2})
                carrier._dispatch_capability("acceptance", "acceptance_child_start", args)
            self.assertEqual(carrier.round_summary(ticket["acceptance_round_id"])["status"], "blocked")
            carrier.cleanup()

    def test_carrier_platform_mcp_startup_mismatch_returns_failure_and_retries_once(self) -> None:
        from modeling_team.tests.test_r23005_contracts import _ticket

        ticket = _ticket("startup")
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            auth_home = base / "codex-home"
            auth_home.mkdir(mode=0o700)
            (auth_home / "auth.json").write_text("{}", encoding="utf-8")
            (auth_home / "auth.json").chmod(0o600)
            process_calls = []

            def process_factory(command, **kwargs):
                process_calls.append((command, kwargs))
                return _FakeProcess(command, kwargs)

            adapter = CodexRuntimeAdapter(
                repository_root=root,
                use_bwrap=False,
                process_factory=process_factory,
            )
            adapter._rpc = lambda _agent, method, _params: (
                {"thread": {"id": "startup-thread"}}
                if method == "thread/start"
                else {"turn": {"id": "startup-turn"}}
                if method == "turn/start"
                else {}
            )
            adapter._require_mcp_surface = lambda _agent, _expected: (_ for _ in ()).throw(
                CodexRuntimeError("mcp inventory mismatch")
            )
            carrier = RunnerAcceptanceCarrier(
                base / "carrier",
                task_id=ticket["task_id"],
                acceptance_id="acceptance",
                child_factory=adapter.acceptance_child_factory,
            )
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                ticket_digest_value=ticket["ticket_digest"],
            )
            projection, input_digest = carrier.project_child_input(
                round_id=ticket["acceptance_round_id"], kind="platform"
            )
            with patch.dict(os.environ, {"CODEX_HOME": str(auth_home)}, clear=False):
                handle0 = carrier.start_child(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    kind="platform",
                    input_ref=projection,
                    input_digest=input_digest,
                    ticket_digest_value=ticket["ticket_digest"],
                    request_id="startup-child-0",
                    attempt=0,
                )
            readiness0 = carrier.get_report(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle0,
                request_id="startup-report-0",
            )
            self.assertEqual(readiness0["type"], "infrastructure_failure")
            self.assertEqual(readiness0["reason_code"], "child-start-failed")
            self.assertEqual(readiness0["attempt"], 0)
            resource0 = carrier.child_resource_receipt(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle0,
            )
            self.assertFalse((base / resource0.private_root).exists())
            self.assertFalse((Path("/tmp") / f"mt-ex-{handle0.digest[:24]}").exists())
            self.assertEqual(adapter.cleanup_identifiers()["acceptance_children"]["active"], 0)
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle0,
                completion_ref={"infrastructure_failure_digest": readiness0["failure_digest"]},
                request_id="startup-recycle-0",
            )
            with patch.dict(os.environ, {"CODEX_HOME": str(auth_home)}, clear=False):
                handle1 = carrier.start_child(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    kind="platform",
                    input_ref=projection,
                    input_digest=input_digest,
                    ticket_digest_value=ticket["ticket_digest"],
                    request_id="startup-child-1",
                    attempt=1,
                )
            readiness1 = carrier.get_report(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle1,
                request_id="startup-report-1",
            )
            self.assertEqual(readiness1["reason_code"], "child-start-failed")
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle1,
                completion_ref={"infrastructure_failure_digest": readiness1["failure_digest"]},
                request_id="startup-recycle-1",
            )
            self.assertEqual(carrier.round_summary(ticket["acceptance_round_id"])["status"], "blocked")
            self.assertEqual(adapter.cleanup_identifiers()["acceptance_children"]["active"], 0)
            carrier.cleanup()
            adapter.stop()

    def test_acceptance_package_and_skill_describe_only_runner_owned_retry(self) -> None:
        root = Path(__file__).resolve().parents[2]
        skill = (root / "modeling_team" / "skills" / "acceptance" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        instructions = (root / "modeling_team" / "agent-packages" / "acceptance" / "instructions.md").read_text(encoding="utf-8")
        for text in (skill, instructions):
            self.assertIn("Runner-owned", text)
            self.assertIn("attempt-0", text)
            self.assertIn("infrastructure", text)
            self.assertIn("BLOCKED", text)
            self.assertIn("input_ref", text)
            self.assertIn("input_digest", text)
            self.assertIn("omit", text.lower())
            self.assertNotIn("start or control examiner children", text)
        self.assertIn("opaque child", instructions)
        self.assertIn("fixed not-ready", " ".join(instructions.split()))

    def test_child_mcp_inventory_mismatch_fails_before_turn(self) -> None:
        adapter = CodexRuntimeAdapter(repository_root=Path(__file__).resolve().parents[2], use_bwrap=False)
        adapter._rpc = lambda _agent, _method, _params: {
            "data": [{"name": "examiner_report", "tools": [{"name": "submit_examiner_report"}]}]
        }
        agent = SimpleNamespace(agent_id="platform-examiner", package=SimpleNamespace(package_id="platform-examiner"))
        with patch("modeling_team.runtimes.codex.time.monotonic", side_effect=[0, 1, 100]), patch(
            "modeling_team.runtimes.codex.time.sleep", return_value=None
        ), self.assertRaises(CodexRuntimeError):
            adapter._require_mcp_surface(
                agent,
                {
                    "examiner_report": {"submit_examiner_report"},
                    "platform_read_proxy": set(PLATFORM_PROXY_READ_TOOLS),
                },
            )

    def test_formal_platform_key_uses_scope_api_and_proves_post_revoke_denial(self) -> None:
        scope = _FakePlatformScope()
        forwarders: list[_FakeForwarder] = []

        def make_forwarder(**_kwargs):
            forwarder = _FakeForwarder()
            forwarders.append(forwarder)
            return forwarder

        lifecycle = PlatformApiReadKeyLifecycle(
            scope,
            forwarder_factory=make_forwarder,
        )
        record = lifecycle.create(
            project_id="project-one",
            ontology_id="ontology-one",
            acceptance_round_id="round-one",
            ticket_digest_value="a" * 64,
            input_digest="b" * 64,
            config_digest="c" * 64,
        )
        forward = lifecycle.forwarder_for(record.key_id, expected_tools=["check_platform_health"])
        forwarded = forward("check_platform_health", {"cursor": "next", "limit": 2}, "temporary-read-key")
        self.assertEqual(forwarded["arguments"], {"cursor": "next", "limit": 2})
        revoked = lifecycle.revoke(record.key_id)
        self.assertEqual(revoked.status, "revoked")
        self.assertEqual(lifecycle.post_revoke_denial_count(record.key_id), 1)
        self.assertTrue(forwarders[0].stopped)
        self.assertEqual(
            [call[1] for call in scope.calls],
            [
                "/api/api-keys",
                "/api/api-keys/platform-key-1:revoke",
                "/api/api-keys/platform-key-1",
                "/api/projects/project-one",
            ],
        )
        lifecycle.assert_no_active()

    def test_watchdog_records_only_fixed_failure_codes(self) -> None:
        failures = []
        resource = _CodexChildResource(
            {
                "record_infrastructure_failure": lambda category, reason: failures.append((category, reason)) or {"ok": True},
                "timeout_seconds": 5,
            },
            _CrashProcess([], {}),
        )
        for _ in range(20):
            if failures:
                break
            time.sleep(0.01)
        self.assertEqual(failures, [("runtime", "child-crash")])
        self.assertEqual(resource.failure_evidence(), {"failure_category": "runtime", "reason_code": "child-crash"})
        resource.destroy()

    def test_scoped_proxy_validates_scope_allowlist_and_post_revoke_denial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            proxy = ScopedReadProxy(
                socket_path=Path(directory) / "proxy.sock",
                token="proxy-token",
                read_key="temporary-read-key",
                project_id="project-one",
                ontology_id="ontology-one",
                graph_set_id="graph-one",
                ticket_digest="a" * 64,
                model_state_digest="b" * 64,
                allowed_tools=list(PLATFORM_PROXY_READ_TOOLS),
            )
            receipt = proxy.start()
            self.assertEqual(receipt.allowed_tools, PLATFORM_PROXY_READ_TOOLS)
            self.assertEqual(proxy.handle({"token": "proxy-token", "operation": "tools/list"})["tools"], list(PLATFORM_PROXY_READ_TOOLS))
            arguments = {
                "project_id": "project-one",
                "ontology_id": "ontology-one",
                "graph_set_id": "graph-one",
                "ticket_digest": "a" * 64,
                "model_state_digest": "b" * 64,
            }
            self.assertEqual(proxy.handle({"token": "proxy-token", "operation": "tools/call", "tool": "get_ontology_read_model", "arguments": arguments})["code"], "platform-forwarding-unconfigured")
            arguments["ontology_id"] = "foreign-ontology"
            self.assertEqual(proxy.handle({"token": "proxy-token", "operation": "tools/call", "tool": "get_ontology_read_model", "arguments": arguments})["code"], "read-scope-denied")
            proxy.revoke()
            denied = proxy.handle({"token": "proxy-token", "operation": "tools/list"})
            self.assertEqual(denied["code"], "read-key-revoked")
            self.assertEqual(proxy.post_revoke_denials, 1)
            proxy.destroy()
            self.assertFalse((Path(directory) / "proxy.sock").exists())

    def test_scoped_proxy_preserves_pagination_arguments_and_typed_result_digest(self) -> None:
        captured = []

        def forward(tool, arguments, read_key):
            captured.append((tool, dict(arguments), read_key))
            return {"items": [{"id": "item-1"}], "next_cursor": "cursor-2"}

        with tempfile.TemporaryDirectory() as directory:
            proxy = ScopedReadProxy(
                socket_path=Path(directory) / "proxy.sock",
                token="proxy-token",
                read_key="temporary-read-key",
                project_id="project-one",
                ontology_id="ontology-one",
                graph_set_id="graph-one",
                ticket_digest="a" * 64,
                model_state_digest="b" * 64,
                allowed_tools=list(PLATFORM_PROXY_READ_TOOLS),
                forward=forward,
            )
            arguments = {
                "project_id": "project-one",
                "ontology_id": "ontology-one",
                "graph_set_id": "graph-one",
                "ticket_digest": "a" * 64,
                "model_state_digest": "b" * 64,
                "cursor": "cursor-1",
                "page_size": 10,
                "entity_iri": "https://example.test/rule",
            }
            result = proxy.handle(
                {
                    "token": "proxy-token",
                    "operation": "tools/call",
                    "tool": "get_entity_statement_context",
                    "arguments": arguments,
                }
            )
            self.assertTrue(result["ok"])
            self.assertEqual(captured, [("get_entity_statement_context", arguments, "temporary-read-key")])
            self.assertEqual(result["result"]["next_cursor"], "cursor-2")
            self.assertEqual(len(result["response_digest"]), 64)

    def test_default_codex_child_stages_private_process_proxy_and_first_turn(self) -> None:
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            private_root = base / "private-child"
            private_root.mkdir(mode=0o700)
            (private_root / "input.json").write_text("{}", encoding="utf-8")
            auth_home = base / "codex-home"
            auth_home.mkdir(mode=0o700)
            (auth_home / "auth.json").write_text("{}", encoding="utf-8")
            (auth_home / "auth.json").chmod(0o600)
            process_calls: list[tuple[list[str], dict[str, object]]] = []

            def process_factory(command, **kwargs):
                process_calls.append((command, kwargs))
                return _FakeProcess(command, kwargs)

            adapter = CodexRuntimeAdapter(repository_root=root, use_bwrap=False, process_factory=process_factory)
            adapter._rpc = lambda _agent, method, _params: (
                {"thread": {"id": "child-thread"}}
                if method == "thread/start"
                else {"turn": {"id": "child-turn"}}
                if method == "turn/start"
                else {
                    "data": [
                        {"name": "examiner_report", "tools": [{"name": "submit_examiner_report"}]},
                        {"name": "platform_read_proxy", "tools": [{"name": name} for name in PLATFORM_PROXY_READ_TOOLS]},
                    ]
                }
                if method == "mcpServerStatus/list"
                else {}
            )
            spec = {
                "task_id": "task-one",
                "acceptance_round_id": "round-one",
                "kind": "platform",
                "attempt": 0,
                "session_id": "session-one",
                "child_handle_digest": "c" * 64,
                "ticket_digest": "a" * 64,
                "input_digest": "d" * 64,
                "private_root": str(private_root),
                "private_input": str(private_root / "input.json"),
                "read_key_id": "read-key-one",
                "read_key_digest": "e" * 64,
                "descriptor": {"kind": "platform_examiner", "package_digest": "f" * 64},
                "platform_read_scope": {"project_id": "project-one", "ontology_id": "ontology-one", "graph_set_id": "graph-one"},
                "model_state_digest": "b" * 64,
                "allowed_read_tools": list(PLATFORM_PROXY_READ_TOOLS),
                "read_key_plaintext": "temporary-read-key",
                "read_key_revoke": lambda _key_id: None,
                "timeout_seconds": 30,
            }
            # R2.3-008: the child env also carries the Host's proxy variables
            # (this host only reaches the model endpoint through a local
            # proxy); pin them deterministically for the exact-equality check.
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(auth_home),
                    "http_proxy": "http://127.0.0.1:1080",
                    "https_proxy": "http://127.0.0.1:1080",
                    "no_proxy": "localhost,127.0.0.1,::1",
                    "HTTP_PROXY": "",
                    "HTTPS_PROXY": "",
                    "NO_PROXY": "",
                },
                clear=False,
            ):
                resource = adapter.acceptance_child_factory(spec)
            self.assertEqual(resource.thread_id, "child-thread")
            self.assertEqual(resource.first_turn_input[0]["type"], "text")
            self.assertIsNotNone(resource.proxy)
            self.assertEqual(process_calls[0][1]["env"], {
                "CODEX_HOME": str(private_root / "home"),
                "HOME": str(private_root / "home"),
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "TERM": "xterm-256color",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "http_proxy": "http://127.0.0.1:1080",
                "https_proxy": "http://127.0.0.1:1080",
                "no_proxy": "localhost,127.0.0.1,::1",
            })
            self.assertNotIn("team_transport", (private_root / "home" / "config.toml").read_text(encoding="utf-8"))
            self.assertIn("platform_read_proxy", (private_root / "home" / "config.toml").read_text(encoding="utf-8"))
            child_config = (private_root / "home" / "child-config.json").read_text(encoding="utf-8")
            credential_manifest = (private_root / "home" / "child-credential-manifest.json").read_text(encoding="utf-8")
            self.assertNotIn(str(private_root), child_config)
            self.assertNotIn(str(private_root), credential_manifest)
            self.assertNotIn("temporary-read-key", child_config)
            self.assertNotIn("temporary-read-key", credential_manifest)
            self.assertEqual((private_root / "home" / "child-config.json").read_text(encoding="utf-8").count("platform-proxy.sock"), 1)
            self.assertIn("submit_examiner_report", resource.first_turn_input[0]["text"])
            self.assertNotIn("/agent/home/report.sock", resource.first_turn_input[0]["text"])
            self.assertIn("child-thread", resource.thread_id)
            self.assertIn("c" * 64, adapter._acceptance_children)
            resource.destroy()
            self.assertNotIn("c" * 64, adapter._acceptance_children)
            adapter.stop()
            self.assertTrue(resource.destroyed)
            self.assertFalse(private_root.exists())


if __name__ == "__main__":
    unittest.main()
