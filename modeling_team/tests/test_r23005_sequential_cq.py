"""Start68 formal Coordinator sequential-CQ contract regressions."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.acceptance import (
    AcceptanceContractError,
    CoordinatorPhaseController,
    RunnerAcceptanceCarrier,
    model_state_digest,
    ticket_digest,
)
from modeling_team.contracts import load_formal_team_configuration, repository_root
from modeling_team.runner import TeamRunner
from modeling_team.tests.test_r23005_contracts import _ticket


def _two_tickets() -> tuple[dict, dict, dict]:
    first = _ticket("1")
    first["competency_questions"] = [
        {"id": "cq-001", "question": "Which output is consumed first?"},
        {"id": "cq-002", "question": "Which output is consumed second?"},
    ]
    first["question_id"] = "cq-001"
    first["question"] = first["competency_questions"][0]["question"]
    first["ticket_digest"] = ticket_digest(first)
    for receipt in first["modeling_receipts"]:
        receipt["evidence_ref"]["ticket_digest"] = first["ticket_digest"]

    second = copy.deepcopy(first)
    second["ticket_id"] = "ticket-r23005-2"
    second["acceptance_round_id"] = "round-r23005-2"
    second["question_id"] = "cq-002"
    second["question"] = second["competency_questions"][1]["question"]
    second["ticket_digest"] = ticket_digest(second)
    for receipt in second["modeling_receipts"]:
        receipt["evidence_ref"]["ticket_digest"] = second["ticket_digest"]

    policy = {
        "quality_standard_ref": first["quality_standard_ref"],
        "quality_standard_digest": first["quality_standard_digest"],
        "quality_standard_artifact": first["quality_standard_artifact"],
        "unknown_policy": first["unknown_policy"],
        "competency_questions": first["competency_questions"],
        "approved_source_paths_by_question": {
            "cq-001": ["source.md"],
            "cq-002": ["source.md"],
        },
    }
    return first, second, policy


def _runner_for_carrier(
    carrier: RunnerAcceptanceCarrier,
    phase: CoordinatorPhaseController,
) -> TeamRunner:
    configuration = SimpleNamespace(
        task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
        profile=SimpleNamespace(profile_id="r2-3-005-modeling-team"),
    )
    runner = TeamRunner(repository_root=repository_root(), adapter=SimpleNamespace())
    runner.run = SimpleNamespace(configuration=configuration)
    runner.acceptance = carrier
    runner.coordinator_phase = phase
    return runner


def _prepared_runner(
    root: Path,
    *,
    state_reader=None,
) -> tuple[TeamRunner, RunnerAcceptanceCarrier, CoordinatorPhaseController, dict, dict]:
    first, second, policy = _two_tickets()
    carrier = RunnerAcceptanceCarrier(
        root / "carrier",
        task_id=first["task_id"],
        acceptance_id="acceptance",
        ticket_policy=policy,
    )
    carrier._ticket_drafts[first["ticket_digest"]] = copy.deepcopy(first)
    carrier._ticket_drafts[second["ticket_digest"]] = copy.deepcopy(second)
    carrier.bind_model_state(first["model_state"], state_reader=state_reader)
    carrier.publish_ticket(
        first,
        coordinator_id="coordinator",
        owner_revision=first["quality_standard_ref"],
    )
    carrier.publish_ticket(
        second,
        coordinator_id="coordinator",
        owner_revision=second["quality_standard_ref"],
    )
    phase = CoordinatorPhaseController()
    phase.start()
    phase.assign_slice(sender_id="coordinator", objective="formal slice")
    generation = phase.generation
    phase.readiness(
        sender_id="modeling",
        message_kind="ready_for_acceptance",
        generation=generation,
    )
    phase.readiness(
        sender_id="protocol",
        message_kind="silent_for_acceptance",
        generation=generation,
    )
    return _runner_for_carrier(carrier, phase), carrier, phase, first, second


def _mark_pass(carrier: RunnerAcceptanceCarrier, ticket: dict) -> None:
    round_data = carrier._rounds[ticket["acceptance_round_id"]]
    verdict_digest_value = "c" * 64
    round_data.update(
        {
            "status": "cleaned",
            "verdict": {
                "verdict": "PASS",
                "acceptance_round_id": ticket["acceptance_round_id"],
                "ticket_digest": ticket["ticket_digest"],
                "model_state_digest": ticket["model_state_digest"],
                "verdict_digest": verdict_digest_value,
            },
            "state_digest": ticket["model_state_digest"],
            "verdict_usable": True,
            "cleanup": {"source", "platform"},
        }
    )
    carrier._verdicts[ticket["acceptance_round_id"]] = SimpleNamespace(
        verdict_digest=verdict_digest_value
    )


class R23005SequentialCQTests(unittest.TestCase):
    def test_runner_accepts_cq1_then_exact_published_cq2_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, carrier, phase, first, second = _prepared_runner(Path(directory))
            generation = phase.generation
            runner._coordination_phase_callback(
                "coordinator", "acceptance", "acceptance_start", first["acceptance_round_id"], generation
            )
            self.assertEqual(phase.phase.value, "ACCEPTANCE_ROUND_ACTIVE")
            phase.set_reports_ready()
            phase.route_verdict(
                sender_id="acceptance", verdict={"verdict": "PASS"}, generation=generation
            )
            self.assertEqual(phase.phase.value, "WAITING_ACCEPTANCE")
            _mark_pass(carrier, first)

            runner._coordination_phase_callback(
                "coordinator", "acceptance", "acceptance_start", second["acceptance_round_id"], generation
            )
            self.assertEqual(phase.phase.value, "ACCEPTANCE_ROUND_ACTIVE")
            self.assertEqual(
                [item["acceptance_round_id"] for item in phase.events if item["event"] == "acceptance-start"],
                [first["acceptance_round_id"], second["acceptance_round_id"]],
            )
            self.assertEqual(carrier._tickets[second["acceptance_round_id"]]["ticket_digest"], second["ticket_digest"])

    def test_invalid_selection_is_rejected_before_phase_or_runtime_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, carrier, phase, first, second = _prepared_runner(Path(directory))
            generation = phase.generation

            for selected in ("unpublished-round", second["acceptance_round_id"]):
                before_events = len(phase.events)
                before_rounds = copy.deepcopy(carrier._rounds)
                with self.assertRaises(AcceptanceContractError):
                    runner._coordination_phase_callback(
                        "coordinator", "acceptance", "acceptance_start", selected, generation
                    )
                self.assertEqual(phase.phase.value, "WAITING_ACCEPTANCE")
                self.assertEqual(len(phase.events), before_events)
                self.assertEqual(carrier._rounds, before_rounds)
                self.assertEqual(runner._coordination_runtime_queue, [])

            before_events = len(phase.events)
            before_rounds = copy.deepcopy(carrier._rounds)
            with self.assertRaises(AcceptanceContractError):
                runner._coordination_phase_callback(
                    "coordinator", "acceptance", "acceptance_start", first["acceptance_round_id"], generation + 1
                )
            self.assertEqual(phase.phase.value, "WAITING_ACCEPTANCE")
            self.assertEqual(len(phase.events), before_events)
            self.assertEqual(carrier._rounds, before_rounds)

            runner._coordination_phase_callback(
                "coordinator", "acceptance", "acceptance_start", first["acceptance_round_id"], generation
            )
            phase.set_reports_ready()
            phase.route_verdict(
                sender_id="acceptance", verdict={"verdict": "PASS"}, generation=generation
            )
            _mark_pass(carrier, first)
            before_events = len(phase.events)
            before_rounds = copy.deepcopy(carrier._rounds)
            with self.assertRaises(AcceptanceContractError):
                runner._coordination_phase_callback(
                    "coordinator", "acceptance", "acceptance_start", first["acceptance_round_id"], generation
                )
            self.assertEqual(phase.phase.value, "WAITING_ACCEPTANCE")
            self.assertEqual(len(phase.events), before_events)
            self.assertEqual(carrier._rounds, before_rounds)

    def test_cq2_revalidation_invalidates_stale_cq1_pass_without_enqueue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changed_state = {
                "project_id": "project-r23005",
                "ontology_id": "ontology-r23005",
                "model_revision": 2,
                "build_session_id": "session-r23005",

            }
            changed_state["state_digest"] = model_state_digest(changed_state)
            runner, carrier, phase, first, second = _prepared_runner(
                Path(directory), state_reader=lambda: changed_state
            )
            generation = phase.generation
            runner._coordination_phase_callback(
                "coordinator", "acceptance", "acceptance_start", first["acceptance_round_id"], generation
            )
            phase.set_reports_ready()
            phase.route_verdict(
                sender_id="acceptance", verdict={"verdict": "PASS"}, generation=generation
            )
            _mark_pass(carrier, first)
            before_events = len(phase.events)
            with self.assertRaises(AcceptanceContractError):
                runner._coordination_phase_callback(
                    "coordinator", "acceptance", "acceptance_start", second["acceptance_round_id"], generation
                )
            self.assertEqual(phase.phase.value, "WAITING_ACCEPTANCE")
            self.assertEqual(len(phase.events), before_events)
            self.assertEqual(runner._coordination_runtime_queue, [])
            self.assertFalse(carrier._rounds[first["acceptance_round_id"]]["verdict_usable"])
            self.assertTrue(carrier.state_invalidations)

    def test_cq2_requires_current_cq1_digest_and_full_child_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, carrier, phase, first, second = _prepared_runner(Path(directory))
            generation = phase.generation
            runner._coordination_phase_callback(
                "coordinator", "acceptance", "acceptance_start", first["acceptance_round_id"], generation
            )
            phase.set_reports_ready()
            phase.route_verdict(
                sender_id="acceptance", verdict={"verdict": "PASS"}, generation=generation
            )
            _mark_pass(carrier, first)

            before_events = len(phase.events)
            carrier._rounds[first["acceptance_round_id"]]["cleanup"] = set()
            with self.assertRaises(AcceptanceContractError):
                runner._coordination_phase_callback(
                    "coordinator", "acceptance", "acceptance_start", second["acceptance_round_id"], generation
                )
            self.assertEqual(len(phase.events), before_events)
            self.assertEqual(phase.phase.value, "WAITING_ACCEPTANCE")

            carrier._rounds[first["acceptance_round_id"]]["cleanup"] = {"source", "platform"}
            carrier._rounds[first["acceptance_round_id"]]["state_digest"] = "a" * 64
            before_root_evidence = set((carrier.root / "evidence").glob("state-revalidation-*.json"))
            with self.assertRaises(AcceptanceContractError):
                runner._coordination_phase_callback(
                    "coordinator", "acceptance", "acceptance_start", second["acceptance_round_id"], generation
                )
            self.assertEqual(
                set((carrier.root / "evidence").glob("state-revalidation-*.json")),
                before_root_evidence,
            )
            self.assertEqual(phase.phase.value, "WAITING_ACCEPTANCE")

    def test_final_cq2_pass_rejects_third_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner, carrier, phase, first, second = _prepared_runner(Path(directory))
            generation = phase.generation
            runner._coordination_phase_callback(
                "coordinator", "acceptance", "acceptance_start", first["acceptance_round_id"], generation
            )
            phase.set_reports_ready()
            phase.route_verdict(
                sender_id="acceptance", verdict={"verdict": "PASS"}, generation=generation
            )
            _mark_pass(carrier, first)
            runner._coordination_phase_callback(
                "coordinator", "acceptance", "acceptance_start", second["acceptance_round_id"], generation
            )
            phase.set_reports_ready()
            phase.route_verdict(
                sender_id="acceptance", verdict={"verdict": "PASS"}, generation=generation
            )
            _mark_pass(carrier, second)

            before_events = len(phase.events)
            before_rounds = copy.deepcopy(carrier._rounds)
            with self.assertRaises(AcceptanceContractError):
                runner._coordination_phase_callback(
                    "coordinator", "acceptance", "acceptance_start", "round-r23005-3", generation
                )
            self.assertEqual(phase.phase.value, "WAITING_ACCEPTANCE")
            self.assertEqual(len(phase.events), before_events)
            self.assertEqual(carrier._rounds, before_rounds)

    def test_formal_prompt_is_coordinator_only(self) -> None:
        root = repository_root()
        configuration = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration, protocol_context=None)
        coordinator = runner._task_text("coordinator")
        self.assertIn("Do not wait for a cq-002 verdict before starting", coordinator)
        self.assertIn("final cq-002 PASS starts no further", coordinator)
        for role in ("modeling", "acceptance"):
            self.assertNotIn("Formal R2.3-005 sequential acceptance is mandatory", runner._task_text(role))

    def test_formal_prompt_keeps_the_formal_only_acceptance_text(self) -> None:
        root = repository_root()
        configuration = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration, protocol_context=None)

        coordinator = runner._task_text("coordinator")
        for phrase in (
            "coordinator_ticket_draft",
            "acceptance_start",
            "Modeling, Protocol, and Acceptance have each reported completed or blocked",
        ):
            self.assertIn(phrase, coordinator)
        self.assertIn("ready_for_acceptance", runner._task_text("modeling"))


if __name__ == "__main__":
    unittest.main()
