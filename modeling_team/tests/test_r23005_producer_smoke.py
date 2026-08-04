from __future__ import annotations

import hashlib
import json
import os
import unittest

from modeling_team.r23005_producer_smoke import _canonical_digest, run_no_semantic_start_smoke


class R23005ProducerSmokeTests(unittest.TestCase):
    def test_canonical_digest_recomputes_retained_tool_and_scope_preimages(self) -> None:
        protocol_tools = ["build_candidate_receipt", "verify_scoped_retrieval_fallback"]
        scope = {
            "project_id": "project-smoke",
            "ontology_id": "ontology-smoke",
            "scope_mode": "create",
        }
        for value in (protocol_tools, scope):
            canonical = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            self.assertEqual(_canonical_digest(value), hashlib.sha256(canonical).hexdigest())

    @unittest.skipUnless(
        os.environ.get("R23005_RUN_REAL_SMOKE") == "1",
        "real Codex Runtime smoke requires explicit opt-in",
    )
    def test_neutral_handoff_projects_generic_runtime_without_semantic_start(self) -> None:
        evidence = run_no_semantic_start_smoke()
        self.assertFalse(evidence["semantic_start"])
        self.assertEqual(evidence["platform_calls"], 0)
        self.assertEqual(evidence["ledger_mutations"], 0)
        self.assertFalse(evidence["acceptance_started"])
        self.assertEqual(
            evidence["protocol_tools"],
            ["build_candidate_receipt", "verify_scoped_retrieval_fallback"],
        )
        self.assertEqual(evidence["receipt"]["status"], "accepted")
        self.assertEqual(evidence["translated_batch"]["mode"], "dry_run")
        self.assertEqual(evidence["scope_rejections"], {"prior": "rejected", "caller": "rejected"})
        self.assertEqual(evidence["proof_rejection"]["error_code"], -32602)
        self.assertEqual(
            evidence["protocol_tools_digest"], _canonical_digest(evidence["protocol_tools"])
        )
        self.assertEqual(evidence["scope_digest"], _canonical_digest(evidence["scope"]))
        self.assertNotEqual(evidence["prompt_digest"], evidence["task_projection_digest"])
        guard = evidence["platform_guard"]
        self.assertEqual(guard["identity"], "r23005-producer-platform-guard/v1")
        self.assertEqual(guard["attempted_call_count"], 0)
        self.assertEqual(guard["accepted_call_count"], 0)
        self.assertEqual(guard["attempted_calls"], [])
        self.assertFalse(guard["real_platform_server_reachable"])
        self.assertFalse(guard["real_platform_key_configured"])
        self.assertEqual(
            evidence["platform_resource_snapshots"]["before"],
            evidence["platform_resource_snapshots"]["after"],
        )
        self.assertEqual(evidence["process_snapshots"]["after"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
