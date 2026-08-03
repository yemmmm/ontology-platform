from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import _load_package, digest_file, repository_root
from modeling_team.runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError, _Agent


class ProofV2RuntimeAssetTests(unittest.TestCase):
    def _run(self, root: Path, base: Path) -> tuple[CodexRuntimeAdapter, _Agent]:
        adapter = CodexRuntimeAdapter(repository_root=root)
        agent = _Agent(
            "protocol",
            _load_package(root, "protocol"),
            base / "home",
            base / "work",
            base / "skills",
            schema_version=2,
        )
        for path in (agent.home, agent.work, agent.skills):
            path.mkdir(parents=True)
        run = SimpleNamespace(
            root=base,
            run_id="r23002-proof-v2-asset-test",
            configuration=SimpleNamespace(task=SimpleNamespace(schema_version=2)),
        )
        adapter._run_root = base
        adapter._run_id = run.run_id
        adapter.agents = {agent.agent_id: agent}
        adapter._stage_protocol_retrieval_mcp(run, agent)
        return adapter, agent

    def test_staged_dir_subprocess_initialize_and_tools_list_imports_proof_v2(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory)
            for name in ("protocol_retrieval_mcp.py", "protocol_mechanics.py", "proof_v2.py"):
                source = root / "modeling_team" / name
                target = staged / name
                shutil.copyfile(source, target)
                os.chmod(target, 0o600 if name == "proof_v2.py" else 0o444)
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(staged)
            process = subprocess.Popen(
                [sys.executable, str(staged / "protocol_retrieval_mcp.py")],
                cwd=staged,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                assert process.stdin is not None and process.stdout is not None
                for request in (
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                ):
                    process.stdin.write(json.dumps(request) + "\n")
                    process.stdin.flush()
                    response = json.loads(process.stdout.readline())
                    self.assertEqual(response.get("jsonrpc"), "2.0")
                    self.assertEqual(response.get("id"), request["id"])
                    self.assertNotIn("error", response)
                    if request["method"] == "initialize":
                        self.assertEqual(response["result"]["serverInfo"]["name"], "protocol_mechanics")
                    else:
                        tools = response["result"]["tools"]
                        self.assertEqual(
                            {item["name"] for item in tools},
                            {
                                "build_candidate_receipt",
                                "verify_scoped_retrieval_fallback",
                                "write_candidate_item_evidence_map",
                            },
                        )
                        tool = next(item for item in tools if item["name"] == "verify_scoped_retrieval_fallback")
                        self.assertEqual(tool["name"], "verify_scoped_retrieval_fallback")
                        self.assertIn("pagination", tool["inputSchema"]["properties"])
                process.stdin.close()
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

    def test_missing_or_tampered_proof_v2_asset_fails_closed(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter, agent = self._run(root, base)
            assert agent.proof_v2_path is not None
            agent.proof_v2_path.unlink()
            with self.assertRaisesRegex(CodexRuntimeError, "asset is unavailable|asset metadata is invalid"):
                adapter._open_protocol_retrieval_assets(agent)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter, agent = self._run(root, base)
            assert agent.proof_v2_path is not None
            agent.proof_v2_path.write_text("tampered", encoding="utf-8")
            os.chmod(agent.proof_v2_path, 0o600)
            with self.assertRaisesRegex(CodexRuntimeError, "asset digest is invalid"):
                adapter._open_protocol_retrieval_assets(agent)

    def test_proof_v2_asset_contract_hash_and_modes_are_bound(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter, agent = self._run(root, base)
            assert agent.proof_v2_path is not None
            self.assertEqual(digest_file(root / "modeling_team/proof_v2.py"), digest_file(agent.proof_v2_path))
            self.assertEqual(stat.S_IMODE(agent.proof_v2_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(agent.proof_v2_path.parent.stat().st_mode), 0o700)
            self.assertEqual(agent.proof_v2_path.stat().st_uid, os.getuid())
            adapter.stop()


if __name__ == "__main__":
    unittest.main()
