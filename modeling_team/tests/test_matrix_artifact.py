from __future__ import annotations

import json
import unittest
from pathlib import Path

from modeling_team.matrix_artifact import (
    MATRIX_RELATIVE,
    build_matrix,
    canonical_digest,
    load_matrix,
    verify_matrix,
)
from modeling_team.p2a_fixture import run_p2a_fixture


class MatrixArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).parents[2]

    def test_frozen_matrix_has_48_rows_and_matches_deterministic_inputs(self) -> None:
        matrix = load_matrix(self.root)
        generated = build_matrix(self.root)
        self.assertEqual(matrix, generated)
        self.assertEqual(len(matrix["rows"]), 48)
        self.assertEqual(
            matrix["matrix_digest"],
            "db6383a114f94a2c47bf28be52ca1eb88dce5e553a037c5fb407912d0882508b",
        )
        self.assertEqual(
            matrix["source_candidate_digest"],
            "7bfb8f5b10338b9a8ba8dc0a33fcdf69d64060d0c4f184c855373733a366f471",
        )

    def test_matrix_verifier_rejects_source_candidate_or_digest_drift(self) -> None:
        matrix = load_matrix(self.root)
        broken = json.loads(json.dumps(matrix))
        broken["source_candidate_digest"] = "0" * 64
        broken["matrix_digest"] = canonical_digest(
            {key: broken[key] for key in ("schema_version", "source_run_id", "source_candidate_digest", "rows")}
        )
        with self.assertRaisesRegex(ValueError, "does not match deterministic retained inputs"):
            verify_matrix(broken, root=self.root)

    def test_p2a_representative_proof_has_no_start_or_pass_side_effect(self) -> None:
        result = run_p2a_fixture(self.root)
        self.assertTrue(result["verifier"]["complete"])
        self.assertEqual(
            set(result["representative_binding_categories"]),
            {"resource_output", "relation_delta", "literal_delta", "vocabulary"},
        )
        self.assertEqual(set(result["representative_target_kinds"]), {"resource", "statement"})
        self.assertFalse(result["semantic_start_written"])
        self.assertFalse(result["p2a_pass_written"])
        self.assertFalse((self.root / "workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json").exists())
        self.assertTrue((self.root / MATRIX_RELATIVE).is_file())


if __name__ == "__main__":
    unittest.main()
