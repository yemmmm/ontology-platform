from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import _load_package, repository_root
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _Agent


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
            gate_binding={"proof_matrix_path": "matrix", "proof_matrix_digest": "0" * 64},
            configuration=SimpleNamespace(task=SimpleNamespace(schema_version=2)),
        )
        adapter._run_root = base
        adapter._run_id = run.run_id
        adapter.agents = {agent.agent_id: agent}
        adapter._stage_protocol_retrieval_mcp(run, agent)
        return adapter, agent

    def test_active_staged_dir_exposes_only_neutral_protocol_tools(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory)
            for name in ("protocol_retrieval_mcp.py", "protocol_mechanics.py"):
                source = root / "modeling_team" / name
                target = staged / name
                shutil.copyfile(source, target)
                os.chmod(target, 0o444)
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
                                "build_unified_resource_binding_receipt",
                                "translate_candidate_to_batches",
                            },
                        )
                        self.assertNotIn(
                            "verify_scoped_retrieval_fallback",
                            {item["name"] for item in tools},
                        )
                process.stdin.close()
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

    def test_proof_v2_asset_is_not_staged_even_when_historical_gate_is_present(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter, agent = self._run(root, base)
            self.assertIsNone(agent.proof_v2_path)
            descriptors = adapter._open_protocol_retrieval_assets(agent)
            self.assertEqual(len(descriptors), 2)
            adapter._close_retrieval_asset_fds(agent)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter, agent = self._run(root, base)
            self.assertIsNone(agent.proof_v2_path)
            descriptors = adapter._open_protocol_retrieval_assets(agent)
            self.assertEqual(len(descriptors), 2)
            adapter._close_retrieval_asset_fds(agent)

    def test_active_runtime_does_not_bind_proof_v2_asset_contract(self) -> None:
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter, agent = self._run(root, base)
            self.assertIsNone(agent.proof_v2_path)
            adapter.stop()


if __name__ == "__main__":
    unittest.main()
