from __future__ import annotations

import contextlib
import importlib.util
import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "modeling_handoff", Path(__file__).resolve().parents[1] / "lib" / "modeling_handoff.py"
)
assert SPEC and SPEC.loader
handoff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = handoff
SPEC.loader.exec_module(handoff)


def valid_draft() -> dict:
    traces = json.loads(
        (REPO / "skills/ontology-builder/evals/example-traces.json").read_text(encoding="utf-8")
    )
    return next(
        trace["modeler_handoff"]
        for trace in traces
        if trace["id"] == "modeler-vertical-slice-and-dry-run"
    )


def prepare_worker(root: str, source: str, generation_id: str, queue) -> None:
    spool = handoff.Spool(REPO, root=Path(root))
    try:
        spool.prepare(
            build_session_id="concurrent-session",
            artifact_key="modeling-draft",
            generation_id=generation_id,
            expected_previous_generation_id=None,
            correction_round=0,
            inputs={"prompt.md": Path(source)},
            prompt_input="prompt.md",
        )
    except handoff.HandoffError as exc:
        queue.put(exc.code)
    else:
        queue.put("won")


class ModelingHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.spool = handoff.Spool(REPO, root=self.root / "spool")
        self.inputs = self.root / "source"
        self.inputs.mkdir()
        (self.inputs / "prompt.md").write_text(
            "Return the exact structured draft.", encoding="utf-8"
        )
        (self.inputs / "pack.json").write_text('{"version":1}', encoding="utf-8")
        self.common = {
            "build_session_id": "session-12345678",
            "artifact_key": "modeling-draft",
            "generation_id": "generation-0001",
            "expected_previous_generation_id": None,
            "correction_round": 0,
            "inputs": {
                "prompt.md": self.inputs / "prompt.md",
                "pack.json": self.inputs / "pack.json",
            },
            "prompt_input": "prompt.md",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare(self, **changes):
        arguments = dict(self.common)
        arguments.update(changes)
        manifest = self.spool.prepare(**arguments)
        paths = self.spool.paths(
            arguments["build_session_id"], arguments["artifact_key"], arguments["generation_id"]
        )
        return paths, manifest

    def complete_process(self, paths, document, *, exit_code=0, as_final=False):
        state = self.spool._state(paths)
        state["state"] = "running"
        state["supervisor_identity"] = {
            "pid": 999999,
            "start_ticks": 1,
            "cmdline_sha256": "a" * 64,
        }
        self.spool._write_state(paths, state)
        payload = (
            document
            if isinstance(document, bytes)
            else json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        )
        target = paths.draft if as_final else paths.temporary
        target.write_bytes(payload)
        os.chmod(target, 0o600)
        handoff.atomic_json(
            paths.status,
            {
                "status_version": 1,
                "generation_id": paths.generation_id,
                "supervisor_identity": state["supervisor_identity"],
                "child_identity": {"pid": 999998, "start_ticks": 1, "cmdline_sha256": "b" * 64},
                "started_at": handoff.now_iso(),
                "completed_at": handoff.now_iso(),
                "exit_code": exit_code,
                "signal": None,
                "output_size_bytes": len(payload),
                "output_sha256": handoff.sha256_bytes(payload),
                "diagnostic": "",
            },
        )
        return payload

    def assert_error(self, code, callback):
        with self.assertRaises(handoff.HandoffError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_prepare_is_owner_only_and_idempotent(self):
        paths, first = self.prepare()
        second = self.spool.prepare(**self.common)
        self.assertEqual(first, second)
        self.assertEqual(paths.generation.stat().st_mode & 0o777, 0o700)
        self.assertEqual((paths.inputs / "prompt.md").stat().st_mode & 0o777, 0o400)
        handoff.atomic_json(paths.chain / "head.json", {"generation_id": None})
        self.spool.prepare(**self.common)
        self.assertEqual(
            handoff.read_object(paths.chain / "head.json")["generation_id"],
            paths.generation_id,
        )
        changed = dict(self.common)
        changed["correction_round"] = 1
        self.assert_error("generation_id_conflict", lambda: self.spool.prepare(**changed))

    def test_chain_head_cas_conflict_and_independent_key(self):
        self.prepare()
        self.assert_error(
            "generation_conflict",
            lambda: self.prepare(generation_id="generation-0002"),
        )
        _, manifest = self.prepare(artifact_key="other-draft", generation_id="generation-0002")
        self.assertEqual(manifest["state"], "prepared")

    def test_concurrent_cas_has_exactly_one_winner(self):
        queue = multiprocessing.Queue()
        workers = [
            multiprocessing.Process(
                target=prepare_worker,
                args=(
                    str(self.root / "race-spool"),
                    str(self.inputs / "prompt.md"),
                    f"generation-race-{index}",
                    queue,
                ),
            )
            for index in range(2)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(10)
            self.assertEqual(worker.exitcode, 0)
        self.assertCountEqual(
            [queue.get(timeout=2), queue.get(timeout=2)],
            ["won", "generation_conflict"],
        )

    def test_successful_publication_validation_and_cleanup(self):
        paths, _ = self.prepare()
        payload = self.complete_process(paths, valid_draft())
        manifest = self.spool.recover(paths)
        self.assertEqual(manifest["state"], "validated")
        self.assertEqual(manifest["sha256"], handoff.sha256_bytes(payload))
        self.assertEqual(manifest["item_count"], 4)
        self.assertFalse(paths.temporary.exists())
        self.assertTrue(paths.draft.is_file())
        persisted = self.spool.mark_persisted(
            paths,
            workflow_artifact_id="artifact-12345678",
            canonical_content_hash=manifest["canonical_content_hash"],
        )
        self.assertEqual(persisted["state"], "cleaned")
        self.assertFalse(paths.draft.exists())
        self.assertFalse(paths.inputs.exists())
        self.assertLess(len(handoff.canonical_bytes(persisted)), handoff.MAX_MANIFEST_BYTES)

    def test_recovery_after_atomic_rename_repairs_state(self):
        paths, _ = self.prepare()
        self.complete_process(paths, valid_draft(), as_final=True)
        manifest = self.spool.recover(paths)
        self.assertEqual(manifest["state"], "validated")

    def test_nonzero_process_never_publishes(self):
        paths, _ = self.prepare()
        self.complete_process(paths, valid_draft(), exit_code=9)
        self.assert_error("handoff_process_failed", lambda: self.spool.recover(paths))
        self.assertFalse(paths.draft.exists())

    def test_missing_or_mismatched_status_is_unknown(self):
        paths, _ = self.prepare()
        state = self.spool._state(paths)
        state["state"] = "running"
        state["supervisor_identity"] = {"pid": 999999, "start_ticks": 1, "cmdline_sha256": "x"}
        self.spool._write_state(paths, state)
        self.assert_error("handoff_exit_status_unknown", lambda: self.spool.recover(paths))

    def test_hash_mismatch_fails_closed(self):
        paths, _ = self.prepare()
        self.complete_process(paths, valid_draft())
        paths.temporary.write_text("{}", encoding="utf-8")
        os.chmod(paths.temporary, 0o600)
        self.assert_error("handoff_hash_mismatch", lambda: self.spool.recover(paths))

    def test_nonstandard_or_duplicate_key_json_is_rejected(self):
        invalid_payloads = [
            b'{"vertical_slice_rationale":NaN}',
            b'{"vertical_slice_rationale":"one","vertical_slice_rationale":"two"}',
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload[:30]):
                self.tearDown()
                self.setUp()
                paths, _ = self.prepare()
                self.complete_process(paths, payload)
                self.assert_error("handoff_schema_invalid", lambda: self.spool.recover(paths))

    def test_diagnostic_accumulator_is_bounded_and_detects_split_secret(self):
        accumulator = handoff.DiagnosticAccumulator()
        first = b"Z" * 200_000 + b" sk-SplitBound"
        second = b"arySecret1234567890"
        accumulator.feed(first)
        self.assertLessEqual(len(accumulator._overlap), handoff.MAX_SECRET_SCAN_OVERLAP)
        accumulator.feed(second)
        summary = accumulator.finish()
        self.assertEqual(summary["stderr_bytes_observed"], len(first) + len(second))
        self.assertEqual(summary["secret_categories"], ["openai_style_key"])
        self.assertEqual(accumulator._overlap, b"")
        self.assertNotIn("SplitBoundarySecret", json.dumps(summary))

    def test_modeler_ignores_user_config_and_receives_no_credential_environment(self):
        live_spool = handoff.Spool(REPO)
        session_id = f"test-{uuid.uuid4().hex}"
        generation_id = f"test-{uuid.uuid4().hex}"
        fake_codex_home = self.root / "codex-home"
        fake_codex_home.mkdir(mode=0o700)
        (fake_codex_home / "auth.json").write_text(
            '{"auth_mode":"file-backed-test-auth"}', encoding="utf-8"
        )
        (fake_codex_home / "config.toml").write_text(
            '[mcp_servers.ontology]\ncommand="malicious-ontology-mcp"\n', encoding="utf-8"
        )
        fake = self.root / "config-auditing-fake-codex"
        draft_text = json.dumps(valid_draft(), ensure_ascii=False)
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "args = sys.argv\n"
            "target = pathlib.Path(args[args.index('--output-last-message') + 1])\n"
            "config = pathlib.Path(os.environ['CODEX_HOME']) / 'config.toml'\n"
            "audit = {\n"
            "    'argv': args[1:],\n"
            "    'environment': dict(os.environ),\n"
            "    'user_mcp_config_loaded': (\n"
            "        config.exists() and '--ignore-user-config' not in args\n"
            "    ),\n"
            "    'auth_store_visible': (\n"
            "        pathlib.Path(os.environ['CODEX_HOME']) / 'auth.json'\n"
            "    ).is_file(),\n"
            "}\n"
            "(target.parent / 'invocation-audit.json').write_text(\n"
            "    json.dumps(audit, sort_keys=True), encoding='utf-8'\n"
            ")\n"
            "sys.stdin.read()\n"
            f"target.write_text({draft_text!r}, encoding='utf-8')\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        inherited = {
            "HOME": str(self.root / "home"),
            "CODEX_HOME": str(fake_codex_home),
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "HTTPS_PROXY": "https://proxy.example",
            "HTTP_PROXY": "http://proxy-user:proxy-password@proxy.example",
            "ONTOLOGY_MCP_API_KEY": "platform-key-must-not-cross",
            "MCP_GATEWAY_TOKEN": "mcp-token-must-not-cross",
            "PLATFORM_LEASE_TOKEN": "lease-token-must-not-cross",
            "AUTHORIZATION": "Bearer platform-auth-must-not-cross",
            "SESSION_COOKIE": "cookie-must-not-cross",
            "DATABASE_PASSWORD": "password-must-not-cross",
            "OPENAI_API_KEY": "environment-auth-must-not-cross",
        }
        try:
            live_spool.prepare(
                build_session_id=session_id,
                artifact_key="modeling-draft",
                generation_id=generation_id,
                expected_previous_generation_id=None,
                correction_round=0,
                inputs={"prompt.md": self.inputs / "prompt.md"},
                prompt_input="prompt.md",
            )
            paths = live_spool.paths(session_id, "modeling-draft", generation_id)
            with mock.patch.dict(os.environ, inherited, clear=True):
                completed = live_spool.start_codex(paths, codex_bin=str(fake))
            self.assertEqual(completed["state"], "validated")
            audit = json.loads(
                (paths.generation / "invocation-audit.json").read_text(encoding="utf-8")
            )
            self.assertIn("--ignore-user-config", audit["argv"])
            self.assertFalse(audit["user_mcp_config_loaded"])
            self.assertTrue(audit["auth_store_visible"])
            environment = audit["environment"]
            self.assertEqual(environment["CODEX_HOME"], str(fake_codex_home))
            self.assertEqual(environment["HTTPS_PROXY"], "https://proxy.example")
            self.assertNotIn("HTTP_PROXY", environment)
            for denied_part in handoff.DENIED_ENV_PARTS:
                self.assertFalse(
                    any(denied_part in key.upper() for key in environment),
                    f"credential category crossed into modeler env: {denied_part}",
                )
            self.assertNotIn("OPENAI_API_KEY", environment)
            self.assertEqual(
                handoff.safe_modeler_environment({}),
                {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
            )
        finally:
            live_spool.cleanup_session(session_id)

    def test_secret_is_deleted_and_never_in_manifest(self):
        paths, _ = self.prepare()
        secret = b'{"authorization":"Bearer abcdefghijklmnopqrstuvwxyz"}'
        self.complete_process(paths, secret)
        self.assert_error("handoff_secret_detected", lambda: self.spool.recover(paths))
        self.assertFalse(paths.temporary.exists())
        manifest = paths.manifest.read_text(encoding="utf-8")
        state = paths.state.read_text(encoding="utf-8")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", manifest + state)

    def test_invalid_schema_duplicate_dependency_cycle_and_item_ref(self):
        invalid_documents = []
        missing_field = valid_draft()
        missing_field.pop("handoff_summary")
        invalid_documents.append(missing_field)

        duplicate = valid_draft()
        duplicate["modeling_batch"]["items"][1]["client_item_id"] = duplicate["modeling_batch"][
            "items"
        ][0]["client_item_id"]
        invalid_documents.append(duplicate)

        cycle = valid_draft()
        first, second = cycle["modeling_batch"]["items"][:2]
        first["depends_on"] = [second["client_item_id"]]
        second["depends_on"] = [first["client_item_id"]]
        invalid_documents.append(cycle)

        unresolved = valid_draft()
        unresolved["modeling_batch"]["items"][1]["payload"]["class_id"]["item_ref"][
            "client_item_id"
        ] = "missing-item"
        invalid_documents.append(unresolved)

        for index, document in enumerate(invalid_documents):
            with self.subTest(index=index):
                self.tearDown()
                self.setUp()
                paths, _ = self.prepare()
                self.complete_process(paths, document)
                expected = "handoff_schema_invalid" if index == 0 else "handoff_reference_invalid"
                self.assert_error(expected, lambda: self.spool.recover(paths))

    def test_canonical_one_mib_boundary_is_exact(self):
        for extra, expected in ((0, "validated"), (1, "handoff_too_large")):
            with self.subTest(extra=extra):
                self.tearDown()
                self.setUp()
                document = valid_draft()
                document["handoff_summary"] = ""
                base_size = len(handoff.canonical_bytes(document))
                document["handoff_summary"] = "x" * (handoff.MAX_ARTIFACT_BYTES + extra - base_size)
                self.assertEqual(
                    len(handoff.canonical_bytes(document)),
                    handoff.MAX_ARTIFACT_BYTES + extra,
                )
                paths, _ = self.prepare()
                self.complete_process(paths, document)
                if expected == "validated":
                    self.assertEqual(self.spool.recover(paths)["state"], expected)
                else:
                    self.assert_error(expected, lambda: self.spool.recover(paths))

    def test_symlink_output_is_rejected(self):
        paths, _ = self.prepare()
        outside = self.root / "outside.json"
        outside.write_text(json.dumps(valid_draft()), encoding="utf-8")
        state = self.spool._state(paths)
        state["state"] = "running"
        state["supervisor_identity"] = {"pid": 999999, "start_ticks": 1, "cmdline_sha256": "a"}
        self.spool._write_state(paths, state)
        paths.temporary.symlink_to(outside)
        handoff.atomic_json(
            paths.status,
            {
                "generation_id": paths.generation_id,
                "supervisor_identity": state["supervisor_identity"],
                "child_identity": {"pid": 9},
                "completed_at": handoff.now_iso(),
                "exit_code": 0,
                "output_size_bytes": outside.stat().st_size,
                "output_sha256": handoff.sha256_bytes(outside.read_bytes()),
            },
        )
        self.assert_error("handoff_file_unsafe", lambda: self.spool.recover(paths))

    def test_modified_after_validation_and_platform_hash_conflict(self):
        paths, _ = self.prepare()
        self.complete_process(paths, valid_draft())
        self.spool.recover(paths)
        paths.draft.write_bytes(paths.draft.read_bytes() + b" ")
        self.assert_error("handoff_hash_mismatch", lambda: self.spool.recover(paths))

        self.tearDown()
        self.setUp()
        paths, _ = self.prepare()
        self.complete_process(paths, valid_draft())
        self.spool.recover(paths)
        self.assert_error(
            "handoff_platform_hash_conflict",
            lambda: self.spool.mark_persisted(
                paths,
                workflow_artifact_id="artifact-12345678",
                canonical_content_hash="0" * 64,
            ),
        )

    def test_rework_limit_and_repeated_failure_class(self):
        paths, _ = self.prepare()
        state = self.spool._state(paths)
        state["failure_class"] = "schema"
        self.spool._write_state(paths, state)
        successor = dict(self.common)
        successor.update(
            generation_id="generation-0002",
            expected_previous_generation_id=paths.generation_id,
            correction_round=1,
            failure_class="schema",
        )
        self.assert_error("handoff_rework_limit", lambda: self.spool.prepare(**successor))
        successor["user_authorization_id"] = "decision-12345678"
        self.assertEqual(self.spool.prepare(**successor)["state"], "prepared")

        third = dict(successor)
        third.update(
            generation_id="generation-0003",
            expected_previous_generation_id="generation-0002",
            correction_round=3,
            failure_class="different",
            user_authorization_id=None,
        )
        self.assert_error("handoff_rework_limit", lambda: self.spool.prepare(**third))

    def test_terminal_and_stale_cleanup_are_bounded(self):
        paths, _ = self.prepare()
        self.assertEqual(self.spool.cleanup_session(paths.build_session_id), 1)
        self.assertFalse((self.spool.root / paths.build_session_id).exists())

        paths, _ = self.prepare(build_session_id="session-87654321")
        state = self.spool._state(paths)
        state["state"] = "cleaned"
        self.spool._write_state(paths, state)
        successor, _ = self.prepare(
            build_session_id="session-87654321",
            generation_id="generation-0002",
            expected_previous_generation_id=paths.generation_id,
            correction_round=1,
        )
        old = handoff.time.time() - 3600
        os.utime(paths.state, (old, old))
        os.utime(successor.state, (old, old))
        self.assertEqual(self.spool.cleanup_stale(60), 1)
        self.assertTrue(paths.generation.exists())
        self.assertFalse(successor.generation.exists())
        self.assertEqual(
            handoff.read_object(paths.chain / "head.json")["generation_id"],
            paths.generation_id,
        )

    def test_detached_supervisor_discards_stdout_and_recovers(self):
        live_spool = handoff.Spool(REPO)
        session_id = f"test-{uuid.uuid4().hex}"
        generation_id = f"test-{uuid.uuid4().hex}"
        fake = self.root / "fake-codex"
        draft_text = json.dumps(valid_draft(), ensure_ascii=False)
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, sys, time\n"
            "args = sys.argv\n"
            "target = pathlib.Path(args[args.index('--output-last-message') + 1])\n"
            "sys.stdin.read()\n"
            "print('X' * 200000)\n"
            "sys.stderr.write('RAW_PROMPT_MARKER_' + 'Y' * 200000 + ' sk-SplitBound')\n"
            "sys.stderr.flush()\n"
            "time.sleep(0.15)\n"
            "sys.stderr.write('arySecret1234567890')\n"
            "sys.stderr.flush()\n"
            "time.sleep(0.3)\n"
            f"target.write_text({draft_text!r}, encoding='utf-8')\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        try:
            manifest = live_spool.prepare(
                build_session_id=session_id,
                artifact_key="modeling-draft",
                generation_id=generation_id,
                expected_previous_generation_id=None,
                correction_round=0,
                inputs={
                    "prompt.md": self.inputs / "prompt.md",
                    "pack.json": self.inputs / "pack.json",
                },
                prompt_input="prompt.md",
            )
            paths = live_spool.paths(session_id, "modeling-draft", generation_id)
            running = live_spool.start_codex(paths, codex_bin=str(fake), wait=False)
            self.assertEqual(running["state"], "running")
            for _ in range(100):
                if paths.status.exists():
                    break
                time.sleep(0.01)
            self.assertTrue(paths.status.exists())
            self.assertEqual(list(paths.generation.glob("*diagnostic*")), [])
            live_status = handoff.read_object(paths.status)
            self.assertLess(len(handoff.canonical_bytes(live_status)), handoff.MAX_MANIFEST_BYTES)
            self.assertNotIn("RAW_PROMPT_MARKER", json.dumps(live_status))
            self.assertNotIn("SplitBoundarySecret", json.dumps(live_status))
            for _ in range(100):
                try:
                    completed = live_spool.recover(paths)
                except handoff.HandoffError as exc:
                    self.assertEqual(exc.code, "handoff_still_running")
                    time.sleep(0.03)
                    continue
                break
            else:
                self.fail("detached supervisor did not complete")
            self.assertEqual(completed["state"], "validated")
            self.assertEqual(completed["item_count"], 4)
            self.assertLess(len(handoff.canonical_bytes(completed)), handoff.MAX_MANIFEST_BYTES)
            self.assertEqual(manifest["generation_id"], completed["generation_id"])
            status = handoff.read_object(paths.status)
            self.assertGreater(status["diagnostic"]["stderr_bytes_observed"], 200_000)
            self.assertIn("openai_style_key", status["diagnostic"]["secret_categories"])
            self.assertLess(len(handoff.canonical_bytes(status)), handoff.MAX_MANIFEST_BYTES)
            persisted_status = json.dumps(status)
            self.assertNotIn("RAW_PROMPT_MARKER", persisted_status)
            self.assertNotIn("SplitBoundarySecret", persisted_status)
            self.assertEqual(list(paths.generation.glob("*diagnostic*")), [])
        finally:
            live_spool.cleanup_session(session_id)

    def test_supervisor_crash_never_leaves_raw_diagnostic_file(self):
        live_spool = handoff.Spool(REPO)
        session_id = f"test-{uuid.uuid4().hex}"
        generation_id = f"test-{uuid.uuid4().hex}"
        fake = self.root / "slow-fake-codex"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import sys, time\n"
            "sys.stdin.read()\n"
            "sys.stderr.write('CRASH_RAW_MARKER_' + 'Q' * 200000)\n"
            "sys.stderr.flush()\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        try:
            live_spool.prepare(
                build_session_id=session_id,
                artifact_key="modeling-draft",
                generation_id=generation_id,
                expected_previous_generation_id=None,
                correction_round=0,
                inputs={"prompt.md": self.inputs / "prompt.md"},
                prompt_input="prompt.md",
            )
            paths = live_spool.paths(session_id, "modeling-draft", generation_id)
            live_spool.start_codex(paths, codex_bin=str(fake), wait=False)
            for _ in range(200):
                if paths.status.exists():
                    break
                time.sleep(0.01)
            status = handoff.read_object(paths.status)
            self.assertEqual(list(paths.generation.glob("*diagnostic*")), [])
            supervisor_identity = status["supervisor_identity"]
            child_identity = status["child_identity"]
            if handoff.identity_is_live(supervisor_identity):
                os.kill(supervisor_identity["pid"], handoff.signal.SIGKILL)
            for _ in range(100):
                if not handoff.identity_is_live(supervisor_identity):
                    break
                time.sleep(0.01)
            if handoff.identity_is_live(child_identity):
                os.killpg(child_identity["pid"], handoff.signal.SIGTERM)
            for _ in range(100):
                if not handoff.identity_is_live(child_identity):
                    break
                time.sleep(0.01)
            self.assertEqual(list(paths.generation.glob("*diagnostic*")), [])
            persisted = "".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in (paths.state, paths.status, paths.manifest)
                if path.exists()
            )
            self.assertNotIn("CRASH_RAW_MARKER", persisted)
            self.assertLess(paths.status.stat().st_size, handoff.MAX_MANIFEST_BYTES)
            self.assert_error("handoff_exit_status_unknown", lambda: live_spool.recover(paths))
        finally:
            with contextlib.suppress(handoff.HandoffError):
                live_spool.cleanup_session(session_id)

    def test_nonzero_supervisor_keeps_only_category_diagnostic(self):
        live_spool = handoff.Spool(REPO)
        session_id = f"test-{uuid.uuid4().hex}"
        generation_id = f"test-{uuid.uuid4().hex}"
        fake = self.root / "failing-fake-codex"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stdin.read()\n"
            "sys.stderr.write('NONZERO_RAW_' + 'N' * 250000 + ' Bearer abcdefghijklmnopqrstuvwxyz')\n"
            "raise SystemExit(9)\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        try:
            live_spool.prepare(
                build_session_id=session_id,
                artifact_key="modeling-draft",
                generation_id=generation_id,
                expected_previous_generation_id=None,
                correction_round=0,
                inputs={"prompt.md": self.inputs / "prompt.md"},
                prompt_input="prompt.md",
            )
            paths = live_spool.paths(session_id, "modeling-draft", generation_id)
            self.assert_error(
                "handoff_process_failed",
                lambda: live_spool.start_codex(paths, codex_bin=str(fake)),
            )
            status = handoff.read_object(paths.status)
            self.assertGreater(status["diagnostic"]["stderr_bytes_observed"], 250_000)
            self.assertIn("bearer_token", status["diagnostic"]["secret_categories"])
            persisted = json.dumps(status)
            self.assertNotIn("NONZERO_RAW", persisted)
            self.assertNotIn("abcdefghijklmnopqrstuvwxyz", persisted)
            self.assertLess(paths.status.stat().st_size, handoff.MAX_MANIFEST_BYTES)
            self.assertEqual(list(paths.generation.glob("*diagnostic*")), [])
        finally:
            live_spool.cleanup_session(session_id)


if __name__ == "__main__":
    unittest.main()
