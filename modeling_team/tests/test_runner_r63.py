from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import TeamConfigurationError
from modeling_team.runner import (
    _P2A_SCHEMA,
    _P2A_PASS_RELATIVE,
    _PROOF_MATRIX_RELATIVE,
    TeamRunner,
)


class _AnswerAdapter:
    def __init__(self, root: Path, *, fail: bool = False) -> None:
        self.root = root
        self.fail = fail
        self.sent: list[object] = []
        self.record_seen_before_send = False

    def send_message(self, _recipient: str, delivery: object) -> None:
        self.record_seen_before_send = (self.root / "evidence/outer-user.jsonl").is_file()
        self.sent.append(delivery)
        if self.fail:
            raise RuntimeError("send failed")


class RunnerRound63Tests(unittest.TestCase):
    def test_preflight_validates_matrix_p2a_hashes_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix_path = root / _PROOF_MATRIX_RELATIVE
            p2a_path = root / _P2A_PASS_RELATIVE
            matrix_path.parent.mkdir(parents=True)
            p2a_path.parent.mkdir(parents=True)
            source_matrix = Path(__file__).parents[1] / "references/r2-3-002-proof-v2-assertion-matrix.json"
            matrix = json.loads(source_matrix.read_text(encoding="utf-8"))
            matrix["source_run_id"] = "source-run"
            matrix["matrix_digest"] = TeamRunner._canonical_digest(
                {key: matrix[key] for key in ("schema_version", "source_run_id", "source_candidate_digest", "rows")}
            )
            p2a = {
                "schema_version": _P2A_SCHEMA,
                "matrix_path": _PROOF_MATRIX_RELATIVE,
                "matrix_digest": matrix["matrix_digest"],
                "source_run_id": "source-run",
                "p2a_run_id": "p2a-run",
                "verifier_complete": True,
                "evidence_hashes": ["c" * 64],
                "tested_at": "2026-08-01T10:00:00Z",
            }
            p2a_digest = TeamRunner._canonical_digest(p2a)
            matrix_path.write_text(json.dumps(matrix, separators=(",", ":")), encoding="utf-8")
            p2a_path.write_text(json.dumps(p2a, separators=(",", ":")), encoding="utf-8")
            run_root = root / "run"
            (run_root / "evidence").mkdir(parents=True)
            runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
            runner.run = SimpleNamespace(
                gate_binding={
                    "proof_matrix_path": _PROOF_MATRIX_RELATIVE,
                    "proof_matrix_digest": matrix["matrix_digest"],
                    "p2a_pass_path": _P2A_PASS_RELATIVE,
                    "p2a_pass_digest": p2a_digest,
                    "source_run_id": "source-run",
                },
                root=run_root,
            )
            runner._preflight_proof_v2_gate()
            self.assertTrue((run_root / "evidence/proof-v2-preflight.jsonl").is_file())
            p2a["verifier_complete"] = False
            p2a_path.write_text(json.dumps(p2a), encoding="utf-8")
            with self.assertRaisesRegex(TeamConfigurationError, "P2a pass binding"):
                runner._preflight_proof_v2_gate()

    def test_owner_answer_record_is_fsynced_before_send_and_failed_id_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_root = root / "run"
            (run_root / "evidence").mkdir(parents=True)
            adapter = _AnswerAdapter(run_root)
            runner = TeamRunner(repository_root=root, adapter=adapter)
            runner.run = SimpleNamespace(
                run_id="run-1",
                root=run_root,
                scope={"project_id": "project-1"},
                configuration=SimpleNamespace(
                    task=SimpleNamespace(schema_version=2),
                    profile=SimpleNamespace(parameters={"owner_answer_authorization_id": "auth-1"}),
                ),
            )
            runner._outer_questions["question-1"] = {
                "question_delivery_id": "question-1",
                "project_id": "project-1",
                "run_id": "run-1",
                "text": "Which release?",
            }
            runner._release_owner_answer("coordinator", "Release 2", "question-1")
            self.assertTrue(adapter.record_seen_before_send)
            record = json.loads((run_root / "evidence/outer-user.jsonl").read_text().strip())
            self.assertEqual(
                set(record),
                {
                    "owner_answer_id",
                    "project_id",
                    "run_id",
                    "authorization_id",
                    "release_id",
                    "question_delivery_id",
                    "delivery_id",
                    "text",
                    "released_at",
                },
            )
            self.assertTrue(record["owner_answer_id"].startswith("owner-answer-"))
            self.assertEqual(record["release_id"], record["delivery_id"])
            sent_count = len(adapter.sent)
            runner._release_owner_answer("coordinator", "Release 2", "question-1")
            self.assertEqual(len(adapter.sent), sent_count)

            failing_root = root / "failing-run"
            (failing_root / "evidence").mkdir(parents=True)
            failing_adapter = _AnswerAdapter(failing_root, fail=True)
            failing = TeamRunner(repository_root=root, adapter=failing_adapter)
            failing.run = SimpleNamespace(
                run_id="run-2",
                root=failing_root,
                scope={"project_id": "project-1"},
                configuration=SimpleNamespace(
                    task=SimpleNamespace(schema_version=2),
                    profile=SimpleNamespace(parameters={"owner_answer_authorization_id": "auth-1"}),
                ),
            )
            failing._outer_questions["question-2"] = {
                "question_delivery_id": "question-2",
                "project_id": "project-1",
                "run_id": "run-2",
                "text": "Which release?",
            }
            with self.assertRaises(RuntimeError):
                failing._release_owner_answer("coordinator", "Release 3", "question-2")
            self.assertTrue((failing_root / "evidence/outer-user.jsonl").is_file())
            with self.assertRaisesRegex(TeamConfigurationError, "previously failed"):
                failing._release_owner_answer("coordinator", "Release 3", "question-2")

    def test_prepare_binding_resolves_tester_p2a_digest_from_static_t_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix_path = root / _PROOF_MATRIX_RELATIVE
            p2a_path = root / _P2A_PASS_RELATIVE
            matrix_path.parent.mkdir(parents=True)
            p2a_path.parent.mkdir(parents=True)
            source_matrix = Path(__file__).parents[1] / "references/r2-3-002-proof-v2-assertion-matrix.json"
            matrix = json.loads(source_matrix.read_text(encoding="utf-8"))
            matrix["source_run_id"] = "source-run"
            matrix["matrix_digest"] = TeamRunner._canonical_digest(
                {key: matrix[key] for key in ("schema_version", "source_run_id", "source_candidate_digest", "rows")}
            )
            p2a = {
                "schema_version": _P2A_SCHEMA,
                "matrix_path": _PROOF_MATRIX_RELATIVE,
                "matrix_digest": matrix["matrix_digest"],
                "source_run_id": "source-run",
                "p2a_run_id": "p2a-run",
                "verifier_complete": True,
                "evidence_hashes": ["c" * 64],
                "tested_at": "2026-08-01T10:00:00Z",
            }
            matrix_path.write_text(json.dumps(matrix, separators=(",", ":")), encoding="utf-8")
            p2a_path.write_text(json.dumps(p2a, separators=(",", ":")), encoding="utf-8")
            runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
            expected = {
                "proof_matrix_path": _PROOF_MATRIX_RELATIVE,
                "proof_matrix_digest": matrix["matrix_digest"],
                "p2a_pass_path": _P2A_PASS_RELATIVE,
                "source_run_id": "source-run",
                "source_candidate_digest": matrix["source_candidate_digest"],
            }
            resolved = runner._resolve_expected_matrix_binding(expected)
            self.assertEqual(resolved["proof_matrix_digest"], matrix["matrix_digest"])
            self.assertEqual(resolved["p2a_pass_path"], _P2A_PASS_RELATIVE)
            self.assertEqual(resolved["p2a_pass_digest"], TeamRunner._canonical_digest(p2a))


if __name__ == "__main__":
    unittest.main()
