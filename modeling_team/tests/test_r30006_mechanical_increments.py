"""R3.0-006 M1-M3 mechanical-increment tests (test plan T0-1 .. T0-5c).

M1: multi_slice_workflow runs skip the StartLedger budget gate; every other
v2 task keeps its byte-identical ledger binding.
M2: the Runner and the multi-slice Profile contract are role-agnostic around
the three message-routing core roles.
M3: the additive ``topology_decision.ontology_plan`` extension, its gate
closure validation, the PlatformScope ontology-plan application and gate-open
delivery, and the multi-Ontology terminal/retained-handoff aggregate.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace

from modeling_team.contracts import (
    TeamConfigurationError,
    load_multi_slice_team_configuration,
    repository_root,
)
from modeling_team.platform_scope import PlatformScope
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.base import (
    AgentRuntimeIdentity,
    RuntimeAdapter,
    RuntimeDelivery,
)
from modeling_team.scenario_map import validate_topology_decision

REPO_ROOT = repository_root()
MULTI_SLICE_PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml"
MULTI_SLICE_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-002-multi-slice-smoke.yaml"
FORMAL_PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "base-three-agent.yaml"
ORDINARY_TASK = REPO_ROOT / "modeling_team" / "tasks" / "new-scope-business-slice.yaml"
FIXTURES = json.loads(
    (
        REPO_ROOT
        / "modeling_team"
        / "tests"
        / "fixtures"
        / "r30002-scenario-map-fixtures.json"
    ).read_text(encoding="utf-8")
)


class _StartAdapter(RuntimeAdapter):
    """Minimal deterministic adapter for start()-path tests."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, RuntimeDelivery]] = []
        self.started: list[str] = []

    def start_roster(self, run, agents):
        return [AgentRuntimeIdentity(agent.agent_id, "private") for agent in agents]

    def probe_role_visibility(self, run):
        return {agent.agent_id: {"probe": "passed"} for agent in run.configuration.profile.agents}

    def start_task(self, agent_id, task_text, skill_paths, roster):
        self.started.append(agent_id)

    def send_message(self, agent_id, delivery):
        self.messages.append((agent_id, delivery))

    def receive_messages(self):
        return []

    def get_agent_states(self):
        return []

    def wait_settled(self, agent_ids, timeout):
        return True

    def pause(self):
        return None

    def resume(self):
        return None

    def stop(self):
        return None

    def cleanup_identifiers(self):
        return {}


def _prepare(tmp_path, tag, *, profile, task, ledger_root):
    run_id = f"r30006-{tag}-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]}"
    runner = TeamRunner(
        repository_root=REPO_ROOT,
        adapter=_StartAdapter(),
        ledger_root=ledger_root,
        freeze_started_at=datetime.now(UTC).isoformat(),
    )
    runner.prepare(
        run_id=run_id,
        profile_path=profile,
        task_path=task,
        scope={"mode": "create"},
    )
    run_root = REPO_ROOT / "workspaces" / "modeling-runs" / run_id
    return runner, run_root


def _write_artifact(run_root: Path, filename: str, payload) -> None:
    directory = run_root / "scenario-map"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _gate_events(run_root: Path) -> list[dict]:
    path = run_root / "evidence" / "multi-slice-gate.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _slice_ids() -> set[str]:
    return {
        item["slice_id"] for item in FIXTURES["scenario_map"]["valid"]["slices"]
    }


class _FakePlanScope:
    def __init__(self, ontology_ids, *, fail=False):
        self.ontology_ids = list(ontology_ids)
        self.fail = fail
        self.applied = []

    def apply_ontology_plan(self, plan):
        if self.fail:
            raise RuntimeError("platform ontology creation failed")
        self.applied.append(plan)
        return list(self.ontology_ids)

    def read_protocol_context(self):
        context = {
            "project_id": "project-1",
            "ontology_id": self.ontology_ids[0],
            "workspace_version": "version-1",
        }
        if len(self.ontology_ids) > 1:
            context["ontology_ids"] = ",".join(self.ontology_ids)
        return context

    def cleanup(self):
        return {}


# --- T0-1 / T0-2 (M1): ledger budget gate scoping ---


class LedgerBudgetGateTests(unittest.TestCase):
    def test_multi_slice_run_skips_the_start_ledger_entirely(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            ledger_root = Path(directory) / "ledger"
            runner, run_root = _prepare(
                Path(directory),
                "ledger-exempt",
                profile=MULTI_SLICE_PROFILE,
                task=MULTI_SLICE_TASK,
                ledger_root=ledger_root,
            )
            try:
                self.assertTrue(runner._multi_slice_workflow)
                self.assertIsNone(runner._ledger)
                # No reservation file is created anywhere under the ledger root.
                self.assertFalse(ledger_root.exists())
                self.assertFalse(list((Path(directory)).glob("**/.r2-3-002-start-ledger.jsonl")))
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)

    def test_ordinary_v2_task_still_reserves_through_the_ledger(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            ledger_root = Path(directory) / "ledger"
            runner, run_root = _prepare(
                Path(directory),
                "ledger-bound",
                profile=FORMAL_PROFILE,
                task=ORDINARY_TASK,
                ledger_root=ledger_root,
            )
            try:
                self.assertFalse(runner._multi_slice_workflow)
                self.assertIsNotNone(runner._ledger)
                ledger_files = list(ledger_root.glob("*.jsonl"))
                self.assertEqual(len(ledger_files), 1)
                records = [
                    json.loads(line)
                    for line in ledger_files[0].read_text(encoding="utf-8").splitlines()
                ]
                self.assertTrue(any(record.get("event") == "reservation" for record in records))
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)

    def test_ordinary_v2_task_keeps_the_reservation_gate(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            ledger_root = Path(directory) / "ledger"
            first, first_root = _prepare(
                Path(directory),
                "reserved-1",
                profile=FORMAL_PROFILE,
                task=ORDINARY_TASK,
                ledger_root=ledger_root,
            )
            try:
                self.assertIsNotNone(first._ledger)
                # While the first reservation is active, a second ordinary v2
                # prepare is still rejected by the ledger (cap semantics and
                # single-active-reservation rule unchanged).
                with self.assertRaisesRegex(
                    TeamConfigurationError, "start reservation is active"
                ):
                    _prepare(
                        Path(directory),
                        "reserved-2",
                        profile=FORMAL_PROFILE,
                        task=ORDINARY_TASK,
                        ledger_root=ledger_root,
                    )
            finally:
                if first.run is not None:
                    first.cleanup()
                if first_root.exists():
                    rmtree(first_root)


# --- T0-3 (M2): role-agnostic Runner start() ---


class RoleAgnosticStartTests(unittest.TestCase):
    def test_three_role_multi_slice_run_starts_with_role_derived_dependencies(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            runner, run_root = _prepare(
                Path(directory),
                "three-role-start",
                profile=MULTI_SLICE_PROFILE,
                task=MULTI_SLICE_TASK,
                ledger_root=Path(directory) / "ledger",
            )
            try:
                self.assertEqual(
                    sorted(agent.package.role for agent in runner.run.configuration.profile.agents),
                    ["coordinator", "modeling", "protocol"],
                )
                runner.start()
                self.assertIsNotNone(runner.transport)
                self.assertEqual(
                    runner.transport.terminal_dependencies,
                    {"protocol": {"modeling"}, "coordinator": {"modeling", "protocol"}},
                )
                self.assertEqual(sorted(runner.adapter.started), ["coordinator", "modeling", "protocol"])
                # M1: the visibility probe and semantic-start evidence belong to
                # every v2 run, including the ledger-less multi-slice run.
                self.assertTrue((run_root / "evidence" / "semantic-start.jsonl").exists())
                self.assertTrue((run_root / "evidence" / "runtime-visibility-probe.jsonl").exists())
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)

    def test_four_role_formal_roster_dependency_graph_is_unchanged(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            runner, run_root = _prepare(
                Path(directory),
                "four-role-start",
                profile=FORMAL_PROFILE,
                task=ORDINARY_TASK,
                ledger_root=Path(directory) / "ledger",
            )
            try:
                runner.start()
                self.assertEqual(
                    runner.transport.terminal_dependencies,
                    {
                        "protocol": {"modeling"},
                        "coordinator": {"modeling", "protocol", "acceptance"},
                    },
                )
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)

    def test_retained_completion_status_is_derived_from_the_actual_role_set(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(
                repository_root=REPO_ROOT, adapter=SimpleNamespace()
            )
            run_root = Path(directory) / "run"
            (run_root / "evidence").mkdir(parents=True)
            three = ["coordinator", "modeling", "protocol"]
            runner.run = SimpleNamespace(
                run_id="r30006-roles",
                root=run_root,
                terminal_results={role: {"status": "completed"} for role in three},
                configuration=SimpleNamespace(
                    profile=SimpleNamespace(
                        agents=[
                            SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
                            for role in three
                        ]
                    )
                ),
            )
            self.assertEqual(
                runner._completed_terminal_statuses(runner.run.terminal_results),
                {role: "completed" for role in three},
            )
            # A Profile role without a completed terminal result is rejected.
            runner.run.configuration.profile.agents.append(
                SimpleNamespace(agent_id="acceptance", package=SimpleNamespace(role="acceptance"))
            )
            with self.assertRaisesRegex(TeamConfigurationError, "every Profile Agent"):
                runner._completed_terminal_statuses(runner.run.terminal_results)


# --- T0-4 (M2): inclusive multi-slice Profile contract ---


def _write_profile(directory: Path, agents: list[dict], communication: list[dict]) -> Path:
    profile = directory / "profile.yaml"
    profile.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_id": "r3-0-006-extra-role-team",
                "runtime": "codex",
                "agents": agents,
                "communication": communication,
                "parameters": {},
            }
        ),
        encoding="utf-8",
    )
    return profile


class InclusiveProfileContractTests(unittest.TestCase):
    CORE_AGENTS = [
        {"agent_id": "coordinator", "package": "coordinator"},
        {"agent_id": "modeling", "package": "modeling"},
        {"agent_id": "protocol", "package": "protocol"},
    ]
    CORE_EDGES = [
        {"from": "coordinator", "to": ["modeling", "protocol"]},
        {"from": "modeling", "to": ["coordinator", "protocol"]},
        {"from": "protocol", "to": ["coordinator", "modeling"]},
    ]

    def test_extra_role_profile_loads_and_starts(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = _write_profile(
                root,
                self.CORE_AGENTS
                + [{"agent_id": "examiner", "package": "source-specialist"}],
                self.CORE_EDGES + [{"from": "coordinator", "to": ["examiner"]}],
            )
            configuration = load_multi_slice_team_configuration(profile, MULTI_SLICE_TASK)
            self.assertEqual(
                sorted(agent.package.role for agent in configuration.profile.agents),
                ["coordinator", "modeling", "protocol", "source-specialist"],
            )
            runner, run_root = _prepare(
                root,
                "extra-role-start",
                profile=profile,
                task=MULTI_SLICE_TASK,
                ledger_root=root / "ledger",
            )
            try:
                runner.start()
                self.assertEqual(
                    sorted(runner.adapter.started),
                    ["coordinator", "examiner", "modeling", "protocol"],
                )
                # Extra roles carry no terminal dependency.
                self.assertEqual(
                    runner.transport.terminal_dependencies,
                    {"protocol": {"modeling"}, "coordinator": {"modeling", "protocol"}},
                )
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)

    def test_missing_core_role_is_fail_closed(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = _write_profile(
                root,
                [
                    {"agent_id": "coordinator", "package": "coordinator"},
                    {"agent_id": "modeling", "package": "modeling"},
                    {"agent_id": "examiner", "package": "source-specialist"},
                ],
                self.CORE_EDGES,
            )
            with self.assertRaisesRegex(
                TeamConfigurationError, "exactly one Coordinator, Modeling, and Protocol"
            ):
                load_multi_slice_team_configuration(profile, MULTI_SLICE_TASK)

    def test_core_agent_id_role_identity_is_still_required(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = _write_profile(
                root,
                [
                    {"agent_id": "coordinator", "package": "coordinator"},
                    {"agent_id": "renamed-modeling", "package": "modeling"},
                    {"agent_id": "protocol", "package": "protocol"},
                ],
                self.CORE_EDGES,
            )
            with self.assertRaisesRegex(
                TeamConfigurationError, "core Agent IDs must match the role IDs"
            ):
                load_multi_slice_team_configuration(profile, MULTI_SLICE_TASK)

    def test_missing_core_edge_is_still_rejected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = _write_profile(
                root,
                self.CORE_AGENTS,
                [
                    {"from": "coordinator", "to": ["modeling", "protocol"]},
                    {"from": "modeling", "to": ["coordinator"]},
                    {"from": "protocol", "to": ["coordinator", "modeling"]},
                ],
            )
            with self.assertRaisesRegex(TeamConfigurationError, "communication graph drift"):
                load_multi_slice_team_configuration(profile, MULTI_SLICE_TASK)

    def test_formal_profile_cross_wire_is_still_rejected(self) -> None:
        with self.assertRaisesRegex(
            TeamConfigurationError, "multi-slice Profile is not registered"
        ):
            load_multi_slice_team_configuration(
                REPO_ROOT / "modeling_team" / "profiles" / "r2-3-005-modeling-team.yaml",
                MULTI_SLICE_TASK,
            )


# --- T0-5a (M3): ontology_plan contract extension ---


class OntologyPlanContractTests(unittest.TestCase):
    def _decision(self, **overrides):
        decision = json.loads(json.dumps(FIXTURES["topology_decision"]["multi_ontology_plan_valid"]))
        decision.update(overrides)
        return decision

    def test_valid_plan_has_no_issues_with_and_without_slice_closure(self) -> None:
        decision = FIXTURES["topology_decision"]["multi_ontology_plan_valid"]
        self.assertEqual(validate_topology_decision(decision) == (), True)
        self.assertEqual(validate_topology_decision(decision, slice_ids=_slice_ids()) == (), True)

    def test_plan_is_mandatory_for_non_single_selection(self) -> None:
        legacy = FIXTURES["topology_decision"]["valid"]
        issues = validate_topology_decision(legacy)
        self.assertEqual([issue.reason_code for issue in issues], ["topology_missing_ontology_plan"])

    def test_plan_is_forbidden_for_single_ontology_selection(self) -> None:
        single = json.loads(
            json.dumps(FIXTURES["topology_decision"]["single_ontology_selected_valid"])
        )
        single["ontology_plan"] = [
            {"name": "one", "slice_ids": ["S1"]},
            {"name": "two", "slice_ids": ["S2"]},
        ]
        codes = [issue.reason_code for issue in validate_topology_decision(single)]
        self.assertIn("topology_schema_mismatch", codes)

    def test_plan_structural_rules(self) -> None:
        cases = {
            "single_entry": [{"name": "only", "slice_ids": ["S1", "S2"]}],
            "duplicate_names": [
                {"name": "same", "slice_ids": ["S1", "S2"]},
                {"name": "same", "slice_ids": ["S3"]},
            ],
            "entry_fields_drift": [
                {"name": "one", "slice_ids": ["S1"], "extra": True},
                {"name": "two", "slice_ids": ["S2"]},
            ],
            "empty_name": [
                {"name": "", "slice_ids": ["S1"]},
                {"name": "two", "slice_ids": ["S2"]},
            ],
            "empty_slice_ids": [
                {"name": "one", "slice_ids": []},
                {"name": "two", "slice_ids": ["S2"]},
            ],
            "overlapping_slice": [
                {"name": "one", "slice_ids": ["S1", "S2"]},
                {"name": "two", "slice_ids": ["S2", "S3"]},
            ],
            "uncovered_slice": [
                {"name": "one", "slice_ids": ["S1"]},
                {"name": "two", "slice_ids": ["S2"]},
            ],
        }
        for variant, plan in cases.items():
            with self.subTest(variant=variant):
                codes = [
                    issue.reason_code
                    for issue in validate_topology_decision(
                        self._decision(ontology_plan=plan), slice_ids=_slice_ids()
                    )
                ]
                self.assertIn("topology_invalid_ontology_plan", codes)

    def test_dangling_slice_reference_is_only_reported_with_slice_ids(self) -> None:
        plan = [
            {"name": "one", "slice_ids": ["S1", "S9"]},
            {"name": "two", "slice_ids": ["S2", "S3", "S4", "S5"]},
        ]
        decision = self._decision(ontology_plan=plan)
        without = [
            issue.reason_code for issue in validate_topology_decision(decision)
        ]
        self.assertNotIn("topology_dangling_slice", without)
        with_map = [
            issue.reason_code
            for issue in validate_topology_decision(decision, slice_ids=_slice_ids())
        ]
        self.assertIn("topology_dangling_slice", with_map)


# --- T0-5b (M3): gate closure, plan application, ontology-id delivery ---


class GatePlanApplicationTests(unittest.TestCase):
    def _prepared_runner(self, directory: Path, tag: str):
        runner, run_root = _prepare(
            Path(directory),
            tag,
            profile=MULTI_SLICE_PROFILE,
            task=MULTI_SLICE_TASK,
            ledger_root=Path(directory) / "ledger",
        )
        _write_artifact(
            run_root, "scenario-map.json", FIXTURES["scenario_map"]["valid"]
        )
        _write_artifact(
            run_root,
            "topology-decision.json",
            FIXTURES["topology_decision"]["multi_ontology_plan_valid"],
        )
        return runner, run_root

    def test_gate_rejects_a_plan_with_dangling_slice_against_the_map(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            runner, run_root = self._prepared_runner(Path(directory), "dangling")
            try:
                decision = json.loads(
                    json.dumps(
                        FIXTURES["topology_decision"]["multi_ontology_plan_valid"]
                    )
                )
                decision["ontology_plan"][1]["slice_ids"].append("S9")
                _write_artifact(run_root, "topology-decision.json", decision)
                runner._check_multi_slice_topology_gate()
                state = json.loads(
                    (run_root / "candidate-gate" / "state.json").read_text(encoding="utf-8")
                )
                self.assertEqual(state["state"], "closed")
                self.assertEqual(state["reason_code"], "topology_dangling_slice")
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)

    def test_gate_open_applies_the_plan_and_delivers_all_ontology_ids(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            runner, run_root = self._prepared_runner(Path(directory), "plan-apply")
            scope = _FakePlanScope(["ontology-1", "ontology-2"])
            runner.scope = scope
            try:
                runner._check_multi_slice_topology_gate()
                state = json.loads(
                    (run_root / "candidate-gate" / "state.json").read_text(encoding="utf-8")
                )
                self.assertEqual(state["state"], "open")
                self.assertEqual(len(scope.applied), 1)
                events = [event["event"] for event in _gate_events(run_root)]
                self.assertIn("ontology-plan-applied", events)
                self.assertIn("ontology-plan-delivered", events)
                deliveries = [
                    (agent_id, delivery)
                    for agent_id, delivery in runner.adapter.messages
                    if delivery.kind == "multi-slice-ontology-plan"
                ]
                self.assertEqual(len(deliveries), 1)
                agent_id, delivery = deliveries[0]
                self.assertEqual(agent_id, "protocol")
                self.assertEqual(delivery.sender_id, "runner/multi-slice-gate")
                self.assertFalse(delivery.expects_reply)
                notice = json.loads(delivery.text)
                self.assertEqual(
                    notice["schema_version"], "r3-0-006-multi-slice-ontology-plan/v1"
                )
                self.assertEqual(notice["ontology_ids"], ["ontology-1", "ontology-2"])
                self.assertEqual(
                    runner.run.protocol_context["ontology_ids"], "ontology-1,ontology-2"
                )
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)

    def test_plan_apply_failure_is_evidence_only_and_never_kills_the_run(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            runner, run_root = self._prepared_runner(Path(directory), "plan-fail")
            runner.scope = _FakePlanScope(["ontology-1", "ontology-2"], fail=True)
            try:
                runner._check_multi_slice_topology_gate()
                state = json.loads(
                    (run_root / "candidate-gate" / "state.json").read_text(encoding="utf-8")
                )
                self.assertEqual(state["state"], "open")
                events = _gate_events(run_root)
                failure = next(
                    event for event in events if event["event"] == "ontology-plan-apply-failed"
                )
                self.assertEqual(failure["classification"], "runtime/infrastructure")
                self.assertFalse(
                    any(delivery.kind == "multi-slice-ontology-plan" for _, delivery in runner.adapter.messages)
                )
                self.assertIsNotNone(runner.run)
            finally:
                if runner.run is not None:
                    runner.cleanup()
                if run_root.exists():
                    rmtree(run_root)


class PlatformScopeOntologyPlanTests(unittest.TestCase):
    def _client(self):
        return _MultiOntologyClient()

    def test_apply_ontology_plan_accepts_a_slice_shared_by_two_ontologies(self) -> None:
        """T-G5-4: the relaxed plan still applies deterministically, unchanged.

        ``PlatformScope.apply_ontology_plan`` never indexed slice→Ontology and
        never rejected overlapping ``slice_ids``, so the shared-core-plus-domain
        shape needs no platform change: the same slice may be served by the
        core and the domain Ontology and the creation order stays plan order.
        """

        client = self._client()
        scope = PlatformScope(
            "http://example", "r30006-plan", lambda: ("admin", "admin-id"), lambda _: True, client
        )
        scope.prepare({"mode": "create"})
        shared_plan = [
            {"name": "shared-core", "slice_ids": ["S1", "S2"]},
            {"name": "fault-domain", "slice_ids": ["S2", "S3"]},
        ]
        self.assertEqual(
            scope.apply_ontology_plan(shared_plan), ["ontology-1", "ontology-2"]
        )
        self.assertEqual(client.created, [("fault-domain", "ontology-2")])
        # Idempotent reuse is unchanged for the overlapping plan.
        self.assertEqual(
            scope.apply_ontology_plan(shared_plan), ["ontology-1", "ontology-2"]
        )
        self.assertEqual(client.created, [("fault-domain", "ontology-2")])
        # Protocol still receives every planned Ontology identity.
        self.assertEqual(
            scope.read_protocol_context()["ontology_ids"],
            "ontology-1,ontology-2",
        )

    def test_apply_ontology_plan_creates_remaining_ontologies_idempotently(self) -> None:
        client = self._client()
        scope = PlatformScope(
            "http://example", "r30006-plan", lambda: ("admin", "admin-id"), lambda _: True, client
        )
        scope.prepare({"mode": "create"})
        plan = [
            {"name": "first", "slice_ids": ["S1", "S2"]},
            {"name": "second", "slice_ids": ["S3", "S4", "S5"]},
        ]
        self.assertEqual(scope.apply_ontology_plan(plan), ["ontology-1", "ontology-2"])
        self.assertEqual(client.created, [("second", "ontology-2")])
        # Re-applying on the same scope does not create anything new.
        self.assertEqual(scope.apply_ontology_plan(plan), ["ontology-1", "ontology-2"])
        self.assertEqual(client.created, [("second", "ontology-2")])
        # A fresh scope over the same project reuses the existing same-name
        # Ontology instead of duplicating it.
        resumed = PlatformScope(
            "http://example", "r30006-plan", lambda: ("admin", "admin-id"), lambda _: True, client
        )
        resumed.project_id = "project-1"
        resumed.ontology_id = "ontology-1"
        resumed.admin_key = "admin"
        self.assertEqual(resumed.apply_ontology_plan(plan), ["ontology-1", "ontology-2"])
        self.assertEqual(client.created, [("second", "ontology-2")])

    def test_apply_ontology_plan_rejects_structurally_invalid_plans(self) -> None:
        from modeling_team.platform_scope import PlatformScopeError

        scope = PlatformScope(
            "http://example", "r30006-plan", lambda: ("admin", "admin-id"), lambda _: True, self._client()
        )
        scope.prepare({"mode": "create"})
        for plan in (
            [{"name": "only", "slice_ids": ["S1"]}],
            [{"name": "a", "slice_ids": ["S1"]}, {"name": "a", "slice_ids": ["S2"]}],
            [{"name": "a", "slice_ids": []}, {"name": "b", "slice_ids": ["S2"]}],
            "not-a-plan",
        ):
            with self.subTest(plan=plan):
                with self.assertRaises(PlatformScopeError):
                    scope.apply_ontology_plan(plan)

    def test_protocol_context_lists_every_planned_ontology(self) -> None:
        scope = PlatformScope(
            "http://example", "r30006-plan", lambda: ("admin", "admin-id"), lambda _: True, self._client()
        )
        scope.prepare({"mode": "create"})
        single = scope.read_protocol_context()
        self.assertEqual(
            single,
            {
                "project_id": "project-1",
                "ontology_id": "ontology-1",
                "workspace_version": "version-ontology-1",
            },
        )
        scope.apply_ontology_plan(
            [
                {"name": "first", "slice_ids": ["S1", "S2"]},
                {"name": "second", "slice_ids": ["S3"]},
            ]
        )
        self.assertEqual(
            scope.read_protocol_context(),
            {
                "project_id": "project-1",
                "ontology_id": "ontology-1",
                "workspace_version": "version-ontology-1",
                "ontology_ids": "ontology-1,ontology-2",
            },
        )


class _MultiOntologyClient:
    """Platform HTTP double over one Project with two planned Ontologies."""

    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.written = False
        self.second_session_visible = True
        self.second_involved = ["ontology-2"]
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, path, body, key):
        self.calls.append((method, path))
        if method == "POST" and path == "/api/projects":
            return 201, {"id": "project-1"}
        if method == "POST" and path == "/api/projects/project-1/ontologies":
            if body.get("description") == "owned empty ontology":
                return 201, {"id": "ontology-1"}
            ontology_id = f"ontology-{len(self.created) + 2}"
            self.created.append((body["name"], ontology_id))
            return 201, {"id": ontology_id}
        if method == "GET" and path == "/api/projects/project-1/ontologies":
            rows = [{"id": "ontology-1", "name": "prebuilt"}] + [
                {"id": ontology_id, "name": name} for name, ontology_id in self.created
            ]
            return 200, rows
        if path.endswith("workspace-context"):
            return 200, {"state": "ready"}
        if path.endswith("modeling-batches"):
            return 200, ({"batches": [{"batch_id": "batch-1"}]} if self.written else {"items": []})
        if path.endswith("modeling-context"):
            ontology_id = path.split("/")[3]
            return 200, {
                "project": {"id": "project-1"},
                "ontology": {"id": ontology_id},
                "workspace": {"state": "ready", "workspace_version": f"version-{ontology_id}"},
            }
        if path.endswith("build-context"):
            recent = []
            if self.written:
                recent.append({"id": "session-1"})
                if self.second_session_visible:
                    recent.append({"id": "session-2"})
            return 200, {"agent_state": {"active_sessions": [], "recent_sessions": recent}}
        if path == "/api/build-sessions/session-1":
            return 200, {
                "session": {"id": "session-1", "project_id": "project-1", "status": "completed", "revision": 1},
                "involved_ontology_ids": ["ontology-1"],
                "modeling_batches": [],
                "leases": [{"state": "released"}],
            }
        if path == "/api/build-sessions/session-2":
            return 200, {
                "session": {"id": "session-2", "project_id": "project-1", "status": "completed", "revision": 1},
                "involved_ontology_ids": list(self.second_involved),
                "modeling_batches": [],
                "leases": [{"state": "released"}],
            }
        if method == "POST" and path.endswith("/members"):
            return 201, {"user_id": "operator-user"}
        if path == "/api/auth/me":
            return 200, {"user_id": "operator-user"}
        if path == "/api/api-keys":
            return 201, {"id": "model-key", "plaintext_key": "secret"}
        if path.endswith(":revoke"):
            return 200, {"revoked_at": "now"}
        return 200, {"id": "project-1"}


# --- T0-5c (M3): multi-Ontology terminal/retained aggregate ---


def _multi_scope(client, **overrides):
    scope = PlatformScope(
        "http://example", "r30006-aggregate", lambda: ("admin", "admin-id"), lambda _: True, client
    )
    scope.retain_nonempty = True
    scope.terminal_results = {
        role: {"status": "completed"}
        for role in ("coordinator", "modeling", "protocol")
    }
    scope.prepare({"mode": "create"})
    scope.ontology_ids = overrides.pop("ontology_ids", ["ontology-1", "ontology-2"])
    for key, value in overrides.items():
        setattr(client, key, value)
    return scope


class MultiOntologyTerminalAggregateTests(unittest.TestCase):
    def test_successful_multi_ontology_run_reaches_retained_pending_acceptance(self) -> None:
        client = _MultiOntologyClient()
        scope = _multi_scope(client, written=True)
        cleanup = scope.cleanup()
        self.assertEqual(cleanup["scope_disposition"], "retained-pending-acceptance")
        self.assertEqual(cleanup["ontology_ids"], ["ontology-1", "ontology-2"])
        self.assertEqual(
            cleanup["workspace_versions"],
            {"ontology-1": "version-ontology-1", "ontology-2": "version-ontology-2"},
        )
        self.assertEqual(
            cleanup["completed_session_ids"],
            {"ontology-1": "session-1", "ontology-2": "session-2"},
        )
        self.assertNotIn("workspace_version", cleanup)

    def test_foreign_or_missing_ontology_involvement_blocks_cleanup(self) -> None:
        for mode in ("foreign", "uncovered"):
            with self.subTest(mode=mode):
                client = _MultiOntologyClient()
                overrides = {"written": True}
                if mode == "foreign":
                    overrides["second_involved"] = ["foreign-ontology"]
                else:
                    overrides["second_session_visible"] = False
                scope = _multi_scope(client, **overrides)
                cleanup = scope.cleanup()
                self.assertEqual(cleanup["scope_disposition"], "blocked")
                self.assertIn("Ontology", cleanup["cleanup_blocker"])

    def test_duplicate_completed_session_for_one_ontology_is_a_success_blocker(self) -> None:
        client = _MultiOntologyClient()
        scope = _multi_scope(client, written=True, second_involved=["ontology-1"])
        cleanup = scope.cleanup()
        self.assertEqual(cleanup["scope_disposition"], "failed-written-retained")

    def test_multi_ontology_has_writes_covers_every_planned_ontology(self) -> None:
        # Default: neither planned Ontology has Modeling Batch history.
        empty = _multi_scope(_MultiOntologyClient())
        self.assertFalse(empty._has_writes())

        # The primary Ontology is empty but the second has writes: the
        # aggregate write check still reports the scope as written.
        class _PrimaryEmpty(_MultiOntologyClient):
            def __call__(self, method, path, body, key):
                if path == "/api/ontologies/ontology-1/modeling-batches":
                    return 200, {"items": []}
                if path.endswith("modeling-batches"):
                    return 200, {"batches": [{"batch_id": "batch-1"}]}
                return super().__call__(method, path, body, key)

        mixed = _multi_scope(_PrimaryEmpty())
        self.assertTrue(mixed._has_writes())

    def test_retained_handoff_evidence_records_the_ontology_set(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(repository_root=REPO_ROOT, adapter=SimpleNamespace())
            run_root = Path(directory) / "run"
            (run_root / "evidence").mkdir(parents=True)
            roles = ["coordinator", "modeling", "protocol"]
            runner.run = SimpleNamespace(
                run_id="r30006-retained",
                root=run_root,
                terminal_results={role: {"status": "completed"} for role in roles},
                configuration=SimpleNamespace(
                    profile=SimpleNamespace(
                        agents=[
                            SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
                            for role in roles
                        ]
                    )
                ),
            )
            scope = {
                "mode": "create",
                "owned": True,
                "project_id": "project-1",
                "ontology_id": "ontology-1",
                "ontology_ids": ["ontology-1", "ontology-2"],
                "workspace_versions": {
                    "ontology-1": "version-ontology-1",
                    "ontology-2": "version-ontology-2",
                },
                "completed_session_ids": {
                    "ontology-1": "session-1",
                    "ontology-2": "session-2",
                },
                "sessions_terminal": True,
                "protocol_key_revoked": True,
                "admin_key_revoked": True,
                "scope_disposition": "retained-pending-acceptance",
            }
            runner._write_retained_handoff_evidence(scope)
            payload = json.loads(
                (run_root / "evidence" / "retained-handoff-input.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                payload["scope"],
                {
                    "project_id": "project-1",
                    "ontology_id": "ontology-1",
                    "ontology_ids": ["ontology-1", "ontology-2"],
                    "workspace_versions": {
                        "ontology-1": "version-ontology-1",
                        "ontology-2": "version-ontology-2",
                    },
                    "completed_session_ids": {
                        "ontology-1": "session-1",
                        "ontology-2": "session-2",
                    },
                    "scope_disposition": "retained-pending-acceptance",
                    "owned": True,
                },
            )
            self.assertEqual(
                payload["terminal_statuses"], {role: "completed" for role in roles}
            )

    def test_retained_handoff_rejects_incomplete_multi_ontology_evidence(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            runner = TeamRunner(repository_root=REPO_ROOT, adapter=SimpleNamespace())
            run_root = Path(directory) / "run"
            (run_root / "evidence").mkdir(parents=True)
            roles = ["coordinator", "modeling", "protocol"]
            runner.run = SimpleNamespace(
                run_id="r30006-retained-incomplete",
                root=run_root,
                terminal_results={role: {"status": "completed"} for role in roles},
                configuration=SimpleNamespace(
                    profile=SimpleNamespace(
                        agents=[
                            SimpleNamespace(agent_id=role, package=SimpleNamespace(role=role))
                            for role in roles
                        ]
                    )
                ),
            )
            complete = {
                "mode": "create",
                "owned": True,
                "project_id": "project-1",
                "ontology_id": "ontology-1",
                "ontology_ids": ["ontology-1", "ontology-2"],
                "workspace_versions": {
                    "ontology-1": "version-ontology-1",
                    "ontology-2": "version-ontology-2",
                },
                "completed_session_ids": {
                    "ontology-1": "session-1",
                    "ontology-2": "session-2",
                },
                "sessions_terminal": True,
                "protocol_key_revoked": True,
                "admin_key_revoked": True,
                "scope_disposition": "retained-pending-acceptance",
            }
            for mutation in (
                {"workspace_versions": {"ontology-1": "version-ontology-1"}},
                {"completed_session_ids": {"ontology-1": "session-1", "ontology-2": ""}},
                {"ontology_ids": ["ontology-1", "ontology-3"]},
            ):
                with self.subTest(mutation=mutation):
                    scope = dict(complete)
                    scope.update(mutation)
                    with self.assertRaisesRegex(
                        TeamConfigurationError, "multi-Ontology scope evidence is incomplete"
                    ):
                        runner._write_retained_handoff_evidence(scope)
            self.assertFalse((run_root / "evidence" / "retained-handoff-input.json").exists())


if __name__ == "__main__":
    unittest.main()
