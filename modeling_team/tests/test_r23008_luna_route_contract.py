"""R2.3-008 Luna full-stack route carrier: deterministic contract/asset/ledger tests.

These tests stay below the real-run boundary: no model or provider process is
started, no real ledger under ``workspaces/modeling-runs`` is touched (temp
directories only), and the subscription preflight is exercised through its
injected seam.  The real Luna formal run belongs to the bounded test round.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace
from unittest.mock import patch

from modeling_team import __main__ as team_main
from modeling_team.acceptance import (
    RunnerAcceptanceCarrier,
    modeling_receipt_digest,
    ticket_digest,
)
from modeling_team.contracts import TeamConfigurationError, load_formal_team_configuration
from modeling_team.formal_runs import (
    FORMAL_RUN_CONTRACTS,
    R2_3_003_CONTRACT,
    R2_3_005_CONTRACT,
    R2_3_008_CONTRACT,
    formal_run_contract_for,
    load_formal_run_configuration,
    validate_formal_run_contract_assets,
)
from modeling_team.model_routing import load_team_model_profile, profile_requires_codex_subscription_auth
from modeling_team.preflight import normalize_formal_scope
from modeling_team.runner import TeamRunner
from modeling_team.start_ledger import StartLedger, resolve_ledger_config
from modeling_team.tests.test_r23005_contracts import _ticket


ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "modeling_team/profiles/r2-3-008-modeling-team.yaml"
TASK_PATH = ROOT / "modeling_team/tasks/r2-3-008-formal-acceptance.yaml"
STANDARD_PATH = ROOT / "modeling_team/references/r2-3-008-acceptance-standard.json"

_TEST_FORMAL_CREDENTIAL = Path(tempfile.mkdtemp(prefix="r23008-formal-credential-")) / "deepseek.env"
_TEST_FORMAL_CREDENTIAL.write_text("DEEPSEEK_API_KEY=round23-test-sentinel\n", encoding="utf-8")
_TEST_FORMAL_CREDENTIAL.chmod(0o600)

_NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _ledger(root: Path) -> StartLedger:
    return StartLedger(root, requirement_id="R2.3-008", now=lambda: _NOW)


def _consume_start(ledger: StartLedger, run_id: str, *, failure: str | None) -> None:
    ledger.reserve(run_id, f"baseline-{run_id}", _NOW.isoformat())
    ledger.mark_semantic_start(run_id)
    if failure is not None:
        ledger.terminal_failure(run_id, failure, False)


class R23008ContractTests(unittest.TestCase):
    def test_a1_new_pair_resolves_the_closed_r23008_contract(self) -> None:
        configuration, contract = load_formal_run_configuration(PROFILE_PATH, TASK_PATH, root=ROOT)
        self.assertIs(contract, R2_3_008_CONTRACT)
        self.assertIs(formal_run_contract_for(configuration), R2_3_008_CONTRACT)
        self.assertIs(
            formal_run_contract_for(
                profile_id="r2-3-008-modeling-team", task_id="r2-3-008-formal-acceptance"
            ),
            R2_3_008_CONTRACT,
        )
        self.assertEqual(contract.scope_mode, "create")
        self.assertEqual(contract.default_model_profile_id, "openai-luna-medium")
        self.assertEqual(contract.ledger_requirement_id, "R2.3-008")

    def test_a2_cross_wired_pairs_fail_closed(self) -> None:
        for profile_id, task_id in (
            ("r2-3-008-modeling-team", "r2-3-005-formal-acceptance"),
            ("r2-3-005-modeling-team", "r2-3-008-formal-acceptance"),
            ("r2-3-008-modeling-team", "r2-3-003-existing-scope-incremental"),
        ):
            with self.subTest(profile_id=profile_id, task_id=task_id):
                self.assertIsNone(formal_run_contract_for(profile_id=profile_id, task_id=task_id))
        with self.assertRaisesRegex(TeamConfigurationError, "unknown or cross-wired"):
            load_formal_run_configuration(
                PROFILE_PATH, ROOT / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml", root=ROOT
            )
        with self.assertRaisesRegex(TeamConfigurationError, "unknown or cross-wired"):
            load_formal_run_configuration(
                ROOT / "modeling_team/profiles/r2-3-005-modeling-team.yaml", TASK_PATH, root=ROOT
            )

    def _patched_configuration(self, **parameter_overrides: object) -> SimpleNamespace:
        configuration = load_formal_team_configuration(PROFILE_PATH, TASK_PATH, root=ROOT)
        parameters = dict(configuration.profile.parameters)
        parameters.update(parameter_overrides)
        return SimpleNamespace(
            profile=SimpleNamespace(
                profile_id=configuration.profile.profile_id,
                parameters=parameters,
                agents=configuration.profile.agents,
            ),
            task=configuration.task,
        )

    def test_a3_authoritative_path_and_parameter_bindings_reject_drift(self) -> None:
        # Authoritative path: a loaded 008 identity presented through the 005
        # Profile file is rejected before any run side effect.
        with patch(
            "modeling_team.formal_runs.load_formal_team_configuration",
            side_effect=lambda *_args, **_kwargs: self._patched_configuration(),
        ), self.assertRaisesRegex(
            TeamConfigurationError, "formal Profile path is not the authoritative contract asset"
        ):
            load_formal_run_configuration(
                ROOT / "modeling_team/profiles/r2-3-005-modeling-team.yaml", TASK_PATH, root=ROOT
            )
        drifts = (
            {"formal_contract": "r2-3-005-formal-create"},
            {
                "acceptance_standard": (
                    "modeling_team/references/r2-3-005-acceptance-standard.json"
                )
            },
        )
        for parameters in drifts:
            with self.subTest(parameters=parameters), patch(
                "modeling_team.formal_runs.load_formal_team_configuration",
                side_effect=lambda *_args, _parameters=parameters, **_kwargs: (
                    self._patched_configuration(**_parameters)
                ),
            ), self.assertRaisesRegex(TeamConfigurationError, "drifts"):
                load_formal_run_configuration(PROFILE_PATH, TASK_PATH, root=ROOT)

    def test_a3_unavailable_or_symlinked_formal_assets_reject(self) -> None:
        with patch(
            "modeling_team.formal_runs.load_formal_team_configuration",
            side_effect=lambda *_args, **_kwargs: self._patched_configuration(),
        ):
            with patch.object(
                Path,
                "is_file",
                new=lambda self: self.name != "openai-luna-medium.yaml",
            ), self.assertRaisesRegex(TeamConfigurationError, "formal model profile is unavailable"):
                load_formal_run_configuration(PROFILE_PATH, TASK_PATH, root=ROOT)
            with patch.object(
                Path,
                "is_symlink",
                new=lambda self: self.name == "r2-3-008-acceptance-standard.json",
            ), self.assertRaisesRegex(
                # The symlinked standard is rejected fail-closed: the v2 Task
                # role-source gate fires first with its own unavailable message,
                # and the formal asset loop would reject it identically.
                TeamConfigurationError,
                "unavailable.*r2-3-008-acceptance-standard.json",
            ):
                load_formal_run_configuration(PROFILE_PATH, TASK_PATH, root=ROOT)

    def test_a4_deletion_policy_stays_none_and_restricted_to_r23003(self) -> None:
        self.assertIsNone(R2_3_008_CONTRACT.deletion_policy)
        validate_formal_run_contract_assets(R2_3_008_CONTRACT)
        drifted = replace(R2_3_008_CONTRACT, deletion_policy={"targets": []})
        with self.assertRaisesRegex(
            TeamConfigurationError, "deletion policy is restricted to R2.3-003"
        ):
            validate_formal_run_contract_assets(drifted)

    def test_a5_existing_contracts_register_unchanged(self) -> None:
        self.assertIn(R2_3_005_CONTRACT, FORMAL_RUN_CONTRACTS)
        self.assertIn(R2_3_003_CONTRACT, FORMAL_RUN_CONTRACTS)
        self.assertEqual(
            [contract.contract_id for contract in FORMAL_RUN_CONTRACTS],
            [
                "r2-3-005-formal-create",
                "r2-3-003-existing-incremental",
                "r2-3-008-luna-route-create",
            ],
        )
        self.assertEqual(R2_3_005_CONTRACT.default_model_profile_id, "deepseek-v4-flash-max")
        self.assertEqual(R2_3_005_CONTRACT.profile_id, "r2-3-005-modeling-team")
        self.assertEqual(R2_3_003_CONTRACT.profile_id, "r2-3-003-modeling-team")
        self.assertIsNotNone(R2_3_003_CONTRACT.deletion_policy)

    def test_a6_closed_profile_id_registration_gates_candidate_progress_timeout(self) -> None:
        # Positive: the registered 008 Profile carries the formal 300s timeout
        # through the strict loader.
        configuration = load_formal_team_configuration(PROFILE_PATH, TASK_PATH, root=ROOT)
        self.assertEqual(configuration.profile.parameters["candidate_progress_timeout_seconds"], 300)
        # Negative: the same parameter on an unregistered Profile ID is still
        # rejected by the closed-set membership gate.
        with tempfile.TemporaryDirectory() as directory:
            drifted = Path(directory) / "unregistered-profile.yaml"
            drifted.write_text(
                PROFILE_PATH.read_text(encoding="utf-8").replace(
                    "profile_id: r2-3-008-modeling-team",
                    "profile_id: r2-3-008-unregistered-team",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                TeamConfigurationError,
                "candidate progress timeout is restricted to the formal Profile",
            ):
                load_formal_team_configuration(drifted, TASK_PATH, root=ROOT)

    def test_a7_formal_deferred_pump_covers_the_new_task_id(self) -> None:
        class PumpResource:
            def __init__(self, spec: dict[str, object]) -> None:
                self.spec = spec
                self.stopped = False
                self.destroyed = False

            def activate_output_pump(self) -> None:
                return None

            def stop(self) -> None:
                self.stopped = True

            def destroy(self) -> None:
                self.destroyed = True

        def _start(task_id: str, specs: list[dict[str, object]]) -> None:
            resources: list[PumpResource] = []

            def factory(spec: dict[str, object]) -> PumpResource:
                resource = PumpResource(spec)
                resources.append(resource)
                return resource

            ticket = _ticket("r23008-pump")
            ticket["task_id"] = task_id
            if task_id == "r2-3-003-existing-scope-incremental":
                # The 003 ticket contract projects the accepted candidate
                # revision as the numeric slice revision.
                ticket["slice_revision"] = "1"
                for receipt in ticket["modeling_receipts"]:
                    receipt["slice_revision"] = "1"
                    receipt["receipt_digest"] = modeling_receipt_digest(receipt)
            ticket["ticket_digest"] = ticket_digest(ticket)
            for receipt in ticket["modeling_receipts"]:
                receipt["evidence_ref"]["ticket_digest"] = ticket["ticket_digest"]
            with tempfile.TemporaryDirectory(prefix="r23008-pump-") as directory:
                carrier = RunnerAcceptanceCarrier(
                    Path(directory),
                    task_id=task_id,
                    acceptance_id="acceptance",
                    child_factory=factory,
                )
                carrier.publish_ticket(
                    ticket,
                    coordinator_id="coordinator",
                    owner_revision=ticket["quality_standard_ref"],
                )
                carrier.ack_ticket(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    ticket_digest_value=ticket["ticket_digest"],
                )
                projection, digest = carrier.project_child_input(
                    round_id=ticket["acceptance_round_id"], kind="source"
                )
                carrier.start_child(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    kind="source",
                    input_ref=projection,
                    input_digest=digest,
                    ticket_digest_value=ticket["ticket_digest"],
                    request_id=f"pump-{task_id}",
                    attempt=0,
                )
                specs.extend(resource.spec for resource in resources)
                carrier.cleanup()

        formal_specs: list[dict[str, object]] = []
        _start("r2-3-008-formal-acceptance", formal_specs)
        self.assertTrue(formal_specs[0]["defer_output_pump"])
        unchanged_005: list[dict[str, object]] = []
        _start("r2-3-005-formal-acceptance", unchanged_005)
        self.assertTrue(unchanged_005[0]["defer_output_pump"])
        unchanged_003: list[dict[str, object]] = []
        _start("r2-3-003-existing-scope-incremental", unchanged_003)
        self.assertTrue(unchanged_003[0]["defer_output_pump"])
        nonformal_specs: list[dict[str, object]] = []
        _start("task-r23005", nonformal_specs)
        self.assertNotIn("defer_output_pump", nonformal_specs[0])


class R23008LedgerTests(unittest.TestCase):
    def test_b1_resolver_returns_the_exact_formal_mirror_policy(self) -> None:
        config = resolve_ledger_config("R2.3-008")
        self.assertEqual(config.ledger_filename, ".r2-3-008-start-ledger.jsonl")
        self.assertEqual(config.lock_filename, ".r2-3-008-start-ledger.lock")
        self.assertEqual(config.initial_start_cap, 3)
        self.assertEqual(config.authorization_increment, 3)
        self.assertTrue(config.strict_sequence)
        self.assertTrue(config.allow_incomplete_modeling_quality_repair)
        self.assertTrue(config.allow_variable_authorization)
        for kwargs in (
            {"ledger_filename": ".r2-3-005-start-ledger.jsonl"},
            {"lock_filename": ".r2-3-005-start-ledger.lock"},
            {"initial_start_cap": 1},
            {"authorization_increment": 4},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(
                TeamConfigurationError, "does not match requirement configuration"
            ):
                resolve_ledger_config("R2.3-008", **kwargs)
        with self.assertRaisesRegex(TeamConfigurationError, "unknown start-ledger requirement ID"):
            resolve_ledger_config("R2.3-009")

    def test_b2_budget_gates_three_starts_and_one_active_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = _ledger(Path(directory))
            for index in range(3):
                run_id = f"r23008-start{index + 1}"
                ledger.reserve(run_id, f"baseline-{index}", _NOW.isoformat())
                # A second reservation while one is active is rejected.
                with self.assertRaisesRegex(
                    TeamConfigurationError, "another R2.3-008 start reservation is active"
                ):
                    ledger.reserve(f"r23008-shadow-{index}", f"baseline-shadow-{index}", _NOW.isoformat())
                ledger.mark_semantic_start(run_id)
                ledger.terminal_failure(run_id, "collaboration/routing", False)
            with self.assertRaisesRegex(
                TeamConfigurationError, "R2.3-008 semantic-start budget is exhausted"
            ):
                ledger.reserve("r23008-start4", "baseline-3", _NOW.isoformat())

    def test_b3_completed_start_without_terminal_failure_closes_the_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = _ledger(Path(directory))
            _consume_start(ledger, "r23008-start1", failure=None)
            with self.assertRaisesRegex(
                TeamConfigurationError, "previous semantic start lacks a terminal failure"
            ):
                ledger.reserve("r23008-start2", "baseline-2", _NOW.isoformat())

    def test_b4_terminal_failure_and_budget_extension_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = _ledger(Path(directory))
            _consume_start(ledger, "r23008-start1", failure=None)
            # A failure must classify the latest semantic start.
            with self.assertRaisesRegex(
                TeamConfigurationError, "terminal failure must classify the latest semantic start"
            ):
                ledger.terminal_failure("r23008-other", "collaboration/routing", False)
            ledger.terminal_failure("r23008-start1", "collaboration/routing", False)
            # Extension before the initial budget is consumed is rejected.
            with self.assertRaisesRegex(
                TeamConfigurationError, "budget authorization is not yet consumed"
            ):
                ledger.authorize_budget(3, "authorization-one", "user-reference-one")
            for index in (2, 3):
                _consume_start(ledger, f"r23008-start{index}", failure="collaboration/routing")
            # Consumed cap plus a classified latest failure opens the extension.
            ledger.authorize_budget(3, "authorization-one", "user-reference-one")
            with self.assertRaisesRegex(TeamConfigurationError, "budget authorization is immutable"):
                ledger.authorize_budget(3, "authorization-one", "user-reference-two")
            with self.assertRaisesRegex(TeamConfigurationError, "budget authorization is immutable"):
                ledger.authorize_budget(3, "authorization-two", "user-reference-one")
            ledger.reserve("r23008-start4", "baseline-4", _NOW.isoformat())
            records = ledger._records()
            self.assertEqual(ledger._semantic_start_count(records), 3)
            self.assertEqual(ledger._start_cap(records), 6)

    def test_b5_initial_authorization_is_r23003_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = _ledger(Path(directory))
            with self.assertRaisesRegex(
                TeamConfigurationError, "initial authorization is R2.3-003-only"
            ):
                ledger.initial_authorization()

    def test_b6_strict_replay_rejects_tampered_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = _ledger(Path(directory))
            _consume_start(ledger, "r23008-start1", failure="collaboration/routing")
            lines = ledger.path.read_text(encoding="utf-8").splitlines()
            # Duplicate a semantic_start record: replay must fail closed.
            duplicated = [
                line for line in lines if json.loads(line).get("event") == "semantic_start"
            ][0]
            ledger.path.write_text(
                "\n".join([*lines, duplicated]) + "\n", encoding="utf-8"
            )
            with self.assertRaises(TeamConfigurationError):
                ledger.reserve("r23008-start2", "baseline-2", _NOW.isoformat())
            # Out-of-order records are rejected as well.
            reordered = "\n".join([lines[1], lines[0], *lines[2:]]) + "\n"
            ledger.path.write_text(reordered, encoding="utf-8")
            with self.assertRaises(TeamConfigurationError):
                ledger.reserve("r23008-start3", "baseline-3", _NOW.isoformat())


class R23008StandardTests(unittest.TestCase):
    def _policy(self, standard: dict[str, object], root: Path) -> dict[str, object]:
        probe = object.__new__(TeamRunner)
        probe.repository_root = root
        relative = "modeling_team/references/r2-3-008-acceptance-standard.json"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(standard, ensure_ascii=False), encoding="utf-8")
        configuration = SimpleNamespace(
            profile=SimpleNamespace(parameters={"acceptance_standard": relative}),
            task=SimpleNamespace(task_id="r2-3-008-formal-acceptance"),
        )
        return probe._acceptance_ticket_policy(configuration)

    def test_c2_standard_parses_with_two_cqs_and_frozen_digest(self) -> None:
        import yaml

        probe = object.__new__(TeamRunner)
        probe.repository_root = ROOT
        configuration = load_formal_team_configuration(PROFILE_PATH, TASK_PATH, root=ROOT)
        policy = probe._acceptance_ticket_policy(configuration)
        self.assertEqual(
            policy["quality_standard_ref"], "docs/requirements/requirements-v2.3.md#R2.3-008"
        )
        self.assertEqual(
            policy["quality_standard_digest"],
            hashlib.sha256(STANDARD_PATH.read_bytes()).hexdigest(),
        )
        standard = yaml.safe_load(STANDARD_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            [question["id"] for question in standard["competency_questions"]],
            ["cq-001", "cq-002"],
        )
        self.assertEqual(standard["unknown_policy"], "preserve-explicit-unknown")
        self.assertEqual(standard["schema_version"], "r2-3-008-acceptance-standard/v1")

    def test_c3_standard_shape_drift_fails_closed(self) -> None:
        import copy

        import yaml

        standard = yaml.safe_load(STANDARD_PATH.read_text(encoding="utf-8"))
        base = json.loads(json.dumps(standard))
        # Note: the ticket-policy schema requires at least one CQ; the
        # exactly-two cq-001/cq-002 contract is the runner-injected Acceptance
        # instruction text (C2 asserts that exact ID set), not a schema field.
        duplicated = copy.deepcopy(base)
        duplicated["competency_questions"][1]["id"] = "cq-001"
        extra_field = copy.deepcopy(base)
        extra_field["competency_questions"][0]["expected_answer"] = "hidden"
        wrong_unknown = copy.deepcopy(base)
        wrong_unknown["unknown_policy"] = "fill-best-guess"
        missing_paths = copy.deepcopy(base)
        missing_paths["competency_questions"][0]["approved_source_paths"] = []
        for label, drifted in (
            ("duplicated-ids", duplicated),
            ("extra-field", extra_field),
            ("wrong-unknown-policy", wrong_unknown),
            ("empty-source-paths", missing_paths),
        ):
            with self.subTest(drift=label), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(TeamConfigurationError):
                    self._policy(drifted, Path(directory))

    def test_c4_task_objective_and_surfaces_mirror_r23005(self) -> None:
        import yaml

        new = yaml.safe_load(TASK_PATH.read_text(encoding="utf-8"))
        old = yaml.safe_load(
            (ROOT / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            new["objective"],
            old["objective"].replace(
                "For formal R2.3-005, every `relation` item",
                "For formal R2.3-008 (reusing the R2.3-005 slice contract), "
                "every `relation` item",
            ),
        )
        # No route/terminal or "quality does not gate" wording leaked into the
        # role-facing objective.
        self.assertNotIn("route", new["objective"])
        self.assertNotIn("terminal evidence", new["objective"])
        for field in (
            "role_sources",
            "protocol_tools",
            "expected_terminal_evidence",
            "semantic_start_evidence",
            "retain_nonempty",
        ):
            mirrored = old[field]
            if field == "role_sources":
                mirrored = [
                    {
                        **source,
                        "path": source["path"].replace(
                            "r2-3-005-acceptance-standard.json",
                            "r2-3-008-acceptance-standard.json",
                        ),
                    }
                    for source in mirrored
                ]
            self.assertEqual(new[field], mirrored, field)
        acceptance_source = [
            source
            for source in new["role_sources"]
            if "acceptance" in source["roles"]
        ]
        self.assertEqual(
            [source["path"] for source in acceptance_source],
            ["modeling_team/references/r2-3-008-acceptance-standard.json"],
        )

    def test_c5_baseline_freezes_the_same_model_profile_digest(self) -> None:
        manifest, baseline_hash = TeamRunner.preview_baseline(
            repository_root=ROOT,
            run_id="r23008-baseline-probe",
            profile_path=PROFILE_PATH,
            task_path=TASK_PATH,
        )
        binding = manifest["team_model_profile"]
        self.assertEqual(binding["profile_id"], "openai-luna-medium")
        self.assertEqual(
            binding["sha256"],
            hashlib.sha256(
                (ROOT / "modeling_team/model-profiles/openai-luna-medium.yaml").read_bytes()
            ).hexdigest(),
        )
        again, second_hash = TeamRunner.preview_baseline(
            repository_root=ROOT,
            run_id="r23008-baseline-probe",
            profile_path=PROFILE_PATH,
            task_path=TASK_PATH,
        )
        self.assertEqual(baseline_hash, second_hash)
        self.assertEqual(manifest, again)


class R23008ModelProfileTests(unittest.TestCase):
    def test_d1_contract_default_is_luna_not_the_deepseek_default(self) -> None:
        self.assertEqual(
            team_main._resolve_model_profile_selection(None, R2_3_008_CONTRACT),
            "openai-luna-medium",
        )
        self.assertIsNone(team_main._resolve_model_profile_selection(None, None))
        self.assertEqual(
            team_main._resolve_model_profile_selection("deepseek-v4-flash-max", R2_3_008_CONTRACT),
            "deepseek-v4-flash-max",
        )
        with self.assertRaisesRegex(
            TeamConfigurationError, "model profile selection requires a formal run contract"
        ):
            team_main._resolve_model_profile_selection("openai-luna-medium", None)

    def test_d2_luna_profile_projects_six_safe_role_bindings(self) -> None:
        profile = load_team_model_profile(ROOT, "openai-luna-medium")
        self.assertTrue(profile_requires_codex_subscription_auth(profile))
        encoded = json.dumps(profile.as_dict(), ensure_ascii=False)
        for package_id in (
            "coordinator",
            "modeling",
            "protocol",
            "acceptance",
            "source-examiner",
            "platform-examiner",
        ):
            binding = profile.binding_for(package_id)
            self.assertEqual(binding.provider_id, "openai-codex")
            self.assertEqual(binding.model, "gpt-5.6-luna")
            self.assertEqual(binding.requested_effort, "medium")
            self.assertEqual(binding.effective_effort, "medium")
        for forbidden in ("endpoint", "credential", "token", "api_key", "auth.json"):
            self.assertNotIn(forbidden, encoded)
        self.assertIn("chatgpt-subscription", encoded)

    def _runner(
        self,
        ledger_root: Path,
        events: list[str] | None = None,
        *,
        freeze: str | None = None,
    ) -> TeamRunner:
        def prestart(**kwargs: object) -> dict[str, object]:
            if events is not None:
                events.append("canonical")
            return {"status_code": 200, "product_write_mode": "rdf_primary"}

        return TeamRunner(
            repository_root=ROOT,
            adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
            deepseek_credential_path=_TEST_FORMAL_CREDENTIAL,
            ledger_factory=lambda *, root, config, now: StartLedger(root, config=config, now=now),
            freeze_started_at=freeze or _NOW.isoformat(),
            prestart_preflight=prestart,
        )

    def test_d3_subscription_preflight_gates_before_any_run_or_ledger_side_effect(self) -> None:
        events: list[str] = []
        run_root = ROOT / "workspaces" / "modeling-runs" / "r23008-preflight-fail-probe"
        ledger_root = Path(tempfile.mkdtemp(prefix="r23008-ledger-")) / "ledger"
        runner = self._runner(ledger_root, events)
        runner._canonical_ledger_root = lambda: ledger_root

        def failing_subscription() -> str:
            events.append("subscription")
            raise TeamConfigurationError("codex-subscription-auth-unavailable")

        try:
            with patch(
                "modeling_team.runner.preflight_codex_subscription_auth",
                side_effect=failing_subscription,
            ), self.assertRaisesRegex(
                TeamConfigurationError, "codex-subscription-auth-unavailable"
            ):
                runner.prepare(
                    run_id="r23008-preflight-fail-probe",
                    profile_path=PROFILE_PATH,
                    task_path=TASK_PATH,
                    scope={"mode": "create"},
                )
            self.assertEqual(events, ["subscription"])
            self.assertFalse(run_root.exists())
            self.assertFalse(ledger_root.exists())
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)
            rmtree(ledger_root.parent)

    def test_d3_prepare_uses_contract_default_and_freezes_luna_binding(self) -> None:
        run_root = ROOT / "workspaces" / "modeling-runs" / "r23008-prepare-default-probe"
        ledger_root = Path(tempfile.mkdtemp(prefix="r23008-ledger-")) / "ledger"
        runner = self._runner(ledger_root, freeze=datetime.now(UTC).isoformat())
        runner._canonical_ledger_root = lambda: ledger_root
        try:
            with patch(
                "modeling_team.runner.preflight_codex_subscription_auth",
                return_value="chatgpt-subscription",
            ) as subscription, patch(
                "modeling_team.preflight.capture_clean_checkout",
                return_value={
                    "repository_root": str(ROOT),
                    "head": "a" * 40,
                    "status_porcelain": "",
                    "status_digest": "b" * 64,
                },
            ):
                run = runner.prepare(
                    run_id="r23008-prepare-default-probe",
                    profile_path=PROFILE_PATH,
                    task_path=TASK_PATH,
                    scope={"mode": "create"},
                )
            subscription.assert_called_once_with()
            self.assertEqual(runner.codex_subscription_auth_mode, "chatgpt-subscription")
            assert run.team_model_profile is not None
            self.assertEqual(run.team_model_profile.profile_id, "openai-luna-medium")
            self.assertEqual(run.scope, {"mode": "create"})
            self.assertEqual(normalize_formal_scope(run.scope), {"mode": "create"})
            self.assertIsNotNone(runner._candidate_progress)
            self.assertEqual(runner._candidate_progress.timeout_seconds, 300.0)
            records = StartLedger(ledger_root, requirement_id="R2.3-008")._records()
            self.assertEqual([record["event"] for record in records], ["reservation"])
            self.assertEqual(records[0]["run_id"], "r23008-prepare-default-probe")
        finally:
            runner.cleanup()
            if run_root.exists():
                rmtree(run_root)
            rmtree(ledger_root.parent)

    def test_d4_shared_selection_branch_keeps_explicit_override(self) -> None:
        # All three CLI commands resolve through this one seam; an explicit
        # formal profile id passes unchanged while non-formal stays rejected.
        self.assertEqual(
            team_main._resolve_model_profile_selection("openai-luna-medium", R2_3_008_CONTRACT),
            "openai-luna-medium",
        )
        with self.assertRaises(TeamConfigurationError):
            team_main._resolve_model_profile_selection("openai-luna-medium", None)


if __name__ == "__main__":
    unittest.main()
