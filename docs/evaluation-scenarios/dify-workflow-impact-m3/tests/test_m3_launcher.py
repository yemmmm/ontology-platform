"""Focused regression tests for the M3 file-spool isolation contract."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCENARIO_ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gateway = load("m3_spool_gateway", "m3_file_spool_gateway.py")
launcher = load("m3_launcher", "run_autonomous_modeling.py")


class M3LauncherTests(unittest.TestCase):
    def make_gateway(self, root: Path, calls: list[dict]) -> tuple[object, Path, Path, Path]:
        requests, responses, archive = root / "requests", root / "responses", root / "archive"
        requests.mkdir()

        def upstream(request: dict) -> tuple[int, dict[str, str], object]:
            calls.append(request)
            return 200, {"content-type": "application/json", "server": "hidden"}, {"ok": True}

        return (
            gateway.FileSpoolGateway(
                requests=requests,
                responses=responses,
                archive=archive,
                audit_path=root / "audit.jsonl",
                api_key="not-a-real-secret",
                upstream=upstream,
            ),
            requests,
            responses,
            archive,
        )

    def write_request(self, directory: Path, request_id: str, **changes: object) -> Path:
        request = {"id": request_id, "method": "GET", "path": "/api/projects", "headers": {}, "body": None}
        request.update(changes)
        target = directory / f"{request_id}.json"
        target.write_bytes(gateway.canonical_json(request))
        return target

    def rejected(self, root: Path) -> list[dict]:
        return [json.loads(line) for line in (root / "audit.jsonl").read_text().splitlines() if '"rejected"' in line]

    def write_receipt_run(
        self, root: Path, *, run_tag: str = "m3-receipt-test", status: int = 200
    ) -> Path:
        run_dir = root / run_tag
        work, archive, responses = run_dir / "work", run_dir / "gateway-request-archive", run_dir / "gateway-responses"
        work.mkdir(parents=True)
        archive.mkdir()
        responses.mkdir()
        request_id = "receipt01"
        request = {"id": request_id, "method": "GET", "path": "/api/health", "headers": {}, "body": None}
        response = {"id": request_id, "status": status, "headers": {"content-type": "application/json"}, "body": {"ok": True}}
        request_bytes, response_bytes = gateway.canonical_json(request), gateway.canonical_json(response)
        (archive / f"{request_id}.json").write_bytes(request_bytes)
        (responses / f"{request_id}.json").write_bytes(response_bytes)
        (run_dir / "gateway.jsonl").write_text(
            json.dumps(
                {
                    "policy": "forwarded",
                    "request_id": request_id,
                    "status": status,
                    "request_sha256": gateway.sha256_bytes(request_bytes),
                    "response_sha256": gateway.sha256_bytes(response_bytes),
                }
            )
            + "\n"
        )
        receipt = {
            "run_tag": run_tag,
            "request_id": request_id,
            "response_id": request_id,
            "canonical_request_sha256": gateway.sha256_bytes(request_bytes),
            "host_response_sha256": gateway.sha256_bytes(response_bytes),
            "status": status,
            "response_read_confirmed": True,
        }
        receipt_path = work / launcher.RECEIPT_FILENAME
        receipt_path.write_bytes(launcher.canonical_json(receipt) + b"\n")
        digest = launcher.sha256(receipt_path)
        (work / "runtime-record.json").write_text(
            json.dumps(
                {
                    "run_tag": run_tag,
                    "spool_receipt_log": {"path": launcher.RECEIPT_FILENAME, "sha256": digest, "count": 1},
                    "spool_receipts": [receipt],
                }
            )
        )
        (run_dir / "agent-transcript.jsonl").write_text(
            f"M3_RECEIPT_SUMMARY run_tag={run_tag} receipt_count=1 receipt_log_sha256={digest}\n"
        )
        return run_dir

    def write_completed_session_run(
        self, root: Path, *, run_tag: str = "m3-session-test", final_status: str = "completed"
    ) -> Path:
        run_dir = root / run_tag
        work, responses = run_dir / "work", run_dir / "gateway-responses"
        work.mkdir(parents=True)
        responses.mkdir()
        session_id, checkpoint_id = "session-001", "checkpoint-001"
        calls = [
            (
                "checkpoint-request",
                "POST",
                f"/api/build-sessions/{session_id}/checkpoints",
                {"session": {"id": session_id, "revision": 4}, "checkpoint": {"id": checkpoint_id}},
            ),
            (
                "complete-request",
                "POST",
                f"/api/build-sessions/{session_id}:complete",
                {"id": session_id, "status": final_status, "completed_at": "2026-07-26T00:00:00Z"},
            ),
            (
                "final-read-request",
                "GET",
                f"/api/build-sessions/{session_id}",
                {
                    "session": {
                        "id": session_id,
                        "status": final_status,
                        "completed_at": "2026-07-26T00:00:00Z",
                    },
                    "latest_checkpoint": {"id": checkpoint_id},
                },
            ),
        ]
        entries = []
        for request_id, method, path, body in calls:
            response = gateway.canonical_json(
                {"id": request_id, "status": 200, "headers": {}, "body": body}
            )
            (responses / f"{request_id}.json").write_bytes(response)
            entries.append({"policy": "forwarded", "request_id": request_id, "method": method, "path": path, "status": 200})
        (run_dir / "gateway.jsonl").write_text("".join(json.dumps(item) + "\n" for item in entries))
        (work / "runtime-record.json").write_text(
            json.dumps(
                {
                    "run_tag": run_tag,
                    "build_session_id": session_id,
                    "build_session_completion": {
                        "run_tag": run_tag,
                        "checkpoint_id": checkpoint_id,
                        "checkpoint_request_id": "checkpoint-request",
                        "complete_request_id": "complete-request",
                        "final_session_read_request_id": "final-read-request",
                        "status": final_status,
                        "completed_at": "2026-07-26T00:00:00Z",
                    },
                }
            )
        )
        return run_dir

    def test_frozen_manifest_stages_exactly_the_declared_files(self) -> None:
        manifest = launcher.read_manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            staging = Path(temp_dir) / "staging"
            evidence = launcher.verify_and_stage(manifest, staging)
            self.assertEqual(launcher.sha256(staging / "input-manifest.json"), launcher.FROZEN_MANIFEST_SHA256)
            self.assertEqual(set(evidence["declared_mount_set"]), {"input-manifest.json", *(item["mounted_path"] for item in manifest["files"])})

    def test_spool_rejects_symlink_path_traversal_size_non_api_and_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, calls = Path(temp_dir), []
            spool, requests, _, _ = self.make_gateway(root, calls)
            target = root / "outside.json"
            target.write_text("{}")
            (requests / "symlinked.json").symlink_to(target)
            self.write_request(requests, "traversal1", path="/api/../private")
            self.write_request(requests, "nonapi001", path="/docs")
            self.write_request(requests, "authhead1", headers={"Authorization": "forbidden"})
            (requests / "oversize1.json").write_bytes(b"x" * (gateway.MAX_REQUEST_BYTES + 1))
            spool.process_once()
            self.assertEqual(calls, [])
            self.assertGreaterEqual(len(self.rejected(root)), 5)

    def test_spool_rejects_duplicate_id_and_precreated_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, calls = Path(temp_dir), []
            spool, requests, responses, archive = self.make_gateway(root, calls)
            self.write_request(requests, "duplicate1")
            spool.process_once()
            self.assertEqual(len(calls), 1)
            temporary = requests / ".duplicate1.tmp"
            temporary.write_bytes(gateway.canonical_json({"id": "duplicate1", "method": "GET", "path": "/api/health", "headers": {}, "body": None}))
            temporary.replace(requests / "duplicate1.json")
            spool.process_once()
            self.assertEqual(len(calls), 1)
            self.assertTrue((archive / "duplicate1.json").is_file())
            self.assertTrue((responses / "duplicate1.json").is_file())

        with tempfile.TemporaryDirectory() as temp_dir:
            root, calls = Path(temp_dir), []
            spool, requests, responses, _ = self.make_gateway(root, calls)
            self.write_request(requests, "precreate1")
            (responses / "precreate1.json").write_text("forged")
            spool.process_once()
            self.assertEqual(calls, [])
            self.assertTrue(self.rejected(root))

    def test_spool_survives_atomic_temp_entry_that_vanishes_after_scandir(self) -> None:
        class VanishedEntry:
            name = ".m3-request.tmp"

            def stat(self, *, follow_symlinks: bool) -> object:
                raise FileNotFoundError

        class VanishedEntries:
            def __enter__(self) -> list[VanishedEntry]:
                return [VanishedEntry()]

            def __exit__(self, *_: object) -> None:
                return None

        with tempfile.TemporaryDirectory() as temp_dir:
            root, calls = Path(temp_dir), []
            spool, _, _, _ = self.make_gateway(root, calls)
            with patch.object(gateway.os, "scandir", return_value=VanishedEntries()):
                self.assertEqual(spool.process_once(), 0)
            self.assertEqual(calls, [])

    def test_archive_and_audit_use_canonical_hashes_without_request_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root, calls = Path(temp_dir), []
            spool, requests, responses, archive = self.make_gateway(root, calls)
            self.write_request(requests, "canonical1", body={"z": 1, "a": [True]})
            spool.process_once()
            request_bytes = (archive / "canonical1.json").read_bytes()
            response_bytes = (responses / "canonical1.json").read_bytes()
            event = json.loads((root / "audit.jsonl").read_text())
            self.assertEqual(event["request_sha256"], gateway.sha256_bytes(request_bytes))
            self.assertEqual(event["response_sha256"], gateway.sha256_bytes(response_bytes))
            self.assertNotIn("body", event)
            self.assertEqual(calls[0]["body"], {"a": [True], "z": 1})

    def test_response_mount_prevents_precreate_forge_write_replace_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace, responses = root / "work", root / "host-responses"
            (workspace / "rpc" / "requests").mkdir(parents=True)
            (workspace / "rpc" / "responses").mkdir(parents=True)
            responses.mkdir()
            original = gateway.canonical_json({"id": "response1", "status": 200, "headers": {}, "body": {"ok": True}})
            (responses / "response1.json").write_bytes(original)
            command = [
                "bwrap", "--unshare-user", "--unshare-pid", "--clearenv", "--ro-bind", "/usr", "/usr",
                "--ro-bind", "/bin", "/bin", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
                "--bind", str(workspace), "/mnt", "--ro-bind", str(responses), "/mnt/rpc/responses", "--dev", "/dev", "--proc", "/proc", "--",
                "/bin/sh", "-c", "! touch /mnt/rpc/responses/precreate.json && ! printf forged >/mnt/rpc/responses/response1.json && ! printf after >>/mnt/rpc/responses/response1.json && ! mv /mnt/rpc/responses/response1.json /mnt/rpc/responses/replaced.json && ! rm /mnt/rpc/responses/response1.json",
            ]
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((responses / "response1.json").read_bytes(), original)
            self.assertFalse((responses / "precreate.json").exists())

    def test_artifact_audit_rejects_secret_and_forbidden_host_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "transcript.jsonl"
            transcript.write_text(json.dumps({"item": {"command": "cat /home/yangxiang/.codex/history.jsonl"}}) + " token=not-a-real-secret")
            result = launcher.scan_files([transcript], "not-a-real-secret")
            self.assertFalse(result["passed"])

    def test_artifact_audit_allows_public_api_provenance_paths_but_checks_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            response = Path(temp_dir) / "response.json"
            response.write_text(
                json.dumps(
                    {
                        "body": {
                            "workspace": "/workspace/default",
                            "source": "/home/yangxiang/projects/ontology-platform/backend/scripts/dev_owl_reasoner.py",
                        }
                    }
                )
            )
            result = launcher.scan_files([response], "not-a-real-secret", scan_host_paths=False)
            self.assertTrue(result["passed"])

    def test_receipt_audit_binds_agent_receipt_runtime_and_transcript_to_host_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_receipt_run(Path(temp_dir))
            result = launcher.receipt_audit(run_dir, "m3-receipt-test")
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(result["forwarded_count"], 1)
            self.assertEqual(result["receipt_count"], 1)

    def test_receipt_audit_accepts_exact_created_and_error_host_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_receipt_run(Path(temp_dir), status=201)
            result = launcher.receipt_audit(run_dir, "m3-receipt-test")
            self.assertTrue(result["passed"], result["errors"])
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_receipt_run(Path(temp_dir), status=422)
            result = launcher.receipt_audit(run_dir, "m3-receipt-test")
            self.assertTrue(result["passed"], result["errors"])

    def test_receipt_audit_rejects_missing_duplicate_or_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_receipt_run(Path(temp_dir))
            receipt_path = run_dir / "work" / launcher.RECEIPT_FILENAME
            receipt_path.write_bytes(receipt_path.read_bytes() * 2)
            duplicate = launcher.receipt_audit(run_dir, "m3-receipt-test")
            self.assertFalse(duplicate["passed"])

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_receipt_run(Path(temp_dir))
            (run_dir / "work" / launcher.RECEIPT_FILENAME).unlink()
            missing = launcher.receipt_audit(run_dir, "m3-receipt-test")
            self.assertFalse(missing["passed"])

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_receipt_run(Path(temp_dir))
            record = run_dir / "work" / "runtime-record.json"
            value = json.loads(record.read_text())
            value["run_tag"] = "m3-hand-edited"
            record.write_text(json.dumps(value))
            drift = launcher.receipt_audit(run_dir, "m3-receipt-test")
            self.assertFalse(drift["passed"])

    def test_build_session_audit_binds_agent_checkpoint_completion_and_final_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_completed_session_run(Path(temp_dir))
            result = launcher.build_session_audit(run_dir, "m3-session-test")
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(result["checkpoint_id"], "checkpoint-001")

    def test_build_session_audit_rejects_missing_checkpoint_active_or_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_completed_session_run(Path(temp_dir))
            lines = (run_dir / "gateway.jsonl").read_text().splitlines()
            (run_dir / "gateway.jsonl").write_text("\n".join(lines[1:]) + "\n")
            self.assertFalse(launcher.build_session_audit(run_dir, "m3-session-test")["passed"])

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_completed_session_run(Path(temp_dir), final_status="active")
            self.assertFalse(launcher.build_session_audit(run_dir, "m3-session-test")["passed"])

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_completed_session_run(Path(temp_dir))
            record = run_dir / "work" / "runtime-record.json"
            value = json.loads(record.read_text())
            value["build_session_completion"]["run_tag"] = "m3-hand-edited"
            record.write_text(json.dumps(value))
            self.assertFalse(launcher.build_session_audit(run_dir, "m3-session-test")["passed"])

        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = self.write_completed_session_run(Path(temp_dir))
            record = run_dir / "work" / "runtime-record.json"
            value = json.loads(record.read_text())
            value["session_id"] = "different-session"
            record.write_text(json.dumps(value))
            self.assertFalse(launcher.build_session_audit(run_dir, "m3-session-test")["passed"])

    def test_spool_and_run_tag_policy(self) -> None:
        self.assertTrue(gateway.is_allowed_path("/openapi.json"))
        self.assertTrue(gateway.is_allowed_path("/api/projects?limit=1"))
        self.assertFalse(gateway.is_allowed_path("/api/../private"))
        self.assertFalse(gateway.is_allowed_path("/docs"))
        self.assertIsNotNone(launcher.RUN_TAG_RE.fullmatch("m3-20260726-abc123"))
        self.assertIsNone(launcher.RUN_TAG_RE.fullmatch("../m3"))


if __name__ == "__main__":
    unittest.main()
