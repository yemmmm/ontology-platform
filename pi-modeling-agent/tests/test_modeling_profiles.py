from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PATH = Path(__file__).parents[1] / "lib" / "modeling_profiles.py"
SPEC = importlib.util.spec_from_file_location("modeling_profiles", PATH)
assert SPEC and SPEC.loader
profiles = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = profiles
SPEC.loader.exec_module(profiles)


class ModelingProfilesTest(unittest.TestCase):
    def test_default_local_and_strict_eval_formal_are_orthogonal(self) -> None:
        local = profiles.select_profile({})
        strict = profiles.select_profile({"evaluation_profile": "strict_eval"})
        self.assertEqual((local.execution_profile, local.evaluation_profile), ("local", None))
        self.assertEqual(
            (strict.execution_profile, strict.evaluation_profile), ("formal", "strict_eval")
        )
        self.assertEqual(
            profiles.select_profile({"evaluation_profile": "fast_local"}).execution_profile,
            "local",
        )

    def test_profile_cannot_switch_in_place_and_handoffs_are_reference_only(self) -> None:
        frozen = profiles.freeze_profile({}, profiles.select_profile({}))
        with self.assertRaisesRegex(profiles.ProfileContractError, "fixed"):
            profiles.freeze_profile(frozen, profiles.select_profile({"formal_delivery": True}))
        handoff = profiles.worker_handoff(
            run_path="workspaces/modeling-runs/run-1",
            work_unit_id="unit-1",
            schema_path="schema.json",
            output_path="units/unit-1/result.json",
        )
        self.assertEqual(set(handoff), {"run_path", "work_unit_id", "schema_path", "output_path"})
        self.assertNotIn("candidate", profiles.main_handoff(run_path="run", phase="review"))


if __name__ == "__main__":
    unittest.main()
